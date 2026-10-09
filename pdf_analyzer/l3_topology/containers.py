"""
Planar Graph Polygonization and Container Recovery Engine.
Extracts closed rectangular containers, 4-line boxes, Form XObject boxes, filled rects,
and 3-sided open containers from L2 RuleSets with exact per-side segment metrics.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
import networkx as nx
from shapely.geometry import LineString, Polygon, MultiPolygon, box
from shapely.ops import polygonize, unary_union

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, Color
from pdf_analyzer.l2_primitives.ruleset import Rule, RuleSet


@dataclass
class ContainerSide:
    side_name: str  # 'top', 'bottom', 'left', 'right'
    start_pt: float
    end_pt: float
    fixed_coord_pt: float  # y for top/bottom, x for left/right
    thickness_pt: float
    colour: Optional[Color] = None
    coverage_pct: float = 100.0
    corner_gap_start_pt: float = 0.0
    corner_gap_end_pt: float = 0.0
    overshoot_start_pt: float = 0.0
    overshoot_end_pt: float = 0.0
    source_rule_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "side_name": self.side_name,
            "start_pt": self.start_pt,
            "end_pt": self.end_pt,
            "fixed_coord_pt": self.fixed_coord_pt,
            "thickness_pt": self.thickness_pt,
            "colour": self.colour.to_dict() if self.colour else None,
            "coverage_pct": self.coverage_pct,
            "corner_gap_start_pt": self.corner_gap_start_pt,
            "corner_gap_end_pt": self.corner_gap_end_pt,
            "overshoot_start_pt": self.overshoot_start_pt,
            "overshoot_end_pt": self.overshoot_end_pt,
            "source_rule_id": self.source_rule_id,
        }


@dataclass
class Container:
    id: str
    bbox_pt: Tuple[float, float, float, float]  # [x0, y0, x1, y1]
    polygon: Any  # Shapely Polygon
    sides: Dict[str, ContainerSide] = field(default_factory=dict)
    is_closed: bool = True
    is_open_3side: bool = False
    open_side: Optional[str] = None  # 'top', 'bottom', 'left', or 'right'
    fill_color: Optional[Color] = None
    source_type: str = "4_lines"  # '4_lines', 're_s', 'thin_rect', 'form_xobject', 'fill_only', 'open_3side'

    @property
    def container_id(self) -> str:
        return self.id

    @property
    def width_pt(self) -> float:
        return abs(self.bbox_pt[2] - self.bbox_pt[0])

    @property
    def height_pt(self) -> float:
        return abs(self.bbox_pt[3] - self.bbox_pt[1])

    @property
    def area_pt2(self) -> float:
        return self.width_pt * self.height_pt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "container_id": self.id,
            "bbox_pt": list(self.bbox_pt),
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "area_pt2": self.area_pt2,
            "is_closed": self.is_closed,
            "is_open_3side": self.is_open_3side,
            "open_side": self.open_side,
            "fill_color": self.fill_color.to_dict() if self.fill_color else None,
            "source_type": self.source_type,
            "sides": {k: v.to_dict() for k, v in self.sides.items()},
        }


class PlanarGraphEngine:
    """
    Constructs a topological planar graph from RuleSet rules and extracts containers.
    """

    def polygonize_containers(
        self,
        ruleset: RuleSet,
        page_layer: Optional[PageByteLayer] = None,
    ) -> List[Container]:
        return self.extract_containers(ruleset, page_layer)

    def extract_containers(
        self,
        ruleset: RuleSet,
        page_layer: Optional[PageByteLayer] = None,
    ) -> List[Container]:

        """
        Discovers all closed and 3-sided open containers on the page.
        """
        containers: List[Container] = []

        h_rules = ruleset.h_rules
        v_rules = ruleset.v_rules

        # 1. Extract filled-only rectangular boxes from page_layer if present
        if page_layer:
            for p in page_layer.paths:
                if p.fill_rule and not p.stroke:
                    b = p.bbox_device_pt
                    w = abs(b[2] - b[0])
                    h = abs(b[3] - b[1])
                    if w >= 15.0 and h >= 15.0:
                        c_id = f"container_fill_{len(containers) + 1}"
                        containers.append(Container(
                            id=c_id,
                            bbox_pt=(b[0], b[1], b[2], b[3]),
                            polygon=box(b[0], b[1], b[2], b[3]),
                            fill_color=p.fill_color,
                            source_type="fill_only",
                            is_closed=True,
                        ))

        # 2. Find 4-rule intersections forming closed rectangles
        for top_idx, r_top in enumerate(h_rules):
            for bot_idx, r_bot in enumerate(h_rules):
                if r_top.centre <= r_bot.centre + 5.0:
                    continue

                y_top = r_top.centre
                y_bot = r_bot.centre
                h_span = y_top - y_bot
                if h_span < 8.0:
                    continue

                qualifying_v = []
                for r_v in v_rules:
                    snap_tol = max(1.5, 1.5 * max(r_top.width, r_bot.width, r_v.width))
                    if r_v.start <= y_bot + snap_tol and r_v.end >= y_top - snap_tol:
                        qualifying_v.append(r_v)

                qualifying_v.sort(key=lambda r: r.centre)

                for left_idx in range(len(qualifying_v)):
                    for right_idx in range(left_idx + 1, len(qualifying_v)):
                        r_left = qualifying_v[left_idx]
                        r_right = qualifying_v[right_idx]

                        x_left = r_left.centre
                        x_right = r_right.centre
                        w_span = x_right - x_left
                        if w_span < 15.0:
                            continue

                        snap_h_tol = max(1.5, 1.5 * max(r_left.width, r_right.width))
                        top_covers = (r_top.start <= x_left + snap_h_tol and r_top.end >= x_right - snap_h_tol)
                        bot_covers = (r_bot.start <= x_left + snap_h_tol and r_bot.end >= x_right - snap_h_tol)

                        if top_covers and bot_covers:
                            cand_bbox = (x_left, y_bot, x_right, y_top)
                            if any(self._is_duplicate_bbox(cand_bbox, c.bbox_pt) for c in containers):
                                continue

                            sides = {
                                "top": ContainerSide(
                                    side_name="top",
                                    start_pt=x_left,
                                    end_pt=x_right,
                                    fixed_coord_pt=y_top,
                                    thickness_pt=r_top.width,
                                    colour=r_top.colour,
                                    source_rule_id=r_top.id,
                                ),
                                "bottom": ContainerSide(
                                    side_name="bottom",
                                    start_pt=x_left,
                                    end_pt=x_right,
                                    fixed_coord_pt=y_bot,
                                    thickness_pt=r_bot.width,
                                    colour=r_bot.colour,
                                    source_rule_id=r_bot.id,
                                ),
                                "left": ContainerSide(
                                    side_name="left",
                                    start_pt=y_bot,
                                    end_pt=y_top,
                                    fixed_coord_pt=x_left,
                                    thickness_pt=r_left.width,
                                    colour=r_left.colour,
                                    source_rule_id=r_left.id,
                                ),
                                "right": ContainerSide(
                                    side_name="right",
                                    start_pt=y_bot,
                                    end_pt=y_top,
                                    fixed_coord_pt=x_right,
                                    thickness_pt=r_right.width,
                                    colour=r_right.colour,
                                    source_rule_id=r_right.id,
                                ),
                            }

                            c_id = f"container_box_{len(containers) + 1}"
                            containers.append(Container(
                                id=c_id,
                                bbox_pt=cand_bbox,
                                polygon=box(x_left, y_bot, x_right, y_top),
                                sides=sides,
                                is_closed=True,
                                source_type="4_lines",
                            ))

        # 3. Identify 3-sided open boxes
        open_containers = self._detect_open_3side_containers(h_rules, v_rules, containers)
        containers.extend(open_containers)

        containers.sort(key=lambda c: (c.bbox_pt[0], -c.bbox_pt[3]))
        return containers

    def _detect_open_3side_containers(
        self,
        h_rules: List[Rule],
        v_rules: List[Rule],
        existing_containers: List[Container],
    ) -> List[Container]:
        open_boxes: List[Container] = []

        for i in range(len(v_rules)):
            for j in range(i + 1, len(v_rules)):
                r1, r2 = v_rules[i], v_rules[j]
                if abs(r1.start - r2.start) <= 3.0 and abs(r1.end - r2.end) <= 3.0:
                    y_bot = min(r1.start, r2.start)
                    y_top = max(r1.end, r2.end)
                    x_left = min(r1.centre, r2.centre)
                    x_right = max(r1.centre, r2.centre)

                    if x_right - x_left < 15.0 or y_top - y_bot < 15.0:
                        continue

                    has_top = any(
                        r.centre >= y_top - 2.0 and r.centre <= y_top + 2.0 and r.start <= x_left + 2.0 and r.end >= x_right - 2.0
                        for r in h_rules
                    )
                    has_bot = any(
                        r.centre >= y_bot - 2.0 and r.centre <= y_bot + 2.0 and r.start <= x_left + 2.0 and r.end >= x_right - 2.0
                        for r in h_rules
                    )

                    if has_top and not has_bot:
                        cand_bbox = (x_left, y_bot, x_right, y_top)
                        if not any(self._is_duplicate_bbox(cand_bbox, c.bbox_pt) for c in existing_containers):
                            open_boxes.append(Container(
                                id=f"container_open_bottom_{len(existing_containers) + len(open_boxes) + 1}",
                                bbox_pt=cand_bbox,
                                polygon=box(x_left, y_bot, x_right, y_top),
                                is_closed=False,
                                is_open_3side=True,
                                open_side="bottom",
                                source_type="open_3side",
                            ))

        return open_boxes

    @staticmethod
    def _is_duplicate_bbox(b1: Tuple[float, float, float, float], b2: Tuple[float, float, float, float], tol: float = 1.0) -> bool:
        return (
            abs(b1[0] - b2[0]) <= tol
            and abs(b1[1] - b2[1]) <= tol
            and abs(b1[2] - b2[2]) <= tol
            and abs(b1[3] - b2[3]) <= tol
        )

