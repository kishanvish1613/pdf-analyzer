"""Font metrics extractor using fontTools on embedded fonts with standard-14 fallbacks."""

import io
import logging
from typing import Dict, Any, Optional
from fontTools.ttLib import TTFont
import pymupdf

from pdf_analyzer.models import FontMetricsModel
from pdf_analyzer.utils.font_parser import clean_font_name

logger = logging.getLogger(__name__)

# Standard fallback font metrics (units per 1000 em)
STANDARD_METRICS = {
    "helvetica": {"ascender": 718, "descender": -207, "cap_height": 718, "x_height": 523, "avg_width": 520, "units_per_em": 1000},
    "times": {"ascender": 683, "descender": -217, "cap_height": 662, "x_height": 450, "avg_width": 500, "units_per_em": 1000},
    "courier": {"ascender": 629, "descender": -157, "cap_height": 562, "x_height": 426, "avg_width": 600, "units_per_em": 1000},
    "default": {"ascender": 800, "descender": -200, "cap_height": 700, "x_height": 500, "avg_width": 500, "units_per_em": 1000},
}


class FontMetricsExtractor:
    """Extracts ascender, descender, cap height, x-height, unitsPerEm, and avgCharWidth."""

    def __init__(self, doc: pymupdf.Document):
        self.doc = doc
        self._font_cache: Dict[str, FontMetricsModel] = {}

    def get_font_metrics(self, font_name: str, page_index: int = 0) -> FontMetricsModel:
        """Extract exact font metrics from embedded font or fallback to typographic tables."""
        clean_name = clean_font_name(font_name)
        if clean_name in self._font_cache:
            return self._font_cache[clean_name]

        # Attempt to find font xref on page
        page_fonts = self.doc.get_page_fonts(page_index)
        embedded_buffer = None
        font_type = "Standard"
        is_embedded = False

        for f_info in page_fonts:
            xref, ext, ftype, name = f_info[0], f_info[1], f_info[2], f_info[3]
            if clean_font_name(name).lower() == clean_name.lower():
                font_type = ftype
                if xref > 0:
                    try:
                        # Extract font buffer
                        embedded_buffer = self.doc.extract_font(xref)[3]
                        if embedded_buffer:
                            is_embedded = True
                    except Exception as e:
                        logger.debug(f"Could not extract font buffer for xref {xref}: {e}")
                break

        # If embedded buffer is present, inspect with fontTools
        if embedded_buffer:
            try:
                tt = TTFont(io.BytesIO(embedded_buffer))
                upem = tt["head"].unitsPerEm if "head" in tt else 1000
                hhea = tt.get("hhea")
                os2 = tt.get("OS/2")

                ascender = float(os2.sTypoAscender if os2 else (hhea.ascent if hhea else 800))
                descender = float(os2.sTypoDescender if os2 else (hhea.descent if hhea else -200))
                cap_height = float(os2.sCapHeight if os2 and hasattr(os2, "sCapHeight") and os2.sCapHeight > 0 else ascender * 0.9)
                x_height = float(os2.sxHeight if os2 and hasattr(os2, "sxHeight") and os2.sxHeight > 0 else ascender * 0.65)
                avg_w = float(os2.xAvgCharWidth if os2 and hasattr(os2, "xAvgCharWidth") and os2.xAvgCharWidth > 0 else 500)

                model = FontMetricsModel(
                    font_name=clean_name,
                    clean_family=clean_name.split("-")[0],
                    units_per_em=upem,
                    ascender=ascender,
                    descender=descender,
                    cap_height=cap_height,
                    x_height=x_height,
                    avg_char_width=avg_w,
                    is_embedded=True,
                    font_type=font_type
                )
                self._font_cache[clean_name] = model
                return model
            except Exception as e:
                logger.debug(f"fontTools parsing fallback for {clean_name}: {e}")

        # Fallback to standard font metric tables
        lower = clean_name.lower()
        if "times" in lower or "roman" in lower:
            ref = STANDARD_METRICS["times"]
        elif "courier" in lower or "mono" in lower:
            ref = STANDARD_METRICS["courier"]
        elif "helvetica" in lower or "arial" in lower or "sans" in lower:
            ref = STANDARD_METRICS["helvetica"]
        else:
            ref = STANDARD_METRICS["default"]

        model = FontMetricsModel(
            font_name=clean_name,
            clean_family=clean_name.split("-")[0],
            units_per_em=ref["units_per_em"],
            ascender=float(ref["ascender"]),
            descender=float(ref["descender"]),
            cap_height=float(ref["cap_height"]),
            x_height=float(ref["x_height"]),
            avg_char_width=float(ref["avg_width"]),
            is_embedded=is_embedded,
            font_type=font_type
        )
        self._font_cache[clean_name] = model
        return model

