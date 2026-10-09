"""PyMuPDF extractor with rawdict char-level bounds, font box vs ink box calculation."""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Tuple, Optional
import pymupdf
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel, PageMeta, FontMetricsModel
from pdf_analyzer.utils.units import CoordinateTransform, create_bbox_from_pt, create_multi_unit_value
from pdf_analyzer.utils.color import int_or_float_to_rgb, rgb_to_hex
from pdf_analyzer.utils.font_parser import parse_font_properties, clean_font_name
from pdf_analyzer.utils.font_metrics import FontMetricsExtractor
from pdf_analyzer.extractors.subpixel_raster import SubpixelRasterEngine

logger = logging.getLogger(__name__)


class MuPDFExtractor:
    """Extracts raw primitives, character baselines, font boxes, and tight ink boxes."""

    def __init__(self, doc: pymupdf.Document, config: AnalyzerConfig):
        self.doc = doc
        self.config = config
        self.font_extractor = FontMetricsExtractor(doc)
        self.subpixel_engine = SubpixelRasterEngine(config.dpi)

    def get_coordinate_transform(self, page_index: int) -> CoordinateTransform:
        """Create authoritative CoordinateTransform for page."""
        page = self.doc[page_index]
        cropbox = list(page.cropbox)
        mediabox = list(page.mediabox)
        rotation = page.rotation
        return CoordinateTransform(cropbox, mediabox, rotation, self.config.dpi)

    def get_page_meta(self, page_index: int) -> PageMeta:
        """Extract metadata, orientation, boxes, and rotation for a page."""
        transform = self.get_coordinate_transform(page_index)
        page = self.doc[page_index]
        w_pt = transform.page_width
        h_pt = transform.page_height
        orientation = "portrait" if h_pt >= w_pt else "landscape"

        return PageMeta(
            page_number=page_index + 1,
            total_pages=len(self.doc),
            width=transform.create_multi_unit(w_pt, is_vertical=False, source="content_stream", confidence=1.0),
            height=transform.create_multi_unit(h_pt, is_vertical=True, source="content_stream", confidence=1.0),
            orientation=orientation,
            rotation_deg=page.rotation,
            cropbox=list(page.cropbox),
            mediabox=list(page.mediabox),
            dpi=self.config.dpi
        )

    def extract_text_spans(
        self,
        page_index: int,
        img_bgr: Optional[np.ndarray] = None
    ) -> List[TextSpanModel]:
        """Extract all text spans with BOTH Font Box and Ink Box, character bboxes, and baselines."""
        page = self.doc[page_index]
        transform = self.get_coordinate_transform(page_index)
        page_w = transform.page_width
        page_h = transform.page_height

        # Use rawdict to access character-level glyph coordinates
        raw_text_page = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        spans: List[TextSpanModel] = []

        for block in raw_text_page.get("blocks", []):
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        chars = span.get("chars", [])
                        text = "".join(c.get("c", "") for c in chars) if chars else span.get("text", "")
                        if not text or text.strip() == "":
                            continue

                        span_bbox = span.get("bbox", (0, 0, 0, 0))
                        origin = span.get("origin", (span_bbox[0], span_bbox[3]))
                        
                        # Transform coordinates through authoritative Transform
                        tl_origin_x, tl_origin_y = transform.native_to_top_left_point(origin[0], origin[1])
                        
                        font_name = span.get("font", "Unknown")
                        flags = span.get("flags", 0)
                        size = float(span.get("size", 10.0))
                        raw_color = span.get("color", 0)
                        opacity = float(span.get("opacity", 1.0))

                        clean_name, family, is_bold, is_italic, is_mono, is_serif, weight = parse_font_properties(
                            font_name, flags
                        )
                        rgb = int_or_float_to_rgb(raw_color)
                        hex_color = rgb_to_hex(rgb)

                        # Get Font Metrics
                        metrics = self.font_extractor.get_font_metrics(font_name, page_index)

                        # 1. Compute Font Box: (ascent/descent scaled by font size)
                        scale_em = size / max(1.0, float(metrics.units_per_em))
                        font_ascent_pt = metrics.ascender * scale_em
                        font_descent_pt = metrics.descender * scale_em  # usually negative

                        # Span width
                        span_w = abs(span_bbox[2] - span_bbox[0])
                        font_box_y0 = tl_origin_y - font_ascent_pt
                        font_box_y1 = tl_origin_y - font_descent_pt
                        font_box_x0 = tl_origin_x
                        font_box_x1 = tl_origin_x + span_w

                        font_box = transform.create_bbox(
                            font_box_x0, font_box_y0, font_box_x1, font_box_y1,
                            source="content_stream", confidence=1.0
                        )

                        # 2. Compute Tight Ink Box: (tight union of character glyph bounds)
                        char_boxes = []
                        if chars:
                            char_x0s, char_y0s, char_x1s, char_y1s = [], [], [], []
                            for ch in chars:
                                cb = ch.get("bbox", (0, 0, 0, 0))
                                tcb_x0, tcb_y0, tcb_x1, tcb_y1 = transform.native_to_top_left_bbox(
                                    cb[0], cb[1], cb[2], cb[3]
                                )
                                char_boxes.append((ch.get("c", ""), (tcb_x0, tcb_y0, tcb_x1, tcb_y1)))
                                char_x0s.append(tcb_x0)
                                char_y0s.append(tcb_y0)
                                char_x1s.append(tcb_x1)
                                char_y1s.append(tcb_y1)

                            ink_x0 = min(char_x0s)
                            ink_y0 = min(char_y0s)
                            ink_x1 = max(char_x1s)
                            ink_y1 = max(char_y1s)
                        else:
                            ink_x0, ink_y0, ink_x1, ink_y1 = transform.native_to_top_left_bbox(
                                span_bbox[0], span_bbox[1], span_bbox[2], span_bbox[3]
                            )

                        ink_box = transform.create_bbox(
                            ink_x0, ink_y0, ink_x1, ink_y1,
                            source="pymupdf", confidence=1.0
                        )

                        # 3. Anti-Aliasing Corrected Color
                        if img_bgr is not None:
                            _, aa_hex = self.subpixel_engine.extract_anti_aliased_color(
                                img_bgr, (ink_x0, ink_y0, ink_x1, ink_y1), percentile=20.0
                            )
                        else:
                            aa_hex = hex_color

                        baseline_mu = transform.create_multi_unit(
                            tl_origin_y, is_vertical=True, source="pymupdf", confidence=1.0
                        )

                        spans.append(TextSpanModel(
                            text=text,
                            ink_box=ink_box,
                            font_box=font_box,
                            origin_point=(tl_origin_x, tl_origin_y),
                            baseline_y=baseline_mu,
                            font_name=clean_name,
                            clean_font_family=family,
                            font_size_pt=size,
                            nominal_font_size_pt=size,
                            is_bold=is_bold,
                            is_italic=is_italic,
                            is_monospace=is_mono,
                            is_serif=is_serif,
                            inferred_weight=weight,
                            color_rgb=rgb,
                            color_hex=hex_color,
                            anti_aliasing_corrected_hex=aa_hex,
                            opacity=opacity,
                            page_number=page_index + 1,
                            char_boxes=char_boxes,
                            font_metrics=metrics
                        ))

        return spans

    def extract_drawings(
        self,
        page_index: int,
        img_bgr: Optional[np.ndarray] = None
    ) -> List[Dict[str, Any]]:
        """Extract vector paths, rects, and compute sub-pixel FWHM stroke thickness."""
        page = self.doc[page_index]
        transform = self.get_coordinate_transform(page_index)
        raw_drawings = page.get_drawings()
        drawings = []

        for d in raw_drawings:
            rect = d.get("rect", pymupdf.Rect(0, 0, 0, 0))
            tl_x0, tl_y0, tl_x1, tl_y1 = transform.native_to_top_left_bbox(
                rect.x0, rect.y0, rect.x1, rect.y1
            )
            color = int_or_float_to_rgb(d.get("color"))
            fill = int_or_float_to_rgb(d.get("fill")) if d.get("fill") is not None else None
            raw_w = d.get("width")
            width = float(raw_w) if raw_w is not None else 0.0
            dashes = d.get("dashes", None)
            line_cap = d.get("lineCap", 0)
            line_join = d.get("lineJoin", 0)
            opacity_raw = d.get("opacity")
            opacity = float(opacity_raw) if opacity_raw is not None else 1.0
            fill_opacity_raw = d.get("fill_opacity")
            fill_opacity = float(fill_opacity_raw) if fill_opacity_raw is not None else 1.0

            items = d.get("items", [])
            item_types = [it[0] for it in items]

            # Sub-pixel FWHM measurement cross-check if line and image available
            fwhm_info = {}
            if img_bgr is not None and width > 0:
                fwhm_info = self.subpixel_engine.measure_line_subpixel_fwhm(
                    img_bgr, (tl_x0, tl_y0), (tl_x1, tl_y1), vector_stroke_pt=width
                )

            drawings.append({
                "bbox": (tl_x0, tl_y0, tl_x1, tl_y1),
                "width_pt": abs(tl_x1 - tl_x0),
                "height_pt": abs(tl_y1 - tl_y0),
                "stroke_color_rgb": color,
                "stroke_color_hex": rgb_to_hex(color) if d.get("color") is not None else None,
                "fill_color_rgb": fill,
                "fill_color_hex": rgb_to_hex(fill) if fill is not None else None,
                "stroke_width_pt": width,
                "subpixel_fwhm_pt": fwhm_info.get("fwhm_pt", width),
                "subpixel_deviation_pt": fwhm_info.get("deviation_pt", 0.0),
                "flagged_deviation": fwhm_info.get("flagged_deviation", False),
                "dashes": dashes,
                "line_cap": line_cap,
                "line_join": line_join,
                "opacity": opacity,
                "fill_opacity": fill_opacity,
                "items": items,
                "item_types": item_types
            })
        return drawings

    def extract_images(self, page_index: int) -> List[Dict[str, Any]]:
        """Extract embedded images with standardized coordinate transform."""
        page = self.doc[page_index]
        transform = self.get_coordinate_transform(page_index)
        image_list = page.get_images(full=True)
        extracted_images = []

        for img_info in image_list:
            xref = img_info[0]
            rects = page.get_image_rects(xref)
            for r in rects:
                try:
                    pix = pymupdf.Pixmap(self.doc, xref)
                    if pix.n >= 5:
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

                    tl_x0, tl_y0, tl_x1, tl_y1 = transform.native_to_top_left_bbox(
                        r.x0, r.y0, r.x1, r.y1
                    )
                    disp_w = abs(tl_x1 - tl_x0)
                    disp_h = abs(tl_y1 - tl_y0)
                    orig_w = pix.width
                    orig_h = pix.height
                    
                    eff_dpi_x = (orig_w / (disp_w / 72.0)) if disp_w > 0 else 0.0
                    eff_dpi_y = (orig_h / (disp_h / 72.0)) if disp_h > 0 else 0.0

                    extracted_images.append({
                        "xref": xref,
                        "bbox_pt": (tl_x0, tl_y0, tl_x1, tl_y1),
                        "width_pt": disp_w,
                        "height_pt": disp_h,
                        "orig_pixel_width": orig_w,
                        "orig_pixel_height": orig_h,
                        "effective_dpi": round((eff_dpi_x + eff_dpi_y) / 2.0, 1),
                        "colorspace": pix.colorspace.name if pix.colorspace else "Unknown",
                        "format": "PNG",
                        "pixmap": pix
                    })
                except Exception as e:
                    logger.warning(f"Error extracting image xref {xref}: {e}")

        return extracted_images

    def get_font_inventory(self, page_index: int) -> List[Dict[str, Any]]:
        """List all embedded fonts with standard-14 / subset / embedded flags."""
        fonts = self.doc.get_page_fonts(page_index)
        inventory = []
        for f in fonts:
            xref, ext, ftype, name, refname, encoding = f[0], f[1], f[2], f[3], f[4], f[5]
            is_subset = bool("+" in name and len(name.split("+")[0]) == 6)
            clean_name = clean_font_name(name)
            is_std14 = any(s.lower() in clean_name.lower() for s in [
                "Helvetica", "Times", "Courier", "Symbol", "ZapfDingbats"
            ])
            inventory.append({
                "font_name": clean_name,
                "raw_name": name,
                "type": ftype,
                "extension": ext,
                "is_subset": is_subset,
                "is_standard_14": is_std14,
                "is_embedded": xref > 0
            })
        return inventory
