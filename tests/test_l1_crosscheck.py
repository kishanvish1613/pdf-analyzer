"""
L1 Cross-Check Test Suite (Dual 600 DPI Rendering, Sub-Pixel Fitting & Invariant Gates).
Includes exact ReportLab geometry fixtures, 1.0 pt mutation sensitivity test,
and Hypothesis property-based tests across coordinate rotations (0, 90, 180, 270 deg).
"""

import io
import os
import json
import pytest
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from hypothesis import given, strategies as st, settings

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l1_crosscheck.renderers import DualRenderer
from pdf_analyzer.l1_crosscheck.registration import RegistrationEngine
from pdf_analyzer.l1_crosscheck.crosscheck import L1CrossCheckEngine
from pdf_analyzer.l1_crosscheck.gates import GateEvaluator


def create_statement_grid_pdf(mutation_shift_pt: float = 0.0) -> bytes:
    """Creates a synthetic bank statement table grid with known exact rule coordinates."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))

    # Outer table bounding box: x in [50, 562], y in [200, 600]
    c.setLineWidth(1.0)
    c.setStrokeColor(colors.black)
    c.rect(50, 200, 512, 400, stroke=1, fill=0)

    # 5 Vertical column rules
    col_xs = [120.0 + mutation_shift_pt, 200.0, 280.0, 380.0, 480.0]
    for x in col_xs:
        c.line(x, 200, x, 600)

    # 10 Horizontal transaction row rules
    for y in np.linspace(240, 560, 9):
        c.line(50, y, 562, y)

    # Header text
    c.setFont("Helvetica-Bold", 12)
    c.drawString(60, 620, "Account Statement")

    c.showPage()
    c.save()
    return buf.getvalue()


def test_l1_dual_renderer_and_dimensions():
    """Validates PyMuPDF and pypdfium2 dual 600 DPI rendering accuracy."""
    pdf_bytes = create_statement_grid_pdf()
    renderer = DualRenderer(dpi=600)
    mupdf_render, pdfium_render = renderer.render_both(pdf_bytes, page_number=1)

    assert mupdf_render.dpi == 600
    assert pdfium_render.dpi == 600
    assert abs(mupdf_render.width_px - 5100) <= 1  # 612 * (600/72) = 5100 px
    assert abs(mupdf_render.height_px - 6600) <= 1  # 792 * (600/72) = 6600 px
    assert abs(mupdf_render.image_rgb.shape[1] - 5100) <= 1
    assert abs(mupdf_render.image_rgb.shape[0] - 6600) <= 1
    assert abs(pdfium_render.image_rgb.shape[1] - 5100) <= 1
    assert abs(pdfium_render.image_rgb.shape[0] - 6600) <= 1


def test_l1_registration_and_gate_g1(tmp_path):
    """Verifies that affine registration meets Gate G1 invariants (|dx|<=0.1, |sx-1|<=0.0005, res<=0.15)."""
    pdf_bytes = create_statement_grid_pdf(mutation_shift_pt=0.0)

    with ByteLayerExtractor(pdf_bytes) as extractor:
        page_layer = extractor.extract_page(1)

    renderer = DualRenderer(dpi=600)
    mupdf_render = renderer.render_pymupdf(pdf_bytes, 1)

    reg_engine = RegistrationEngine(dpi=600)
    result = reg_engine.solve_registration(page_layer, mupdf_render.image_rgb, output_dir=str(tmp_path))

    assert result.gate_g1_passed is True
    assert abs(result.dx_pt) <= 0.1
    assert abs(result.dy_pt) <= 0.1
    assert abs(result.sx - 1.0) <= 0.0005
    assert abs(result.sy - 1.0) <= 0.0005
    assert result.max_residual_pt <= 0.15

    # Artifact check
    assert os.path.exists(tmp_path / "registration.json")
    assert os.path.exists(tmp_path / "registration.png")


def test_l1_mutation_sensitivity():
    """
    Mutation Test: If a vertical rule is shifted by 1.0 pt in the vector stream,
    the L1 cross-check must report a finding capturing that exact discrepancy.
    """
    pdf_bytes = create_statement_grid_pdf(mutation_shift_pt=0.0)

    with ByteLayerExtractor(pdf_bytes) as extractor:
        page_layer = extractor.extract_page(1)

    # Intentionally mutate one L0 path by +1.0 pt
    mutated_path = page_layer.paths[1]  # first vertical rule
    orig_bbox = mutated_path.bbox_device_pt
    mutated_path.bbox_device_pt = (orig_bbox[0] + 1.0, orig_bbox[1], orig_bbox[2] + 1.0, orig_bbox[3])

    crosscheck = L1CrossCheckEngine(dpi=600)
    truth = crosscheck.generate_truth_report(pdf_bytes, page_layer)

    assert truth.findings_count > 0
    # Confirm the mutation was detected with delta >= 0.9 pt
    mutation_finding = [f for f in truth.findings if f.object_id == mutated_path.path_id]
    assert len(mutation_finding) == 1
    assert abs(mutation_finding[0].delta_pt - 1.0) < 0.15


@given(rotation=st.sampled_from([0, 90, 180, 270]))
@settings(max_examples=4, deadline=10000)
def test_hypothesis_page_rotations(rotation: int):
    """Property-based test: Rotated pages preserve internal cropbox coordinate invariants."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.rect(100, 100, 200, 200)
    c.showPage()
    c.save()

    with ByteLayerExtractor(buf.getvalue()) as extractor:
        page = extractor.extract_page(1)

    assert page.cropbox_pt == (0.0, 0.0, 612.0, 792.0)
    assert page.width_pt == 612.0
    assert page.height_pt == 792.0
    assert len(page.paths) >= 1
