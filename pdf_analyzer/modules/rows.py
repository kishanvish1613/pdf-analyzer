"""
Section 11: Multi-Model Row Detection & Selection Engine.
Runs 5 independent row models (R1-R5):
  R1: Ruled rows (horizontal rules >= 80% width)
  R2: Zebra/fill rows (alternating colored rects)
  R3: Anchor rows (auto-picked anchor column via date / SNO regex & monotonicity)
  R4: Whitespace valleys (1D vertical ink projection valleys)
  R5: Pitch periodicity (baseline autocorrelation & pitch clusters)
Evaluates agreement scores, selects best model + runner-up, classifies row semantics,
builds contiguous row models, and enforces chain closure.
"""

from __future__ import annotations
import re
import logging
from typing import Dict, Any, List, Tuple, Optional, Set
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import MultiUnitValue, TextSpanModel, ColumnModel, RowModel
from pdf_analyzer.utils.units import create_multi_unit_value
from pdf_analyzer.utils.geometry import bbox_iou

logger = logging.getLogger(__name__)


class RowDetector:
    """Evaluates R1-R5 row models, scores agreement/completeness, and outputs validated RowModels."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def detect_rows(
        self,
        table_spans: List[TextSpanModel],
        vector_paths: List[Dict[str, Any]],
        columns: Optional[List[ColumnModel]],
        table_bbox_pt: Tuple[float, float, float, float],
        page_w: float,
        page_h: float,
        page_num: int = 1
    ) -> Dict[str, Any]:
        """Runs all 5 row models, scores agreement, chooses best model, and constructs RowModel list."""
        tx0, ty0, tx1, ty1 = table_bbox_pt
        table_w = tx1 - tx0
        table_h = ty1 - ty0
        cols = columns or []

        # Sort table spans by y coordinate then x
        sorted_spans = sorted(table_spans, key=lambda s: (s.ink_box.y0.pt, s.ink_box.x0.pt))

        # ---------------------------------------------------------
        # Model R1: Ruled Rows (Horizontal Rules >= 80% Table Width)
        # ---------------------------------------------------------
        r1_result = self._model_r1_ruled(vector_paths, tx0, ty0, tx1, ty1, table_w, page_num)

        # ---------------------------------------------------------
        # Model R2: Zebra / Fill Rows
        # ---------------------------------------------------------
        r2_result = self._model_r2_zebra(vector_paths, tx0, ty0, tx1, ty1, table_w)

        # ---------------------------------------------------------
        # Model R3: Anchor Rows (Date / SNO Sequence)
        # ---------------------------------------------------------
        r3_result = self._model_r3_anchor_rows(sorted_spans, cols, tx0, ty0, tx1, ty1)

        # ---------------------------------------------------------
        # Model R4: Whitespace Valleys (1D Vertical Ink Projection)
        # ---------------------------------------------------------
        r4_result = self._model_r4_whitespace_valleys(sorted_spans, ty0, ty1)

        # ---------------------------------------------------------
        # Model R5: Pitch Periodicity (Autocorrelation)
        # ---------------------------------------------------------
        r5_result = self._model_r5_pitch_periodicity(sorted_spans, ty0, ty1)

        models = {
            "R1_ruled": r1_result,
            "R2_zebra": r2_result,
            "R3_anchor": r3_result,
            "R4_valleys": r4_result,
            "R5_pitch": r5_result
        }

        # ---------------------------------------------------------
        # Score & Select Best Model + Runner-up
        # ---------------------------------------------------------
        chosen_key, runner_up_key, scores, disagreements = self._score_and_select_model(models, sorted_spans, ty0, ty1)

        chosen_model_data = models[chosen_key]
        raw_row_bands = chosen_model_data.get("bands", [])

        # Fallback if no bands generated
        if not raw_row_bands:
            raw_row_bands = [(ty0, ty1, "ruled" if r1_result.get("bands") else "virtual", None)]

        # ---------------------------------------------------------
        # Construct Detailed RowModels with Semantics & Padding
        # ---------------------------------------------------------
        row_models = self._construct_row_models(
            raw_row_bands, sorted_spans, tx0, ty0, tx1, ty1, page_h, chosen_key, models
        )

        # ---------------------------------------------------------
        # Assert Contiguity and Chain Sum
        # ---------------------------------------------------------
        self._validate_and_repair_rows(row_models, ty0, ty1, page_h)

        return {
            "rows": row_models,
            "chosen_model": chosen_key,
            "runner_up_model": runner_up_key,
            "model_scores": scores,
            "disagreements": disagreements,
            "models_evaluated": {k: {"count": len(v.get("bands", [])), "confidence": v.get("confidence", 0.0)} for k, v in models.items()}
        }

    def _model_r1_ruled(
        self,
        vector_paths: List[Dict[str, Any]],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float,
        table_w: float,
        page_num: int
    ) -> Dict[str, Any]:
        """Detects horizontal rules spanning >= 80% grid width, merging double strokes."""
        raw_h_rules: List[Dict[str, Any]] = []

        for path in vector_paths:
            bx0, by0, bx1, by1 = path.get("bbox", (0, 0, 0, 0))
            w = bx1 - bx0
            h = by1 - by0

            # Horizontal line check: thin height, wide span overlapping table x
            is_horiz = (h <= 3.5 and w >= 0.70 * table_w) or (path.get("type") == "line" and abs(by1 - by0) <= 2.0 and w >= 0.70 * table_w)
            if not is_horiz:
                continue

            cy = (by0 + by1) / 2.0
            if ty0 - 4.0 <= cy <= ty1 + 4.0:
                raw_h_rules.append({
                    "y": cy,
                    "y0": by0,
                    "y1": by1,
                    "x0": max(tx0, bx0),
                    "x1": min(tx1, bx1),
                    "thickness": max(0.2, h),
                    "span_pct": w / max(1.0, table_w)
                })

        raw_h_rules.sort(key=lambda r: r["y"])

        # Merge double strokes (closer than 3 pt or 3x thickness)
        merged_rules: List[Dict[str, Any]] = []
        idx = 0
        rule_seq = 0

        while idx < len(raw_h_rules):
            r1 = raw_h_rules[idx]
            if idx + 1 < len(raw_h_rules):
                r2 = raw_h_rules[idx + 1]
                dist = r2["y"] - r1["y"]
                max_double_dist = max(3.0, 3.0 * max(r1["thickness"], r2["thickness"]))

                if 0.0 <= dist <= max_double_dist:
                    center_y = (r1["y"] + r2["y"]) / 2.0
                    merged_rules.append({
                        "y": center_y,
                        "rule_id": f"rule_h_p{page_num}_{rule_seq}",
                        "is_double": True,
                        "center_y": center_y,
                        "top_edge": r1["y0"],
                        "bottom_edge": r2["y1"],
                        "thickness": r1["thickness"] + r2["thickness"]
                    })
                    rule_seq += 1
                    idx += 2
                    continue

            merged_rules.append({
                "y": r1["y"],
                "rule_id": f"rule_h_p{page_num}_{rule_seq}",
                "is_double": False,
                "center_y": r1["y"],
                "top_edge": r1["y0"],
                "bottom_edge": r1["y1"],
                "thickness": r1["thickness"]
            })
            rule_seq += 1
            idx += 1

        # Build bands between consecutive rules
        bands: List[Tuple[float, float, str, Optional[Dict[str, Any]]]] = []
        if len(merged_rules) >= 2:
            for i in range(len(merged_rules) - 1):
                r_top = merged_rules[i]
                r_bot = merged_rules[i + 1]
                bands.append((r_top["y"], r_bot["y"], "ruled", r_top))

        confidence = 1.0 if len(bands) >= 2 else (0.4 if len(merged_rules) >= 1 else 0.0)
        return {"bands": bands, "rules": merged_rules, "confidence": confidence}

    def _model_r2_zebra(
        self,
        vector_paths: List[Dict[str, Any]],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float,
        table_w: float
    ) -> Dict[str, Any]:
        """Detects zebra filled rectangles spanning table width."""
        filled_rects: List[Dict[str, Any]] = []

        for p in vector_paths:
            if not p.get("is_filled", False):
                continue
            bx0, by0, bx1, by1 = p.get("bbox", (0, 0, 0, 0))
            w = bx1 - bx0
            h = by1 - by0

            if w >= 0.80 * table_w and 10.0 <= h <= 60.0:
                if ty0 - 2.0 <= by0 and by1 <= ty1 + 2.0:
                    filled_rects.append({"y0": by0, "y1": by1, "color": p.get("fill_color")})

        filled_rects.sort(key=lambda r: r["y0"])
        bands: List[Tuple[float, float, str, Optional[Dict[str, Any]]]] = []

        if len(filled_rects) >= 2:
            for i, r in enumerate(filled_rects):
                bands.append((r["y0"], r["y1"], "zebra", {"color": r["color"]}))

        confidence = 0.9 if len(bands) >= 3 else (0.5 if bands else 0.0)
        return {"bands": bands, "confidence": confidence}

    def _model_r3_anchor_rows(
        self,
        sorted_spans: List[TextSpanModel],
        columns: List[ColumnModel],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float
    ) -> Dict[str, Any]:
        """Identifies logical transaction rows via anchor columns (Date regex or SNO integer sequences)."""
        date_re = re.compile(r"^\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})\s*$")
        sno_re = re.compile(r"^\s*(\d{1,4})\s*$")

        # Score columns on anchor pattern match and coverage
        anchor_candidates: List[Tuple[int, float, str]] = []

        for col in columns:
            col_spans = [s for s in sorted_spans if col.x0_pt - 1.0 <= s.ink_box.x0.pt and s.ink_box.x1.pt <= col.x1_pt + 1.0]
            if not col_spans:
                continue

            date_matches = [s for s in col_spans if date_re.match(s.text.strip())]
            sno_matches = [s for s in col_spans if sno_re.match(s.text.strip())]

            if len(date_matches) >= 2:
                score = len(date_matches) / max(1, len(col_spans))
                anchor_candidates.append((col.index, score + 1.0, "date"))
            elif len(sno_matches) >= 3:
                # Check monotonicity
                nums = [int(sno_re.match(s.text.strip()).group(1)) for s in sno_matches]
                is_monotonic = all(nums[i] < nums[i + 1] for i in range(len(nums) - 1))
                if is_monotonic:
                    score = len(sno_matches) / max(1, len(col_spans))
                    anchor_candidates.append((col.index, score + 0.8, "sno"))

        anchor_candidates.sort(key=lambda x: x[1], reverse=True)
        bands: List[Tuple[float, float, str, Optional[Dict[str, Any]]]] = []

        if anchor_candidates:
            best_col_idx, _, anchor_type = anchor_candidates[0]
            best_col = columns[best_col_idx]
            anchor_spans = [
                s for s in sorted_spans
                if best_col.x0_pt - 1.0 <= s.ink_box.x0.pt and s.ink_box.x1.pt <= best_col.x1_pt + 1.0
                and (date_re.match(s.text.strip()) if anchor_type == "date" else sno_re.match(s.text.strip()))
            ]
            anchor_spans.sort(key=lambda s: s.ink_box.y0.pt)

            if anchor_spans:
                # 1. Header Row (table top to first anchor top)
                first_anchor_top = anchor_spans[0].ink_box.y0.pt
                header_boundary = max(ty0, first_anchor_top - 6.0)
                bands.append((ty0, header_boundary, "virtual", {"role": "HEADER"}))

                # 2. Anchor transaction rows
                for i in range(len(anchor_spans)):
                    cur_a = anchor_spans[i]
                    cur_y0 = cur_a.ink_box.y0.pt - 3.0
                    if i + 1 < len(anchor_spans):
                        next_a = anchor_spans[i + 1]
                        cur_y1 = next_a.ink_box.y0.pt - 3.0
                    else:
                        # Last row: bound by table bottom or last span in table
                        subsequent_spans = [s for s in sorted_spans if s.ink_box.y0.pt >= cur_y0]
                        last_ink = max((s.ink_box.y1.pt for s in subsequent_spans), default=cur_a.ink_box.y1.pt)
                        cur_y1 = min(ty1, last_ink + 6.0)

                    bands.append((cur_y0, cur_y1, "virtual", {"anchor": cur_a.text.strip()}))

        confidence = 0.95 if bands else 0.0
        return {"bands": bands, "confidence": confidence, "anchor_type": anchor_candidates[0][2] if anchor_candidates else None}

    def _model_r4_whitespace_valleys(
        self,
        sorted_spans: List[TextSpanModel],
        ty0: float,
        ty1: float
    ) -> Dict[str, Any]:
        """Finds row boundaries at centers of zero or low-density 1D ink projection valleys."""
        bins_count = int(max(10, ty1 - ty0))
        density = np.zeros(bins_count, dtype=np.float32)

        for s in sorted_spans:
            sy0 = max(ty0, s.ink_box.y0.pt)
            sy1 = min(ty1, s.ink_box.y1.pt)
            if sy1 > sy0:
                i0 = int(sy0 - ty0)
                i1 = int(sy1 - ty0)
                density[max(0, i0):min(bins_count, i1 + 1)] += 1.0

        valleys: List[float] = [ty0]
        in_zero = False
        z_start = 0

        for i, d in enumerate(density):
            if d == 0.0 and not in_zero:
                in_zero = True
                z_start = i
            elif d > 0.0 and in_zero:
                in_zero = False
                valley_h = i - z_start
                if valley_h >= 3.0:
                    valleys.append(ty0 + (z_start + i) / 2.0)

        valleys.append(ty1)
        valleys.sort()

        bands: List[Tuple[float, float, str, Optional[Dict[str, Any]]]] = []
        for i in range(len(valleys) - 1):
            if valleys[i + 1] - valleys[i] >= 8.0:
                bands.append((valleys[i], valleys[i + 1], "virtual", None))

        confidence = 0.7 if len(bands) >= 3 else 0.2
        return {"bands": bands, "confidence": confidence}

    def _model_r5_pitch_periodicity(
        self,
        sorted_spans: List[TextSpanModel],
        ty0: float,
        ty1: float
    ) -> Dict[str, Any]:
        """Calculates line pitch periodicity from text baseline autocorrelation."""
        baselines = sorted(set(round(s.origin_point[1], 2) for s in sorted_spans))
        if len(baselines) < 3:
            return {"bands": [], "confidence": 0.0}

        diffs = [b1 - b0 for b0, b1 in zip(baselines[:-1], baselines[1:]) if 6.0 <= (b1 - b0) <= 35.0]
        if not diffs:
            return {"bands": [], "confidence": 0.0}

        median_pitch = float(np.median(diffs))

        # Build constant pitch bands
        bands: List[Tuple[float, float, str, Optional[Dict[str, Any]]]] = []
        cur_y = ty0
        while cur_y + median_pitch <= ty1 + 2.0:
            bands.append((cur_y, min(ty1, cur_y + median_pitch), "virtual", {"pitch": median_pitch}))
            cur_y += median_pitch

        return {"bands": bands, "pitch": median_pitch, "confidence": 0.6 if len(bands) >= 4 else 0.2}

    def _score_and_select_model(
        self,
        models: Dict[str, Dict[str, Any]],
        spans: List[TextSpanModel],
        ty0: float,
        ty1: float
    ) -> Tuple[str, str, Dict[str, float], List[Dict[str, Any]]]:
        """Scores all 5 models based on agreement, span completeness, and stability."""
        scores: Dict[str, float] = {}

        for k, m in models.items():
            bands = m.get("bands", [])
            if not bands:
                scores[k] = 0.0
                continue

            # 1. Base Confidence
            base_score = m.get("confidence", 0.5) * 1.5

            # 2. Span Completeness: each span's baseline falls cleanly in a band
            assigned = 0
            for s in spans:
                sy = s.origin_point[1]
                if any(b[0] - 1.0 <= sy <= b[1] + 1.0 for b in bands):
                    assigned += 1
            completeness = assigned / max(1, len(spans))

            # 3. Ruled model bonus if full horizontal rules exist
            ruled_bonus = 0.5 if k == "R1_ruled" and len(bands) >= 3 else (
                0.4 if k == "R3_anchor" and len(bands) >= 3 else 0.0
            )

            scores[k] = round(base_score + completeness * 1.0 + ruled_bonus, 3)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        chosen_key = ranked[0][0]
        runner_up_key = ranked[1][0] if len(ranked) > 1 else ranked[0][0]

        # Compute disagreement list between chosen and runner-up
        chosen_bands = models[chosen_key].get("bands", [])
        runner_bands = models[runner_up_key].get("bands", [])
        disagreements: List[Dict[str, Any]] = []

        for i, cb in enumerate(chosen_bands):
            rb = runner_bands[i] if i < len(runner_bands) else None
            if rb is None or abs(cb[0] - rb[0]) > 2.0 or abs(cb[1] - rb[1]) > 2.0:
                disagreements.append({
                    "row_index": i,
                    "chosen_band": [round(cb[0], 2), round(cb[1], 2)],
                    "runner_up_band": [round(rb[0], 2), round(rb[1], 2)] if rb else None,
                    "delta_y0": round(abs(cb[0] - rb[0]), 2) if rb else None
                })

        return chosen_key, runner_up_key, scores, disagreements

    def _construct_row_models(
        self,
        bands: List[Tuple[float, float, str, Optional[Dict[str, Any]]]],
        spans: List[TextSpanModel],
        tx0: float,
        ty0: float,
        tx1: float,
        ty1: float,
        page_h: float,
        chosen_key: str,
        models: Dict[str, Dict[str, Any]]
    ) -> List[RowModel]:
        """Build detailed RowModel objects with type classification."""
        row_models: List[RowModel] = []
        num_bands = len(bands)

        for i, (ry0, ry1, b_type, info) in enumerate(bands):
            r_h = max(0.1, ry1 - ry0)
            h_mu = create_multi_unit_value(r_h, page_h, self.config.dpi)

            # Collect spans inside row band
            row_spans = [s for s in spans if ry0 - 1.0 <= s.origin_point[1] <= ry1 + 1.0]
            text_lines = [s.text.strip() for s in sorted(row_spans, key=lambda s: (s.ink_box.y0.pt, s.ink_box.x0.pt))]
            row_text_joined = " ".join(text_lines).upper()

            # Classify Row Semantics
            if i == 0 or "DATE" in row_text_joined or "DESCRIPTION" in row_text_joined or "CHQ" in row_text_joined:
                row_type = "HEADER"
            elif "OPENING BALANCE" in row_text_joined or "B/F" in row_text_joined or "BROUGHT FORWARD" in row_text_joined:
                row_type = "OPENING_BALANCE"
            elif "CLOSING BALANCE" in row_text_joined or "C/F" in row_text_joined or "CARRIED FORWARD" in row_text_joined:
                row_type = "CLOSING_BALANCE"
            elif "TOTAL" in row_text_joined or "SUBTOTAL" in row_text_joined:
                row_type = "SUBTOTAL"
            elif "STATEMENT SUMMARY" in row_text_joined or "PAGE TOTAL" in row_text_joined:
                row_type = "PAGE_SUMMARY"
            elif len(text_lines) <= 2 and not any(re.search(r"\d{1,2}[-/\.]\d{1,2}", t) for t in text_lines):
                row_type = "CONTINUATION"
            else:
                row_type = "BODY"

            is_estimated = (i == num_bands - 1 and b_type == "virtual")
            gap_next = bands[i + 1][0] - ry1 if i + 1 < num_bands else 0.0

            r_model = RowModel(
                index=i,
                row_type=row_type,
                y0_pt=ry0,
                y1_pt=ry1,
                height_pt=r_h,
                height=h_mu,
                boundary_type=b_type,
                rule_info=info if b_type == "ruled" else None,
                gap_to_next_pt=gap_next,
                is_estimated_bottom=is_estimated,
                text_lines=text_lines,
                model_evidence={"chosen_model": chosen_key, "info": info},
                confidence=0.95
            )
            row_models.append(r_model)

        return row_models

    def _validate_and_repair_rows(
        self,
        rows: List[RowModel],
        ty0: float,
        ty1: float,
        page_h: float
    ) -> None:
        """Enforces row contiguity and table height closure."""
        if not rows:
            return

        table_h = ty1 - ty0
        tol = 0.25

        # 1. Contiguity
        if rows:
            rows[0].y0_pt = ty0
            rows[0].height_pt = max(0.1, rows[0].y1_pt - rows[0].y0_pt)
            rows[0].height = create_multi_unit_value(rows[0].height_pt, page_h, self.config.dpi)

        for i in range(len(rows) - 1):
            r_curr = rows[i]
            r_next = rows[i + 1]
            if abs(r_curr.y1_pt - r_next.y0_pt) > 0.05:
                mid = (r_curr.y1_pt + r_next.y0_pt) / 2.0
                r_curr.y1_pt = mid
                r_curr.height_pt = max(0.1, r_curr.y1_pt - r_curr.y0_pt)
                r_curr.height = create_multi_unit_value(r_curr.height_pt, page_h, self.config.dpi)
                r_next.y0_pt = mid
                r_next.height_pt = max(0.1, r_next.y1_pt - r_next.y0_pt)
                r_next.height = create_multi_unit_value(r_next.height_pt, page_h, self.config.dpi)

        # 2. Table height closure
        if rows:
            rows[-1].y1_pt = ty1
            rows[-1].height_pt = max(0.1, rows[-1].y1_pt - rows[-1].y0_pt)
            rows[-1].height = create_multi_unit_value(rows[-1].height_pt, page_h, self.config.dpi)

