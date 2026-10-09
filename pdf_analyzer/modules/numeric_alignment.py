"""Module L: Debit / Credit / Balance numeric alignment and suffix split analysis.

Splits numeric values and suffixes (e.g., '12,450.00' and 'Cr.'), verifies alignment consistency
separately for digits and suffixes, and computes decimal separator positions.
"""

import re
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel


class NumericAlignmentAnalyzer:
    """Analyzes numeric column alignment, digits vs suffix separation, and standard deviations."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_numeric_columns(
        self,
        table_columns: List[Dict[str, Any]],
        spans: List[TextSpanModel],
        page_w: float
    ) -> Dict[str, Any]:
        """Classify right vs decimal alignment and suffix consistency for financial columns."""
        numeric_cols = [
            c for c in table_columns
            if c.get("semantic_type", "generic") in ["debit", "credit", "balance", "generic", "numeric"]
            or any(kw in str(c.get("header_text", "")).lower() for kw in ["debit", "credit", "balance", "amount", "withdrawal", "deposit", "total"])
        ]

        column_reports: Dict[str, Any] = {}

        for col in numeric_cols:
            col_x0 = col.get("x0_pt", col.get("raw_x0_pt", 0.0))
            col_x1 = col.get("x1_pt", col.get("raw_x1_pt", 0.0))
            c_name = col.get("header_text", f"col_{col.get('index', 0)}")

            # Filter spans within column bounds
            col_spans = [
                s for s in spans
                if col_x0 - 2.0 <= s.ink_box.x0.pt and s.ink_box.x1.pt <= col_x1 + 4.0
                and s.text.strip() != c_name.strip()
            ]

            report = self._analyze_single_numeric_column(col_spans, col, page_w)
            column_reports[c_name] = report

        return {
            "columns_analyzed": list(column_reports.keys()),
            "numeric_column_details": column_reports
        }

    def _analyze_single_numeric_column(
        self,
        col_spans: List[TextSpanModel],
        col_meta: Dict[str, Any],
        page_w: float
    ) -> Dict[str, Any]:
        """Analyze digits right edge, decimal point x, suffix right edge, and standard deviations."""
        h_text = col_meta.get("header_text", "")
        if not col_spans:
            return {
                "header_text": h_text,
                "semantic_type": col_meta.get("semantic_type", "generic"),
                "data_alignment": "right",
                "alignment_type": "right_aligned",
                "sample_count": 0,
                "digits_right_edge_std_dev_pt": 0.0,
                "suffix_right_edge_std_dev_pt": 0.0,
                "currency_symbol": None,
                "thousand_separator_system": "None",
                "negative_format": "N/A",
                "empty_cell_convention": "blank"
            }

        digits_right_edges = []
        suffix_right_edges = []
        suffix_left_edges = []
        decimal_xs = []
        parsed_entries = []

        for s in col_spans:
            text = s.text.strip()
            # Regex to split numeric digits and suffix (e.g. '1,234.50 Cr.' -> digits: '1,234.50', suffix: 'Cr.')
            match = re.match(r"^([^\d]*[\d,.]+)\s*([A-Za-z./]+)?$", text)
            
            if match:
                digit_part = match.group(1)
                suffix_part = match.group(2) if match.group(2) else ""

                # Compute approximate bounds of digit part vs suffix using char boxes if available
                if s.char_boxes and len(s.char_boxes) == len(text):
                    # Exact char box right edge of digit part
                    d_len = len(digit_part)
                    d_right = s.char_boxes[d_len - 1][1][2]
                    digits_right_edges.append(d_right)

                    if suffix_part:
                        s_left = s.char_boxes[d_len][1][0]
                        s_right = s.char_boxes[-1][1][2]
                        suffix_left_edges.append(s_left)
                        suffix_right_edges.append(s_right)
                else:
                    # Estimate proportional
                    total_len = max(1, len(text))
                    d_ratio = len(digit_part) / total_len
                    d_right = s.ink_box.x0.pt + (s.ink_box.width.pt * d_ratio)
                    digits_right_edges.append(d_right)
                    if suffix_part:
                        suffix_right_edges.append(s.ink_box.x1.pt)

                # Locate decimal point
                if "." in digit_part:
                    dot_idx = digit_part.index(".")
                    if s.char_boxes and dot_idx < len(s.char_boxes):
                        dot_x = (s.char_boxes[dot_idx][1][0] + s.char_boxes[dot_idx][1][2]) / 2.0
                    else:
                        dot_ratio = dot_idx / max(1, len(digit_part))
                        dot_x = s.ink_box.x0.pt + (s.ink_box.width.pt * (dot_ratio * d_ratio))
                    decimal_xs.append(dot_x)

                parsed_entries.append({
                    "raw_text": text,
                    "digit_part": digit_part,
                    "suffix_part": suffix_part,
                    "digit_right_pt": round(d_right, 3)
                })

        # Compute Standard Deviations
        std_digits = float(np.std(digits_right_edges)) if digits_right_edges else 0.0
        std_suffix = float(np.std(suffix_right_edges)) if suffix_right_edges else 0.0
        std_decimal = float(np.std(decimal_xs)) if len(decimal_xs) >= 2 else 999.0

        if std_decimal <= self.config.tolerances.decimal_alignment_tolerance_pt:
            alignment_type = "decimal_point_aligned"
        elif std_digits <= self.config.tolerances.alignment_tolerance_pt * 2.0:
            alignment_type = "right_aligned (digits-locked)"
        else:
            alignment_type = "right_aligned_approximate"

        # Detect currency symbols
        all_text = " ".join(s.text for s in col_spans)
        currency_match = re.search(r"([$€£₹]|USD|EUR|GBP|INR)", all_text)
        currency_sym = currency_match.group(1) if currency_match else None

        # Number grouping
        if re.search(r"\d{1,2},\d{2},\d{3}", all_text):
            thousand_sep = "Indian (1,00,000)"
        elif re.search(r"\d{1,3},\d{3}", all_text):
            thousand_sep = "International (100,000)"
        elif re.search(r"\d{1,3}\.\d{3},\d{2}", all_text):
            thousand_sep = "European (100.000,00)"
        else:
            thousand_sep = "None / Unformatted"

        # Negative format
        if re.search(r"\(\s*[\d,.]+\s*\)", all_text):
            negative_fmt = "parentheses: (1,234.50)"
        elif re.search(r"-\s*[\d,.]+", all_text):
            negative_fmt = "minus_prefix: -1,234.50"
        elif re.search(r"[\d,.]+\s*(?:Dr|DR)", all_text):
            negative_fmt = "suffix_dr_cr: 1,234.50 Dr"
        else:
            negative_fmt = "unsigned_column"

        # Empty cell convention
        empty_convention = "hyphen ('-')" if "-" in [s.text.strip() for s in col_spans] else "blank_whitespace"

        return {
            "header_text": col_meta.get("header_text", ""),
            "semantic_type": col_meta.get("semantic_type", "generic"),
            "alignment_type": alignment_type,
            "header_alignment": col_meta.get("alignment", "left"),
            "data_alignment": "right",
            "digits_right_edge_std_dev_pt": round(std_digits, 3),
            "suffix_right_edge_std_dev_pt": round(std_suffix, 3) if suffix_right_edges else None,
            "decimal_point_std_dev_pt": round(std_decimal, 3) if decimal_xs else None,
            "mean_decimal_x_pt": round(float(np.mean(decimal_xs)), 3) if decimal_xs else None,
            "currency_symbol": currency_sym,
            "thousand_separator_system": thousand_sep,
            "negative_format": negative_fmt,
            "empty_cell_convention": empty_convention,
            "sample_parsed_entries": parsed_entries[:6]
        }

