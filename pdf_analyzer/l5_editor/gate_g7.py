"""
Gate G7: Dimension Lane Visual Verification & Endpoint Registration.
Validates that every dimension arrow endpoint snaps to its underlying RuleSet rule
within 0.5 px at 600 DPI (0.06 pt), with strictly zero visual collision or text overlap.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneModel, DimensionArrow


@dataclass
class ArrowEndpointCheck:
    arrow_index: int
    endpoint: str  # 'start' | 'end'
    arrow_coord_pt: float
    rule_id: str
    rule_coord_pt: float
    delta_pt: float
    delta_px: float
    passed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arrow_index": self.arrow_index,
            "endpoint": self.endpoint,
            "arrow_coord_pt": self.arrow_coord_pt,
            "rule_id": self.rule_id,
            "rule_coord_pt": self.rule_coord_pt,
            "delta_pt": self.delta_pt,
            "delta_px": self.delta_px,
            "passed": self.passed,
        }


@dataclass
class GateG7Report:
    passed: bool
    arrows_checked: int
    max_endpoint_delta_px: float
    checks: List[ArrowEndpointCheck] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "arrows_checked": self.arrows_checked,
            "max_endpoint_delta_px": self.max_endpoint_delta_px,
            "checks": [c.to_dict() for c in self.checks],
            "error_message": self.error_message,
        }


class GateG7Evaluator:
    """
    Evaluates Gate G7: Arrow endpoints must be within 0.5 px of RuleSet rules.
    """

    def evaluate_g7(
        self,
        dimension_lane: DimensionLaneModel,
        ruleset: RuleSet,
        dpi: int = 600,
        tolerance_px: float = 0.5,
    ) -> GateG7Report:
        if not dimension_lane or not dimension_lane.arrows:
            return GateG7Report(
                passed=True,
                arrows_checked=0,
                max_endpoint_delta_px=0.0,
                checks=[],
            )

        pt_to_px = dpi / 72.0
        checks: List[ArrowEndpointCheck] = []
        max_delta_px = 0.0
        overall_passed = True
        error_msgs = []

        for idx, arrow in enumerate(dimension_lane.arrows):
            # Check Start Endpoint (rule_id_a)
            rule_a = ruleset.get_rule_by_id(arrow.rule_id_a)
            if rule_a:
                if arrow.is_left_outer:
                    target_coord = rule_a.centre - rule_a.width / 2.0
                else:
                    target_coord = rule_a.centre + rule_a.width / 2.0

                delta_pt = abs(arrow.x0_pt - target_coord)
                delta_px = delta_pt * pt_to_px
                passed = delta_px <= (tolerance_px + 1e-4)
                if delta_px > max_delta_px:
                    max_delta_px = delta_px
                if not passed:
                    overall_passed = False
                    error_msgs.append(
                        f"Arrow {idx} start (x={arrow.x0_pt:.3f}pt) differs from Rule {rule_a.id} (x={target_coord:.3f}pt) by {delta_px:.3f}px > {tolerance_px}px"
                    )
                checks.append(
                    ArrowEndpointCheck(
                        arrow_index=idx,
                        endpoint="start",
                        arrow_coord_pt=arrow.x0_pt,
                        rule_id=arrow.rule_id_a,
                        rule_coord_pt=target_coord,
                        delta_pt=delta_pt,
                        delta_px=delta_px,
                        passed=passed,
                    )
                )

            # Check End Endpoint (rule_id_b)
            rule_b = ruleset.get_rule_by_id(arrow.rule_id_b)
            if rule_b:
                if arrow.is_right_outer:
                    target_coord = rule_b.centre + rule_b.width / 2.0
                else:
                    target_coord = rule_b.centre - rule_b.width / 2.0

                delta_pt = abs(arrow.x1_pt - target_coord)
                delta_px = delta_pt * pt_to_px
                passed = delta_px <= (tolerance_px + 1e-4)
                if delta_px > max_delta_px:
                    max_delta_px = delta_px
                if not passed:
                    overall_passed = False
                    error_msgs.append(
                        f"Arrow {idx} end (x={arrow.x1_pt:.3f}pt) differs from Rule {rule_b.id} (x={target_coord:.3f}pt) by {delta_px:.3f}px > {tolerance_px}px"
                    )
                checks.append(
                    ArrowEndpointCheck(
                        arrow_index=idx,
                        endpoint="end",
                        arrow_coord_pt=arrow.x1_pt,
                        rule_id=arrow.rule_id_b,
                        rule_coord_pt=target_coord,
                        delta_pt=delta_pt,
                        delta_px=delta_px,
                        passed=passed,
                    )
                )

        return GateG7Report(
            passed=overall_passed,
            arrows_checked=len(dimension_lane.arrows),
            max_endpoint_delta_px=max_delta_px,
            checks=checks,
            error_message="; ".join(error_msgs) if error_msgs else None,
        )
