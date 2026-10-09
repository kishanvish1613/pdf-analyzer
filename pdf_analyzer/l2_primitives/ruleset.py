"""
L2 Rule and RuleSet Engine.
Built strictly from L0 ByteLayer primitives. Merges collinear overlapping stroke segments
within 0.15 pt tolerance, fuses parallel double-stroke rules, and extracts thin filled rects.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedPath, Color, StreamProvenance


@dataclass
class Rule:
    id: str
    orientation: str  # 'H' or 'V'
    centre: float  # X coordinate for V rule, Y coordinate for H rule
    painted_outer: float  # Outer bounding extent
    painted_inner: float  # Inner bounding extent
    start: float  # Min coordinate along the rule span (y_min for V, x_min for H)
    end: float  # Max coordinate along the rule span (y_max for V, x_max for H)
    width: float  # Stroke width or thin-rect thickness
    cap: int = 0  # 0: Butt, 1: Round, 2: Projecting Square
    colour: Optional[Color] = None
    byte_provenance: Optional[StreamProvenance] = None
    is_double: bool = False
    double_gap: float = 0.0
    stroke1_width: float = 0.0
    stroke2_width: float = 0.0
    sub_segments: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def span(self) -> float:
        return abs(self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "orientation": self.orientation,
            "centre": self.centre,
            "painted_outer": self.painted_outer,
            "painted_inner": self.painted_inner,
            "start": self.start,
            "end": self.end,
            "width": self.width,
            "span": self.span,
            "cap": self.cap,
            "colour": self.colour.to_dict() if self.colour else None,
            "byte_provenance": self.byte_provenance.to_dict() if self.byte_provenance else None,
            "is_double": self.is_double,
            "double_gap": self.double_gap,
            "stroke1_width": self.stroke1_width,
            "stroke2_width": self.stroke2_width,
            "sub_segments_count": len(self.sub_segments),
        }


def color_luminance(c: Optional[Color]) -> float:
    if not c:
        return 0.0
    r, g, b = c.rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


@dataclass
class RuleSet:
    page_number: int
    width_pt: float
    height_pt: float
    h_rules: List[Rule] = field(default_factory=list)
    v_rules: List[Rule] = field(default_factory=list)

    @classmethod
    def from_page_layer(cls, page_layer: PageByteLayer) -> RuleSet:
        """
        Constructs the canonical RuleSet for a page strictly from L0 ByteLayer primitives.
        """
        ruleset = cls(
            page_number=page_layer.page_number,
            width_pt=page_layer.width_pt,
            height_pt=page_layer.height_pt,
        )

        raw_h_segments: List[Rule] = []
        raw_v_segments: List[Rule] = []

        # 1. Extract raw line and rect segments from L0 paths
        for path in page_layer.paths:
            # Check color luminance: skip pale shading/backgrounds (>0.85)
            col = path.stroke_color or path.fill_color
            if col and color_luminance(col) > 0.85:
                continue

            cap_style = path.stroke.cap if path.stroke else 0
            stroke_w = path.stroke.width_pt if path.stroke else (
                min(abs(path.bbox_device_pt[2] - path.bbox_device_pt[0]),
                    abs(path.bbox_device_pt[3] - path.bbox_device_pt[1]))
                if path.fill_rule else 0.5
            )

            # (A) Thin filled rectangles
            if path.fill_rule:
                b = path.bbox_device_pt
                w = abs(b[2] - b[0])
                h = abs(b[3] - b[1])
                if w <= 3.0 and h >= 5.0:  # Thin vertical rect rule
                    center_x = (b[0] + b[2]) / 2.0
                    r = Rule(
                        id=f"rule_v_{path.path_id}",
                        orientation="V",
                        centre=center_x,
                        painted_outer=b[2],
                        painted_inner=b[0],
                        start=min(b[1], b[3]),
                        end=max(b[1], b[3]),
                        width=w,
                        cap=0,
                        colour=path.fill_color,
                        byte_provenance=path.provenance,
                        sub_segments=[{"path_id": path.path_id, "bbox": list(b)}],
                    )
                    raw_v_segments.append(r)
                elif h <= 3.0 and w >= 5.0:  # Thin horizontal rect rule
                    center_y = (b[1] + b[3]) / 2.0
                    r = Rule(
                        id=f"rule_h_{path.path_id}",
                        orientation="H",
                        centre=center_y,
                        painted_outer=b[3],
                        painted_inner=b[1],
                        start=min(b[0], b[2]),
                        end=max(b[0], b[2]),
                        width=h,
                        cap=0,
                        colour=path.fill_color,
                        byte_provenance=path.provenance,
                        sub_segments=[{"path_id": path.path_id, "bbox": list(b)}],
                    )
                    raw_h_segments.append(r)
                continue

            # (B) Stroked vector paths
            if not path.stroke:
                continue

            for seg_idx, seg in enumerate(path.segments):
                if seg[0] == "re":
                    rx, ry, rw, rh = float(seg[1]), float(seg[2]), float(seg[3]), float(seg[4])
                    if rw <= 3.0 and rh >= 5.0:
                        raw_v_segments.append(Rule(
                            id=f"rule_v_{path.path_id}_re",
                            orientation="V",
                            centre=rx + rw / 2.0,
                            painted_outer=rx + rw,
                            painted_inner=rx,
                            start=min(ry, ry + rh),
                            end=max(ry, ry + rh),
                            width=rw,
                            cap=cap_style,
                            colour=path.stroke_color,
                            byte_provenance=path.provenance,
                        ))
                    elif rh <= 3.0 and rw >= 5.0:
                        raw_h_segments.append(Rule(
                            id=f"rule_h_{path.path_id}_re",
                            orientation="H",
                            centre=ry + rh / 2.0,
                            painted_outer=ry + rh,
                            painted_inner=ry,
                            start=min(rx, rx + rw),
                            end=max(rx, rx + rw),
                            width=rh,
                            cap=cap_style,
                            colour=path.stroke_color,
                            byte_provenance=path.provenance,
                        ))
                    else:
                        # 4 sides of stroked rectangle
                        raw_h_segments.append(Rule(
                            id=f"rule_h_{path.path_id}_b",
                            orientation="H",
                            centre=ry,
                            painted_outer=ry + stroke_w / 2.0,
                            painted_inner=ry - stroke_w / 2.0,
                            start=min(rx, rx + rw),
                            end=max(rx, rx + rw),
                            width=stroke_w,
                            cap=cap_style,
                            colour=path.stroke_color,
                            byte_provenance=path.provenance,
                        ))
                        raw_h_segments.append(Rule(
                            id=f"rule_h_{path.path_id}_t",
                            orientation="H",
                            centre=ry + rh,
                            painted_outer=ry + rh + stroke_w / 2.0,
                            painted_inner=ry + rh - stroke_w / 2.0,
                            start=min(rx, rx + rw),
                            end=max(rx, rx + rw),
                            width=stroke_w,
                            cap=cap_style,
                            colour=path.stroke_color,
                            byte_provenance=path.provenance,
                        ))
                        raw_v_segments.append(Rule(
                            id=f"rule_v_{path.path_id}_l",
                            orientation="V",
                            centre=rx,
                            painted_outer=rx - stroke_w / 2.0,
                            painted_inner=rx + stroke_w / 2.0,
                            start=min(ry, ry + rh),
                            end=max(ry, ry + rh),
                            width=stroke_w,
                            cap=cap_style,
                            colour=path.stroke_color,
                            byte_provenance=path.provenance,
                        ))
                        raw_v_segments.append(Rule(
                            id=f"rule_v_{path.path_id}_r",
                            orientation="V",
                            centre=rx + rw,
                            painted_outer=rx + rw + stroke_w / 2.0,
                            painted_inner=rx + rw - stroke_w / 2.0,
                            start=min(ry, ry + rh),
                            end=max(ry, ry + rh),
                            width=stroke_w,
                            cap=cap_style,
                            colour=path.stroke_color,
                            byte_provenance=path.provenance,
                        ))
                elif seg[0] == "l" and len(path.segments) >= 2:
                    # Find previous point
                    prev_seg = path.segments[seg_idx - 1] if seg_idx > 0 else path.segments[0]
                    if prev_seg[0] in ("m", "l"):
                        x0, y0 = float(prev_seg[1]), float(prev_seg[2])
                        x1, y1 = float(seg[1]), float(seg[2])
                        if abs(x1 - x0) <= 0.2 and abs(y1 - y0) >= 4.0:  # Vertical line
                            c_x = (x0 + x1) / 2.0
                            raw_v_segments.append(Rule(
                                id=f"rule_v_{path.path_id}_{seg_idx}",
                                orientation="V",
                                centre=c_x,
                                painted_outer=c_x + stroke_w / 2.0,
                                painted_inner=c_x - stroke_w / 2.0,
                                start=min(y0, y1),
                                end=max(y0, y1),
                                width=stroke_w,
                                cap=cap_style,
                                colour=path.stroke_color,
                                byte_provenance=path.provenance,
                            ))
                        elif abs(y1 - y0) <= 0.2 and abs(x1 - x0) >= 4.0:  # Horizontal line
                            c_y = (y0 + y1) / 2.0
                            raw_h_segments.append(Rule(
                                id=f"rule_h_{path.path_id}_{seg_idx}",
                                orientation="H",
                                centre=c_y,
                                painted_outer=c_y + stroke_w / 2.0,
                                painted_inner=c_y - stroke_w / 2.0,
                                start=min(x0, x1),
                                end=max(x0, x1),
                                width=stroke_w,
                                cap=cap_style,
                                colour=path.stroke_color,
                                byte_provenance=path.provenance,
                            ))

        # 2. Merge collinear overlapping segments (tol 0.15 pt)
        merged_h = cls._merge_collinear_segments(raw_h_segments, orientation="H", identity_tol_pt=0.15)
        merged_v = cls._merge_collinear_segments(raw_v_segments, orientation="V", identity_tol_pt=0.15)

        # 3. Fuse parallel double-stroke rules (gap <= 3 pt or 3x width)
        fused_h = cls._fuse_double_stroke_rules(merged_h, orientation="H")
        fused_v = cls._fuse_double_stroke_rules(merged_v, orientation="V")

        ruleset.h_rules = fused_h
        ruleset.v_rules = fused_v
        return ruleset

    @staticmethod
    def _merge_collinear_segments(
        segments: List[Rule],
        orientation: str,
        identity_tol_pt: float = 0.15,
    ) -> List[Rule]:
        """
        Groups segments by coordinate position (within identity_tol_pt) and merges
        overlapping or contiguous interval spans.
        """
        if not segments:
            return []

        # Group by centre position
        segments.sort(key=lambda r: r.centre)
        clusters: List[List[Rule]] = []

        for seg in segments:
            placed = False
            for cluster in clusters:
                if abs(cluster[0].centre - seg.centre) <= identity_tol_pt:
                    cluster.append(seg)
                    placed = True
                    break
            if not placed:
                clusters.append([seg])

        merged_rules: List[Rule] = []

        for cluster in clusters:
            avg_centre = float(np.mean([r.centre for r in cluster]))
            max_width = max([r.width for r in cluster])
            cap = cluster[0].cap
            colour = cluster[0].colour
            prov = cluster[0].byte_provenance

            # Sort spans by start
            spans = sorted([(r.start, r.end, r) for r in cluster], key=lambda s: s[0])
            merged_spans: List[Tuple[float, float, List[Dict[str, Any]]]] = []

            for s_start, s_end, r_item in spans:
                if not merged_spans:
                    merged_spans.append((s_start, s_end, list(r_item.sub_segments)))
                else:
                    last_start, last_end, last_subs = merged_spans[-1]
                    if s_start <= last_end + identity_tol_pt:
                        new_end = max(last_end, s_end)
                        merged_spans[-1] = (last_start, new_end, last_subs + r_item.sub_segments)
                    else:
                        merged_spans.append((s_start, s_end, list(r_item.sub_segments)))

            for idx, (m_start, m_end, m_subs) in enumerate(merged_spans):
                rule_id = f"rule_{orientation.lower()}_{len(merged_rules) + 1}"
                merged_rules.append(Rule(
                    id=rule_id,
                    orientation=orientation,
                    centre=avg_centre,
                    painted_outer=avg_centre + max_width / 2.0,
                    painted_inner=avg_centre - max_width / 2.0,
                    start=m_start,
                    end=m_end,
                    width=max_width,
                    cap=cap,
                    colour=colour,
                    byte_provenance=prov,
                    sub_segments=m_subs,
                ))

        merged_rules.sort(key=lambda r: (r.centre, r.start))
        return merged_rules

    @staticmethod
    def _fuse_double_stroke_rules(
        rules: List[Rule],
        orientation: str,
    ) -> List[Rule]:
        """
        Fuses two parallel rules closer than 3.0 pt or 3x width with overlapping spans.
        """
        if len(rules) < 2:
            return rules

        fused: List[Rule] = []
        skip_indices = set()

        for i in range(len(rules)):
            if i in skip_indices:
                continue
            r1 = rules[i]
            matched = False

            for j in range(i + 1, len(rules)):
                if j in skip_indices:
                    continue
                r2 = rules[j]
                gap = abs(r2.centre - r1.centre)
                max_allowed_gap = max(3.0, 3.0 * max(r1.width, r2.width))

                if gap <= max_allowed_gap:
                    overlap_start = max(r1.start, r2.start)
                    overlap_end = min(r1.end, r2.end)
                    if overlap_end - overlap_start >= 10.0:
                        fused_centre = (r1.centre + r2.centre) / 2.0
                        total_width = abs(r2.painted_outer - r1.painted_inner) if r2.centre > r1.centre else abs(r1.painted_outer - r2.painted_inner)
                        inner_gap = gap - (r1.width + r2.width) / 2.0

                        fused_rule = Rule(
                            id=f"rule_double_{orientation.lower()}_{len(fused) + 1}",
                            orientation=orientation,
                            centre=fused_centre,
                            painted_outer=max(r1.painted_outer, r2.painted_outer),
                            painted_inner=min(r1.painted_inner, r2.painted_inner),
                            start=min(r1.start, r2.start),
                            end=max(r1.end, r2.end),
                            width=total_width,
                            cap=r1.cap,
                            colour=r1.colour,
                            byte_provenance=r1.byte_provenance,
                            is_double=True,
                            double_gap=max(0.0, inner_gap),
                            stroke1_width=r1.width,
                            stroke2_width=r2.width,
                            sub_segments=r1.sub_segments + r2.sub_segments,
                        )
                        fused.append(fused_rule)
                        skip_indices.add(i)
                        skip_indices.add(j)
                        matched = True
                        break

            if not matched:
                fused.append(r1)

        fused.sort(key=lambda r: (r.centre, r.start))
        return fused

    @property
    def rules(self) -> List[Rule]:
        return self.h_rules + self.v_rules

    def get_rule_by_id(self, rule_id: str) -> Optional[Rule]:
        return self.get_v_rule_by_id(rule_id) or self.get_h_rule_by_id(rule_id)

    def get_v_rule_by_id(self, rule_id: str) -> Optional[Rule]:
        for r in self.v_rules:
            if r.id == rule_id:
                return r
        return None

    def get_h_rule_by_id(self, rule_id: str) -> Optional[Rule]:
        for r in self.h_rules:
            if r.id == rule_id:
                return r
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "h_rules_count": len(self.h_rules),
            "v_rules_count": len(self.v_rules),
            "h_rules": [r.to_dict() for r in self.h_rules],
            "v_rules": [r.to_dict() for r in self.v_rules],
        }

