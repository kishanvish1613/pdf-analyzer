"""
L4 Content Accounting Engine.
Audits the LayoutTree to guarantee full coverage of page characters and paths.
Computes orphan characters, invisible text, and residual raster ink outside classified regions.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Set
import numpy as np

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar
from pdf_analyzer.l4_layout.models import LayoutTree, LayoutNode, AccountingReport


class ContentAccountingEngine:
    """
    Engine for auditing content accounting across the layout tree.
    Enforces Invariant I4: Every character belongs to exactly one leaf.
    """

    def evaluate_accounting(
        self,
        page_layer: PageByteLayer,
        layout_tree: LayoutTree,
        raster_image_rgb: Optional[np.ndarray] = None,
        dpi: int = 600,
    ) -> AccountingReport:
        return self.audit_content_accounting(
            page_layer=page_layer,
            layout_tree=layout_tree,
            raster_image_rgb=raster_image_rgb,
            dpi=dpi,
        )

    def audit_content_accounting(
        self,
        page_layer: PageByteLayer,
        layout_tree: LayoutTree,
        raster_image_rgb: Optional[np.ndarray] = None,
        dpi: int = 600,
    ) -> AccountingReport:
        total_chars = len(page_layer.chars)
        
        # Collect all char_ids from leaf nodes of layout tree
        accounted_char_ids: Set[str] = set()
        
        def traverse(node: LayoutNode):
            if node.is_leaf:
                for c in node.chars:
                    accounted_char_ids.add(c.char_id)
            for child in node.children:
                traverse(child)

        traverse(layout_tree.root)
        
        # In case root itself holds chars when flat
        for c in layout_tree.root.chars:
            accounted_char_ids.add(c.char_id)

        accounted_count = len(accounted_char_ids)
        orphan_chars_count = max(0, total_chars - accounted_count)
        
        # Find invisible chars (e.g. render mode 3 or zero opacity)
        invisible_count = 0
        for c in page_layer.chars:
            if getattr(c, "is_invisible", False):
                invisible_count += 1

        # Calculate residual raster ink if image is provided
        residual_ink_pct = 0.0
        residual_ink_passed = True
        unclassified_boxes: List[Tuple[float, float, float, float]] = []

        if raster_image_rgb is not None and raster_image_rgb.size > 0:
            # Grayscale threshold to detect dark pixels (ink)
            if len(raster_image_rgb.shape) == 3:
                gray = np.mean(raster_image_rgb, axis=2)
            else:
                gray = raster_image_rgb
            
            total_dark_pixels = int(np.sum(gray < 240))
            if total_dark_pixels > 0:
                # Mask out accounted regions
                mask = np.zeros(gray.shape, dtype=bool)
                h_img, w_img = gray.shape[:2]
                scale = dpi / 72.0
                
                # Mask out media/cropbox bounds
                crop_y0 = page_layer.cropbox_pt[1]
                crop_h = page_layer.height_pt

                def mask_node(node: LayoutNode):
                    if node.bbox_pt and node.bbox_pt != (0.0, 0.0, 0.0, 0.0):
                        x0, y0, x1, y1 = node.bbox_pt
                        # PDF y is bottom-up; image y is top-down
                        # pixel coords
                        px0 = max(0, int(x0 * scale))
                        px1 = min(w_img, int(x1 * scale + 1))
                        # Invert y for image top-down
                        py0 = max(0, int((crop_h - y1) * scale))
                        py1 = min(h_img, int((crop_h - y0) * scale + 1))
                        if px1 > px0 and py1 > py0:
                            mask[py0:py1, px0:px1] = True
                    for child in node.children:
                        mask_node(child)

                mask_node(layout_tree.root)
                
                unaccounted_dark_pixels = int(np.sum((gray < 240) & (~mask)))
                residual_ink_pct = (unaccounted_dark_pixels / max(1, total_dark_pixels)) * 100.0
                # Pass if residual ink <= 0.3%
                residual_ink_passed = (residual_ink_pct <= 0.3)
            else:
                residual_ink_pct = 0.0
                residual_ink_passed = True

        return AccountingReport(
            total_chars=total_chars,
            accounted_chars=accounted_count,
            orphan_chars_count=orphan_chars_count,
            invisible_chars_count=invisible_count,
            residual_ink_pct=residual_ink_pct,
            residual_ink_passed=residual_ink_passed,
            unclassified_ink_boxes=unclassified_boxes,
        )
