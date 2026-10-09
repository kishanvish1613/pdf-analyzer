"""CSV elements exporter using pandas with Ink Box and Font Box metrics."""

from typing import List
import pandas as pd
from pdf_analyzer.models import TextSpanModel


def export_elements_csv(spans: List[TextSpanModel], output_path: str) -> None:
    """Export every text span with Ink Box, Font Box, and all 4-unit measurements."""
    rows = []
    for s in spans:
        ink = s.ink_box
        font_b = s.font_box
        rows.append({
            "page": s.page_number,
            "text": s.text,
            "ink_x0_pt": round(ink.x0.pt, 3),
            "ink_y0_pt": round(ink.y0.pt, 3),
            "ink_x1_pt": round(ink.x1.pt, 3),
            "ink_y1_pt": round(ink.y1.pt, 3),
            "ink_width_pt": round(ink.width.pt, 3),
            "ink_height_pt": round(ink.height.pt, 3),
            "font_box_x0_pt": round(font_b.x0.pt, 3),
            "font_box_y0_pt": round(font_b.y0.pt, 3),
            "font_box_x1_pt": round(font_b.x1.pt, 3),
            "font_box_y1_pt": round(font_b.y1.pt, 3),
            "baseline_y_pt": round(s.baseline_y.pt, 3),
            "origin_x_pt": round(s.origin_point[0], 3),
            "font_name": s.font_name,
            "font_family": s.clean_font_family,
            "font_size_pt": round(s.font_size_pt, 3),
            "weight": s.inferred_weight,
            "color_hex": s.color_hex,
            "aa_corrected_hex": s.anti_aliasing_corrected_hex,
            "ink_x0_mm": round(ink.x0.mm, 2),
            "ink_y0_mm": round(ink.y0.mm, 2),
            "ink_width_mm": round(ink.width.mm, 2),
            "ink_height_mm": round(ink.height.mm, 2),
            "ink_x0_px": round(ink.x0.px, 1),
            "ink_y0_px": round(ink.y0.px, 1),
            "ink_width_px": round(ink.width.px, 1),
            "ink_height_px": round(ink.height.px, 1),
            "ink_width_rel_pct": round(ink.width.rel_pct, 3),
            "ink_height_rel_pct": round(ink.height.rel_pct, 3),
            "opacity": s.opacity
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, encoding="utf-8")

