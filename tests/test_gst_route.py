"""Test Suite for Form GSTR-3B Pixel-Perfect Clone Route & Generators."""

import os
import json
import pytest
import pymupdf

from app import app, OUTPUT_FOLDER
from pdf_analyzer.gst.gstr3b_generator import generate_gstr3b_pdf, get_default_gstr3b_data
from pdf_analyzer.gst.gstr3b_html import generate_gstr3b_html


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_gstr3b_pdf_generator_creates_exact_3_pages(tmp_path):
    """Verify that ReportLab Platypus GSTR-3B generator produces exactly 3 pages with proper metadata."""
    out_pdf = str(tmp_path / "test_gstr3b.pdf")
    data = get_default_gstr3b_data()
    generate_gstr3b_pdf(out_pdf, data=data)

    assert os.path.exists(out_pdf)
    
    doc = pymupdf.open(out_pdf)
    assert len(doc) == 3, f"Expected exactly 3 pages, found {len(doc)}"

    # Check page dimensions (A4: 595.28 x 841.89 pt within 1pt tolerance)
    for p in doc:
        rect = p.rect
        assert abs(rect.width - 595.28) < 1.0
        assert abs(rect.height - 841.89) < 1.0

    # Page 1 checks
    p1_text = doc[0].get_text()
    assert "Form GSTR-3B" in p1_text
    assert "23BCHPB7336L1ZM" in p1_text
    assert "PRIYANKA NARWARIYA" in p1_text
    assert "ATHARV ENTERPRISES" in p1_text
    assert "AA230326938530E" in p1_text
    assert "3.1 Details of Outward supplies" in p1_text
    assert "4. Eligible ITC" in p1_text or "4.  Eligible ITC" in p1_text

    # Page 2 checks
    p2_text = doc[1].get_text()
    assert "5 Values of exempt, nil-rated" in p2_text or "5  Values of exempt, nil-rated" in p2_text
    assert "5.1 Interest and Late fee" in p2_text
    assert "6.1 Payment of tax" in p2_text

    # Page 3 checks
    p3_text = doc[2].get_text()
    assert "Verification" in p3_text
    assert "solemnly affirm and declare" in p3_text
    assert "PRIYANKA NARWARIYA" in p3_text
    assert "PROPRIETORSHIP" in p3_text

    doc.close()


def test_gstr3b_html_generator():
    """Verify HTML clone generator includes all section tables and styling."""
    html = generate_gstr3b_html()
    assert "<!DOCTYPE html>" in html
    assert "Form GSTR-3B" in html or "FORM GSTR-3B" in html
    assert "23BCHPB7336L1ZM" in html
    assert "PRIYANKA NARWARIYA" in html
    assert "ATHARV ENTERPRISES" in html
    assert "AA230326938530E" in html
    assert "#FDE9D9" in html or "#fde8d7" in html or "#FAD2B1" in html  # Peach/Orange header color
    assert "FILED" in html  # Watermark text
    assert 'class="page"' in html or "gstr-page" in html or ".page" in html


def test_gst_page_route(client):
    """Test GET /gst returns status 200 and loads GSTR-3B dashboard."""
    response = client.get("/gst")
    assert response.status_code == 200
    assert b"Form GSTR-3B Clone Engine" in response.data
    assert b"Interactive Data Editor" in response.data
    assert b"Live 3-Page Visual Preview" in response.data


def test_gst_data_api(client):
    """Test GET /api/gst/data returns complete GSTR-3B JSON data structure."""
    response = client.get("/api/gst/data")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["gstin"] == "23BCHPB7336L1ZM"
    assert data["legal_name"] == "PRIYANKA NARWARIYA"
    assert data["trade_name"] == "ATHARV ENTERPRISES"
    assert data["arn"] == "AA230326938530E"
    assert "table_3_1" in data
    assert "table_3_1_1" in data
    assert "table_3_2" in data
    assert "table_4_a" in data
    assert "table_5" in data
    assert "table_5_1" in data
    assert "table_6_1_a" in data
    assert "breakup" in data
    assert "verification" in data


def test_gst_generate_api_post(client):
    """Test POST /api/gst/generate compiles PDF, HTML, and renders preview images."""
    response = client.post("/api/gst/generate", json={})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert data["page_count"] == 3
    assert len(data["preview_pages"]) == 3
    assert data["pdf_url"] == "/output/Form_GSTR_3B.pdf"
    assert data["html_url"] == "/output/Form_GSTR_3B.html"

    # Verify output files exist on disk
    pdf_path = os.path.join(OUTPUT_FOLDER, "Form_GSTR_3B.pdf")
    html_path = os.path.join(OUTPUT_FOLDER, "Form_GSTR_3B.html")
    assert os.path.exists(pdf_path)
    assert os.path.exists(html_path)
    for i in range(1, 4):
        assert os.path.exists(os.path.join(OUTPUT_FOLDER, f"gstr3b_page_{i}.png"))


def test_gst_generate_with_custom_data(client, tmp_path):
    """Test compiling with customized business data."""
    custom_payload = get_default_gstr3b_data()
    custom_payload["gstin"] = "27ABCDE1234F1Z5"
    custom_payload["legal_name"] = "TECH CORP INDIA PRIVATE LIMITED"
    custom_payload["trade_name"] = "TECH CORP SOLUTIONS"

    response = client.post("/api/gst/generate", json=custom_payload)
    assert response.status_code == 200
    res_data = json.loads(response.data)
    assert res_data["status"] == "success"

    # Read generated PDF and check new content
    pdf_path = os.path.join(OUTPUT_FOLDER, "Form_GSTR_3B.pdf")
    doc = pymupdf.open(pdf_path)
    p1_text = doc[0].get_text()
    assert "27ABCDE1234F1Z5" in p1_text
    assert "TECH CORP INDIA PRIVATE LIMITED" in p1_text
    assert "TECH CORP SOLUTIONS" in p1_text
    doc.close()


def test_gst_download_pdf_route(client):
    """Test GET /api/gst/download-pdf returns attachment response."""
    response = client.get("/api/gst/download-pdf")
    assert response.status_code == 200
    assert response.headers.get("Content-Type") == "application/pdf"
    assert "attachment" in response.headers.get("Content-Disposition", "")


def test_gst_metadata_api(client):
    """Test GET /api/gst/metadata returns comprehensive PDF, Font, Color, and Geometry spec."""
    response = client.get("/api/gst/metadata")
    assert response.status_code == 200
    meta = json.loads(response.data)
    
    # EXIF & pdfinfo
    assert meta["exif"]["Creator"] == "pdfmake"
    assert meta["exif"]["Producer"] == "pdfmake"
    assert meta["exif"]["PageCount"] == 3
    assert meta["pdfinfo"]["creator"] == "pdfmake"
    assert meta["pdfinfo"]["producer"] == "pdfmake"
    assert "595.28 x 841.89" in meta["pdfinfo"]["pageSize"]
    
    # Fonts
    assert len(meta["pdffonts"]) == 3
    font_names = [f["name"] for f in meta["pdffonts"]]
    assert any("Roboto-Medium" in n for n in font_names)
    assert any("Roboto-Italic" in n for n in font_names)
    assert any("Roboto-Regular" in n for n in font_names)

    # Colors
    assert meta["colors"]["banner_background"]["hex"] == "#fde8d7"
    assert meta["colors"]["table_border"]["hex"] == "#1e293b"
    assert meta["colors"]["table_border_light"]["hex"] == "#94a3b8"
    assert meta["colors"]["text_primary"]["hex"] == "#0f172a"
    assert meta["colors"]["watermark"]["text"] == "FILED"

    # Geometry
    assert meta["geometry"]["page_width_pt"] == 595.28
    assert meta["geometry"]["page_height_pt"] == 841.89
    assert meta["geometry"]["usable_width_pt"] == 538.57


def test_gst_pdf_metadata_attributes(tmp_path):
    """Verify generated PDF file contains creator and title metadata."""
    out_pdf = str(tmp_path / "meta_test.pdf")
    generate_gstr3b_pdf(out_pdf)
    doc = pymupdf.open(out_pdf)
    meta = doc.metadata
    assert meta.get("creator") == "pdfmake"
    assert meta.get("producer") == "pdfmake"
    assert "GSTR3B" in meta.get("title", "")
    doc.close()


def test_gst_prompt_api(client):
    """Test GET and POST /api/gst/prompt returns authoritative Form GSTR-3B layout prompt."""
    response = client.get("/api/gst/prompt")
    assert response.status_code == 200
    res = json.loads(response.data)
    assert res["status"] == "success"
    prompt = res["prompt"]
    assert "FORM GSTR-3B" in prompt
    assert "595.28 pt" in prompt
    assert "#fde8d7" in prompt
    assert "Roboto-Medium" in prompt
    assert "FILED" in prompt


