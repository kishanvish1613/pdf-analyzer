"""
L4 Numeric Cell & Digit-Suffix Alignment Engine (Phase 8C Task 5).
Handles numeric column consistency:
- Fuses numeric digits + suffix (Cr., Dr, parentheses) into ONE content entity.
- Computes right-edge consistency standard deviation for digits and suffix.
- Deletes narrow clutter boxes / guides that cover digit columns (fixes Kotak Balance digit occlusion).
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar

logger = logging.getLogger(__name__)

NUMERIC_SUFFIX_REGEX = re.compile(
    r"^(?P<num>[\d,]+\.\d{2}|\([\d,]+\.\d{2}\)|[\d,]+)\s*(?P<suf>Cr\.?|Dr\.?|\(Cr\)|\(Dr\)|\))?$",
    re.IGNORECASE,
)


@dataclass
class NumericCellAudit:
    column_index: int
    cells_count: int
    digits_right_std_pt: float
    suffix_right_std_pt: float
    is_right_aligned: bool
    fused_cells: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_index": self.column_index,
            "cells_count": self.cells_count,
            "digits_right_std_pt": self.digits_right_std_pt,
            "suffix_right_std_pt": self.suffix_right_std_pt,
            "is_right_aligned": self.is_right_aligned,
            "fused_cells_count": len(self.fused_cells),
        }


class NumericCellEngine:
    """
    Analyzes numeric alignment, suffix binding, and cleans occlusion clutter over numbers.
    """

    def audit_numeric_columns(
        self,
        page_layer: PageByteLayer,
        columns: List[Any],
    ) -> List[NumericCellAudit]:
        results: List[NumericCellAudit] = []

        for col in columns:
            col_idx = col.index if hasattr(col, "index") else col.get("index", 1)
            cx0 = col.x0_pt if hasattr(col, "x0_pt") else col.get("x0_pt", 0.0)
            cx1 = col.x1_pt if hasattr(col, "x1_pt") else col.get("x1_pt", 0.0)

            col_chars = [
                c for c in page_layer.chars
                if cx0 <= c.origin_device_pt[0] <= cx1
            ]

            # Group characters by baseline
            baselines: Dict[float, List[PaintedTextChar]] = {}
            for c in col_chars:
                by = round(c.origin_device_pt[1], 1)
                baselines.setdefault(by, []).append(c)

            digit_rights = []
            suffix_rights = []
            fused = []

            for by, group in baselines.items():
                group.sort(key=lambda c: c.origin_device_pt[0])
                txt = "".join(c.unicode_text or c.char_text for c in group).strip()
                m = NUMERIC_SUFFIX_REGEX.match(txt)
                if m:
                    num_part = m.group("num")
                    suf_part = m.group("suf")

                    # Compute digit right edge
                    num_chars = group[:len(num_part)] if len(group) >= len(num_part) else group
                    d_right = max(c.font_bbox_device_pt[2] for c in num_chars)
                    digit_rights.append(d_right)

                    s_right = max(c.font_bbox_device_pt[2] for c in group)
                    if suf_part:
                        suffix_rights.append(s_right)

                    fused.append({
                        "full_text": txt,
                        "numeric_part": num_part,
                        "suffix_part": suf_part,
                        "right_edge_pt": s_right,
                    })

            if len(digit_rights) >= 3:
                d_std = float(np.std(digit_rights))
                s_std = float(np.std(suffix_rights)) if suffix_rights else 0.0
                is_aligned = d_std <= 2.5

                results.append(NumericCellAudit(
                    column_index=col_idx,
                    cells_count=len(fused),
                    digits_right_std_pt=d_std,
                    suffix_right_std_pt=s_std,
                    is_right_aligned=is_aligned,
                    fused_cells=fused,
                ))

        return results

    def filter_clutter_boxes_and_guides(
        self,
        boxes: List[Dict[str, Any]],
        guides: List[Any],
        numeric_columns: List[Any],
    ) -> Tuple[List[Dict[str, Any]], List[Any]]:
        """
        Removes narrow boxes and non-boundary vertical guides that occlude numeric columns.
        """
        cleaned_boxes = []
        for b in boxes:
            bx0, bx1 = b.get("x0_pt", 0.0), b.get("x1_pt", 0.0)
            bw = bx1 - bx0
            # If a box is very narrow (< 30 pt) and sits inside a numeric column, it's cell clutter
            is_clutter = False
            if bw < 30.0:
                for col in numeric_columns:
                    cx0 = col.x0_pt if hasattr(col, "x0_pt") else col.get("x0_pt", 0.0)
                    cx1 = col.x1_pt if hasattr(col, "x1_pt") else col.get("x1_pt", 0.0)
                    if cx0 <= bx0 and bx1 <= cx1:
                        is_clutter = True
                        logger.info(f"Removing clutter box {b.get('id')} over numeric column")
                        break
            if not is_clutter:
                cleaned_boxes.append(b)

        cleaned_guides = []
        for g in guides:
            axis = g.axis if hasattr(g, "axis") else g.get("axis", "X")
            coord = g.coord_pt if hasattr(g, "coord_pt") else g.get("coord_pt", 0.0)
            g_type = g.guide_type if hasattr(g, "guide_type") else g.get("guide_type", "")

            is_clutter_guide = False
            if axis == "X" and g_type != "column_boundary":
                for col in numeric_columns:
                    cx0 = col.x0_pt if hasattr(col, "x0_pt") else col.get("x0_pt", 0.0)
                    cx1 = col.x1_pt if hasattr(col, "x1_pt") else col.get("x1_pt", 0.0)
                    # If vertical guide lies strictly inside the middle of a numeric column
                    if cx0 + 5.0 < coord < cx1 - 5.0:
                        is_clutter_guide = True
                        break
            if not is_clutter_guide:
                cleaned_guides.append(g)

        return cleaned_boxes, cleaned_guides
