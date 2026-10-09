"""
L4 Table Bounding Box & Suffix-Aware Numeric Extent Engine (E2, E13).
Computes exact table bounds strictly from outermost RuleSet rules UNION enclosed content ink,
fuses numeric digits with suffix tokens ('Cr.', 'Dr', parentheses) into single cell entities,
and flags suffixes touching or clipped by cell borders.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGrid, ColumnModel, RowModel


SUFFIX_REGEX = re.compile(r"^(Cr\.?|Dr\.?|\(.*\)|[+-])$", re.IGNORECASE)
NUMERIC_WITH_SUFFIX_REGEX = re.compile(r"^([+-]?[\d,]+\.?\d*)\s*(Cr\.?|Dr\.?|\(.*?\))?$", re.IGNORECASE)


@dataclass
class NumericCellExtent:
    cell_id: str
    column_index: int
    row_index: int
    full_text: str
    numeric_part: str
    suffix_part: Optional[str]
    ink_bbox_pt: Tuple[float, float, float, float]
    touches_right_border: bool = False
    clipped_by_border: bool = False
    distance_to_right_border_pt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "column_index": self.column_index,
            "row_index": self.row_index,
            "full_text": self.full_text,
            "numeric_part": self.numeric_part,
            "suffix_part": self.suffix_part,
            "ink_bbox_pt": list(self.ink_bbox_pt),
            "touches_right_border": self.touches_right_border,
            "clipped_by_border": self.clipped_by_border,
            "distance_to_right_border_pt": self.distance_to_right_border_pt,
        }


NumericSuffixExtent = NumericCellExtent


@dataclass
class ExactTableBBoxResult:
    table_bbox_pt: Tuple[float, float, float, float]
    outer_rule_bbox_pt: Tuple[float, float, float, float]
    content_ink_bbox_pt: Tuple[float, float, float, float]
    numeric_cells: List[NumericCellExtent] = field(default_factory=list)
    has_rules: bool = True
    edge_residual_pt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_bbox_pt": list(self.table_bbox_pt),
            "outer_rule_bbox_pt": list(self.outer_rule_bbox_pt),
            "content_ink_bbox_pt": list(self.content_ink_bbox_pt),
            "has_rules": self.has_rules,
            "edge_residual_pt": self.edge_residual_pt,
            "numeric_cells_count": len(self.numeric_cells),
            "numeric_cells": [c.to_dict() for c in self.numeric_cells],
        }


TableBBoxResult = ExactTableBBoxResult



class TableBBoxEngine:
    """
    Computes exact table bbox and fuses numeric digits with suffix tokens.
    """

    def compute_exact_table_bbox(
        self,
        table_grid: TableGrid,
        page_layer: PageByteLayer,
        ruleset: RuleSet,
    ) -> ExactTableBBoxResult:
        grid_bbox = table_grid.table_bbox_pt
        t_x0, t_y0, t_x1, t_y1 = grid_bbox

        chars_in_table = [
            c for c in page_layer.chars
            if (t_x0 - 1.0 <= c.origin_device_pt[0] <= t_x1 + 1.0 or t_x0 - 1.0 <= c.font_bbox_device_pt[2] <= t_x1 + 1.0)
            and (t_y0 - 2.0 <= c.origin_device_pt[1] <= t_y1 + 2.0)
        ]

        if chars_in_table:
            c_x0 = min(c.font_bbox_device_pt[0] for c in chars_in_table)
            c_y0 = min(c.font_bbox_device_pt[1] for c in chars_in_table)
            c_x1 = max(c.font_bbox_device_pt[2] for c in chars_in_table)
            c_y1 = max(c.font_bbox_device_pt[3] for c in chars_in_table)
            content_ink_bbox = (c_x0, c_y0, c_x1, c_y1)
        else:
            content_ink_bbox = grid_bbox

        if not table_grid.is_borderless and table_grid.boundaries:
            final_x0 = t_x0
            final_x1 = t_x1
            final_y0 = t_y0
            final_y1 = t_y1
            has_rules = True
            edge_res = 0.0
        else:
            final_x0 = min(t_x0, content_ink_bbox[0])
            final_x1 = max(t_x1, content_ink_bbox[2])
            final_y0 = min(t_y0, content_ink_bbox[1])
            final_y1 = max(t_y1, content_ink_bbox[3])
            has_rules = False
            edge_res = abs(final_x1 - t_x1)

        numeric_extents = self._analyze_numeric_cells(page_layer, table_grid)

        return ExactTableBBoxResult(
            table_bbox_pt=(final_x0, final_y0, final_x1, final_y1),
            outer_rule_bbox_pt=grid_bbox,
            content_ink_bbox_pt=content_ink_bbox,
            numeric_cells=numeric_extents,
            has_rules=has_rules,
            edge_residual_pt=edge_res,
        )

    def _analyze_numeric_cells(
        self,
        page_layer: PageByteLayer,
        table_grid: TableGrid,
    ) -> List[NumericCellExtent]:
        results: List[NumericCellExtent] = []
        if not table_grid.columns or not table_grid.rows:
            return results

        for col in table_grid.columns:
            right_border_x = col.x1_pt

            for row in table_grid.rows:
                cell_chars = [
                    c for c in page_layer.chars
                    if (col.x0_pt - 1.0 <= c.origin_device_pt[0] <= col.x1_pt + 1.0)
                    and (row.y0_pt - 1.0 <= c.origin_device_pt[1] <= row.y1_pt + 1.0)
                ]
                if not cell_chars:
                    continue

                cell_chars.sort(key=lambda c: c.origin_device_pt[0])
                cell_text = "".join(c.unicode_text or c.char_text for c in cell_chars).strip()

                m = NUMERIC_WITH_SUFFIX_REGEX.match(cell_text)
                if m:
                    num_part = m.group(1)
                    suf_part = m.group(2)

                    min_x0 = min(c.font_bbox_device_pt[0] for c in cell_chars)
                    min_y0 = min(c.font_bbox_device_pt[1] for c in cell_chars)
                    max_x1 = max(c.font_bbox_device_pt[2] for c in cell_chars)
                    max_y1 = max(c.font_bbox_device_pt[3] for c in cell_chars)

                    dist_to_border = right_border_x - max_x1
                    touches = abs(dist_to_border) <= 1.0
                    clipped = max_x1 > right_border_x + 0.1

                    results.append(NumericCellExtent(
                        cell_id=f"cell_{col.index}_{row.index}",
                        column_index=col.index,
                        row_index=row.index,
                        full_text=cell_text,
                        numeric_part=num_part,
                        suffix_part=suf_part,
                        ink_bbox_pt=(min_x0, min_y0, max_x1, max_y1),
                        touches_right_border=touches,
                        clipped_by_border=clipped,
                        distance_to_right_border_pt=dist_to_border,
                    ))

        return results
