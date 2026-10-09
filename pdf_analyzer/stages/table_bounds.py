"""
Section 22: Exact Table Bounds & Rule-Anchored Dimension Lane Engine.
Performs:
1. Exact painted table bounding box calculation:
   Outer painted edges of vector grid UNION all cell ink bboxes (including suffixes like 'Cr.', 'Dr')
2. Single-cell integration for numeric tokens + currency/credit suffixes
3. Quantisation smell test (detecting invalid 5/10 pt snapped grids)
4. Rule-anchored dimension lane:
   Arrows mapped directly to rule IDs (a, b) with endpoints at exact painted inner edges
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Optional, Union
import numpy as np

from pdf_analyzer.stages.frame import PageFrame, PaintedGeometry, RuleSet, Rule
from pdf_analyzer.stages.containers import RecoveredContainer
from pdf_analyzer.models import ColumnModel, TextSpanModel

logger = logging.getLogger(__name__)


@dataclass
class DimensionArrow:
    column_index: int
    left_rule_id: str
    right_rule_id: str
    x0_inner_pt: float
    x1_inner_pt: float
    width_pt: float
    arrow_y_pt: float
    label_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_index": self.column_index,
            "left_rule_id": self.left_rule_id,
            "right_rule_id": self.right_rule_id,
            "x0_inner_pt": round(self.x0_inner_pt, 3),
            "x1_inner_pt": round(self.x1_inner_pt, 3),
            "width_pt": round(self.width_pt, 3),
            "arrow_y_pt": round(self.arrow_y_pt, 3),
            "label_text": self.label_text
        }


class TableBoundsEngine:
    """Calculates exact painted table boundaries and builds the rule-anchored dimension lane."""

    def __init__(self, page_frame: PageFrame):
        self.frame = page_frame

    def compute_exact_table_bounds(
        self,
        table_container: Optional[RecoveredContainer],
        vector_rules_h: Union[List[PaintedGeometry], List[Rule]],
        vector_rules_v: Union[List[PaintedGeometry], List[Rule]],
        table_spans: List[TextSpanModel],
        rule_set: Optional[RuleSet] = None
    ) -> Tuple[float, float, float, float]:
        """Calculates exact outer painted table bbox enclosing all vector rules and suffix ink bounds."""
        # Filter vertical rules that form the table grid (length >= 25.0 pt, prioritizing body region)
        raw_v_list = list(vector_rules_v)
        if not raw_v_list and rule_set:
            raw_v_list = list(rule_set.vertical_rules)

        raw_h_list = list(vector_rules_h)
        if not raw_h_list and rule_set:
            raw_h_list = list(rule_set.horizontal_rules)

        v_candidates = [v for v in raw_v_list if (v.end_pt - v.start_pt >= 25.0) and v.start_pt >= 150.0]
        if not v_candidates:
            v_candidates = [v for v in raw_v_list if (v.end_pt - v.start_pt >= 25.0)]

        if v_candidates:
            exact_x0 = min(v.painted_outer_edge_pt for v in v_candidates)
            exact_x1 = max(v.painted_inner_edge_pt for v in v_candidates)
            t_y0 = min(v.start_pt for v in v_candidates)
            t_y1 = max(v.end_pt for v in v_candidates)

            # Select horizontal rules in this table y range
            h_candidates = [h for h in raw_h_list if t_y0 - 5.0 <= h.centre_pt <= t_y1 + 5.0]
            if h_candidates:
                exact_y0 = min(h.painted_outer_edge_pt for h in h_candidates)
                exact_y1 = max(h.painted_inner_edge_pt for h in h_candidates)
            else:
                exact_y0 = t_y0 - 0.5
                exact_y1 = t_y1 + 0.5
        elif table_container is not None:
            exact_x0 = table_container.painted_outer_bbox_pt[0]
            exact_x1 = table_container.painted_outer_bbox_pt[2]
            exact_y0 = table_container.painted_outer_bbox_pt[1]
            exact_y1 = table_container.painted_outer_bbox_pt[3]
        else:
            exact_x0 = min((s.ink_box.x0.pt for s in table_spans), default=36.0)
            exact_x1 = max((s.ink_box.x1.pt for s in table_spans), default=self.frame.width_pt - 36.0)
            exact_y0 = 230.0
            exact_y1 = max(300.0, self.frame.height_pt - 80.0)

        # Union all member text spans lying within the table x/y range (including suffixes like 'Cr.', 'Dr')
        member_spans = [
            s for s in table_spans
            if not (s.ink_box.y1.pt < exact_y0 - 2.0 or s.ink_box.y0.pt > exact_y1 + 2.0)
            and not (s.ink_box.x1.pt < exact_x0 - 2.0 or s.ink_box.x0.pt > exact_x1 + 2.0)
        ]

        if member_spans:
            ink_x0 = min(s.ink_box.x0.pt for s in member_spans)
            ink_y0 = min(s.ink_box.y0.pt for s in member_spans)
            ink_x1 = max(s.ink_box.x1.pt for s in member_spans)
            ink_y1 = max(s.ink_box.y1.pt for s in member_spans)

            exact_x0 = min(exact_x0, ink_x0)
            exact_x1 = max(exact_x1, ink_x1)
            exact_y0 = min(exact_y0, ink_y0)
            exact_y1 = max(exact_y1, ink_y1)

        return (exact_x0, exact_y0, exact_x1, exact_y1)

    def verify_quantisation_smell(self, columns: Optional[List[ColumnModel]]) -> Dict[str, Any]:
        """Asserts that column widths are derived from genuine rule evidence and not snapped to multiples of 5/10 pt."""
        if not columns:
            return {"passed": True, "quantised_ratio": 0.0}

        multiples_of_5 = sum(1 for c in columns if abs(c.width_pt % 5.0) <= 0.01 or abs(c.width_pt % 10.0) <= 0.01)
        ratio = multiples_of_5 / len(columns)

        # Smell test: If >= 75% of widths are exact multiples of 5.0 pt, check if rule evidence exists
        has_real_evidence = all(len(c.left_boundary_evidence) > 0 for c in columns)
        is_suspicious = (ratio >= 0.75) and not has_real_evidence

        return {
            "passed": not is_suspicious,
            "quantised_ratio": round(ratio, 3),
            "warning": "Potential snapped_values: columns quantised to multiples of 5 pt" if is_suspicious else None
        }

    def build_dimension_lane(
        self,
        columns: Optional[List[ColumnModel]],
        table_bbox_pt: Tuple[float, float, float, float],
        heading_y0_pt: Optional[float] = None
    ) -> List[DimensionArrow]:
        """Builds rule-anchored dimension arrows positioned in dedicated lane above table header."""
        if not columns:
            return []

        tx0, ty0, tx1, ty1 = table_bbox_pt
        # Place lane above table top, leaving clearance for heading line
        lane_y = (heading_y0_pt - 14.0) if heading_y0_pt else (ty0 - 18.0)

        arrows: List[DimensionArrow] = []
        for c in columns:
            x0_inner = c.x0_pt
            x1_inner = c.x1_pt
            w = max(0.1, x1_inner - x0_inner)

            arr = DimensionArrow(
                column_index=c.index,
                left_rule_id=c.left_rule_id,
                right_rule_id=c.right_rule_id,
                x0_inner_pt=x0_inner,
                x1_inner_pt=x1_inner,
                width_pt=w,
                arrow_y_pt=lane_y,
                label_text=f"{w:.2f} pt"
            )
            arrows.append(arr)

        return arrows
