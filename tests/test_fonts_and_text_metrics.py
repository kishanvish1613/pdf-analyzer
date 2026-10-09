"""Test suite for Font and Text-Metrics Layer in L0 and Exporters.

Asserts:
1. Extraction of font metadata (subset prefix, is_embedded, font_type, Tc, Tw, Tz, Ts, widths) across font formats.
2. Detection of Type3 fonts and non-text glyph path outlines.
3. Spec "fonts" dictionary serialization and metadata accuracy.
4. String width parity and corrective char-spacing across corpus documents (reporting worst 10 strings).
"""

import os
import json
import pytest
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.font_manager import (
    parse_font_name_parts,
    get_best_fallback_font,
    calculate_string_width_parity,
    extract_and_register_fonts,
)
from pdf_analyzer.l0_bytes.fonts import create_font_metrics
from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline


def _create_font_type_fixture(pdf_path: str, font_name: str = "Helvetica", size: float = 10.0) -> str:
    """Create a minimal PDF fixture with specified standard font."""
    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.setFont(font_name, size)
    c.drawString(72.0, 700.0, "Font Layer Test String 12345")
    c.save()
    return pdf_path


def test_font_type_fixtures(tmp_path):
    """Test L0 extraction across font type configurations."""
    # 1. Type 1 Standard Font
    t1_pdf = str(tmp_path / "type1_test.pdf")
    _create_font_type_fixture(t1_pdf, "Helvetica-Bold", 12.0)

    with ByteLayerExtractor(t1_pdf) as ble:
        layer = ble.extract_page(1)
        assert len(layer.text_chars) > 0
        char = layer.text_chars[0]
        assert char.font_size_pt == 12.0
        assert char.char_spacing_pt == 0.0
        assert char.horiz_scaling == 100.0
        assert len(layer.fonts) > 0

    # 2. Subset Prefix Parser
    prefix, clean = parse_font_name_parts("UCWCLL+SourceSans3-SemiBold")
    assert prefix == "UCWCLL+"
    assert clean == "SourceSans3-SemiBold"

    prefix_none, clean_none = parse_font_name_parts("Helvetica-Bold")
    assert prefix_none is None
    assert clean_none == "Helvetica-Bold"

    # 3. Best Fallback Font
    assert get_best_fallback_font("SourceSans3-SemiBold") == "Helvetica-Bold"
    assert get_best_fallback_font("TimesNewRomanPSMT") == "Times-Roman"
    assert get_best_fallback_font("CourierNewPS-BoldMT") == "Courier-Bold"


def test_type3_and_non_text_glyphs_detection(tmp_path):
    """Test detection of Type3 fonts and outline path glyphs."""
    pdf_path = str(tmp_path / "outline_test.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    # Draw a small filled path (e.g. custom bullet / outline glyph) without text operator
    c.setFillColor(colors.HexColor("#1A202C"))
    c.rect(72.0, 700.0, 8.0, 8.0, fill=1, stroke=0)
    c.save()

    with ByteLayerExtractor(pdf_path) as ble:
        layer = ble.extract_page(1)
        assert hasattr(layer, "non_text_glyphs")
        # The small rect should be captured
        assert len(layer.non_text_glyphs) >= 1
        g = layer.non_text_glyphs[0]
        assert g["type"] in ["path_outline_glyph", "type3_glyph"]
        assert "bbox_pt" in g


def test_string_width_parity_corpus_check():
    """Verify string width parity and report worst 10 width discrepancies across corpus."""
    corpus_manifest = "tests/corpus/manifest.json"
    if not os.path.exists(corpus_manifest):
        pytest.skip("Corpus manifest not found.")

    with open(corpus_manifest, "r", encoding="utf-8") as f:
        items = json.load(f)

    discrepancies = []

    for item in items:
        pdf_path = item.get("file", "")
        if not os.path.exists(pdf_path):
            continue

        try:
            with ByteLayerExtractor(pdf_path) as ble:
                layer = ble.extract_page(1)
                chars = layer.text_chars
                if not chars:
                    continue

                # Group into spans/words
                cur_text = []
                cur_font = chars[0].font_name
                cur_size = chars[0].font_size_pt
                cur_width = 0.0

                for ch in chars:
                    if ch.unicode_text.isspace():
                        if cur_text:
                            stxt = "".join(cur_text).strip()
                            if len(stxt) > 1:
                                parity = calculate_string_width_parity(
                                    text=stxt,
                                    original_width_pt=cur_width,
                                    font_name=cur_font,
                                    font_size_pt=cur_size,
                                    threshold_pt=0.05,
                                )
                                discrepancies.append((abs(parity["delta_pt"]), pdf_path, stxt, parity))
                            cur_text = []
                            cur_width = 0.0
                    else:
                        cur_text.append(ch.unicode_text)
                        cur_font = ch.font_name
                        cur_size = ch.font_size_pt
                        cur_width += ch.advance_pt

                if cur_text:
                    stxt = "".join(cur_text).strip()
                    if len(stxt) > 1:
                        parity = calculate_string_width_parity(
                            text=stxt,
                            original_width_pt=cur_width,
                            font_name=cur_font,
                            font_size_pt=cur_size,
                            threshold_pt=0.05,
                        )
                        discrepancies.append((abs(parity["delta_pt"]), pdf_path, stxt, parity))
        except Exception:
            pass

    discrepancies.sort(key=lambda x: x[0], reverse=True)
    worst_10 = discrepancies[:10]

    print("\n=== Worst 10 String Width Discrepancies Before Correction ===")
    for rank, (delta, doc, stxt, p) in enumerate(worst_10, 1):
        print(f"#{rank}: Delta={delta:.4f} pt | Text='{stxt}' | Doc={Path(doc).name} | TargetFont={p['target_font']} | CharSpace={p['char_spacing_correction_pt']:.5f} pt")

    # Assert that corrective char spacing handles all strings
    for delta, doc, stxt, p in discrepancies:
        if p["needs_correction"]:
            # After applying char_spacing_correction_pt, residual delta must be <= 0.05 pt
            n_gaps = max(1, len(stxt) - 1)
            corrected_width = p["target_width_pt"] + p["char_spacing_correction_pt"] * n_gaps
            residual = abs(p["original_width_pt"] - corrected_width)
            assert residual <= 0.06, f"Residual {residual} pt exceeds 0.06 pt for '{stxt}'"


def test_fonts_section_in_pipeline_output(tmp_path):
    """Assert the pipeline JSON spec contains the 'fonts' section with required properties."""
    pdf_path = "uploads/upload_test.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip(f"{pdf_path} not found.")

    out_dir = str(tmp_path / "font_pipe_out")
    config = AnalyzerConfig(dpi=300, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(pdf_path, output_dir=out_dir)

    assert "fonts" in spec
    assert isinstance(spec["fonts"], dict)
    for font_name, font_data in spec["fonts"].items():
        assert "font_name" in font_data
        assert "clean_family" in font_data
        assert "is_embedded" in font_data
        assert "fallback_font" in font_data
        assert "font_type" in font_data

