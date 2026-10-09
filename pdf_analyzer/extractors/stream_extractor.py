"""
Content Stream Operator Extractor.
Parses raw PDF content streams (using pikepdf) to recover exact operator values:
`cm`, `re`, `m/l`, `w`, `d`, `RG/rg/G/g/K/k`, `Tc`, `Tw`, `Tz`, `Ts`, `TL`, `Tm`.
Computes effective font size as Tm scale x CTM scale x font size operand.
"""

from __future__ import annotations
import logging
from typing import Dict, Any, List, Tuple, Optional
import pikepdf

logger = logging.getLogger(__name__)


class StreamExtractor:
    """Extracts raw content stream operators and matrices from PDF pages."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._pdf = None
        try:
            self._pdf = pikepdf.Pdf.open(pdf_path)
        except Exception as e:
            logger.warning(f"Could not open {pdf_path} with pikepdf: {e}")

    def get_page_operators(self, page_index: int) -> List[Dict[str, Any]]:
        """Extracts operator stream instructions from the given page index."""
        if self._pdf is None or page_index >= len(self._pdf.pages):
            return []

        operators: List[Dict[str, Any]] = []
        try:
            page = self._pdf.pages[page_index]
            for operands, operator in pikepdf.parse_content_stream(page):
                op_name = str(operator)
                op_args = [float(x) if isinstance(x, (int, float, pikepdf.Decimal)) else str(x) for x in operands]
                operators.append({
                    "operator": op_name,
                    "operands": op_args
                })
        except Exception as e:
            logger.warning(f"Error parsing content stream for page {page_index}: {e}")

        return operators

    def compute_effective_font_size(
        self,
        nominal_size: float,
        tm_matrix: Optional[Tuple[float, float, float, float, float, float]] = None,
        ctm_matrix: Optional[Tuple[float, float, float, float, float, float]] = None
    ) -> float:
        """Computes effective font size as Tm scale x CTM scale x font size operand."""
        tm_scale = 1.0
        if tm_matrix:
            # tm = [a, b, c, d, e, f], vertical scale is hypot(b, d) or sqrt(c^2 + d^2)
            a, b, c, d, _, _ = tm_matrix
            tm_scale = (a**2 + b**2)**0.5

        ctm_scale = 1.0
        if ctm_matrix:
            ca, cb, cc, cd, _, _ = ctm_matrix
            ctm_scale = (ca**2 + cb**2)**0.5

        return nominal_size * tm_scale * ctm_scale

    def close(self):
        if self._pdf is not None:
            try:
                self._pdf.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

