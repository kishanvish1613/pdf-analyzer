"""Module I: Background colors and shading analysis.

Extracts vector fill colors across document regions, cross-validates with raster pixel sampling
via OpenCV K-means, and detects gradient fills.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.extractors.raster_extractor import RasterExtractor
from pdf_analyzer.utils.color import is_near_white


class BackgroundsAnalyzer:
    """Analyzes vector and raster background colors, header bands, and zebra row shading."""

    def __init__(self, config: AnalyzerConfig, raster_extractor: RasterExtractor):
        self.config = config
        self.raster_extractor = raster_extractor

    def analyze_backgrounds(
        self,
        drawings: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        img_bgr: np.ndarray,
        page_w: float,
        page_h: float
    ) -> Dict[str, Any]:
        """Map background fills to regions and validate against raster pixel sampling."""
        # 1. Page Background (Check large vector rect covering >= 80% page)
        page_bg_hex = "#FFFFFF"
        for d in drawings:
            w = d.get("width_pt", 0)
            h = d.get("height_pt", 0)
            fill_hex = d.get("fill_color_hex")
            if fill_hex and w >= page_w * 0.8 and h >= page_h * 0.8:
                page_bg_hex = fill_hex
                break

        # 2. Region-specific Backgrounds
        region_backgrounds = []
        dpi_scale = self.config.dpi / 72.0

        for reg in regions:
            r_type = reg.get("region_type")
            bbox_dict = reg.get("bbox", {})
            rx0 = bbox_dict.get("x0", {}).get("pt", 0.0)
            ry0 = bbox_dict.get("y0", {}).get("pt", 0.0)
            rx1 = bbox_dict.get("x1", {}).get("pt", page_w)
            ry1 = bbox_dict.get("y1", {}).get("pt", page_h)

            # Check vector fills inside region
            matched_vector_fill = None
            for d in drawings:
                dbbox = d.get("bbox", (0, 0, 0, 0))
                fill_hex = d.get("fill_color_hex")
                if fill_hex and abs(dbbox[1] - ry0) <= 5.0 and abs(dbbox[3] - ry1) <= 5.0:
                    matched_vector_fill = fill_hex
                    break

            # Cross-check via raster OpenCV sampling
            px_bbox = (int(rx0 * dpi_scale), int(ry0 * dpi_scale), int(rx1 * dpi_scale), int(ry1 * dpi_scale))
            raster_rgb, raster_hex, is_gradient = self.raster_extractor.sample_dominant_color(
                img_bgr, px_bbox, k=self.config.raster.color_palette_k
            )

            region_backgrounds.append({
                "region_type": r_type,
                "vector_fill_hex": matched_vector_fill or page_bg_hex,
                "raster_sampled_hex": raster_hex,
                "is_gradient_detected": is_gradient,
                "is_shaded": matched_vector_fill is not None and not is_near_white(raster_rgb),
                "confidence": 1.0 if matched_vector_fill else 0.85
            })

        # 3. Zebra striping / Alternating row fills in table
        zebra_shading = self._detect_zebra_fills(drawings, regions)

        return {
            "page_background_hex": page_bg_hex,
            "region_backgrounds": region_backgrounds,
            "zebra_row_shading": zebra_shading
        }

    def _detect_zebra_fills(
        self,
        drawings: List[Dict[str, Any]],
        regions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect recurring alternating row fill rects in the table region."""
        table_reg = next((r for r in regions if r.get("region_type") == "transaction_table"), None)
        if not table_reg:
            return {"has_zebra_striping": False, "alternate_color_hex": None}

        ty0 = table_reg["bbox"]["y0"]["pt"]
        ty1 = table_reg["bbox"]["y1"]["pt"]

        row_fills = [
            d.get("fill_color_hex") for d in drawings
            if d.get("fill_color_hex") and ty0 <= d.get("bbox", (0, 0, 0, 0))[1] <= ty1
        ]

        if len(row_fills) >= 2:
            alt_color = row_fills[0]
            return {
                "has_zebra_striping": True,
                "alternate_color_hex": alt_color,
                "stripe_count": len(row_fills)
            }

        return {"has_zebra_striping": False, "alternate_color_hex": None}
