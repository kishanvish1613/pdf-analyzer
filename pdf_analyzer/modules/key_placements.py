"""Module K: Date, account details & statement heading placement analysis.

Detects date formats via regex, checks heading centering against page center,
and computes inter-field grid positioning metrics.
"""

import re
from typing import List, Dict, Any, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel
from pdf_analyzer.utils.units import create_bbox_from_pt, create_multi_unit_value


DATE_REGEX_PATTERNS = [
    (r"\b\d{2}[/-]\d{2}[/-]\d{4}\b", "DD/MM/YYYY (or MM/DD/YYYY)"),
    (r"\b\d{2}[/-]\d{2}[/-]\d{2}\b", "DD/MM/YY"),
    (r"\b\d{4}[/-]\d{2}[/-]\d{2}\b", "YYYY-MM-DD (ISO 8601)"),
    (r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2,4}\b", "DD-MMM-YYYY"),
    (r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2,4}\b", "DD MMM YYYY")
]


class KeyPlacementsAnalyzer:
    """Analyzes specific anchor placements: Date formatting, Heading Centering, and Account Grids."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_key_placements(
        self,
        spans: List[TextSpanModel],
        table_columns: List[Dict[str, Any]],
        page_w: float,
        page_h: float
    ) -> Dict[str, Any]:
        """Analyze Date format, Heading centering math, and Account detail field matrix."""
        # 1. Date Format & Column Alignment
        date_analysis = self._analyze_date_column(spans, table_columns, page_w)

        # 2. Statement Heading Centering Check
        heading_analysis = self._analyze_heading_centering(spans, page_w, page_h)

        return {
            "date_column_analysis": date_analysis,
            "statement_heading_analysis": heading_analysis
        }

    def _analyze_date_column(
        self,
        spans: List[TextSpanModel],
        table_columns: List[Dict[str, Any]],
        page_w: float
    ) -> Dict[str, Any]:
        """Detect date strings, matched regex format, and left-edge consistency."""
        detected_formats = []
        date_spans = []

        for s in spans:
            for pat, fmt_name in DATE_REGEX_PATTERNS:
                if re.search(pat, s.text.strip(), re.IGNORECASE):
                    detected_formats.append(fmt_name)
                    date_spans.append(s)
                    break

        predominant_format = max(set(detected_formats), key=detected_formats.count) if detected_formats else "Unknown"

        # Check alignment consistency of date spans
        if date_spans:
            x0s = [s.bbox.x0.pt for s in date_spans]
            std_x0 = float(np.std(x0s))
            mean_x0 = float(np.mean(x0s))
            font_sample = date_spans[0].font_name
            size_sample = date_spans[0].font_size_pt
        else:
            std_x0 = 0.0
            mean_x0 = 0.0
            font_sample = "N/A"
            size_sample = 0.0

        return {
            "detected_date_format": predominant_format,
            "sample_date_count": len(date_spans),
            "mean_x0_pt": round(mean_x0, 2),
            "x0_std_dev_pt": round(std_x0, 3),
            "alignment_consistency": "perfect" if std_x0 < 0.5 else "consistent" if std_x0 < 2.0 else "variable",
            "font_name": font_sample,
            "font_size_pt": size_sample
        }

    def _analyze_heading_centering(
        self,
        spans: List[TextSpanModel],
        page_w: float,
        page_h: float
    ) -> Dict[str, Any]:
        """Check if main document title is geometrically centered relative to page width."""
        top_spans = [s for s in spans if s.bbox.y0.pt < page_h * 0.25]
        if not top_spans:
            return {"is_centered": False, "offset_from_page_center_pt": 0.0}

        # Largest font span near top
        heading_span = max(top_spans, key=lambda s: s.font_size_pt)
        h_center_x = (heading_span.bbox.x0.pt + heading_span.bbox.x1.pt) / 2.0
        page_center_x = page_w / 2.0
        diff_from_center = h_center_x - page_center_x

        is_centered = abs(diff_from_center) <= self.config.tolerances.centering_tolerance_pt

        return {
            "heading_text": heading_span.text,
            "heading_bbox": heading_span.bbox.to_dict(),
            "page_center_x_pt": round(page_center_x, 2),
            "heading_center_x_pt": round(h_center_x, 2),
            "offset_from_page_center_pt": round(diff_from_center, 2),
            "is_centered": is_centered,
            "font_size_pt": heading_span.font_size_pt
        }
