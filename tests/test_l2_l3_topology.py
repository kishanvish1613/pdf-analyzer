"""
Unit and Regression Test Suite for L2 Primitives & L3 Topology.
Tests RuleSet canonical extraction, collinear merging, double-stroke fusion,
planar graph container polygonization, strict column contiguity, ReportLab fixtures,
hypothesis random grids, mutation sensitivity, and real bank statement truth recovery.
"""

from __future__ import annotations
import os
import io
import pytest
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from hypothesis import given, strategies as st, settings

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.containers import PlanarGraphEngine, Container
from pdf_analyzer.l3_topology.table_grid import TableGridEngine, TableGrid
from pdf_analyzer.l1_crosscheck.gates import GateEvaluator


def create_pdf_bytes_from_canvas_fn(fn) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    fn(c)
    c.save()
    return buf.getvalue()


# ==============================================================================
# 1. L2 RuleSet Unit Tests
# ==============================================================================

def test_ruleset_collinear_merge(tmp_path):
    """Verifies that collinear overlapping stroke segments are merged within 0.15 pt tolerance."""
    pdf_path = str(tmp_path / "collinear.pdf")

    def draw(c):
        c.setLineWidth(1.0)
        c.setStrokeColor(colors.black)
        c.line(50, 200, 150, 200)
        c.line(140, 200, 250, 200)

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)

    assert len(ruleset.h_rules) == 1
    h = ruleset.h_rules[0]
    assert abs(h.centre - 200.0) < 0.05
    assert abs(h.start - 50.0) < 0.05
    assert abs(h.end - 250.0) < 0.05


def test_ruleset_double_stroke_fusion(tmp_path):
    """Verifies that parallel double-stroke rules closer than 3 pt become ONE boundary reporting inner gap."""
    pdf_path = str(tmp_path / "double_stroke.pdf")

    def draw(c):
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.black)
        c.line(50, 300, 300, 300)
        c.line(50, 301.5, 300, 301.5)

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)

    assert len(ruleset.h_rules) == 1
    h = ruleset.h_rules[0]
    assert h.is_double is True
    assert abs(h.centre - 300.75) < 0.05
    assert abs(h.double_gap - 1.0) < 0.1


def test_ruleset_thin_filled_rect_rules(tmp_path):
    """Verifies that thin filled rectangles (< 3 pt) are extracted as rules."""
    pdf_path = str(tmp_path / "thin_rects.pdf")

    def draw(c):
        c.setFillColor(colors.HexColor("#555555"))
        c.rect(120, 200, 0.6, 100, fill=1, stroke=0)

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)

    assert len(ruleset.v_rules) == 1
    v = ruleset.v_rules[0]
    assert abs(v.centre - 120.3) < 0.05
    assert abs(v.width - 0.6) < 0.05
    assert abs(v.span - 100.0) < 0.05


# ==============================================================================
# 2. L3 Planar Graph Containers Unit Tests
# ==============================================================================

def test_containers_4_line_box_recovery(tmp_path):
    """Tests polygonization of 4 individual stroked lines into a closed rectangular container."""
    pdf_path = str(tmp_path / "box_4lines.pdf")

    def draw(c):
        c.setLineWidth(1.0)
        c.setStrokeColor(colors.black)
        c.line(50, 100, 250, 100)
        c.line(50, 200, 250, 200)
        c.line(50, 100, 50, 200)
        c.line(250, 100, 250, 200)

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        containers = PlanarGraphEngine().extract_containers(ruleset, page_layer)

    assert len(containers) >= 1
    box_c = containers[0]
    assert box_c.is_closed is True
    assert abs(box_c.width_pt - 200.0) < 0.1
    assert abs(box_c.height_pt - 100.0) < 0.1
    assert "top" in box_c.sides
    assert "bottom" in box_c.sides
    assert "left" in box_c.sides
    assert "right" in box_c.sides


def test_containers_open_3side_detection(tmp_path):
    """Tests identification of 3-sided open boxes (e.g. missing bottom border)."""
    pdf_path = str(tmp_path / "open_box.pdf")

    def draw(c):
        c.setLineWidth(1.0)
        c.setStrokeColor(colors.black)
        c.line(50, 300, 250, 300)
        c.line(50, 150, 50, 300)
        c.line(250, 150, 250, 300)

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        containers = PlanarGraphEngine().extract_containers(ruleset, page_layer)

    open_boxes = [c for c in containers if c.is_open_3side]
    assert len(open_boxes) == 1
    ob = open_boxes[0]
    assert ob.open_side == "bottom"
    assert ob.is_closed is False


# ==============================================================================
# 3. ReportLab Fixture Suite (Diverse Table Layouts)
# ==============================================================================

def test_fixture_full_grid_table(tmp_path):
    """Fixture 1: Full grid table with 4 columns and 5 rows."""
    pdf_path = str(tmp_path / "full_grid.pdf")

    def draw(c):
        c.setLineWidth(0.75)
        c.setStrokeColor(colors.black)
        for x in [50, 150, 250, 350, 450]:
            c.line(x, 200, x, 350)
        for y in [200, 230, 260, 290, 320, 350]:
            c.line(50, y, 450, y)

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        table = TableGridEngine().build_table_grid(ruleset, page_layer)

    assert len(table.columns) == 4
    assert len(table.rows) == 5
    assert table.contiguity_passed is True
    for col in table.columns:
        assert abs(col.width_pt - (100.0 - 0.75)) < 0.1


def test_fixture_vertical_rules_only_wrapped_rows(tmp_path):
    """Fixture 2: Vertical rules only, text anchor date clustering creates logical rows."""
    pdf_path = str(tmp_path / "vertical_only.pdf")

    def draw(c):
        c.setLineWidth(1.0)
        c.setStrokeColor(colors.black)
        for x in [50, 150, 350, 500]:
            c.line(x, 200, x, 400)
        c.line(50, 400, 500, 400)
        c.line(50, 200, 500, 200)

        c.setFont("Helvetica", 10)
        c.drawString(60, 385, "Date")
        c.drawString(160, 385, "Description")
        c.drawString(360, 385, "Amount")

        c.drawString(60, 350, "01/01/2026")
        c.drawString(160, 350, "Salary Deposit from Employer")
        c.drawString(160, 338, "Transaction Ref #987654321")
        c.drawString(360, 350, "5,000.00")

        c.drawString(60, 310, "02/01/2026")
        c.drawString(160, 310, "Grocery Store Purchase")
        c.drawString(360, 310, "150.00")

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        table = TableGridEngine().build_table_grid(ruleset, page_layer)

    assert len(table.columns) == 3
    assert len(table.rows) >= 2
    assert table.contiguity_passed is True


def test_fixture_cr_suffix_touching_right_border(tmp_path):
    """Fixture 3: 'Cr.' suffix close to right rule, ensuring right rule is exact right boundary."""
    pdf_path = str(tmp_path / "cr_suffix.pdf")

    def draw(c):
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.black)
        for x in [50, 200, 350, 500]:
            c.line(x, 200, x, 300)
        c.line(50, 300, 500, 300)
        c.line(50, 200, 500, 200)

        c.setFont("Helvetica", 9)
        c.drawString(360, 250, "12,450.00 Cr.")

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        table = TableGridEngine().build_table_grid(ruleset, page_layer)

    assert len(table.columns) == 3
    last_col = table.columns[-1]
    assert abs(last_col.x1_pt - 499.75) < 0.05
    assert abs(table.table_bbox_pt[2] - 500.25) < 0.05


# ==============================================================================
# 4. Hypothesis Randomized Grid Recovery Test
# ==============================================================================

@settings(max_examples=10, deadline=None)
@given(
    widths=st.lists(st.floats(min_value=30.0, max_value=120.0), min_size=2, max_size=5),
)
def test_hypothesis_random_grid(tmp_path_factory, widths):
    """Randomized grid test verifying exact column width recovery within 0.05 pt."""
    tmp_path = tmp_path_factory.mktemp("hypo_grid")
    pdf_path = str(tmp_path / "random_grid.pdf")

    line_w = 0.5
    start_x = 50.0
    x_positions = [start_x]
    for w in widths:
        x_positions.append(x_positions[-1] + w)

    def draw(c):
        c.setLineWidth(line_w)
        c.setStrokeColor(colors.black)
        for x in x_positions:
            c.line(x, 100, x, 300)
        c.line(x_positions[0], 300, x_positions[-1], 300)
        c.line(x_positions[0], 100, x_positions[-1], 100)

    pdf_bytes = create_pdf_bytes_from_canvas_fn(draw)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        table = TableGridEngine().build_table_grid(ruleset, page_layer)

    assert len(table.columns) == len(widths)
    assert table.contiguity_passed is True

    for i, exp_w in enumerate(widths):
        recovered_w = table.columns[i].width_pt
        assert abs(recovered_w - (exp_w - line_w)) < 0.05


# ==============================================================================
# 5. Mutation Test: Shift One Rule by 1.0 pt
# ==============================================================================

def test_mutation_rule_shift(tmp_path):
    """Shifting one interior rule by 1.0 pt changes exactly the two adjacent column widths by 1.0 pt."""
    base_pdf = str(tmp_path / "base.pdf")
    mut_pdf = str(tmp_path / "mutated.pdf")

    def draw_base(c):
        c.setLineWidth(1.0)
        c.setStrokeColor(colors.black)
        for x in [50, 150, 250, 350]:
            c.line(x, 100, x, 300)
        c.line(50, 300, 350, 300)
        c.line(50, 100, 350, 100)

    def draw_mutated(c):
        c.setLineWidth(1.0)
        c.setStrokeColor(colors.black)
        for x in [50, 151, 250, 350]:
            c.line(x, 100, x, 300)
        c.line(50, 300, 350, 300)
        c.line(50, 100, 350, 100)

    with open(base_pdf, "wb") as f:
        f.write(create_pdf_bytes_from_canvas_fn(draw_base))
    with open(mut_pdf, "wb") as f:
        f.write(create_pdf_bytes_from_canvas_fn(draw_mutated))

    with ByteLayerExtractor(base_pdf) as ext_b, ByteLayerExtractor(mut_pdf) as ext_m:
        grid_b = TableGridEngine().build_table_grid(RuleSet.from_page_layer(ext_b.extract_page(1)), ext_b.extract_page(1))
        grid_m = TableGridEngine().build_table_grid(RuleSet.from_page_layer(ext_m.extract_page(1)), ext_m.extract_page(1))

    assert abs((grid_m.columns[0].width_pt - grid_b.columns[0].width_pt) - 1.0) < 0.05
    assert abs((grid_m.columns[1].width_pt - grid_b.columns[1].width_pt) - (-1.0)) < 0.05
    assert abs(grid_m.columns[2].width_pt - grid_b.columns[2].width_pt) < 0.05
    assert abs(grid_m.outer_width_pt - grid_b.outer_width_pt) < 0.05


# ==============================================================================
# 6. Real Statement Ground Truth Test: Bank of India (7 Columns)
# ==============================================================================

def test_real_bank_of_india_7_columns():
    """Verifies that Bank of India statement recovers exactly 7 columns strictly from RuleSet."""
    boi_path = "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf"
    if not os.path.exists(boi_path):
        pytest.skip("Bank of India sample PDF not present")

    with ByteLayerExtractor(boi_path) as extractor:
        page_layer = extractor.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        table = TableGridEngine().build_table_grid(ruleset, page_layer)

    assert len(table.columns) == 7
    assert table.contiguity_passed is True
    assert len(table.unused_qualifying_rules) == 0

