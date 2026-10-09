"""
Font Descriptor, ToUnicode CMap, and FontTools Outline Parser.
Recovers exact glyph advance widths, font metrics (ascent/descent/cap_height),
and glyph bounding boxes from embedded TrueType/CFF fonts, ToUnicode CMaps,
standard 14 base font AFM tables, and Type0 / CIDFont metric arrays.
"""

from __future__ import annotations
import io
import re
from typing import Dict, Tuple, Optional, Any, List
import pymupdf
from pdf_analyzer.l0_bytes.primitives import FontMetrics

STANDARD_14_CANDIDATES = [
    "Helvetica-BoldOblique",
    "Helvetica-Bold",
    "Helvetica-Oblique",
    "Helvetica",
    "Times-BoldItalic",
    "Times-Bold",
    "Times-Italic",
    "Times-Roman",
    "Courier-BoldOblique",
    "Courier-Bold",
    "Courier-Oblique",
    "Courier",
    "Symbol",
    "ZapfDingbats",
]

_STD_FONT_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_std_font_metrics(font_name: str) -> Optional[Dict[str, Any]]:
    clean = font_name.split("+")[-1].replace(" ", "").replace(",", "-")
    matched = None
    for cand in STANDARD_14_CANDIDATES:
        if cand.lower() in clean.lower():
            matched = cand
            break
    if not matched:
        if "times" in clean.lower():
            matched = "Times-Roman"
        elif "helv" in clean.lower() or "arial" in clean.lower():
            matched = "Helvetica"
        elif "cour" in clean.lower():
            matched = "Courier"
        else:
            matched = "Helvetica"

    if matched in _STD_FONT_CACHE:
        return _STD_FONT_CACHE[matched]

    try:
        f = pymupdf.Font(matched)
        units_per_em = 1000.0
        ascent = float(f.ascender) * 1000.0 if f.ascender else 800.0
        descent = float(f.descender) * 1000.0 if f.descender else -200.0
        widths: Dict[int, float] = {}
        for c in range(256):
            adv = float(f.glyph_advance(c)) * 1000.0
            if adv > 0:
                widths[c] = adv
        entry = {
            "matched_name": matched,
            "units_per_em": units_per_em,
            "ascent": ascent,
            "descent": descent,
            "widths": widths,
            "default_width": widths.get(32, 500.0),
        }
        _STD_FONT_CACHE[matched] = entry
        return entry
    except Exception:
        return None


def parse_to_unicode_cmap(cmap_bytes: bytes) -> Dict[int, str]:
    """
    Parses a PDF ToUnicode CMap stream and maps character/CID codes to Unicode strings.
    """
    mapping: Dict[int, str] = {}
    if not cmap_bytes:
        return mapping

    text = cmap_bytes.decode("latin1", errors="replace")

    # Parse beginbfchar / endbfchar blocks
    bfchar_blocks = re.findall(r"(\d+)\s+beginbfchar\s*(.*?)\s*endbfchar", text, re.DOTALL)
    for count, block in bfchar_blocks:
        pairs = re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", block)
        for src_hex, dst_hex in pairs:
            try:
                src_code = int(src_hex, 16)
                dst_bytes = bytes.fromhex(dst_hex)
                dst_str = dst_bytes.decode("utf-16-be", errors="replace")
                mapping[src_code] = dst_str
            except Exception:
                pass

    # Parse beginbfrange / endbfrange blocks
    bfrange_blocks = re.findall(r"(\d+)\s+beginbfrange\s*(.*?)\s*endbfrange", text, re.DOTALL)
    for count, block in bfrange_blocks:
        # Format 1: <start> <end> <dest_start>
        ranges = re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", block)
        for start_hex, end_hex, dst_start_hex in ranges:
            try:
                start_code = int(start_hex, 16)
                end_code = int(end_hex, 16)
                dst_start_val = int(dst_start_hex, 16)
                for offset in range(end_code - start_code + 1):
                    code = start_code + offset
                    target_val = dst_start_val + offset
                    mapping[code] = chr(target_val)
            except Exception:
                pass

        # Format 2: <start> <end> [ <dest1> <dest2> ... ]
        array_ranges = re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*\[(.*?)\]", block, re.DOTALL)
        for start_hex, end_hex, arr_str in array_ranges:
            try:
                start_code = int(start_hex, 16)
                dest_hexes = re.findall(r"<([0-9a-fA-F]+)>", arr_str)
                for offset, d_hex in enumerate(dest_hexes):
                    code = start_code + offset
                    d_bytes = bytes.fromhex(d_hex)
                    mapping[code] = d_bytes.decode("utf-16-be", errors="replace")
            except Exception:
                pass

    return mapping


def parse_cid_widths(w_array: Any) -> Dict[int, float]:
    """
    Parses a PDF CIDFont /W array into a mapping of {cid: width_pt}.
    """
    widths: Dict[int, float] = {}
    if not w_array:
        return widths

    w_list = list(w_array)
    i = 0
    while i < len(w_list):
        item = w_list[i]
        if i + 1 < len(w_list) and (isinstance(w_list[i + 1], (list, tuple, pymupdf.Rect)) or hasattr(w_list[i + 1], "__iter__")):
            if not isinstance(w_list[i + 1], (int, float, str)):
                start_cid = int(item)
                for idx, w in enumerate(w_list[i + 1]):
                    widths[start_cid + idx] = float(w)
                i += 2
                continue
        elif i + 1 < len(w_list) and hasattr(w_list[i + 1], "__iter__") and not isinstance(w_list[i + 1], (int, float)):
            start_cid = int(item)
            for idx, w in enumerate(w_list[i + 1]):
                widths[start_cid + idx] = float(w)
            i += 2
        elif i + 2 < len(w_list):
            c_first = int(item)
            c_last = int(w_list[i + 1])
            w_val = float(w_list[i + 2])
            for c in range(c_first, c_last + 1):
                widths[c] = w_val
            i += 3
        else:
            i += 1
    return widths


def parse_embedded_font_metrics(font_file_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Uses FontTools to extract exact glyph metrics and outlines from embedded TTF/OTF font streams.
    """
    if not font_file_bytes:
        return None
    try:
        from fontTools.ttLib import TTFont
        font_stream = io.BytesIO(font_file_bytes)
        tt = TTFont(font_stream)

        units_per_em = float(tt.get("head").unitsPerEm) if "head" in tt else 1000.0
        ascent = float(tt["hhea"].ascent) if "hhea" in tt else 800.0
        descent = float(tt["hhea"].descent) if "hhea" in tt else -200.0

        widths: Dict[str, float] = {}
        if "hmtx" in tt:
            for gname, (adv, lsb) in tt["hmtx"].metrics.items():
                widths[gname] = float(adv)

        glyph_bboxes: Dict[str, Tuple[float, float, float, float]] = {}
        if "glyf" in tt:
            for gname, glyph in tt["glyf"].glyphs.items():
                if hasattr(glyph, "xMin"):
                    glyph_bboxes[gname] = (
                        float(glyph.xMin),
                        float(glyph.yMin),
                        float(glyph.xMax),
                        float(glyph.yMax),
                    )

        return {
            "units_per_em": units_per_em,
            "ascent": ascent,
            "descent": descent,
            "widths": widths,
            "glyph_bboxes": glyph_bboxes,
        }
    except Exception:
        return None


def create_font_metrics(
    font_name: str,
    base_font: str,
    font_dict: Optional[Dict[str, Any]] = None,
    font_file_bytes: Optional[bytes] = None,
    to_unicode_bytes: Optional[bytes] = None,
) -> FontMetrics:
    """
    Constructs a FontMetrics instance synthesizing dictionary metadata, ToUnicode CMap,
    FontTools embedded metrics, CIDFont /W arrays, and standard 14 AFM fallbacks.
    """
    from pdf_analyzer.l0_bytes.font_manager import parse_font_name_parts, get_best_fallback_font

    prefix, clean_fam = parse_font_name_parts(base_font or font_name)
    is_t0 = bool(font_dict.get("is_type0", False)) if font_dict else False
    is_t3 = bool(font_dict.get("is_type3", False)) if font_dict else ("type3" in (base_font or font_name).lower())
    
    font_subtype = (font_dict.get("subtype") or ("Type0" if is_t0 else ("Type3" if is_t3 else "TrueType"))) if font_dict else "TrueType"

    fallback = get_best_fallback_font(clean_fam)

    fm = FontMetrics(
        font_name=font_name,
        base_font=base_font,
        subset_prefix=prefix,
        clean_family=clean_fam,
        is_embedded=bool(font_file_bytes),
        is_type3=is_t3,
        is_type0=is_t0,
        font_type=font_subtype,
        fallback_font=fallback,
    )

    # 1. Base standard 14 font fallback
    std_info = _load_std_font_metrics(base_font)
    if std_info:
        fm.units_per_em = std_info["units_per_em"]
        fm.ascent = std_info["ascent"]
        fm.descent = std_info["descent"]
        fm.default_width = std_info["default_width"]
        for c, w in std_info["widths"].items():
            fm.widths[c] = w

    # 2. ToUnicode CMap
    if to_unicode_bytes:
        fm.to_unicode_map = parse_to_unicode_cmap(to_unicode_bytes)

    # 3. Embedded font files
    if font_file_bytes:
        extracted = parse_embedded_font_metrics(font_file_bytes)
        if extracted:
            fm.units_per_em = extracted["units_per_em"]
            fm.ascent = extracted["ascent"]
            fm.descent = extracted["descent"]
            if "widths" in extracted:
                for k, v in extracted["widths"].items():
                    try:
                        code = ord(k) if len(k) == 1 else None
                        if code is not None:
                            fm.widths[code] = v
                    except Exception:
                        pass

    # 4. Explicit Font Dictionary /FirstChar and /Widths
    if font_dict:
        if "ascent" in font_dict and font_dict["ascent"] is not None:
            fm.ascent = float(font_dict["ascent"])
        if "descent" in font_dict and font_dict["descent"] is not None:
            fm.descent = float(font_dict["descent"])
        if "cap_height" in font_dict and font_dict["cap_height"] is not None:
            fm.cap_height = float(font_dict["cap_height"])
        if "units_per_em" in font_dict and font_dict["units_per_em"] is not None:
            fm.units_per_em = float(font_dict["units_per_em"])
        if "font_bbox" in font_dict and font_dict["font_bbox"] is not None:
            fm.bbox = tuple(float(v) for v in font_dict["font_bbox"])
        if "first_char" in font_dict and "widths" in font_dict:
            fc = font_dict["first_char"]
            for idx, w in enumerate(font_dict["widths"]):
                fm.widths[fc + idx] = float(w)
        if "cid_widths" in font_dict:
            for cid, w in font_dict["cid_widths"].items():
                fm.widths[cid] = float(w)
        if "default_width" in font_dict:
            fm.default_width = float(font_dict["default_width"])

    # 5. Compute expected width error against fallback font if not embedded
    if not fm.is_embedded and std_info and fm.widths:
        std_widths = std_info.get("widths", {})
        diffs = [abs(fm.widths[c] - std_widths[c]) for c in fm.widths if c in std_widths]
        if diffs:
            fm.expected_width_error_pt = float(sum(diffs) / len(diffs)) / 1000.0

    return fm

