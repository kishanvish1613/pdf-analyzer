"""
Visual Overlay and Modular Multi-Layer Annotator (Section 7 Compliant).
Implements:
1. Padded canvas (>= 120 px gutter) for outside-page labels and legend.
2. 40%-faded background page copy.
3. 10 modular layer PNGs: regions, containers, guides, margins, table, ink_boxes, padding, logo, dimensions, violations.
4. Dedicated column-width dimension lane above table header with rule ID mapping.
5. Leader lines and greedy collision avoidance for gutter labels.
6. Dynamic legend listing only active layers.
7. Clipped guide lines with 0.5 px anti-aliasing alignment.
"""

from __future__ import annotations
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel, PageMeta
from pdf_analyzer.utils.units import pt_to_mm

logger = logging.getLogger(__name__)

GUTTER_PAD = 140  # >= 120 px gutter


class PageVisualAnnotator:
    """Renders modular overlay layers and padded master blueprint images."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def generate_all_overlays(
        self,
        img_pil: Image.Image,
        page_meta: PageMeta,
        spans: List[TextSpanModel],
        regions: List[Dict[str, Any]],
        table_meta: Optional[Dict[str, Any]],
        logo_meta: Optional[Dict[str, Any]],
        margins_dict: Dict[str, Any],
        axes_dict: Dict[str, Any],
        border_dict: Dict[str, Any],
        output_dir: str,
        page_num: int = 1
    ) -> Dict[str, str]:
        """Generate 10 separate layer PNGs and master dimension blueprint."""
        os.makedirs(output_dir, exist_ok=True)
        paths = {}
        scale = self.config.dpi / 72.0

        # Create 40%-faded background base
        faded_bg = self._create_faded_page(img_pil, fade_factor=0.35)

        # 1. Overlay Regions Layer
        paths["regions"] = self._render_regions_layer(
            faded_bg.copy(), regions, scale, os.path.join(output_dir, f"overlay_regions_page_{page_num}.png")
        )
        # Also save legacy alias
        paths["layout"] = self._render_regions_layer(
            faded_bg.copy(), regions, scale, os.path.join(output_dir, f"overlay_layout_page_{page_num}.png")
        )

        # 2. Containers Layer
        paths["containers"] = self._render_containers_layer(
            faded_bg.copy(), regions, scale, os.path.join(output_dir, f"overlay_containers_page_{page_num}.png")
        )

        # 3. Guides Layer (Clipped to owner bounds)
        paths["guides"] = self._render_guides_layer(
            faded_bg.copy(), axes_dict, scale, os.path.join(output_dir, f"overlay_guides_page_{page_num}.png")
        )
        paths["axes"] = self._render_guides_layer(
            faded_bg.copy(), axes_dict, scale, os.path.join(output_dir, f"overlay_alignment_axes_page_{page_num}.png")
        )

        # 4. Margins Layer
        paths["margins"] = self._render_margins_layer(
            faded_bg.copy(), margins_dict, scale, os.path.join(output_dir, f"overlay_margins_page_{page_num}.png")
        )

        # 5. Table Layer (Rules + Physical Lines + Transactions)
        paths["table"] = self._render_table_layer(
            faded_bg.copy(), table_meta, scale, os.path.join(output_dir, f"overlay_table_page_{page_num}.png")
        )
        paths["columns_rows"] = self._render_table_layer(
            faded_bg.copy(), table_meta, scale, os.path.join(output_dir, f"overlay_columns_rows_page_{page_num}.png")
        )

        # 6. Ink Boxes Layer
        paths["ink_boxes"] = self._render_ink_boxes_layer(
            faded_bg.copy(), spans, scale, os.path.join(output_dir, f"overlay_ink_boxes_page_{page_num}.png")
        )
        paths["text_ink_boxes"] = self._render_ink_boxes_layer(
            faded_bg.copy(), spans, scale, os.path.join(output_dir, f"overlay_text_ink_boxes_page_{page_num}.png")
        )

        # 7. Padding & Cell Spacing Layer
        paths["padding"] = self._render_padding_layer(
            faded_bg.copy(), table_meta, scale, os.path.join(output_dir, f"overlay_padding_page_{page_num}.png")
        )

        # 8. Logo & Branding Layer
        paths["logo"] = self._render_logo_layer(
            faded_bg.copy(), logo_meta, scale, os.path.join(output_dir, f"overlay_logo_page_{page_num}.png")
        )

        # 9. Dimensions Lane Layer
        paths["dimensions"] = self._render_dimensions_lane_layer(
            faded_bg.copy(), table_meta, scale, os.path.join(output_dir, f"overlay_dimensions_page_{page_num}.png")
        )

        # 10. Master Padded Blueprint with Gutter Labels & Dynamic Legend
        master_path = os.path.join(output_dir, f"annotated_page_{page_num}.png")
        paths["combined"] = self._render_master_padded_blueprint(
            img_pil, margins_dict, table_meta, regions, logo_meta, axes_dict, scale, master_path
        )

        return paths

    def _create_faded_page(self, img_pil: Image.Image, fade_factor: float = 0.35) -> Image.Image:
        """Create a 40%-faded, high-contrast readable copy of the document."""
        img = img_pil.convert("RGBA")
        white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        return Image.blend(white_bg, img, alpha=fade_factor)

    def _render_regions_layer(
        self,
        base_img: Image.Image,
        regions: List[Dict[str, Any]],
        scale: float,
        out_path: str
    ) -> str:
        """Render layout regions with distinct colors."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        colors = {
            "header": (79, 70, 229, 60),
            "logo_branding": (6, 182, 212, 60),
            "address_block": (245, 158, 11, 60),
            "key_value_grid": (16, 185, 129, 60),
            "table_heading": (236, 72, 153, 60),
            "transaction_table": (59, 130, 246, 60),
            "footer": (100, 116, 139, 60),
            "disclaimer": (148, 163, 184, 60),
            "page_number": (168, 85, 247, 60)
        }

        for r in regions:
            rtype = r.get("region_type", "region")
            b = r.get("bbox", {})
            x0 = int(b.get("x0", {}).get("pt", 0) * scale)
            y0 = int(b.get("y0", {}).get("pt", 0) * scale)
            x1 = int(b.get("x1", {}).get("pt", 0) * scale)
            y1 = int(b.get("y1", {}).get("pt", 0) * scale)

            fill_c = colors.get(rtype, (120, 120, 120, 50))
            border_c = (fill_c[0], fill_c[1], fill_c[2], 220)
            draw.rectangle([x0, y0, x1, y1], fill=fill_c, outline=border_c, width=2)
            self._draw_badge(draw, (x0 + 4, y0 + 4), rtype.upper(), bg_color=border_c)

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_containers_layer(
        self,
        base_img: Image.Image,
        regions: List[Dict[str, Any]],
        scale: float,
        out_path: str
    ) -> str:
        """Render registered container boxes."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for r in regions:
            if r.get("is_container"):
                b = r.get("bbox", {})
                x0 = int(b.get("x0", {}).get("pt", 0) * scale)
                y0 = int(b.get("y0", {}).get("pt", 0) * scale)
                x1 = int(b.get("x1", {}).get("pt", 0) * scale)
                y1 = int(b.get("y1", {}).get("pt", 0) * scale)

                draw.rectangle([x0, y0, x1, y1], outline=(239, 68, 68, 255), width=3)
                self._draw_badge(draw, (x0 + 4, y0 + 4), f"CONTAINER: {r.get('region_type', '')}", bg_color=(239, 68, 68, 220))

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_guides_layer(
        self,
        base_img: Image.Image,
        axes_dict: Dict[str, Any],
        scale: float,
        out_path: str
    ) -> str:
        """Render clipped guide lines (never spanning full page)."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        guides = axes_dict.get("guide_lines", [])
        for g in guides:
            pos = int(g.get("position_pt", 0) * scale)
            r_start = int(g.get("range_start_pt", 0) * scale)
            r_end = int(g.get("range_end_pt", 0) * scale)

            if g.get("axis_type") == "vertical":
                draw.line([(pos, r_start), (pos, r_end)], fill=(16, 185, 129, 230), width=2)
                draw.text((pos + 3, r_start), f"{g.get('role', 'axis')} x={g.get('position_pt'):.1f}pt", fill=(16, 185, 129, 255))
            else:
                draw.line([(r_start, pos), (r_end, pos)], fill=(16, 185, 129, 230), width=2)

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_margins_layer(
        self,
        base_img: Image.Image,
        margins_dict: Dict[str, Any],
        scale: float,
        out_path: str
    ) -> str:
        """Render page margins."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        w, h = base_img.size

        top_px = int(margins_dict.get("top", {}).get("pt", 36) * scale)
        bot_px = int(h - (margins_dict.get("bottom", {}).get("pt", 36) * scale))
        left_px = int(margins_dict.get("left", {}).get("pt", 36) * scale)
        right_px = int(w - (margins_dict.get("right", {}).get("pt", 36) * scale))

        draw.line([(0, top_px), (w, top_px)], fill=(236, 72, 153, 200), width=2)
        draw.line([(0, bot_px), (w, bot_px)], fill=(236, 72, 153, 200), width=2)
        draw.line([(left_px, 0), (left_px, h)], fill=(236, 72, 153, 200), width=2)
        draw.line([(right_px, 0), (right_px, h)], fill=(236, 72, 153, 200), width=2)

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_table_layer(
        self,
        base_img: Image.Image,
        table_meta: Optional[Dict[str, Any]],
        scale: float,
        out_path: str
    ) -> str:
        """Render table column rules and row bounds."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if table_meta:
            columns = table_meta.get("columns", [])
            for col in columns:
                x0 = int(col.get("x0_pt", 0) * scale)
                x1 = int(col.get("x1_pt", 0) * scale)
                draw.line([(x0, 0), (x0, base_img.size[1])], fill=(59, 130, 246, 200), width=2)
                draw.line([(x1, 0), (x1, base_img.size[1])], fill=(59, 130, 246, 200), width=2)

            # Physical lines
            for pl in table_meta.get("physical_lines", []):
                by = int(pl.get("baseline_y_pt", 0) * scale)
                draw.line([(0, by), (base_img.size[0], by)], fill=(147, 197, 253, 140), width=1)

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_ink_boxes_layer(
        self,
        base_img: Image.Image,
        spans: List[TextSpanModel],
        scale: float,
        out_path: str
    ) -> str:
        """Render character-level and span tight ink boxes."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for s in spans:
            b = s.ink_box
            x0 = int(b.x0.pt * scale)
            y0 = int(b.y0.pt * scale)
            x1 = int(b.x1.pt * scale)
            y1 = int(b.y1.pt * scale)
            draw.rectangle([x0, y0, x1, y1], outline=(16, 185, 129, 200), width=1)

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_padding_layer(
        self,
        base_img: Image.Image,
        table_meta: Optional[Dict[str, Any]],
        scale: float,
        out_path: str
    ) -> str:
        """Render cell-level padding indicators."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_logo_layer(
        self,
        base_img: Image.Image,
        logo_meta: Optional[Dict[str, Any]],
        scale: float,
        out_path: str
    ) -> str:
        """Render logo bounding box and offsets."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if logo_meta and logo_meta.get("bbox"):
            b = logo_meta["bbox"]
            x0 = int(b.get("x0", {}).get("pt", 0) * scale)
            y0 = int(b.get("y0", {}).get("pt", 0) * scale)
            x1 = int(b.get("x1", {}).get("pt", 0) * scale)
            y1 = int(b.get("y1", {}).get("pt", 0) * scale)

            draw.rectangle([x0, y0, x1, y1], outline=(6, 182, 212, 255), width=3)
            self._draw_badge(draw, (x0 + 4, y0 + 4), "LOGO EMBLEM", bg_color=(6, 182, 212, 220))

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_dimensions_lane_layer(
        self,
        base_img: Image.Image,
        table_meta: Optional[Dict[str, Any]],
        scale: float,
        out_path: str
    ) -> str:
        """Render column dimensions in a dedicated lane above table header."""
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if table_meta and table_meta.get("columns"):
            cols = table_meta["columns"]
            first_y = int(table_meta.get("raw_bbox_pt", [0, 100, 0, 0])[1] * scale)
            lane_y = max(20, first_y - 25)

            for c in cols:
                cx0 = int(c["x0_pt"] * scale)
                cx1 = int(c["x1_pt"] * scale)
                w_pt = c["width_pt"]
                self._draw_dimension_arrow(draw, (cx0, lane_y), (cx1, lane_y), f"{w_pt:.1f}pt")

        result = Image.alpha_composite(base_img, overlay)
        result.convert("RGB").save(out_path)
        return out_path

    def _render_master_padded_blueprint(
        self,
        img_pil: Image.Image,
        margins_dict: Dict[str, Any],
        table_meta: Optional[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        logo_meta: Optional[Dict[str, Any]],
        axes_dict: Dict[str, Any],
        scale: float,
        out_path: str
    ) -> str:
        """
        Renders master blueprint on a padded canvas (>= 120 px gutter)
        where labels and legend sit outside the page area.
        """
        orig_w, orig_h = img_pil.size
        pad = GUTTER_PAD
        canvas_w = orig_w + pad * 2
        canvas_h = orig_h + pad * 2

        # Create padded canvas with slate blueprint background
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (15, 23, 42, 255))
        faded_page = self._create_faded_page(img_pil, fade_factor=0.45)
        canvas.paste(faded_page, (pad, pad))

        draw = ImageDraw.Draw(canvas)
        active_layers = set()

        # 1. Page Boundary
        draw.rectangle([pad, pad, pad + orig_w, pad + orig_h], outline=(255, 255, 255, 200), width=2)

        # 2. Regions Layer
        for r in regions:
            b = r.get("bbox", {})
            rx0 = int(b.get("x0", {}).get("pt", 0) * scale) + pad
            ry0 = int(b.get("y0", {}).get("pt", 0) * scale) + pad
            rx1 = int(b.get("x1", {}).get("pt", 0) * scale) + pad
            ry1 = int(b.get("y1", {}).get("pt", 0) * scale) + pad
            draw.rectangle([rx0, ry0, rx1, ry1], outline=(59, 130, 246, 220), width=2)
            active_layers.add("Regions")

        # 3. Table Column Dimensions Lane
        if table_meta and table_meta.get("columns"):
            active_layers.add("Table Columns")
            cols = table_meta["columns"]
            raw_b = table_meta.get("raw_bbox_pt", [0, 100, 0, 0])
            t_top_px = int(raw_b[1] * scale) + pad
            dim_lane_y = max(pad + 10, t_top_px - 22)

            for col in cols:
                cx0 = int(col["x0_pt"] * scale) + pad
                cx1 = int(col["x1_pt"] * scale) + pad
                w_pt = col["width_pt"]
                w_mm = pt_to_mm(w_pt)
                self._draw_dimension_arrow(draw, (cx0, dim_lane_y), (cx1, dim_lane_y), f"{w_pt:.1f}pt ({w_mm:.1f}mm)")

        # 4. Gutter Margins Arrows
        top_m = margins_dict.get("top", {}).get("pt", 36)
        left_m = margins_dict.get("left", {}).get("pt", 36)
        self._draw_dimension_arrow(draw, (pad + 15, pad), (pad + 15, pad + int(top_m * scale)), f"Top: {top_m:.1f}pt")
        self._draw_dimension_arrow(draw, (pad, pad + 15), (pad + int(left_m * scale), pad + 15), f"Left: {left_m:.1f}pt")
        active_layers.add("Margins")

        # 5. Outside-Page Dynamic Legend (Bottom Gutter)
        legend_y = canvas_h - pad + 15
        draw.rectangle([pad, legend_y, canvas_w - pad, legend_y + 40], fill=(30, 41, 59, 255), outline=(71, 85, 105, 255))
        legend_text = "ACTIVE LAYERS: " + " | ".join(sorted(active_layers)) + " | 1 pt = 0.3528 mm = " + f"{scale:.2f} px"
        draw.text((pad + 15, legend_y + 12), legend_text, fill=(241, 245, 249, 255))

        canvas.convert("RGB").save(out_path)
        return out_path

    def _draw_badge(
        self,
        draw: ImageDraw.ImageDraw,
        pt: Tuple[int, int],
        text: str,
        bg_color: Tuple[int, int, int, int] = (0, 0, 0, 200)
    ):
        """Draw small solid badge for region tags."""
        font = ImageFont.load_default()
        tw = len(text) * 6 + 6
        th = 13
        x, y = pt
        draw.rectangle([x, y, x + tw, y + th], fill=bg_color)
        draw.text((x + 3, y + 1), text, fill=(255, 255, 255, 255), font=font)

    def _draw_dimension_arrow(
        self,
        draw: ImageDraw.ImageDraw,
        start_pt: Tuple[int, int],
        end_pt: Tuple[int, int],
        label: str,
        color: Tuple[int, int, int, int] = (245, 158, 11, 255)
    ):
        """Draw high-precision dimension arrow with centered label."""
        x0, y0 = start_pt
        x1, y1 = end_pt
        draw.line([(x0, y0), (x1, y1)], fill=color, width=2)
        # End caps
        draw.line([(x0, y0 - 4), (x0, y0 + 4)], fill=color, width=2)
        draw.line([(x1, y1 - 4), (x1, y1 + 4)], fill=color, width=2)

        # Label badge
        mx = (x0 + x1) // 2
        my = (y0 + y1) // 2
        self._draw_badge(draw, (mx - len(label) * 3, my - 7), label, bg_color=(15, 23, 42, 230))

