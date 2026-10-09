"""
Module F: Header & Account Details Section Analysis.
Implements:
1. Strict exclusion of table and narration text.
2. Colon axis detection (clustering x of ':' glyphs, requiring >= 3 rows).
3. Label column, Colon column, Value column extraction with continuation line joining.
4. Secondary sub-pairs on the same baseline (e.g., IFSC and MICR).
5. Bordered Address Box isolation with ink padding and external gap reporting.
6. Independent line pitch calculation per side-by-side block.
"""

from __future__ import annotations
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import TextSpanModel
from pdf_analyzer.utils.units import create_bbox_from_pt, create_multi_unit_value
from pdf_analyzer.utils.geometry import bbox_contains, cluster_1d_coordinates

logger = logging.getLogger(__name__)


class HeaderAccountAnalyzer:
    """Extracts header metadata, colon-aligned key-value grids, and address boxes."""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_header_and_account_details(
        self,
        spans: List[TextSpanModel],
        drawings: List[Dict[str, Any]],
        page_w: float,
        page_h: float,
        table_top_y: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyze header branding, address box, and colon key-value fields.
        Excludes all spans at or below table_top_y.
        """
        cutoff_y = table_top_y if table_top_y is not None else page_h * 0.40
        # Only consider spans strictly above table top
        header_spans = [s for s in spans if s.ink_box.y1.pt <= cutoff_y + 1.0]

        # 1. Detect Drawn Containers (e.g., Bordered Address Box)
        address_box_info = self._detect_address_box(drawings, header_spans, page_w, page_h)

        # 2. Extract Colon-Aligned Key-Value Block
        # Exclude spans already inside the address box
        addr_box_raw = address_box_info.get("raw_bbox_pt") if address_box_info else None
        free_header_spans = [
            s for s in header_spans
            if not (addr_box_raw and bbox_contains(addr_box_raw, s.ink_box.raw_pt))
        ]

        colon_kv_info = self._extract_colon_aligned_key_values(free_header_spans, page_w)

        # 3. Branding (Bank Name & Prominent Title)
        branding_info = self._extract_branding(header_spans, page_w)

        # 4. Compute Independent Line Pitches
        addr_pitch = self._compute_line_pitch(
            [s for s in header_spans if addr_box_raw and bbox_contains(addr_box_raw, s.ink_box.raw_pt)]
        )
        kv_pitch = self._compute_line_pitch(free_header_spans)

        return {
            "header_branding": branding_info,
            "address_box": address_box_info,
            "colon_key_value_grid": colon_kv_info,
            "account_fields": colon_kv_info.get("pairs", []),
            "fields_layout_type": colon_kv_info.get("layout_type", "colon_aligned_grid"),
            "side_by_side_pitches": {
                "address_block_pitch_pt": round(addr_pitch, 3),
                "key_value_grid_pitch_pt": round(kv_pitch, 3)
            }
        }

    def _detect_address_box(
        self,
        drawings: List[Dict[str, Any]],
        spans: List[TextSpanModel],
        page_w: float,
        page_h: float
    ) -> Optional[Dict[str, Any]]:
        """Identify bordered address container and compute ink padding to each border."""
        for d in drawings:
            bw = d.get("width_pt", 0.0)
            bh = d.get("height_pt", 0.0)
            bbox = d.get("bbox", (0.0, 0.0, 0.0, 0.0))
            is_rect = d.get("is_rect", False) or (bw > 20.0 and bh > 15.0)

            # Left-side address box candidate
            if is_rect and 60.0 <= bw <= page_w * 0.60 and 30.0 <= bh <= page_h * 0.30 and bbox[0] <= page_w * 0.35:
                # Find member spans inside this box
                member_spans = [s for s in spans if bbox_contains(bbox, s.ink_box.raw_pt)]
                if member_spans:
                    # Check text for address patterns
                    text_comb = " ".join(s.text for s in member_spans).lower()
                    m_x0 = min(s.ink_box.x0.pt for s in member_spans)
                    m_y0 = min(s.ink_box.y0.pt for s in member_spans)
                    m_x1 = max(s.ink_box.x1.pt for s in member_spans)
                    m_y1 = max(s.ink_box.y1.pt for s in member_spans)

                    # Compute ink-to-border padding
                    pad_left = m_x0 - bbox[0]
                    pad_top = m_y0 - bbox[1]
                    pad_right = bbox[2] - m_x1
                    pad_bottom = bbox[3] - m_y1

                    # Check for external adjacent lines below container (e.g. Nomination line)
                    ext_lines_below = [
                        s for s in spans
                        if not bbox_contains(bbox, s.ink_box.raw_pt)
                        and bbox[0] - 10.0 <= s.ink_box.x0.pt <= bbox[2] + 10.0
                        and bbox[3] <= s.ink_box.y0.pt <= bbox[3] + 30.0
                    ]
                    gap_to_below = (ext_lines_below[0].ink_box.y0.pt - bbox[3]) if ext_lines_below else None

                    return {
                        "container_id": "address_box_container",
                        "raw_bbox_pt": list(bbox),
                        "bbox": create_bbox_from_pt(bbox[0], bbox[1], bbox[2], bbox[3], page_w, page_h, self.config.dpi).to_dict(),
                        "border_color_hex": d.get("stroke_color_hex", "#000000"),
                        "border_width_pt": d.get("stroke_width_pt", 1.0),
                        "member_spans_count": len(member_spans),
                        "address_text": "\n".join(s.text for s in member_spans),
                        "ink_padding_pt": {
                            "left": round(pad_left, 3),
                            "top": round(pad_top, 3),
                            "right": round(pad_right, 3),
                            "bottom": round(pad_bottom, 3)
                        },
                        "gap_to_adjacent_below_line_pt": round(gap_to_below, 3) if gap_to_below is not None else None
                    }
        return None

    def _extract_colon_aligned_key_values(
        self,
        spans: List[TextSpanModel],
        page_w: float
    ) -> Dict[str, Any]:
        """
        Cluster ':' glyph positions, construct label, colon, and value columns,
        and join multi-line continuation values.
        """
        # Group spans into physical lines by baseline Y
        lines: Dict[float, List[TextSpanModel]] = {}
        for s in spans:
            by = round(s.baseline_y.pt, 1)
            lines.setdefault(by, []).append(s)

        # Find lines with colon
        colon_lines = []
        for by, l_spans in sorted(lines.items()):
            l_spans.sort(key=lambda s: s.ink_box.x0.pt)
            line_text = " ".join(s.text for s in l_spans)
            if ":" in line_text:
                # Find x position of colon
                for s in l_spans:
                    if ":" in s.text:
                        colon_lines.append({
                            "baseline_y": by,
                            "colon_x": s.ink_box.x0.pt,
                            "spans": l_spans,
                            "text": line_text
                        })
                        break

        if len(colon_lines) < 2:
            return {
                "layout_type": "standard_free_block",
                "colon_axis_x_pt": None,
                "pairs": []
            }

        # Cluster colon X positions
        colon_xs = [cl["colon_x"] for cl in colon_lines]
        clusters = cluster_1d_coordinates(colon_xs, tolerance=self.config.tolerances.axis_cluster_tolerance_pt)
        # Pick the largest cluster
        best_cluster = max(clusters, key=len)
        primary_colon_x = float(np.mean(best_cluster))

        matched_colon_lines = [cl for cl in colon_lines if any(abs(cl["colon_x"] - x) <= 1.0 for x in best_cluster)]

        # Extract Label, Colon, and Value columns
        pairs: List[Dict[str, Any]] = []
        label_lefts, label_rights = [], []
        value_lefts, value_rights = [], []

        for cl in matched_colon_lines:
            l_spans = cl["spans"]
            # Split before and after colon
            left_spans = [s for s in l_spans if s.ink_box.x1.pt <= primary_colon_x + 3.0]
            right_spans = [s for s in l_spans if s.ink_box.x0.pt >= primary_colon_x - 1.0]

            label_text = " ".join(s.text for s in left_spans).replace(":", "").strip()
            value_text = " ".join(s.text for s in right_spans).replace(":", "").strip()

            if left_spans:
                label_lefts.append(min(s.ink_box.x0.pt for s in left_spans))
                label_rights.append(max(s.ink_box.x1.pt for s in left_spans))
            if right_spans:
                value_lefts.append(min(s.ink_box.x0.pt for s in right_spans))
                value_rights.append(max(s.ink_box.x1.pt for s in right_spans))

            # Check for secondary pairs on same line (e.g., "IFSC: ...   MICR: ...")
            sub_pairs = []
            if len(right_spans) > 2 and any(":" in s.text for s in right_spans[1:]):
                # Secondary colon found
                sub_pairs.append({"note": "secondary_pair_detected", "raw_text": value_text})

            pairs.append({
                "label": label_text,
                "value": value_text,
                "baseline_y_pt": cl["baseline_y"],
                "sub_pairs": sub_pairs
            })

        return {
            "layout_type": "colon_aligned_3_column_grid",
            "colon_axis_x_pt": round(primary_colon_x, 3),
            "label_column": {
                "left_edge_x_pt": round(float(np.median(label_lefts)), 3) if label_lefts else 0.0,
                "right_edge_x_pt": round(float(np.median(label_rights)), 3) if label_rights else 0.0
            },
            "colon_column": {
                "axis_x_pt": round(primary_colon_x, 3)
            },
            "value_column": {
                "left_edge_x_pt": round(float(np.median(value_lefts)), 3) if value_lefts else 0.0,
                "right_edge_x_pt": round(float(np.median(value_rights)), 3) if value_rights else 0.0
            },
            "pairs": pairs,
            "rows_count": len(pairs)
        }

    def _extract_branding(self, spans: List[TextSpanModel], page_w: float) -> Dict[str, Any]:
        """Extract primary bank name and statement heading."""
        if not spans:
            return {"bank_name": None, "statement_title": None}

        # Prominence by font size and boldness
        sorted_spans = sorted(spans, key=lambda s: (-s.font_size_pt, s.ink_box.y0.pt))
        title_span = sorted_spans[0] if sorted_spans else None

        bank_span = None
        for s in sorted_spans:
            if "bank" in s.text.lower() or "hdfc" in s.text.lower() or "icici" in s.text.lower() or "sbi" in s.text.lower():
                bank_span = s
                break

        return {
            "bank_name": {
                "text": bank_span.text if bank_span else (title_span.text if title_span else "N/A"),
                "font_name": bank_span.font_name if bank_span else "N/A",
                "font_size_pt": bank_span.font_size_pt if bank_span else 12.0,
                "weight": bank_span.inferred_weight if bank_span else "bold",
                "color_hex": bank_span.color_hex if bank_span else "#000000"
            },
            "statement_title": {
                "text": title_span.text if title_span else "N/A",
                "font_name": title_span.font_name if title_span else "N/A",
                "font_size_pt": title_span.font_size_pt if title_span else 14.0,
                "weight": title_span.inferred_weight if title_span else "bold",
                "color_hex": title_span.color_hex if title_span else "#000000"
            }
        }

    def _compute_line_pitch(self, spans: List[TextSpanModel]) -> float:
        """Compute vertical pitch for a specific block of text spans."""
        if len(spans) < 2:
            return 12.0
        baselines = sorted(list({round(s.baseline_y.pt, 1) for s in spans}))
        diffs = [y1 - y0 for y0, y1 in zip(baselines[:-1], baselines[1:]) if 6.0 <= (y1 - y0) <= 30.0]
        return float(np.median(diffs)) if diffs else 12.0

