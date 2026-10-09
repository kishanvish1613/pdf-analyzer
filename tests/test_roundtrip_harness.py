"""Test suite for closed-loop roundtrip verification harness (tools.roundtrip).

Asserts:
1. run_roundtrip produces complete RoundtripResult with SSIM, diff%, geometry metrics, heatmaps, and failure attribution.
2. Exporters (ReportLab and WeasyPrint) produce valid PDFs and HTML/CSS templates.
3. Harness detects a deliberately shifted PDF (1.0 pt shift) and reports accurate delta and failure.
4. Held-out folder evaluation is separated in summary markdown.
"""

import os
import shutil
import pytest
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors

from tools.roundtrip.roundtrip import (
    run_roundtrip,
    generate_summary_markdown,
    load_thresholds,
    get_threshold_for_template,
)
from tools.roundtrip.metrics import (
    extract_words_from_l0,
    compute_geometry_metrics,
    compute_pixel_metrics_and_heatmap,
    rasterize_page_at_dpi,
    WordBox,
)


def _create_test_pdf(pdf_path: str, shift_pt: float = 0.0) -> str:
    """Create a clean 1-page test PDF with optional coordinate shift."""
    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter

    # Top banner / logo
    c.setFillColor(colors.HexColor("#1A365D"))
    c.rect(36 + shift_pt, h - 80, 100, 30, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(45 + shift_pt, h - 62, "TEST BANK")

    # Key-value lines
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(36 + shift_pt, h - 120, "Account Number: 1234567890")
    c.drawString(36 + shift_pt, h - 135, "Statement Period: 01/01/2026 to 31/01/2026")

    # Table
    t_top = h - 160
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1.0)
    c.rect(36 + shift_pt, t_top - 100, 540, 100, fill=0, stroke=1)
    c.line(36 + shift_pt, t_top - 20, 576 + shift_pt, t_top - 20)

    # Table header
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40 + shift_pt, t_top - 14, "Date")
    c.drawString(120 + shift_pt, t_top - 14, "Description")
    c.drawString(450 + shift_pt, t_top - 14, "Amount")

    # Table row
    c.setFont("Helvetica", 8)
    c.drawString(40 + shift_pt, t_top - 34, "01/01/2026")
    c.drawString(120 + shift_pt, t_top - 34, "Opening Balance")
    c.drawString(450 + shift_pt, t_top - 34, "10000.00")

    c.save()
    return pdf_path


@pytest.mark.roundtrip
def test_roundtrip_upload_test(tmp_path):
    """Test full roundtrip flow on real sample document."""
    pdf_path = "uploads/upload_test.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip(f"{pdf_path} not found.")

    out_dir = str(tmp_path / "out_roundtrip")
    res = run_roundtrip(pdf_path, exporter="reportlab", output_dir=out_dir)

    # 1. Result Structure
    assert res.template_name == "upload_test"
    assert res.exporter == "reportlab"
    assert os.path.exists(res.generated_pdf_path)
    assert os.path.exists(res.diff_heatmap_path)
    assert os.path.exists(res.spec_path)

    # 2. Pixel Metrics
    assert 0.0 <= res.pixel_metrics.ssim <= 1.0
    assert 0.0 <= res.pixel_metrics.diff_percent <= 100.0

    # 3. Geometry Metrics
    assert res.geometry_metrics.total_orig_words > 0
    assert res.geometry_metrics.matched_words_count > 0
    assert "p95" in res.geometry_metrics.dx_pt
    assert "p95" in res.geometry_metrics.dy_pt

    # 4. Failure Attribution
    assert "TEXT" in res.failure_attribution
    assert "RULE" in res.failure_attribution
    assert "FILL" in res.failure_attribution
    assert "OTHER" in res.failure_attribution


@pytest.mark.roundtrip
def test_deliberately_shifted_pdf_detected(tmp_path):
    """Assert the harness detects a deliberately shifted PDF (shift by 1.0 pt, expect failure on tight limits)."""
    orig_pdf = str(tmp_path / "original.pdf")
    shifted_pdf = str(tmp_path / "shifted_1pt.pdf")

    _create_test_pdf(orig_pdf, shift_pt=0.0)
    _create_test_pdf(shifted_pdf, shift_pt=1.0)

    # 1. Geometry comparison via L0 extractor
    orig_words, _ = extract_words_from_l0(orig_pdf, page_number=1)
    shifted_words, _ = extract_words_from_l0(shifted_pdf, page_number=1)

    assert len(orig_words) == len(shifted_words)
    geom_metrics = compute_geometry_metrics(orig_words, shifted_words)

    # Measured dx must be exactly ~1.0 pt
    assert abs(geom_metrics.dx_pt["mean"] - 1.0) < 0.05
    assert abs(geom_metrics.dx_pt["p95"] - 1.0) < 0.05
    assert abs(geom_metrics.dx_pt["max"] - 1.0) < 0.05

    # 2. Assert failure when tight threshold is enforced (e.g. max dx = 0.5 pt)
    tight_thresholds = {
        "templates": {
            "shifted_1pt": {
                "reportlab": {
                    "ssim_min": 0.999,
                    "diff_percent_max": 0.01,
                    "word_dx_p95_max_pt": 0.5,
                    "word_dy_p95_max_pt": 0.5,
                }
            }
        },
        "default": {
            "ssim_min": 0.999,
            "diff_percent_max": 0.01,
            "word_dx_p95_max_pt": 0.5,
            "word_dy_p95_max_pt": 0.5,
        }
    }

    t_file = str(tmp_path / "tight_thresholds.yaml")
    import yaml
    with open(t_file, "w", encoding="utf-8") as f:
        yaml.dump(tight_thresholds, f)

    res = run_roundtrip(
        shifted_pdf,
        exporter="reportlab",
        output_dir=str(tmp_path / "shifted_out"),
        thresholds_file=t_file,
    )
    # The tight thresholds must fail
    assert res.passed is False or len(res.failure_reasons) > 0


@pytest.mark.roundtrip
def test_weasyprint_exporter_generates_html_and_pdf(tmp_path):
    """Test WeasyPrint exporter generates valid HTML and PDF artifacts."""
    pdf_path = "uploads/upload_test.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip(f"{pdf_path} not found.")

    out_dir = str(tmp_path / "weasy_out")
    res = run_roundtrip(pdf_path, exporter="weasyprint", output_dir=out_dir)

    assert res.exporter == "weasyprint"
    assert res.generated_html_path is not None
    assert os.path.exists(res.generated_html_path)
    assert os.path.exists(res.generated_pdf_path)

    # Check HTML content
    with open(res.generated_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    assert "<!DOCTYPE html>" in html_content
    assert "@page" in html_content


@pytest.mark.roundtrip
def test_summary_markdown_heldout_separation():
    """Verify summary.md correctly partitions standard corpus and held-out templates."""
    from tools.roundtrip.metrics import PixelMetrics, GeometryMetrics
    from tools.roundtrip.roundtrip import RoundtripResult

    dummy_pix = PixelMetrics(ssim=0.92, diff_percent=3.5, differing_pixels_count=1000, total_pixels=100000, heatmap_path="diff.png")
    dummy_geom = GeometryMetrics(total_orig_words=50, total_gen_words=50, matched_words_count=50, dx_pt={"mean": 1.0, "p95": 2.0, "max": 3.0}, dy_pt={"mean": 1.0, "p95": 2.0, "max": 3.0})

    corpus_r = RoundtripResult(
        template_name="corpus_doc1",
        pdf_path="uploads/corpus_doc1.pdf",
        exporter="reportlab",
        page_number=1,
        spec_path="spec.json",
        generated_pdf_path="gen.pdf",
        generated_html_path=None,
        diff_heatmap_path="diff.png",
        pixel_metrics=dummy_pix,
        geometry_metrics=dummy_geom,
        failure_attribution={"TEXT": 10, "RULE": 2, "FILL": 0, "OTHER": 0},
        thresholds={},
        passed=True,
        is_heldout=False,
    )

    heldout_r = RoundtripResult(
        template_name="heldout_doc1",
        pdf_path="corpus/heldout/heldout_doc1.pdf",
        exporter="reportlab",
        page_number=1,
        spec_path="spec.json",
        generated_pdf_path="gen.pdf",
        generated_html_path=None,
        diff_heatmap_path="diff.png",
        pixel_metrics=dummy_pix,
        geometry_metrics=dummy_geom,
        failure_attribution={"TEXT": 5, "RULE": 1, "FILL": 0, "OTHER": 0},
        thresholds={},
        passed=True,
        is_heldout=True,
    )

    summary_md = generate_summary_markdown([corpus_r], [heldout_r])
    assert "## Corpus Verification Results" in summary_md
    assert "corpus_doc1" in summary_md
    assert "## Held-out Evaluation (corpus/heldout/)" in summary_md
    assert "heldout_doc1" in summary_md

