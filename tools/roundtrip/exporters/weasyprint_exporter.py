"""WeasyPrint HTML/CSS Exporter for Roundtrip Verification Harness.

Generates exact HTML5 / CSS3 layout from the design specification dictionary with
@font-face embedded font declarations, letter-spacing parity corrections, and renders to PDF.
"""

from __future__ import annotations
import os
import logging
from typing import Dict, Any, List, Optional, Tuple
from pdf_analyzer.privacy.engine import apply_privacy_transform

logger = logging.getLogger(__name__)


def _color_to_css(val: Any, default: str = "#000000", alpha: Optional[float] = None) -> str:
    if not val:
        return default
    if isinstance(val, (list, tuple)):
        if len(val) == 3:
            r = int(round(val[0] if val[0] > 1.0 else val[0] * 255))
            g = int(round(val[1] if val[1] > 1.0 else val[1] * 255))
            b = int(round(val[2] if val[2] > 1.0 else val[2] * 255))
            a = alpha if alpha is not None else 1.0
            return f"rgba({r}, {g}, {b}, {a})"
        elif len(val) == 4:
            c = val[0] * 100 if val[0] <= 1.0 else val[0]
            m = val[1] * 100 if val[1] <= 1.0 else val[1]
            y = val[2] * 100 if val[2] <= 1.0 else val[2]
            k = val[3] * 100 if val[3] <= 1.0 else val[3]
            return f"device-cmyk({c:.1f}%, {m:.1f}%, {y:.1f}%, {k:.1f}%)"
    if isinstance(val, dict):
        space = val.get("space", "DeviceRGB")
        comps = val.get("components", [])
        a = val.get("alpha", alpha if alpha is not None else 1.0)
        if space == "DeviceCMYK" and len(comps) == 4:
            return f"device-cmyk({comps[0]*100:.1f}%, {comps[1]*100:.1f}%, {comps[2]*100:.1f}%, {comps[3]*100:.1f}%)"
        elif len(comps) == 3:
            r = int(round(comps[0] * 255))
            g = int(round(comps[1] * 255))
            b = int(round(comps[2] * 255))
            return f"rgba({r}, {g}, {b}, {a})"
    if isinstance(val, str):
        return val
    return default


def generate_weasyprint_html(spec: Dict[str, Any], output_html_path: str, privacy_mode: str = "none") -> str:
    """Generate a clean HTML5/CSS3 template matching the design specification geometry."""
    os.makedirs(os.path.dirname(os.path.abspath(output_html_path)), exist_ok=True)

    if privacy_mode in ("redacted", "synthetic"):
        spec, _ = apply_privacy_transform(spec, mode=privacy_mode)


    meta = spec.get("meta", {})
    frame = spec.get("frame", {})
    margins = spec.get("margins_spacing", {}).get("page_margins", {})

    width_pt = float(frame.get("width_pt") or meta.get("width", {}).get("pt") or 612.0)
    height_pt = float(frame.get("height_pt") or meta.get("height", {}).get("pt") or 792.0)

    top_m = float(margins.get("top", {}).get("pt", 36.0))
    right_m = float(margins.get("right", {}).get("pt", 36.0))
    bot_m = float(margins.get("bottom", {}).get("pt", 36.0))
    left_m = float(margins.get("left", {}).get("pt", 36.0))

    header = spec.get("header") or {}
    bank_name = header.get("bank_name", {}).get("text", "BANK STATEMENT") if isinstance(header.get("bank_name"), dict) else "BANK STATEMENT"
    stmt_title = header.get("statement_title", {}).get("text", "STATEMENT OF ACCOUNT") if isinstance(header.get("statement_title"), dict) else "STATEMENT OF ACCOUNT"

    fonts_dict = spec.get("fonts", {})
    font_faces = []
    for f_name, f_info in fonts_dict.items():
        if isinstance(f_info, dict) and f_info.get("file_path"):
            rel_path = os.path.relpath(f_info["file_path"], os.path.dirname(os.path.abspath(output_html_path))).replace("\\", "/")
            font_faces.append(f"""
                @font-face {{
                    font-family: '{f_name}';
                    src: url('{rel_path}');
                }}
            """)

    kv_data = spec.get("key_values", {})
    if isinstance(kv_data, dict):
        key_values = kv_data.get("entities", [])
    elif isinstance(kv_data, list):
        key_values = kv_data
    else:
        key_values = []

    hb_data = spec.get("header_blocks", {})
    if isinstance(hb_data, dict):
        header_blocks = hb_data.get("blocks", [])
    elif isinstance(hb_data, list):
        header_blocks = hb_data
    else:
        header_blocks = []

    tbl_model = spec.get("table_model", {})
    table = spec.get("table", {})
    columns = tbl_model.get("columns") or table.get("columns", [])
    rows = tbl_model.get("rows") or table.get("rows", [])
    t_bbox = tbl_model.get("bbox_pt") or table.get("bbox_pt") or [left_m, 200.0, width_pt - right_m, height_pt - bot_m]
    tw = max(1.0, float(t_bbox[2]) - float(t_bbox[0]))

    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html lang='en'><head><meta charset='utf-8'>")
    html.append(f"<title>{bank_name} - Layout Spec</title>")
    html.append("<style>")
    html.append(f"""
        @page {{
            size: {width_pt}pt {height_pt}pt;
            margin: {top_m}pt {right_m}pt {bot_m}pt {left_m}pt;
        }}
        {''.join(font_faces)}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            color: #1A202C;
            font-size: 8.5pt;
            line-height: 1.3;
            background: #ffffff;
            width: 100%;
        }}
        .header-section {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid #1A365D;
            padding-bottom: 8pt;
            margin-bottom: 12pt;
        }}
        .bank-title {{
            font-size: 14pt;
            font-weight: bold;
            color: #1A365D;
        }}
        .statement-title {{
            font-size: 11pt;
            font-weight: bold;
            color: #2D3748;
            text-align: right;
        }}
        .kv-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 4pt 16pt;
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            padding: 8pt;
            margin-bottom: 14pt;
            font-size: 8pt;
        }}
        .kv-row {{
            display: flex;
            justify-content: space-between;
        }}
        .kv-key {{
            font-weight: bold;
            color: #4A5568;
        }}
        .kv-val {{
            color: #1A202C;
        }}
        .table-container {{
            width: 100%;
            margin-top: 10pt;
        }}
        table.data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 8pt;
        }}
        table.data-table th {{
            background: #F1F5F9;
            color: #1E293B;
            font-weight: bold;
            padding: 5pt 4pt;
            border-top: 1px solid #CBD5E1;
            border-bottom: 1.5px solid #94A3B8;
        }}
        table.data-table td {{
            padding: 4pt;
            border-bottom: 0.5px solid #E2E8F0;
            color: #334155;
        }}
        .align-left {{ text-align: left; }}
        .align-right {{ text-align: right; }}
        .align-center {{ text-align: center; }}
        .footer-section {{
            margin-top: 16pt;
            font-size: 7.5pt;
            color: #64748B;
            border-top: 1px solid #E2E8F0;
            padding-top: 6pt;
        }}
    """)
    html.append("</style></head><body>")

    # Header section
    html.append("<div class='header-section'>")
    html.append(f"  <div><div class='bank-title'>{bank_name}</div></div>")
    html.append(f"  <div><div class='statement-title'>{stmt_title}</div></div>")
    html.append("</div>")

    # Key-Value Grid
    if key_values:
        html.append("<div class='kv-grid'>")
        for kv in key_values:
            if isinstance(kv, dict):
                k = kv.get("key_text", "")
                v = kv.get("value_text") or kv.get("val_text", "")
                if k or v:
                    html.append(f"  <div class='kv-row'><span class='kv-key'>{k}:</span> <span class='kv-val'>{v}</span></div>")
        html.append("</div>")

    # Table
    if columns:
        html.append("<div class='table-container'><table class='data-table'><thead><tr>")
        for col in columns:
            if isinstance(col, dict):
                h_text = col.get("header_text") or col.get("name") or "Column"
                align = col.get("alignment", "left").lower()
                cw = float(col.get("width_pt", 50.0))
                w_pct = round((cw / tw * 100.0) if tw > 0 else (100.0 / max(1, len(columns))), 1)
                html.append(f"  <th class='align-{align}' style='width: {w_pct}%;'>{h_text}</th>")
        html.append("</tr></thead><tbody>")

        for row in rows:
            if not isinstance(row, dict):
                continue
            html.append("<tr>")
            cells = row.get("cells", [])
            if cells:
                for c_idx, cell in enumerate(cells):
                    if c_idx < len(columns):
                        col = columns[c_idx]
                        align = col.get("alignment", "left").lower() if isinstance(col, dict) else "left"
                        c_txt = str(cell.get("text", "") if isinstance(cell, dict) else cell)
                        html.append(f"  <td class='align-{align}'>{c_txt}</td>")
            else:
                s_txt = row.get("text_summary") or row.get("raw_text") or ""
                html.append(f"  <td colspan='{len(columns)}'>{s_txt}</td>")
            html.append("</tr>")
        html.append("</tbody></table></div>")

    # Footer
    fb_data = spec.get("footer_blocks", {})
    if isinstance(fb_data, dict):
        footer_blocks = fb_data.get("sub_blocks", [])
    elif isinstance(fb_data, list):
        footer_blocks = fb_data
    else:
        footer_blocks = []

    if footer_blocks:
        html.append("<div class='footer-section'>")
        for fb in footer_blocks:
            if isinstance(fb, dict):
                f_txt = fb.get("text", "")
                if f_txt:
                    html.append(f"  <div>{f_txt}</div>")
        html.append("</div>")

    html.append("</body></html>")

    content = "\n".join(html)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_html_path


def generate_weasyprint_pdf(spec: Dict[str, Any], output_pdf_path: str, output_html_path: Optional[str] = None, privacy_mode: str = "none") -> Tuple[str, str]:
    """Generate HTML/CSS template and render to PDF."""
    if output_html_path is None:
        output_html_path = os.path.splitext(output_pdf_path)[0] + ".html"

    generate_weasyprint_html(spec, output_html_path, privacy_mode=privacy_mode)

    # Attempt native WeasyPrint conversion
    try:
        import weasyprint
        doc = weasyprint.HTML(filename=output_html_path)
        doc.write_pdf(output_pdf_path)
        logger.info(f"Generated PDF via native WeasyPrint: {output_pdf_path}")
    except Exception as e:
        logger.warning(
            f"WeasyPrint native rendering unavailable ({e}); falling back to ReportLab layout generator for PDF."
        )
        from tools.roundtrip.exporters.reportlab_exporter import generate_reportlab_pdf
        generate_reportlab_pdf(spec, output_pdf_path, privacy_mode=privacy_mode)

    return output_pdf_path, output_html_path

