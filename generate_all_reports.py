"""
Runner script to generate and save reports for all 5 statement pages.
"""

import os
import sys
import json
import pymupdf

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l1_crosscheck.audit import run_l1_audit, print_audit_terminal_report
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneEngine
from pdf_analyzer.dossier import TemplateDossierEngine
from pdf_analyzer.closed_loop import ClosedLoopEngine
from pdf_analyzer.corpus_check import CorpusCheckEngine, print_corpus_check_report


PDF_TARGETS = [
    ("hdfc_p1", "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf", 1),
    ("hdfc_p56", "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf", 56),  # 56-page HDFC statement; Page 56 is the empty table last page
    ("kotak", "uploads/AccountStatement_20-Sep-2026_20-Sep-2026.pdf", 1),
    ("sbi", "uploads/RAVIN18081966.pdf", 1),
    ("bank_of_india", "uploads/shivay orthocare feb 25 to jan 26.pdf", 1),
    ("union_bank", "uploads/bank-statement-optransactionhistoryux3-pdf11-06-2026-178160404281321470_.pdf", 1),
]


def run_target(name, pdf_path, page_num):
    out_dir = os.path.join("out", name)
    os.makedirs(out_dir, exist_ok=True)
    print(f"=== PROCESSING: {name} ({pdf_path} Page {page_num}) ===")

    # 1. Dossier
    dossier_engine = TemplateDossierEngine()
    dossier = dossier_engine.generate_dossier(pdf_path, page_number=page_num, output_dir=out_dir)
    md_content = dossier_engine.render_markdown_report(dossier)
    with open(os.path.join(out_dir, "dossier.md"), "w", encoding="utf-8") as f:
        f.write(md_content)

    # 2. Strict Audit
    try:
        passed, audit_dict = run_l1_audit(pdf_path, page_number=page_num, strict=True, output_dir=out_dir)
    except Exception as e:
        passed = False
        audit_dict = {}
        print(f"Audit failed with exception: {e}")

    # Capture terminal audit text
    import io
    from contextlib import redirect_stdout
    f_str = io.StringIO()
    with redirect_stdout(f_str):
        if audit_dict:
            print_audit_terminal_report(audit_dict)
    audit_text = f_str.getvalue()
    with open(os.path.join(out_dir, "audit_strict.txt"), "w", encoding="utf-8") as f:
        f.write(audit_text)

    # 3. Vertical Rules Table
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(page_num)
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    table_grid = grid_engine.build_table_grid(ruleset, page_layer)

    v_rule_lines = []
    v_rule_lines.append(f"{'Rule ID':<15} | {'X (pt)':<10} | {'Width (pt)':<10} | {'Span (pt)':<10} | {'Used as Boundary'}")
    v_rule_lines.append("-" * 70)
    boundary_xs = [b.centre_x_pt for b in table_grid.boundaries]
    for r in ruleset.v_rules:
        is_boundary = any(abs(r.centre - bx) <= 0.5 for bx in boundary_xs)
        v_rule_lines.append(f"{r.id:<15} | {r.centre:<10.3f} | {r.width:<10.3f} | {r.span:<10.3f} | {str(is_boundary)}")
    if not ruleset.v_rules:
        v_rule_lines.append("No vertical rules present (table uses virtual column boundaries)")

    v_rule_text = "\n".join(v_rule_lines)
    with open(os.path.join(out_dir, "vertical_rules.txt"), "w", encoding="utf-8") as f:
        f.write(v_rule_text)

    # 4. Column List with Evidence
    col_lines = []
    col_lines.append(f"{'Col #':<6} | {'X0 (pt)':<10} | {'X1 (pt)':<10} | {'Width (pt)':<12} | {'Header Text':<25} | {'Evidence'}")
    col_lines.append("-" * 95)
    for c in table_grid.columns:
        ev_str = ", ".join(c.evidence) if c.evidence else "physical_rules"
        hdr_txt = c.header_text or "-"
        col_lines.append(f"{c.index:<6} | {c.x0_pt:<10.3f} | {c.x1_pt:<10.3f} | {c.width_pt:<12.3f} | {hdr_txt:<25} | {ev_str}")
    if not table_grid.columns:
        col_lines.append("No columns detected (empty table)")

    col_text = "\n".join(col_lines)
    with open(os.path.join(out_dir, "columns.txt"), "w", encoding="utf-8") as f:
        f.write(col_text)

    # 5. Arrow List
    lane_engine = DimensionLaneEngine()
    lane_model = lane_engine.build_dimension_lane(table_grid, ruleset, page_layer)
    arrow_lines = []
    arrow_lines.append(f"{'Arrow #':<8} | {'Left Rule':<15} | {'Right Rule':<15} | {'Start X':<10} | {'End X':<10} | {'Width (pt)':<10} | {'Label'}")
    arrow_lines.append("-" * 90)
    for a in lane_model.arrows:
        arrow_lines.append(f"{a.column_index:<8} | {a.rule_id_a:<15} | {a.rule_id_b:<15} | {a.x0_pt:<10.3f} | {a.x1_pt:<10.3f} | {a.width_pt:<10.3f} | {a.label_text}")
    if not lane_model.arrows:
        arrow_lines.append(f"Lane absent: {lane_model.lane_absent_reason}")

    arrow_text = "\n".join(arrow_lines)
    with open(os.path.join(out_dir, "arrows.txt"), "w", encoding="utf-8") as f:
        f.write(arrow_text)

    # 6. Closed Loop Structure-Mask SSIM
    closed_loop_engine = ClosedLoopEngine(dpi=150, min_ssim_threshold=0.80)
    try:
        ssim_report = closed_loop_engine.evaluate_closed_loop(pdf_path, page_number=page_num, output_dir=out_dir)
        ssim_lines = []
        ssim_lines.append(f"{'Region':<15} | {'SSIM Score':<12} | {'Verdict'}")
        ssim_lines.append("-" * 40)
        for r in ssim_report.region_scores:
            st = "PASS" if r.passed else "FAIL"
            ssim_lines.append(f"{r.region_name:<15} | {r.ssim_score:<12.4f} | {st}")
        ssim_lines.append("-" * 40)
        ssim_lines.append(f"{'Overall':<15} | {ssim_report.overall_ssim:<12.4f} | {'PASS' if ssim_report.overall_passed else 'FAIL'}")
        ssim_lines.append(f"Winning Model: {ssim_report.winning_model} (Primary: {ssim_report.chosen_model}, Runner-up: {ssim_report.runner_up_model})")
        ssim_text = "\n".join(ssim_lines)
    except Exception as e:
        ssim_text = f"Closed loop evaluation error: {e}"

    with open(os.path.join(out_dir, "ssim_table.txt"), "w", encoding="utf-8") as f:
        f.write(ssim_text)


def main():
    for name, path, p_num in PDF_TARGETS:
        if os.path.exists(path):
            run_target(name, path, p_num)
        else:
            print(f"Path not found: {path}")

    # Run Corpus Check and save
    corpus_engine = CorpusCheckEngine()
    corpus_report = corpus_engine.run_corpus_check()
    f_str = io.StringIO()
    with redirect_stdout(f_str):
        print_corpus_check_report(corpus_report)
    corpus_text = f_str.getvalue()
    with open("out/corpus_check.txt", "w", encoding="utf-8") as f:
        f.write(corpus_text)
    print("ALL TARGET RUNS COMPLETE.")


if __name__ == "__main__":
    import io
    from contextlib import redirect_stdout
    main()
