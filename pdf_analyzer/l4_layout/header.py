"""
L4 Header Reconstruction & Two-Block Partitioning Engine (E5, Phase 8B Task 4).
Splits header regions into side-by-side blocks by vertical gutters, supports full-width titles,
builds TextLines from TextSegments sharing baseline +- 0.5 pt without dropping segments or spaces,
classifies Title using a rigorous scoring engine (largest font size, horizontal centring, position
above table, not inside container, not address/key-value), and computes exact gap metrics.
"""

from __future__ import annotations
import math
import re
from typing import List, Dict, Tuple, Optional, Any
import numpy as np

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, Color
from pdf_analyzer.l4_layout.models import (
    TextSegment,
    TextLine,
    BlockType,
    HeaderBlock,
    HeaderModel,
    TitleScoreRecord,
)
from pdf_analyzer.l4_layout.key_value import KeyValueEngine


class HeaderEngine:
    """
    Partitions header text into side-by-side blocks, scores Title candidates,
    and classifies sub-block structures.
    """

    def __init__(self):
        self.kv_engine = KeyValueEngine()

    def _score_title_candidates(
        self,
        lines: List[TextLine],
        page_layer: PageByteLayer,
        table_top_y_pt: float,
    ) -> List[TitleScoreRecord]:
        """
        Scores all candidate lines for Title classification:
        - Font size score (up to 40)
        - Centering score (up to 30)
        - Position above table score (20)
        - Container / Address / KV penalty (-50 to -30)
        - Title keywords boost (+30)
        """
        if not lines:
            return []

        max_font_size = max([max([s.font_size_pt for s in l.segments] or [10.0]) for l in lines] or [10.0])
        page_centre_x = page_layer.width_pt / 2.0

        address_pattern = re.compile(
            r"(,|ROAD|DIST|PIN|FLAT|STREET|NAGAR|COLONY|PLOT|SECTOR|HOUSE|BUILDING|LTD|PVT|BRANCH|IFSC|MICR|PHONE|TEL|EMAIL|MAHWADI|MAHWA|JAIPUR)",
            re.IGNORECASE,
        )
        title_keywords = re.compile(
            r"\b(statement\s+of\s+account|account\s+statement|transaction\s+(statement|history|details)|statement\s+summary|bank\s+statement)\b",
            re.IGNORECASE,
        )

        records: List[TitleScoreRecord] = []

        for line in lines:
            line_text = line.text.strip()
            line_size = max([s.font_size_pt for s in line.segments] or [10.0])
            line_centre_x = (line.x0 + line.x1) / 2.0

            # 1. Font Size Score: 0 to 40
            font_size_score = (line_size / max_font_size) * 40.0

            # 2. Centering Score: up to 30
            dx = abs(line_centre_x - page_centre_x)
            centering_score = max(0.0, 30.0 - dx * 0.4)

            # 3. Above Table Score: 20
            above_table_score = 20.0 if line.y0 >= table_top_y_pt else 0.0

            # 4. Container / Narrow Column Penalty: -30 if narrow width
            container_penalty = -30.0 if (line.x1 - line.x0) < 0.20 * page_layer.width_pt else 0.0

            # 5. Address / KV Penalty: -50 if address tokens or colons
            has_addr = address_pattern.search(line_text) is not None
            has_colon = ":" in line_text
            address_kv_penalty = -50.0 if (has_addr or has_colon) else 0.0

            # 6. Title Keywords Boost: +30
            has_title_kw = title_keywords.search(line_text) is not None
            title_keywords_boost = 30.0 if has_title_kw else 0.0

            total = (
                font_size_score
                + centering_score
                + above_table_score
                + container_penalty
                + address_kv_penalty
                + title_keywords_boost
            )

            rec = TitleScoreRecord(
                line_id=line.line_id,
                text=line_text,
                font_size_pt=line_size,
                font_size_score=round(font_size_score, 2),
                centering_score=round(centering_score, 2),
                above_table_score=round(above_table_score, 2),
                container_penalty=round(container_penalty, 2),
                address_kv_penalty=round(address_kv_penalty, 2),
                title_keywords_boost=round(title_keywords_boost, 2),
                total_score=round(total, 2),
                is_classified_title=False,
            )
            records.append(rec)

        return records

    def build_header_model(
        self,
        page_layer: PageByteLayer,
        table_top_y_pt: float,
    ) -> HeaderModel:
        header_chars = [
            c for c in page_layer.chars
            if c.origin_device_pt[1] >= table_top_y_pt + 1.0
        ]

        if not header_chars:
            return HeaderModel(
                header_bbox_pt=(36.0, table_top_y_pt, page_layer.width_pt - 36.0, page_layer.height_pt - 36.0),
                blocks=[],
            )

        lines = self._build_lines_from_chars(header_chars)
        if not lines:
            return HeaderModel(
                header_bbox_pt=(36.0, table_top_y_pt, page_layer.width_pt - 36.0, page_layer.height_pt - 36.0),
                blocks=[],
            )

        lines.sort(key=lambda l: l.baseline_y_pt, reverse=True)

        h_x0 = min(l.x0 for l in lines)
        h_y0 = min(l.y0 for l in lines)
        h_x1 = max(l.x1 for l in lines)
        h_y1 = max(l.y1 for l in lines)
        header_bbox = (h_x0, h_y0, h_x1, h_y1)

        # 1. Run Title Scoring Engine
        title_scores = self._score_title_candidates(lines, page_layer, table_top_y_pt)

        title_block: Optional[HeaderBlock] = None
        statement_title_block: Optional[HeaderBlock] = None
        remaining_lines = list(lines)

        title_pattern = re.compile(
            r"\b(statement\s+of\s+account|account\s+statement|transaction\s+(statement|history|details)|statement\s+summary)\b",
            re.IGNORECASE,
        )

        # 2. Check if the top line qualifies as top Document/Full-Width Title
        if remaining_lines:
            first_line = remaining_lines[0]
            first_rec = next((r for r in title_scores if r.line_id == first_line.line_id), None)
            if first_rec and first_rec.total_score >= 45.0 and ":" not in first_line.text and "," not in first_line.text:
                title_block = HeaderBlock(
                    block_id="header_title",
                    block_type=BlockType.TITLE,
                    bbox_pt=first_line.bbox_pt,
                    lines=[first_line],
                    reading_order_rank=1,
                )
                remaining_lines = remaining_lines[1:]
                first_rec.is_classified_title = True

        # 3. Detect Statement Title / Section Subtitle (e.g. "Statement of account" or line close above table)
        for idx, line in enumerate(remaining_lines):
            line_text = line.text.strip()
            if title_pattern.search(line_text) or (
                len(remaining_lines) > 1
                and ":" not in line_text
                and "," not in line_text
                and idx == len(remaining_lines) - 1
                and (line.y0 - table_top_y_pt) < 60.0
            ):
                statement_title_block = HeaderBlock(
                    block_id="statement_title",
                    block_type=BlockType.TITLE,
                    bbox_pt=line.bbox_pt,
                    lines=[line],
                    reading_order_rank=99,
                )
                remaining_lines = [l for i, l in enumerate(remaining_lines) if i != idx]
                for r in title_scores:
                    if r.line_id == line.line_id:
                        r.is_classified_title = True
                break

        # 4. If statement_title is not set and title_block was set right above table, set statement_title
        if statement_title_block is None and title_block is not None and (title_block.bbox_pt[1] - table_top_y_pt) <= 60.0 and len(remaining_lines) > 0:
            statement_title_block = title_block
            statement_title_block.block_id = "statement_title"
            title_block = None

        # 5. Partition Account Details Blocks
        blocks = self._partition_side_by_side_blocks(remaining_lines, header_bbox, start_rank=2 if title_block else 1)

        is_two_block = len(blocks) >= 2
        gutter_w = 0.0
        vert_offset = 0.0
        shared_baselines = 0

        if is_two_block:
            b_left = blocks[0]
            b_right = blocks[1]
            gutter_w = max(0.0, b_right.bbox_pt[0] - b_left.bbox_pt[2])
            vert_offset = abs(b_left.bbox_pt[3] - b_right.bbox_pt[3])

            left_bases = [l.baseline_y_pt for l in b_left.lines]
            right_bases = [l.baseline_y_pt for l in b_right.lines]
            for lb in left_bases:
                if any(abs(lb - rb) <= 1.0 for rb in right_bases):
                    shared_baselines += 1

        # 6. Compute Exact Gap Metrics (Account Details <-> Statement Title <-> Table Top)
        gap_account_to_title = 0.0
        gap_title_to_table = 0.0
        account_to_table_gap = 0.0

        if blocks:
            account_bottom_y = min(b.bbox_pt[1] for b in blocks)
            account_to_table_gap = max(0.0, account_bottom_y - table_top_y_pt)

            if statement_title_block:
                title_top_y = statement_title_block.bbox_pt[3]
                title_bottom_y = statement_title_block.bbox_pt[1]
                gap_account_to_title = max(0.0, account_bottom_y - title_top_y)
                gap_title_to_table = max(0.0, title_bottom_y - table_top_y_pt)

        all_blocks = (
            ([title_block] if title_block else [])
            + blocks
            + ([statement_title_block] if statement_title_block else [])
        )

        return HeaderModel(
            header_bbox_pt=header_bbox,
            blocks=all_blocks,
            is_two_block=is_two_block,
            gutter_width_pt=gutter_w,
            vertical_offset_pt=vert_offset,
            shared_baselines_count=shared_baselines,
            full_width_title=title_block,
            statement_title=statement_title_block,
            gap_account_to_title_pt=gap_account_to_title,
            gap_title_to_table_pt=gap_title_to_table,
            account_to_table_gap_pt=account_to_table_gap,
            title_scores=title_scores,
        )

    def _assemble_segment_text(self, chars: List[PaintedTextChar]) -> str:
        """Assembles character sequence into text, inserting spaces where glyph gap > 0.25 x font space width."""
        if not chars:
            return ""
        tokens = []
        for i, ch in enumerate(chars):
            txt = ch.unicode_text or ch.char_text
            if i > 0:
                prev = chars[i - 1]
                gap = ch.origin_device_pt[0] - prev.font_bbox_device_pt[2]
                space_thresh = max(0.8, 0.0625 * prev.font_size_pt)
                if gap >= space_thresh and not txt.startswith(" ") and not (tokens and tokens[-1].endswith(" ")):
                    tokens.append(" ")
            tokens.append(txt)
        return "".join(tokens)

    def _build_lines_from_chars(self, chars: List[PaintedTextChar], baseline_tol_pt: float = 0.5) -> List[TextLine]:
        sorted_chars = sorted(chars, key=lambda c: c.origin_device_pt[1], reverse=True)
        baseline_groups: List[List[PaintedTextChar]] = []

        for c in sorted_chars:
            placed = False
            for group in baseline_groups:
                if abs(group[0].origin_device_pt[1] - c.origin_device_pt[1]) <= baseline_tol_pt:
                    group.append(c)
                    placed = True
                    break
            if not placed:
                baseline_groups.append([c])

        lines: List[TextLine] = []
        for line_idx, group in enumerate(baseline_groups):
            group.sort(key=lambda c: c.origin_device_pt[0])
            avg_base_y = float(np.mean([c.origin_device_pt[1] for c in group]))

            segments: List[TextSegment] = []
            curr_chars: List[PaintedTextChar] = []

            for i, c in enumerate(group):
                if not curr_chars:
                    curr_chars.append(c)
                else:
                    prev = curr_chars[-1]
                    same_font = (prev.font_name == c.font_name)
                    same_size = abs(prev.font_size_pt - c.font_size_pt) <= 0.5
                    gap = c.font_bbox_device_pt[0] - prev.font_bbox_device_pt[2]
                    large_gap = (gap > max(4.0 * prev.font_size_pt * 0.3, 15.0))

                    if same_font and same_size and not large_gap:
                        curr_chars.append(c)
                    else:
                        seg_text = self._assemble_segment_text(curr_chars)
                        seg_x0 = min(ch.font_bbox_device_pt[0] for ch in curr_chars)
                        seg_y0 = min(ch.font_bbox_device_pt[1] for ch in curr_chars)
                        seg_x1 = max(ch.font_bbox_device_pt[2] for ch in curr_chars)
                        seg_y1 = max(ch.font_bbox_device_pt[3] for ch in curr_chars)

                        is_bold = "bold" in curr_chars[0].font_name.lower() or "black" in curr_chars[0].font_name.lower()
                        is_italic = "italic" in curr_chars[0].font_name.lower() or "oblique" in curr_chars[0].font_name.lower()

                        segments.append(TextSegment(
                            text=seg_text,
                            bbox_pt=(seg_x0, seg_y0, seg_x1, seg_y1),
                            font_name=curr_chars[0].font_name,
                            font_size_pt=curr_chars[0].font_size_pt,
                            is_bold=is_bold,
                            is_italic=is_italic,
                            colour=curr_chars[0].fill_color,
                            chars=list(curr_chars),
                            gap_to_next_pt=gap,
                        ))
                        curr_chars = [c]

            if curr_chars:
                seg_text = self._assemble_segment_text(curr_chars)
                seg_x0 = min(ch.font_bbox_device_pt[0] for ch in curr_chars)
                seg_y0 = min(ch.font_bbox_device_pt[1] for ch in curr_chars)
                seg_x1 = max(ch.font_bbox_device_pt[2] for ch in curr_chars)
                seg_y1 = max(ch.font_bbox_device_pt[3] for ch in curr_chars)

                is_bold = "bold" in curr_chars[0].font_name.lower() or "black" in curr_chars[0].font_name.lower()
                is_italic = "italic" in curr_chars[0].font_name.lower() or "oblique" in curr_chars[0].font_name.lower()

                segments.append(TextSegment(
                    text=seg_text,
                    bbox_pt=(seg_x0, seg_y0, seg_x1, seg_y1),
                    font_name=curr_chars[0].font_name,
                    font_size_pt=curr_chars[0].font_size_pt,
                    is_bold=is_bold,
                    is_italic=is_italic,
                    colour=curr_chars[0].fill_color,
                    chars=list(curr_chars),
                    gap_to_next_pt=0.0,
                ))

            if segments:
                lx0 = min(s.x0 for s in segments)
                ly0 = min(s.y0 for s in segments)
                lx1 = max(s.x1 for s in segments)
                ly1 = max(s.y1 for s in segments)

                lines.append(TextLine(
                    line_id=f"hline_{line_idx + 1}",
                    segments=segments,
                    baseline_y_pt=avg_base_y,
                    bbox_pt=(lx0, ly0, lx1, ly1),
                ))

        return lines

    def _partition_side_by_side_blocks(
        self,
        lines: List[TextLine],
        header_bbox: Tuple[float, float, float, float],
        start_rank: int = 1,
    ) -> List[HeaderBlock]:
        if not lines:
            return []

        total_w = header_bbox[2] - header_bbox[0]
        if total_w < 200.0:
            return [self._create_block("header_block_single", lines, start_rank)]

        # 1. First test if individual lines have side-by-side segments
        mid_x = (header_bbox[0] + header_bbox[2]) / 2.0
        gutter_splits = 0
        for line in lines:
            left_segs = [s for s in line.segments if s.x1 <= mid_x + 60.0]
            right_segs = [s for s in line.segments if s.x0 >= mid_x - 60.0]
            if left_segs and right_segs and (right_segs[0].x0 - left_segs[-1].x1 >= 15.0):
                gutter_splits += 1

        # 2. Also search for a global vertical ink-free gutter across all segments
        all_segments = []
        for line in lines:
            all_segments.extend(line.segments)

        best_gutter_cut: Optional[float] = None
        best_gutter_width = 0.0

        if all_segments:
            # Check candidate cuts across header width
            min_x_bound = header_bbox[0] + 0.20 * total_w
            max_x_bound = header_bbox[0] + 0.80 * total_w
            
            # Find all horizontal gaps between segment endpoints
            sorted_segs = sorted(all_segments, key=lambda s: s.x0)
            for i in range(len(sorted_segs) - 1):
                cur_right = max(s.x1 for s in sorted_segs[:i+1])
                next_left = min(s.x0 for s in sorted_segs[i+1:])
                if min_x_bound <= cur_right < next_left <= max_x_bound:
                    gap_w = next_left - cur_right
                    if gap_w >= 15.0 and gap_w > best_gutter_width:
                        # Verify both sides have at least 1 line
                        left_has = any(s.x1 <= cur_right + 1.0 for s in all_segments)
                        right_has = any(s.x0 >= next_left - 1.0 for s in all_segments)
                        if left_has and right_has:
                            best_gutter_width = gap_w
                            best_gutter_cut = (cur_right + next_left) / 2.0

        if gutter_splits >= 2 or best_gutter_cut is not None:
            cut_x = best_gutter_cut if best_gutter_cut is not None else mid_x
            left_lines: List[TextLine] = []
            right_lines: List[TextLine] = []

            for line in lines:
                left_segs = []
                right_segs = []
                for s in line.segments:
                    if s.x1 <= cut_x + 1.0:
                        left_segs.append(s)
                    elif s.x0 >= cut_x - 1.0:
                        right_segs.append(s)
                    else:
                        # Segment straddles cut_x: assign by centroid
                        if (s.x0 + s.x1) / 2.0 < cut_x:
                            left_segs.append(s)
                        else:
                            right_segs.append(s)

                if left_segs:
                    lx0 = min(s.x0 for s in left_segs)
                    ly0 = min(s.y0 for s in left_segs)
                    lx1 = max(s.x1 for s in left_segs)
                    ly1 = max(s.y1 for s in left_segs)
                    left_lines.append(TextLine(
                        line_id=f"{line.line_id}_left",
                        segments=left_segs,
                        baseline_y_pt=line.baseline_y_pt,
                        bbox_pt=(lx0, ly0, lx1, ly1),
                    ))

                if right_segs:
                    rx0 = min(s.x0 for s in right_segs)
                    ry0 = min(s.y0 for s in right_segs)
                    rx1 = max(s.x1 for s in right_segs)
                    ry1 = max(s.y1 for s in right_segs)
                    right_lines.append(TextLine(
                        line_id=f"{line.line_id}_right",
                        segments=right_segs,
                        baseline_y_pt=line.baseline_y_pt,
                        bbox_pt=(rx0, ry0, rx1, ry1),
                    ))

            blocks = []
            if left_lines:
                blocks.append(self._create_block("header_block_left", left_lines, start_rank))
            if right_lines:
                blocks.append(self._create_block("header_block_right", right_lines, start_rank + 1))
            return blocks
        else:
            return [self._create_block("header_block_single", lines, start_rank)]

    def _create_block(self, block_id: str, lines: List[TextLine], rank: int) -> HeaderBlock:
        lines.sort(key=lambda l: l.baseline_y_pt, reverse=True)

        bx0 = min(l.x0 for l in lines)
        by0 = min(l.y0 for l in lines)
        bx1 = max(l.x1 for l in lines)
        by1 = max(l.y1 for l in lines)

        pitches: List[float] = []
        for i in range(len(lines) - 1):
            p = abs(lines[i].baseline_y_pt - lines[i + 1].baseline_y_pt)
            pitches.append(p)

        mean_pitch = float(np.mean(pitches)) if pitches else 0.0
        std_pitch = float(np.std(pitches)) if pitches else 0.0

        kv_grid = self.kv_engine.extract_kv_grid(lines, grid_id=f"kv_{block_id}")

        if kv_grid and kv_grid.is_valid_grid and kv_grid.rows_count >= 3 and kv_grid.value_axis_x_pt is not None:
            b_type = BlockType.KV_GRID
        elif kv_grid and len(kv_grid.entries) >= 1 and any(e.separator_type != "free_pair" for e in kv_grid.entries):
            b_type = BlockType.INLINE_PAIRS
        else:
            b_type = BlockType.FREE_TEXT_LIST

        return HeaderBlock(
            block_id=block_id,
            block_type=b_type,
            bbox_pt=(bx0, by0, bx1, by1),
            lines=lines,
            kv_grid=kv_grid,
            mean_pitch_pt=mean_pitch,
            std_pitch_pt=std_pitch,
            pitch_list_pt=pitches,
            reading_order_rank=rank,
        )
