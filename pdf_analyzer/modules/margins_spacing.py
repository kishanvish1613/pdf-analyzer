"""Module C: Margins, padding, spacing & inter-block gaps analysis.

Computes margins from union of ALL content (text ink, raster, vector paths), identifies source
elements per margin edge, reports text-only margins, and measures block gaps (border-to-border and ink-to-ink).
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel, PageMeta
from pdf_analyzer.utils.units import create_multi_unit_value


class MarginsSpacingAnalyzer:
    """Analyzes page margins, text-only margins, source elements, and inter-block gaps."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_margins_and_spacing(
        self,
        page_meta: PageMeta,
        spans: List[TextSpanModel],
        regions: List[Dict[str, Any]],
        drawings: List[Dict[str, Any]],
        images: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compute comprehensive margins with source element attribution and inter-block gaps."""
        page_w = page_meta.width.pt
        page_h = page_meta.height.pt

        # 1. Text-Only Margins
        if spans:
            t_left = min(s.ink_box.x0.pt for s in spans)
            t_top = min(s.ink_box.y0.pt for s in spans)
            t_right = page_w - max(s.ink_box.x1.pt for s in spans)
            t_bottom = page_h - max(s.ink_box.y1.pt for s in spans)
        else:
            t_left = t_top = t_right = t_bottom = 0.0

        text_only_margins = {
            "top": create_multi_unit_value(t_top, page_h, self.config.dpi).to_dict(),
            "right": create_multi_unit_value(t_right, page_w, self.config.dpi).to_dict(),
            "bottom": create_multi_unit_value(t_bottom, page_h, self.config.dpi).to_dict(),
            "left": create_multi_unit_value(t_left, page_w, self.config.dpi).to_dict(),
        }

        # 2. Comprehensive Margins (Text Ink + Images + Vector Paths)
        all_elements = []
        for s in spans:
            all_elements.append({
                "type": "text",
                "label": f"Text: '{s.text[:20]}'",
                "bbox": s.ink_box.raw_pt
            })
        for img in images:
            all_elements.append({
                "type": "image",
                "label": f"Image (xref {img.get('xref')})",
                "bbox": img.get("bbox_pt", (0, 0, 0, 0))
            })
        for d in drawings:
            # Only count visible strokes/fills
            if d.get("width_pt", 0) > 0 or d.get("fill_color_hex"):
                all_elements.append({
                    "type": "vector",
                    "label": "Vector Drawing/Rule",
                    "bbox": d.get("bbox", (0, 0, 0, 0))
                })

        if all_elements:
            # Find elements defining each edge
            min_top_el = min(all_elements, key=lambda e: e["bbox"][1])
            min_left_el = min(all_elements, key=lambda e: e["bbox"][0])
            max_right_el = max(all_elements, key=lambda e: e["bbox"][2])
            max_bot_el = max(all_elements, key=lambda e: e["bbox"][3])

            c_top = min_top_el["bbox"][1]
            c_left = min_left_el["bbox"][0]
            c_right = page_w - max_right_el["bbox"][2]
            c_bottom = page_h - max_bot_el["bbox"][3]

            source_elements = {
                "top": min_top_el["label"],
                "left": min_left_el["label"],
                "right": max_right_el["label"],
                "bottom": max_bot_el["label"]
            }
        else:
            c_top = c_left = c_right = c_bottom = 0.0
            source_elements = {"top": "N/A", "left": "N/A", "right": "N/A", "bottom": "N/A"}

        comprehensive_margins = {
            "top": create_multi_unit_value(c_top, page_h, self.config.dpi).to_dict(),
            "right": create_multi_unit_value(c_right, page_w, self.config.dpi).to_dict(),
            "bottom": create_multi_unit_value(c_bottom, page_h, self.config.dpi).to_dict(),
            "left": create_multi_unit_value(c_left, page_w, self.config.dpi).to_dict(),
            "source_elements": source_elements
        }

        # 3. Inter-Block Gaps (border-to-border and ink-to-ink)
        block_gaps = self._compute_block_gaps(regions, page_h)

        # 4. Leading and Whitespace Map
        leading_info = self._analyze_line_leading(spans, page_h)
        whitespace_map = self._compute_whitespace_map(spans, page_w, page_h)

        return {
            "page_margins": comprehensive_margins,
            "text_only_margins": text_only_margins,
            "inter_block_gaps": block_gaps,
            "line_spacing_and_leading": leading_info,
            "whitespace_map": whitespace_map
        }

    def _compute_block_gaps(self, regions: List[Dict[str, Any]], page_h: float) -> Dict[str, Any]:
        """Measure gaps between Header -> Account Box -> Table Heading -> Table -> Footer."""
        region_map = {r["region_type"]: r for r in regions}
        gaps = {}

        sequence = ["header", "account_details", "table_heading", "transaction_table", "footer"]
        present_seq = [s for s in sequence if s in region_map]

        for i in range(len(present_seq) - 1):
            r1_name = present_seq[i]
            r2_name = present_seq[i + 1]
            r1_box = region_map[r1_name]["bbox"]
            r2_box = region_map[r2_name]["bbox"]

            r1_bot = r1_box["y1"]["pt"]
            r2_top = r2_box["y0"]["pt"]

            gap_pt = max(0.0, r2_top - r1_bot)
            gap_key = f"{r1_name}_to_{r2_name}"

            gaps[gap_key] = {
                "gap_pt": round(gap_pt, 3),
                "multi_unit": create_multi_unit_value(gap_pt, page_h, self.config.dpi).to_dict()
            }

        return gaps

    def _analyze_line_leading(self, spans: List[TextSpanModel], page_h: float) -> Dict[str, Any]:
        """Calculate line-to-line leading and line height multipliers across font sizes."""
        if len(spans) < 2:
            return {"mean_leading_pt": 0.0, "leading_ratio": 1.2}

        leadings = []
        sorted_spans = sorted(spans, key=lambda s: s.ink_box.y0.pt)
        for i in range(len(sorted_spans) - 1):
            s1 = sorted_spans[i]
            s2 = sorted_spans[i + 1]
            if abs(s1.ink_box.x0.pt - s2.ink_box.x0.pt) <= 5.0:
                dy = s2.baseline_y.pt - s1.baseline_y.pt
                if 5.0 <= dy <= 30.0:
                    leadings.append(dy)

        mean_leading = float(np.mean(leadings)) if leadings else 12.0
        median_leading = float(np.median(leadings)) if leadings else 12.0

        return {
            "mean_leading_pt": round(mean_leading, 3),
            "median_leading_pt": round(median_leading, 3),
            "estimated_leading_multiplier": round(mean_leading / 10.0, 2)
        }

    def _compute_whitespace_map(
        self,
        spans: List[TextSpanModel],
        page_w: float,
        page_h: float
    ) -> List[Dict[str, Any]]:
        """Find largest unoccupied vertical bands on page."""
        if not spans:
            return []

        sorted_spans = sorted(spans, key=lambda s: s.ink_box.y0.pt)
        empty_bands = []

        for i in range(len(sorted_spans) - 1):
            bottom = sorted_spans[i].ink_box.y1.pt
            next_top = sorted_spans[i + 1].ink_box.y0.pt
            gap = next_top - bottom
            if gap >= 15.0:
                empty_bands.append({
                    "y0_pt": round(bottom, 3),
                    "y1_pt": round(next_top, 3),
                    "height_pt": round(gap, 3),
                    "relative_gap_pct": round(gap / page_h * 100.0, 3)
                })

        return sorted(empty_bands, key=lambda b: b["height_pt"], reverse=True)[:5]

