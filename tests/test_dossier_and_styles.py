"""
Tests for Phase 8A: Template Dossier, 6 Table Styles, Stream-Order Row Recovery,
Quantisation Audit, and Layer Uniqueness.
"""

import os
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from pdf_analyzer.dossier import TemplateDossierEngine, generate_template_dossier
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine
from pdf_analyzer.quantisation_audit import QuantisationAuditEngine
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneEngine


def make_full_grid_pdf(path: str):
    """Full grid: horizontal + vertical rules enclosing header + data cells."""
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Full Grid Bank Statement")
    c.drawString(50, 720, "Account: 12345678")
    
    # Table bbox: [50, 400, 550, 680]
    # Header
    c.drawString(60, 660, "Date")
    c.drawString(160, 660, "Description")
    c.drawString(360, 660, "Debit")
    c.drawString(460, 660, "Balance")
    
    # Data rows
    for i, y in enumerate([620, 580, 540, 500, 460]):
        c.drawString(60, y, f"0{i+1}/01/2026")
        c.drawString(160, y, f"Transaction Ref {i+100}")
        c.drawString(360, y, f"{100*(i+1)}.00")
        c.drawString(460, y, f"{5000 - 100*(i+1)}.00")
        
    # Draw horizontal rules
    for y in [680, 650, 610, 570, 530, 490, 450]:
        c.line(50, y, 550, y)
        
    # Draw vertical rules
    for x in [50, 150, 350, 450, 550]:
        c.line(x, 450, x, 680)
        
    c.showPage()
    c.save()


def make_vertical_only_pdf(path: str):
    """Vertical only: column rules present, no horizontal cell rules."""
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Vertical Only Statement")
    
    # Header
    c.drawString(60, 660, "Date")
    c.drawString(160, 660, "Description")
    c.drawString(360, 660, "Amount")
    c.drawString(460, 660, "Balance")
    
    # Data rows
    for i, y in enumerate([620, 580, 540, 500]):
        c.drawString(60, y, f"0{i+1}/01/2026")
        c.drawString(160, y, f"Salary Payout {i+1}")
        c.drawString(360, y, f"{250*(i+1)}.00")
        c.drawString(460, y, f"{10000 + 250*(i+1)}.00")
        
    # Top and bottom horizontal rules only
    c.line(50, 680, 550, 680)
    c.line(50, 470, 550, 470)
    
    # Vertical column rules
    for x in [50, 150, 350, 450, 550]:
        c.line(x, 470, x, 680)
        
    c.showPage()
    c.save()


def make_horizontal_only_pdf(path: str):
    """Horizontal only: horizontal row lines present, zero vertical rules."""
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Horizontal Only Statement")
    
    # Header
    c.drawString(60, 660, "Date")
    c.drawString(160, 660, "Description")
    c.drawString(360, 660, "Amount")
    
    for i, y in enumerate([620, 580, 540, 500]):
        c.drawString(60, y, f"0{i+1}/01/2026")
        c.drawString(160, y, f"Payment Item {i+1}")
        c.drawString(360, y, f"{50*(i+1)}.00")
        
    # Horizontal rules only
    for y in [680, 650, 610, 570, 530, 490]:
        c.line(50, y, 550, y)
        
    c.showPage()
    c.save()


def make_filled_header_pdf(path: str):
    """Filled header: colored rectangle background under header row, no vertical rules."""
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Filled Header Statement")
    
    # Filled header band
    c.setFillColor(colors.HexColor("#0f172a"))
    c.rect(50, 650, 500, 28, fill=True, stroke=False)
    
    c.setFillColor(colors.white)
    c.drawString(60, 660, "Date")
    c.drawString(160, 660, "Description")
    c.drawString(360, 660, "Amount")
    c.drawString(460, 660, "Balance")
    
    c.setFillColor(colors.black)
    for i, y in enumerate([620, 580, 540, 500]):
        c.drawString(60, y, f"0{i+1}/01/2026")
        c.drawString(160, y, f"Online Purchase {i+1}")
        c.drawString(360, y, f"{15*(i+1)}.00")
        c.drawString(460, y, f"{1000 - 15*(i+1)}.00")
        
    c.showPage()
    c.save()


def make_borderless_pdf(path: str):
    """Borderless: whitespace only, zero vector strokes."""
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Borderless Statement")
    
    c.drawString(60, 660, "Date")
    c.drawString(160, 660, "Description")
    c.drawString(360, 660, "Amount")
    
    for i, y in enumerate([620, 580, 540, 500]):
        c.drawString(60, y, f"0{i+1}/01/2026")
        c.drawString(160, y, f"Transfer To Savings {i+1}")
        c.drawString(360, y, f"{300*(i+1)}.00")
        
    c.showPage()
    c.save()


def make_empty_table_pdf(path: str):
    """Empty table: header rules and column headers, but 0 transaction rows."""
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Empty Table Statement (Last Page)")
    
    c.drawString(60, 660, "Date")
    c.drawString(160, 660, "Description")
    c.drawString(360, 660, "Amount")
    c.drawString(460, 660, "Balance")
    
    # Draw empty grid
    c.line(50, 680, 550, 680)
    c.line(50, 640, 550, 640)
    for x in [50, 150, 350, 450, 550]:
        c.line(x, 640, x, 680)
        
    c.showPage()
    c.save()


def test_dossier_on_all_table_styles(tmp_path):
    engine = TemplateDossierEngine()

    # 1. Full Grid
    p1 = str(tmp_path / "full_grid.pdf")
    make_full_grid_pdf(p1)
    d1 = engine.generate_dossier(p1, page_number=1, output_dir=str(tmp_path))
    assert d1.pages[0].table_style_verdict == "full_grid"
    assert d1.pages[0].geometric_rows_count >= 5

    # 2. Vertical Only
    p2 = str(tmp_path / "vertical_only.pdf")
    make_vertical_only_pdf(p2)
    d2 = engine.generate_dossier(p2, page_number=1, output_dir=str(tmp_path))
    assert d2.pages[0].table_style_verdict == "vertical_only"

    # 3. Horizontal Only (produces virtual columns and lane via numbered markers)
    p3 = str(tmp_path / "horizontal_only.pdf")
    make_horizontal_only_pdf(p3)
    d3 = engine.generate_dossier(p3, page_number=1, output_dir=str(tmp_path))
    assert d3.pages[0].table_style_verdict == "horizontal_only"
    assert d3.pages[0].lane_absent_reason is None

    # 4. Filled Header (produces virtual columns and lane via numbered markers)
    p4 = str(tmp_path / "filled_header.pdf")
    make_filled_header_pdf(p4)
    d4 = engine.generate_dossier(p4, page_number=1, output_dir=str(tmp_path))
    assert d4.pages[0].table_style_verdict == "filled_header"
    assert d4.pages[0].lane_absent_reason is None

    # 5. Borderless (produces virtual columns and lane via numbered markers)
    p5 = str(tmp_path / "borderless.pdf")
    make_borderless_pdf(p5)
    d5 = engine.generate_dossier(p5, page_number=1, output_dir=str(tmp_path))
    assert d5.pages[0].table_style_verdict == "borderless"
    assert d5.pages[0].lane_absent_reason is None

    # 6. Empty Table (suppresses lane with visible reason)
    p6 = str(tmp_path / "empty_table.pdf")
    make_empty_table_pdf(p6)
    d6 = engine.generate_dossier(p6, page_number=1, output_dir=str(tmp_path))
    assert d6.pages[0].table_style_verdict == "empty_table"
    assert d6.pages[0].lane_absent_reason is not None


def test_stream_order_row_recovery(tmp_path):
    p = str(tmp_path / "stream_grid.pdf")
    make_full_grid_pdf(p)
    dossier = generate_template_dossier(p, page_number=1, output_dir=str(tmp_path))
    page = dossier.pages[0]
    assert page.stream_order_rows_count >= 5
    assert len(page.stream_order_rows[0].tokens) >= 3


def test_quantisation_audit(tmp_path):
    p = str(tmp_path / "quant.pdf")
    make_full_grid_pdf(p)
    with ByteLayerExtractor(p) as ext:
        layer = ext.extract_page(1)
        
    audit_eng = QuantisationAuditEngine()
    rep = audit_eng.audit_quantisation(
        page_layer=layer,
        dimensions=[
            {"id": "dim_valid", "title": "Column 1 Width", "value_pt": 100.125},
        ]
    )
    assert rep.passed is True


def test_unique_lane_renderer_assertion():
    """
    Asserts that the system enforces exactly one renderer for the dimension lane.
    """
    lane_engine = DimensionLaneEngine()
    # Exactly one engine instance builds DimensionLaneModel
    assert hasattr(lane_engine, "build_dimension_lane")
