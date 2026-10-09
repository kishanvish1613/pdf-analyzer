"""
L1 Gate Verification & Mathematical Invariant Evaluator (G1 - G7).
Evaluates strict mathematical thresholds across all layers:
- Gate G1: Affine Registration residual <= 0.15 pt, scale delta <= 0.0005.
- Gate G2: Byte-vs-MuPDF vector agreement (max delta <= 0.05 pt).
- Gate G3: 600 DPI Sub-Pixel Profile & FWHM Gate (center delta <= 0.25 pt, FWHM delta <= 0.50 pt).
- Gate G4: Topological Table Grid & Strict Multi-Signal Column Enforcement (contiguity <= 0.25 pt, zero virtual boundaries).
- Gate G5: Content Accounting (0 orphans, 600 DPI residual raster ink <= 0.3%).
- Gate G6: Quantisation Audit (L0 raw vs derived quantisation, FAIL derived_quantised).
- Gate G7: Dimension Lane Visual Verification (arrow endpoints within 0.5 px of RuleSet rules).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from pdf_analyzer.l1_crosscheck.registration import RegistrationResult
from pdf_analyzer.l1_crosscheck.crosscheck import TruthReport
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.containers import Container
from pdf_analyzer.l3_topology.table_grid import TableGrid
from pdf_analyzer.l4_layout.models import LayoutTree, AccountingReport
from pdf_analyzer.l5_editor.gate_g7 import GateG7Report, GateG7Evaluator
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneModel
from pdf_analyzer.quantisation_audit import QuantisationAuditEngine, QuantisationReport


@dataclass
class GateResult:
    gate_id: str
    name: str
    status: str  # 'PASSED' | 'FAILED' | 'WARNING'
    threshold_desc: str
    actual_value_desc: str
    violating_objects: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "status": self.status,
            "threshold_desc": self.threshold_desc,
            "actual_value_desc": self.actual_value_desc,
            "violating_objects": self.violating_objects,
        }


@dataclass
class GateReport:
    overall_passed: bool
    g1_registration: GateResult
    g2_mupdf_crosscheck: GateResult
    g3_raster_fwhm: GateResult
    g4_topological_table: GateResult
    g5_content_accounting: GateResult
    g6_quantisation_smell: GateResult
    g7_dimension_lane: GateResult

    @property
    def gates(self) -> List[GateResult]:
        return [
            self.g1_registration,
            self.g2_mupdf_crosscheck,
            self.g3_raster_fwhm,
            self.g4_topological_table,
            self.g5_content_accounting,
            self.g6_quantisation_smell,
            self.g7_dimension_lane,
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_passed": self.overall_passed,
            "gates": [g.to_dict() for g in self.gates],
        }


class GateEvaluator:
    """
    Evaluates Phase 1 - 5 Gates (G1 - G7).
    """

    def evaluate_gates(
        self,
        reg_result: RegistrationResult,
        truth_report: TruthReport,
        ruleset: Optional[RuleSet] = None,
        table_grid: Optional[TableGrid] = None,
        containers: Optional[List[Container]] = None,
        layout_tree: Optional[LayoutTree] = None,
        accounting_report: Optional[AccountingReport] = None,
        dimension_lane: Optional[DimensionLaneModel] = None,
        page_layer: Optional[Any] = None,
        dimensions: Optional[List[Dict[str, Any]]] = None,
    ) -> GateReport:
        # 1. Gate G1: Registration
        g1_actual = (
            f"dx={reg_result.dx_pt:.4f}pt, dy={reg_result.dy_pt:.4f}pt, "
            f"sx={reg_result.sx:.6f}, sy={reg_result.sy:.6f}, "
            f"max_res={reg_result.max_residual_pt:.4f}pt"
        )
        g1_violating = []
        if abs(reg_result.dx_pt) > 0.1:
            g1_violating.append(f"dx={reg_result.dx_pt:.4f}pt > 0.1pt")
        if abs(reg_result.dy_pt) > 0.1:
            g1_violating.append(f"dy={reg_result.dy_pt:.4f}pt > 0.1pt")
        if abs(reg_result.sx - 1.0) > 0.0005:
            g1_violating.append(f"|sx-1|={abs(reg_result.sx-1.0):.6f} > 0.0005")
        if abs(reg_result.sy - 1.0) > 0.0005:
            g1_violating.append(f"|sy-1|={abs(reg_result.sy-1.0):.6f} > 0.0005")
        if reg_result.max_residual_pt > 0.15:
            g1_violating.append(f"max_residual={reg_result.max_residual_pt:.4f}pt > 0.15pt")

        g1 = GateResult(
            gate_id="G1",
            name="Registration Gate",
            status="PASSED" if not g1_violating else "FAILED",
            threshold_desc="dx,dy <= 0.1pt, |s-1| <= 0.0005, max_residual <= 0.15pt",
            actual_value_desc=g1_actual,
            violating_objects=g1_violating,
        )

        # 2. Gate G2: MuPDF Crosscheck
        g2_violating = []
        max_d = getattr(truth_report, "max_path_delta_pt", 0.0)
        mean_d = getattr(truth_report, "mean_path_delta_pt", 0.0)
        if getattr(truth_report, "vector_comparisons", None):
            deltas = [c.delta_pt for c in truth_report.vector_comparisons]
            max_d = max(deltas)
            mean_d = sum(deltas) / len(deltas)
            for c in truth_report.vector_comparisons:
                if c.delta_pt > 0.05:
                    g2_violating.append(f"Vector {c.primitive_id} delta={c.delta_pt:.4f}pt > 0.05pt")
        elif getattr(truth_report, "findings", None):
            for f in truth_report.findings:
                if f.delta_pt > 0.05:
                    g2_violating.append(f"Finding {f.object_id} delta={f.delta_pt:.4f}pt > 0.05pt")

        g2 = GateResult(
            gate_id="G2",
            name="Byte-vs-MuPDF Vector Agreement",
            status="PASSED" if not g2_violating else "FAILED",
            threshold_desc="Max vector delta <= 0.05pt",
            actual_value_desc=f"max_delta={max_d:.4f}pt, mean={mean_d:.4f}pt",
            violating_objects=g2_violating,
        )

        # 3. Gate G3: Raster Sub-Pixel Profile & FWHM Gate
        g3_violating = []
        max_c_delta = 0.0
        max_f_delta = 0.0
        if truth_report.fwhm_profiles:
            for p in truth_report.fwhm_profiles:
                c_d = p.delta_to_byte_pt
                f_d = p.fwhm_delta_pt
                max_c_delta = max(max_c_delta, c_d)
                max_f_delta = max(max_f_delta, f_d)
                if c_d > 0.25:
                    g3_violating.append(f"Profile {p.rule_id} center delta={c_d:.4f}pt > 0.25pt")
                if f_d > 0.50:
                    g3_violating.append(f"Profile {p.rule_id} FWHM delta={f_d:.4f}pt > 0.50pt")

        g3 = GateResult(
            gate_id="G3",
            name="Raster 600 DPI Sub-Pixel & FWHM Gate",
            status="PASSED" if not g3_violating else "FAILED",
            threshold_desc="Center delta <= 0.25pt, FWHM delta <= 0.50pt",
            actual_value_desc=f"max_center_delta={max_c_delta:.4f}pt, max_fwhm_delta={max_f_delta:.4f}pt",
            violating_objects=g3_violating,
        )

        # 4. Gate G4: Topological Table Grid & Column Contiguity
        g4_violating = []
        g4_status = "PASSED"
        if table_grid:
            if not table_grid.contiguity_passed:
                g4_violating.append(f"Table column contiguity failed: sum({table_grid.sum_column_widths_pt:.2f}pt) != outer({table_grid.outer_width_pt:.2f}pt)")
                g4_status = "FAILED"
            for b in table_grid.boundaries:
                if b.is_virtual and not table_grid.is_borderless:
                    g4_violating.append(f"Virtual column boundary at x={b.centre_x_pt:.2f}pt forbidden on ruled table")
                    g4_status = "FAILED"
            g4_actual = f"cols={len(table_grid.columns)}, rows={len(table_grid.rows)}, contiguity_passed={table_grid.contiguity_passed}"
        else:
            g4_actual = "No table grid evaluated"

        g4 = GateResult(
            gate_id="G4",
            name="Table Grid & Strict Column Contiguity",
            status=g4_status,
            threshold_desc="Sum column widths == outer width +-0.25pt, zero virtual boundaries",
            actual_value_desc=g4_actual,
            violating_objects=g4_violating,
        )

        # 5. Gate G5: Content Accounting & Residual Ink
        g5_violating = []
        g5_status = "PASSED"
        if accounting_report:
            if accounting_report.orphan_chars_count > 0:
                g5_violating.append(f"{accounting_report.orphan_chars_count} orphan characters unassigned to layout leaves")
                g5_status = "FAILED"
            if not accounting_report.residual_ink_passed:
                g5_violating.append(f"Residual raster ink {accounting_report.residual_ink_pct:.2f}% exceeds 0.3% threshold")
                g5_status = "FAILED"
            g5_actual = f"orphans={accounting_report.orphan_chars_count}, residual_ink={accounting_report.residual_ink_pct:.2f}%, invisible={accounting_report.invisible_chars_count}"
        else:
            g5_actual = "No accounting evaluated"

        g5 = GateResult(
            gate_id="G5",
            name="Content Accounting & Residual Ink",
            status=g5_status,
            threshold_desc="0 orphan characters, 600 DPI residual raster ink <= 0.3%",
            actual_value_desc=g5_actual,
            violating_objects=g5_violating,
        )

        # 6. Gate G6: Quantisation Audit (Phase 8A Task 5)
        g6_violating = []
        g6_status = "PASSED"
        dims_to_check = dimensions or []
        if not dims_to_check and table_grid and table_grid.columns:
            for c in table_grid.columns:
                dims_to_check.append({
                    "id": f"dim_col_{c.index}_width",
                    "title": f"Column {c.index} Width",
                    "value_pt": c.width_pt,
                })

        if page_layer and dims_to_check:
            q_engine = QuantisationAuditEngine()
            q_report = q_engine.audit_quantisation(page_layer=page_layer, dimensions=dims_to_check)
            if not q_report.passed:
                g6_status = "FAILED"
                for f in q_report.findings:
                    g6_violating.append(f"derived_quantised: {f.violation_reason}")
            g6_actual = f"Raw 1pt mults: {q_report.raw_multiples_of_1pt_pct:.1f}%, 0.25pt mults: {q_report.raw_multiples_of_0_25pt_pct:.1f}%, derived_checked={len(dims_to_check)}"
        elif table_grid and table_grid.columns:
            col_widths = [c.width_pt for c in table_grid.columns]
            multiples_of_5 = [w for w in col_widths if (abs(w % 5.0) <= 0.01 or abs(w % 5.0 - 5.0) <= 0.01)]
            pct_multiples = (len(multiples_of_5) / len(col_widths)) * 100.0 if col_widths else 0.0
            if pct_multiples >= 75.0 and len(col_widths) >= 4:
                g6_violating.append(f"derived_quantised: {pct_multiples:.1f}% of column widths are exact multiples of 5pt")
                g6_status = "FAILED"
            g6_actual = f"Exact 5pt multiples: {pct_multiples:.1f}% ({len(multiples_of_5)}/{len(col_widths)})"
        else:
            g6_actual = "No dimensions or columns to inspect"

        g6 = GateResult(
            gate_id="G6",
            name="Quantisation Audit",
            status=g6_status,
            threshold_desc="Derived dimensions not coarsely quantised compared to raw L0 coordinates",
            actual_value_desc=g6_actual,
            violating_objects=g6_violating,
        )

        # 7. Gate G7: Dimension Lane Visual Verification & Endpoint Registration
        g7_violating = []
        g7_status = "PASSED"
        if dimension_lane and ruleset and len(dimension_lane.arrows) > 0:
            g7_eval = GateG7Evaluator()
            g7_rep = g7_eval.evaluate_g7(dimension_lane, ruleset, dpi=600)
            if not g7_rep.passed:
                g7_status = "FAILED"
                if g7_rep.error_message:
                    g7_violating.append(g7_rep.error_message)
            g7_actual = f"arrows={g7_rep.arrows_checked}, max_endpoint_delta={g7_rep.max_endpoint_delta_px:.3f}px (tol <= 0.5px)"
        elif dimension_lane and dimension_lane.lane_absent_reason:
            g7_actual = f"Lane absent: {dimension_lane.lane_absent_reason}"
            g7_status = "PASSED"
        else:
            g7_actual = "No dimension lane evaluated"

        g7 = GateResult(
            gate_id="G7",
            name="Dimension Lane & Visualizer Non-Collision",
            status=g7_status,
            threshold_desc="Arrow endpoints within 0.5px of RuleSet rules, no text overlap",
            actual_value_desc=g7_actual,
            violating_objects=g7_violating,
        )

        overall = (
            g1.status == "PASSED"
            and g2.status == "PASSED"
            and g3.status == "PASSED"
            and g4.status == "PASSED"
            and g5.status == "PASSED"
            and g6.status == "PASSED"
            and g7.status == "PASSED"
        )

        return GateReport(
            overall_passed=overall,
            g1_registration=g1,
            g2_mupdf_crosscheck=g2,
            g3_raster_fwhm=g3,
            g4_topological_table=g4,
            g5_content_accounting=g5,
            g6_quantisation_smell=g6,
            g7_dimension_lane=g7,
        )
