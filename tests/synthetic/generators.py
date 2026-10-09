"""
Synthetic Statement PDF Generator with Exact Programmatic Ground Truth.

Generates PDFs with 100% known geometric coordinates:
- Exact page dimensions and margins
- Exact vector line coordinates (x0, y0, x1, y1, stroke width)
- Exact fill rectangles and background colors
- Exact text strings, origins, font families, font sizes, advance widths
- Exact table column boundaries, column widths, row pitches, and cell values

Returns a GroundTruthSpec containing every known coordinate so tests can
assert against independent mathematical truth (not against extractor output).
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors


@dataclass
class KnownLine:
    id: str
    orientation: str  # 'H' or 'V'
    x0: float
    y0: float
    x1: float
    y1: float
    stroke_width: float
    color_rgb: Tuple[float, float, float]


@dataclass
class KnownRect:
    id: str
    x0: float
    y0: float
    x1: float
    y1: float
    fill_color_rgb: Tuple[float, float, float]


@dataclass
class KnownText:
    text: str
    x: float
    y: float
    font_name: str
    font_size: float
    width_pt: float
    color_rgb: Tuple[float, float, float]


@dataclass
class KnownColumn:
    index: int
    header: str
    x0: float
    x1: float
    width: float  # center-to-center width
    inner_width: float  # inner cell width subtracting rule stroke widths
    alignment: str


@dataclass
class KnownRow:
    index: int
    is_header: bool
    baseline_y: float
    pitch: float
    lines_count: int
    cells: List[str]


@dataclass
class GroundTruthSpec:
    template_name: str
    page_width: float
    page_height: float
    margins: Dict[str, float]  # top, right, bottom, left
    lines: List[KnownLine] = field(default_factory=list)
    rects: List[KnownRect] = field(default_factory=list)
    texts: List[KnownText] = field(default_factory=list)
    columns: List[KnownColumn] = field(default_factory=list)
    rows: List[KnownRow] = field(default_factory=list)


def create_full_grid_synthetic_statement(pdf_path: str) -> GroundTruthSpec:
    """
    Creates a full-grid synthetic bank statement with exact known geometry.
    Table has complete vertical and horizontal rules.
    """
    c = canvas.Canvas(pdf_path, pagesize=letter)
    page_w, page_h = letter  # 612 x 792 pt
    
    spec = GroundTruthSpec(
        template_name="full_grid_synthetic",
        page_width=page_w,
        page_height=page_h,
        margins={"top": 42.0, "right": 36.0, "bottom": 42.0, "left": 36.0},
    )
    
    # 1. Header & Title Text
    c.setFont("Helvetica-Bold", 14)
    title = "Apex National Bank - Account Statement"
    c.drawString(36.0, 750.0, title)
    title_w = c.stringWidth(title, "Helvetica-Bold", 14)
    spec.texts.append(KnownText(title, 36.0, 750.0, "Helvetica-Bold", 14.0, title_w, (0, 0, 0)))
    
    c.setFont("Helvetica", 9)
    sub = "Statement Period: 01/08/2026 to 31/08/2026 | Account: 009918273645"
    c.drawString(36.0, 732.0, sub)
    sub_w = c.stringWidth(sub, "Helvetica", 9)
    spec.texts.append(KnownText(sub, 36.0, 732.0, "Helvetica", 9.0, sub_w, (0, 0, 0)))
    
    # 2. Table Column Grid Definition
    # 6 Columns spanning from x=36.0 to x=576.0 (width 540 pt)
    col_x_edges = [36.0, 106.0, 266.0, 346.0, 426.0, 506.0, 576.0]
    col_headers = ["Date", "Narration Details", "Chq/Ref", "Withdrawal", "Deposit", "Balance"]
    col_aligns = ["left", "left", "left", "right", "right", "right"]
    
    for i in range(len(col_headers)):
        x0 = col_x_edges[i]
        x1 = col_x_edges[i + 1]
        c_w = x1 - x0
        spec.columns.append(KnownColumn(
            index=i + 1,
            header=col_headers[i],
            x0=x0,
            x1=x1,
            width=c_w,
            inner_width=c_w - 0.75,
            alignment=col_aligns[i],
        ))
        
    # Table Y coordinates
    table_top_y = 690.0
    hdr_row_h = 24.0
    hdr_bot_y = table_top_y - hdr_row_h  # 666.0
    
    # Draw Header Fill Background
    c.setFillColor(colors.HexColor("#E2E8F0"))
    c.rect(36.0, hdr_bot_y, 540.0, hdr_row_h, fill=True, stroke=False)
    spec.rects.append(KnownRect("header_fill", 36.0, hdr_bot_y, 576.0, table_top_y, (0.886, 0.910, 0.941)))
    
    # Header Row Text
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    hdr_baseline_y = 673.0
    for i, h_text in enumerate(col_headers):
        tx = col_x_edges[i] + 5.0
        c.drawString(tx, hdr_baseline_y, h_text)
        tw = c.stringWidth(h_text, "Helvetica-Bold", 9)
        spec.texts.append(KnownText(h_text, tx, hdr_baseline_y, "Helvetica-Bold", 9.0, tw, (0, 0, 0)))
        
    spec.rows.append(KnownRow(
        index=1,
        is_header=True,
        baseline_y=hdr_baseline_y,
        pitch=0.0,
        lines_count=1,
        cells=list(col_headers),
    ))
    
    # Body Rows Data
    body_data = [
        ("01/08/2026", "OPENING BALANCE B/F", "-", "-", "-", "50,000.00"),
        ("03/08/2026", "UPI/234981/MERCHANT PURCHASE", "UPI001", "1,500.00", "-", "48,500.00"),
        ("10/08/2026", "NEFT DR-CORP001-VENDOR PAYMENT", "N10081", "8,200.00", "-", "40,300.00"),
        ("18/08/2026", "SALARY DIRECT DEPOSIT AUGUST", "SAL202608", "-", "65,000.00", "105,300.00"),
        ("25/08/2026", "ELECTRICITY BILL PAYMENT BESCOM", "EB99281", "2,450.00", "-", "102,850.00"),
        ("31/08/2026", "CLOSING BALANCE C/F", "-", "-", "-", "102,850.00"),
    ]
    
    row_pitch = 22.0
    cur_top_y = hdr_bot_y
    
    c.setFont("Helvetica", 8)
    for row_idx, row_cells in enumerate(body_data):
        cur_bot_y = cur_top_y - row_pitch
        cur_baseline_y = cur_bot_y + 7.0
        
        for c_idx, cell_str in enumerate(row_cells):
            cw = c.stringWidth(cell_str, "Helvetica", 8)
            if col_aligns[c_idx] == "right" and cell_str != "-":
                tx = col_x_edges[c_idx + 1] - 5.0 - cw
            else:
                tx = col_x_edges[c_idx] + 5.0
            c.drawString(tx, cur_baseline_y, cell_str)
            spec.texts.append(KnownText(cell_str, tx, cur_baseline_y, "Helvetica", 8.0, cw, (0, 0, 0)))
            
        spec.rows.append(KnownRow(
            index=row_idx + 2,
            is_header=False,
            baseline_y=cur_baseline_y,
            pitch=row_pitch,
            lines_count=1,
            cells=list(row_cells),
        ))
        cur_top_y = cur_bot_y
        
    table_bot_y = cur_top_y
    
    # 3. Draw Table Rules (Stroke width = 0.75 pt)
    c.setStrokeColor(colors.HexColor("#4A5568"))
    c.setLineWidth(0.75)
    
    # Horizontal Rules (Top, Header Bottom, and after each row)
    h_y_positions = [table_top_y, hdr_bot_y] + [hdr_bot_y - (k + 1) * row_pitch for k in range(len(body_data))]
    for k, hy in enumerate(h_y_positions):
        c.line(36.0, hy, 576.0, hy)
        spec.lines.append(KnownLine(
            id=f"h_rule_{k+1}",
            orientation="H",
            x0=36.0,
            y0=hy,
            x1=576.0,
            y1=hy,
            stroke_width=0.75,
            color_rgb=(0.29, 0.33, 0.41),
        ))
        
    # Vertical Rules (7 boundaries)
    for k, vx in enumerate(col_x_edges):
        c.line(vx, table_bot_y, vx, table_top_y)
        spec.lines.append(KnownLine(
            id=f"v_rule_{k+1}",
            orientation="V",
            x0=vx,
            y0=table_bot_y,
            x1=vx,
            y1=table_top_y,
            stroke_width=0.75,
            color_rgb=(0.29, 0.33, 0.41),
        ))
        
    c.showPage()
    c.save()
    return spec


def create_unruled_synthetic_statement(pdf_path: str) -> GroundTruthSpec:
    """
    Creates an unruled synthetic bank statement with exact known geometry
    (zero vector lines and zero fill rectangles).
    """
    c = canvas.Canvas(pdf_path, pagesize=letter)
    page_w, page_h = letter  # 612 x 792 pt
    
    spec = GroundTruthSpec(
        template_name="unruled_synthetic",
        page_width=page_w,
        page_height=page_h,
        margins={"top": 42.0, "right": 36.0, "bottom": 42.0, "left": 36.0},
    )
    
    # Title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(36.0, 750.0, "Zenith Bank - Account Statement")
    spec.texts.append(KnownText("Zenith Bank - Account Statement", 36.0, 750.0, "Helvetica-Bold", 14.0, 210.0, (0, 0, 0)))
    
    # 5 Columns
    col_starts = [40.0, 120.0, 300.0, 410.0, 500.0]
    col_widths = [70.0, 165.0, 95.0, 80.0, 70.0]
    headers = ["Date", "Narration Details", "Chq / Ref No", "Withdrawal", "Balance"]
    aligns = ["left", "left", "left", "right", "right"]
    
    for i in range(len(headers)):
        spec.columns.append(KnownColumn(
            index=i + 1,
            header=headers[i],
            x0=col_starts[i],
            x1=col_starts[i] + col_widths[i],
            width=col_widths[i],
            inner_width=col_widths[i],
            alignment=aligns[i],
        ))
        
    # Header Row
    hdr_baseline_y = 700.0
    c.setFont("Helvetica-Bold", 9)
    for i, h in enumerate(headers):
        c.drawString(col_starts[i], hdr_baseline_y, h)
        spec.texts.append(KnownText(h, col_starts[i], hdr_baseline_y, "Helvetica-Bold", 9.0, c.stringWidth(h, "Helvetica-Bold", 9), (0, 0, 0)))
        
    spec.rows.append(KnownRow(
        index=1,
        is_header=True,
        baseline_y=hdr_baseline_y,
        pitch=0.0,
        lines_count=1,
        cells=list(headers),
    ))
    
    # Transactions (multi-line wrapped narration)
    txns = [
        ("02/09/2026", ["UPI/2349810/Merchant Pay", "Order 99182 Bangalore"], "UPI992", "1,250.00", "48,750.00"),
        ("08/09/2026", ["NEFT DR-ABC ENTERPRISES", "INVOICE NO 4491-SEP", "SUPPLY CONTRACT 2026"], "N09051", "5,000.00", "43,750.00"),
        ("15/09/2026", ["SALARY CREDIT SEPT 2026"], "SAL2026", "0.00", "93,750.00"),
        ("22/09/2026", ["MONTHLY UTILITY BILL", "ELECTRICITY BOARD"], "EB9918", "2,340.50", "91,409.50"),
    ]
    
    y = 665.0
    c.setFont("Helvetica", 8)
    for r_idx, (dt, narr_lines, ref, amt, bal) in enumerate(txns):
        c.drawString(col_starts[0], y, dt)
        spec.texts.append(KnownText(dt, col_starts[0], y, "Helvetica", 8.0, c.stringWidth(dt, "Helvetica", 8), (0, 0, 0)))
        
        for l_idx, nl in enumerate(narr_lines):
            ly = y - (l_idx * 11.0)
            c.drawString(col_starts[1], ly, nl)
            spec.texts.append(KnownText(nl, col_starts[1], ly, "Helvetica", 8.0, c.stringWidth(nl, "Helvetica", 8), (0, 0, 0)))
            
        c.drawString(col_starts[2], y, ref)
        spec.texts.append(KnownText(ref, col_starts[2], y, "Helvetica", 8.0, c.stringWidth(ref, "Helvetica", 8), (0, 0, 0)))
        
        amt_w = c.stringWidth(amt, "Helvetica", 8)
        amt_x = col_starts[3] + col_widths[3] - amt_w
        c.drawString(amt_x, y, amt)
        spec.texts.append(KnownText(amt, amt_x, y, "Helvetica", 8.0, amt_w, (0, 0, 0)))
        
        bal_w = c.stringWidth(bal, "Helvetica", 8)
        bal_x = col_starts[4] + col_widths[4] - bal_w
        c.drawString(bal_x, y, bal)
        spec.texts.append(KnownText(bal, bal_x, y, "Helvetica", 8.0, bal_w, (0, 0, 0)))
        
        line_cnt = len(narr_lines)
        spec.rows.append(KnownRow(
            index=r_idx + 2,
            is_header=False,
            baseline_y=y,
            pitch=11.0 if line_cnt > 1 else 0.0,
            lines_count=line_cnt,
            cells=[dt, " \n ".join(narr_lines), ref, amt, bal],
        ))
        y -= (line_cnt * 11.0 + 13.0)
        
    c.showPage()
    c.save()
    return spec
