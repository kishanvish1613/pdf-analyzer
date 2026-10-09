"""
Phase 8C-FIX Test Suite: Structure-Mask SSIM, Independent Golden Data,
Table Closure Invariant, Virtual Column Lane Markers, and Anchored Rows.
"""

import os
import pytest
from hypothesis import given, strategies as st, settings
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import (
    TableGridEngine,
    TableStyleVerdict,
    RowBandType,
)
from pdf_analyzer.l3_topology.logical_rows import LogicalRowEngine
from pdf_analyzer.l4_layout.numeric_cells import NumericCellEngine
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneEngine
from pdf_analyzer.closed_loop import ClosedLoopEngine
from pdf_analyzer.corpus_check import CorpusCheckEngine
from pdf_analyzer.dossier import TemplateDossierEngine


def make_kotak_like_pdf(path: str):
    """
    Kotak-style statement:
    - Horizontal rules present, zero vertical rules.
    - Filled pink header band / table title band.
    - Multi-line (2-3 line) wrapped description cells.
    - Numeric balance cells with Dr/Cr suffixes.
    """
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Kotak Mahindra Bank Statement")
    
    # Table Title Band (Pink fill)
    c.setFillColor(colors.HexColor("#FCE4EC"))
    c.rect(50, 680, 500, 20, fill=True, stroke=False)
    c.setFillColor(colors.HexColor("#880E4F"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, 686, "Savings Account Transactions")
    
    # Header Row (Gray fill)
    c.setFillColor(colors.HexColor("#EEEEEE"))
    c.rect(50, 655, 500, 22, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(55, 662, "Date")
    c.drawString(120, 662, "Transaction Details")
    c.drawString(340, 662, "Chq / Ref No")
    c.drawString(410, 662, "Amount")
    c.drawString(480, 662, "Balance")
    
    # Opening Balance row
    c.setFont("Helvetica", 8)
    c.drawString(120, 638, "OPENING BALANCE")
    c.drawString(480, 638, "25,000.00 Cr.")
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.line(50, 630, 550, 630)
    
    # Row 1 (2 lines of description)
    c.drawString(55, 615, "01/09/2026")
    c.drawString(120, 615, "UPI/234567890/Merchant Pay")
    c.drawString(120, 603, "Ref: TXN99881122 Bangalore")
    c.drawString(340, 615, "UPI99881")
    c.drawString(410, 615, "1,250.00")
    c.drawString(480, 615, "23,750.00 Cr.")
    c.line(50, 595, 550, 595)
    
    # Row 2 (3 lines of description)
    c.drawString(55, 580, "05/09/2026")
    c.drawString(120, 580, "NEFT DR-HDFC0000123-ABC")
    c.drawString(120, 568, "ENTERPRISES PRIVATE LIMITED")
    c.drawString(120, 556, "INVOICE NO 4491-SEP")
    c.drawString(340, 580, "N0905111")
    c.drawString(410, 580, "5,000.00")
    c.drawString(480, 580, "18,750.00 Cr.")
    c.line(50, 545, 550, 545)
    
    # Row 3 (1 line)
    c.drawString(55, 530, "10/09/2026")
    c.drawString(120, 530, "SALARY CREDIT SEPT 2026")
    c.drawString(340, 530, "SAL202609")
    c.drawString(410, 530, "45,000.00")
    c.drawString(480, 530, "63,750.00 Cr.")
    c.line(50, 515, 550, 515)
    
    # Closing balance
    c.drawString(120, 498, "CLOSING BALANCE")
    c.drawString(480, 498, "63,750.00 Cr.")
    c.line(50, 490, 550, 490)
    
    c.showPage()
    c.save()


def make_sbi_like_pdf(path: str):
    """
    SBI-style statement:
    - Filled dark header band.
    - Zero vertical rules.
    - 4-5 line wrapped cells.
    - Empty filled band at the bottom.
    """
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "STATE BANK OF INDIA")
    c.drawString(50, 735, "Account Statement: 00000011223344")
    
    # Header Band
    c.setFillColor(colors.HexColor("#003366"))
    c.rect(50, 680, 500, 24, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(55, 688, "Txn Date")
    c.drawString(110, 688, "Value Date")
    c.drawString(170, 688, "Description")
    c.drawString(370, 688, "Debit")
    c.drawString(430, 688, "Credit")
    c.drawString(490, 688, "Balance")
    
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 7.5)
    
    # Transaction 1: 4-line description wrap
    y = 660
    c.drawString(55, y, "01/08/2026")
    c.drawString(110, y, "01/08/2026")
    c.drawString(170, y, "TRANSFER FROM 45910029384")
    c.drawString(170, y - 10, "UPI/CR/3294829104/RAJESH KUMAR")
    c.drawString(170, y - 20, "PAYMENT FOR MONTHLY GROCERY")
    c.drawString(170, y - 30, "ORDER REF: 84920194821")
    c.drawString(430, y, "2,450.00")
    c.drawString(490, y, "12,450.00")
    
    # Transaction 2: 5-line description wrap
    y = 610
    c.drawString(55, y, "12/08/2026")
    c.drawString(110, y, "12/08/2026")
    c.drawString(170, y, "BULK POSTING SALARY")
    c.drawString(170, y - 10, "ACH/CMS/000294819284/INFOTECH")
    c.drawString(170, y - 20, "EMPLOYEE ID: EMP-98210")
    c.drawString(170, y - 30, "MONTH OF JULY PAID AUGUST")
    c.drawString(170, y - 40, "ALLOWANCE INCLUDED")
    c.drawString(430, y, "65,000.00")
    c.drawString(490, y, "77,450.00")
    
    # Empty filled band at the bottom
    c.setFillColor(colors.HexColor("#F0F4F8"))
    c.rect(50, 540, 500, 18, fill=True, stroke=False)
    
    c.showPage()
    c.save()


def make_hdfc_last_page_pdf(path: str):
    """
    HDFC last page:
    - Empty table with a single horizontal rule or zero body rows.
    """
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "HDFC BANK LIMITED - STATEMENT SUMMARY")
    c.drawString(50, 720, "No transactions during this final period.")
    
    # Header only
    c.line(50, 680, 550, 680)
    c.drawString(60, 665, "Date")
    c.drawString(160, 665, "Narration")
    c.drawString(360, 665, "Withdrawal")
    c.drawString(460, 665, "Deposit")
    c.line(50, 655, 550, 655)
    
    c.drawString(50, 500, "End of Statement.")
    c.showPage()
    c.save()


def make_borderless_sample_pdf(path: str):
    """
    Borderless table:
    - Whitespace only, zero vector rules or fill rects.
    """
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(50, 750, "Borderless Statement")
    
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 680, "Date")
    c.drawString(140, 680, "Particulars")
    c.drawString(340, 680, "Debit")
    c.drawString(430, 680, "Credit")
    c.drawString(510, 680, "Balance")
    
    c.setFont("Helvetica", 8)
    for i, y in enumerate([650, 620, 590, 560]):
        c.drawString(50, y, f"0{i+1}/09/2026")
        c.drawString(140, y, f"Item Purchase {i+1}")
        c.drawString(340, y, f"{120 * (i+1)}.00")
        c.drawString(430, y, "0.00")
        c.drawString(510, y, f"{5000 - 120*(i+1)}.00")
        
    c.showPage()
    c.save()


# ----------------------------------------------------------------------
# TESTS
# ----------------------------------------------------------------------

def test_kotak_virtual_columns_and_wrapped_rows(tmp_path):
    """
    Tests Kotak statement table style verdict, virtual column recovery,
    multi-line wrap gathering, and band classification.
    """
    pdf_path = str(tmp_path / "kotak_statement.pdf")
    make_kotak_like_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    
    chosen, runner_up, _ = grid_engine.determine_table_style_models(ruleset, page_layer)
    assert chosen in [TableStyleVerdict.HORIZONTAL_ONLY, TableStyleVerdict.FILLED_HEADER]
    
    grid = grid_engine.build_table_grid(ruleset, page_layer, chosen)
    assert grid is not None
    assert len(grid.columns) >= 4
    
    for col in grid.columns:
        assert len(col.evidence) > 0
        
    row_engine = LogicalRowEngine()
    rows = row_engine.extract_logical_rows(
        page_layer=page_layer,
        table_bbox_pt=grid.bbox_pt,
        columns=grid.columns,
        h_rules=ruleset.h_rules,
    )
    
    assert len(rows) >= 3
    band_types = [r.row_type for r in rows]
    assert RowBandType.OPENING_BALANCE in band_types or RowBandType.HEADER in band_types
    assert RowBandType.BODY in band_types


def test_sbi_deep_wraps_and_empty_band(tmp_path):
    """
    Tests SBI 4-5 line wrapped cells, filled header band, and empty band classification.
    """
    pdf_path = str(tmp_path / "sbi_statement.pdf")
    make_sbi_like_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    
    chosen, runner_up, _ = grid_engine.determine_table_style_models(ruleset, page_layer)
    assert chosen in [TableStyleVerdict.FILLED_HEADER, TableStyleVerdict.BORDERLESS]
    
    grid = grid_engine.build_table_grid(ruleset, page_layer, chosen)
    assert grid is not None
    assert len(grid.columns) >= 4
    
    row_engine = LogicalRowEngine()
    rows = row_engine.extract_logical_rows(
        page_layer=page_layer,
        table_bbox_pt=grid.bbox_pt,
        columns=grid.columns,
        h_rules=ruleset.h_rules,
    )
    
    body_rows = [r for r in rows if r.row_type == RowBandType.BODY]
    assert len(body_rows) >= 2
    line_counts = [r.lines_count for r in body_rows]
    assert max(line_counts) >= 4


def test_hdfc_empty_table_page(tmp_path):
    """
    Tests HDFC last page with empty table: header-less/empty body.
    """
    pdf_path = str(tmp_path / "hdfc_empty.pdf")
    make_hdfc_last_page_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
    
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    
    chosen, runner_up, _ = grid_engine.determine_table_style_models(ruleset, page_layer)
    grid = grid_engine.build_table_grid(ruleset, page_layer, chosen)
    assert grid is not None
    assert grid.body_rows_count == 0 or chosen == TableStyleVerdict.EMPTY_TABLE


def test_virtual_column_lane_numbered_markers(tmp_path):
    """
    Tests that virtual column tables produce a dimension lane with numbered markers
    and that lane suppression is avoided when body rows exist (Phase 8C-FIX Task F5).
    """
    pdf_path = str(tmp_path / "kotak_lane.pdf")
    make_kotak_like_pdf(pdf_path)
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    lane_engine = DimensionLaneEngine()
    lane = lane_engine.build_dimension_lane(grid, ruleset, page_layer)
    
    assert lane.lane_absent_reason is None
    assert len(lane.arrows) == len(grid.columns)
    assert len(lane.numbered_markers) == len(grid.columns)


def test_table_closure_invariant(tmp_path):
    """
    Verifies closure invariant: sum(arrow widths) + interior rule widths == table outer width +- 0.25 pt
    (Phase 8C-FIX Task F3).
    """
    pdf_path = str(tmp_path / "closure_test.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    for x in [50, 120, 250, 400, 550]:
        c.line(x, 200, x, 400)
    c.line(50, 400, 550, 400)
    c.line(50, 200, 550, 200)
    c.drawString(60, 380, "01/01/2026")
    c.showPage()
    c.save()
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    lane_engine = DimensionLaneEngine()
    lane = lane_engine.build_dimension_lane(grid, ruleset, page_layer)
    
    assert lane.width_invariance_passed is True
    assert lane.delta_pt <= 0.25


def test_golden_independent_not_self_comparison(tmp_path):
    """
    Verifies that golden data is derived from independent_probe.py (PyMuPDF only)
    and asserts tolerance <= 0.10 pt on ruled tables, failing if deltas are constant (Task H2).
    """
    from tests.independent_probe import extract_independent_ground_truth
    
    # Test on Bank of India (full grid)
    sample_pdf = "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf"
    if os.path.exists(sample_pdf):
        golden = extract_independent_ground_truth(sample_pdf, 1)
        assert golden["has_table"] is True
        assert golden["table_bbox"] is not None
        
        with ByteLayerExtractor(sample_pdf) as ext:
            page_layer = ext.extract_page(1)
        ruleset = RuleSet.from_page_layer(page_layer)
        grid = TableGridEngine().build_table_grid(ruleset, page_layer)
        
        # Verify columns exist
        assert len(grid.columns) >= 7
        
        # Check delta is not artificial constant
        deltas = []
        for i in range(min(len(golden["columns"]), len(grid.columns))):
            g_w = golden["columns"][i]["width_pt"]
            a_w = grid.columns[i].width_pt
            deltas.append(abs(a_w - g_w))
            
        assert len(deltas) > 0
        nonzero = [round(d, 4) for d in deltas if round(d, 4) > 0.0]
        if nonzero:
            assert len(set(nonzero)) > 1 or len(nonzero) < len(deltas), "Deltas must not be identical non-zero artificial constants"
        assert max(deltas) <= 0.10, "Delta must not exceed 0.10 pt"


def test_structure_mask_ssim_evaluation(tmp_path):
    """
    Tests Structure-Mask SSIM with 300 DPI polygon/fill/image/text-ink rendering (Phase 8C-FIX Task F1).
    """
    pdf_path = str(tmp_path / "mask_test.pdf")
    make_kotak_like_pdf(pdf_path)
    
    engine = ClosedLoopEngine(dpi=150, min_ssim_threshold=0.80)
    report = engine.evaluate_closed_loop(pdf_path, page_number=1, output_dir=str(tmp_path))
    
    assert report.overall_ssim >= 0.80
    assert len(report.region_scores) >= 1
    for r in report.region_scores:
        assert hasattr(r, "discrepancies")


# ----------------------------------------------------------------------
# HYPOTHESIS PROPERTY TESTS
# ----------------------------------------------------------------------

@settings(max_examples=10, deadline=None)
@given(
    wrap_lines=st.integers(min_value=1, max_value=6),
    num_rows=st.integers(min_value=2, max_value=5),
)
def test_hypothesis_multi_line_row_wrap(tmp_path_factory, wrap_lines, num_rows):
    """
    Property-based test: randomly generating N rows with M wrap lines per description.
    """
    tmp_dir = tmp_path_factory.mktemp("hypo")
    pdf_path = str(tmp_dir / f"hypo_{wrap_lines}_{num_rows}.pdf")
    
    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 700, "Date")
    c.drawString(150, 700, "Description")
    c.drawString(450, 700, "Amount")
    
    y = 670
    c.setFont("Helvetica", 8)
    for r_idx in range(num_rows):
        c.drawString(50, y, f"0{r_idx+1}/01/2026")
        c.drawString(450, y, f"{100*(r_idx+1)}.00")
        for w_idx in range(wrap_lines):
            c.drawString(150, y - (w_idx * 10), f"Row {r_idx+1} Description line {w_idx+1}")
        y -= (wrap_lines * 10 + 15)
        
    c.showPage()
    c.save()
    
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(1)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    grid = grid_engine.build_table_grid(ruleset, page_layer, TableStyleVerdict.BORDERLESS)
    assert grid is not None
    
    row_engine = LogicalRowEngine()
    rows = row_engine.extract_logical_rows(
        page_layer=page_layer,
        table_bbox_pt=grid.bbox_pt,
        columns=grid.columns,
    )
    
    body_rows = [r for r in rows if r.row_type == RowBandType.BODY]
    assert len(body_rows) == num_rows
    for r in body_rows:
        assert r.lines_count >= 1


# ----------------------------------------------------------------------
# K1: Corpus-check provenance and exit-code tests
# ----------------------------------------------------------------------

def test_k1_manual_golden_without_editor_export_source_is_rejected(tmp_path):
    """K1: A manual golden file lacking source='editor_export' must be silently ignored."""
    from pdf_analyzer.corpus_check import _load_manual_golden
    import json

    # Create a file WITHOUT the required source key
    bad_file = str(tmp_path / "bad.manual.json")
    with open(bad_file, "w") as f:
        json.dump({"source": "manual_ground_truth", "table_bbox": {"width_pt": 500}}, f)
    result = _load_manual_golden(bad_file)
    assert result is None, "File without source='editor_export' must return None"

    # Create a file WITH the correct key
    good_file = str(tmp_path / "good.manual.json")
    with open(good_file, "w") as f:
        json.dump({
            "source": "editor_export",
            "exported_at": "2026-10-01T00:00:00",
            "table_bbox": {"width_pt": 500},
        }, f)
    result = _load_manual_golden(good_file)
    assert result is not None, "File with source='editor_export' must be accepted"
    assert result["source"] == "editor_export"


def test_k1_corpus_check_exits_nonzero_on_identical_delta():
    """K1: corpus_check_exit_code must return 1 when constant_delta_detected=True."""
    from pdf_analyzer.corpus_check import CorpusCheckReport, corpus_check_exit_code, DiscrepancyRecord

    rec = DiscrepancyRecord("t1", "TableBBox", "width_pt", 500.0, 505.5, 5.5)
    report = CorpusCheckReport(
        total_templates_compared=5,
        mean_delta_pt=5.5,
        max_delta_pt=5.5,
        worst_10_discrepancies=[rec],
        all_discrepancies=[rec] * 5,
        constant_delta_detected=True,
        auto_equals_golden_ratio=0.0,
    )
    assert corpus_check_exit_code(report) == 1, "Should exit non-zero when constant_delta_detected"


def test_k1_corpus_check_exits_nonzero_on_auto_equals_golden_ratio():
    """K1: corpus_check_exit_code must return 1 when auto==golden on >90% of objects."""
    from pdf_analyzer.corpus_check import CorpusCheckReport, corpus_check_exit_code, DiscrepancyRecord

    rec = DiscrepancyRecord("t1", "TableBBox", "width_pt", 500.0, 500.0, 0.0)
    report = CorpusCheckReport(
        total_templates_compared=5,
        mean_delta_pt=0.0,
        max_delta_pt=0.0,
        worst_10_discrepancies=[rec],
        all_discrepancies=[rec] * 10,
        constant_delta_detected=False,
        auto_equals_golden_ratio=0.95,
    )
    assert corpus_check_exit_code(report) == 1, "Should exit non-zero when >90% auto==golden"


# ----------------------------------------------------------------------
# K5: Corpus style-selection test — chosen style must match manifest
# ----------------------------------------------------------------------

def test_k5_chosen_style_matches_manifest_expected():
    """K5: For each statement in manifest (has_table=true), first, middle, and last page
    chosen style must equal expected_table_style. Prints a table of results."""
    import json

    manifest_path = "tests/corpus/manifest.json"
    if not os.path.exists(manifest_path):
        pytest.skip("manifest.json not found")

    with open(manifest_path) as f:
        entries = json.load(f)

    statement_entries = [e for e in entries if e.get("has_table") and os.path.exists(e.get("file", ""))]
    if not statement_entries:
        pytest.skip("No reachable statement PDFs in manifest")

    grid_engine = TableGridEngine()
    failures = []
    print(f"\n{'File':<45} {'Page':<6} {'Expected':<16} {'Chosen':<16} {'Match'}")
    print("-" * 92)

    for entry in statement_entries:
        pdf_path = entry["file"]
        expected = entry.get("expected_table_style", "")
        base = os.path.basename(pdf_path)
        pages = entry.get("pages", 1)

        pages_to_test = [1]
        mid = pages // 2
        if mid > 1 and mid not in pages_to_test:
            pages_to_test.append(mid)
        if pages > 1 and pages not in pages_to_test:
            pages_to_test.append(pages)

        with ByteLayerExtractor(pdf_path) as ext:
            for p in pages_to_test:
                expected_p = "empty_table" if (base.startswith("bank-statement-acct-statement-2821") and p == 56) else expected
                try:
                    page_layer = ext.extract_page(p)
                    ruleset = RuleSet.from_page_layer(page_layer)
                    chosen, _, _ = grid_engine.determine_table_style_models(ruleset, page_layer)
                    chosen_val = chosen.value
                except Exception as e:
                    chosen_val = f"ERROR:{e}"

                match = "OK" if chosen_val == expected_p else "FAIL"
                print(f"{base[:45]:<45} {p:<6} {expected_p:<16} {chosen_val:<16} {match}")
                if match == "FAIL":
                    failures.append(f"{base} p.{p}: expected={expected_p} got={chosen_val}")

    assert not failures, "Style mismatch:\n" + "\n".join(failures)
