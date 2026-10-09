"""
Section 10: Multi-Signal Column Detection & Boundary Fusion Engine.
Collects 5 independent signals (S1-S5), fuses candidate boundaries with weighted voting,
handles double-stroke rules, partial rules, spanning headers, and validates column contiguity.
"""

from __future__ import annotations
import re
import logging
from typing import Dict, Any, List, Tuple, Optional, Set, Union
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import MultiUnitValue, TextSpanModel, ColumnModel
from pdf_analyzer.stages.frame import RuleSet, Rule
from pdf_analyzer.utils.units import create_multi_unit_value

logger = logging.getLogger(__name__)


class ColumnDetector:
    """Detects table columns via multi-signal weighted voting (S1-S5) and boundary fusion."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def detect_columns(
        self,
        table_spans: List[TextSpanModel],
        vector_paths: Union[List[Dict[str, Any]], RuleSet],
        table_bbox_pt: Tuple[float, float, float, float],
        page_w: float,
        page_h: float,
        page_num: int = 1,
        rule_set: Optional[RuleSet] = None
    ) -> Optional[List[ColumnModel]]:
        """Runs RuleSet-anchored column extraction, resolves rules, and builds ColumnModels."""
        tx0, ty0, tx1, ty1 = table_bbox_pt
        table_w = tx1 - tx0
        table_h = ty1 - ty0

        # Obtain authoritative RuleSet
        if isinstance(vector_paths, RuleSet):
            r_set = vector_paths
        elif rule_set is not None:
            r_set = rule_set
        else:
            r_set = RuleSet.from_drawings(page_num, vector_paths, page_w, page_h)

        # Filter vertical rules overlapping table y-range
        v_rules = [
            r for r in r_set.vertical_rules
            if not (r.end_pt < ty0 - 5.0 or r.start_pt > ty1 + 5.0)
        ]
        v_rules.sort(key=lambda r: r.centre_pt)

        if len(v_rules) < 2:
            logger.warning(f"Page {page_num}: Fewer than 2 vertical rules found ({len(v_rules)}). Returning columns=None without inventing columns.")
            return None

        # Deduplicate double strokes (closer than 3.0 pt or 3x width)
        deduped_rules = []
        double_rule_flags = {}
        for r in v_rules:
            if not deduped_rules:
                deduped_rules.append(r)
            else:
                if r.centre_pt - deduped_rules[-1].centre_pt < 3.0:
                    prev_r = deduped_rules[-1]
                    double_rule_flags[prev_r.rule_id] = True
                    double_rule_flags[r.rule_id] = True
                    if r.width_pt > prev_r.width_pt:
                        deduped_rules[-1] = r
                else:
                    deduped_rules.append(r)

        if len(deduped_rules) < 2:
            logger.warning(f"Page {page_num}: Deduplicated vertical rules < 2. Returning columns=None.")
            return None

        columns: List[ColumnModel] = []
        for i in range(len(deduped_rules) - 1):
            r_a = deduped_rules[i]
            r_b = deduped_rules[i + 1]

            assert r_a.rule_id in r_set.rules_by_id, f"Rule {r_a.rule_id} missing in RuleSet"
            assert r_b.rule_id in r_set.rules_by_id, f"Rule {r_b.rule_id} missing in RuleSet"

            x0 = r_a.painted_inner_edge_pt if i > 0 else r_a.painted_outer_edge_pt
            x1 = r_b.painted_outer_edge_pt if i + 1 < len(deduped_rules) - 1 else r_b.painted_inner_edge_pt
            col_w = max(0.1, x1 - x0)

            col_spans = [
                s for s in table_spans
                if ty0 <= s.ink_box.y0.pt <= ty0 + 35.0 and (x0 - 1.0 <= s.ink_box.x0.pt and s.ink_box.x1.pt <= x1 + 1.0)
            ]
            header_text = " ".join(s.text.strip() for s in sorted(col_spans, key=lambda s: s.ink_box.x0.pt))

            is_dbl = bool(double_rule_flags.get(r_a.rule_id) or double_rule_flags.get(r_b.rule_id))
            w_mu = create_multi_unit_value(col_w, page_w, self.config.dpi)
            col_model = ColumnModel(
                index=i,
                x0_pt=x0,
                x1_pt=x1,
                width_pt=col_w,
                width=w_mu,
                left_rule_id=r_a.rule_id,
                right_rule_id=r_b.rule_id,
                left_boundary_evidence=[{"rule_id": r_a.rule_id, "x": r_a.centre_pt, "weight": 1.0, "signal": "S1"}],
                right_boundary_evidence=[{"rule_id": r_b.rule_id, "x": r_b.centre_pt, "weight": 1.0, "signal": "S1"}],
                header_text=header_text,
                boundary_type="double" if is_dbl else "single",
                is_double_rule=is_dbl,
                double_rule_info={"is_double": True} if is_dbl else None,
                coverage_pct=1.0,
                confidence=1.0
            )
            columns.append(col_model)

        self._detect_spanning_headers(columns, table_spans, ty0)
        self._validate_and_repair_columns(columns, deduped_rules[0].painted_outer_edge_pt, deduped_rules[-1].painted_inner_edge_pt, page_w)
        return columns

    def _extract_s1_vertical_rules(
        self,
        vector_paths: List[Dict[str, Any]],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float,
        page_num: int
    ) -> List[Dict[str, Any]]:
        """Extract vertical rules, thin rects, and detect double strokes."""
        raw_rules: List[Dict[str, Any]] = []
        table_h = ty1 - ty0

        for path in vector_paths:
            bx0, by0, bx1, by1 = path.get("bbox", (0, 0, 0, 0))
            w = bx1 - bx0
            h = by1 - by0

            is_vert = (w <= 3.5 and h >= 15.0) or (path.get("type") == "line" and abs(bx1 - bx0) <= 2.0 and h >= 15.0)
            if not is_vert:
                continue

            iy0 = max(ty0 - 2.0, by0)
            iy1 = min(ty1 + 2.0, by1)
            if iy1 - iy0 < 10.0:
                continue

            cx = (bx0 + bx1) / 2.0
            if not (tx0 - 5.0 <= cx <= tx1 + 5.0):
                continue

            coverage = min(1.0, (iy1 - iy0) / max(1.0, table_h))
            raw_rules.append({
                "x": cx,
                "x0": bx0,
                "x1": bx1,
                "y0": iy0,
                "y1": iy1,
                "width": max(0.2, w),
                "coverage": coverage,
                "raw_path": path
            })

        raw_rules.sort(key=lambda r: r["x"])

        merged_rules: List[Dict[str, Any]] = []
        idx = 0
        rule_seq = 0

        while idx < len(raw_rules):
            r1 = raw_rules[idx]
            if idx + 1 < len(raw_rules):
                r2 = raw_rules[idx + 1]
                gap = r2["x0"] - r1["x1"]
                dist = r2["x"] - r1["x"]
                max_double_dist = max(3.0, 3.0 * max(r1["width"], r2["width"]))

                if 0.0 <= dist <= max_double_dist and abs(r1["coverage"] - r2["coverage"]) <= 0.4:
                    center_x = (r1["x"] + r2["x"]) / 2.0
                    merged_rules.append({
                        "x": center_x,
                        "weight": 1.0,
                        "signal": "S1",
                        "rule_id": f"rule_v_p{page_num}_{rule_seq}",
                        "boundary_type": "double",
                        "is_double_rule": True,
                        "double_rule_info": {
                            "center_x": round(center_x, 3),
                            "outer_width": round(r2["x1"] - r1["x0"], 3),
                            "inner_gap": round(max(0.0, gap), 3),
                            "stroke1_width": round(r1["width"], 3),
                            "stroke2_width": round(r2["width"], 3)
                        },
                        "coverage": max(r1["coverage"], r2["coverage"]),
                        "width": r1["width"] + r2["width"]
                    })
                    rule_seq += 1
                    idx += 2
                    continue

            merged_rules.append({
                "x": r1["x"],
                "weight": 1.0,
                "signal": "S1",
                "rule_id": f"rule_v_p{page_num}_{rule_seq}",
                "boundary_type": "single",
                "is_double_rule": False,
                "double_rule_info": None,
                "coverage": r1["coverage"],
                "width": r1["width"]
            })
            rule_seq += 1
            idx += 1

        return merged_rules

    def _extract_s2_header_edges(
        self,
        table_spans: List[TextSpanModel],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float
    ) -> List[Dict[str, Any]]:
        """Extract header text boundaries and whitespace between neighbouring header labels (Weight 0.6)."""
        header_spans = [s for s in table_spans if ty0 <= s.ink_box.y0.pt <= ty0 + 35.0]
        if not header_spans:
            return []

        candidates: List[Dict[str, Any]] = []
        sorted_spans = sorted(header_spans, key=lambda s: s.ink_box.x0.pt)

        for i, s in enumerate(sorted_spans):
            candidates.append({"x": s.ink_box.x0.pt, "weight": 0.6, "signal": "S2", "label": s.text})
            candidates.append({"x": s.ink_box.x1.pt, "weight": 0.6, "signal": "S2", "label": s.text})
            if i + 1 < len(sorted_spans):
                next_s = sorted_spans[i + 1]
                gap = next_s.ink_box.x0.pt - s.ink_box.x1.pt
                if gap >= 4.0:
                    mid_x = (s.ink_box.x1.pt + next_s.ink_box.x0.pt) / 2.0
                    candidates.append({"x": mid_x, "weight": 0.6, "signal": "S2_midpoint", "gap": gap})

        return candidates

    def _extract_s3_whitespace_gutters(
        self,
        table_spans: List[TextSpanModel],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float
    ) -> List[Dict[str, Any]]:
        """1D ink density projection onto the x-axis to find vertical whitespace gutters (Weight 0.5)."""
        bins_count = int(max(10, tx1 - tx0))
        density = np.zeros(bins_count, dtype=np.float32)

        for s in table_spans:
            sx0 = max(tx0, s.ink_box.x0.pt)
            sx1 = min(tx1, s.ink_box.x1.pt)
            if sx1 > sx0:
                i0 = int(sx0 - tx0)
                i1 = int(sx1 - tx0)
                density[max(0, i0):min(bins_count, i1 + 1)] += 1.0

        candidates: List[Dict[str, Any]] = []
        in_zero = False
        z_start = 0
        min_gutter_pt = getattr(self.config.tolerances, "column_gap_min_pt", 12.0)

        for i, d in enumerate(density):
            if d == 0.0 and not in_zero:
                in_zero = True
                z_start = i
            elif d > 0.0 and in_zero:
                in_zero = False
                gutter_w = i - z_start
                if gutter_w >= min_gutter_pt:
                    gutter_center_x = tx0 + (z_start + i) / 2.0
                    candidates.append({
                        "x": gutter_center_x,
                        "weight": 0.5,
                        "signal": "S3",
                        "gutter_width": float(gutter_w)
                    })

        return candidates

    def _extract_s4_numeric_axes(
        self,
        table_spans: List[TextSpanModel],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float
    ) -> List[Dict[str, Any]]:
        """Right-edge clusters of numeric tokens and decimal points (Weight 0.4)."""
        num_re = re.compile(r"^\s*[\d,]+(\.\d{2})?\s*$")
        num_right_edges: List[float] = []

        for s in table_spans:
            if num_re.match(s.text.strip()):
                num_right_edges.append(s.ink_box.x1.pt)

        if not num_right_edges:
            return []

        clusters = self._cluster_1d(num_right_edges, tol=1.0)
        candidates: List[Dict[str, Any]] = []
        for c in clusters:
            if len(c) >= 3:
                med_x = float(np.median(c))
                candidates.append({
                    "x": med_x + 2.0,
                    "weight": 0.4,
                    "signal": "S4",
                    "count": len(c)
                })

        return candidates

    def _extract_s5_left_edge_clusters(
        self,
        table_spans: List[TextSpanModel],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float
    ) -> List[Dict[str, Any]]:
        """Text left-edge clusters per column with tol 0.5 pt (Weight 0.3)."""
        left_edges = [s.ink_box.x0.pt for s in table_spans if tx0 - 2.0 <= s.ink_box.x0.pt <= tx1 + 2.0]
        if not left_edges:
            return []

        clusters = self._cluster_1d(left_edges, tol=0.5)
        candidates: List[Dict[str, Any]] = []
        for c in clusters:
            if len(c) >= 3:
                candidates.append({
                    "x": float(np.median(c)),
                    "weight": 0.3,
                    "signal": "S5",
                    "count": len(c)
                })

        return candidates

    def _fuse_signals(
        self,
        signals: Dict[str, List[Dict[str, Any]]],
        tx0: float,
        tx1: float,
        table_h: float
    ) -> List[Dict[str, Any]]:
        """Fuse candidate boundaries with weighted voting and rule prioritization."""
        tol = getattr(self.config.tolerances, "cluster_x_tol_pt", 1.0)
        s1_rules = signals.get("S1", [])
        boundaries: List[Dict[str, Any]] = []

        if s1_rules:
            for r in s1_rules:
                b_x = r["x"]
                evidence = [r]
                total_weight = r["weight"]

                for s_name, c_list in signals.items():
                    if s_name == "S1":
                        continue
                    for c in c_list:
                        if abs(c["x"] - b_x) <= tol + 2.0:
                            evidence.append(c)
                            total_weight += c["weight"]

                boundaries.append({
                    "x": b_x,
                    "rule_id": r.get("rule_id"),
                    "boundary_type": r.get("boundary_type", "single"),
                    "is_double_rule": r.get("is_double_rule", False),
                    "double_rule_info": r.get("double_rule_info"),
                    "coverage": r.get("coverage", 1.0),
                    "score": round(total_weight, 3),
                    "evidence": evidence
                })
        else:
            raw_candidates: List[Dict[str, Any]] = []
            for s_name, c_list in signals.items():
                raw_candidates.extend(c_list)

            sorted_c = sorted(raw_candidates, key=lambda c: c["x"])
            clusters: List[List[Dict[str, Any]]] = []
            for c in sorted_c:
                if not clusters:
                    clusters.append([c])
                else:
                    if abs(c["x"] - clusters[-1][-1]["x"]) <= tol * 2.0:
                        clusters[-1].append(c)
                    else:
                        clusters.append([c])

            for idx, cl in enumerate(clusters):
                med_x = float(np.median([c["x"] for c in cl]))
                tot_weight = sum(c.get("weight", 0.3) for c in cl)
                boundaries.append({
                    "x": med_x,
                    "rule_id": f"virtual_rule_{idx}",
                    "boundary_type": "virtual",
                    "is_double_rule": False,
                    "double_rule_info": None,
                    "coverage": 1.0,
                    "score": round(tot_weight, 3),
                    "evidence": cl
                })

        has_left = any(abs(b["x"] - tx0) <= 3.0 for b in boundaries)
        has_right = any(abs(b["x"] - tx1) <= 3.0 for b in boundaries)

        if not has_left:
            boundaries.insert(0, {
                "x": tx0,
                "rule_id": "rule_v_left_edge",
                "boundary_type": "virtual",
                "is_double_rule": False,
                "double_rule_info": None,
                "coverage": 1.0,
                "score": 1.0,
                "evidence": [{"signal": "table_bbox_left", "x": tx0}]
            })
        if not has_right:
            boundaries.append({
                "x": tx1,
                "rule_id": "rule_v_right_edge",
                "boundary_type": "virtual",
                "is_double_rule": False,
                "double_rule_info": None,
                "coverage": 1.0,
                "score": 1.0,
                "evidence": [{"signal": "table_bbox_right", "x": tx1}]
            })

        boundaries.sort(key=lambda b: b["x"])
        deduped: List[Dict[str, Any]] = [boundaries[0]]
        for b in boundaries[1:]:
            if b["x"] - deduped[-1]["x"] >= 8.0:
                deduped.append(b)
            else:
                if b["score"] > deduped[-1]["score"]:
                    deduped[-1] = b

        return deduped

    def _construct_columns(
        self,
        boundaries: List[Dict[str, Any]],
        table_spans: List[TextSpanModel],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float,
        page_w: float,
        page_num: int
    ) -> List[ColumnModel]:
        """Construct ColumnModel instances from fused boundaries."""
        columns: List[ColumnModel] = []

        for i in range(len(boundaries) - 1):
            b_left = boundaries[i]
            b_right = boundaries[i + 1]

            cx0 = b_left["x"]
            cx1 = b_right["x"]
            col_w = max(0.1, cx1 - cx0)

            col_spans = [
                s for s in table_spans
                if ty0 <= s.ink_box.y0.pt <= ty0 + 35.0 and (cx0 - 1.0 <= s.ink_box.x0.pt and s.ink_box.x1.pt <= cx1 + 1.0)
            ]
            header_text = " ".join(s.text.strip() for s in sorted(col_spans, key=lambda s: s.ink_box.x0.pt))

            b_type = "double" if (b_left.get("is_double_rule") or b_right.get("is_double_rule")) else (
                "single" if (b_left.get("boundary_type") == "single" or b_right.get("boundary_type") == "single") else "virtual"
            )

            w_mu = create_multi_unit_value(col_w, page_w, self.config.dpi)
            col_model = ColumnModel(
                index=i,
                x0_pt=cx0,
                x1_pt=cx1,
                width_pt=col_w,
                width=w_mu,
                left_rule_id=b_left.get("rule_id", f"rule_v_p{page_num}_{i}"),
                right_rule_id=b_right.get("rule_id", f"rule_v_p{page_num}_{i+1}"),
                left_boundary_evidence=b_left.get("evidence", []),
                right_boundary_evidence=b_right.get("evidence", []),
                header_text=header_text,
                boundary_type=b_type,
                is_double_rule=b_left.get("is_double_rule", False) or b_right.get("is_double_rule", False),
                double_rule_info=b_left.get("double_rule_info") or b_right.get("double_rule_info"),
                coverage_pct=min(b_left.get("coverage", 1.0), b_right.get("coverage", 1.0)),
                confidence=min(1.0, (b_left.get("score", 1.0) + b_right.get("score", 1.0)) / 2.0)
            )
            columns.append(col_model)

        return columns

    def _detect_spanning_headers(
        self,
        columns: List[ColumnModel],
        table_spans: List[TextSpanModel],
        ty0: float
    ) -> None:
        """Detect headers spanning 2 or more body columns."""
        header_spans = [s for s in table_spans if ty0 <= s.ink_box.y0.pt <= ty0 + 35.0]

        for s in header_spans:
            sx0 = s.ink_box.x0.pt
            sx1 = s.ink_box.x1.pt

            covered_cols: List[int] = []
            for col in columns:
                if max(sx0, col.x0_pt) < min(sx1, col.x1_pt) - 4.0:
                    covered_cols.append(col.index)

            if len(covered_cols) >= 2:
                for c_idx in covered_cols:
                    columns[c_idx].is_spanning_header = True
                    columns[c_idx].child_column_indices = covered_cols

    def _validate_and_repair_columns(
        self,
        columns: List[ColumnModel],
        tx0: float,
        tx1: float,
        page_w: float
    ) -> None:
        """Assert column contiguity and table width closure with auto-repair."""
        if not columns:
            return

        columns[0].x0_pt = tx0
        columns[0].width_pt = max(0.1, columns[0].x1_pt - columns[0].x0_pt)
        columns[0].width = create_multi_unit_value(columns[0].width_pt, page_w, self.config.dpi)

        columns[-1].x1_pt = tx1
        columns[-1].width_pt = max(0.1, columns[-1].x1_pt - columns[-1].x0_pt)
        columns[-1].width = create_multi_unit_value(columns[-1].width_pt, page_w, self.config.dpi)

    def _cluster_1d(self, values: List[float], tol: float = 1.0) -> List[List[float]]:
        if not values:
            return []
        sorted_v = sorted(values)
        clusters: List[List[float]] = [[sorted_v[0]]]
        for v in sorted_v[1:]:
            if v - clusters[-1][-1] <= tol:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return clusters
