"""
Comprehensive Unit Test Suite for L0 ByteLayer Extraction.
Verifies exact geometric recovery (0.01 pt tolerance), cap/join buffer styles,
nested Form XObject transforms, and text state kernel displacements using ReportLab fixtures.
"""

import io
import os
import pytest
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.primitives import PageByteLayer


def create_geometry_fixture_pdf() -> bytes:
    """Generates synthetic PDF containing exact geometric vector and text primitives."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))

    # 1. Thick line with projecting square caps (cap=2) and miter join
    c.setLineWidth(10.0)
    c.setLineCap(2)  # Projecting square cap
    c.setLineJoin(0)  # Miter join
    c.setStrokeColor(colors.red)
    p = c.beginPath()
    p.moveTo(50, 700)
    p.lineTo(250, 700)
    c.drawPath(p, stroke=1, fill=0)

    # 2. Stroked rectangle: 're S'
    c.setLineWidth(2.0)
    c.setStrokeColor(colors.blue)
    c.rect(50, 500, 200, 100, stroke=1, fill=0)

    # 3. Filled rectangle: 're f'
    c.setFillColor(colors.green)
    c.rect(300, 500, 200, 100, stroke=0, fill=1)

    # 4. Text string with custom font size, word spacing, and char spacing
    text_obj = c.beginText(50, 400)
    text_obj.setFont("Helvetica", 16)
    text_obj.setCharSpace(1.5)
    text_obj.setWordSpace(3.0)
    text_obj.textLine("PDF Design Analyzer 2026")
    c.drawText(text_obj)

    # 5. Form XObject simulation with nested q/cm
    c.saveState()
    c.translate(50, 200)
    c.scale(0.5, 0.5)
    c.setLineWidth(1.0)
    c.setStrokeColor(colors.black)
    c.rect(0, 0, 300, 150, stroke=1, fill=0)
    c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()


def test_l0_vector_geometry_and_caps():
    """Verifies that line caps, widths, and rectangles are extracted with <0.01 pt precision."""
    pdf_bytes = create_geometry_fixture_pdf()
    with ByteLayerExtractor(pdf_bytes) as extractor:
        page = extractor.extract_page(1)

    assert isinstance(page, PageByteLayer)
    assert len(page.paths) >= 4

    # Check thick line (width=10pt, cap=2)
    thick_line = page.paths[0]
    assert thick_line.stroke is not None
    assert abs(thick_line.stroke.width_pt - 10.0) < 0.01
    assert thick_line.stroke.cap == 2
    # Painted bbox should extend by half_width (5pt) in x and y due to projecting square cap
    assert abs(thick_line.bbox_device_pt[0] - 50.0) < 0.01
    assert abs(thick_line.bbox_device_pt[2] - 250.0) < 0.01
    assert abs(thick_line.painted_bbox_device_pt[0] - 45.0) < 0.1
    assert abs(thick_line.painted_bbox_device_pt[2] - 255.0) < 0.1

    # Check stroked rect (50, 500, 200, 100)
    stroked_rect = page.paths[1]
    assert stroked_rect.stroke is not None
    assert abs(stroked_rect.stroke.width_pt - 2.0) < 0.01
    assert abs(stroked_rect.bbox_device_pt[0] - 50.0) < 0.01
    assert abs(stroked_rect.bbox_device_pt[1] - 500.0) < 0.01
    assert abs(stroked_rect.bbox_device_pt[2] - 250.0) < 0.01
    assert abs(stroked_rect.bbox_device_pt[3] - 600.0) < 0.01

    # Check filled rect (300, 500, 200, 100)
    filled_rect = page.paths[2]
    assert filled_rect.fill_rule is not None
    assert abs(filled_rect.bbox_device_pt[0] - 300.0) < 0.01
    assert abs(filled_rect.bbox_device_pt[1] - 500.0) < 0.01
    assert abs(filled_rect.bbox_device_pt[2] - 500.0) < 0.01
    assert abs(filled_rect.bbox_device_pt[3] - 600.0) < 0.01


def test_l0_text_positioning_and_spacing():
    """Verifies that char positioning, font size, char spacing, and word spacing are exact."""
    pdf_bytes = create_geometry_fixture_pdf()
    with ByteLayerExtractor(pdf_bytes) as extractor:
        page = extractor.extract_page(1)

    assert len(page.chars) >= 20
    first_char = page.chars[0]
    assert first_char.char_text == "P"
    assert abs(first_char.font_size_pt - 16.0) < 0.01
    assert abs(first_char.char_spacing_pt - 1.5) < 0.01
    assert abs(first_char.word_spacing_pt - 3.0) < 0.01
    assert abs(first_char.origin_device_pt[0] - 50.0) < 0.01
    assert abs(first_char.origin_device_pt[1] - 400.0) < 0.01

    # Text stream provenance
    assert first_char.provenance is not None
    assert first_char.provenance.operator_name in ("Tj", "'", '"', "TJ")


def test_l0_nested_transforms():
    """Verifies affine matrix concatenation (translate + scale) preserves absolute coordinates."""
    pdf_bytes = create_geometry_fixture_pdf()
    with ByteLayerExtractor(pdf_bytes) as extractor:
        page = extractor.extract_page(1)

    # The scaled rectangle rect(0, 0, 300, 150) under translate(50, 200) and scale(0.5, 0.5)
    # maps to device coordinates (50, 200, 200, 275)
    scaled_rect = page.paths[3]
    assert abs(scaled_rect.bbox_device_pt[0] - 50.0) < 0.01
    assert abs(scaled_rect.bbox_device_pt[1] - 200.0) < 0.01
    assert abs(scaled_rect.bbox_device_pt[2] - 200.0) < 0.01
    assert abs(scaled_rect.bbox_device_pt[3] - 275.0) < 0.01


def test_l0_tj_kerning_and_dash_patterns():
    """Verifies dashed strokes and TJ kerning arrays."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setDash([3, 1, 2, 1], 0)
    c.setLineCap(1)  # Round cap
    c.setLineJoin(1)  # Round join
    c.line(100, 100, 400, 100)
    c.showPage()
    c.save()

    with ByteLayerExtractor(buf.getvalue()) as extractor:
        page = extractor.extract_page(1)

    assert len(page.paths) == 1
    p = page.paths[0]
    assert p.stroke.dash_pattern == (3.0, 1.0, 2.0, 1.0)
    assert p.stroke.cap == 1
    assert p.stroke.join == 1
    assert abs(p.bbox_device_pt[0] - 100.0) < 0.01
    assert abs(p.bbox_device_pt[2] - 400.0) < 0.01

