"""Module G: Typography, font styles, weights, colors, and role inventory analysis.

Builds a comprehensive typography hierarchy (H1, H2, Table Header, Body, Metadata, Footer),
records embedded/standard-14 font status, and computes leading per style.
"""

from typing import List, Dict, Any, Tuple
from collections import Counter
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel


class TypographyAnalyzer:
    """Analyzes typographic style hierarchy, font embedding, and role assignments."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_typography(
        self,
        spans: List[TextSpanModel],
        font_inventory: List[Dict[str, Any]],
        page_h: float
    ) -> Dict[str, Any]:
        """Generate typography inventory, style groupings, and role mappings."""
        if not spans:
            return {"styles": [], "fonts": font_inventory, "role_hierarchy": {}}

        # Group spans by unique typographic fingerprint: (clean_font_family, font_size_pt, weight, color_hex)
        style_groups: Dict[Tuple[str, float, str, str], List[TextSpanModel]] = {}
        for s in spans:
            key = (s.clean_font_family, round(s.font_size_pt, 1), s.inferred_weight, s.color_hex)
            style_groups.setdefault(key, []).append(s)

        # Sort styles by prominence (font size descending, then count descending)
        sorted_style_keys = sorted(
            style_groups.keys(),
            key=lambda k: (-k[1], -len(style_groups[k]))
        )

        styles_list: List[Dict[str, Any]] = []
        role_mapping: Dict[str, Any] = {}

        # Determine dominant body style (most frequent span style)
        most_frequent_key = max(style_groups.keys(), key=lambda k: len(style_groups[k]))

        for key in sorted_style_keys:
            family, size, weight, color_hex = key
            span_list = style_groups[key]
            sample_span = span_list[0]
            count = len(span_list)

            # Assign semantic role based on font size, weight, position, and frequency
            role = self._assign_role(key, span_list, most_frequent_key, page_h)

            # Compute leading for this specific style
            leadings = []
            for i in range(len(span_list) - 1):
                dy = span_list[i + 1].baseline_y.pt - span_list[i].baseline_y.pt
                if 5.0 <= dy <= 35.0:
                    leadings.append(dy)
            style_leading = round(float(np.median(leadings)), 2) if leadings else round(size * 1.25, 2)

            style_entry = {
                "role": role,
                "clean_font_family": family,
                "font_name": sample_span.font_name,
                "font_size_pt": size,
                "inferred_weight": weight,
                "is_bold": sample_span.is_bold,
                "is_italic": sample_span.is_italic,
                "is_monospace": sample_span.is_monospace,
                "is_serif": sample_span.is_serif,
                "color_hex": color_hex,
                "color_rgb": list(sample_span.color_rgb),
                "frequency_count": count,
                "recommended_leading_pt": style_leading,
                "css_style_string": f"font-family: '{family}', sans-serif; font-size: {size}pt; font-weight: {'bold' if weight in ['bold', 'semibold'] else 'normal'}; color: {color_hex}; line-height: {style_leading}pt;"
            }
            styles_list.append(style_entry)
            role_mapping[role] = style_entry

        return {
            "styles_inventory": styles_list,
            "embedded_fonts": font_inventory,
            "role_hierarchy": role_mapping
        }

    def _assign_role(
        self,
        key: Tuple[str, float, str, str],
        span_list: List[TextSpanModel],
        body_key: Tuple[str, float, str, str],
        page_h: float
    ) -> str:
        """Heuristic semantic role classifier for document styles."""
        family, size, weight, color_hex = key
        avg_y = float(np.mean([s.bbox.y0.pt for s in span_list]))

        if avg_y > page_h * 0.88 and size <= 9.0:
            return "footer_disclaimer"
        if key == body_key:
            return "table_body_text"
        if size >= 15.0:
            return "document_title_h1"
        if size >= 11.0 and weight in ["bold", "semibold"]:
            return "section_heading_h2"
        if weight in ["bold", "semibold"] and 8.0 <= size <= 11.0 and avg_y < page_h * 0.6:
            return "table_header_or_field_label"
        if size < body_key[1]:
            return "caption_or_small_metadata"
        return f"text_style_{int(size)}pt_{weight}"
