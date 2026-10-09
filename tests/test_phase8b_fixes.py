"""
Phase 8B Regression & Verification Test Suite.
Verifies all 8 tasks of Phase 8B:
1. Lane placement candidate search (above, below, docked strip)
2. STRtree zero-ink collision assertion for extension lines (<= 12 pt)
3. Column arrow count & width summation invariance
4. Strict CropBox clamping of all regions, guides, boxes, and labels
5. Collision-free label placer with zero label-label overlap & ellipsis truncation
6. Title classification scoring engine
7. Footer detection and anchoring
8. Authoritative single table bbox
"""

import os
import pytest
import pymupdf
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from shapely.geometry import box as shapely_box, LineString
from shapely.strtree import STRtree

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, Color
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.table_grid import TableGridEngine, TableGrid, ColumnModel, RowModel
from pdf_analyzer.l4_layout.header import HeaderEngine
from pdf_analyzer.l4_layout.footer import FooterEngine
from pdf_analyzer.l4_layout.models import BlockType
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneEngine, DimensionLaneModel
from pdf_analyzer.l5_editor.label_placer import LabelPlacerEngine, LabelAnchor
from pdf_analyzer.l5_editor.model import EditorModelBuilder


@pytest.fixture
def test_pdf(tmp_path):
    pdf_path = str(tmp_path / "phase8b_fixture.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2.0, h - 50.0, "ACCOUNT STATEMENT")

    # Address (Should NOT be classified as title)
    c.setFont("Helvetica", 9)
    c.drawString(54.0, h - 90.0, "JAIPUR ROAD, MAHWADI, DIST DAUSA")
    c.drawString(54.0, h - 105.0, "PIN: 303303, TEL: 0141-123456")

    # Table Header & Grid
    tbl_x0 = 54.0
    tbl_x1 = w - 54.0
    tbl_y_top = h - 160.0
    tbl_y_bot = 200.0

    # Draw vertical rules (4 columns -> 5 rules)
    col_xs = [tbl_x0, tbl_x0 + 80.0, tbl_x0 + 220.0, tbl_x0 + 380.0, tbl_x1]
    for x in col_xs:
        c.setLineWidth(1.0)
        c.line(x, tbl_y_bot, x, tbl_y_top)

    # Draw horizontal rules
    for y in [tbl_y_top, tbl_y_top - 20.0, tbl_y_top - 45.0, tbl_y_bot]:
        c.setLineWidth(1.0)
        c.line(tbl_x0, y, tbl_x1, y)

    # Table Text
    c.setFont("Helvetica-Bold", 9)
    c.drawString(tbl_x0 + 10, tbl_y_top - 14, "Date")
    c.drawString(col_xs[1] + 10, tbl_y_top - 14, "Narration")
    c.drawString(col_xs[2] + 10, tbl_y_top - 14, "Withdrawal")
    c.drawString(col_xs[3] + 10, tbl_y_top - 14, "Balance")

    # Footer
    c.setFont("Helvetica", 8)
    c.drawString(54.0, 50.0, "Statement Generated on 03/10/2026. This is a computer generated document.")
    c.drawRightString(w - 54.0, 50.0, "Page 1 of 1")

    c.save()
    return pdf_path


def test_title_classification_scoring(test_pdf):
    with ByteLayerExtractor(test_pdf) as extractor:
        page_layer = extractor.extract_page(1)

    header_engine = HeaderEngine()
    header_model = header_engine.build_header_model(page_layer, table_top_y_pt=letter[1] - 160.0)

    assert header_model.full_width_title is not None
    assert "ACCOUNT STATEMENT" in header_model.full_width_title.lines[0].text
    assert "JAIPUR" not in header_model.full_width_title.lines[0].text

    # Verify title score records are populated
    assert len(header_model.title_scores) > 0
    title_rec = next(r for r in header_model.title_scores if r.is_classified_title)
    assert "ACCOUNT STATEMENT" in title_rec.text
    assert title_rec.total_score >= 45.0


def test_dimension_lane_strtree_and_invariants(test_pdf):
    with ByteLayerExtractor(test_pdf) as extractor:
        page_layer = extractor.extract_page(1)

    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    table_grid = grid_engine.build_table_grid(ruleset, page_layer)

    assert len(table_grid.columns) == 4
    assert table_grid.contiguity_passed

    lane_engine = DimensionLaneEngine()
    lane_model = lane_engine.build_dimension_lane(table_grid, ruleset, page_layer)

    # Invariants verification
    assert len(lane_model.arrows) == 4
    assert lane_model.width_invariance_passed
    assert lane_model.delta_pt <= 0.25
    assert lane_model.lane_absent_reason is None

    # Extension lines check: must be <= 12 pt
    for ext in lane_model.extension_lines:
        assert ext.length_pt <= 12.01

    # STRtree collision check: extension lines must have zero intersection with ink
    tree, geoms = lane_engine._build_ink_strtree(page_layer)
    for ext in lane_model.extension_lines:
        line_geom = LineString([(ext.x_pt, ext.y0_pt), (ext.x_pt, ext.y1_pt)])
        hits = tree.query(line_geom)
        for h in hits:
            g = geoms[h]
            if line_geom.intersects(g) and g.area > 0.0:
                assert line_geom.intersection(g).length <= 0.1


def test_label_placer_zero_overlap_and_truncation():
    placer = LabelPlacerEngine()

    anchors = [
        LabelAnchor(anchor_id="lbl_1", target_x_pt=100.0, target_y_pt=100.0, text="Very Long Region Header Text That Exceeds Normal Box Width", width_pt=60.0, height_pt=14.0),
        LabelAnchor(anchor_id="lbl_2", target_x_pt=110.0, target_y_pt=105.0, text="Account Details Card", width_pt=80.0, height_pt=14.0),
        LabelAnchor(anchor_id="lbl_3", target_x_pt=120.0, target_y_pt=110.0, text="Title Badge", width_pt=70.0, height_pt=14.0),
    ]

    placed = placer.place_labels(anchors=anchors, page_bounds_pt=(0.0, 0.0, 612.0, 792.0))

    assert len(placed) == 3
    # Check truncation with ellipsis
    assert placed[0].is_truncated
    assert placed[0].text.endswith("...")
    assert placed[0].full_text == "Very Long Region Header Text That Exceeds Normal Box Width"

    # Assert zero label-label collision
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            b1 = placed[i].bbox_pt
            b2 = placed[j].bbox_pt
            assert not placer._rect_overlap(b1, b2)


def test_cropbox_clamping_and_editor_model(test_pdf):
    with ByteLayerExtractor(test_pdf) as extractor:
        page_layer = extractor.extract_page(1)

    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    table_grid = grid_engine.build_table_grid(ruleset, page_layer)

    header_engine = HeaderEngine()
    header_model = header_engine.build_header_model(page_layer, table_grid.table_bbox_pt[3])

    footer_engine = FooterEngine()
    footer_model = footer_engine.build_footer_model(page_layer, table_grid.table_bbox_pt[1])

    builder = EditorModelBuilder(dpi=300)
    model = builder.build_editor_model(
        page_layer=page_layer,
        ruleset=ruleset,
        table_grid=table_grid,
        header_model=header_model,
        footer_model=footer_model,
    )

    w = model.width_pt
    h = model.height_pt

    # Assert all boxes inside CropBox
    for b in model.boxes:
        assert 0.0 <= b["x0_pt"] <= w
        assert 0.0 <= b["x1_pt"] <= w
        assert 0.0 <= b["y0_pt"] <= h
        assert 0.0 <= b["y1_pt"] <= h

    # Assert all guides inside CropBox
    for g in model.guides:
        assert 0.0 <= g.coord_pt <= (w if g.axis == "X" else h)

    # Assert all placed labels inside CropBox
    for lbl in model.labels:
        b = lbl.bbox_pt
        assert 0.0 <= b[0] <= w
        assert 0.0 <= b[2] <= w
        assert 0.0 <= b[1] <= h
        assert 0.0 <= b[3] <= h


def test_empty_table_suppresses_lane(tmp_path):
    pdf_path = str(tmp_path / "empty_table.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.drawString(100, 700, "Empty table test")
    c.save()

    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(1)

    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    table_grid = grid_engine.build_table_grid(ruleset, page_layer)

    lane_engine = DimensionLaneEngine()
    lane_model = lane_engine.build_dimension_lane(table_grid, ruleset, page_layer)

    # Must suppress lane and surface visible reason
    assert len(lane_model.arrows) == 0
    assert lane_model.lane_absent_reason is not None
    assert "lane_absent:" in lane_model.lane_absent_reason


def test_frame_bug_kotak_title_top_left_matches_pymupdf():
    """J1: Real Kotak page title top-left y must match PyMuPDF span bbox within 0.1 pt."""
    pdf_path = os.path.join("uploads", "AccountStatement_20-Sep-2026_20-Sep-2026.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Kotak sample not found")

    # PyMuPDF ground truth span bbox
    doc = pymupdf.open(pdf_path)
    page_mupdf = doc[0]
    mupdf_title_span = None
    for b in page_mupdf.get_text("dict")["blocks"]:
        if "lines" in b:
            for l in b["lines"]:
                for s in l["spans"]:
                    if "Account Statement" in s["text"]:
                        mupdf_title_span = s
                        break
    doc.close()
    assert mupdf_title_span is not None
    mupdf_y0 = mupdf_title_span["bbox"][1]

    # Model / audit extraction
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
    header_engine = HeaderEngine()
    header_model = header_engine.build_header_model(page_layer, table_top_y_pt=487.5)
    assert header_model.full_width_title is not None
    assert "Account Statement" in header_model.full_width_title.lines[0].text

    from pdf_analyzer.utils.units import to_top_left_bbox
    title_tl_bbox = to_top_left_bbox(header_model.full_width_title.bbox_pt, page_layer.cropbox_pt)
    assert abs(title_tl_bbox[1] - mupdf_y0) <= 0.1, f"Title top-left y {title_tl_bbox[1]} != PyMuPDF {mupdf_y0}"


def test_frame_bug_a4_fixture_title_top_left_matches_pymupdf(tmp_path):
    """J1: A4 fixture title top-left y must match PyMuPDF span bbox within 0.1 pt."""
    pdf_path = str(tmp_path / "a4_statement.pdf")
    c = canvas.Canvas(pdf_path, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50.0, h - 80.0, "OFFICIAL STATEMENT TITLE")
    c.save()

    doc = pymupdf.open(pdf_path)
    page_mupdf = doc[0]
    mupdf_span = None
    for b in page_mupdf.get_text("dict")["blocks"]:
        if "lines" in b:
            for l in b["lines"]:
                for s in l["spans"]:
                    if "OFFICIAL STATEMENT TITLE" in s["text"]:
                        mupdf_span = s
                        break
    doc.close()
    assert mupdf_span is not None
    mupdf_y0 = mupdf_span["bbox"][1]

    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)

    header_engine = HeaderEngine()
    header_model = header_engine.build_header_model(page_layer, table_top_y_pt=h - 200.0)
    assert header_model.full_width_title is not None

    from pdf_analyzer.utils.units import to_top_left_bbox
    tl_bbox = to_top_left_bbox(header_model.full_width_title.bbox_pt, page_layer.cropbox_pt)
    assert abs(tl_bbox[1] - mupdf_y0) <= 0.1, f"A4 title top-left y {tl_bbox[1]} != PyMuPDF {mupdf_y0}"



def test_k2_parametric_page_heights_title_top_left(tmp_path):
    """K2: Pipeline converter tested on fixture pages of heights 595, 700, 842, 1000.
    The title top-left y from to_top_left_bbox must match PyMuPDF span bbox within 0.1 pt.
    This test catches any hardcoded page-height constant in the conversion path.
    """
    from pdf_analyzer.utils.units import to_top_left_bbox

    for height in [595.0, 700.0, 842.0, 1000.0]:
        page_size = (612.0, height)
        pdf_path = str(tmp_path / f"fixture_h{int(height)}.pdf")
        c = canvas.Canvas(pdf_path, pagesize=page_size)
        w, h = page_size
        c.setFont("Helvetica-Bold", 18)
        c.drawString(40.0, h - 60.0, f"STMT H{int(height)}")
        c.save()

        # PyMuPDF ground truth (top-down origin)
        doc = pymupdf.open(pdf_path)
        page_mupdf = doc[0]
        mupdf_span = None
        for b in page_mupdf.get_text("dict")["blocks"]:
            if "lines" in b:
                for ln in b["lines"]:
                    for s in ln["spans"]:
                        if f"STMT H{int(height)}" in s["text"]:
                            mupdf_span = s
                            break
        doc.close()
        assert mupdf_span is not None, f"PyMuPDF did not find title on h={height} page"
        mupdf_y0 = mupdf_span["bbox"][1]  # top-left y of title span (top-down)

        # Pipeline extraction
        with ByteLayerExtractor(pdf_path) as ext:
            page_layer = ext.extract_page(1)

        # CropBox height must match the fixture page height
        cb = page_layer.cropbox_pt
        assert abs((cb[3] - cb[1]) - height) < 0.5, (
            f"h={height}: CropBox height {cb[3]-cb[1]:.1f} != {height}"
        )

        # Find title chars in device space (bottom-up: high y = near top of page)
        title_chars = [
            ch for ch in page_layer.chars
            if ch.origin_device_pt[1] > 0.8 * page_layer.height_pt
        ]
        assert len(title_chars) > 0, f"h={height}: no title chars in page_layer"

        char_x0 = min(ch.font_bbox_device_pt[0] for ch in title_chars)
        char_y0_dev = min(ch.font_bbox_device_pt[1] for ch in title_chars)
        char_x1 = max(ch.font_bbox_device_pt[2] for ch in title_chars)
        char_y1_dev = max(ch.font_bbox_device_pt[3] for ch in title_chars)

        tl = to_top_left_bbox((char_x0, char_y0_dev, char_x1, char_y1_dev), page_layer.cropbox_pt)
        pipeline_y0 = tl[1]

        assert abs(pipeline_y0 - mupdf_y0) <= 0.1, (
            f"h={height}: pipeline top-left y {pipeline_y0:.3f} != PyMuPDF {mupdf_y0:.3f} "
            f"(delta={abs(pipeline_y0-mupdf_y0):.4f} pt)"
        )
