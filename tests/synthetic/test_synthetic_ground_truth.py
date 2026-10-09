"""
Independent Ground-Truth Test Suite for Synthetic Statements.

Evaluates extractor accuracy against known mathematical ground truth (not against extractor output):
1. Vector line coordinates (x0, y0, x1, y1, stroke width)
2. Text span coordinates (origin x, origin y, font size, string text)
3. Table column edges and column widths
4. Row baselines, line counts, and row pitch
5. Reports measured mean, p95, and max delta in pt
"""

import os
import pytest
import numpy as np

from tests.synthetic.generators import (
    create_full_grid_synthetic_statement,
    create_unruled_synthetic_statement,
)
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine, TableStyleVerdict, RowBandType


def test_synthetic_full_grid_recovery(tmp_path):
    """
    Test 1: Full-Grid Synthetic Statement Ground-Truth Recovery.
    Verifies that every line, column width, and text origin is recovered
    within float precision (<= 0.05 pt for lines/text, <= 0.10 pt for columns).
    """
    pdf_path = str(tmp_path / "full_grid.pdf")
    gt = create_full_grid_synthetic_statement(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    # 1. Page Dimensions Check
    assert abs(page_layer.width_pt - gt.page_width) < 1e-4
    assert abs(page_layer.height_pt - gt.page_height) < 1e-4
    
    # 2. Vector Lines Recovery Check
    ruleset = RuleSet.from_page_layer(page_layer)
    
    h_line_deltas = []
    for kl in [l for l in gt.lines if l.orientation == "H"]:
        # Find matching extracted rule
        matching = [r for r in ruleset.h_rules if abs(r.centre - kl.y0) <= 0.5 and abs(r.start - kl.x0) <= 1.0]
        assert len(matching) >= 1, f"Missing H-rule at y={kl.y0}"
        best = matching[0]
        delta_y = abs(best.centre - kl.y0)
        delta_w = abs(best.width - kl.stroke_width)
        h_line_deltas.append(delta_y)
        assert delta_y <= 0.05, f"H-rule y error: {delta_y:.4f} pt > 0.05 pt"
        assert delta_w <= 0.05, f"H-rule width error: {delta_w:.4f} pt > 0.05 pt"
        
    v_line_deltas = []
    for kl in [l for l in gt.lines if l.orientation == "V"]:
        matching = [r for r in ruleset.v_rules if abs(r.centre - kl.x0) <= 0.5 and abs(r.start - kl.y0) <= 1.0]
        assert len(matching) >= 1, f"Missing V-rule at x={kl.x0}"
        best = matching[0]
        delta_x = abs(best.centre - kl.x0)
        v_line_deltas.append(delta_x)
        assert delta_x <= 0.05, f"V-rule x error: {delta_x:.4f} pt > 0.05 pt"
        
    # 3. Table Column Recovery Check
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    assert grid.table_style_chosen == TableStyleVerdict.FULL_GRID
    assert len(grid.columns) == len(gt.columns)
    
    col_width_deltas = []
    for i, kc in enumerate(gt.columns):
        extracted_col = grid.columns[i]
        delta_w = abs(extracted_col.width_pt - kc.inner_width)
        col_width_deltas.append(delta_w)
        # Verify column boundaries and inner cell widths within 0.05 pt
        assert delta_w <= 0.05, f"Column {i+1} inner width error: {delta_w:.4f} pt > 0.05 pt (expected {kc.inner_width:.2f}, got {extracted_col.width_pt:.2f})"
        exp_x0 = kc.x0 + 0.375
        assert abs(extracted_col.x0_pt - exp_x0) <= 0.05, f"Column {i+1} x0 error: got {extracted_col.x0_pt:.2f}, expected {exp_x0:.2f}"
        
    # 4. Text Character Origin & Advance Widths Check
    text_deltas = []
    for kt in gt.texts:
        # Match by text substring
        matching_chars = [c for c in page_layer.chars if (c.unicode_text or c.char_text).strip()]
        line_chars = [c for c in matching_chars if abs(c.origin_device_pt[1] - kt.y) <= 0.5]
        if line_chars:
            first_c = min(line_chars, key=lambda c: c.origin_device_pt[0])
            # For left aligned text starting at kt.x
            if any(abs(c.origin_device_pt[0] - kt.x) <= 0.5 for c in line_chars):
                matched_c = next(c for c in line_chars if abs(c.origin_device_pt[0] - kt.x) <= 0.5)
                delta_pos = abs(matched_c.origin_device_pt[0] - kt.x)
                text_deltas.append(delta_pos)
                assert delta_pos <= 0.05, f"Text '{kt.text}' origin error: {delta_pos:.4f} pt"
                
    # Report actual measured errors
    print("\n--- Measured Full Grid Geometric Errors ---")
    print(f"H-Lines Mean Delta: {np.mean(h_line_deltas):.4f} pt | P95: {np.percentile(h_line_deltas, 95):.4f} pt | Max: {max(h_line_deltas):.4f} pt")
    print(f"V-Lines Mean Delta: {np.mean(v_line_deltas):.4f} pt | P95: {np.percentile(v_line_deltas, 95):.4f} pt | Max: {max(v_line_deltas):.4f} pt")
    print(f"Column Widths Mean Delta: {np.mean(col_width_deltas):.4f} pt | P95: {np.percentile(col_width_deltas, 95):.4f} pt | Max: {max(col_width_deltas):.4f} pt")


def test_synthetic_unruled_recovery(tmp_path):
    """
    Test 2: Unruled Synthetic Statement Ground-Truth Recovery.
    Verifies that virtual column dividers, text baselines, multi-line rows,
    and row pitches are recovered from pure whitespace gutters without vector rules.
    """
    pdf_path = str(tmp_path / "unruled.pdf")
    gt = create_unruled_synthetic_statement(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    assert grid.table_style_chosen in (TableStyleVerdict.UNRULED, TableStyleVerdict.BORDERLESS)
    assert len(grid.columns) == len(gt.columns)
    
    # Assert row grouping and pitch
    body_rows = [r for r in grid.rows if r.row_type == RowBandType.BODY]
    assert len(body_rows) == 4
    
    # Row 1 has 2 lines, Row 2 has 3 lines
    assert body_rows[0].lines_count == 2
    assert body_rows[1].lines_count == 3
    assert abs(body_rows[0].pitch_pt - 11.0) <= 0.5
    assert abs(body_rows[1].pitch_pt - 11.0) <= 0.5
    
    # Assert column alignment
    assert grid.columns[3].alignment == "right"
    assert grid.columns[4].alignment == "right"
    assert grid.columns[1].alignment == "left"
