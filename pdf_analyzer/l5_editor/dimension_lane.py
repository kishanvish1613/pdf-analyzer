"""
L5 Dimension Lane Engine (E9, E11, Phase 8B Tasks 1 & 2, Phase 8C-FIX Task F5).
Constructs the canonical dimension lane with multi-candidate search and strict spatial constraints:
- Candidate search: Free ink-free band ABOVE table within 60 pt, band BELOW table within 60 pt,
  else DOCKED_STRIP in padded canvas with NUMBERED MARKERS (1..N) on the table top edge.
- Extension lines <= 12 pt, strictly tested against all ink boxes using shapely.strtree.STRtree.
- Zero intersection invariant with content ink asserted.
- Virtual column support: filled_header/horizontal_only/borderless produce virtual columns and
  docked strip numbered markers (1..N) with values in Dimensions panel.
- Suppresses lane ONLY when table has zero body rows or fewer than 2 boundaries, with visible reason.
- Invariant: arrows == columns and sum(arrow widths) + interior rule widths == table outer width +-0.25 pt.
- Draggable lane vertical offset support.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np

from shapely.geometry import box as shapely_box, LineString
from shapely.strtree import STRtree

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, PaintedPath
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.table_grid import TableGrid, ColumnModel

logger = logging.getLogger(__name__)


@dataclass
class DimensionArrow:
    column_index: int
    rule_id_a: str
    rule_id_b: str
    x0_pt: float
    x1_pt: float
    width_pt: float
    lane_y_pt: float
    label_text: str
    is_left_outer: bool = False
    is_right_outer: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_index": self.column_index,
            "rule_id_a": self.rule_id_a,
            "rule_id_b": self.rule_id_b,
            "rule_id_left": self.rule_id_a,
            "rule_id_right": self.rule_id_b,
            "x0_pt": self.x0_pt,
            "x1_pt": self.x1_pt,
            "start_x_pt": self.x0_pt,
            "end_x_pt": self.x1_pt,
            "width_pt": self.width_pt,
            "lane_y_pt": self.lane_y_pt,
            "label_text": self.label_text,
            "title": self.label_text,
            "is_left_outer": self.is_left_outer,
            "is_right_outer": self.is_right_outer,
        }


@dataclass
class ExtensionLine:
    rule_id: str
    x_pt: float
    y0_pt: float
    y1_pt: float
    is_outer: bool = False

    @property
    def length_pt(self) -> float:
        return abs(self.y1_pt - self.y0_pt)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "x_pt": self.x_pt,
            "y0_pt": self.y0_pt,
            "y1_pt": self.y1_pt,
            "length_pt": self.length_pt,
            "is_outer": self.is_outer,
        }


@dataclass
class NumberedMarker:
    column_index: int
    marker_label: str
    x_pt: float
    y_pt: float
    width_pt: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_index": self.column_index,
            "marker_label": self.marker_label,
            "x_pt": self.x_pt,
            "y_pt": self.y_pt,
            "width_pt": self.width_pt,
        }


@dataclass
class DimensionLaneModel:
    lane_id: str
    lane_y_pt: float
    candidate_chosen: str = "above"  # 'above' | 'below' | 'docked_strip'
    arrows: List[DimensionArrow] = field(default_factory=list)
    extension_lines: List[ExtensionLine] = field(default_factory=list)
    numbered_markers: List[NumberedMarker] = field(default_factory=list)
    user_offset_pt: float = 0.0
    total_table_width_pt: float = 0.0
    sum_arrow_widths_pt: float = 0.0
    interior_rule_widths_sum_pt: float = 0.0
    width_invariance_passed: bool = True
    columns_count: int = 0
    delta_pt: float = 0.0
    lane_absent_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "lane_y_pt": self.lane_y_pt,
            "candidate_chosen": self.candidate_chosen,
            "table_top_y_pt": self.lane_y_pt,
            "user_offset_pt": self.user_offset_pt,
            "arrows_count": len(self.arrows),
            "total_table_width_pt": self.total_table_width_pt,
            "table_outer_width_pt": self.total_table_width_pt,
            "sum_arrow_widths_pt": self.sum_arrow_widths_pt,
            "sum_widths_pt": self.sum_arrow_widths_pt,
            "interior_rule_widths_sum_pt": self.interior_rule_widths_sum_pt,
            "interior_rules_width_pt": self.interior_rule_widths_sum_pt,
            "width_invariance_passed": self.width_invariance_passed,
            "is_valid": self.width_invariance_passed,
            "delta_pt": self.delta_pt,
            "columns_count": self.columns_count,
            "lane_absent_reason": self.lane_absent_reason,
            "arrows": [a.to_dict() for a in self.arrows],
            "extension_lines": [e.to_dict() for e in self.extension_lines],
            "numbered_markers": [m.to_dict() for m in self.numbered_markers],
        }


class DimensionLaneEngine:
    """
    Constructs the canonical dimension lane with multi-candidate placement search,
    STRtree ink collision checking, virtual column support, and strict geometric assertions.
    """

    def _build_ink_strtree(self, page_layer: PageByteLayer) -> Tuple[STRtree, List[Any]]:
        """Constructs an STRtree over all painted character ink boxes and vector paths."""
        geoms = []
        for c in page_layer.chars:
            bx0, by0, bx1, by1 = c.font_bbox_device_pt
            if bx1 > bx0 and by1 > by0:
                geoms.append(shapely_box(bx0, by0, bx1, by1))

        for p in page_layer.paths:
            px0, py0, px1, py1 = p.bbox_device_pt
            if px1 > px0 and py1 > py0:
                geoms.append(shapely_box(px0, py0, px1, py1))

        if not geoms:
            geoms.append(shapely_box(0, 0, 0, 0))

        tree = STRtree(geoms)
        return tree, geoms

    def find_best_candidate_placement(
        self,
        page_layer: PageByteLayer,
        table_x_range: Tuple[float, float],
        table_top_y_pt: float,
        table_bottom_y_pt: float,
        tree: STRtree,
        geoms: List[Any],
    ) -> Tuple[str, float, bool]:
        """
        Searches candidates:
        1. Band ABOVE table top within 60 pt [t_y1, t_y1 + 60]
        2. Band BELOW table bottom within 60 pt [t_y0 - 60, t_y0]
        3. DOCKED_STRIP in padded canvas (fallback)
        Returns: (candidate_chosen, candidate_y, is_docked)
        """
        tx0, tx1 = table_x_range
        c_x0, c_y0, c_x1, c_y1 = page_layer.cropbox_pt
        page_h = c_y1 - c_y0

        # 1. Search candidate band ABOVE table top
        for offset in np.arange(8.0, 56.0, 4.0):
            cand_y = table_top_y_pt + offset
            if cand_y >= page_h - 10.0:
                break

            band_box = shapely_box(tx0 + 2.0, cand_y - 4.0, tx1 - 2.0, cand_y + 4.0)
            hits = tree.query(band_box)
            actual_hits = [idx for idx in hits if band_box.intersects(geoms[idx])]
            if len(actual_hits) == 0:
                return "above", float(cand_y), False

        # 2. Search candidate band BELOW table bottom
        for offset in np.arange(8.0, 56.0, 4.0):
            cand_y = table_bottom_y_pt - offset
            if cand_y <= 10.0:
                break

            band_box = shapely_box(tx0 + 2.0, cand_y - 4.0, tx1 - 2.0, cand_y + 4.0)
            hits = tree.query(band_box)
            actual_hits = [idx for idx in hits if band_box.intersects(geoms[idx])]
            if len(actual_hits) == 0:
                return "below", float(cand_y), False

        # 3. Fallback to Docked Strip mode
        docked_y = min(page_h - 12.0, table_top_y_pt + 24.0)
        return "docked_strip", float(docked_y), True

    def build_dimension_lane(
        self,
        table_grid: TableGrid,
        ruleset: RuleSet,
        page_layer: PageByteLayer,
        user_offset_pt: float = 0.0,
    ) -> DimensionLaneModel:
        cols = table_grid.columns
        num_cols = len(cols)

        # Suppress lane ONLY when table has no columns, fewer than 2 boundaries, or zero body rows
        if num_cols < 2 or len(table_grid.rows) == 0 or table_grid.body_rows_count == 0:
            reason = "lane_absent: Table has fewer than 2 column boundaries or zero body transaction rows"
            logger.warning(f"Page {page_layer.page_number} dimension lane omitted: {reason}")
            return DimensionLaneModel(
                lane_id=f"dim_lane_p{page_layer.page_number}",
                lane_y_pt=0.0,
                candidate_chosen="none",
                arrows=[],
                extension_lines=[],
                numbered_markers=[],
                user_offset_pt=0.0,
                total_table_width_pt=0.0,
                sum_arrow_widths_pt=0.0,
                interior_rule_widths_sum_pt=0.0,
                width_invariance_passed=True,
                columns_count=0,
                delta_pt=0.0,
                lane_absent_reason=reason,
            )

        t_x0, t_y0, t_x1, t_y1 = table_grid.table_bbox_pt
        total_table_width = t_x1 - t_x0

        # Build STRtree over ink boxes
        tree, geoms = self._build_ink_strtree(page_layer)

        # Find placement candidate
        cand_mode, cand_y, is_docked = self.find_best_candidate_placement(
            page_layer=page_layer,
            table_x_range=(t_x0, t_x1),
            table_top_y_pt=t_y1,
            table_bottom_y_pt=t_y0,
            tree=tree,
            geoms=geoms,
        )

        lane_y = cand_y + user_offset_pt

        rule_map: Dict[str, Rule] = {r.id: r for r in ruleset.v_rules}

        arrows: List[DimensionArrow] = []
        ext_lines: List[ExtensionLine] = []
        numbered_markers: List[NumberedMarker] = []

        interior_rules_sum = 0.0
        for col in cols[:-1]:
            if col.right_rule_id in rule_map:
                r = rule_map[col.right_rule_id]
                interior_rules_sum += r.width

        # In docked mode or virtual mode, generate numbered markers 1..N on table top edge
        if is_docked or table_grid.is_borderless:
            for i, col in enumerate(cols):
                mid_x = (col.x0_pt + col.x1_pt) / 2.0
                numbered_markers.append(NumberedMarker(
                    column_index=i + 1,
                    marker_label=str(i + 1),
                    x_pt=mid_x,
                    y_pt=t_y1,
                    width_pt=col.width_pt,
                ))

        for i, col in enumerate(cols):
            l_rule = rule_map.get(col.left_rule_id)
            r_rule = rule_map.get(col.right_rule_id)

            # Left endpoint
            if i == 0:
                x0 = (l_rule.centre - l_rule.width / 2.0) if l_rule else col.x0_pt
                if l_rule and not is_docked and not table_grid.is_borderless:
                    ext_y0 = min(lane_y, t_y1)
                    ext_y1 = max(lane_y, t_y1)
                    if abs(ext_y1 - ext_y0) <= 12.0:
                        ext_lines.append(ExtensionLine(
                            rule_id=l_rule.id,
                            x_pt=x0,
                            y0_pt=ext_y0,
                            y1_pt=ext_y1,
                            is_outer=True,
                        ))
            else:
                x0 = (l_rule.centre + l_rule.width / 2.0) if l_rule else col.x0_pt

            # Right endpoint
            if i == num_cols - 1:
                x1 = (r_rule.centre + r_rule.width / 2.0) if r_rule else col.x1_pt
                if r_rule and not is_docked and not table_grid.is_borderless:
                    ext_y0 = min(lane_y, t_y1)
                    ext_y1 = max(lane_y, t_y1)
                    if abs(ext_y1 - ext_y0) <= 12.0:
                        ext_lines.append(ExtensionLine(
                            rule_id=r_rule.id,
                            x_pt=x1,
                            y0_pt=ext_y0,
                            y1_pt=ext_y1,
                            is_outer=True,
                        ))
            else:
                x1 = (r_rule.centre - r_rule.width / 2.0) if r_rule else col.x1_pt
                if r_rule and not is_docked and not table_grid.is_borderless:
                    ext_y0 = min(lane_y, t_y1)
                    ext_y1 = max(lane_y, t_y1)
                    if abs(ext_y1 - ext_y0) <= 12.0:
                        ext_lines.append(ExtensionLine(
                            rule_id=r_rule.id,
                            x_pt=r_rule.centre,
                            y0_pt=ext_y0,
                            y1_pt=ext_y1,
                            is_outer=False,
                        ))

            width_pt = max(0.0, x1 - x0)
            label = f"{width_pt:.2f} pt"
            arrows.append(DimensionArrow(
                column_index=i + 1,
                rule_id_a=col.left_rule_id,
                rule_id_b=col.right_rule_id,
                x0_pt=x0,
                x1_pt=x1,
                width_pt=width_pt,
                lane_y_pt=lane_y,
                label_text=label,
                is_left_outer=(i == 0),
                is_right_outer=(i == num_cols - 1),
            ))

        # Test extension lines against STRtree
        valid_ext_lines: List[ExtensionLine] = []
        for ext in ext_lines:
            assert ext.length_pt <= 12.01, f"Extension line length {ext.length_pt:.2f} pt exceeds 12 pt limit"
            ext_geom = LineString([(ext.x_pt, ext.y0_pt), (ext.x_pt, ext.y1_pt)])
            hits = tree.query(ext_geom)
            has_ink_collision = False
            for h in hits:
                target_geom = geoms[h]
                if ext_geom.intersects(target_geom) and target_geom.area > 0.0:
                    inter = ext_geom.intersection(target_geom)
                    if inter.length > 0.1:
                        has_ink_collision = True
                        break

            assert not has_ink_collision, f"Extension line at x={ext.x_pt:.2f} intersects content ink box"
            valid_ext_lines.append(ext)

        # Enforce arrow count == column count invariant
        assert len(arrows) == num_cols, f"Mismatch: {len(arrows)} dimension arrows generated for {num_cols} columns"

        sum_arrows = sum(a.width_pt for a in arrows)
        computed_total = sum_arrows + interior_rules_sum
        delta = abs(computed_total - total_table_width)
        invariance_passed = (delta <= 0.25)

        return DimensionLaneModel(
            lane_id=f"dim_lane_p{page_layer.page_number}",
            lane_y_pt=lane_y,
            candidate_chosen=cand_mode,
            arrows=arrows,
            extension_lines=valid_ext_lines,
            numbered_markers=numbered_markers,
            user_offset_pt=user_offset_pt,
            total_table_width_pt=total_table_width,
            sum_arrow_widths_pt=sum_arrows,
            interior_rule_widths_sum_pt=interior_rules_sum,
            width_invariance_passed=invariance_passed,
            columns_count=num_cols,
            delta_pt=delta,
            lane_absent_reason=None,
        )
