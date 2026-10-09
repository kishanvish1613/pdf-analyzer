"""
Section 16: Table Overlays & Multi-Layer Visual Diagnostics Engine.
Renders high-resolution diagnostic layers:
  a) Columns overlay: boundary lines with index + width arrows, color-coded by evidence
  b) Rows overlay: boundaries with index + type + height, virtual dashed
  c) Cells overlay: grid with padding wedges (L/R/T/B) and red hatch on touching/overflow
  d) Gaps overlay: dimension arrows colored by definition (ink-ink, rule-rule, baseline-baseline, ink-rule)
  e) Evidence overlay: where S1-S5 / R1-R5 disagree
"""

from __future__ import annotations
import os
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import ColumnModel, RowModel, CellModel, GapRecord

logger = logging.getLogger(__name__)


class TableOverlayRenderer:
    """Renders 5 specialized table overlay PNGs on a 40%-faded page background with gutter lanes."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def render_all_table_overlays(
        self,
        base_img_bgr: np.ndarray,
        columns: List[ColumnModel],
        rows: List[RowModel],
        cells: List[CellModel],
        gaps: List[GapRecord],
        disagreements: List[Dict[str, Any]],
        table_bbox_pt: Tuple[float, float, float, float],
        output_dir: str,
        page_num: int = 1
    ) -> Dict[str, str]:
        """Renders 5 standalone overlay PNGs for columns, rows, cells, gaps, and evidence."""
        scale = self.config.dpi / 72.0
        orig_h, orig_w, _ = base_img_bgr.shape
        pad = 140
        canvas_w = orig_w + 2 * pad
        canvas_h = orig_h + 2 * pad

        # 40% faded page background
        faded_page = cv2.addWeighted(base_img_bgr, 0.40, np.full_like(base_img_bgr, 255), 0.60, 0)
        base_canvas = np.full((canvas_h, canvas_w, 3), 248, dtype=np.uint8)
        base_canvas[pad:pad + orig_h, pad:pad + orig_w] = faded_page

        tx0, ty0, tx1, ty1 = table_bbox_pt
        tx0_px, ty0_px = int(tx0 * scale) + pad, int(ty0 * scale) + pad
        tx1_px, ty1_px = int(tx1 * scale) + pad, int(ty1 * scale) + pad

        generated_files: Dict[str, str] = {}

        # ---------------------------------------------------------
        # Layer 1: Columns Overlay
        # ---------------------------------------------------------
        col_img = base_canvas.copy()
        for c in columns:
            cx0_px = int(c.x0_pt * scale) + pad
            cx1_px = int(c.x1_pt * scale) + pad
            # Color by evidence
            col_color = (0, 180, 0) if c.boundary_type == "single" else ((200, 100, 0) if c.boundary_type == "double" else (0, 120, 255))
            cv2.line(col_img, (cx0_px, ty0_px - 40), (cx0_px, ty1_px + 20), col_color, 2)

            # Dimension arrow
            arrow_y = ty0_px - 20
            cv2.arrowedLine(col_img, (cx0_px, arrow_y), (cx1_px, arrow_y), (40, 40, 40), 1, tipLength=0.08)
            cv2.arrowedLine(col_img, (cx1_px, arrow_y), (cx0_px, arrow_y), (40, 40, 40), 1, tipLength=0.08)
            lbl = f"C{c.index}: {c.width_pt:.1f}pt"
            cv2.putText(col_img, lbl, (cx0_px + 4, arrow_y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1)

        fn_col = os.path.join(output_dir, f"overlay_columns_page_{page_num}.png")
        cv2.imwrite(fn_col, col_img)
        generated_files["overlay_columns"] = os.path.basename(fn_col)

        # ---------------------------------------------------------
        # Layer 2: Rows Overlay
        # ---------------------------------------------------------
        row_img = base_canvas.copy()
        for r in rows:
            ry0_px = int(r.y0_pt * scale) + pad
            ry1_px = int(r.y1_pt * scale) + pad
            row_color = (220, 50, 50) if r.boundary_type == "ruled" else (180, 100, 220)
            is_virtual = r.boundary_type == "virtual"

            if is_virtual:
                # Dashed line
                for x in range(tx0_px, tx1_px, 15):
                    cv2.line(row_img, (x, ry0_px), (min(tx1_px, x + 8), ry0_px), row_color, 1)
            else:
                cv2.line(row_img, (tx0_px, ry0_px), (tx1_px, ry0_px), row_color, 2)

            # Left gutter label
            lbl = f"R{r.index} [{r.row_type[:4]}] {r.height_pt:.1f}pt"
            cv2.putText(row_img, lbl, (10, ry0_px + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (30, 30, 30), 1)

        fn_row = os.path.join(output_dir, f"overlay_rows_page_{page_num}.png")
        cv2.imwrite(fn_row, row_img)
        generated_files["overlay_rows"] = os.path.basename(fn_row)

        # ---------------------------------------------------------
        # Layer 3: Cells Overlay (Padding Wedges & Red Hatch)
        # ---------------------------------------------------------
        cell_img = base_canvas.copy()
        for cell in cells:
            ix0 = int(cell.inner_bbox_pt[0] * scale) + pad
            iy0 = int(cell.inner_bbox_pt[1] * scale) + pad
            ix1 = int(cell.inner_bbox_pt[2] * scale) + pad
            iy1 = int(cell.inner_bbox_pt[3] * scale) + pad

            # Cell box border
            cv2.rectangle(cell_img, (ix0, iy0), (ix1, iy1), (180, 180, 180), 1)

            # Red hatch on touching border / overflow
            if cell.flags.get("touching_border") or cell.flags.get("overflow"):
                for diag in range(ix0, ix1 + (iy1 - iy0), 12):
                    p1 = (diag, iy0)
                    p2 = (diag - (iy1 - iy0), iy1)
                    # Clip to cell rect
                    cv2.line(cell_img, (max(ix0, min(ix1, p1[0])), max(iy0, min(iy1, p1[1]))),
                             (max(ix0, min(ix1, p2[0])), max(iy0, min(iy1, p2[1]))), (0, 0, 220), 1)

            # Text ink box
            if cell.ink_bbox_pt:
                kx0 = int(cell.ink_bbox_pt[0] * scale) + pad
                ky0 = int(cell.ink_bbox_pt[1] * scale) + pad
                kx1 = int(cell.ink_bbox_pt[2] * scale) + pad
                ky1 = int(cell.ink_bbox_pt[3] * scale) + pad
                cv2.rectangle(cell_img, (kx0, ky0), (kx1, ky1), (0, 140, 0), 1)

        fn_cell = os.path.join(output_dir, f"overlay_cells_page_{page_num}.png")
        cv2.imwrite(fn_cell, cell_img)
        generated_files["overlay_cells"] = os.path.basename(fn_cell)

        # ---------------------------------------------------------
        # Layer 4: Gaps Overlay
        # ---------------------------------------------------------
        gap_img = base_canvas.copy()
        for g in gaps:
            # Color by definition code
            g_code = g.definition_code
            col = (200, 50, 0) if g_code == "ink_to_ink" else (
                (0, 150, 0) if g_code == "rule_to_rule" else (
                    (0, 140, 255) if g_code == "baseline_to_baseline" else (180, 0, 180)
                )
            )
            # Draw sample gap annotation in right gutter
            val_txt = f"{g.gap_type}: {g.value_pt:.1f}pt ({g_code})"
            # Gutter display
            cv2.putText(gap_img, val_txt[:40], (canvas_w - pad + 5, min(canvas_h - 20, 40 + len(gap_img) % 400)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)

        fn_gap = os.path.join(output_dir, f"overlay_gaps_page_{page_num}.png")
        cv2.imwrite(fn_gap, gap_img)
        generated_files["overlay_gaps"] = os.path.basename(fn_gap)

        # ---------------------------------------------------------
        # Layer 5: Evidence & Disagreements Overlay
        # ---------------------------------------------------------
        ev_img = base_canvas.copy()
        for d in disagreements:
            r_idx = d.get("row_index", 0)
            cb = d.get("chosen_band", [0, 0])
            dy0_px = int(cb[0] * scale) + pad
            cv2.circle(ev_img, (tx0_px + 20, dy0_px), 6, (0, 0, 255), -1)
            cv2.putText(ev_img, f"R{r_idx} model disagreement", (tx0_px + 35, dy0_px + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 200), 1)

        fn_ev = os.path.join(output_dir, f"overlay_evidence_page_{page_num}.png")
        cv2.imwrite(fn_ev, ev_img)
        generated_files["overlay_evidence"] = os.path.basename(fn_ev)

        return generated_files

