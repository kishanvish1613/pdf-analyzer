"""
Module E: Transaction-to-transaction vertical spacing analysis.
Calculates granular per-line and per-transaction spacing, separating border-to-border
and ink-to-ink gaps, baseline-to-baseline distances, and flags pitch deviations.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel


class TransactionSpacingAnalyzer:
    """Calculates granular vertical metrics between successive transaction lines."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_transaction_spacing(
        self,
        rows: List[Dict[str, Any]],
        spans: List[TextSpanModel],
        page_h: float
    ) -> Dict[str, Any]:
        """Compute per-row metrics table, border vs ink gaps, and outliers."""
        if not rows:
            return {
                "per_row_table": [],
                "spacing_summary": {},
                "deviating_rows": []
            }

        per_row_table: List[Dict[str, Any]] = []
        ink_gaps: List[float] = []
        baseline_distances: List[float] = []

        for i in range(len(rows)):
            r = rows[i]
            r_next = rows[i + 1] if i + 1 < len(rows) else None

            ink_t = r.get("ink_top_pt", r.get("raw_y0_pt", 0.0))
            ink_b = r.get("ink_bottom_pt", r.get("raw_y1_pt", 0.0))
            by = r.get("baseline_y_pt", ink_b)
            h = r.get("height_pt", (ink_b - ink_t))

            if r_next:
                next_t = r_next.get("ink_top_pt", r_next.get("raw_y0_pt", 0.0))
                next_by = r_next.get("baseline_y_pt", next_t)
                i_gap = max(0.0, next_t - ink_b)
                b2b = max(0.0, next_by - by)
                ink_gaps.append(i_gap)
                baseline_distances.append(b2b)
            else:
                i_gap = 0.0
                b2b = 0.0

            row_entry = {
                "line_index": r.get("line_index", i + 1),
                "y_top_pt": round(ink_t, 3),
                "y_bottom_pt": round(ink_b, 3),
                "height_pt": round(h, 3),
                "baseline_y_pt": round(by, 3),
                "gap_to_next_pt": round(i_gap, 3) if r_next else None,
                "baseline_to_baseline_pt": round(b2b, 3) if r_next else None,
                "text_summary": r.get("text", "")[:40]
            }
            per_row_table.append(row_entry)

        # Statistical Summary
        median_b2b = float(np.median(baseline_distances)) if baseline_distances else 12.0
        deviating = [
            pr["line_index"] for pr in per_row_table
            if pr["baseline_to_baseline_pt"] is not None and abs(pr["baseline_to_baseline_pt"] - median_b2b) > 0.5
        ]

        return {
            "per_row_table": per_row_table,
            "spacing_summary": {
                "median_baseline_distance_pt": round(median_b2b, 3),
                "min_baseline_distance_pt": round(min(baseline_distances), 3) if baseline_distances else 0.0,
                "max_baseline_distance_pt": round(max(baseline_distances), 3) if baseline_distances else 0.0,
                "std_baseline_distance_pt": round(float(np.std(baseline_distances)), 3) if len(baseline_distances) > 1 else 0.0
            },
            "deviating_rows": deviating
        }

