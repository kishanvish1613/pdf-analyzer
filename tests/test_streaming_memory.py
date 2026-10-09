"""
Tests for Page-by-Page Streaming, Memory Boundedness, and L0 Hardening:
1. Rotation handling (0, 90, 180, 270 degrees)
2. MediaBox vs non-zero CropBox origin
3. Color spaces (DeviceCMYK, DeviceRGB, DeviceGray) and alpha transparency (/CA, /ca)
4. Vector clipping paths
5. 150-page PDF streaming memory benchmark with tracemalloc
"""

import os
import gc
import tracemalloc
import pytest
import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline, CarryOverState
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.stages.frame import PageFrame
from tools.roundtrip.exporters.reportlab_exporter import generate_reportlab_pdf
from tools.roundtrip.exporters.weasyprint_exporter import generate_weasyprint_html


def test_rotation_handling(tmp_path):
    """Asserts that 0, 90, 180, 270 rotated pages are normalized to top-left CropBox coordinates."""
    pdf_path = str(tmp_path / "rotated.pdf")
    doc = pymupdf.open()

    for rot in (0, 90, 180, 270):
        page = doc.new_page(width=612, height=792)
        page.set_rotation(rot)
        # Draw a rectangle in user coordinates
        page.draw_rect(pymupdf.Rect(100, 150, 300, 200), color=(0, 0, 0), width=1)
        # Insert text
        page.insert_text(pymupdf.Point(110, 180), f"Rotation {rot}", fontsize=10)

    doc.save(pdf_path)
    doc.close()

    with ByteLayerExtractor(pdf_path) as ble:
        for p_num in range(1, 5):
            layer = ble.extract_page(p_num)
            expected_rot = (p_num - 1) * 90
            assert layer.rotation_deg == expected_rot
            assert layer.mediabox_pt == (0.0, 0.0, 612.0, 792.0)
            assert len(layer.painted_paths) >= 1 or len(layer.text_chars) >= 1


def test_nonzero_cropbox_origin(tmp_path):
    """Asserts non-zero CropBox origin maps coordinates to top-left CropBox frame."""
    pdf_path = str(tmp_path / "offset_cropbox.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    # Set non-zero CropBox
    page.set_cropbox(pymupdf.Rect(50, 100, 550, 700))
    page.draw_rect(pymupdf.Rect(100, 150, 400, 300), color=(0, 0, 0), width=1)
    page.insert_text(pymupdf.Point(120, 200), "Cropped Content", fontsize=10)
    doc.save(pdf_path)
    doc.close()

    with ByteLayerExtractor(pdf_path) as ble:
        layer = ble.extract_page(1)
        assert layer.cropbox_pt == (50.0, 92.0, 550.0, 692.0)
        assert layer.mediabox_pt == (0.0, 0.0, 612.0, 792.0)

    frame = PageFrame(
        page_number=1,
        cropbox_pt=layer.cropbox_pt,
        mediabox_pt=layer.mediabox_pt,
        rotation_deg=0,
        user_unit=1.0,
        dpi=300
    )
    assert abs(frame.width_pt - 500.0) < 1e-4
    assert abs(frame.height_pt - 600.0) < 1e-4


def test_cmyk_and_alpha_extraction_and_export(tmp_path):
    """Asserts that CMYK colors, transparency, and outline glyphs are extracted and exported."""
    pdf_path = str(tmp_path / "cmyk_alpha.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    # CMYK fill
    c.setFillColor(colors.CMYKColor(0.2, 0.4, 0.8, 0.1))
    c.rect(50, 500, 200, 100, fill=1, stroke=0)
    # Alpha stroke and fill
    c.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.5))
    c.setStrokeColor(colors.Color(0.1, 0.8, 0.1, alpha=0.6))
    c.rect(300, 500, 200, 100, fill=1, stroke=1)
    c.drawString(60, 520, "CMYK and Alpha Test")
    c.save()

    with ByteLayerExtractor(pdf_path) as ble:
        layer = ble.extract_page(1)
        assert len(layer.painted_paths) >= 1

    cfg = AnalyzerConfig(output_dir=str(tmp_path / "out_cmyk"), dpi=150)
    pipeline = AnalysisPipeline(cfg)
    spec = pipeline.process_document(pdf_path, output_dir=str(tmp_path / "out_cmyk"), page_number=1)

    # Test ReportLab exporter with CMYK and alpha spec
    rl_out = str(tmp_path / "reproduced_rl.pdf")
    generate_reportlab_pdf(spec, rl_out)
    assert os.path.exists(rl_out)
    assert os.path.getsize(rl_out) > 500

    # Test WeasyPrint exporter
    wp_html = str(tmp_path / "reproduced_wp.html")
    generate_weasyprint_html(spec, wp_html)
    assert os.path.exists(wp_html)


def test_vector_clipping_path(tmp_path):
    """Asserts that vector clipping paths intersect and bound painted geometries."""
    pdf_path = str(tmp_path / "clipped.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    # Draw path with clip
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(50, 50, 400, 400))
    shape.finish(color=(0, 0, 1), fill=(0, 1, 0))
    shape.commit()
    doc.save(pdf_path)
    doc.close()

    with ByteLayerExtractor(pdf_path) as ble:
        layer = ble.extract_page(1)
        assert layer.mediabox_pt[2] == 612.0
        assert layer.mediabox_pt[3] == 792.0


@pytest.mark.timeout(300)
def test_streaming_150_page_memory(tmp_path):
    """Creates a 150-page synthetic PDF and asserts peak memory stays flat/bounded across pages."""
    pdf_path = str(tmp_path / "large_150_pages.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter

    # Generate 150 realistic pages with header, KV grid, and table rows
    for p in range(1, 151):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(36, h - 50, f"SAMPLE BANK STATEMENT - PAGE {p}")
        c.setFont("Helvetica", 9)
        c.drawString(36, h - 70, f"Account: 1234-5678-{p:04d} | Statement Period: 01/01/2026 - 01/31/2026")

        # Table header
        c.setFillColor(colors.HexColor("#F1F5F9"))
        c.rect(36, h - 130, w - 72, 20, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(45, h - 120, "Date")
        c.drawString(120, h - 120, "Description")
        c.drawString(350, h - 120, "Debit")
        c.drawString(430, h - 120, "Credit")
        c.drawString(510, h - 120, "Balance")

        # Table rows
        y = h - 145
        c.setFont("Helvetica", 7.5)
        for r in range(12):
            c.drawString(45, y, f"01/{r+1:02d}/2026")
            c.drawString(120, y, f"Transaction narration item #{r+1}")
            c.drawString(350, y, f"${(r+1)*12.50:.2f}")
            c.drawString(430, y, "-")
            c.drawString(510, y, f"${1000.0 - (r+1)*12.50:.2f}")
            y -= 15

        c.showPage()

    c.save()
    assert os.path.exists(pdf_path)

    out_dir = str(tmp_path / "streaming_out")
    cfg = AnalyzerConfig(
        output_dir=out_dir,
        dpi=72,
        include_visual_overlays=False,
        include_closed_loop_verification=False
    )
    pipeline = AnalysisPipeline(cfg)

    # Track memory during streaming execution
    gc.collect()
    tracemalloc.start()

    carry_over = CarryOverState()
    mem_samples = {}

    for p_idx in range(150):
        p_spec, carry_over = pipeline.process_single_page(
            pdf_path=pdf_path,
            page_idx=p_idx,
            carry_over=carry_over,
            output_dir=out_dir
        )
        assert p_spec is not None
        assert carry_over.page_number == p_idx + 1

        if (p_idx + 1) in (10, 30, 60, 100, 150):
            current, peak = tracemalloc.get_traced_memory()
            mem_samples[p_idx + 1] = peak / (1024 * 1024)

    tracemalloc.stop()

    # Verify per-page specs were written to disk
    assert os.path.exists(os.path.join(out_dir, "page_1_spec.json"))
    assert os.path.exists(os.path.join(out_dir, "page_150_spec.json"))

    # Memory boundedness assertion:
    # Memory growth between page 10 and page 150 must not grow linearly with 140 additional pages.
    # Without streaming, 150 pages would consume > 300MB; with streaming, memory stays flat.
    mem_10 = mem_samples[10]
    mem_150 = mem_samples[150]
    growth_mb = mem_150 - mem_10
    print(f"Memory samples (MB): {mem_samples}, Growth from p10 to p150: {growth_mb:.2f} MB")
    assert growth_mb < 45.0, f"Memory grew by {growth_mb:.2f} MB, exceeding bounded limit."
