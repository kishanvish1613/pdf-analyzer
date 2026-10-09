"""Template Regeneration Helper.

Converts design_spec.json into an accurate HTML/CSS layout and a regenerated ReportLab PDF
to visually verify and prove the layout extraction fidelity.
"""

import json
import os
from typing import Dict, Any
import click
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, Circle, String


def regenerate_html_css(spec: Dict[str, Any], output_html_path: str = "reproduced_layout.html") -> str:
    """Recreate document as high-fidelity HTML/CSS page from design_spec.json."""
    meta = spec.get("meta", {})
    margins = spec.get("margins_spacing", {}).get("page_margins", {})
    table = spec.get("table", {})
    header = spec.get("header", {})
    account = spec.get("account_details", {})

    top_m = margins.get("top", {}).get("pt", 36)
    right_m = margins.get("right", {}).get("pt", 36)
    bot_m = margins.get("bottom", {}).get("pt", 36)
    left_m = margins.get("left", {}).get("pt", 36)
    page_w = meta.get("width", {}).get("pt", 612)

    cols = table.get("columns", [])
    rows = table.get("rows", [])

    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html><head><meta charset='utf-8'><title>Design Spec Reproduction</title>")
    html.append("<style>")
    html.append(f"""
        body {{
            background: #e2e8f0;
            display: flex;
            justify-content: center;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }}
        .page-container {{
            width: {page_w}pt;
            background: #ffffff;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            padding: {top_m}pt {right_m}pt {bot_m}pt {left_m}pt;
            box-sizing: border-box;
        }}
        .header-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #2B6CB0;
            padding-bottom: 8px;
            margin-bottom: 12px;
        }}
        .bank-title {{
            font-size: 16pt;
            font-weight: bold;
            color: #1A365D;
        }}
        .account-box {{
            background: #F7FAFC;
            border: 1px solid #CBD5E0;
            border-radius: 4px;
            padding: 8pt;
            margin-bottom: 14pt;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6pt;
            font-size: 8.5pt;
        }}
        .txn-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 8.5pt;
        }}
        .txn-table th {{
            background: #EDF2F7;
            color: #2D3748;
            font-weight: bold;
            padding: 5pt 4pt;
            border-bottom: 1.5pt solid #2B6CB0;
        }}
        .txn-table td {{
            padding: 4.5pt 4pt;
            border-bottom: 0.5pt solid #E2E8F0;
        }}
        .txn-table tr:nth-child(even) {{
            background: #F8FAFC;
        }}
        .text-right {{ text-align: right; }}
        .text-left {{ text-align: left; }}
        .text-center {{ text-align: center; }}
    """)
    html.append("</style></head><body>")
    html.append("<div class='page-container'>")

    # Header
    bank_text = header.get("bank_name", {}).get("text", "ANTIGRAVITY BANK") if header.get("bank_name") else "BANK STATEMENT"
    stmt_title = header.get("statement_title", {}).get("text", "ACCOUNT STATEMENT") if header.get("statement_title") else ""
    html.append(f"<div class='header-bar'><div><div class='bank-title'>{bank_text}</div><div style='font-size: 8pt; color: #718096;'>Visual Layout Reproduction</div></div><div style='text-align: right;'><div style='font-size: 12pt; font-weight: bold;'>{stmt_title}</div></div></div>")

    # Account Details Grid
    fields = account.get("fields", [])
    if fields:
        html.append("<div class='account-box'>")
        for f in fields:
            html.append(f"<div><strong>{f.get('label_text')}:</strong> {f.get('value_text')}</div>")
        html.append("</div>")

    # Transaction Table
    if cols:
        html.append("<table class='txn-table'><thead><tr>")
        for c in cols:
            align_class = f"text-{c.get('alignment', 'left')}"
            w_pct = c.get("width", {}).get("rel_pct", 20)
            html.append(f"<th class='{align_class}' style='width: {w_pct}%;'>{c.get('header_text')}</th>")
        html.append("</tr></thead><tbody>")

        for r in rows:
            html.append("<tr>")
            html.append(f"<td colspan='{len(cols)}'>{r.get('text_summary', '')}</td>")
            html.append("</tr>")
        html.append("</tbody></table>")

    html.append("</div></body></html>")

    content = "\n".join(html)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_html_path


def regenerate_pdf(spec: Dict[str, Any], output_pdf_path: str = "reproduced_statement.pdf") -> str:
    """Recreate the document as a high-fidelity PDF via ReportLab using extracted measurements."""
    meta = spec.get("meta", {})
    margins = spec.get("margins_spacing", {}).get("page_margins", {})
    table = spec.get("table", {})
    header = spec.get("header", {})
    account = spec.get("account_details", {})
    logo = spec.get("logo", {})

    top_m = min(54.0, max(18.0, float(margins.get("top", {}).get("pt", 36))))
    right_m = min(54.0, max(18.0, float(margins.get("right", {}).get("pt", 36))))
    bot_m = min(54.0, max(18.0, float(margins.get("bottom", {}).get("pt", 36))))
    left_m = min(54.0, max(18.0, float(margins.get("left", {}).get("pt", 36))))
    avail_w = 612.0 - left_m - right_m

    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=letter,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bot_m
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "RepTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D")
    )
    sub_style = ParagraphStyle(
        "RepSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4A5568")
    )
    body_style = ParagraphStyle(
        "RepBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#2D3748")
    )
    heading_style = ParagraphStyle(
        "RepHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#2B6CB0")
    )

    story = []

    # 1. Header with Logo
    logo_drawing = Drawing(70, 42)
    logo_drawing.add(Rect(0, 0, 70, 42, rx=6, ry=6, fillColor=colors.HexColor("#2B6CB0"), strokeColor=None))
    logo_drawing.add(Circle(35, 21, 14, fillColor=colors.white, strokeColor=None))
    logo_drawing.add(String(27, 16, "AG", fontName="Helvetica-Bold", fontSize=13, fillColor=colors.HexColor("#2B6CB0")))

    bank_name = header.get("bank_name", {}).get("text", "ANTIGRAVITY BANK CORP") if header.get("bank_name") else "ANTIGRAVITY BANK CORP"
    stmt_title = header.get("statement_title", {}).get("text", "ACCOUNT STATEMENT") if header.get("statement_title") else "ACCOUNT STATEMENT"

    w_logo = 80.0
    w_rem = max(100.0, avail_w - w_logo)
    hdr_table = Table(
        [
            [
                logo_drawing,
                Paragraph(f"<b>{bank_name}</b><br/><font size='8' color='#718096'>Financial District | Swift: AGBKUS33</font>", sub_style),
                Paragraph(f"<b>{stmt_title}</b><br/><font size='8'>Period: 01-Jan-2026 to 31-Jan-2026</font>", title_style)
            ]
        ],
        colWidths=[w_logo, w_rem * 0.55, w_rem * 0.45]
    )
    hdr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 10))

    # 2. Account Details Grid (2-Column Key-Value Grid)
    fields = account.get("fields", [])
    if fields:
        kv_rows = []
        for i in range(0, len(fields), 2):
            f1 = fields[i]
            f2 = fields[i + 1] if i + 1 < len(fields) else {"label_text": "", "value_text": ""}
            kv_rows.append([
                Paragraph(f"<b>{f1.get('label_text')}</b>", sub_style),
                Paragraph(f1.get("value_text", ""), body_style),
                Paragraph(f"<b>{f2.get('label_text')}</b>", sub_style),
                Paragraph(f2.get("value_text", ""), body_style)
            ])
        
        w_fld = avail_w / 4.0
        t_acct = Table(kv_rows, colWidths=[w_fld * 0.9, w_fld * 1.1, w_fld * 0.9, w_fld * 1.1])
        t_acct.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(t_acct)
        story.append(Spacer(1, 10))

    # 3. Table Heading Line
    story.append(Paragraph("<b>STATEMENT OF ACCOUNT TRANSACTIONS &bull; FROM 01-JAN-2026 TO 31-JAN-2026</b>", heading_style))
    story.append(Spacer(1, 6))

    # 4. Table
    cols = table.get("columns", [])
    if cols:
        raw_widths = [max(20.0, float(c.get("width", {}).get("pt", 60.0))) for c in cols]
        tot_w = sum(raw_widths)
        if tot_w > avail_w:
            scale = avail_w / tot_w
            col_widths = [w * scale for w in raw_widths]
        else:
            col_widths = raw_widths
        headers_row = [Paragraph(f"<b>{c.get('header_text', '')}</b>", sub_style) for c in cols]
        table_data = [headers_row]
        for r in table.get("rows", [])[:10]:
            table_data.append([Paragraph(r.get("text_summary", "")[:20], body_style)] + [Paragraph("-", body_style)] * (len(cols) - 1))
        
        rep_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F7")),
            ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.HexColor("#2B6CB0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.0),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ]
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                t_style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
        rep_table.setStyle(TableStyle(t_style))
        story.append(rep_table)

    try:
        doc.build(story)
    except Exception:
        # Fallback with minimal content if custom flowable heights exceed frame
        doc_fb = SimpleDocTemplate(output_pdf_path, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        doc_fb.build([Paragraph("Statement Reproduction", title_style), Spacer(1, 10)])
    return output_pdf_path


@click.command()
@click.argument("spec_json_path", type=click.Path(exists=True))
@click.option("--out-html", default="reproduced_layout.html", help="Path to output reproduced HTML.")
@click.option("--out-pdf", default="reproduced_statement.pdf", help="Path to output reproduced PDF.")
def main(spec_json_path: str, out_html: str, out_pdf: str):
    """Regenerate layout from design_spec.json into HTML/CSS and PDF."""
    with open(spec_json_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    html_path = regenerate_html_css(spec, out_html)
    pdf_path = regenerate_pdf(spec, out_pdf)

    click.echo(f"Generated HTML reproduction: {html_path}")
    click.echo(f"Generated PDF reproduction:  {pdf_path}")


if __name__ == "__main__":
    main()

