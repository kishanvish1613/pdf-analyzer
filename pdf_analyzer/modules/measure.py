"""
Section 13: Measurement Ontology, Multi-Frame Coordinates & Gap Matrix Engine.
Enforces named anchors, produces structured MeasurementRecords and GapRecords,
reports coordinates in 3 frames (page, parent, table), and exports CSVs.
"""

from __future__ import annotations
import csv
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import (
    MultiUnitValue, TextSpanModel, ColumnModel, RowModel, CellModel,
    MeasurementRecord, GapRecord
)
from pdf_analyzer.utils.units import pt_to_mm, pt_to_px

logger = logging.getLogger(__name__)

# Measurement Ontology Named Anchors
ANCHORS = [
    "RULE_CENTER", "RULE_INNER_EDGE", "RULE_OUTER_EDGE",
    "INK_TOP", "INK_BOTTOM", "INK_LEFT", "INK_RIGHT",
    "BASELINE", "CAP_LINE", "X_HEIGHT_LINE",
    "FONT_BOX_TOP", "FONT_BOX_BOTTOM",
    "CELL_INNER_EDGE", "PAGE_EDGE", "CONTENT_EDGE"
]


class PrecisionMeasurer:
    """Computes comprehensive gap matrices, 3-frame coordinate systems, and repeating pitch statistics."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def build_measurements_and_gaps(
        self,
        columns: List[ColumnModel],
        rows: List[RowModel],
        cells: List[CellModel],
        layout_spec: Dict[str, Any],
        page_w: float,
        page_h: float,
        table_bbox_pt: Tuple[float, float, float, float],
        page_num: int = 1
    ) -> Dict[str, Any]:
        """Calculates gap matrix, multi-frame coordinates, and pitch metrics."""
        tx0, ty0, tx1, ty1 = table_bbox_pt
        table_w = tx1 - tx0
        table_h = ty1 - ty0
        dpi = self.config.dpi

        measurements: List[MeasurementRecord] = []
        gaps: List[GapRecord] = []

        # ---------------------------------------------------------
        # 1. Page Gap Matrix (All Required Page Intervals)
        # ---------------------------------------------------------
        regions = layout_spec.get("regions", [])
        reg_map = {r.get("region_type"): r.get("raw_bbox_pt") for r in regions}

        # Page top -> First element
        first_elem_y = min((r[1] for r in reg_map.values()), default=ty0)
        gap_top = max(0.0, first_elem_y)
        gaps.append(self._create_gap(
            "gap_page_top_first_elem", "PAGE_TOP", "FIRST_ELEMENT", "page_top_to_first_element",
            "ink_to_ink", gap_top, dpi, "Distance from page top (y=0) to the highest ink element top"
        ))

        # Logo -> Address block
        if "logo_branding" in reg_map and "address_block" in reg_map:
            l_b = reg_map["logo_branding"]
            a_b = reg_map["address_block"]
            gap_logo_addr = max(0.0, a_b[1] - l_b[3])
            gaps.append(self._create_gap(
                "gap_logo_to_address", "LOGO", "ADDRESS_BLOCK", "logo_to_address",
                "ink_to_ink", gap_logo_addr, dpi, "Vertical gap from bottom of logo to top of address container"
            ))

        # Address block -> Key-Value block (horizontal gap)
        if "address_block" in reg_map and "key_value_grid" in reg_map:
            a_b = reg_map["address_block"]
            kv_b = reg_map["key_value_grid"]
            gap_addr_kv = max(0.0, kv_b[0] - a_b[2])
            gaps.append(self._create_gap(
                "gap_address_to_kv_h", "ADDRESS_BLOCK", "KEY_VALUE_GRID", "address_to_kv_horizontal",
                "inner_to_inner", gap_addr_kv, dpi, "Horizontal whitespace between address container and key-value block"
            ))

        # Key-Value block -> Heading line
        if "key_value_grid" in reg_map and "heading_band" in reg_map:
            kv_b = reg_map["key_value_grid"]
            h_b = reg_map["heading_band"]
            gap_kv_hdg = max(0.0, h_b[1] - kv_b[3])
            gaps.append(self._create_gap(
                "gap_kv_to_heading", "KEY_VALUE_GRID", "HEADING_BAND", "kv_to_heading",
                "ink_to_ink", gap_kv_hdg, dpi, "Vertical gap from key-value block bottom to heading line top"
            ))

        # Heading line -> Table top
        if "heading_band" in reg_map:
            h_b = reg_map["heading_band"]
            gap_hdg_tbl = max(0.0, ty0 - h_b[3])
            gaps.append(self._create_gap(
                "gap_heading_to_table", "HEADING_BAND", "TRANSACTION_TABLE", "heading_to_table_top",
                "ink_to_rule", gap_hdg_tbl, dpi, "Vertical gap from heading bottom to top table rule"
            ))

        # Table top -> Header text
        header_cells = [c for c in cells if c.row_index == 0 and c.ink_bbox_pt]
        if header_cells:
            first_h_top = min(c.ink_bbox_pt[1] for c in header_cells)
            gap_tbl_htext = max(0.0, first_h_top - ty0)
            gaps.append(self._create_gap(
                "gap_table_top_to_header_text", "TABLE_TOP_RULE", "HEADER_TEXT", "table_top_to_header_text",
                "rule_to_rule", gap_tbl_htext, dpi, "Top padding from table top rule to header text ink top"
            ))

        # Header bottom -> First body row
        if len(rows) >= 2:
            gap_hdr_body = max(0.0, rows[1].y0_pt - rows[0].y1_pt)
            gaps.append(self._create_gap(
                "gap_header_to_first_body", "HEADER_ROW", "ROW_1", "header_bottom_to_first_body_row",
                "inner_to_inner", gap_hdr_body, dpi, "Gap/rule between header row bottom and first body row top"
            ))

        # Row n -> Row n+1 (ALL rows full list)
        for i in range(len(rows) - 1):
            r_curr = rows[i]
            r_next = rows[i + 1]
            r_gap = max(0.0, r_next.y0_pt - r_curr.y1_pt)
            gaps.append(self._create_gap(
                f"gap_row_{i}_to_row_{i+1}", f"ROW_{i}", f"ROW_{i+1}", f"row_n_to_row_n_plus_1",
                "rule_to_rule" if r_curr.boundary_type == "ruled" else "baseline_to_baseline",
                r_gap, dpi, f"Inter-row boundary distance between row {i} and row {i+1}"
            ))

        # Last row -> Table bottom
        if rows:
            last_r = rows[-1]
            gap_last_tbl = max(0.0, ty1 - last_r.y1_pt)
            gaps.append(self._create_gap(
                "gap_last_row_to_table_bottom", f"ROW_{len(rows)-1}", "TABLE_BOTTOM_RULE", "last_row_to_table_bottom",
                "rule_to_rule", gap_last_tbl, dpi, "Distance from last row bottom to table closing rule"
            ))

        # Table bottom -> Footer
        if "footer_disclaimer" in reg_map:
            f_b = reg_map["footer_disclaimer"]
            gap_tbl_ftr = max(0.0, f_b[1] - ty1)
            gaps.append(self._create_gap(
                "gap_table_to_footer", "TRANSACTION_TABLE", "FOOTER", "table_bottom_to_footer",
                "rule_to_rule", gap_tbl_ftr, dpi, "Gap from table bottom rule to footer top ink"
            ))
            # Footer -> Page bottom
            gap_ftr_bot = max(0.0, page_h - f_b[3])
            gaps.append(self._create_gap(
                "gap_footer_to_page_bottom", "FOOTER", "PAGE_BOTTOM", "footer_to_page_bottom",
                "ink_to_ink", gap_ftr_bot, dpi, "Bottom margin from footer ink bottom to page bottom"
            ))

        # Page margins to table
        gap_m_left = max(0.0, tx0)
        gap_m_right = max(0.0, page_w - tx1)
        gaps.append(self._create_gap(
            "margin_left_to_table", "PAGE_LEFT", "TABLE_LEFT", "margin_left_to_table",
            "rule_to_rule", gap_m_left, dpi, "Left margin from page edge to table left vertical rule"
        ))
        gaps.append(self._create_gap(
            "margin_right_to_table", "TABLE_RIGHT", "PAGE_RIGHT", "margin_right_to_table",
            "rule_to_rule", gap_m_right, dpi, "Right margin from table right vertical rule to page right edge"
        ))

        # Column rules to first/last ink per column
        cols = columns or []
        for c in cols:
            col_cells = [cell for cell in cells if cell.col_index == c.index and cell.ink_bbox_pt]
            if col_cells:
                min_pad_l = min(cell.padding_left_pt for cell in col_cells)
                min_pad_r = min(cell.padding_right_pt for cell in col_cells)
                gaps.append(self._create_gap(
                    f"pad_left_col_{c.index}", f"RULE_V_{c.index}", f"COL_{c.index}_INK", "rule_to_first_ink",
                    "ink_to_rule", min_pad_l, dpi, f"Left padding from column {c.index} left rule to first text ink"
                ))
                gaps.append(self._create_gap(
                    f"pad_right_col_{c.index}", f"COL_{c.index}_INK", f"RULE_V_{c.index+1}", "last_ink_to_rule",
                    "ink_to_rule", min_pad_r, dpi, f"Right padding from column {c.index} last text ink to right rule"
                ))

        # ---------------------------------------------------------
        # 2. Multi-Frame Position Coordinates (Page, Parent, Table)
        # ---------------------------------------------------------
        positions = {
            "table_frame": {
                "origin_in_page_pt": [round(tx0, 3), round(ty0, 3)],
                "width_pt": round(table_w, 3),
                "height_pt": round(table_h, 3)
            },
            "columns": [
                {
                    "index": c.index,
                    "page_frame": {"x0": round(c.x0_pt, 3), "x1": round(c.x1_pt, 3), "w": round(c.width_pt, 3)},
                    "table_frame": {"x0": round(c.x0_pt - tx0, 3), "x1": round(c.x1_pt - tx0, 3), "w": round(c.width_pt, 3)},
                    "offset_from_table_left_pt": round(c.x0_pt - tx0, 3)
                }
                for c in cols
            ],
            "rows": [
                {
                    "index": r.index,
                    "page_frame": {"y0": round(r.y0_pt, 3), "y1": round(r.y1_pt, 3), "h": round(r.height_pt, 3)},
                    "table_frame": {"y0": round(r.y0_pt - ty0, 3), "y1": round(r.y1_pt - ty0, 3), "h": round(r.height_pt, 3)},
                    "offset_from_table_top_pt": round(r.y0_pt - ty0, 3)
                }
                for r in rows
            ],
            "cells": [
                {
                    "cell_id": cell.cell_id,
                    "row": cell.row_index,
                    "col": cell.col_index,
                    "page_frame": {
                        "x0": round(cell.inner_bbox_pt[0], 3), "y0": round(cell.inner_bbox_pt[1], 3),
                        "x1": round(cell.inner_bbox_pt[2], 3), "y1": round(cell.inner_bbox_pt[3], 3)
                    },
                    "table_frame": {
                        "x0": round(cell.inner_bbox_pt[0] - tx0, 3), "y0": round(cell.inner_bbox_pt[1] - ty0, 3),
                        "x1": round(cell.inner_bbox_pt[2] - tx0, 3), "y1": round(cell.inner_bbox_pt[3] - ty0, 3)
                    }
                }
                for cell in cells
            ]
        }

        # ---------------------------------------------------------
        # 3. Repeating Pattern & Pitch Statistics
        # ---------------------------------------------------------
        row_heights = [r.height_pt for r in rows if r.row_type != "HEADER"] or [15.0]
        mean_pitch = float(np.mean(row_heights))
        std_pitch = float(np.std(row_heights)) if len(row_heights) > 1 else 0.0

        line_counts = [cell.line_count for cell in cells if cell.line_count > 0] or [1]
        dist_counts = {str(k): int(v) for k, v in zip(*np.unique(line_counts, return_counts=True))}

        pitch_report = {
            "nominal_pitch_pt": round(mean_pitch, 3),
            "pitch_std_pt": round(std_pitch, 3),
            "lines_per_row_distribution": dist_counts,
            "per_row_deviations": [
                {"row_index": r.index, "height_pt": round(r.height_pt, 3), "delta_from_nominal_pt": round(r.height_pt - mean_pitch, 3)}
                for r in rows
            ]
        }

        return {
            "gaps": [g.to_dict() for g in gaps],
            "positions": positions,
            "pitch_report": pitch_report,
            "raw_gaps": gaps
        }

    def _create_gap(
        self,
        gap_id: str,
        from_el: str,
        to_el: str,
        gap_type: str,
        def_code: str,
        val_pt: float,
        dpi: int,
        def_str: str
    ) -> GapRecord:
        return GapRecord(
            id=gap_id,
            from_element=from_el,
            to_element=to_el,
            gap_type=gap_type,
            definition_code=def_code,
            value_pt=val_pt,
            value_mm=pt_to_mm(val_pt),
            value_px=pt_to_px(val_pt, dpi),
            definition_string=def_str
        )

    def export_gaps_csv(self, gaps: List[GapRecord], csv_path: str) -> None:
        """Exports full gap matrix to gaps.csv."""
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "gap_id", "from_element", "to_element", "gap_type", "definition_code",
                "value_pt", "value_mm", "value_px", "definition_string"
            ])
            for g in gaps:
                writer.writerow([
                    g.id, g.from_element, g.to_element, g.gap_type, g.definition_code,
                    round(g.value_pt, 3), round(g.value_mm, 2), round(g.value_px, 1),
                    g.definition_string
                ])

    def export_columns_csv(self, columns: List[ColumnModel], csv_path: str) -> None:
        """Exports column boundaries and evidence to columns.csv."""
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "column_index", "x0_pt", "x1_pt", "width_pt", "width_mm", "width_px",
                "left_rule_id", "right_rule_id", "header_text", "boundary_type",
                "is_double_rule", "is_spanning_header", "confidence"
            ])
            for c in columns:
                writer.writerow([
                    c.index, round(c.x0_pt, 3), round(c.x1_pt, 3),
                    round(c.width_pt, 3), round(c.width.mm, 2), round(c.width.px, 1),
                    c.left_rule_id, c.right_rule_id, c.header_text, c.boundary_type,
                    c.is_double_rule, c.is_spanning_header, round(c.confidence, 3)
                ])

    def export_rows_csv(self, rows: List[RowModel], csv_path: str) -> None:
        """Exports row bands and types to rows.csv."""
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "row_index", "row_type", "y0_pt", "y1_pt", "height_pt", "height_mm", "height_px",
                "boundary_type", "gap_to_next_pt", "is_estimated_bottom", "confidence"
            ])
            for r in rows:
                writer.writerow([
                    r.index, r.row_type, round(r.y0_pt, 3), round(r.y1_pt, 3),
                    round(r.height_pt, 3), round(r.height.mm, 2), round(r.height.px, 1),
                    r.boundary_type, round(r.gap_to_next_pt, 3), r.is_estimated_bottom,
                    round(r.confidence, 3)
                ])

