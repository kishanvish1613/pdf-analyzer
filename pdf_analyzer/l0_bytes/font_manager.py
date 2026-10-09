"""Font Extraction, Repair, and Precision Text-Metrics Manager for L0 and Exporters.

Provides:
1. Embedded font extraction from PDF (TrueType, CFF/Type1, Type0/CID) via PyMuPDF.
2. Font table repair (synthesizing missing name, OS/2, cmap, post tables) for ReportLab TTFont registration.
3. Nearest metric-compatible standard 14 font selection with expected width error calculations.
4. Precision string-width computation and corrective char-spacing (charSpace / letter-spacing).
"""

from __future__ import annotations
import io
import os
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
import pymupdf
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._n_a_m_e import table__n_a_m_e, NameRecord
from fontTools.ttLib.tables.O_S_2f_2 import table_O_S_2f_2, Panose
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

logger = logging.getLogger(__name__)

STANDARD_14_FALLBACKS = {
    "helvetica": "Helvetica",
    "helvetica-bold": "Helvetica-Bold",
    "helvetica-oblique": "Helvetica-Oblique",
    "helvetica-boldoblique": "Helvetica-BoldOblique",
    "times": "Times-Roman",
    "times-roman": "Times-Roman",
    "times-bold": "Times-Bold",
    "times-italic": "Times-Italic",
    "times-bolditalic": "Times-BoldItalic",
    "courier": "Courier",
    "courier-bold": "Courier-Bold",
    "courier-oblique": "Courier-Oblique",
    "courier-boldoblique": "Courier-BoldOblique",
    "symbol": "Symbol",
    "zapfdingbats": "ZapfDingbats",
}

_REGISTERED_RL_FONTS: Dict[str, str] = {}


@dataclass
class ExtractedFontInfo:
    font_name: str
    clean_family: str
    subset_prefix: Optional[str]
    is_embedded: bool
    font_type: str
    file_path: Optional[str] = None
    units_per_em: int = 1000
    ascent: float = 800.0
    descent: float = -200.0
    cap_height: float = 700.0
    x_height: float = 500.0
    bbox: Tuple[float, float, float, float] = (-200.0, -200.0, 1200.0, 900.0)
    widths: Dict[int, float] = field(default_factory=dict)
    to_unicode_map: Dict[int, str] = field(default_factory=dict)
    missing_glyphs: List[str] = field(default_factory=list)
    fallback_font: str = "Helvetica"
    expected_width_error_pt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_name": self.font_name,
            "clean_family": self.clean_family,
            "subset_prefix": self.subset_prefix,
            "is_embedded": self.is_embedded,
            "font_type": self.font_type,
            "file_path": self.file_path,
            "units_per_em": self.units_per_em,
            "ascent": round(self.ascent, 3),
            "descent": round(self.descent, 3),
            "cap_height": round(self.cap_height, 3),
            "x_height": round(self.x_height, 3),
            "bbox": [round(v, 2) for v in self.bbox],
            "widths_count": len(self.widths),
            "missing_glyphs_count": len(self.missing_glyphs),
            "fallback_font": self.fallback_font,
            "expected_width_error_pt": round(self.expected_width_error_pt, 4),
        }


def parse_font_name_parts(font_name: str) -> Tuple[Optional[str], str]:
    """Parse 6-letter subset prefix and clean font family name (e.g. 'UCWCLL+SourceSans3' -> ('UCWCLL+', 'SourceSans3'))."""
    if not font_name:
        return None, "Helvetica"
    m = re.match(r"^([A-Z]{6})\+(.+)$", font_name)
    if m:
        return m.group(1) + "+", m.group(2)
    return None, font_name


def get_best_fallback_font(font_name: str, is_bold: bool = False, is_italic: bool = False) -> str:
    """Find the closest standard 14 metric-compatible font."""
    _, clean = parse_font_name_parts(font_name)
    lower = clean.lower()

    if "courier" in lower or "mono" in lower or "consolas" in lower:
        if is_bold and is_italic:
            return "Courier-BoldOblique"
        elif is_bold or "bold" in lower:
            return "Courier-Bold"
        elif is_italic or "oblique" in lower or "italic" in lower:
            return "Courier-Oblique"
        return "Courier"

    if "times" in lower or "serif" in lower or "cambria" in lower or "georgia" in lower:
        if is_bold and is_italic:
            return "Times-BoldItalic"
        elif is_bold or "bold" in lower:
            return "Times-Bold"
        elif is_italic or "italic" in lower:
            return "Times-Italic"
        return "Times-Roman"

    # Default Sans-Serif (Helvetica / Arial / SourceSans / Calibri)
    if is_bold and is_italic:
        return "Helvetica-BoldOblique"
    elif is_bold or "bold" in lower or "semibold" in lower or "black" in lower or "heavy" in lower:
        return "Helvetica-Bold"
    elif is_italic or "oblique" in lower or "italic" in lower:
        return "Helvetica-Oblique"
    return "Helvetica"


def repair_truetype_font_bytes(
    font_bytes: bytes,
    font_name: str,
    to_unicode_map: Optional[Dict[int, str]] = None
) -> bytes:
    """Repair missing name, OS/2, cmap, or post tables in embedded font streams for ReportLab registration."""
    try:
        font_stream = io.BytesIO(font_bytes)
        tt = TTFont(font_stream)
    except Exception as e:
        logger.debug(f"Could not parse font bytes with fontTools: {e}")
        return font_bytes

    _, clean_family = parse_font_name_parts(font_name)
    subfamily = "Bold" if "bold" in clean_family.lower() else "Regular"

    # 1. Ensure 'name' table
    if "name" not in tt:
        name_tbl = newTable("name")
        name_tbl.names = []
        name_entries = [
            (1, clean_family),
            (2, subfamily),
            (4, font_name),
            (6, font_name.replace(" ", "").replace("+", "_")),
        ]
        for name_id, val in name_entries:
            rec = NameRecord()
            rec.nameID = name_id
            rec.platformID = 3
            rec.platEncID = 1
            rec.langID = 0x409
            rec.string = val.encode("utf-16-be")
            name_tbl.names.append(rec)
        tt["name"] = name_tbl

    # 2. Ensure 'OS/2' table
    if "OS/2" not in tt:
        os2 = newTable("OS/2")
        os2.version = 4
        os2.xAvgCharWidth = 500
        os2.usWeightClass = 700 if "bold" in clean_family.lower() else 400
        os2.usWidthClass = 5
        os2.fsType = 0
        os2.ySubscriptXSize = 650
        os2.ySubscriptYSize = 600
        os2.ySubscriptXOffset = 0
        os2.ySubscriptYOffset = 75
        os2.ySuperscriptXSize = 650
        os2.ySuperscriptYSize = 600
        os2.ySuperscriptXOffset = 0
        os2.ySuperscriptYOffset = 350
        os2.yStrikeoutSize = 50
        os2.yStrikeoutPosition = 300
        os2.sFamilyClass = 0
        p = Panose()
        p.bFamilyType = 0
        p.bSerifStyle = 0
        p.bWeight = 0
        p.bProportion = 0
        p.bContrast = 0
        p.bStrokeVariation = 0
        p.bArmStyle = 0
        p.bLetterform = 0
        p.bMidline = 0
        p.bXHeight = 0
        os2.panose = p
        os2.ulUnicodeRange1 = 1
        os2.ulUnicodeRange2 = 0
        os2.ulUnicodeRange3 = 0
        os2.ulUnicodeRange4 = 0
        os2.achVendID = b"NONE"
        os2.fsSelection = 0
        os2.usFirstCharIndex = 32
        os2.usLastCharIndex = 255
        os2.sTypoAscender = 800
        os2.sTypoDescender = -200
        os2.sTypoLineGap = 200
        os2.usWinAscent = 800
        os2.usWinDescent = 200
        os2.ulCodePageRange1 = 1
        os2.ulCodePageRange2 = 0
        os2.sxHeight = 500
        os2.sCapHeight = 700
        os2.usDefaultChar = 0
        os2.usBreakChar = 32
        os2.usMaxContext = 0
        tt["OS/2"] = os2

    # 3. Ensure 'cmap' table
    if "cmap" not in tt:
        cmap_tbl = newTable("cmap")
        cmap_tbl.tableVersion = 0
        subtable = CmapSubtable.newSubtable(4)
        subtable.platformID = 3
        subtable.platEncID = 1
        subtable.language = 0
        glyph_order = tt.getGlyphOrder()
        mapping = {}
        if to_unicode_map:
            for code, u_str in to_unicode_map.items():
                if len(u_str) == 1:
                    u_ord = ord(u_str)
                    if code < len(glyph_order):
                        mapping[u_ord] = glyph_order[code]
        if not mapping:
            for i, name in enumerate(glyph_order):
                if i > 0 and i < 256:
                    mapping[i] = name
        subtable.cmap = mapping
        cmap_tbl.tables = [subtable]
        tt["cmap"] = cmap_tbl

    # 4. Ensure 'post' table
    if "post" not in tt:
        post = newTable("post")
        post.formatType = 3.0
        post.italicAngle = 0.0
        post.underlinePosition = -100
        post.underlineThickness = 50
        post.isFixedPitch = 0
        post.minMemType42 = 0
        post.maxMemType42 = 0
        post.minMemType1 = 0
        post.maxMemType1 = 0
        tt["post"] = post

    out_stream = io.BytesIO()
    try:
        tt.save(out_stream)
        return out_stream.getvalue()
    except Exception as e:
        logger.debug(f"Failed to resave repaired font {font_name}: {e}")
        return font_bytes


def extract_and_register_fonts(
    pdf_path: str,
    output_dir: str = "out/fonts"
) -> Dict[str, ExtractedFontInfo]:
    """Extract embedded fonts from PDF via PyMuPDF and register them for ReportLab and WeasyPrint."""
    os.makedirs(output_dir, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    font_registry: Dict[str, ExtractedFontInfo] = {}

    seen_xrefs = set()
    for pno in range(len(doc)):
        page_fonts = doc.get_page_fonts(pno)
        for f in page_fonts:
            xref = f[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            raw_name, ext, subtype, buf = doc.extract_font(xref)
            font_name = str(raw_name).lstrip("/")
            prefix, clean_family = parse_font_name_parts(font_name)
            is_embedded = bool(buf and len(buf) > 0)
            fallback = get_best_fallback_font(clean_family)

            file_path = None
            if is_embedded:
                # Repair font if TTF/OTF
                repaired_bytes = repair_truetype_font_bytes(buf, font_name)
                ext_clean = "ttf" if ext in ["ttf", "n/a", ""] else ext
                file_name = f"{font_name.replace('+', '_').replace('/', '_')}.{ext_clean}"
                file_path = os.path.join(output_dir, file_name)
                with open(file_path, "wb") as f_out:
                    f_out.write(repaired_bytes)

                # Register with ReportLab
                register_font_for_reportlab(font_name, file_path)

            font_info = ExtractedFontInfo(
                font_name=font_name,
                clean_family=clean_family,
                subset_prefix=prefix,
                is_embedded=is_embedded,
                font_type=subtype or ("TrueType" if ext == "ttf" else "Type1"),
                file_path=file_path,
                fallback_font=fallback,
            )
            font_registry[font_name] = font_info

    doc.close()
    return font_registry


def register_font_for_reportlab(font_name: str, font_path: str) -> Optional[str]:
    """Register TrueType font file with ReportLab's pdfmetrics registry."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as RL_TTFont

    if font_name in _REGISTERED_RL_FONTS:
        return _REGISTERED_RL_FONTS[font_name]

    try:
        rl_font = RL_TTFont(font_name, font_path)
        pdfmetrics.registerFont(rl_font)
        _REGISTERED_RL_FONTS[font_name] = font_name
        logger.info(f"Registered embedded font '{font_name}' with ReportLab.")
        return font_name
    except Exception as e:
        logger.debug(f"Could not register font '{font_name}' in ReportLab ({e}).")
        return None


def calculate_string_width_parity(
    text: str,
    original_width_pt: float,
    font_name: str,
    font_size_pt: float,
    threshold_pt: float = 0.05
) -> Dict[str, Any]:
    """Check width produced by target rendering engine against source rendered width and compute corrective spacing."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    # Try target font or fallback
    target_font = font_name if font_name in _REGISTERED_RL_FONTS else get_best_fallback_font(font_name)
    try:
        target_width_pt = float(stringWidth(text, target_font, font_size_pt))
    except Exception:
        fallback_font = get_best_fallback_font(font_name)
        target_width_pt = float(stringWidth(text, fallback_font, font_size_pt))
        target_font = fallback_font

    delta_pt = original_width_pt - target_width_pt
    needs_correction = abs(delta_pt) > threshold_pt

    char_spacing_pt = 0.0
    if needs_correction and len(text) > 1:
        char_spacing_pt = delta_pt / float(len(text) - 1)

    return {
        "text": text,
        "original_width_pt": round(original_width_pt, 4),
        "target_width_pt": round(target_width_pt, 4),
        "delta_pt": round(delta_pt, 4),
        "target_font": target_font,
        "needs_correction": needs_correction,
        "char_spacing_correction_pt": round(char_spacing_pt, 5),
    }

