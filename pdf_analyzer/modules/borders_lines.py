"""Module H: Borders, lines, thickness, and cell structure analysis.

Merges collinear overlapping line segments, flags doubled strokes, treats thin filled rects
as lines, and reconstructs the exact cell border grid with per-side border properties.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.utils.units import create_multi_unit_value, create_bbox_from_pt


class BordersLinesAnalyzer:
    """Analyzes vector strokes, ruling lines, line segment merging, and cell grid structures."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_borders_and_lines(
        self,
        drawings: List[Dict[str, Any]],
        table_bbox_pt: Optional[Tuple[float, float, float, float]],
        page_w: float,
        page_h: float
    ) -> Dict[str, Any]:
        """Merge near-duplicate/collinear strokes, reconstruct cell grid, and classify borders."""
        raw_h_lines: List[Dict[str, Any]] = []
        raw_v_lines: List[Dict[str, Any]] = []
        boxes: List[Dict[str, Any]] = []
        rounded_corners = False
        thin_limit = self.config.tolerances.thin_rect_as_line_max_dim_pt

        for d in drawings:
            bbox = d.get("bbox", (0, 0, 0, 0))
            w = d.get("width_pt", 0.0)
            h = d.get("height_pt", 0.0)
            stroke_w = d.get("stroke_width_pt", 1.0)
            stroke_hex = d.get("stroke_color_hex")
            fill_hex = d.get("fill_color_hex")
            dashes = d.get("dashes")
            stroke_w_val = stroke_w if stroke_w is not None else 0.0

            if "c" in d.get("item_types", []):
                rounded_corners = True

            # 1. Pure line or thin filled rectangle as horizontal line
            if (w > 5.0 and h <= thin_limit) or (h == 0 and w > 5.0):
                raw_h_lines.append({
                    "x0": min(bbox[0], bbox[2]),
                    "x1": max(bbox[0], bbox[2]),
                    "y": (bbox[1] + bbox[3]) / 2.0,
                    "thickness": max(h, stroke_w_val) if h > 0 else stroke_w_val,
                    "color_hex": stroke_hex or fill_hex or "#000000",
                    "dashes": dashes
                })

            # 2. Pure line or thin filled rectangle as vertical line
            elif (h > 5.0 and w <= thin_limit) or (w == 0 and h > 5.0):
                raw_v_lines.append({
                    "y0": min(bbox[1], bbox[3]),
                    "y1": max(bbox[1], bbox[3]),
                    "x": (bbox[0] + bbox[2]) / 2.0,
                    "thickness": max(w, stroke_w_val) if w > 0 else stroke_w_val,
                    "color_hex": stroke_hex or fill_hex or "#000000",
                    "dashes": dashes
                })

            # 3. Regular Rectangle / Box
            elif w > thin_limit and h > thin_limit:
                boxes.append({
                    "bbox": create_bbox_from_pt(bbox[0], bbox[1], bbox[2], bbox[3], page_w, page_h, self.config.dpi).to_dict(),
                    "stroke_width_pt": stroke_w_val,
                    "stroke_color_hex": stroke_hex,
                    "fill_color_hex": fill_hex
                })

        # Merge collinear, overlapping, or doubled lines
        merged_h_lines = self._merge_collinear_lines(raw_h_lines, is_horizontal=True, page_w=page_w, page_h=page_h)
        merged_v_lines = self._merge_collinear_lines(raw_v_lines, is_horizontal=False, page_w=page_w, page_h=page_h)

        # Reconstruct Cell Grid from merged lines
        grid_style = self._reconstruct_table_grid_style(merged_h_lines, merged_v_lines, table_bbox_pt)

        return {
            "total_horizontal_rules": len(merged_h_lines),
            "total_vertical_rules": len(merged_v_lines),
            "total_boxes": len(boxes),
            "has_rounded_corners": rounded_corners,
            "table_border_grid": grid_style,
            "horizontal_rules": merged_h_lines,
            "vertical_rules": merged_v_lines
        }

    def _merge_collinear_lines(
        self,
        raw_lines: List[Dict[str, Any]],
        is_horizontal: bool,
        page_w: float,
        page_h: float
    ) -> List[Dict[str, Any]]:
        """Merge collinear and overlapping line segments within tolerance into single logical borders."""
        tol = self.config.tolerances.line_merge_collinear_tolerance_pt
        if not raw_lines:
            return []

        # Sort lines by perpendicular coordinate (y for horizontal, x for vertical), then along line
        if is_horizontal:
            sorted_lines = sorted(raw_lines, key=lambda l: (round(l["y"] / tol), l["x0"]))
        else:
            sorted_lines = sorted(raw_lines, key=lambda l: (round(l["x"] / tol), l["y0"]))

        merged_groups: List[List[Dict[str, Any]]] = []

        for line in sorted_lines:
            if not merged_groups:
                merged_groups.append([line])
                continue

            last_group = merged_groups[-1]
            last_line = last_group[-1]

            if is_horizontal:
                is_collinear = abs(line["y"] - last_line["y"]) <= tol
                is_overlapping = (line["x0"] <= max(l["x1"] for l in last_group) + tol)
            else:
                is_collinear = abs(line["x"] - last_line["x"]) <= tol
                is_overlapping = (line["y0"] <= max(l["y1"] for l in last_group) + tol)

            if is_collinear and is_overlapping:
                last_group.append(line)
            else:
                merged_groups.append([line])

        merged_results: List[Dict[str, Any]] = []

        for group in merged_groups:
            seg_count = len(group)
            is_doubled = seg_count >= 2

            if is_horizontal:
                merged_x0 = min(l["x0"] for l in group)
                merged_x1 = max(l["x1"] for l in group)
                merged_y = float(np.mean([l["y"] for l in group]))
                # Effective thickness: sum or max depending on doubled overlap
                merged_thick = max(l["thickness"] for l in group)
                color = group[0]["color_hex"]
                length = merged_x1 - merged_x0

                merged_results.append({
                    "start_pt": [round(merged_x0, 3), round(merged_y, 3)],
                    "end_pt": [round(merged_x1, 3), round(merged_y, 3)],
                    "length_pt": round(length, 3),
                    "stroke_width_pt": round(merged_thick, 3),
                    "stroke_color_hex": color,
                    "original_segment_count": seg_count,
                    "doubled_stroke": is_doubled,
                    "is_dashed": group[0]["dashes"] is not None,
                    "multi_unit_length": create_multi_unit_value(length, page_w, self.config.dpi).to_dict()
                })
            else:
                merged_y0 = min(l["y0"] for l in group)
                merged_y1 = max(l["y1"] for l in group)
                merged_x = float(np.mean([l["x"] for l in group]))
                merged_thick = max(l["thickness"] for l in group)
                color = group[0]["color_hex"]
                length = merged_y1 - merged_y0

                merged_results.append({
                    "start_pt": [round(merged_x, 3), round(merged_y0, 3)],
                    "end_pt": [round(merged_x, 3), round(merged_y1, 3)],
                    "length_pt": round(length, 3),
                    "stroke_width_pt": round(merged_thick, 3),
                    "stroke_color_hex": color,
                    "original_segment_count": seg_count,
                    "doubled_stroke": is_doubled,
                    "is_dashed": group[0]["dashes"] is not None,
                    "multi_unit_length": create_multi_unit_value(length, page_h, self.config.dpi).to_dict()
                })

        return merged_results

    def _reconstruct_table_grid_style(
        self,
        h_rules: List[Dict[str, Any]],
        v_rules: List[Dict[str, Any]],
        table_bbox_pt: Optional[Tuple[float, float, float, float]]
    ) -> Dict[str, Any]:
        """Reconstruct table grid and border configurations."""
        if not table_bbox_pt:
            return {
                "style": "borderless / whitespace-separated",
                "outer_border": False,
                "horizontal_row_separators": False,
                "vertical_column_separators": False,
                "stroke_width_pt": 0.0,
                "stroke_color_hex": None,
                "doubled_strokes_detected": False
            }

        tx0, ty0, tx1, ty1 = table_bbox_pt
        table_h_rules = [
            r for r in h_rules
            if ty0 - 5.0 <= r["start_pt"][1] <= ty1 + 5.0
        ]
        table_v_rules = [
            r for r in v_rules
            if tx0 - 5.0 <= r["start_pt"][0] <= tx1 + 5.0
        ]

        has_h_separators = len(table_h_rules) >= 2
        has_v_separators = len(table_v_rules) >= 2
        doubled = any(r.get("doubled_stroke") for r in table_h_rules + table_v_rules)

        if has_h_separators and has_v_separators:
            grid_type = "full_grid"
        elif has_h_separators:
            grid_type = "horizontal_rules_only (clean modern)"
        elif has_v_separators:
            grid_type = "vertical_rules_only"
        else:
            grid_type = "borderless / whitespace-separated"

        avg_stroke = float(np.mean([r["stroke_width_pt"] for r in table_h_rules])) if table_h_rules else 0.5
        sample_color = table_h_rules[0]["stroke_color_hex"] if table_h_rules else "#E0E0E0"

        return {
            "style": grid_type,
            "outer_border": len(table_h_rules) >= 2 and len(table_v_rules) >= 2,
            "horizontal_row_separators": has_h_separators,
            "vertical_column_separators": has_v_separators,
            "average_stroke_width_pt": round(avg_stroke, 3),
            "border_color_hex": sample_color,
            "doubled_strokes_detected": doubled
        }

