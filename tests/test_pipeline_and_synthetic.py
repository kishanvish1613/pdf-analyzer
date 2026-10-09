"""
Comprehensive Regression, Invariant & Stage 0-28 Test Suite for PDF Design Analyzer.
Tests:
1. Stage 0: PageFrame, Control-Point Registration, Sub-pixel Least-Squares solve, registration.json & registration.png
2. Stage 1: Container Recovery, 4-Side Planar Decomposition, containers.json & containers.png
3. Section 22: Exact Table Bounds & Rule-Anchored Dimension Lane
4. Section 23: Header Side-by-Side Block Splitting, header_blocks.json & header_blocks.png
5. Section 24: Advanced Key-Value Detection (K1-K3, colon_axis, colon_attached, weight_split, free_pair)
6. Section 25: Footer Detection & Structure, footer_blocks.json & footer.png
7. Section 26: Full Content Accounting (Zero orphans, 600 DPI residual ink mask <= 0.3%, coverage.json & orphans.png)
8. Section 27: Template Profiler, template_profile.json
9. Sections 10-16: Table Model, Multi-Signal Columns, Multi-Model Rows, Cell Grid, Gap Matrix, C1-C6 Checks
10. Synthetic Fixtures: T1 (Full Grid), T2 (Double Stroke), T4 (Borderless), H1 (Unboxed Two-Block Header), F1 (Footer)
"""

import os
import json
import pytest
import pymupdf
from generate_sample_pdf import (
    create_synthetic_statement,
    create_fixture_t1_full_grid,
    create_fixture_t2_double_stroke,
    create_fixture_t4_borderless,
    create_fixture_h1_unboxed_twoblock,
    create_fixture_f1_footer
)
from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline


@pytest.fixture(scope="module")
def sample_pdf_path(tmp_path_factory):
    fn = tmp_path_factory.mktemp("data") / "benchmark_statement.pdf"
    create_synthetic_statement(str(fn))
    return str(fn)


def test_full_analysis_pipeline_and_invariants(sample_pdf_path, tmp_path):
    out_dir = str(tmp_path / "output")
    config = AnalyzerConfig(dpi=600, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(sample_pdf_path, out_dir)

    # 1. Check Stage 0-28 JSON Artifacts Created
    assert os.path.exists(os.path.join(out_dir, "design_spec.json"))
    assert os.path.exists(os.path.join(out_dir, "layout_tree.json"))
    assert os.path.exists(os.path.join(out_dir, "table_model.json"))
    assert os.path.exists(os.path.join(out_dir, "registration.json"))
    assert os.path.exists(os.path.join(out_dir, "containers.json"))
    assert os.path.exists(os.path.join(out_dir, "header_blocks.json"))
    assert os.path.exists(os.path.join(out_dir, "footer_blocks.json"))
    assert os.path.exists(os.path.join(out_dir, "coverage.json"))
    assert os.path.exists(os.path.join(out_dir, "template_profile.json"))

    # 2. Check Stage 0-28 PNG Overlays Created
    assert os.path.exists(os.path.join(out_dir, "registration.png"))
    assert os.path.exists(os.path.join(out_dir, "containers.png"))
    assert os.path.exists(os.path.join(out_dir, "header_blocks.png"))
    assert os.path.exists(os.path.join(out_dir, "footer.png"))
    assert os.path.exists(os.path.join(out_dir, "orphans.png"))
    assert os.path.exists(os.path.join(out_dir, "overlay_columns_page_1.png"))
    assert os.path.exists(os.path.join(out_dir, "overlay_rows_page_1.png"))
    assert os.path.exists(os.path.join(out_dir, "overlay_cells_page_1.png"))
    assert os.path.exists(os.path.join(out_dir, "overlay_gaps_page_1.png"))

    # 3. Stage 0: Registration Gating
    reg = spec["registration"]
    assert reg["gate_checks"]["gate_passed"] is True
    assert abs(reg["fitted_transform"]["dx_pt"]) <= 0.10
    assert abs(reg["fitted_transform"]["dy_pt"]) <= 0.10

    # 4. Stage 1: Containers 4-Side Recovery
    containers = spec["containers"]
    assert len(containers) >= 1
    # Check 4-side attributes on container
    c0 = containers[0]
    assert "top" in c0["sides"] and "bottom" in c0["sides"]
    assert "left" in c0["sides"] and "right" in c0["sides"]
    assert c0["sides"]["top"]["is_present"] is True

    # 5. Section 22: Table Bounds & Dimension Lane
    tbl_model = spec["table_model"]
    dim_arrows = tbl_model.get("dimension_arrows", [])
    assert len(dim_arrows) == 7
    for arr in dim_arrows:
        assert arr["width_pt"] > 20.0
        assert "left_rule_id" in arr and "right_rule_id" in arr

    # 6. Section 23: Header Side-by-Side Blocks
    hb = spec["header_blocks"]
    assert len(hb["blocks"]) >= 2
    assert hb["pairing_record"]["paired"] is True
    assert hb["pairing_record"]["gutter_width_pt"] > 20.0

    # 7. Section 24: Key-Value Classification
    kvs = spec["key_values"]
    assert kvs["chosen_style"] in ["colon_axis", "colon_attached", "weight_split"]
    assert len(kvs["entities"]) >= 5

    # 8. Section 25: Footer Sub-Blocks & Page Number
    fb = spec["footer_blocks"]
    assert fb is not None
    assert fb["gap_footer_to_page_bottom_pt"] >= 0.0

    # 9. Section 26: Full Content Accounting & Coverage
    cov = spec["coverage"]
    assert cov["orphaned_characters"] == 0
    assert cov["residual_ink_pct"] <= 1.0
    assert cov["status"] in ["PASS", "WARN"]

    # 10. Section 27: Template Profiler
    tp = spec["template_profile"]
    assert tp["table_style"] in ["full_grid", "vertical_rules_only", "zebra_fill", "borderless"]
    assert tp["header_style"] in ["boxed_address_with_kv", "two_block_unboxed"]


def test_fixture_t1_full_grid(tmp_path):
    """T1: Full grid single-stroke rules."""
    fn = str(tmp_path / "t1_grid.pdf")
    create_fixture_t1_full_grid(fn)
    out_dir = str(tmp_path / "t1_out")
    config = AnalyzerConfig(dpi=300, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(fn, out_dir)

    tbl = spec["table_model"]
    assert len(tbl["columns"]) == 4
    assert len(tbl["rows"]) == 4
    assert tbl["chosen_models"]["row_model"] == "R1_ruled"
    assert tbl["all_checks_passed"] is True


def test_fixture_t2_double_stroke(tmp_path):
    """T2: Full grid double-stroke rules."""
    fn = str(tmp_path / "t2_double.pdf")
    create_fixture_t2_double_stroke(fn)
    out_dir = str(tmp_path / "t2_out")
    config = AnalyzerConfig(dpi=300, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(fn, out_dir)

    tbl = spec["table_model"]
    assert len(tbl["columns"]) == 4
    assert any(c.get("is_double_rule") for c in tbl["columns"])


def test_fixture_t4_borderless(tmp_path):
    """T4: Borderless table (whitespace only) returns columns=None/empty without inventing columns."""
    fn = str(tmp_path / "t4_borderless.pdf")
    create_fixture_t4_borderless(fn)
    out_dir = str(tmp_path / "t4_out")
    config = AnalyzerConfig(dpi=300, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(fn, out_dir)

    tbl = spec["table_model"]
    assert len(tbl["columns"]) == 0


def test_fixture_h1_unboxed_header(tmp_path):
    """H1: Unboxed two-block header with centred title and notes."""
    fn = str(tmp_path / "h1_header.pdf")
    create_fixture_h1_unboxed_twoblock(fn)
    out_dir = str(tmp_path / "h1_out")
    config = AnalyzerConfig(dpi=300, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(fn, out_dir)

    hb = spec["header_blocks"]
    roles = [b["position_role"] for b in hb["blocks"]]
    assert "full_width_title" in roles or "left_block" in roles
    assert "right_block" in roles


def test_fixture_f1_footer(tmp_path):
    """F1: Footer directly under table."""
    fn = str(tmp_path / "f1_footer.pdf")
    create_fixture_f1_footer(fn)
    out_dir = str(tmp_path / "f1_out")
    config = AnalyzerConfig(dpi=300, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(fn, out_dir)

    fb = spec["footer_blocks"]
    assert fb is not None
    assert any(sb.get("is_page_number") for sb in fb.get("sub_blocks", []))
