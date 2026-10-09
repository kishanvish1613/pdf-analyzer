"""
L4 Page Margins, Logo Extraction, and Alignment Axes Engine (E7).
Computes content-wide margins vs text-only margins, tracks margin source elements,
detects raster and vector logos with effective DPI calculation, and clusters implicit alignment axes.
"""

from __future__ import annotations
import math
from typing import List, Dict, Tuple, Optional, Any, Set
import numpy as np

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, PaintedPath
from pdf_analyzer.l4_layout.models import MarginsModel, LogoModel


class MarginsLogoEngine:
    """
    Recovers page margins, detects logos, and clusters alignment axes.
    """

    def compute_margins_and_logo(
        self,
        page_layer: PageByteLayer,
    ) -> Tuple[MarginsModel, Optional[LogoModel], List[float]]:
        """
        Extracts margins, header logo, and alignment axes for the page.
        """
        margins = self.compute_margins(page_layer)
        header_y_min = page_layer.height_pt - margins.top_margin_pt - 100.0
        logo = self.detect_logo(page_layer, header_y_min=header_y_min)

        # Collect alignment axes from char origins and path coordinates
        x_coords: List[float] = []
        for c in page_layer.chars:
            x_coords.append(c.origin_device_pt[0])
        for p in page_layer.paths:
            if p.bbox_device_pt and (p.stroke or p.fill_color):
                x_coords.append(p.bbox_device_pt[0])
                x_coords.append(p.bbox_device_pt[2])

        alignment_axes = self.cluster_alignment_axes(x_coords, tol_pt=0.5)
        return margins, logo, alignment_axes

    def compute_margins(self, page_layer: PageByteLayer) -> MarginsModel:
        """
        Calculates content-wide and text-only page margins.
        """
        p_w = page_layer.width_pt
        p_h = page_layer.height_pt

        # 1. Text-only margins
        if page_layer.chars:
            t_x0 = min(c.font_bbox_device_pt[0] for c in page_layer.chars)
            t_y0 = min(c.font_bbox_device_pt[1] for c in page_layer.chars)
            t_x1 = max(c.font_bbox_device_pt[2] for c in page_layer.chars)
            t_y1 = max(c.font_bbox_device_pt[3] for c in page_layer.chars)
            text_margins = (t_x0, p_w - t_x1, p_h - t_y1, t_y0)
        else:
            text_margins = (36.0, 36.0, 36.0, 36.0)

        # 2. Content-wide margins (chars + paths + images)
        all_x0: List[float] = []
        all_y0: List[float] = []
        all_x1: List[float] = []
        all_y1: List[float] = []

        for c in page_layer.chars:
            all_x0.append(c.font_bbox_device_pt[0])
            all_y0.append(c.font_bbox_device_pt[1])
            all_x1.append(c.font_bbox_device_pt[2])
            all_y1.append(c.font_bbox_device_pt[3])

        for p in page_layer.paths:
            if p.bbox_device_pt and (p.stroke or p.fill_color):
                all_x0.append(p.bbox_device_pt[0])
                all_y0.append(p.bbox_device_pt[1])
                all_x1.append(p.bbox_device_pt[2])
                all_y1.append(p.bbox_device_pt[3])

        for img in page_layer.images:
            all_x0.append(img.bbox_device_pt[0])
            all_y0.append(img.bbox_device_pt[1])
            all_x1.append(img.bbox_device_pt[2])
            all_y1.append(img.bbox_device_pt[3])

        if all_x0:
            c_x0 = min(all_x0)
            c_y0 = min(all_y0)
            c_x1 = max(all_x1)
            c_y1 = max(all_y1)

            left_m = max(0.0, c_x0)
            right_m = max(0.0, p_w - c_x1)
            top_m = max(0.0, p_h - c_y1)
            bottom_m = max(0.0, c_y0)
        else:
            left_m, right_m, top_m, bottom_m = 36.0, 36.0, 36.0, 36.0

        return MarginsModel(
            left_margin_pt=float(left_m),
            right_margin_pt=float(right_m),
            top_margin_pt=float(top_m),
            bottom_margin_pt=float(bottom_m),
            left_source="content_ink",
            right_source="content_ink",
            top_source="content_ink",
            bottom_source="content_ink",
            text_only_margins_pt=text_margins,
        )

    def detect_logo(self, page_layer: PageByteLayer, header_y_min: float) -> Optional[LogoModel]:
        """
        Detects raster or vector logo in the header region.
        """
        # Check raster images in header
        header_images = [
            img for img in page_layer.images
            if img.bbox_device_pt and img.bbox_device_pt[1] >= header_y_min - 20.0
        ]
        if header_images:
            # Sort by area or top position
            img = max(header_images, key=lambda i: (i.bbox_device_pt[2] - i.bbox_device_pt[0]) * (i.bbox_device_pt[3] - i.bbox_device_pt[1]))
            w_pt = img.bbox_device_pt[2] - img.bbox_device_pt[0]
            h_pt = img.bbox_device_pt[3] - img.bbox_device_pt[1]
            eff_dpi = (img.width_px / (w_pt / 72.0)) if (w_pt > 0 and img.width_px > 0) else 300.0

            return LogoModel(
                logo_id="logo_raster_0",
                bbox_pt=img.bbox_device_pt,
                effective_dpi=float(eff_dpi),
                offset_to_left_margin_pt=float(img.bbox_device_pt[0]),
                offset_to_top_margin_pt=float(page_layer.height_pt - img.bbox_device_pt[3]),
            )

        # Check clustered vector paths forming a logo (e.g. at top-left or top-right)
        header_paths = [
            p for p in page_layer.paths
            if p.bbox_device_pt and (p.stroke or p.fill_color) and p.bbox_device_pt[3] >= header_y_min
        ]
        if len(header_paths) >= 3:
            non_rule_paths = [p for p in header_paths if not self._is_simple_rule(p)]
            if len(non_rule_paths) >= 2:
                bx0 = min(p.bbox_device_pt[0] for p in non_rule_paths)
                by0 = min(p.bbox_device_pt[1] for p in non_rule_paths)
                bx1 = max(p.bbox_device_pt[2] for p in non_rule_paths)
                by1 = max(p.bbox_device_pt[3] for p in non_rule_paths)
                return LogoModel(
                    logo_id="logo_vector_0",
                    bbox_pt=(bx0, by0, bx1, by1),
                    effective_dpi=600.0,  # Vector resolution
                    offset_to_left_margin_pt=float(bx0),
                    offset_to_top_margin_pt=float(page_layer.height_pt - by1),
                )

        return None

    def cluster_alignment_axes(self, x_coords: List[float], tol_pt: float = 0.5) -> List[float]:
        """
        Clusters a list of X-coordinates into distinct alignment axes with given tolerance.
        """
        if not x_coords:
            return []
        sorted_x = sorted(x_coords)
        clusters: List[List[float]] = []
        curr = [sorted_x[0]]

        for x in sorted_x[1:]:
            if x - curr[-1] <= tol_pt:
                curr.append(x)
            else:
                clusters.append(curr)
                curr = [x]
        if curr:
            clusters.append(curr)

        return [float(np.mean(cl)) for cl in clusters]

    def _is_simple_rule(self, path: PaintedPath) -> bool:
        bx0, by0, bx1, by1 = path.bbox_device_pt
        w = bx1 - bx0
        h = by1 - by0
        return w <= 2.0 or h <= 2.0
