"""
Acceptance Test Suite T1-T5 for Dimension Editor, Exporter & State Persistence.
"""

import os
import json
import pytest
from app import app, OUTPUT_FOLDER, UPLOAD_FOLDER
from generate_sample_pdf import create_synthetic_statement
from pdf_analyzer.dimensions_export import export_dimensions
from pdf_analyzer.editor_model import (
    create_default_editor_model,
    recompute_derived_model,
    apply_edits_to_model,
    save_sidecar_edits,
    load_sidecar_edits,
    compute_pdf_hash,
    get_sidecar_edits_path
)


@pytest.fixture
def sample_fixture_model():
    """Builds a realistic mock EditorModel fixture."""
    return {
        "page_number": 1,
        "document_name": "sample_statement.pdf",
        "width_pt": 612.0,
        "height_pt": 792.0,
        "dpi": 300,
        "scale_factor": 300.0 / 72.0,
        "guides": [
            {"id": "guide_v_1", "type": "vertical_rule", "orientation": "V", "position_pt": 36.0, "source": "auto"},
            {"id": "guide_v_2", "type": "vertical_rule", "orientation": "V", "position_pt": 150.0, "source": "auto"},
            {"id": "guide_v_3", "type": "vertical_rule", "orientation": "V", "position_pt": 300.0, "source": "auto"},
            {"id": "guide_v_4", "type": "vertical_rule", "orientation": "V", "position_pt": 576.0, "source": "auto"}
        ],
        "boxes": [
            {"id": "box_container_1", "type": "container", "x0_pt": 36.0, "y0_pt": 80.0, "x1_pt": 250.0, "y1_pt": 180.0, "width_pt": 214.0, "height_pt": 100.0, "title": "Address Box"}
        ],
        "table_bbox": {"x0_pt": 36.0, "y0_pt": 220.0, "x1_pt": 576.0, "y1_pt": 700.0, "width_pt": 540.0, "height_pt": 480.0},
        "columns": [
            {"column_index": 1, "header_text": "Date", "x0_pt": 36.0, "x1_pt": 150.0, "width_pt": 114.0, "source": "auto"},
            {"column_index": 2, "header_text": "Description", "x0_pt": 150.0, "x1_pt": 300.0, "width_pt": 150.0, "source": "auto"},
            {"column_index": 3, "header_text": "Amount", "x0_pt": 300.0, "x1_pt": 576.0, "width_pt": 276.0, "source": "auto"}
        ],
        "rows": [
            {"row_index": 1, "y0_pt": 220.0, "y1_pt": 240.0, "height_pt": 20.0, "row_type": "header"},
            {"row_index": 2, "y0_pt": 240.0, "y1_pt": 260.0, "height_pt": 20.0, "row_type": "body"}
        ],
        "dimensions": [
            {"id": "dim_page_width", "no": 1, "group": "Page & Margins", "title": "Page Width", "value_pt": 612.0, "unit": "pt", "definition": "CropBox width", "from_anchor": "page_left", "to_anchor": "page_right", "source": "auto"},
            {"id": "dim_table_width", "no": 2, "group": "Table & Columns", "title": "Table Width", "value_pt": 540.0, "unit": "pt", "definition": "Total table width", "from_anchor": "table_x0", "to_anchor": "table_x1", "source": "auto"},
            {"id": "dim_col_1_width", "no": 3, "group": "Table & Columns", "title": "Column 1 (Date) Width", "value_pt": 114.0, "unit": "pt", "definition": "Col 1 width", "from_anchor": "col_1:x0", "to_anchor": "col_1:x1", "source": "auto"},
            {"id": "dim_col_2_width", "no": 4, "group": "Table & Columns", "title": "Column 2 (Description) Width", "value_pt": 150.0, "unit": "pt", "definition": "Col 2 width", "from_anchor": "col_2:x0", "to_anchor": "col_2:x1", "source": "auto"},
            {"id": "dim_col_3_width", "no": 5, "group": "Table & Columns", "title": "Column 3 (Amount) Width", "value_pt": 276.0, "unit": "pt", "definition": "Col 3 width", "from_anchor": "col_3:x0", "to_anchor": "col_3:x1", "source": "auto"}
        ]
    }


def test_t1_dimensions_export(sample_fixture_model):
    """T1: Verify every export format is produced and satisfies layout specs."""
    # 1. Markdown Table
    md = export_dimensions(sample_fixture_model, export_format="markdown", unit="pt", decimals=2)
    assert "| No. | Group | Title | Value | Unit | Definition | From Anchor | To Anchor | Source |" in md
    assert "| 1 | Page & Margins | Page Width | 612.00 | pt | CropBox width |" in md

    # 2. Prompt-Ready Compact Block
    prompt = export_dimensions(sample_fixture_model, export_format="prompt", unit="pt")
    assert "### Page Margins" in prompt or "### Page" in prompt
    assert "Page Width = 612.00 pt" in prompt
    assert "### Table Columns" in prompt or "### Table" in prompt
    assert "Table Width = 540.00 pt" in prompt

    # 3. TSV (9 columns)
    tsv = export_dimensions(sample_fixture_model, export_format="tsv", unit="mm", decimals=2)
    lines = tsv.strip().split("\n")
    header_cols = lines[0].split("\t")
    assert len(header_cols) == 9
    assert header_cols[0] == "No" and header_cols[2] == "Title" and header_cols[4] == "Unit"

    # 4. JSON Round-Trip
    json_str = export_dimensions(sample_fixture_model, export_format="json", unit="pt")
    parsed = json.loads(json_str)
    assert parsed["document_name"] == "sample_statement.pdf"
    assert len(parsed["dimensions"]) == 5

    # 5. Plain Text
    plain = export_dimensions(sample_fixture_model, export_format="plain", unit="pt")
    assert "Page Width: 612.00 pt" in plain

    # 6. AI Prompt & Generator Code
    ai_prompt = export_dimensions(sample_fixture_model, export_format="ai_prompt", unit="pt")
    assert "System Prompt & Mathematical Layout Specification" in ai_prompt
    assert "ReportLab Platypus" in ai_prompt
    assert "COL_WIDTHS = [114.0, 150.0, 276.0]" in ai_prompt
    assert "Table Outer Bounding Box" in ai_prompt


def test_t2_editor_model_recomputation(sample_fixture_model):
    """T2: Moving a vertical rule updates adjacent column widths and table width accurately."""
    model = json.loads(json.dumps(sample_fixture_model))

    # Move inner rule guide_v_2 from 150.0 to 180.0 pt (+30 pt)
    model["guides"][1]["position_pt"] = 180.0
    model["guides"][1]["source"] = "manual"

    recomputed = recompute_derived_model(model)

    # Column 1 width should expand: 180 - 36 = 144 pt (was 114)
    # Column 2 width should shrink: 300 - 180 = 120 pt (was 150)
    # Column 3 width should remain: 576 - 300 = 276 pt
    assert abs(recomputed["columns"][0]["width_pt"] - 144.0) < 0.01
    assert abs(recomputed["columns"][1]["width_pt"] - 120.0) < 0.01
    assert abs(recomputed["columns"][2]["width_pt"] - 276.0) < 0.01

    # Sum of column widths must still equal total table width (540 pt)
    sum_w = sum(c["width_pt"] for c in recomputed["columns"])
    assert abs(sum_w - 540.0) < 0.01
    assert recomputed["consistency"]["checks"]["col_width_sum_ok"] is True

    # Move outer right rule guide_v_4 from 576.0 to 600.0 pt (+24 pt)
    model["guides"][3]["position_pt"] = 600.0
    recomputed2 = recompute_derived_model(model)
    assert abs(recomputed2["table_bbox"]["width_pt"] - 564.0) < 0.01
    assert abs(recomputed2["columns"][2]["width_pt"] - 300.0) < 0.01


def test_t3_edits_persistence(tmp_path):
    """T3: Sidecar file persistence, reload fidelity, and hash isolation."""
    pdf_path = str(tmp_path / "test_statement.pdf")
    create_synthetic_statement(pdf_path)

    sidecar_path = get_sidecar_edits_path(pdf_path, str(tmp_path))
    assert sidecar_path.endswith(".edits.json")

    edits_payload = {
        "pages": {
            "1": {
                "guides": {"guide_v_2": {"position_pt": 175.5, "title": "Manual Col 2 Split"}},
                "boxes": {},
                "dimensions": {}
            }
        },
        "total_manual_edits": 1
    }

    save_sidecar_edits(pdf_path, edits_payload, str(tmp_path))
    assert os.path.exists(sidecar_path)

    loaded = load_sidecar_edits(pdf_path, str(tmp_path))
    assert loaded["total_manual_edits"] == 1
    assert loaded["pages"]["1"]["guides"]["guide_v_2"]["position_pt"] == 175.5

    # Test that a different PDF does not load these edits
    diff_pdf = str(tmp_path / "other_statement.pdf")
    with open(diff_pdf, "wb") as f:
        f.write(b"%PDF-1.4 dummy content with different hash")

    diff_loaded = load_sidecar_edits(diff_pdf, str(tmp_path))
    assert diff_loaded["total_manual_edits"] == 0


def test_t4_coordinate_roundtrip_precision():
    """T4: Sub-0.001 pt coordinate round-trip transformation accuracy."""
    from pdf_analyzer.utils.units import CoordinateTransform
    cropbox = [0.0, 0.0, 612.0, 792.0]
    mediabox = [0.0, 0.0, 612.0, 792.0]
    transform = CoordinateTransform(cropbox, mediabox, rotation=0, dpi=300)

    test_pts = [0.0, 36.125, 150.789, 300.5, 576.222, 612.0]
    for x_pt in test_pts:
        px = transform.pt_to_px(x_pt)
        back_pt = transform.px_to_pt(px)
        assert abs(back_pt - x_pt) < 0.001, f"Coordinate roundtrip delta ({abs(back_pt - x_pt)}) exceeded 0.001 pt"


def test_t5_backend_rest_api(sample_fixture_model):
    """T5: REST API endpoints return 200 and conform to schema."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        # 1. Model GET
        res_model = client.get("/api/editor/sample/page/1/model")
        assert res_model.status_code == 200
        data_m = json.loads(res_model.data)
        assert data_m["status"] == "success"
        assert "editor_model" in data_m

        # 2. Edits PUT
        res_put = client.put(
            "/api/editor/sample/page/1/edits",
            data=json.dumps({"page_number": 1, "edits": {"guides": {"guide_v_2": {"position_pt": 180.0}}}}),
            content_type="application/json"
        )
        assert res_put.status_code == 200
        data_p = json.loads(res_put.data)
        assert data_p["status"] == "success"
        assert "sidecar_file" in data_p

        # 3. Recompute POST
        res_recomp = client.post(
            "/api/editor/sample/page/1/recompute",
            data=json.dumps({"editor_model": sample_fixture_model}),
            content_type="application/json"
        )
        assert res_recomp.status_code == 200
        data_r = json.loads(res_recomp.data)
        assert data_r["status"] == "success"
        assert "consistency" in data_r

        # 4. Dimensions Export POST
        res_exp = client.post(
            "/api/editor/sample/dimensions",
            data=json.dumps({"editor_model": sample_fixture_model, "format": "prompt", "units": "pt"}),
            content_type="application/json"
        )
        assert res_exp.status_code == 200
        data_e = json.loads(res_exp.data)
        assert data_e["status"] == "success"
        assert "Page Width = 612.00 pt" in data_e["text"]

        # 5. Ground Truth POST
        res_gt = client.post(
            "/api/editor/sample/ground-truth",
            data=json.dumps({"editor_model": sample_fixture_model}),
            content_type="application/json"
        )
        assert res_gt.status_code == 200
        data_g = json.loads(res_gt.data)
        assert data_g["status"] == "success"
        assert "ground_truth_file" in data_g
