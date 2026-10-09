"""Comprehensive Web UI & Dimension Editor API Test Suite."""

import os
import json
import pytest
from app import app, OUTPUT_FOLDER
from generate_sample_pdf import create_synthetic_statement


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_page(client):
    """Test dashboard index page rendering."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"PDF Design Analyzer" in response.data
    assert b"Interactive Dimension Editor" in response.data


def test_sample_api_endpoint(client):
    """Test sample generation and analysis endpoint returns editor model."""
    response = client.post("/api/sample", data={"dpi": 150, "pages": "all"})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "spec" in data
    assert "editor_model" in data
    assert "urls" in data
    assert "dimensions" in data["editor_model"]
    assert "guides" in data["editor_model"]
    assert "boxes" in data["editor_model"]


def test_upload_api_endpoint(client, tmp_path):
    """Test uploading a PDF and receiving analysis + editor model."""
    pdf_path = str(tmp_path / "upload_test.pdf")
    create_synthetic_statement(pdf_path)

    with open(pdf_path, "rb") as f:
        response = client.post(
            "/api/upload",
            data={
                "pdf": (f, "upload_test.pdf"),
                "dpi": 150,
                "pages": "all"
            },
            content_type="multipart/form-data"
        )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "spec" in data
    assert "editor_model" in data


def test_editor_model_endpoint(client):
    """Test GET /api/editor/model endpoint."""
    # Ensure sample analysis has run
    client.post("/api/sample", data={"dpi": 150, "pages": "all"})

    response = client.get("/api/editor/model?page=1")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "editor_model" in data
    model = data["editor_model"]
    assert model["page_number"] == 1
    assert "guides" in model
    assert "boxes" in model
    assert "dimensions" in model
    assert len(model["dimensions"]) > 0


def test_editor_save_endpoint(client):
    """Test POST /api/editor/save endpoint."""
    mock_model = {
        "page_number": 99,
        "width_pt": 612.0,
        "height_pt": 792.0,
        "guides": [
            {"id": "guide_v_99", "type": "vertical_rule", "orientation": "V", "position_pt": 150.0, "source": "manual"}
        ],
        "boxes": [],
        "dimensions": [
            {"id": "dim_99", "no": 1, "title": "Custom Col 99", "value_pt": 150.0, "unit": "pt", "source": "manual"}
        ]
    }

    response = client.post(
        "/api/editor/save",
        data=json.dumps({"page_number": 99, "editor_model": mock_model}),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"

    # Verify model is returned on subsequent load
    get_res = client.get("/api/editor/model?page=99")
    assert get_res.status_code == 200
    get_data = json.loads(get_res.data)
    assert get_data["editor_model"]["guides"][0]["id"] == "guide_v_99"

    # Clean up test state file
    test_state_file = os.path.join(OUTPUT_FOLDER, "editor_state_page_99.json")
    if os.path.exists(test_state_file):
        os.remove(test_state_file)


def test_editor_redetect_endpoint(client):
    """Test POST /api/editor/redetect ROI re-detection."""
    # Ensure sample is created
    client.post("/api/sample", data={"dpi": 150, "pages": "all"})

    response = client.post(
        "/api/editor/redetect",
        data=json.dumps({
            "page_number": 1,
            "roi_bbox_pt": [36.0, 200.0, 576.0, 600.0],
            "dpi": 150
        }),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "columns" in data
    assert "rows" in data
    assert "rules" in data


def test_editor_copy_page_edits_endpoint(client):
    """Test POST /api/editor/copy_page_edits repeating guide propagation."""
    mock_model = {
        "page_number": 1,
        "width_pt": 612.0,
        "height_pt": 792.0,
        "guides": [
            {"id": "guide_v_col_1", "orientation": "V", "position_pt": 120.0}
        ],
        "boxes": [],
        "dimensions": []
    }

    response = client.post(
        "/api/editor/copy_page_edits",
        data=json.dumps({
            "source_page": 1,
            "target_pages": [2, 3],
            "editor_model": mock_model
        }),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert data["updated_pages"] == [2, 3]

    # Clean up target page states
    for p in [2, 3]:
        p_file = os.path.join(OUTPUT_FOLDER, f"editor_state_page_{p}.json")
        if os.path.exists(p_file):
            os.remove(p_file)


def test_pdf_info_and_analyze_specific_page(client):
    """Test /api/pdf-info and POST /api/analyze-page for individual page extraction."""
    # Ensure sample is created
    client.post("/api/sample", data={"dpi": 150, "page": 1})

    # Test PDF info
    info_res = client.get("/api/pdf-info?doc=sample_statement.pdf")
    assert info_res.status_code == 200
    info_data = json.loads(info_res.data)
    assert info_data["status"] == "success"
    assert info_data["total_pages"] >= 1
    assert "pages" in info_data

    # Test analyze specific page
    analyze_res = client.post(
        "/api/analyze-page",
        data=json.dumps({
            "doc_id": "sample_statement.pdf",
            "page": 1,
            "dpi": 150
        }),
        content_type="application/json"
    )
    assert analyze_res.status_code == 200
    analyze_data = json.loads(analyze_res.data)
    assert analyze_data["status"] == "success"
    assert analyze_data["page_number"] == 1
    assert "editor_model" in analyze_data
    assert "annotated_image" in analyze_data["urls"]

