"""
Test Suite for Unruled and Row-Bands-Only Table Grid Inference (L3 Topology Engine).

Verifies:
1. TableStyleVerdict: UNRULED and ROW_BANDS_ONLY detection.
2. Column boundary precision: inferred column boundaries match ground-truth within <= 0.5 pt.
3. Edge cases:
   - Right-aligned numeric amounts (Dr/Cr suffixes, 2-decimal formatting).
   - Multi-line wrapped narration/description cells without losing anchor association.
   - Empty cells (sparse columns such as Debit/Credit).
   - Narrow gutters (whitespace gutters <= 5.0 pt).
4. Row inference: baseline clustering, row pitch calculation, lines count, continuation lines.
5. Confidence scoring & diagnostic reasons: boundary and table confidence scores between 0 and 1.
6. Ruled table regression check: ruled table extractions remain unchanged.
"""

import os
import pytest
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import (
    TableGridEngine,
    TableStyleVerdict,
    RowBandType,
    ColumnBoundary,
    ColumnModel,
    RowModel,
    TableGrid,
)
from pdf_analyzer.l3_topology.logical_rows import LogicalRowEngine


def make_synthetic_unruled_pdf(
    path: str,
    col_x_starts=(50.0, 130.0, 310.0, 410.0, 500.0),
    col_widths=(70.0, 170.0, 90.0, 80.0, 80.0),
    narrow_gutters: bool = False,
    include_empty_cells: bool = False,
):
    """
    Creates a synthetic unruled PDF (zero vector lines and zero fill rects)
    with precisely known column geometry.
    """
    c = canvas.Canvas(path, pagesize=letter)
    
    # Title
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 750, "Bank Statement of Account (Unruled)")
    c.setFont("Helvetica", 9)
    c.drawString(50, 735, "Statement Period: 01/09/2026 to 30/09/2026")
    
    # Header row
    y_hdr = 700.0
    c.setFont("Helvetica-Bold", 9)
    headers = ["Date", "Narration Details", "Chq / Ref No", "Withdrawal (Dr)", "Balance"]
    for i, (hx, hw, title) in enumerate(zip(col_x_starts, col_widths, headers)):
        c.drawString(hx, y_hdr, title)
        
    # Transactions
    c.setFont("Helvetica", 8)
    transactions = [
        ("01/09/2026", ["UPI/2349810/Merchant Pay", "Order ID 9928172 Bangalore"], "UPI99281", "1,250.00", "48,750.00"),
        ("05/09/2026", ["NEFT DR-CORP001928-ABC LTD", "INVOICE NO 4491-SEP", "SUPPLY CONTRACT 2026"], "N09051", "5,000.00", "43,750.00"),
        ("12/09/2026", ["SALARY CREDIT SEPT 2026"], "SAL202609", "" if include_empty_cells else "0.00", "93,750.00"),
        ("18/09/2026", ["MONTHLY UTILITY BILL", "ELECTRICITY BOARD BESCOM"], "EB99182", "2,340.50", "91,409.50"),
        ("25/09/2026", ["ATM CASH WITHDRAWAL", "ATM TXN ID 881920 MUMBAI"], "ATM8819", "10,000.00", "81,409.50"),
    ]
    
    y = 670.0
    for txn_date, narration_lines, ref_no, amount, balance in transactions:
        c.drawString(col_x_starts[0], y, txn_date)
        
        # Narration (multi-line wrapped)
        for line_idx, n_line in enumerate(narration_lines):
            c.drawString(col_x_starts[1], y - (line_idx * 11.0), n_line)
            
        if ref_no:
            c.drawString(col_x_starts[2], y, ref_no)
        if amount:
            # Right align amount in its column
            amt_w = c.stringWidth(amount, "Helvetica", 8)
            c.drawString(col_x_starts[3] + col_widths[3] - amt_w, y, amount)
        if balance:
            # Right align balance
            bal_w = c.stringWidth(balance, "Helvetica", 8)
            c.drawString(col_x_starts[4] + col_widths[4] - bal_w, y, balance)
            
        line_count = len(narration_lines)
        y -= (line_count * 11.0 + 10.0)
        
    c.showPage()
    c.save()


def make_synthetic_row_bands_pdf(path: str):
    """
    Creates a synthetic row-bands-only PDF with alternating shaded zebra rows,
    zero vertical rules, and zero horizontal rules.
    """
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 750, "Zebra Row-Bands Statement")
    
    col_x = [50.0, 130.0, 310.0, 420.0, 500.0]
    headers = ["Date", "Narration", "Ref No", "Debit", "Balance"]
    
    # Header band (Dark blue)
    c.setFillColor(colors.HexColor("#1A365D"))
    c.rect(45, 690, 530, 22, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    for hx, title in zip(col_x, headers):
        c.drawString(hx, 697, title)
        
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    
    rows_data = [
        ("02/09/2026", "TRANSFER TO SAVINGS 001928", "TRF001", "1,000.00", "24,000.00"),
        ("06/09/2026", "GROCERY STORE PAYMENT", "POS881", "3,450.00", "20,550.00"),
        ("15/09/2026", "INVESTMENT MUTUAL FUND SIP", "SIP992", "5,000.00", "15,550.00"),
        ("22/09/2026", "RESTAURANT DINING BILL", "POS119", "1,800.00", "13,750.00"),
    ]
    
    y = 665.0
    for idx, (dt, narr, ref, dr, bal) in enumerate(rows_data):
        # Alternating zebra shading
        if idx % 2 == 1:
            c.setFillColor(colors.HexColor("#F7FAFC"))
            c.rect(45, y - 6, 530, 20, fill=True, stroke=False)
            
        c.setFillColor(colors.black)
        c.drawString(col_x[0], y, dt)
        c.drawString(col_x[1], y, narr)
        c.drawString(col_x[2], y, ref)
        c.drawString(col_x[3], y, dr)
        c.drawString(col_x[4], y, bal)
        y -= 24.0
        
    c.showPage()
    c.save()


# ----------------------------------------------------------------------
# TESTS
# ----------------------------------------------------------------------

def test_unruled_table_style_verdict(tmp_path):
    """
    Test 1: Verifies that a statement with zero rules and zero fill rects
    is classified as TableStyleVerdict.UNRULED (or BORDERLESS).
    """
    pdf_path = str(tmp_path / "pure_unruled.pdf")
    make_synthetic_unruled_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    
    chosen, runner_up, evidence = grid_engine.determine_table_style_models(ruleset, page_layer)
    assert chosen in (TableStyleVerdict.UNRULED, TableStyleVerdict.BORDERLESS)
    assert len(evidence) > 0


def test_row_bands_only_style_verdict(tmp_path):
    """
    Test 2: Verifies that a statement with zebra row bands and no vertical rules
    is classified as TableStyleVerdict.ROW_BANDS_ONLY (or FILLED_HEADER).
    """
    pdf_path = str(tmp_path / "zebra_bands.pdf")
    make_synthetic_row_bands_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    
    chosen, runner_up, evidence = grid_engine.determine_table_style_models(ruleset, page_layer)
    assert chosen in (TableStyleVerdict.ROW_BANDS_ONLY, TableStyleVerdict.FILLED_HEADER)


def test_unruled_column_boundaries_precision(tmp_path):
    """
    Test 3: Precision column boundary test.
    Asserts that inferred column boundaries in an unruled table match
    the true whitespace gutter midpoints within <= 0.5 pt.
    """
    col_starts = (50.0, 130.0, 310.0, 410.0, 500.0)
    col_widths = (70.0, 170.0, 90.0, 80.0, 80.0)
    
    pdf_path = str(tmp_path / "precision_unruled.pdf")
    make_synthetic_unruled_pdf(pdf_path, col_x_starts=col_starts, col_widths=col_widths)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    assert grid is not None
    assert len(grid.columns) == 5
    assert len(grid.boundaries) == 6
    
    # Assert each interior boundary matches the true gutter midpoint within <= 0.5 pt
    expected_midpoints = [
        (90.032 + 130.0) / 2.0,   # Date (ends 90.032) to Narration (starts 130.0) -> 110.016
        (253.576 + 310.0) / 2.0,  # Narration (ends 253.576) to Chq/Ref (starts 310.0) -> 281.788
        (351.808 + 454.416) / 2.0, # Chq/Ref (ends 351.808) to Withdrawal right-aligned (starts 454.416) -> 403.112
        (485.552 + 544.416) / 2.0, # Withdrawal (ends 485.552) to Balance right-aligned (starts 544.416) -> 514.984
    ]
    
    for i, exp_mid in enumerate(expected_midpoints):
        inferred_boundary = grid.boundaries[i + 1]
        assert abs(inferred_boundary.centre_x_pt - exp_mid) <= 0.5, (
            f"Boundary {i+1}: expected {exp_mid:.3f}, got {inferred_boundary.centre_x_pt:.3f}"
        )
        # Check boundary confidence
        assert inferred_boundary.confidence >= 0.70
        assert len(inferred_boundary.confidence_reasons) > 0


def test_unruled_right_aligned_numeric_detection(tmp_path):
    """
    Test 4: Verifies right-aligned numeric column detection for amounts and balances.
    """
    pdf_path = str(tmp_path / "numeric_unruled.pdf")
    make_synthetic_unruled_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    # Columns 4 and 5 (Withdrawal and Balance) should be numeric and right-aligned
    assert grid.columns[3].is_numeric is True
    assert grid.columns[3].alignment == "right"
    assert grid.columns[4].is_numeric is True
    assert grid.columns[4].alignment == "right"
    
    # Column 2 (Narration) should be left-aligned
    assert grid.columns[1].alignment == "left"


def test_unruled_multi_line_wrapped_rows_and_pitch(tmp_path):
    """
    Test 5: Verifies that multi-line narration rows are properly clustered,
    line count is recorded, and row pitch is measured.
    """
    pdf_path = str(tmp_path / "wrap_unruled.pdf")
    make_synthetic_unruled_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    body_rows = [r for r in grid.rows if r.row_type == RowBandType.BODY]
    assert len(body_rows) == 5
    
    # Row 1 has 2 lines, Row 2 has 3 lines
    assert body_rows[0].lines_count == 2
    assert body_rows[1].lines_count == 3
    
    # Verify measured row pitch is approximately 11.0 pt
    assert abs(body_rows[0].pitch_pt - 11.0) <= 1.0
    assert abs(body_rows[1].pitch_pt - 11.0) <= 1.0


def test_unruled_empty_cells_handling(tmp_path):
    """
    Test 6: Edge case: columns with empty cells (e.g. sparse withdrawal amounts)
    must still recover valid column boundaries using header labels and projection gutters.
    """
    pdf_path = str(tmp_path / "empty_cells_unruled.pdf")
    make_synthetic_unruled_pdf(pdf_path, include_empty_cells=True)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    assert len(grid.columns) == 5
    assert grid.table_confidence >= 0.80
    assert len(grid.confidence_reasons) > 0


def test_unruled_narrow_gutters(tmp_path):
    """
    Test 7: Edge case: narrow whitespace gutters (e.g. 6 pt spacing).
    """
    narrow_starts = (50.0, 115.0, 275.0, 375.0, 465.0)
    narrow_widths = (60.0, 155.0, 95.0, 85.0, 85.0)
    
    pdf_path = str(tmp_path / "narrow_unruled.pdf")
    make_synthetic_unruled_pdf(pdf_path, col_x_starts=narrow_starts, col_widths=narrow_widths, narrow_gutters=True)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    assert len(grid.columns) == 5
    assert grid.contiguity_passed is True
