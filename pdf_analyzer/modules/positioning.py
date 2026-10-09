"""
Module B: Exact Positioning & Alignment Analysis.
Implements:
1. Clipped Guide Line objects (strictly bounded by owner extent y0..y1 or x0..x1).
2. Cross-region implicit axis linkage (e.g. table heading aligned to key-value label column).
3. Exact cell centering offsets and modal alignment classification.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel, GuideLine
from pdf_analyzer.utils.units import create_multi_unit_value
from pdf_analyzer.utils.geometry import cluster_1d_coordinates


class PositioningAnalyzer:
    """Analyzes exact positions, alignments, implicit shared axes, and inter-element offsets."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def classify_horizontal_alignment(
        self,
        span_ink_bbox_pt: Tuple[float, float, float, float],
        container_bbox_pt: Tuple[float, float, float, float]
    ) -> Tuple[str, float]:
        """Classify alignment using ink box against container and compute offset from center in pt."""
        tol = self.config.tolerances.alignment_tolerance_pt
        cx0, cy0, cx1, cy1 = container_bbox_pt
        sx0, sy0, sx1, sy1 = span_ink_bbox_pt

        container_center_x = (cx0 + cx1) / 2.0
        span_center_x = (sx0 + sx1) / 2.0
        offset_from_center = span_center_x - container_center_x

        left_diff = abs(sx0 - cx0)
        right_diff = abs(cx1 - sx1)

        if left_diff <= tol and right_diff <= tol:
            return "justified", offset_from_center
        if left_diff <= tol * 2.0:
            return "left", offset_from_center
        if right_diff <= tol * 2.0:
            return "right", offset_from_center
        if abs(offset_from_center) <= self.config.tolerances.centering_tolerance_pt:
            return "center", offset_from_center

        if sx0 - cx0 < cx1 - sx1:
            return "left", offset_from_center
        return "right", offset_from_center

    def detect_shared_alignment_axes(
        self,
        spans: List[TextSpanModel],
        page_w: float,
        page_h: float
    ) -> Dict[str, Any]:
        """
        Cluster left edges, right edges, centers, and baselines with 0.5 pt strict tolerance.
        Produces clipped GuideLine objects strictly bounded to member element extents.
        """
        tol = self.config.tolerances.axis_cluster_tolerance_pt

        lefts = [(s.ink_box.x0.pt, s.ink_box.y0.pt, s.ink_box.y1.pt, s.text[:30]) for s in spans]
        rights = [(s.ink_box.x1.pt, s.ink_box.y0.pt, s.ink_box.y1.pt, s.text[:30]) for s in spans]
        centers = [((s.ink_box.x0.pt + s.ink_box.x1.pt) / 2.0, s.ink_box.y0.pt, s.ink_box.y1.pt, s.text[:30]) for s in spans]
        baselines = [(s.baseline_y.pt, s.ink_box.x0.pt, s.ink_box.x1.pt, s.text[:30]) for s in spans]

        left_clusters = self._cluster_with_extents(lefts, tol, axis_type="vertical")
        right_clusters = self._cluster_with_extents(rights, tol, axis_type="vertical")
        center_clusters = self._cluster_with_extents(centers, tol, axis_type="vertical")
        baseline_clusters = self._cluster_with_extents(baselines, tol, axis_type="horizontal")

        # Major Implicit Axes (>= 2 members sharing alignment coordinate)
        guide_lines: List[GuideLine] = []
        major_left = []
        for c in left_clusters:
            if c["count"] >= 2:
                g = GuideLine(
                    axis_type="vertical",
                    position_pt=c["coord"],
                    range_start_pt=c["range_start"],
                    range_end_pt=c["range_end"],
                    owner_id=f"left_axis_{int(c['coord'])}",
                    member_count=c["count"],
                    role="shared_left_edge"
                )
                guide_lines.append(g)
                major_left.append({
                    "x_pt": round(c["coord"], 3),
                    "y_start_pt": round(c["range_start"], 3),
                    "y_end_pt": round(c["range_end"], 3),
                    "member_count": c["count"],
                    "member_snippets": c["members"][:6],
                    "axis_type": "shared_left_edge",
                    "cross_region_links": [m for m in c["members"] if any(k in m.lower() for k in ["statement", "account", "from", "to", "date", "balance"])]
                })

        major_right = []
        for c in right_clusters:
            if c["count"] >= 2:
                g = GuideLine(
                    axis_type="vertical",
                    position_pt=c["coord"],
                    range_start_pt=c["range_start"],
                    range_end_pt=c["range_end"],
                    owner_id=f"right_axis_{int(c['coord'])}",
                    member_count=c["count"],
                    role="shared_right_edge"
                )
                guide_lines.append(g)
                major_right.append({
                    "x_pt": round(c["coord"], 3),
                    "y_start_pt": round(c["range_start"], 3),
                    "y_end_pt": round(c["range_end"], 3),
                    "member_count": c["count"],
                    "member_snippets": c["members"][:6],
                    "axis_type": "shared_right_edge"
                })

        return {
            "implicit_axes_detected": len(major_left) + len(major_right),
            "shared_left_axes": major_left,
            "shared_right_axes": major_right,
            "guide_lines": [g.to_dict() for g in guide_lines],
            "baselines_count": len(baseline_clusters)
        }

    def _cluster_with_extents(
        self,
        items: List[Tuple[float, float, float, str]],
        tol: float,
        axis_type: str
    ) -> List[Dict[str, Any]]:
        """Cluster items and compute bounding range (y0..y1 for vertical, x0..x1 for horizontal)."""
        if not items:
            return []
        sorted_items = sorted(items, key=lambda x: x[0])
        clusters: List[List[Tuple[float, float, float, str]]] = []
        cur_c = [sorted_items[0]]

        for it in sorted_items[1:]:
            if it[0] - cur_c[-1][0] <= tol:
                cur_c.append(it)
            else:
                clusters.append(cur_c)
                cur_c = [it]
        clusters.append(cur_c)

        result = []
        for c in clusters:
            coord = float(np.mean([x[0] for x in c]))
            r_start = min(x[1] for x in c)
            r_end = max(x[2] for x in c)
            members = [x[3] for x in c]
            result.append({
                "coord": coord,
                "range_start": r_start,
                "range_end": r_end,
                "count": len(c),
                "members": members
            })
        return sorted(result, key=lambda x: -x["count"])

