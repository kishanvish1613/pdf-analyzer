"""
Tests for PII Detection, Same-Width Redaction, Synthetic Data Substitution,
AI Prompt Privacy Controls, and Exporter Protection.
"""

import os
import io
import json
import pytest
import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from pdf_analyzer.privacy import (
    PIIDetector,
    RedactionEngine,
    SyntheticDataEngine,
    PrivacyEngine,
    apply_privacy_transform,
    apply_privacy_to_editor_model,
    redact_string_with_same_width
)
from pdf_analyzer.dimensions_export import generate_ai_prompt, export_dimensions
from pdf_analyzer.pipeline import AnalysisPipeline, AnalyzerConfig
from tools.roundtrip.exporters.reportlab_exporter import generate_reportlab_pdf
from tools.roundtrip.exporters.weasyprint_exporter import generate_weasyprint_html, generate_weasyprint_pdf


def test_pii_detector_categories():
    """Verifies that PIIDetector identifies names, account numbers, addresses, phones, and emails."""
    detector = PIIDetector()

    # 1. Email and UPI
    matches_email = detector.detect_in_text("Please contact customer at john.doe@fintechcorp.com or upi handle user99@okaxis")
    categories = [m.category for m in matches_email]
    assert "EMAIL" in categories
    assert any(m.original_text == "john.doe@fintechcorp.com" for m in matches_email)

    # 2. Phone Numbers
    matches_phone = detector.detect_in_text("Mobile: +91 9876543210 or office landline 022-28491029")
    phone_matches = [m for m in matches_phone if m.category == "PHONE"]
    assert len(phone_matches) >= 1

    # 3. Account Number / PAN / IFSC
    matches_acct = detector.detect_in_text("A/C No: 50200012345678, PAN: ABCDE1234F, IFSC: HDFC0000001")
    acct_matches = [m for m in matches_acct if m.category == "ACCOUNT_NUMBER"]
    assert len(acct_matches) >= 2

    # 4. Contextual detection
    m_name = detector.detect_in_text("ROHIT SHARMA", field_context="Customer Name")
    assert len(m_name) == 1 and m_name[0].category == "NAME"

    m_addr = detector.detect_in_text("FLAT 402, SUNSHINE HEIGHTS, ANDHERI WEST, MUMBAI 400058", field_context="Customer Address")
    assert len(m_addr) == 1 and m_addr[0].category == "ADDRESS"


def test_same_width_redaction_precision():
    """Verifies same-width redaction preserves character advance width and layout geometry."""
    orig_str = "MR. JOHNATHAN DOE"
    red_str, parity = redact_string_with_same_width(orig_str, font_name="Helvetica", font_size_pt=10.0)

    # Replaces letters with X, preserves space/punctuation
    assert red_str == "XX. XXXXXXXXX XOX" or (red_str.startswith("XX.") and len(red_str) == len(orig_str))
    assert len(red_str) == len(orig_str)
    # Width delta is bounded
    assert parity["width_delta_pt"] is not None
    assert parity["width_delta_pt"] < 35.0


def test_synthetic_data_substitution():
    """Verifies realistic synthetic data generation for financial entities."""
    synth = SyntheticDataEngine(seed=123)

    # Name
    s_name, _ = synth.substitute_text("M/S ABC ENTERPRISES PVT LTD", category="NAME")
    assert s_name != "M/S ABC ENTERPRISES PVT LTD"
    assert len(s_name) > 3

    # Account Number
    s_acct, _ = synth.substitute_text("50200098765432", category="ACCOUNT_NUMBER")
    assert s_acct != "50200098765432"
    assert len(s_acct) == len("50200098765432")

    # Date
    s_date, _ = synth.substitute_text("15/03/2025", category="DATE")
    assert s_date != "15/03/2025"
    assert len(s_date) == 10 and "/" in s_date

    # Amount
    s_amt, _ = synth.substitute_text("$1,250.00", category="AMOUNT")
    assert "$" in s_amt and "." in s_amt


def test_ai_prompt_privacy_controls():
    """Verifies that 'Copy AI PDF Generator Prompt' defaults to synthetic data with safety warnings."""
    sensitive_model = {
        "document_name": "confidential_statement.pdf",
        "page_number": 1,
        "width_pt": 612.0,
        "height_pt": 792.0,
        "table_bbox": {"x0_pt": 36.0, "y0_pt": 200.0, "width_pt": 540.0, "height_pt": 400.0},
        "boxes": [
            {
                "id": "customer_box",
                "type": "header_block",
                "title": "Customer Card",
                "text_lines": [
                    "MR. SECRET CUSTOMER",
                    "TOP SECRET RESIDENCE, SECTOR 99",
                    "NEW DELHI 110099"
                ]
            },
            {
                "id": "kv_box",
                "type": "header_block",
                "title": "Account Info",
                "kv_entries": [
                    {"key": "Customer Name", "value": "SECRET CUSTOMER"},
                    {"key": "Account No", "value": "999988887777"},
                    {"key": "Phone", "value": "+91 9999988888"}
                ]
            }
        ],
        "columns": [
            {"column_index": 1, "header_text": "Date", "width_pt": 60.0},
            {"column_index": 2, "header_text": "Description", "width_pt": 200.0},
            {"column_index": 3, "header_text": "Amount", "width_pt": 80.0}
        ],
        "rows": []
    }

    # 1. Default (Synthetic Mode)
    prompt_default = generate_ai_prompt(sensitive_model)
    assert "PRIVACY PROTECTED (SYNTHETIC DATA MODE" in prompt_default
    assert "SECRET CUSTOMER" not in prompt_default
    assert "999988887777" not in prompt_default
    assert "+91 9999988888" not in prompt_default

    # 2. Redacted Mode
    prompt_redacted = generate_ai_prompt(sensitive_model, privacy_mode="redacted")
    assert "PRIVACY PROTECTED (REDACTED MODE)" in prompt_redacted
    assert "SECRET CUSTOMER" not in prompt_redacted
    assert "999988887777" not in prompt_redacted

    # 3. Real Mode (Requires explicit toggle, includes visible warning banner)
    prompt_real = generate_ai_prompt(sensitive_model, privacy_mode="real")
    assert "CAUTION: REAL CUSTOMER DATA INCLUDED" in prompt_real
    assert "SECRET CUSTOMER" in prompt_real
    assert "999988887777" in prompt_real


def test_redacted_pdf_roundtrip_and_non_exposure(tmp_path):
    """
    Creates a synthetic PDF with customer PII, runs pipeline, applies redaction,
    generates PDF via ReportLab & WeasyPrint, and asserts zero PII exposure.
    """
    pdf_path = str(tmp_path / "sensitive_statement.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter

    # Draw Sensitive Content
    c.setFont("Helvetica-Bold", 14)
    c.drawString(36, h - 50, "FIRST NATIONAL PRIVATE BANK")
    c.setFont("Helvetica", 9)
    c.drawString(36, h - 80, "Customer: MR. ALEXANDER VIP CUSTOMER")
    c.drawString(36, h - 95, "Account: 4092-8172-9104-5555")
    c.drawString(36, h - 110, "Email: alexander.vip@confidentialmail.com")

    # Table
    c.rect(36, h - 250, w - 72, 100, fill=0, stroke=1)
    c.drawString(45, h - 170, "Date")
    c.drawString(120, h - 170, "Narration")
    c.drawString(400, h - 170, "Amount")

    c.drawString(45, h - 190, "15/01/2026")
    c.drawString(120, h - 190, "UPI-SECRET RECIPIENT-TRANSFER TO VIP")
    c.drawString(400, h - 190, "$9,999.00")

    c.save()
    assert os.path.exists(pdf_path)

    # Run Analysis Pipeline
    out_dir = str(tmp_path / "out_sensitive")
    cfg = AnalyzerConfig(output_dir=out_dir, dpi=150, include_visual_overlays=False)
    pipeline = AnalysisPipeline(cfg)
    spec = pipeline.process_document(pdf_path, output_dir=out_dir, page_number=1)

    # 1. Apply Redaction Transform
    red_spec, pii_report = apply_privacy_transform(spec, mode="redacted")
    assert pii_report.total_detected >= 3
    assert "ACCOUNT_NUMBER" in pii_report.categories or "NAME" in pii_report.categories

    # Export Redacted PDF with ReportLab
    rl_red_pdf = str(tmp_path / "redacted_reportlab.pdf")
    generate_reportlab_pdf(red_spec, rl_red_pdf)
    assert os.path.exists(rl_red_pdf)

    # Inspect generated PDF text: Ensure NO original sensitive strings appear
    doc = pymupdf.open(rl_red_pdf)
    page_text = doc[0].get_text()
    doc.close()

    assert "ALEXANDER VIP CUSTOMER" not in page_text
    assert "4092-8172-9104-5555" not in page_text
    assert "alexander.vip@confidentialmail.com" not in page_text

    # Export Synthetic PDF with WeasyPrint Exporter
    synth_spec, _ = apply_privacy_transform(spec, mode="synthetic")
    wp_html = str(tmp_path / "synthetic_weasyprint.html")
    generate_weasyprint_html(synth_spec, wp_html)
    assert os.path.exists(wp_html)

    with open(wp_html, "r", encoding="utf-8") as f:
        html_content = f.read()

    assert "ALEXANDER VIP CUSTOMER" not in html_content
    assert "4092-8172-9104-5555" not in html_content
    assert "alexander.vip@confidentialmail.com" not in html_content


def test_privacy_rest_api_endpoints():
    """Verifies that Flask API endpoints for dimensions and PII report handle privacy modes correctly."""
    from app import app
    client = app.test_client()

    sample_model = {
        "document_name": "test_statement.pdf",
        "page_number": 1,
        "width_pt": 612.0,
        "height_pt": 792.0,
        "boxes": [
            {
                "id": "box_1",
                "type": "header_block",
                "text_lines": ["MS. PRIYA SHARMA", "ACCOUNT: 502000889900", "PRIYA@EXAMPLE.COM"]
            }
        ],
        "columns": [{"column_index": 1, "header_text": "Amount", "width_pt": 100.0}],
        "rows": []
    }

    # 1. PII Report endpoint
    res_pii = client.post("/api/editor/sample/pii-report", json={
        "editor_model": sample_model,
        "privacy_mode": "synthetic"
    })
    assert res_pii.status_code == 200
    data_pii = res_pii.get_json()
    assert data_pii["status"] == "success"
    assert data_pii["report"]["total_detected"] >= 2

    # 2. Dimensions Export with default synthetic mode
    res_dim_synth = client.post("/api/editor/sample/dimensions", json={
        "editor_model": sample_model,
        "format": "ai_prompt",
        "privacy_mode": "synthetic"
    })
    assert res_dim_synth.status_code == 200
    text_synth = res_dim_synth.get_json()["text"]
    assert "PRIVACY PROTECTED (SYNTHETIC DATA MODE" in text_synth
    assert "PRIYA SHARMA" not in text_synth

    # 3. Dimensions Export with real mode
    res_dim_real = client.post("/api/editor/sample/dimensions", json={
        "editor_model": sample_model,
        "format": "ai_prompt",
        "privacy_mode": "real"
    })
    assert res_dim_real.status_code == 200
    text_real = res_dim_real.get_json()["text"]
    assert "CAUTION: REAL CUSTOMER DATA INCLUDED" in text_real
    assert "PRIYA SHARMA" in text_real

