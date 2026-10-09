"""
L4 Key-Value Pair & Structured Grid Extraction Engine (E6).
Detects K1 (colon), K2 (font style change), and K3 (whitespace gap >= 2.5x space width)
key-value relationships. Clusters value-start X coordinates, reports alignment jitter,
splits numeric values from currency/balance suffixes (Cr., Dr.), and constructs KVGrid models.
"""

from __future__ import annotations
import re
import math
from typing import List, Dict, Tuple, Optional, Any
import numpy as np

from pdf_analyzer.l4_layout.models import (
    TextSegment,
    TextLine,
    KVEntry,
    KVGrid,
)

NUMERIC_SUFFIX_REGEX = re.compile(
    r"^([+-]?\s*[\d,]+\.?\d*)\s*([A-Za-z%\.]+|\(.*?\))?$",
    re.IGNORECASE,
)


class KeyValueEngine:
    """
    Extracts key-value pairs and structured KV grids from lines of text.
    """

    def __init__(self, space_width_pt: float = 3.5):
        self.space_width_pt = space_width_pt

    def extract_kv_grid(self, lines: List[TextLine], grid_id: str = "kv_grid_0") -> Optional[KVGrid]:
        """
        Attempts to extract a structured KVGrid from a set of lines.
        Requires at least 3 rows to qualify as a structured KV_GRID.
        """
        if not lines:
            return None

        entries: List[KVEntry] = []
        for line in lines:
            entry = self.extract_kv_from_line(line)
            if entry:
                entries.append(entry)

        if len(entries) < 3:
            # Not enough rows for a formal grid, but individual pairs might exist
            return None

        # Compute value alignment axis and jitter
        valid_x = [e.value_start_x_pt for e in entries if e.value_start_x_pt is not None]
        if not valid_x:
            return None

        axis_x = float(np.median(valid_x))
        max_jitter = float(max(abs(x - axis_x) for x in valid_x))

        for e in entries:
            if e.value_start_x_pt is not None:
                e.jitter_pt = float(abs(e.value_start_x_pt - axis_x))

        label_lefts = [e.key_bbox_pt[0] for e in entries]
        label_axis_x = float(np.median(label_lefts)) if label_lefts else None

        return KVGrid(
            grid_id=grid_id,
            entries=entries,
            value_axis_x_pt=axis_x,
            label_left_x_pt=label_axis_x,
            max_jitter_pt=max_jitter,
            rows_count=len(entries),
            is_valid_grid=True,
        )

    def extract_kv_from_line(self, line: TextLine) -> Optional[KVEntry]:
        """
        Extracts a single KVEntry from a line using K1, K2, or K3 criteria.
        """
        if not line.segments:
            return None

        full_text = line.text.strip()
        if not full_text:
            return None

        # K1: Colon Separator
        if ":" in full_text:
            parts = full_text.split(":", 1)
            k_txt = parts[0].strip()
            v_txt = parts[1].strip() if len(parts) > 1 else ""

            # Determine key and value bounding boxes from segments
            k_segs: List[TextSegment] = []
            v_segs: List[TextSegment] = []
            seen_colon = False

            for seg in line.segments:
                if ":" in seg.text:
                    seen_colon = True
                    k_segs.append(seg)
                elif not seen_colon:
                    k_segs.append(seg)
                else:
                    v_segs.append(seg)

            k_bbox = self._compute_segs_bbox(k_segs) or line.bbox_pt
            v_bbox = self._compute_segs_bbox(v_segs) if v_segs else None
            v_start_x = v_segs[0].x0 if v_segs else (line.bbox_pt[0] + line.bbox_pt[2]) / 2.0

            num_val, suffix = self._parse_numeric_and_suffix(v_txt)

            return KVEntry(
                key_text=k_txt,
                value_text=v_txt if v_txt else None,
                key_bbox_pt=k_bbox,
                value_bbox_pt=v_bbox,
                separator_type="K1_COLON",
                value_start_x_pt=v_start_x,
                numeric_value=num_val,
                suffix=suffix,
            )

        # K2: Font Style Change (e.g. bold label, normal value)
        if len(line.segments) >= 2:
            first_seg = line.segments[0]
            rest_segs = line.segments[1:]
            if first_seg.is_bold and not any(s.is_bold for s in rest_segs):
                k_txt = first_seg.text.strip()
                v_txt = " ".join(s.text.strip() for s in rest_segs).strip()
                k_bbox = first_seg.bbox_pt
                v_bbox = self._compute_segs_bbox(rest_segs)
                v_start_x = rest_segs[0].x0
                num_val, suffix = self._parse_numeric_and_suffix(v_txt)

                return KVEntry(
                    key_text=k_txt,
                    value_text=v_txt,
                    key_bbox_pt=k_bbox,
                    value_bbox_pt=v_bbox,
                    separator_type="K2_FONT_STYLE",
                    value_start_x_pt=v_start_x,
                    numeric_value=num_val,
                    suffix=suffix,
                )

        # K3: Whitespace gap >= 2.5x space width
        if len(line.segments) >= 2:
            gap_threshold = 2.5 * self.space_width_pt
            for i in range(len(line.segments) - 1):
                gap = line.segments[i + 1].x0 - line.segments[i].x1
                if gap >= gap_threshold:
                    k_segs = line.segments[: i + 1]
                    v_segs = line.segments[i + 1 :]
                    k_txt = " ".join(s.text for s in k_segs).strip()
                    v_txt = " ".join(s.text for s in v_segs).strip()
                    k_bbox = self._compute_segs_bbox(k_segs) or line.bbox_pt
                    v_bbox = self._compute_segs_bbox(v_segs)
                    v_start_x = v_segs[0].x0
                    num_val, suffix = self._parse_numeric_and_suffix(v_txt)

                    return KVEntry(
                        key_text=k_txt,
                        value_text=v_txt,
                        key_bbox_pt=k_bbox,
                        value_bbox_pt=v_bbox,
                        separator_type="K3_WHITESPACE_GAP",
                        value_start_x_pt=v_start_x,
                        numeric_value=num_val,
                        suffix=suffix,
                    )

        return None

    def _compute_segs_bbox(self, segs: List[TextSegment]) -> Optional[Tuple[float, float, float, float]]:
        if not segs:
            return None
        return (
            min(s.x0 for s in segs),
            min(s.y0 for s in segs),
            max(s.x1 for s in segs),
            max(s.y1 for s in segs),
        )

    def _parse_numeric_and_suffix(self, text: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
        if not text:
            return None, None
        m = NUMERIC_SUFFIX_REGEX.match(text.strip())
        if not m:
            return None, None
        val_str = m.group(1).replace(",", "").strip()
        try:
            val = float(val_str)
            suffix = m.group(2).strip() if m.group(2) else None
            return val, suffix
        except ValueError:
            return None, None
