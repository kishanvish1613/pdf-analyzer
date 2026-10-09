"""
L1-L5 Audit Orchestrator & CLI Diagnostics (Phase 8A & 8B Task 8).
Executes L0 extraction, dual 600 DPI rendering, sub-pixel profile fitting,
least-squares affine registration, L2 RuleSet canonical extraction,
L3 Planar Graph container polygonization, L4 Layout Tree / Header / Footer / Margins recovery,
and L5 Dimension Lane & SnapIndex construction.
Prints PASS/FAIL Gate tables (G1 - G7), Title Scoring Table, Lane Candidates,
arrow list (start, end, width), and all Checks.
"""

from __future__ import annotations
import os
import json
from typing import Dict, Any, Optional, List, Tuple
import click

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedPath
from pdf_analyzer.l1_crosscheck.renderers import DualRenderer
from pdf_analyzer.l1_crosscheck.registration import RegistrationEngine, RegistrationResult
from pdf_analyzer.l1_crosscheck.crosscheck import L1CrossCheckEngine, TruthReport
from pdf_analyzer.l1_crosscheck.gates import GateEvaluator, GateReport
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.containers import PlanarGraphEngine, Container
from pdf_analyzer.l3_topology.table_grid import TableGridEngine, TableGrid
from pdf_analyzer.l4_layout.layout_tree import LayoutTreeEngine
from pdf_analyzer.l4_layout.margins_logo import MarginsLogoEngine
from pdf_analyzer.l4_layout.accounting import ContentAccountingEngine
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneEngine, DimensionLaneModel
from pdf_analyzer.l5_editor.model import EditorModelBuilder
from pdf_analyzer.utils.json_sanitizer import sanitize_for_json


def run_l1_audit(
    pdf_path: str,
    page_number: int = 1,
    strict: bool = False,
    output_dir: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Runs the full Phase 1-5 audit pipeline and returns (success_bool, audit_dict).
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(pdf_path), "audit_output")
    os.makedirs(output_dir, exist_ok=True)

    # 1. L0 ByteLayer Truth Extraction
    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(page_number)

    # 2. Dual 600 DPI Independent Rendering
    renderer = DualRenderer(dpi=600)
    mupdf_render, pdfium_render = renderer.render_both(pdf_path, page_number)

    # 3. Least-Squares Registration & Sub-Pixel Fitting
    reg_engine = RegistrationEngine(dpi=600)
    reg_result = reg_engine.solve_registration(page_layer, mupdf_render.image_rgb, output_dir=output_dir)

    # 4. Multi-Engine Crosscheck & Truth Report
    crosscheck_engine = L1CrossCheckEngine(dpi=600)
    truth_report = crosscheck_engine.generate_truth_report(pdf_path, page_layer, output_dir=output_dir)

    # 5. L2 Canonical RuleSet Extraction
    ruleset = RuleSet.from_page_layer(page_layer)

    # 6. L3 Planar Graph Containers & Table Grid
    planar_engine = PlanarGraphEngine()
    containers = planar_engine.polygonize_containers(ruleset, page_layer)

    table_grid_engine = TableGridEngine()
    table_grid = table_grid_engine.build_table_grid(ruleset, page_layer, containers)

    # 7. L4 Layout Tree, Table BBox, Header, Footer, Margins & Content Accounting
    layout_engine = LayoutTreeEngine()
    layout_tree, table_res, header_model, footer_model = layout_engine.build_layout_tree(
        page_layer=page_layer,
        ruleset=ruleset,
        containers=containers,
        table_grid=table_grid,
    )

    margins_engine = MarginsLogoEngine()
    margins_model, logo_model, alignment_axes = margins_engine.compute_margins_and_logo(page_layer)

    accounting_engine = ContentAccountingEngine()
    accounting_report = accounting_engine.audit_content_accounting(
        page_layer=page_layer,
        layout_tree=layout_tree,
        raster_image_rgb=mupdf_render.image_rgb,
        dpi=600,
    )

    # 8. L5 Dimension Lane & Editor Model
    lane_engine = DimensionLaneEngine()
    dimension_lane = lane_engine.build_dimension_lane(table_grid, ruleset, page_layer)

    editor_builder = EditorModelBuilder(dpi=600)
    editor_model = editor_builder.build_editor_model(
        page_layer=page_layer,
        ruleset=ruleset,
        containers=containers,
        table_grid=table_grid,
        layout_tree=layout_tree,
        table_res=table_res,
        header_model=header_model,
        footer_model=footer_model,
        margins_model=margins_model,
        logo_model=logo_model,
    )

    # 9. Gate Evaluation (G1 - G7)
    gate_evaluator = GateEvaluator()
    gate_report = gate_evaluator.evaluate_gates(
        reg_result=reg_result,
        truth_report=truth_report,
        ruleset=ruleset,
        table_grid=table_grid,
        containers=containers,
        layout_tree=layout_tree,
        accounting_report=accounting_report,
        dimension_lane=dimension_lane,
        page_layer=page_layer,
        dimensions=editor_model.dimensions,
    )

    # 10. Extract Vertical Rules Data with used-as-boundary annotation
    v_rules_data = extract_annotated_vertical_rules(ruleset, table_grid)

    # Compile Audit Dictionary
    audit_dict = {
        "pdf_path": os.path.abspath(pdf_path),
        "page_number": page_number,
        "cropbox_pt": list(page_layer.cropbox_pt),
        "registration": reg_result.to_dict(),
        "truth_report": truth_report.to_dict(),
        "ruleset": ruleset.to_dict(),
        "containers": [c.to_dict() for c in containers],
        "table_grid": table_grid.to_dict(),
        "table_bbox_result": table_res.to_dict(),
        "header_model": header_model.to_dict(),
        "footer_model": footer_model.to_dict(),
        "margins_model": margins_model.to_dict(),
        "logo_model": logo_model.to_dict() if logo_model else None,
        "alignment_axes": alignment_axes,
        "layout_tree": layout_tree.to_dict(),
        "accounting_report": accounting_report.to_dict(),
        "dimension_lane": dimension_lane.to_dict(),
        "editor_model": editor_model.to_dict(),
        "gate_report": gate_report.to_dict(),
        "vertical_rules": v_rules_data,
    }

    # Write audit.json
    with open(os.path.join(output_dir, "audit.json"), "w", encoding="utf-8") as f:
        json.dump(sanitize_for_json(audit_dict), f, indent=2)

    return gate_report.overall_passed, audit_dict


def extract_annotated_vertical_rules(
    ruleset: RuleSet,
    table_grid: TableGrid,
) -> List[Dict[str, Any]]:
    """
    Extracts all vertical vector rules from RuleSet with used-as-boundary annotation.
    """
    max_span = max([r.span for r in ruleset.v_rules]) if ruleset.v_rules else 100.0
    boundary_rules = {b.rule_id for b in table_grid.boundaries}

    res = []
    for r in sorted(ruleset.v_rules, key=lambda x: x.centre):
        is_boundary = r.id in boundary_rules
        coverage = (r.span / max_span) * 100.0 if max_span > 0 else 0.0
        reason = "Qualified primary column boundary" if is_boundary else "Shorter sub-segment / duplicate"

        res.append({
            "id": r.id,
            "centre_x_pt": r.centre,
            "width_pt": r.width,
            "start_y_pt": r.start,
            "end_y_pt": r.end,
            "span_pt": r.span,
            "coverage_pct": coverage,
            "used_as_boundary": is_boundary,
            "decision_reason": reason,
        })
    return res


def print_audit_terminal_report(audit_dict: Dict[str, Any]) -> None:
    """Formats and prints the human-readable audit report to stdout."""
    pdf_name = os.path.basename(audit_dict["pdf_path"])
    page_num = audit_dict["page_number"]
    gate_rep = audit_dict["gate_report"]
    v_rules = audit_dict["vertical_rules"]
    table_grid = audit_dict.get("table_grid", {})
    t_res = audit_dict.get("table_bbox_result", {})
    hdr = audit_dict.get("header_model", {})
    ftr = audit_dict.get("footer_model", {})
    mrg = audit_dict.get("margins_model", {})
    acct = audit_dict.get("accounting_report", {})
    lane = audit_dict.get("dimension_lane", {})
    editor = audit_dict.get("editor_model", {})

    click.echo("\n" + "=" * 98)
    click.echo(f"  PDF DESIGN ANALYZER - L1-L5 RECONSTRUCTION AUDIT (Page {page_num} of {pdf_name})")
    click.echo("=" * 98)

    # 1. Gate Status Table
    click.echo("\n[1] GATE VERIFICATION & INVARIANT STATUS:")
    click.echo("-" * 98)
    click.echo(f"{'Gate':<6} | {'Name':<40} | {'Status':<20} | {'Threshold / Actual'}")
    click.echo("-" * 98)

    for g in gate_rep["gates"]:
        st = g["status"]
        if st == "PASSED":
            st_str = click.style("[PASS]", fg="green", bold=True)
        elif st == "FAILED":
            st_str = click.style("[FAIL]", fg="red", bold=True)
        else:
            st_str = click.style("[NOT_YET_IMPLEMENTED]", fg="yellow")

        name = g["name"][:40]
        desc = g["actual_value_desc"]
        click.echo(f"{g['gate_id']:<6} | {name:<40} | {st_str:<29} | {desc}")
        if g.get("violating_objects"):
            for v in g["violating_objects"][:3]:
                click.echo(f"       * {click.style(v, fg='red')}")

    click.echo("-" * 98)

    # 2. Title Classification Score Table (Phase 8B Task 4)
    title_scores = hdr.get("title_scores", [])
    if title_scores:
        click.echo(f"\n[2] TITLE CLASSIFICATION SCORE TABLE (Phase 8B Task 4):")
        click.echo("-" * 98)
        click.echo(f"{'Line Text':<30} | {'Size':<6} | {'Cent':<6} | {'AbvT':<6} | {'CntPen':<6} | {'AdrPen':<6} | {'KwBst':<6} | {'Total':<6} | {'Verdict'}")
        click.echo("-" * 98)
        for ts in title_scores[:5]:
            verdict = click.style("[TITLE]", fg="green", bold=True) if ts.get("is_classified_title") else "-"
            txt = ts["text"][:30]
            click.echo(
                f"{txt:<30} | {ts['font_size_score']:<6.1f} | {ts['centering_score']:<6.1f} | {ts['above_table_score']:<6.1f} | {ts['container_penalty']:<6.1f} | {ts['address_kv_penalty']:<6.1f} | {ts['title_keywords_boost']:<6.1f} | {ts['total_score']:<6.1f} | {verdict}"
            )
        click.echo("-" * 98)

    # Convert coordinates to Top-Left of CropBox (Rule 6)
    from pdf_analyzer.utils.units import to_top_left_bbox
    cropbox_pt = audit_dict.get("cropbox_pt")
    if not cropbox_pt or len(cropbox_pt) < 4:
        raise ValueError(f"audit_dict missing authoritative 'cropbox_pt': {cropbox_pt}")
    c_x0, c_y0, c_x1, c_y1 = cropbox_pt

    def to_tl_bbox(b: List[float]) -> List[float]:
        res = to_top_left_bbox(b, (c_x0, c_y0, c_x1, c_y1))
        return [round(res[0], 2), round(res[1], 2), round(res[2], 2), round(res[3], 2)]

    # 3. Table Bounds & Suffix Accounting (E2, E13)
    raw_t_bbox = t_res.get("table_bbox_pt", [0, 0, 0, 0])
    t_bbox = to_tl_bbox(raw_t_bbox)
    num_cells = t_res.get("numeric_cells", [])
    click.echo(f"\n[3] TABLE BOUNDS & NUMERIC SUFFIX EXTENTS (E2, E13, Task 7) [Top-Left]:")
    click.echo("-" * 98)
    click.echo(f"Table BBox: [{t_bbox[0]:.2f}, {t_bbox[1]:.2f}, {t_bbox[2]:.2f}, {t_bbox[3]:.2f}] | Width: {t_bbox[2]-t_bbox[0]:.2f}pt | Height: {t_bbox[3]-t_bbox[1]:.2f}pt")
    if num_cells:
        click.echo(f"Fused Numeric Cells ({len(num_cells)} cells with values/suffixes):")
        for c in num_cells[:4]:
            suf_str = f" [Suffix: {c['suffix_part']}]" if c.get("suffix_part") else ""
            click.echo(f"  * {c['cell_id']}: '{c['full_text']}'{suf_str} | distance_to_border={c['distance_to_right_border_pt']:.2f}pt")

    # 4. Dimension Lane (E9, E11, G7, Phase 8B Tasks 1 & 2)
    arrows = lane.get("arrows", [])
    cols_count = len(table_grid.get("columns", []))
    lane_reason = lane.get("lane_absent_reason")
    cand_chosen = lane.get("candidate_chosen", "above")
    raw_lane_y = lane.get("lane_y_pt", 0.0)
    raw_top_y = lane.get("table_top_y_pt", 0.0)
    lane_y_tl = round(c_y1 - raw_lane_y, 2) if raw_lane_y > 0 else 0.0
    table_top_tl = round(c_y1 - raw_top_y, 2) if raw_top_y > 0 else 0.0

    click.echo(f"\n[4] DIMENSION LANE (Candidate: {cand_chosen}, Lane Y: {lane_y_tl:.2f}pt, Table Top Y: {table_top_tl:.2f}pt) [Top-Left]:")
    click.echo("-" * 98)
    if lane_reason:
        click.echo(click.style(f"  * [LANE ABSENT] {lane_reason}", fg="yellow"))
    else:
        click.echo(f"Lane Y: {lane_y_tl:.2f}pt | Table Top Y: {table_top_tl:.2f}pt | Columns: {cols_count} | Arrows: {len(arrows)}")
        for a in arrows:
            click.echo(f"  * Arrow {a['column_index']} ({a['rule_id_left']} -> {a['rule_id_right']}): [{a['start_x_pt']:.2f} pt -> {a['end_x_pt']:.2f} pt] width = {a['width_pt']:.2f} pt")
        click.echo(f"  * Sum Widths: {lane.get('sum_widths_pt', 0.0):.2f} pt + Interior Rules: {lane.get('interior_rules_width_pt', 0.0):.2f} pt == Table Width: {lane.get('table_outer_width_pt', 0.0):.2f} pt (Valid: {lane.get('is_valid')})")

        if cols_count > 0 and len(arrows) != cols_count:
            click.echo(click.style(f"  * [FAIL] Arrow count mismatch: {len(arrows)} arrows != {cols_count} columns", fg="red", bold=True))

    # 5. Header Two-Block & KV Grids (E5, E6)
    click.echo(f"\n[5] HEADER LAYOUT & KEY-VALUE GRIDS (E5, E6) [Top-Left]:")
    click.echo("-" * 98)
    click.echo(f"Two-Block Header: {hdr.get('is_two_block')} | Gutter Width: {hdr.get('gutter_width_pt', 0.0):.2f}pt | Shared Baselines: {hdr.get('shared_baselines_count')}")
    for b in hdr.get("blocks", []):
        kv = b.get("kv_grid")
        kv_info = f" (KVGrid rows={kv['rows_count']}, axis_x={kv.get('value_axis_x_pt')})" if kv and kv.get("is_valid_grid") else ""
        b_tl = to_tl_bbox(b.get("bbox_pt", [0, 0, 0, 0]))
        click.echo(f"  * Block {b['block_id']} ({b['block_type']}): bbox=[{b_tl[0]:.1f}, {b_tl[1]:.1f}, {b_tl[2]:.1f}, {b_tl[3]:.1f}], pitch={b['mean_pitch_pt']:.2f}pt{kv_info}")

    # 6. Footer & Page Number (E4)
    click.echo(f"\n[6] FOOTER & PAGE NUMBER (E4) [Top-Left]:")
    click.echo("-" * 98)
    click.echo(f"Pinned: {ftr.get('is_pinned')} | Page Number: '{ftr.get('page_number_text')}' | Table->Footer Gap: {ftr.get('gap_table_ink_to_footer_ink_pt', 0.0):.2f}pt | Footer->Bottom Gap: {ftr.get('gap_footer_ink_to_page_bottom_pt', 0.0):.2f}pt")

    # 7. Consistency Checks (Checks Tab)
    checks = editor.get("consistency", {}).get("checks", {})
    click.echo(f"\n[7] CONSISTENCY & REASON CHECKS:")
    click.echo("-" * 98)
    for k, v in checks.items():
        click.echo(f"  * {k}: {v}")

    click.echo("=" * 98 + "\n")
