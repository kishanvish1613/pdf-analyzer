"""
Tests for Header Statement Title & Section Gaps Analysis.
Verifies detection of 'Statement of account', gap calculations, and editor integration.
"""

import pytest
from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, Color, StreamProvenance, ByteRange
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l4_layout.header import HeaderEngine
from pdf_analyzer.l4_layout.models import HeaderModel, BlockType
from pdf_analyzer.l5_editor.model import EditorModelBuilder


def make_char(text: str, x0: float, y0: float, x1: float, y1: float, font_name: str = "Helvetica", size: float = 10.0) -> PaintedTextChar:
    prov = StreamProvenance(
        stream_name="Page1",
        byte_range=ByteRange(0, 10),
        operator_index=1,
        operator_name="Tj",
    )
    return PaintedTextChar(
        char_id=f"c_{int(x0)}_{int(y0)}",
        char_code=ord(text) if text else 32,
        char_text=text,
        unicode_text=text,
        font_name=font_name,
        font_size_pt=size,
        origin_device_pt=(x0, y0),
        advance_pt=x1 - x0,
        font_bbox_device_pt=(x0, y0, x1, y1),
        ink_bbox_device_pt=(x0, y0, x1, y1),
        text_matrix=(size, 0.0, 0.0, size, x0, y0),
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        rendering_mode=0,
        fill_color=Color(space="DeviceRGB", components=(0.0, 0.0, 0.0)),
        stroke_color=None,
        provenance=prov,
    )


def test_statement_title_and_gap_detection():
    # 1. Simulate account details line at Y = 700 to 710
    # 2. Simulate "Statement of account" title at Y = 650 to 662
    # 3. Table starts at Y = 600
    chars = []
    # Account detail text: "Branch Code : 3885" at y0=700, y1=710
    acc_text = "Branch Code : 3885"
    for i, ch in enumerate(acc_text):
        chars.append(make_char(ch, 50.0 + i * 6.0, 700.0, 50.0 + (i + 1) * 6.0, 710.0))

    # Statement title text: "Statement of account" at y0=650, y1=662
    title_text = "Statement of account"
    for i, ch in enumerate(title_text):
        chars.append(make_char(ch, 50.0 + i * 8.0, 650.0, 50.0 + (i + 1) * 8.0, 662.0, font_name="Helvetica-Bold", size=12.0))

    page_layer = PageByteLayer(
        page_number=1,
        mediabox_pt=(0.0, 0.0, 595.0, 842.0),
        cropbox_pt=(0.0, 0.0, 595.0, 842.0),
        rotation_deg=0,
        chars=chars,
        paths=[],
    )

    engine = HeaderEngine()
    model: HeaderModel = engine.build_header_model(page_layer=page_layer, table_top_y_pt=600.0)

    assert model.statement_title is not None
    assert "Statement of account" in model.statement_title.lines[0].text
    # Expected gaps:
    # Account bottom is 700.0
    # Title top is 662.0 -> Gap account to title = 700.0 - 662.0 = 38.0 pt
    # Title bottom is 650.0 -> Gap title to table = 650.0 - 600.0 = 50.0 pt
    # Total account to table gap = 700.0 - 600.0 = 100.0 pt
    assert abs(model.gap_account_to_title_pt - 38.0) < 0.1
    assert abs(model.gap_title_to_table_pt - 50.0) < 0.1
    assert abs(model.account_to_table_gap_pt - 100.0) < 0.1

    # Test Editor Model integration
    ruleset = RuleSet(page_number=1, width_pt=595.0, height_pt=842.0, h_rules=[], v_rules=[])
    builder = EditorModelBuilder(dpi=300)
    editor_model = builder.build_editor_model(
        page_layer=page_layer,
        ruleset=ruleset,
        header_model=model,
    )

    box_titles = [b.get("id") for b in editor_model.boxes]
    assert "box_statement_title" in box_titles

    dim_ids = [d["id"] for d in editor_model.dimensions]
    assert "dim_gap_account_to_title" in dim_ids
    assert "dim_gap_title_to_table" in dim_ids
    assert "dim_account_to_table_gap" in dim_ids
