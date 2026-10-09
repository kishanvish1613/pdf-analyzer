"""
Redaction Engine.
Replaces text with same-width placeholders using font metrics and glyph advances
to preserve layout geometry within 0.05 pt.
"""

from __future__ import annotations
import re
from typing import Dict, Any, List, Optional, Tuple
from reportlab.pdfbase.pdfmetrics import stringWidth
from pdf_analyzer.l0_bytes.font_manager import calculate_string_width_parity, get_best_fallback_font


def get_string_width_pt(text: str, font_name: str = "Helvetica", font_size_pt: float = 8.0) -> float:
    """Computes rendered string width in points using ReportLab/standard font metrics."""
    if not text:
        return 0.0
    try:
        return float(stringWidth(text, font_name, font_size_pt))
    except Exception:
        fallback = get_best_fallback_font(font_name)
        try:
            return float(stringWidth(text, fallback, font_size_pt))
        except Exception:
            return float(len(text) * font_size_pt * 0.5)



def redact_string_with_same_width(
    text: str,
    font_name: str = "Helvetica",
    font_size_pt: float = 8.0,
    placeholder_char: str = "X",
    digit_char: str = "8"
) -> Tuple[str, Dict[str, Any]]:
    """
    Replaces alphanumeric characters with same-width placeholders while preserving
    spaces, punctuation, and measuring width parity to ensure layout invariant.

    Returns:
        (redacted_text, parity_info_dict)
    """
    if not text:
        return text, {"width_delta_pt": 0.0, "char_spacing_correction_pt": 0.0}

    # 1. Replace characters preserving whitespace and punctuation
    redacted_chars = []
    for ch in text:
        if ch.isalpha():
            redacted_chars.append(placeholder_char if ch.isupper() else placeholder_char.lower())
        elif ch.isdigit():
            redacted_chars.append(digit_char)
        else:
            redacted_chars.append(ch)

    redacted_text = "".join(redacted_chars)

    # 2. Compute exact original width and redacted width
    orig_w = get_string_width_pt(text, font_name, font_size_pt)
    red_w = get_string_width_pt(redacted_text, font_name, font_size_pt)
    w_delta = abs(orig_w - red_w)

    # 3. Calculate corrective charSpace if width delta exceeds 0.05 pt
    parity = calculate_string_width_parity(
        text=redacted_text,
        original_width_pt=orig_w,
        font_name=font_name,
        font_size_pt=font_size_pt,
        threshold_pt=0.05
    )

    return redacted_text, {
        "original_width_pt": orig_w,
        "redacted_width_pt": red_w,
        "width_delta_pt": w_delta,
        "char_spacing_correction_pt": parity.get("char_spacing_correction_pt", 0.0),
        "needs_correction": parity.get("needs_correction", False)
    }


class RedactionEngine:
    """Applies same-width redaction across text items in a document."""

    def __init__(self, default_font: str = "Helvetica", default_size_pt: float = 8.0):
        self.default_font = default_font
        self.default_size_pt = default_size_pt

    def redact_text(
        self,
        text: str,
        font_name: Optional[str] = None,
        font_size_pt: Optional[float] = None
    ) -> Tuple[str, float]:
        """Redacts text and returns (redacted_str, width_delta_pt)."""
        fn = font_name or self.default_font
        fs = font_size_pt or self.default_size_pt
        red_text, parity = redact_string_with_same_width(text, font_name=fn, font_size_pt=fs)
        return red_text, parity.get("width_delta_pt", 0.0)
