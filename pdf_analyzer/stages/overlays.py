"""
Section 28: Visual Diagnostic Overlays & Rule-Anchored Lane Engine.
Renders high-resolution PNG diagnostic layers on exact-scale 40%-faded page backgrounds:
- header_blocks.png: Side-by-side block bboxes + label & value alignment axes
- footer.png: Flowing/pinned footer region bboxes & page number tokens
- dimension_lane: Exact rule-anchored dimension arrows with numeric pt values
"""

from __future__ import annotations
import os
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import cv2

from pdf_analyzer.stages.frame import PageFrame
from pdf_analyzer.stages.header import HeaderBlock
from pdf_analyzer.stages.footer import FooterRegion
from pdf_analyzer.stages.table_bounds import DimensionArrow

logger = logging.getLogger(__name__)


class StageOverlayRenderer:
    """Renders modular diagnostic overlay PNGs."""

    def __init__(self, page_frame: PageFrame):
        self.frame = page_frame

    def render_header_blocks(
        self,
        base_img_bgr: np.ndarray,
        header_blocks: List[HeaderBlock],
        label_axes: List[float],
        value_axes: List[float],
        output_dir: str
    ) -> str:
        """Renders header side-by-side block outlines and alignment axes."""
        faded = cv2.addWeighted(base_img_bgr, 0.40, np.full_like(base_img_bgr, 255), 0.60, 0)
        overlay = faded.copy()

        for block in header_blocks:
            bx0 = int(round(self.frame.pt_to_px_x(block.bbox_pt[0])))
            by0 = int(round(self.frame.pt_to_px_y(block.bbox_pt[1])))
            bx1 = int(round(self.frame.pt_to_px_x(block.bbox_pt[2])))
            by1 = int(round(self.frame.pt_to_px_y(block.bbox_pt[3])))

            # Block bounding outline
            cv2.rectangle(overlay, (bx0, by0), (bx1, by1), (255, 120, 0), 2)
            cv2.putText(overlay, f"{block.block_id} [{block.position_role}]", (bx0, by0 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (200, 80, 0), 1)

            # Sub-blocks
            for sb in block.sub_blocks:
                sx0 = int(round(self.frame.pt_to_px_x(sb.bbox_pt[0])))
                sy0 = int(round(self.frame.pt_to_px_y(sb.bbox_pt[1])))
                sx1 = int(round(self.frame.pt_to_px_x(sb.bbox_pt[2])))
                sy1 = int(round(self.frame.pt_to_px_y(sb.bbox_pt[3])))
                cv2.rectangle(overlay, (sx0, sy0), (sx1, sy1), (120, 180, 0), 1)

        # Draw Label Axes (Green) & Value Axes (Blue)
        for lax in label_axes:
            px = int(round(self.frame.pt_to_px_x(lax)))
            cv2.line(overlay, (px, 0), (px, int(self.frame.raster_height_px * 0.35)), (0, 180, 0), 1)

        for vax in value_axes:
            px = int(round(self.frame.pt_to_px_x(vax)))
            cv2.line(overlay, (px, 0), (px, int(self.frame.raster_height_px * 0.35)), (220, 50, 0), 1)

        out_path = os.path.join(output_dir, "header_blocks.png")
        cv2.imwrite(out_path, overlay)
        return "header_blocks.png"

    def render_footer(
        self,
        base_img_bgr: np.ndarray,
        footer: Optional[FooterRegion],
        output_dir: str
    ) -> str:
        """Renders footer region bboxes, sub-blocks, and page number token."""
        faded = cv2.addWeighted(base_img_bgr, 0.40, np.full_like(base_img_bgr, 255), 0.60, 0)
        overlay = faded.copy()

        if footer is not None:
            fx0 = int(round(self.frame.pt_to_px_x(footer.bbox_pt[0])))
            fy0 = int(round(self.frame.pt_to_px_y(footer.bbox_pt[1])))
            fx1 = int(round(self.frame.pt_to_px_x(footer.bbox_pt[2])))
            fy1 = int(round(self.frame.pt_to_px_y(footer.bbox_pt[3])))

            cv2.rectangle(overlay, (fx0, fy0), (fx1, fy1), (180, 0, 180), 2)
            cv2.putText(overlay, f"FOOTER ({footer.classification})", (fx0, fy0 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 0, 160), 1)

            for sb in footer.sub_blocks:
                sx0 = int(round(self.frame.pt_to_px_x(sb.bbox_pt[0])))
                sy0 = int(round(self.frame.pt_to_px_y(sb.bbox_pt[1])))
                sx1 = int(round(self.frame.pt_to_px_x(sb.bbox_pt[2])))
                sy1 = int(round(self.frame.pt_to_px_y(sb.bbox_pt[3])))
                col = (0, 0, 220) if sb.is_page_number else (100, 100, 100)
                cv2.rectangle(overlay, (sx0, sy0), (sx1, sy1), col, 1)

        out_path = os.path.join(output_dir, "footer.png")
        cv2.imwrite(out_path, overlay)
        return "footer.png"
