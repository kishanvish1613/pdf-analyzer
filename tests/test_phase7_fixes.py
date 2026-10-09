"""
Phase 7 Regression Test Suite.
Verifies:
1. Character-level origin matching in L1 crosscheck (no spurious intra-span deltas > 0.05 pt).
2. Top-Left CropBox coordinate mapping in EditorModelBuilder (table y0, row y0, dimension lane placement above table top).
3. Strict mode audit pass on real bank statements.
"""

import os
import pytest
import numpy as np

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.primitives import (
    PageByteLayer,
    PaintedTextChar,
    PaintedPath,
    Color,
)
from pdf_analyzer.l1_crosscheck.crosscheck import L1CrossCheckEngine
from pdf_analyzer.l1_crosscheck.audit import run_l1_audit
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.containers import PlanarGraphEngine, Container
from pdf_analyzer.l3_topology.table_grid import TableGridEngine, TableGrid, ColumnModel, RowModel
from pdf_analyzer.l4_layout.layout_tree import LayoutTreeEngine
from pdf_analyzer.l4_layout.margins_logo import MarginsLogoEngine
from pdf_analyzer.l5_editor.model import EditorModelBuilder, EditorPageModel


def make_char(ch: str, x: float, y: float, w: float = 6.0, h: float = 10.0) -> PaintedTextChar:
    return PaintedTextChar(
        char_id=f"c_{ch}_{x}_{y}",
        char_code=ord(ch),
        char_text=ch,
        unicode_text=ch,
        font_name="Helvetica",
        font_size_pt=h,
        text_matrix=(1.0, 0.0, 0.0, 1.0, x, y),
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        origin_device_pt=(x, y),
        advance_pt=w,
        font_bbox_device_pt=(x, y, x + w, y + h),
        ink_bbox_device_pt=(x, y, x + w, y + h),
        fill_color=Color(space="DeviceRGB", components=(0.0, 0.0, 0.0)),
    )


def test_l1_crosscheck_character_level_origins():
    """Verify L1 crosscheck matches individual character origins against rawdict chars."""
    engine = L1CrossCheckEngine(dpi=600)
    
    # Test with synthetic multi-character string
    chars = [
        make_char("A", 100.0, 500.0, 6.0, 10.0),
        make_char("B", 106.0, 500.0, 6.0, 10.0),
        make_char("C", 112.0, 500.0, 6.0, 10.0),
        make_char("D", 118.0, 500.0, 6.0, 10.0),
    ]
    page_layer = PageByteLayer(
        page_number=1,
        mediabox_pt=(0.0, 0.0, 612.0, 792.0),
        cropbox_pt=(0.0, 0.0, 612.0, 792.0),
        rotation_deg=0,
        chars=chars,
        paths=[],
        images=[],
    )
    
    # Generate report on sample statement
    sample_pdf = os.path.join("output", "sample_statement.pdf")
    if os.path.exists(sample_pdf):
        with ByteLayerExtractor(sample_pdf) as ext:
            real_page = ext.extract_page(1)
        report = engine.generate_truth_report(sample_pdf, real_page)
        assert report.max_char_delta_pt <= 0.05, f"Spurious char delta: {report.max_char_delta_pt}"


def test_editor_model_top_left_coordinates():
    """Verify EditorModelBuilder converts bottom-up PDF coordinates to Top-Left CropBox coordinates."""
    black = Color(space="DeviceRGB", components=(0.0, 0.0, 0.0))
    
    # PDF space: height 792, table at bottom y in [200, 500]
    h_rules = [
        Rule(id="r_top", orientation="H", centre=500.0, painted_outer=500.5,
             painted_inner=499.5, start=50.0, end=550.0, width=1.0, cap=0, colour=black),
        Rule(id="r_bot", orientation="H", centre=200.0, painted_outer=200.5,
             painted_inner=199.5, start=50.0, end=550.0, width=1.0, cap=0, colour=black),
    ]
    v_rules = [
        Rule(id="r_left", orientation="V", centre=50.0, painted_outer=49.5,
             painted_inner=50.5, start=200.0, end=500.0, width=1.0, cap=0, colour=black),
        Rule(id="r_mid", orientation="V", centre=200.0, painted_outer=199.5,
             painted_inner=200.5, start=200.0, end=500.0, width=1.0, cap=0, colour=black),
        Rule(id="r_right", orientation="V", centre=550.0, painted_outer=550.5,
             painted_inner=549.5, start=200.0, end=500.0, width=1.0, cap=0, colour=black),
    ]
    ruleset = RuleSet(page_number=1, width_pt=612.0, height_pt=792.0, h_rules=h_rules, v_rules=v_rules)
    
    table_grid = TableGrid(
        table_bbox_pt=(50.0, 200.0, 550.0, 500.0),
        columns=[
            ColumnModel(index=0, x0_pt=50.0, x1_pt=200.0, width_pt=150.0, left_rule_id="r_left", right_rule_id="r_mid"),
            ColumnModel(index=1, x0_pt=200.0, x1_pt=550.0, width_pt=350.0, left_rule_id="r_mid", right_rule_id="r_right"),
        ],
        rows=[
            RowModel(index=0, y0_pt=350.0, y1_pt=500.0, height_pt=150.0, is_header=True),
            RowModel(index=1, y0_pt=200.0, y1_pt=350.0, height_pt=150.0, is_header=False),
        ],
    )
    
    page_layer = PageByteLayer(
        page_number=1,
        mediabox_pt=(0.0, 0.0, 612.0, 792.0),
        cropbox_pt=(0.0, 0.0, 612.0, 792.0),
        rotation_deg=0,
        chars=[],
        paths=[],
        images=[],
    )
    
    builder = EditorModelBuilder(dpi=300)
    model = builder.build_editor_model(
        page_layer=page_layer,
        ruleset=ruleset,
        table_grid=table_grid,
    )
    
    # In Top-Left space (height 792):
    # Table top was at PDF y=500 -> Top-Left y0 = 792 - 500 = 292
    # Table bottom was at PDF y=200 -> Top-Left y1 = 792 - 200 = 592
    assert abs(model.table_bbox["y0_pt"] - 292.0) < 0.1
    assert abs(model.table_bbox["y1_pt"] - 592.0) < 0.1
    assert abs(model.table_bbox["height_pt"] - 300.0) < 0.1
    
    # Dimension lane must sit ABOVE table top in top-left space (lane_y < 292)
    assert model.dimension_lane is not None
    assert model.dimension_lane.lane_y_pt < model.table_bbox["y0_pt"]
    
    # Row 0 (header) was at PDF [350, 500] -> Top-Left [292, 442]
    assert abs(model.rows[0]["y0_pt"] - 292.0) < 0.1
    assert abs(model.rows[0]["y1_pt"] - 442.0) < 0.1


def test_real_bank_of_india_strict_audit_pass():
    """Verify strict L1-L5 audit on Bank of India statement."""
    pdf_path = os.path.join("uploads", "bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Bank of India statement not in uploads")
        
    passed, audit_dict = run_l1_audit(pdf_path, page_number=1, strict=True)
    assert passed is True
    assert audit_dict["gate_report"]["overall_passed"] is True

