"""
Logical Row Extraction Engine (Phase 8C Tasks 3 & 4).
Extracts logical table rows with multi-line wrapped cells and band typing:
- Types rows: TABLE_TITLE_BAND, HEADER, OPENING_BALANCE, BODY, EMPTY_BAND, CLOSING.
- Anchors transaction rows via Date (DD/MM/YYYY) or sequence number columns.
- Gathers 2-5 line wrapped descriptions into their parent anchor row.
- Places row boundaries in ink-free gaps and asserts non-collision using shapely.strtree.STRtree.
- Calculates per-row line count (lines_count) and line pitch (pitch_pt).
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
from shapely.geometry import box as shapely_box, LineString
from shapely.strtree import STRtree

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar
from pdf_analyzer.l2_primitives.ruleset import Rule


DATE_PATTERNS = [
    re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"),
    re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$"),
    re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"),
    re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}$"),
    re.compile(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$"),
]

SNO_PATTERN = re.compile(r"^\d{1,5}$")

TITLE_BAND_PATTERNS = re.compile(
    r"(savings\s+account\s+transactions|transaction\s+details|statement\s+of\s+account|account\s+statement)",
    re.IGNORECASE,
)

OPENING_PATTERNS = re.compile(
    r"(opening\s+balance|balance\s+b/f|b/f|brought\s+forward)",
    re.IGNORECASE,
)

CLOSING_PATTERNS = re.compile(
    r"(closing\s+balance|total|balance\s+c/f|c/f|carried\s+forward|summary|end\s+of\s+statement)",
    re.IGNORECASE,
)


@dataclass
class TextLine:
    text: str
    bbox_pt: Tuple[float, float, float, float]
    baseline_y_pt: float
    chars: List[PaintedTextChar] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return self.bbox_pt[0]

    @property
    def x1(self) -> float:
        return self.bbox_pt[2]

    @property
    def y0(self) -> float:
        return self.bbox_pt[1]

    @property
    def y1(self) -> float:
        return self.bbox_pt[3]


class LogicalRowEngine:
    """
    Recovers logical table rows, resolves multi-line cell wrapping, and classifies band types.
    """

    def extract_logical_rows(
        self,
        page_layer: PageByteLayer,
        table_bbox_pt: Tuple[float, float, float, float],
        columns: List[Any],
        h_rules: Optional[List[Rule]] = None,
    ) -> List[Any]:
        from pdf_analyzer.l3_topology.table_grid import RowModel, RowBandType

        t_x0, t_y0, t_x1, t_y1 = table_bbox_pt

        chars_in_table = [
            c for c in page_layer.chars
            if t_x0 - 2.0 <= c.origin_device_pt[0] <= t_x1 + 2.0
            and t_y0 - 2.0 <= c.origin_device_pt[1] <= t_y1 + 2.0
        ]

        if not chars_in_table:
            # If no text characters, construct geometric rows from horizontal rules if present
            matching_h_rules = []
            if h_rules:
                for r in h_rules:
                    if t_y0 - 2.0 <= r.centre <= t_y1 + 2.0 and r.span >= 0.35 * (t_x1 - t_x0):
                        matching_h_rules.append(r)
                matching_h_rules.sort(key=lambda r: r.centre, reverse=True)
            rows: List[RowModel] = []
            if len(matching_h_rules) >= 2:
                for k in range(len(matching_h_rules) - 1):
                    r_top = matching_h_rules[k]
                    r_bot = matching_h_rules[k + 1]
                    rows.append(RowModel(
                        index=len(rows) + 1,
                        y0_pt=r_bot.centre,
                        y1_pt=r_top.centre,
                        height_pt=r_top.centre - r_bot.centre,
                        is_header=(k == 0),
                        row_type=RowBandType.HEADER if k == 0 else RowBandType.BODY,
                        lines_count=0,
                        pitch_pt=0.0,
                        text_content="",
                        top_rule_id=r_top.id,
                        bottom_rule_id=r_bot.id,
                    ))
            return rows

        # Build STRtree for ink non-collision assertions
        tree, geoms = self._build_ink_tree(chars_in_table)

        lines = self.group_into_lines(chars_in_table)
        if not lines:
            return []

        lines.sort(key=lambda l: l.baseline_y_pt, reverse=True)

        rows: List[RowModel] = []
        data_lines: List[TextLine] = []

        # 1. Identify Table Title Band, Header Band, and Opening/Closing Balance
        for line in lines:
            txt = line.text.strip()
            # Title band (e.g. pink band "Savings Account Transactions")
            if TITLE_BAND_PATTERNS.search(txt) and line.baseline_y_pt >= t_y1 - 25.0:
                rows.append(RowModel(
                    index=len(rows) + 1,
                    y0_pt=line.y0 - 2.0,
                    y1_pt=line.y1 + 2.0,
                    height_pt=line.y1 - line.y0 + 4.0,
                    is_header=False,
                    row_type=RowBandType.TABLE_TITLE_BAND,
                    lines_count=1,
                    pitch_pt=0.0,
                    text_content=txt,
                ))
            # Header row
            # K4: Header row must have >= 4 header keywords on ONE baseline (or >= 2 keywords
            # including primary column headers like description/particulars/narration).
            # Info-block lines like "Date of Statement" only match 1 keyword ("date") and are rejected.
            elif not any(r.row_type == RowBandType.HEADER for r in rows) and self._is_header_text(txt):
                rows.append(RowModel(
                    index=len(rows) + 1,
                    y0_pt=line.y0 - 2.0,
                    y1_pt=line.y1 + 2.0,
                    height_pt=line.y1 - line.y0 + 4.0,
                    is_header=True,
                    row_type=RowBandType.HEADER,
                    lines_count=1,
                    pitch_pt=0.0,
                    text_content=txt,
                ))
            # Opening balance
            elif OPENING_PATTERNS.search(txt) and len(rows) <= 2:
                rows.append(RowModel(
                    index=len(rows) + 1,
                    y0_pt=line.y0 - 2.0,
                    y1_pt=line.y1 + 2.0,
                    height_pt=line.y1 - line.y0 + 4.0,
                    is_header=False,
                    row_type=RowBandType.OPENING_BALANCE,
                    lines_count=1,
                    pitch_pt=0.0,
                    text_content=txt,
                ))
            # Closing row / End of statement
            elif CLOSING_PATTERNS.search(txt) and line.baseline_y_pt <= t_y0 + 55.0:
                rows.append(RowModel(
                    index=len(rows) + 1,
                    y0_pt=line.y0 - 2.0,
                    y1_pt=line.y1 + 2.0,
                    height_pt=line.y1 - line.y0 + 4.0,
                    is_header=False,
                    row_type=RowBandType.CLOSING,
                    lines_count=1,
                    pitch_pt=0.0,
                    text_content=txt,
                ))
            else:
                data_lines.append(line)
        # 2. Check if table has explicit horizontal rules between rows
        matching_h_rules = []
        if h_rules:
            for r in h_rules:
                if t_y0 - 2.0 <= r.centre <= t_y1 + 2.0 and r.span >= 0.35 * (t_x1 - t_x0):
                    matching_h_rules.append(r)
            matching_h_rules.sort(key=lambda r: r.centre, reverse=True)

        if len(matching_h_rules) >= 3:
            # Reconstruct all row slots from physical horizontal rules
            grid_rows: List[RowModel] = []
            for k in range(len(matching_h_rules) - 1):
                r_top = matching_h_rules[k]
                r_bot = matching_h_rules[k + 1]
                slot_y1 = r_top.centre
                slot_y0 = r_bot.centre

                slot_lines = [l for l in lines if slot_y0 - 1.0 <= l.baseline_y_pt <= slot_y1 + 1.0]
                is_hdr = (k == 0)
                line_count = len(slot_lines)
                pitch = float(np.mean([abs(slot_lines[m].baseline_y_pt - slot_lines[m + 1].baseline_y_pt) for m in range(line_count - 1)])) if line_count > 1 else 0.0
                txt_content = " \n ".join(l.text for l in slot_lines)

                r_type = RowBandType.HEADER if is_hdr else RowBandType.BODY
                if not is_hdr and slot_lines:
                    if OPENING_PATTERNS.search(txt_content):
                        r_type = RowBandType.OPENING_BALANCE
                    elif CLOSING_PATTERNS.search(txt_content):
                        r_type = RowBandType.CLOSING

                grid_rows.append(RowModel(
                    index=len(grid_rows) + 1,
                    y0_pt=slot_y0,
                    y1_pt=slot_y1,
                    height_pt=slot_y1 - slot_y0,
                    is_header=is_hdr,
                    row_type=r_type,
                    lines_count=line_count,
                    pitch_pt=pitch,
                    text_content=txt_content,
                    top_rule_id=r_top.id,
                    bottom_rule_id=r_bot.id,
                ))
            return grid_rows

        if not data_lines:
            return rows

        # 3. Multi-Line Wrapped Body Rows Clustering via Anchor Detection
        anchor_indices: List[int] = []
        left_threshold = t_x0 + 0.35 * (t_x1 - t_x0)

        for idx, line in enumerate(data_lines):
            is_anchor = self._is_anchor_line(line, left_threshold)
            if is_anchor or idx == 0:
                anchor_indices.append(idx)

        if not anchor_indices:
            anchor_indices = list(range(len(data_lines)))

        # Form Transaction Rows from anchor clusters
        for i, anchor_idx in enumerate(anchor_indices):
            next_anchor_idx = anchor_indices[i + 1] if i + 1 < len(anchor_indices) else len(data_lines)
            cluster_lines = data_lines[anchor_idx:next_anchor_idx]

            cluster_y1 = max(l.y1 for l in cluster_lines) + 2.0
            cluster_y0 = min(l.y0 for l in cluster_lines) - 2.0

            line_count = len(cluster_lines)
            if line_count > 1:
                pitches = [abs(cluster_lines[k].baseline_y_pt - cluster_lines[k + 1].baseline_y_pt) for k in range(line_count - 1)]
                pitch = float(np.mean(pitches))
            else:
                pitch = 0.0

            row_txt = " \n ".join(l.text for l in cluster_lines)
            is_empty_band = len(cluster_lines) == 0 or (len(cluster_lines) == 1 and not cluster_lines[0].text.strip())
            r_type = RowBandType.EMPTY_BAND if is_empty_band else RowBandType.BODY

            # Assert row boundary does not intersect character ink box
            boundary_line = LineString([(t_x0, cluster_y0), (t_x1, cluster_y0)])
            hits = tree.query(boundary_line)
            for h_idx in hits:
                g = geoms[h_idx]
                if boundary_line.intersects(g) and g.area > 0.0:
                    cluster_y0 = float(g.bounds[1] - 1.0)

            rows.append(RowModel(
                index=len(rows) + 1,
                y0_pt=cluster_y0,
                y1_pt=cluster_y1,
                height_pt=max(1.0, cluster_y1 - cluster_y0),
                is_header=False,
                row_type=r_type,
                lines_count=line_count,
                pitch_pt=pitch,
                text_content=row_txt,
            ))

        return rows

    def _build_ink_tree(self, chars: List[PaintedTextChar]) -> Tuple[STRtree, List[Any]]:
        geoms = []
        for c in chars:
            bx0, by0, bx1, by1 = c.font_bbox_device_pt
            if bx1 > bx0 and by1 > by0:
                geoms.append(shapely_box(bx0, by0, bx1, by1))
        if not geoms:
            geoms.append(shapely_box(0, 0, 0, 0))
        return STRtree(geoms), geoms

    def group_into_lines(self, chars: List[PaintedTextChar], baseline_tol_pt: float = 2.0) -> List[TextLine]:
        if not chars:
            return []

        sorted_chars = sorted(chars, key=lambda c: c.origin_device_pt[1], reverse=True)
        clusters: List[List[PaintedTextChar]] = []

        for c in sorted_chars:
            placed = False
            for cluster in clusters:
                if abs(cluster[0].origin_device_pt[1] - c.origin_device_pt[1]) <= baseline_tol_pt:
                    cluster.append(c)
                    placed = True
                    break
            if not placed:
                clusters.append([c])

        lines: List[TextLine] = []
        for cluster in clusters:
            cluster.sort(key=lambda c: c.origin_device_pt[0])
            avg_base_y = float(np.mean([c.origin_device_pt[1] for c in cluster]))

            txt_tokens = []
            for i, c in enumerate(cluster):
                ch_txt = c.unicode_text or c.char_text
                if i > 0:
                    prev = cluster[i - 1]
                    gap = c.origin_device_pt[0] - prev.font_bbox_device_pt[2]
                    if gap >= max(0.8, 0.0625 * prev.font_size_pt) and not ch_txt.startswith(" "):
                        txt_tokens.append(" ")
                txt_tokens.append(ch_txt)
            line_text = "".join(txt_tokens)

            x0 = min(c.font_bbox_device_pt[0] for c in cluster)
            y0 = min(c.font_bbox_device_pt[1] for c in cluster)
            x1 = max(c.font_bbox_device_pt[2] for c in cluster)
            y1 = max(c.font_bbox_device_pt[3] for c in cluster)

            lines.append(TextLine(
                text=line_text,
                bbox_pt=(x0, y0, x1, y1),
                baseline_y_pt=avg_base_y,
                chars=cluster,
            ))

        return lines

    def _is_anchor_line(self, line: TextLine, left_threshold: float) -> bool:
        """Determines if a line starts with a date pattern, sequence number, or txn token on the left."""
        if not line.chars:
            return False

        first_char_x = line.chars[0].origin_device_pt[0]
        if first_char_x > left_threshold:
            return False

        tokens = line.text.split()
        if not tokens:
            return False

        first_token = tokens[0]
        # 1. Date Check
        for pattern in DATE_PATTERNS:
            if pattern.match(first_token):
                return True

        # 2. Sequence Number Check
        if SNO_PATTERN.match(first_token) and len(first_token) <= 4:
            return True

        return False

    def _is_header_text(self, txt: str) -> bool:
        """K4: Determines if text line represents a table column header row.
        Rejects single-keyword metadata/info lines such as 'Date of Statement'."""
        _HDR_KWS = [
            "value date", "post date", "txn date", "trans date",
            "date", "narration", "particulars", "description", "details",
            "balance", "withdrawal", "deposit", "chq", "ref",
            "debit", "credit", "amount", "#",
        ]
        txt_lower = txt.lower()
        matched = sum(1 for k in _HDR_KWS if k in txt_lower)
        if matched >= 4:
            return True
        if matched >= 2 and any(k in txt_lower for k in ["description", "particulars", "narration", "details"]):
            return True
        return False
