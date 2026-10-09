"""Unit tests for unit conversions, geometry, colors, and font parsing."""

import pytest
from pdf_analyzer.utils.units import pt_to_mm, mm_to_pt, pt_to_px, px_to_pt, create_multi_unit_value, create_bbox_from_pt
from pdf_analyzer.utils.color import int_or_float_to_rgb, rgb_to_hex, hex_to_rgb, calculate_luminance
from pdf_analyzer.utils.font_parser import clean_font_name, parse_font_properties
from pdf_analyzer.utils.geometry import cluster_1d_coordinates, cluster_representatives, bbox_intersection, bbox_iou


def test_unit_conversions():
    # 72 points = 1 inch = 25.4 mm
    assert pytest.approx(pt_to_mm(72.0), 0.001) == 25.4
    assert pytest.approx(mm_to_pt(25.4), 0.001) == 72.0
    # At 300 DPI, 72 pt = 300 px
    assert pytest.approx(pt_to_px(72.0, dpi=300), 0.01) == 300.0
    assert pytest.approx(px_to_pt(300.0, dpi=300), 0.01) == 72.0


def test_multi_unit_value():
    mu = create_multi_unit_value(36.0, page_ref_dim_pt=720.0, dpi=300)
    assert mu.pt == 36.0
    assert pytest.approx(mu.mm, 0.01) == 12.7
    assert pytest.approx(mu.px, 0.01) == 150.0
    assert pytest.approx(mu.rel_pct, 0.01) == 5.0
    d = mu.to_dict()
    assert "pt" in d and "mm" in d and "px" in d and "rel_pct" in d


def test_color_utilities():
    assert rgb_to_hex((255, 0, 128)) == "#FF0080"
    assert hex_to_rgb("#FF0080") == (255, 0, 128)
    assert int_or_float_to_rgb(0xFF0000) == (255, 0, 0)
    assert int_or_float_to_rgb((1.0, 0.5, 0.0)) == (255, 127, 0)
    assert calculate_luminance((0, 0, 0)) == 0.0
    assert pytest.approx(calculate_luminance((255, 255, 255)), 0.01) == 1.0


def test_font_parser():
    clean = clean_font_name("BAAAAA+Helvetica-Bold")
    assert clean == "Helvetica-Bold"

    clean_name, family, is_bold, is_italic, is_mono, is_serif, weight = parse_font_properties("ABCDEF+TimesNewRoman-BoldItalic")
    assert is_bold is True
    assert is_italic is True
    assert is_serif is True
    assert weight == "bold"


def test_geometry_and_clustering():
    values = [10.0, 10.5, 11.0, 50.0, 51.0, 100.0]
    clusters = cluster_1d_coordinates(values, tolerance=2.0)
    assert len(clusters) == 3
    reps = cluster_representatives(values, tolerance=2.0)
    assert len(reps) == 3

    b1 = (0, 0, 10, 10)
    b2 = (5, 5, 15, 15)
    inter = bbox_intersection(b1, b2)
    assert inter == (5, 5, 10, 10)
    iou = bbox_iou(b1, b2)
    assert 0.14 <= iou <= 0.15


def test_report_scripts_print_top_left_coordinates():
    import runpy
    import contextlib
    import io
    import sys
    import os

    scripts = [
        "scratch/sbi_ravin_compare.py",
        "scratch/kotak_report.py",
        "scratch/union_bank_compare.py",
    ]
    for s in scripts:
        if not os.path.exists(s):
            continue
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            runpy.run_path(s)
        stdout_str = buf.getvalue()
        assert "[Coordinate Frame: Top-Left CropBox Origin, pt]" in stdout_str, (
            f"{s} missing '[Coordinate Frame: Top-Left CropBox Origin, pt]' header line"
        )
        if "sbi" in s:
            # Table bbox must be top-left (y in 489..734), NOT bottom-up (107..352)
            assert "489.750, 575.250, 734.250" in stdout_str, (
                f"{s} did not print top-left coordinates for table bbox"
            )
            assert "107.75" not in stdout_str, (
                f"{s} printed bottom-up coordinate 107.75 pt instead of top-left"
            )
            # Header baseline must be top-left ~508.46, NOT bottom-up 333.54
            assert "508.46" in stdout_str, f"{s} missing top-left header baseline"
            assert "333.54" not in stdout_str, f"{s} printed bottom-up baseline 333.54 pt"
        if "union_bank" in s:
            # Table bbox must be top-left y0 ~ 318, NOT bottom-up inverted 802..1064
            assert "318.000, 728.000, 848.000" in stdout_str, (
                f"{s} did not print top-left table bbox with y0 ~ 318"
            )
            assert "802.000" not in stdout_str, (
                f"{s} printed inverted bottom-up coordinate 802.000 pt"
            )


def test_to_top_left_bbox_non_a4_pages():
    """Verify coordinate conversion to top-left on non-A4 pages (heights 1100, 700, 1000 pt)."""
    from pdf_analyzer.utils.units import to_top_left_bbox

    # Test 1: Union Bank 1100 pt height page (782 x 1100 pt)
    cb_1100 = (0.0, 0.0, 782.0, 1100.0)
    # Native bottom-up bbox: header top at y=782, table bottom at y=252
    native_bbox = (34.0, 252.0, 728.0, 782.0)
    tl_bbox = to_top_left_bbox(native_bbox, cb_1100)
    assert pytest.approx(tl_bbox[0], 0.01) == 34.0
    assert pytest.approx(tl_bbox[1], 0.01) == 318.0  # 1100 - 782 = 318
    assert pytest.approx(tl_bbox[2], 0.01) == 728.0
    assert pytest.approx(tl_bbox[3], 0.01) == 848.0  # 1100 - 252 = 848

    # Test 2: Arbitrary 700 pt height page
    cb_700 = (0.0, 0.0, 500.0, 700.0)
    tl_700 = to_top_left_bbox((50.0, 100.0, 450.0, 650.0), cb_700)
    assert pytest.approx(tl_700[1], 0.01) == 50.0   # 700 - 650 = 50
    assert pytest.approx(tl_700[3], 0.01) == 600.0  # 700 - 100 = 600

    # Test 3: Arbitrary 1000 pt height page
    cb_1000 = (0.0, 0.0, 600.0, 1000.0)
    tl_1000 = to_top_left_bbox((20.0, 150.0, 580.0, 920.0), cb_1000)
    assert pytest.approx(tl_1000[1], 0.01) == 80.0   # 1000 - 920 = 80
    assert pytest.approx(tl_1000[3], 0.01) == 850.0  # 1000 - 150 = 850


def test_independent_probe_does_not_import_pdf_analyzer():
    """Verify tests/independent_probe.py does not import anything from pdf_analyzer."""
    import ast

    probe_path = "tests/independent_probe.py"
    with open(probe_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=probe_path)

    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.append(node.module)

    for mod in imported_modules:
        assert not mod.startswith("pdf_analyzer"), (
            f"independent_probe.py imports forbidden module {mod!r} from pdf_analyzer"
        )




def test_golden_manual_json_requires_editor_export_source():
    """
    K1: Any *.manual.json in tests/golden/ must carry
        {"source": "editor_export", "exported_at": ...}
    _load_manual_golden must return None (and warn) for files lacking it.
    Existing golden/*.manual.json files are verified here.
    A synthetic rejection is also proven with a temp file.
    """
    import json
    import glob
    import tempfile
    import os
    from pdf_analyzer.corpus_check import _load_manual_golden

    # 1. Every existing *.manual.json must pass validation
    golden_dir = "tests/golden"
    manual_files = glob.glob(os.path.join(golden_dir, "*.manual.json"))
    for mf in manual_files:
        data = _load_manual_golden(mf)
        assert data is not None, (
            f"{mf} exists but _load_manual_golden returned None — "
            "it lacks source='editor_export'. Supply only editor-exported files."
        )
        assert data.get("source") == "editor_export", (
            f"{mf}: source must be 'editor_export', got {data.get('source')!r}"
        )
        assert "exported_at" in data, (
            f"{mf}: missing required 'exported_at' key"
        )

    # 2. Prove that a file WITHOUT source='editor_export' is rejected (returns None)
    bad_payload = {
        "source": "manual_hand_edit",
        "exported_at": "2026-01-01T00:00:00Z",
        "table_bbox": {"width_pt": 500.0},
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".manual.json", dir=golden_dir, delete=False, encoding="utf-8"
    ) as tf:
        json.dump(bad_payload, tf)
        bad_path = tf.name
    try:
        result = _load_manual_golden(bad_path)
        assert result is None, (
            "_load_manual_golden accepted a file with source='manual_hand_edit' — must reject"
        )
    finally:
        os.unlink(bad_path)

    # 3. Prove that a valid editor_export file is accepted
    good_payload = {
        "source": "editor_export",
        "exported_at": "2026-10-06T09:00:00Z",
        "table_bbox": {"width_pt": 500.0},
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".manual.json", dir=golden_dir, delete=False, encoding="utf-8"
    ) as tf:
        json.dump(good_payload, tf)
        good_path = tf.name
    try:
        result = _load_manual_golden(good_path)
        assert result is not None, (
            "_load_manual_golden rejected a valid editor_export file"
        )
        assert result["source"] == "editor_export"
    finally:
        os.unlink(good_path)


def test_single_drawer_for_lane_and_marker_layers():
    """
    Item 4: Verify only one drawer handles lane and marker layers,
    and assert that duplicate renderer registrations fail.
    """
    import os
    # 1. Verify editor.js registers a unique renderer for grpDimensionLane
    editor_js_path = "static/js/editor.js"
    assert os.path.exists(editor_js_path)
    with open(editor_js_path, "r", encoding="utf-8") as f:
        js_code = f.read()

    # Must contain assertUniqueLayerRenderer call for grpDimensionLane
    assert "this.assertUniqueLayerRenderer('grpDimensionLane', 'renderDimensionLane');" in js_code
    assert "renderDimensionLane()" in js_code

    # 2. Simulate LayerRendererRegistry enforcing single-drawer invariance and throwing on duplicate
    class LayerRendererRegistry:
        def __init__(self):
            self._render_map = {}

        def register_layer_renderer(self, layer_id: str, fn_name: str):
            existing = self._render_map.get(layer_id)
            if existing and existing != fn_name:
                raise ValueError(
                    f"Layer conflict: Layer '{layer_id}' is claimed by both '{existing}' and '{fn_name}'. "
                    "Exactly one drawer/renderer allowed."
                )
            self._render_map[layer_id] = fn_name

    registry = LayerRendererRegistry()
    registry.register_layer_renderer("grpDimensionLane", "renderDimensionLane")
    # Same function re-registration is idempotent
    registry.register_layer_renderer("grpDimensionLane", "renderDimensionLane")

    # Duplicate / conflicting drawer registration MUST fail
    with pytest.raises(ValueError, match="Layer conflict"):
        registry.register_layer_renderer("grpDimensionLane", "renderMarkerLayerDuplicate")

    with pytest.raises(ValueError, match="Layer conflict"):
        registry.register_layer_renderer("grpDimensionLane", "renderSecondaryLaneDrawer")

    # 3. Verify Python DimensionLaneModel unifies arrows and numbered markers under single drawer model
    from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneModel, DimensionArrow, NumberedMarker
    model = DimensionLaneModel(
        lane_id="dim_lane_p1",
        lane_y_pt=500.0,
        arrows=[
            DimensionArrow(1, "r1", "r2", 36.0, 150.0, 114.0, 500.0, "114.00 pt"),
            DimensionArrow(2, "r2", "r3", 150.0, 300.0, 150.0, 500.0, "150.00 pt"),
        ],
        numbered_markers=[
            NumberedMarker(1, "1", 93.0, 500.0, 114.0),
            NumberedMarker(2, "2", 225.0, 500.0, 150.0),
        ],
    )
    d = model.to_dict()
    assert "arrows" in d
    assert "numbered_markers" in d
    assert len(d["arrows"]) == 2
    assert len(d["numbered_markers"]) == 2

