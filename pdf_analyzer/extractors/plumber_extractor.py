"""pdfplumber extractor for lines, rects, and table structures."""

from typing import Any, Dict, List, Optional
import pdfplumber


class PlumberExtractor:
    """Extracts layout elements and tables via pdfplumber for cross-checking."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._pdf = None

    def __enter__(self):
        self._pdf = pdfplumber.open(self.pdf_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._pdf:
            self._pdf.close()

    def extract_page_primitives(self, page_index: int) -> Dict[str, Any]:
        """Extract lines, rects, curves, and table candidates from pdfplumber."""
        if not self._pdf or page_index >= len(self._pdf.pages):
            return {"lines": [], "rects": [], "curves": [], "tables": []}

        page = self._pdf.pages[page_index]

        lines = []
        for l in page.lines:
            lines.append({
                "x0": l.get("x0", 0.0),
                "y0": l.get("top", 0.0),
                "x1": l.get("x1", 0.0),
                "y1": l.get("bottom", 0.0),
                "width": l.get("width", 0.0),
                "height": l.get("height", 0.0),
                "linewidth": l.get("linewidth", 1.0),
                "stroking_color": l.get("stroking_color")
            })

        rects = []
        for r in page.rects:
            rects.append({
                "x0": r.get("x0", 0.0),
                "y0": r.get("top", 0.0),
                "x1": r.get("x1", 0.0),
                "y1": r.get("bottom", 0.0),
                "width": r.get("width", 0.0),
                "height": r.get("height", 0.0),
                "linewidth": r.get("linewidth", 1.0),
                "fill": r.get("non_stroking_color"),
                "stroke": r.get("stroking_color")
            })

        curves = page.curves

        # Table detection via pdfplumber
        tables_found = []
        try:
            detected_tables = page.find_tables()
            for t in detected_tables:
                tables_found.append({
                    "bbox": (t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3]),
                    "rows_count": len(t.rows),
                    "cols_count": len(t.columns),
                    "cells": [c for row in t.rows for c in row.cells if c is not None]
                })
        except Exception:
            pass

        return {
            "lines": lines,
            "rects": rects,
            "curves": curves,
            "tables": tables_found
        }
