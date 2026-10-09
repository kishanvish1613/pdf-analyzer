"""
Section 12: Grid Cell Intersection, Content Mapping & Padding/Alignment Engine.
Computes for every (row x column) cell:
- Cell inner bounding box (rule inner edges accounting for stroke thicknesses)
- Assigned text spans, line count, wrapping flag, joined text
- Cell ink bounding box
- Exact padding (left, right, top, bottom to inner edges in pt/mm/px)
- Horizontal alignment (left/right/center/decimal) & vertical positioning
- Diagnostic flags (touching_border, overflow, clipped, empty, spanning)
- Numeric breakdown (digits right edge, decimal point x, suffix)
- Exports rows to cells.csv
"""

from __future__ import annotations
import re
import csv
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import (
    MultiUnitValue, TextSpanModel, ColumnModel, RowModel, CellModel, BoundingBox
)
from pdf_analyzer.utils.units import create_bbox_from_pt, create_multi_unit_value

logger = logging.getLogger(__name__)


class CellGridBuilder:
    """Builds the 2D cell grid from chosen ColumnModels and RowModels."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def build_cells(
        self,
        columns: Optional[List[ColumnModel]],
        rows: List[RowModel],
        table_spans: List[TextSpanModel],
        page_w: float,
        page_h: float
    ) -> List[CellModel]:
        """Constructs all (row x column) CellModels with exact inner bounds, padding, and alignments."""
        if not columns or not rows:
            return []
        cells: List[CellModel] = []
        num_re = re.compile(r"^\s*([\d,]+)(\.(\d{2}))?\s*([A-Za-z]+)?\s*$")

        for r in rows:
            for c in columns:
                cell_id = f"cell_r{r.index}_c{c.index}"
                raw_box = (c.x0_pt, r.y0_pt, c.x1_pt, r.y1_pt)

                # Compute rule inner edges by accounting for half rule thicknesses
                rule_l_w = c.double_rule_info.get("stroke1_width", 0.5) if c.is_double_rule and c.double_rule_info else 0.5
                rule_r_w = c.double_rule_info.get("stroke2_width", 0.5) if c.is_double_rule and c.double_rule_info else 0.5
                rule_t_w = r.rule_info.get("thickness", 0.5) if r.rule_info else 0.5
                rule_b_w = 0.5

                inner_x0 = c.x0_pt + (rule_l_w / 2.0 if c.boundary_type != "virtual" else 0.0)
                inner_x1 = c.x1_pt - (rule_r_w / 2.0 if c.boundary_type != "virtual" else 0.0)
                inner_y0 = r.y0_pt + (rule_t_w / 2.0 if r.boundary_type != "virtual" else 0.0)
                inner_y1 = r.y1_pt - (rule_b_w / 2.0 if r.boundary_type != "virtual" else 0.0)
                inner_box = (inner_x0, inner_y0, inner_x1, inner_y1)

                cell_bbox = create_bbox_from_pt(inner_x0, inner_y0, inner_x1, inner_y1, page_w, page_h, self.config.dpi)

                # Assign text spans inside cell (by baseline and center)
                cell_spans = [
                    s for s in table_spans
                    if (inner_y0 - 1.5 <= s.origin_point[1] <= inner_y1 + 1.5)
                    and (inner_x0 - 2.0 <= (s.ink_box.x0.pt + s.ink_box.x1.pt) / 2.0 <= inner_x1 + 2.0)
                ]
                cell_spans.sort(key=lambda s: (s.ink_box.y0.pt, s.ink_box.x0.pt))

                joined_text = " ".join(s.text.strip() for s in cell_spans)
                line_count = len(cell_spans)
                is_wrapped = line_count > 1

                # Ink Bounding Box
                if cell_spans:
                    ink_x0 = min(s.ink_box.x0.pt for s in cell_spans)
                    ink_y0 = min(s.ink_box.y0.pt for s in cell_spans)
                    ink_x1 = max(s.ink_box.x1.pt for s in cell_spans)
                    ink_y1 = max(s.ink_box.y1.pt for s in cell_spans)
                    ink_box_pt = (ink_x0, ink_y0, ink_x1, ink_y1)

                    # Padding to Inner Edges
                    pad_l = max(0.0, ink_x0 - inner_x0)
                    pad_r = max(0.0, inner_x1 - ink_x1)
                    pad_t = max(0.0, ink_y0 - inner_y0)
                    pad_b = max(0.0, inner_y1 - ink_y1)

                    # Horizontal Alignment
                    col_width = inner_x1 - inner_x0
                    cell_center_x = (inner_x0 + inner_x1) / 2.0
                    ink_center_x = (ink_x0 + ink_x1) / 2.0

                    m_num = num_re.match(joined_text)
                    if m_num and ("." in joined_text or pad_r <= 6.0):
                        alignment = "decimal" if "." in joined_text else "right"
                        align_offset = pad_r
                    elif abs(ink_center_x - cell_center_x) <= 2.5 and pad_l > 4.0 and pad_r > 4.0:
                        alignment = "center"
                        align_offset = ink_center_x - cell_center_x
                    elif pad_r < pad_l and pad_r <= 5.0:
                        alignment = "right"
                        align_offset = pad_r
                    else:
                        alignment = "left"
                        align_offset = pad_l

                    # Vertical Position
                    cell_h = inner_y1 - inner_y0
                    cell_mid_y = (inner_y0 + inner_y1) / 2.0
                    ink_mid_y = (ink_y0 + ink_y1) / 2.0
                    if abs(ink_mid_y - cell_mid_y) <= 2.0:
                        v_pos = "middle"
                    elif pad_t < pad_b:
                        v_pos = "top"
                    else:
                        v_pos = "bottom"

                    last_baseline = max(s.origin_point[1] for s in cell_spans)
                    baseline_offset = max(0.0, inner_y1 - last_baseline)

                    # Flags
                    flags = {
                        "touching_border": pad_l < 1.0 or pad_r < 1.0 or pad_t < 1.0 or pad_b < 1.0,
                        "overflow": ink_x1 > inner_x1 + 0.5 or ink_y1 > inner_y1 + 0.5 or ink_x0 < inner_x0 - 0.5,
                        "clipped": False,
                        "empty": False,
                        "spanning": c.is_spanning_header
                    }

                    # Numeric Breakdown
                    numeric_info = None
                    if m_num:
                        decimal_x = None
                        for s in cell_spans:
                            if "." in s.text:
                                decimal_x = s.ink_box.x0.pt + (s.ink_box.x1.pt - s.ink_box.x0.pt) * 0.7
                        numeric_info = {
                            "digits_right_edge": round(ink_x1, 3),
                            "suffix": m_num.group(4) if m_num.group(4) else None,
                            "decimal_x": round(decimal_x, 3) if decimal_x else None
                        }

                else:
                    # Empty Cell
                    ink_box_pt = None
                    pad_l, pad_r, pad_t, pad_b = 0.0, 0.0, 0.0, 0.0
                    alignment = "left"
                    align_offset = 0.0
                    v_pos = "top"
                    baseline_offset = 0.0
                    flags = {
                        "touching_border": False,
                        "overflow": False,
                        "clipped": False,
                        "empty": True,
                        "spanning": c.is_spanning_header
                    }
                    numeric_info = None

                c_model = CellModel(
                    cell_id=cell_id,
                    row_index=r.index,
                    col_index=c.index,
                    bbox=cell_bbox,
                    raw_bbox_pt=raw_box,
                    inner_bbox_pt=inner_box,
                    content=cell_spans,
                    joined_text=joined_text,
                    is_wrapped=is_wrapped,
                    line_count=line_count,
                    ink_bbox_pt=ink_box_pt,
                    padding_left_pt=pad_l,
                    padding_right_pt=pad_r,
                    padding_top_pt=pad_t,
                    padding_bottom_pt=pad_b,
                    padding_left=create_multi_unit_value(pad_l, page_w, self.config.dpi),
                    padding_right=create_multi_unit_value(pad_r, page_w, self.config.dpi),
                    padding_top=create_multi_unit_value(pad_t, page_h, self.config.dpi),
                    padding_bottom=create_multi_unit_value(pad_b, page_h, self.config.dpi),
                    alignment=alignment,
                    alignment_offset_pt=align_offset,
                    vertical_position=v_pos,
                    baseline_offset_from_bottom_pt=baseline_offset,
                    flags=flags,
                    numeric_info=numeric_info
                )
                cells.append(c_model)

        return cells

    def export_cells_csv(self, cells: List[CellModel], csv_path: str) -> None:
        """Exports all cells with detailed measurements, paddings, and alignment to cells.csv."""
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "cell_id", "row_index", "col_index",
                "inner_x0_pt", "inner_y0_pt", "inner_x1_pt", "inner_y1_pt",
                "joined_text", "line_count", "is_wrapped",
                "padding_left_pt", "padding_right_pt", "padding_top_pt", "padding_bottom_pt",
                "alignment", "alignment_offset_pt", "vertical_position",
                "touching_border", "overflow", "empty"
            ])
            for c in cells:
                writer.writerow([
                    c.cell_id, c.row_index, c.col_index,
                    round(c.inner_bbox_pt[0], 3), round(c.inner_bbox_pt[1], 3),
                    round(c.inner_bbox_pt[2], 3), round(c.inner_bbox_pt[3], 3),
                    c.joined_text, c.line_count, c.is_wrapped,
                    round(c.padding_left_pt, 3), round(c.padding_right_pt, 3),
                    round(c.padding_top_pt, 3), round(c.padding_bottom_pt, 3),
                    c.alignment, round(c.alignment_offset_pt, 3), c.vertical_position,
                    c.flags.get("touching_border", False),
                    c.flags.get("overflow", False),
                    c.flags.get("empty", False)
                ])

