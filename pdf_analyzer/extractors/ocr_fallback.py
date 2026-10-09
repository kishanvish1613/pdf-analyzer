"""OCR fallback extractor for scanned or image-only PDFs."""

import logging
from typing import List, Tuple, Optional
from PIL import Image
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel
from pdf_analyzer.utils.units import create_bbox_from_pt, create_multi_unit_value

logger = logging.getLogger(__name__)


class OCRFallbackExtractor:
    """Handles scanned/image-only PDFs via OCR fallback when vector text is absent."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def is_scanned_page(self, spans: List[TextSpanModel]) -> bool:
        """Determine if a page lacks searchable vector text."""
        total_chars = sum(len(s.text.strip()) for s in spans)
        return total_chars < self.config.raster.ocr_min_char_count

    def extract_ocr_spans(
        self,
        img_pil: Image.Image,
        page_width_pt: float,
        page_height_pt: float,
        page_number: int
    ) -> List[TextSpanModel]:
        """Run OCR on the rendered image and return synthetic text spans with reduced confidence."""
        ocr_spans: List[TextSpanModel] = []
        try:
            import pytesseract
            # Get word-level bounding boxes
            data = pytesseract.image_to_data(img_pil, output_type=pytesseract.Output.DICT)
            scale = 72.0 / self.config.dpi

            n_boxes = len(data["text"])
            for i in range(n_boxes):
                text = data["text"][i].strip()
                if not text:
                    continue
                conf = float(data["conf"][i])
                if conf < 30.0:
                    continue

                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                # Convert px to pt
                x0_pt = x * scale
                y0_pt = y * scale
                x1_pt = (x + w) * scale
                y1_pt = (y + h) * scale

                bbox = create_bbox_from_pt(
                    x0_pt, y0_pt, x1_pt, y1_pt,
                    page_width_pt, page_height_pt, self.config.dpi,
                    source="raster", confidence=max(0.3, conf / 100.0)
                )
                baseline_mu = create_multi_unit_value(
                    y1_pt - (h * scale * 0.2), page_height_pt, self.config.dpi,
                    source="raster", confidence=0.7
                )

                ocr_spans.append(TextSpanModel(
                    text=text,
                    bbox=bbox,
                    baseline_y=baseline_mu,
                    font_name="OCR-Inferred",
                    clean_font_family="SansSerif",
                    font_size_pt=round(h * scale * 0.8, 1),
                    is_bold=False,
                    is_italic=False,
                    is_monospace=False,
                    is_serif=False,
                    inferred_weight="regular",
                    color_rgb=(0, 0, 0),
                    color_hex="#000000",
                    opacity=1.0,
                    page_number=page_number
                ))
        except Exception as e:
            logger.warning(f"OCR fallback failed or pytesseract not available: {e}")

        return ocr_spans
