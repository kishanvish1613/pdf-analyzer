"""Module J: Logo positioning, dimensions, alignment offsets, and image extraction analysis.

Calculates effective DPI, distances to nearby captions, and offsets to primary alignment axes
(margins, header baseline, and table edge).
"""

import os
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel
from pdf_analyzer.utils.units import create_bbox_from_pt, create_multi_unit_value


class LogoAnalyzer:
    """Analyzes and extracts bank/brand logos with alignment offsets and caption detection."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_logo(
        self,
        images: List[Dict[str, Any]],
        drawings: List[Dict[str, Any]],
        spans: List[TextSpanModel],
        img_pil: Image.Image,
        output_dir: str,
        page_w: float,
        page_h: float,
        table_bbox_pt: Optional[Tuple[float, float, float, float]] = None
    ) -> Optional[Dict[str, Any]]:
        """Detect logo, compute effective DPI, caption proximity, and offsets to alignment axes."""
        # 1. Embedded raster image in top 25% of page
        header_images = [
            img for img in images
            if img["bbox_pt"][1] <= page_h * 0.25 and img["width_pt"] > 10.0 and img["height_pt"] > 10.0
        ]

        detected_bbox_pt: Optional[Tuple[float, float, float, float]] = None
        logo_type = "raster_image"
        logo_metadata = {}
        eff_dpi = 300.0

        if header_images:
            top_img = sorted(header_images, key=lambda img: img["width_pt"] * img["height_pt"], reverse=True)[0]
            detected_bbox_pt = top_img["bbox_pt"]
            disp_w = top_img["width_pt"]
            disp_h = top_img["height_pt"]
            eff_dpi = (top_img["orig_pixel_width"] / (disp_w / 72.0)) if disp_w > 0 else 300.0

            logo_metadata = {
                "xref": top_img["xref"],
                "original_pixel_size": [top_img["orig_pixel_width"], top_img["orig_pixel_height"]],
                "effective_dpi": round(eff_dpi, 2),
                "colorspace": top_img["colorspace"],
                "format": top_img["format"]
            }
            os.makedirs(output_dir, exist_ok=True)
            logo_save_path = os.path.join(output_dir, "extracted_logo.png")
            try:
                top_img["pixmap"].save(logo_save_path)
            except Exception:
                pass

        else:
            # 2. Vector logo fallback: Top cluster of vector paths/curves
            header_vector_paths = [
                d for d in drawings
                if d.get("bbox", (0, 0, 0, 0))[1] <= page_h * 0.20
                and d.get("width_pt", 0) < 180.0
                and d.get("height_pt", 0) < 100.0
                and ("c" in d.get("item_types", []) or len(d.get("items", [])) >= 2)
            ]
            if header_vector_paths:
                vx0 = min(d["bbox"][0] for d in header_vector_paths)
                vy0 = min(d["bbox"][1] for d in header_vector_paths)
                vx1 = max(d["bbox"][2] for d in header_vector_paths)
                vy1 = max(d["bbox"][3] for d in header_vector_paths)
                if (vx1 - vx0) >= 10.0 and (vy1 - vy0) >= 10.0:
                    detected_bbox_pt = (vx0, vy0, vx1, vy1)
                    logo_type = "vector_drawn_emblem"
                    logo_metadata = {
                        "vector_path_count": len(header_vector_paths),
                        "effective_dpi": "Infinite (Vector PDF Paths)",
                        "format": "vector_paths"
                    }
                    os.makedirs(output_dir, exist_ok=True)
                    logo_save_path = os.path.join(output_dir, "extracted_logo.png")
                    dpi_scale = self.config.dpi / 72.0
                    px_box = (int(vx0 * dpi_scale), int(vy0 * dpi_scale), int(vx1 * dpi_scale), int(vy1 * dpi_scale))
                    try:
                        img_pil.crop(px_box).save(logo_save_path)
                    except Exception:
                        pass

        if not detected_bbox_pt:
            return None

        lx0, ly0, lx1, ly1 = detected_bbox_pt
        lw = lx1 - lx0
        lh = ly1 - ly0
        aspect_ratio = round(lw / lh, 3) if lh > 0 else 1.0

        # Placement classification
        center_x = (lx0 + lx1) / 2.0
        if center_x < page_w * 0.35:
            placement = "top-left"
        elif center_x > page_w * 0.65:
            placement = "top-right"
        else:
            placement = "top-center"

        # Caption text near logo (< 30pt distance)
        top_spans = [s for s in spans if s.ink_box.y0.pt <= page_h * 0.3]
        caption_spans = [
            s for s in top_spans
            if (s.ink_box.y0.pt >= ly1 and s.ink_box.y0.pt - ly1 < 25.0 and abs(s.ink_box.x0.pt - lx0) < 40.0)
            or (s.ink_box.x0.pt >= lx1 and s.ink_box.x0.pt - lx1 < 25.0 and abs(s.ink_box.y0.pt - ly0) < 25.0)
        ]
        nearest_caption = caption_spans[0].text if caption_spans else None
        caption_dist = (caption_spans[0].ink_box.y0.pt - ly1) if caption_spans else None

        # Alignment Offsets to Primary Document Axes
        header_spans = [s for s in top_spans if s.font_size_pt >= 12.0]
        header_baseline = header_spans[0].baseline_y.pt if header_spans else ly1
        table_right_x = table_bbox_pt[2] if table_bbox_pt else page_w - 36.0

        offset_to_header_baseline = ly1 - header_baseline
        offset_to_table_right_edge = table_right_x - lx1

        return {
            "type": logo_type,
            "placement": placement,
            "bbox": create_bbox_from_pt(lx0, ly0, lx1, ly1, page_w, page_h, self.config.dpi).to_dict(),
            "aspect_ratio": aspect_ratio,
            "effective_dpi": eff_dpi if isinstance(eff_dpi, float) else 600.0,
            "crop_clip_box_pt": [round(lx0, 3), round(ly0, 3), round(lx1, 3), round(ly1, 3)],
            "dist_from_left_margin_pt": round(lx0, 3),
            "dist_from_top_margin_pt": round(ly0, 3),
            "dist_from_right_margin_pt": round(page_w - lx1, 3),
            "nearest_caption_text": nearest_caption,
            "caption_distance_pt": round(caption_dist, 3) if caption_dist else None,
            "alignment_offsets": {
                "offset_to_header_text_baseline_pt": round(offset_to_header_baseline, 3),
                "offset_to_table_right_edge_pt": round(offset_to_table_right_edge, 3)
            },
            "saved_image_path": "extracted_logo.png",
            "metadata": logo_metadata
        }

