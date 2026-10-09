"""
Test Suite for Template Fingerprinting, Matching, and Regression Diffing.

Tests:
1. Matching the same template on a different customer's statement works with high similarity score.
2. An unrelated PDF (e.g., resume or presentation slide) returns 'unknown' (is_match=False).
3. A deliberately altered column width is reported as a diff with numeric delta and classified as 'possible extraction regression'.
4. A structural change (e.g. column added/removed or large table jump) is classified as 'new template version'.
5. L5 Editor model integration: verify matched_template, similarity_score, and diffs list are present in EditorPageModel.
6. Corpus regression verification across all bank statement templates in uploads/.
"""

import os
import copy
import json
import pytest
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from pdf_analyzer.fingerprint import (
    TemplateFingerprint,
    CoarseGeometryHash,
    DiffRecord,
    TemplateMatchResult,
    match_template,
    load_all_fingerprints,
    diff_spec_against_prior,
    _generate_standard_fingerprints,
)
from pdf_analyzer.editor_model import create_default_editor_model


def make_customer_a_kotak_pdf(path: str):
    """Customer A: John Doe with specific dates & account number."""
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 780, "Kotak Mahindra Bank")
    c.setFont("Helvetica", 10)
    c.drawString(50, 760, "Account Statement")
    c.drawString(50, 745, "Customer: Johnathan Doe | CRN: 987654321")
    c.drawString(50, 730, "Account No: 0123456789 | IFSC Code: KKBK0001234")
    c.drawString(50, 715, "Branch: Mumbai Nariman Point | Status: Active")
    
    # Table Header
    c.setFillColor(colors.HexColor("#EEEEEE"))
    c.rect(44, 650, 507, 25, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 658, "Date")
    c.drawString(110, 658, "Narration")
    c.drawString(280, 658, "Chq / Ref No")
    c.drawString(370, 658, "Withdrawal (Dr)")
    c.drawString(450, 658, "Deposit (Cr)")
    c.drawString(510, 658, "Balance")
    
    # Transaction
    c.setFont("Helvetica", 8)
    c.drawString(50, 630, "15/01/2026")
    c.drawString(110, 630, "UPI/Payment to Vendor A")
    c.drawString(280, 630, "REF998811")
    c.drawString(370, 630, "1,500.00")
    c.drawString(450, 630, "-")
    c.drawString(510, 630, "45,000.00")
    
    c.showPage()
    c.save()


def make_customer_b_kotak_pdf(path: str):
    """Customer B: Jane Smith with completely different personal details & transactions."""
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 780, "Kotak Mahindra Bank")
    c.setFont("Helvetica", 10)
    c.drawString(50, 760, "Account Statement")
    c.drawString(50, 745, "Customer: Jane Smith | CRN: 112233445")
    c.drawString(50, 730, "Account No: 9988776655 | IFSC Code: KKBK0005678")
    c.drawString(50, 715, "Branch: Bengaluru MG Road | Status: Active")
    
    # Table Header (same anchor structure)
    c.setFillColor(colors.HexColor("#EEEEEE"))
    c.rect(44, 650, 507, 25, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 658, "Date")
    c.drawString(110, 658, "Narration")
    c.drawString(280, 658, "Chq / Ref No")
    c.drawString(370, 658, "Withdrawal (Dr)")
    c.drawString(450, 658, "Deposit (Cr)")
    c.drawString(510, 658, "Balance")
    
    # Transaction
    c.setFont("Helvetica", 8)
    c.drawString(50, 630, "28/02/2026")
    c.drawString(110, 630, "Salary Credit from TechCorp")
    c.drawString(280, 630, "SAL202602")
    c.drawString(370, 630, "-")
    c.drawString(450, 630, "120,000.00")
    c.drawString(510, 630, "185,000.00")
    
    c.showPage()
    c.save()


def make_unrelated_recipe_pdf(path: str):
    """An unrelated PDF document (Recipe / Cooking guide) with no banking anchors."""
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 750, "Authentic Neapolitan Pizza Recipe")
    c.setFont("Helvetica", 11)
    c.drawString(50, 720, "Ingredients:")
    c.drawString(70, 700, "1. 500g Tipo 00 Flour")
    c.drawString(70, 680, "2. 325ml Luke-warm Water")
    c.drawString(70, 660, "3. 10g Fine Sea Salt")
    c.drawString(70, 640, "4. 3g Active Dry Yeast")
    c.drawString(50, 600, "Instructions:")
    c.drawString(70, 580, "Dissolve yeast in water, mix flour, knead for 10 minutes.")
    c.drawString(70, 560, "Let ferment for 24 hours at room temperature.")
    c.showPage()
    c.save()


def test_matching_same_template_different_customers(tmp_path):
    """Test 1: Matching the same template on a different customer's statement works."""
    pdf_a = str(tmp_path / "kotak_cust_a.pdf")
    pdf_b = str(tmp_path / "kotak_cust_b.pdf")
    
    make_customer_a_kotak_pdf(pdf_a)
    make_customer_b_kotak_pdf(pdf_b)
    
    match_a = match_template(pdf_a)
    match_b = match_template(pdf_b)
    
    assert match_a.is_match is True
    assert match_a.template_id == "kotak_mahindra_filled_header"
    assert match_a.similarity_score >= 0.80
    
    assert match_b.is_match is True
    assert match_b.template_id == "kotak_mahindra_filled_header"
    assert match_b.similarity_score >= 0.80


def test_unrelated_pdf_returns_unknown(tmp_path):
    """Test 2: An unrelated PDF returns 'unknown' and is_match=False."""
    pdf_unrelated = str(tmp_path / "recipe.pdf")
    make_unrelated_recipe_pdf(pdf_unrelated)
    
    match_res = match_template(pdf_unrelated)
    
    assert match_res.is_match is False
    assert match_res.template_id == "unknown"
    assert match_res.similarity_score < 0.50
    assert len(match_res.diffs) == 0


def test_deliberately_altered_column_width_reported_as_regression():
    """Test 3: Deliberately altered column width is reported as possible extraction regression."""
    prior_spec = {
        "meta": {"width_pt": 595.0, "height_pt": 842.0},
        "table": {
            "columns": [
                {"header_text": "Date", "width": {"pt": 60.0}},
                {"header_text": "Narration", "width": {"pt": 180.0}},
                {"header_text": "Amount", "width": {"pt": 80.0}},
            ],
            "bbox": {"x0": {"pt": 40.0}, "y0": {"pt": 200.0}, "x1": {"pt": 555.0}, "y1": {"pt": 700.0}}
        },
        "margins_spacing": {"page_margins": {"left": {"pt": 40.0}, "right": {"pt": 40.0}, "top": {"pt": 50.0}, "bottom": {"pt": 50.0}}}
    }
    
    # Mutate column 1 width from 180.0 to 184.2 pt (4.2 pt drift)
    current_spec = copy.deepcopy(prior_spec)
    current_spec["table"]["columns"][1]["width"]["pt"] = 184.2
    
    diffs = diff_spec_against_prior(prior_spec, current_spec)
    
    assert len(diffs) == 1
    diff = diffs[0]
    assert diff.property_name == "table.columns[1].width_pt"
    assert diff.prior_value == 180.0
    assert diff.current_value == 184.2
    assert diff.delta_pt == pytest.approx(4.2, abs=0.01)
    assert diff.classification == "possible extraction regression"
    assert "drifted by 4.20 pt" in diff.reason


def test_structural_change_reported_as_new_template_version():
    """Test 4: Structural changes (column count or large table shift) classified as new template version."""
    prior_spec = {
        "table": {
            "columns": [
                {"header_text": "Date", "width_pt": 60.0},
                {"header_text": "Narration", "width_pt": 180.0},
                {"header_text": "Amount", "width_pt": 80.0},
            ],
            "bbox": {"x0": {"pt": 40.0}, "y0": {"pt": 200.0}, "x1": {"pt": 555.0}, "y1": {"pt": 700.0}}
        }
    }
    
    # Case A: Column removed
    mutated_spec_col = copy.deepcopy(prior_spec)
    mutated_spec_col["table"]["columns"].pop()
    diffs_col = diff_spec_against_prior(prior_spec, mutated_spec_col)
    
    assert len(diffs_col) >= 1
    assert any(d.classification == "new template version" and "Column count changed" in d.reason for d in diffs_col)
    
    # Case B: Large table position shift (> 20 pt)
    mutated_spec_shift = copy.deepcopy(prior_spec)
    mutated_spec_shift["table"]["bbox"]["y0"]["pt"] = 235.0  # +35 pt shift
    diffs_shift = diff_spec_against_prior(prior_spec, mutated_spec_shift)
    
    assert any(d.classification == "new template version" and d.delta_pt == 35.0 for d in diffs_shift)


def test_l5_editor_model_contains_template_match(tmp_path):
    """Test 5: L5 Editor model contains matched template name, similarity score, and diffs list."""
    pdf_file = str(tmp_path / "sample_kotak.pdf")
    make_customer_a_kotak_pdf(pdf_file)
    
    spec = {
        "pages": [{"width_pt": 595.0, "height_pt": 842.0}],
        "table": {"bbox_pt": [44.0, 310.0, 551.0, 770.0]}
    }
    
    editor_model = create_default_editor_model(spec, page_number=1, pdf_path=pdf_file)
    
    assert "template_match" in editor_model
    t_match = editor_model["template_match"]
    assert isinstance(t_match, dict)
    assert t_match["template_id"] == "kotak_mahindra_filled_header"
    assert t_match["similarity_score"] >= 0.80
    assert "diffs" in t_match
    assert isinstance(t_match["diffs"], list)


def test_corpus_template_fingerprint_matching():
    """Test 6: Real corpus statements in uploads/ match their respective fingerprints."""
    manifest_p = "tests/corpus/manifest.json"
    if not os.path.exists(manifest_p):
        pytest.skip("Manifest not found")
        
    with open(manifest_p, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    for entry in manifest:
        pdf_p = entry.get("file", "")
        if not os.path.exists(pdf_p):
            continue
            
        bank = entry.get("bank", "None")
        has_table = entry.get("has_table", False)
        
        match_res = match_template(pdf_p)
        
        if not has_table or bank == "None":
            # Non-banking or non-table documents should return unknown
            assert match_res.is_match is False or match_res.similarity_score < 0.50
        else:
            # Banking statements should match their respective fingerprint
            assert match_res.is_match is True
            assert match_res.similarity_score >= 0.50
            if "State Bank" in bank:
                assert "state_bank_of_india" in match_res.template_id
            elif "Kotak" in bank:
                assert "kotak_mahindra" in match_res.template_id
            elif "Bank of India" in bank:
                assert "bank_of_india" in match_res.template_id
            elif "Union Bank" in bank:
                assert "union_bank_of_india" in match_res.template_id

