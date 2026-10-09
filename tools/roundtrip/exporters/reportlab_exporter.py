"""ReportLab PDF Exporter for Roundtrip Verification Harness.

Recreates a PDF document from a design specification dictionary with exact page geometry,
registered embedded fonts, precision string-width parity checking, corrective char-spacing,
vector rules, background fills, headers, key-value grids, and table columns/rows.
"""

from __future__ import annotations
import os
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics

from pdf_analyzer.l0_bytes.font_manager import (
    register_font_for_reportlab,
    get_best_fallback_font,
    calculate_string_width_parity,
)
from pdf_analyzer.privacy.engine import apply_privacy_transform

logger = logging.getLogger(__name__)


def _parse_color(val: Any, default=colors.black, alpha: Optional[float] = None) -> colors.Color:
    if val is None:
        return default
    if isinstance(val, colors.Color):
        if alpha is not None and getattr(val, "alpha", 1.0) == 1.0:
            return colors.Color(val.red, val.green, val.blue, alpha=alpha)
        return val
    if isinstance(val, (list, tuple)):
        if len(val) == 3:
            r = val[0] / 255.0 if val[0] > 1.0 else float(val[0])
            g = val[1] / 255.0 if val[1] > 1.0 else float(val[1])
            b = val[2] / 255.0 if val[2] > 1.0 else float(val[2])
            return colors.Color(r, g, b, alpha=alpha if alpha is not None else 1.0)
        elif len(val) == 4:
            c = val[0] / 100.0 if val[0] > 1.0 else float(val[0])
            m = val[1] / 100.0 if val[1] > 1.0 else float(val[1])
            y = val[2] / 100.0 if val[2] > 1.0 else float(val[2])
            k = val[3] / 100.0 if val[3] > 1.0 else float(val[3])
            return colors.CMYKColor(c, m, y, k, alpha=alpha if alpha is not None else 1.0)
    if isinstance(val, dict):
        space = val.get("space", "DeviceRGB")
        comps = val.get("components", [])
        a = val.get("alpha", alpha if alpha is not None else 1.0)
        if space == "DeviceCMYK" and len(comps) == 4:
            return colors.CMYKColor(comps[0], comps[1], comps[2], comps[3], alpha=a)
        elif len(comps) == 3:
            return colors.Color(comps[0], comps[1], comps[2], alpha=a)
        elif len(comps) == 1:
            return colors.Color(comps[0], comps[0], comps[0], alpha=a)
    if isinstance(val, str):
        hex_str = val.strip()
        if not hex_str.startswith("#"):
            hex_str = "#" + hex_str
        try:
            c = colors.HexColor(hex_str)
            if alpha is not None:
                return colors.Color(c.red, c.green, c.blue, alpha=alpha)
            return c
        except Exception:
            return default
    return default


def _hex_to_color(hex_str: Optional[str], default=colors.black) -> colors.Color:
    return _parse_color(hex_str, default=default)


def generate_reportlab_pdf(spec: Dict[str, Any], output_pdf_path: str, privacy_mode: str = "none") -> str:
    """Generate a high-fidelity PDF from the extracted design specification.

    Args:
        spec: Design specification dictionary (output of AnalysisPipeline).
        output_pdf_path: Path where the generated PDF will be saved.
        privacy_mode: "none", "redacted", or "synthetic"

    Returns:
        The output_pdf_path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)

    if privacy_mode in ("redacted", "synthetic"):
        spec, _ = apply_privacy_transform(spec, mode=privacy_mode)


    meta = spec.get("meta", {})
    frame = spec.get("frame", {})

    width_pt = float(frame.get("width_pt") or meta.get("width", {}).get("pt") or 612.0)
    height_pt = float(frame.get("height_pt") or meta.get("height", {}).get("pt") or 792.0)

    # 1. Register all embedded fonts from spec
    fonts_dict = spec.get("fonts", {})
    registered_fonts = {}
    for f_name, f_info in fonts_dict.items():
        if isinstance(f_info, dict) and f_info.get("file_path") and os.path.exists(f_info.get("file_path", "")):
            reg_name = register_font_for_reportlab(f_name, f_info["file_path"])
            if reg_name:
                registered_fonts[f_name] = reg_name

    c = canvas.Canvas(output_pdf_path, pagesize=(width_pt, height_pt))

    def to_pdf_y(top_y: float, h: float = 0.0) -> float:
        return height_pt - top_y - h

    def draw_precision_text(
        text: str,
        x: float,
        y: float,
        font_name: str,
        font_size_pt: float,
        color: colors.Color,
        is_bold: bool = False,
        is_italic: bool = False,
        align: str = "left",
        width_limit_pt: Optional[float] = None,
    ):
        """Draw string using target/embedded font with precision width parity correction."""
        if not text or not isinstance(text, str) or not text.strip():
            return

        target_font = registered_fonts.get(font_name)
        if not target_font:
            target_font = get_best_fallback_font(font_name, is_bold=is_bold, is_italic=is_italic)

        # Width check & corrective charSpace
        orig_width_pt = width_limit_pt if width_limit_pt is not None else float(len(text) * font_size_pt * 0.5)
        parity = calculate_string_width_parity(
            text=text,
            original_width_pt=orig_width_pt,
            font_name=target_font,
            font_size_pt=font_size_pt,
            threshold_pt=0.05,
        )

        char_space = parity["char_spacing_correction_pt"] if parity["needs_correction"] else 0.0

        if align == "right":
            c.setFont(target_font, font_size_pt)
            c.setFillColor(color)
            if char_space != 0.0:
                c._charSpace = char_space
            c.drawRightString(x, y, text)
            if char_space != 0.0:
                c._charSpace = 0.0
        elif align == "center":
            c.setFont(target_font, font_size_pt)
            c.setFillColor(color)
            if char_space != 0.0:
                c._charSpace = char_space
            c.drawCentredString(x, y, text)
            if char_space != 0.0:
                c._charSpace = 0.0
        else:
            to = c.beginText(x, y)
            to.setFont(target_font, font_size_pt)
            to.setFillColor(color)
            if char_space != 0.0:
                to.setCharSpace(char_space)
            to.textOut(text)
            c.drawText(to)

    # 2. Background Containers & Fills
    containers = spec.get("containers", [])
    if isinstance(containers, list):
        for cont in containers:
            if not isinstance(cont, dict):
                continue
            bbox = cont.get("path_bbox_pt") or cont.get("painted_outer_bbox_pt")
            if bbox and len(bbox) == 4:
                x0, y0, x1, y1 = [float(v) for v in bbox]
                w = max(0.0, x1 - x0)
                h = max(0.0, y1 - y0)
                fill_c = _hex_to_color(cont.get("fill_color_hex"), None)
                stroke_c = _hex_to_color(cont.get("stroke_color_hex"), None)
                stroke_w = float(cont.get("stroke_width_pt", 0.75))

                if fill_c or stroke_c:
                    if fill_c:
                        c.setFillColor(fill_c)
                    if stroke_c:
                        c.setStrokeColor(stroke_c)
                        c.setLineWidth(stroke_w)
                    c.rect(x0, to_pdf_y(y0, h), w, h, fill=1 if fill_c else 0, stroke=1 if stroke_c else 0)

    # 3. Non-text glyphs (outlines / Type3)
    non_text_glyphs = spec.get("non_text_glyphs", [])
    for ntg in non_text_glyphs:
        if isinstance(ntg, dict):
            gbox = ntg.get("bbox_pt")
            if gbox and len(gbox) == 4:
                gx0, gy0, gx1, gy1 = [float(v) for v in gbox]
                gw = max(0.0, gx1 - gx0)
                gh = max(0.0, gy1 - gy0)
                c.setFillColor(colors.HexColor("#1A202C"))
                c.rect(gx0, to_pdf_y(gy0, gh), gw, gh, fill=1, stroke=0)

    # 4. Header and Logo
    logo = spec.get("logo", {})
    if isinstance(logo, dict) and logo.get("detected"):
        bbox = logo.get("bbox_pt")
        if bbox and len(bbox) == 4:
            lx0, ly0, lx1, ly1 = [float(v) for v in bbox]
            lw, lh = max(1.0, lx1 - lx0), max(1.0, ly1 - ly0)
            c.setFillColor(colors.HexColor("#1A365D"))
            c.roundRect(lx0, to_pdf_y(ly0, lh), lw, lh, 3, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", max(6.0, min(12.0, lh * 0.4)))
            c.drawCentredString(lx0 + lw / 2.0, to_pdf_y(ly0, lh) + lh * 0.3, "LOGO")

    # Render header lines/segments with precision fonts & spacing
    header_data = spec.get("header_blocks")
    if isinstance(header_data, dict):
        blocks = header_data.get("blocks", [])
    elif isinstance(header_data, list):
        blocks = header_data
    else:
        blocks = []

    for blk in blocks:
        if isinstance(blk, dict):
            sub_blocks = blk.get("sub_blocks", [blk])
            for sb in sub_blocks:
                lines = sb.get("lines", [])
                for ln in lines:
                    if isinstance(ln, dict):
                        segments = ln.get("segments", [])
                        for seg in segments:
                            stxt = seg.get("text", "")
                            sbox = seg.get("bbox_pt")
                            fsize = float(seg.get("font_size_pt", 8.0))
                            fname = seg.get("font_name", "Helvetica")
                            is_bold = bool(seg.get("is_bold", False))
                            fcolor = _hex_to_color(seg.get("color_hex"), colors.HexColor("#1A202C"))
                            if sbox and len(sbox) == 4:
                                sx0, sy0, sx1, sy1 = [float(v) for v in sbox]
                                draw_precision_text(
                                    text=stxt,
                                    x=sx0,
                                    y=to_pdf_y(sy0, fsize),
                                    font_name=fname,
                                    font_size_pt=fsize,
                                    color=fcolor,
                                    is_bold=is_bold,
                                    width_limit_pt=sx1 - sx0,
                                )
                    elif isinstance(ln, str):
                        draw_precision_text(
                            text=ln,
                            x=36.0,
                            y=to_pdf_y(100.0, 9.0),
                            font_name="Helvetica",
                            font_size_pt=8.5,
                            color=colors.HexColor("#1A202C"),
                        )

    # 5. Key-Value Pairs
    kv_data = spec.get("key_values")
    if isinstance(kv_data, dict):
        kv_entities = kv_data.get("entities", [])
    elif isinstance(kv_data, list):
        kv_entities = kv_data
    else:
        kv_entities = []

    for kv in kv_entities:
        if isinstance(kv, dict) and not header_data:
            k_text = kv.get("key_text", "")
            v_text = kv.get("value_text") or kv.get("val_text", "")
            k_bbox = kv.get("key_bbox_pt")
            v_bbox = kv.get("value_bbox_pt") or kv.get("val_bbox_pt")

            if k_bbox and len(k_bbox) == 4:
                kx0, ky0, kx1, ky1 = [float(v) for v in k_bbox]
                draw_precision_text(
                    text=k_text,
                    x=kx0,
                    y=to_pdf_y(ky0, 8.0),
                    font_name="Helvetica-Bold",
                    font_size_pt=8.0,
                    color=colors.HexColor("#2D3748"),
                    is_bold=True,
                )

            if v_bbox and len(v_bbox) == 4:
                vx0, vy0, vx1, vy1 = [float(v) for v in v_bbox]
                draw_precision_text(
                    text=v_text,
                    x=vx0,
                    y=to_pdf_y(vy0, 8.0),
                    font_name="Helvetica",
                    font_size_pt=8.0,
                    color=colors.HexColor("#1A202C"),
                )

    # 6. Table Structure
    table = spec.get("table", {})
    tbl_model = spec.get("table_model", {})
    columns = tbl_model.get("columns") or table.get("columns", [])
    rows = tbl_model.get("rows") or table.get("rows", [])
    t_bbox = tbl_model.get("bbox_pt") or table.get("bbox_pt") or [36.0, 200.0, width_pt - 36.0, height_pt - 80.0]

    tx0, ty0, tx1, ty1 = [float(v) for v in t_bbox]
    tw = max(1.0, tx1 - tx0)
    th = max(1.0, ty1 - ty0)

    # Table background / outer frame
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1.0)
    c.rect(tx0, to_pdf_y(ty0, th), tw, th, fill=0, stroke=1)

    # Column vertical rules & headers
    hdr_y0 = ty0
    hdr_h = 20.0
    for idx, col in enumerate(columns):
        if not isinstance(col, dict):
            continue
        cx0 = float(col.get("x0_pt", tx0))
        cx1 = float(col.get("x1_pt", cx0 + col.get("width_pt", 50.0)))
        cw = max(1.0, cx1 - cx0)
        h_text = col.get("header_text") or col.get("name") or f"Col {idx + 1}"
        align = col.get("alignment", "left").lower()

        # Vertical rule at column left edge
        if idx > 0:
            c.setStrokeColor(colors.HexColor("#E2E8F0"))
            c.setLineWidth(0.75)
            c.line(cx0, to_pdf_y(ty0, th), cx0, to_pdf_y(ty0))

        # Header background
        c.setFillColor(colors.HexColor("#F1F5F9"))
        c.rect(cx0, to_pdf_y(hdr_y0, hdr_h), cw, hdr_h, fill=1, stroke=0)

        # Header text
        target_x = cx1 - 3.0 if align == "right" else (cx0 + cw / 2.0 if align == "center" else cx0 + 3.0)
        draw_precision_text(
            text=h_text,
            x=target_x,
            y=to_pdf_y(hdr_y0, hdr_h) + 5.0,
            font_name="Helvetica-Bold",
            font_size_pt=8.0,
            color=colors.HexColor("#1E293B"),
            is_bold=True,
            align=align,
            width_limit_pt=cw,
        )

    # Header bottom rule
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(1.0)
    c.line(tx0, to_pdf_y(hdr_y0 + hdr_h), tx1, to_pdf_y(hdr_y0 + hdr_h))

    # Body rows
    cur_row_y = hdr_y0 + hdr_h
    for r_idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        rh = float(row.get("height_pt", 14.0))
        if cur_row_y + rh > ty1:
            break
        # Row bottom line
        c.setStrokeColor(colors.HexColor("#F1F5F9"))
        c.setLineWidth(0.5)
        c.line(tx0, to_pdf_y(cur_row_y + rh), tx1, to_pdf_y(cur_row_y + rh))

        # Row cells / text
        cells = row.get("cells", [])
        if cells:
            for c_idx, cell in enumerate(cells):
                if c_idx < len(columns):
                    col = columns[c_idx]
                    col_x0 = float(col.get("x0_pt", tx0))
                    col_x1 = float(col.get("x1_pt", col_x0 + 50.0))
                    cell_text = str(cell.get("text", "") if isinstance(cell, dict) else cell)
                    align = col.get("alignment", "left").lower() if isinstance(col, dict) else "left"
                    target_x = col_x1 - 3.0 if align == "right" else (col_x0 + (col_x1 - col_x0) / 2.0 if align == "center" else col_x0 + 3.0)
                    draw_precision_text(
                        text=cell_text,
                        x=target_x,
                        y=to_pdf_y(cur_row_y, rh) + 3.0,
                        font_name="Helvetica",
                        font_size_pt=7.5,
                        color=colors.HexColor("#334155"),
                        align=align,
                        width_limit_pt=col_x1 - col_x0,
                    )
        else:
            summary_text = row.get("text_summary") or row.get("raw_text") or ""
            if summary_text:
                draw_precision_text(
                    text=summary_text,
                    x=tx0 + 4.0,
                    y=to_pdf_y(cur_row_y, rh) + 3.0,
                    font_name="Helvetica",
                    font_size_pt=7.5,
                    color=colors.HexColor("#334155"),
                )

        cur_row_y += rh

    # 7. Footer Blocks
    footer_data = spec.get("footer_blocks")
    if isinstance(footer_data, dict):
        sub_blocks = footer_data.get("sub_blocks", [])
    elif isinstance(footer_data, list):
        sub_blocks = footer_data
    else:
        sub_blocks = []

    for fb in sub_blocks:
        if isinstance(fb, dict):
            bbox = fb.get("bbox_pt")
            if bbox and len(bbox) == 4:
                fx0, fy0, fx1, fy1 = [float(v) for v in bbox]
                f_text = fb.get("text", "")
                draw_precision_text(
                    text=f_text,
                    x=fx0,
                    y=to_pdf_y(fy0, 8.0),
                    font_name="Helvetica",
                    font_size_pt=7.5,
                    color=colors.HexColor("#64748B"),
                    width_limit_pt=fx1 - fx0,
                )

    c.save()
    return output_pdf_path
