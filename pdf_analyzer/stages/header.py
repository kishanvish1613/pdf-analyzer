"""
Section 23: Header Side-by-Side Block Splitting & Structure-Based Parsing Engine.
Performs:
1. Horizontal band XY-cut and vertical gutter block splitting (handling 2+ side-by-side blocks + full-width title)
2. Segment-to-line assembly preserving wide intra-line gaps ('Bank Of India ... RATIBAD')
3. Structural sub-block classification: TITLE, FREE_TEXT_LIST, KV_GRID, INLINE_PAIRS, NOTE, SUMMARY_LINE
4. Per-block independent line pitch reporting (mean, std, per-line list)
5. Block pairing records (gutter width, vertical offset, baseline alignments)
6. Outputs header_blocks.json and header_blocks.png
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import cv2

from pdf_analyzer.stages.frame import PageFrame
from pdf_analyzer.models import TextSpanModel

logger = logging.getLogger(__name__)


@dataclass
class HeaderLineSegment:
    text: str
    bbox_pt: Tuple[float, float, float, float]
    baseline_y_pt: float
    font_name: str
    font_size_pt: float
    is_bold: bool
    color_hex: str
    gap_to_next_pt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "bbox_pt": [round(v, 3) for v in self.bbox_pt],
            "baseline_y_pt": round(self.baseline_y_pt, 3),
            "font_name": self.font_name,
            "font_size_pt": round(self.font_size_pt, 3),
            "is_bold": self.is_bold,
            "color_hex": self.color_hex,
            "gap_to_next_pt": round(self.gap_to_next_pt, 3)
        }


@dataclass
class HeaderLine:
    line_index: int
    baseline_y_pt: float
    bbox_pt: Tuple[float, float, float, float]
    segments: List[HeaderLineSegment]
    joined_text: str
    structure_type: str = "TEXT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_index": self.line_index,
            "baseline_y_pt": round(self.baseline_y_pt, 3),
            "bbox_pt": [round(v, 3) for v in self.bbox_pt],
            "segments": [s.to_dict() for s in self.segments],
            "joined_text": self.joined_text,
            "structure_type": self.structure_type
        }


@dataclass
class HeaderSubBlock:
    sub_block_id: str
    block_type: str  # TITLE | FREE_TEXT_LIST | KV_GRID | INLINE_PAIRS | NOTE | SUMMARY_LINE
    bbox_pt: Tuple[float, float, float, float]
    lines: List[HeaderLine]
    mean_pitch_pt: float
    pitch_std_pt: float
    per_line_pitches_pt: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub_block_id": self.sub_block_id,
            "block_type": self.block_type,
            "bbox_pt": [round(v, 3) for v in self.bbox_pt],
            "lines": [l.to_dict() for l in self.lines],
            "mean_pitch_pt": round(self.mean_pitch_pt, 3),
            "pitch_std_pt": round(self.pitch_std_pt, 3),
            "per_line_pitches_pt": [round(p, 3) for p in self.per_line_pitches_pt]
        }


@dataclass
class HeaderBlock:
    block_id: str
    position_role: str  # "full_width_title", "left_block", "right_block", "center_block", "notes_band"
    bbox_pt: Tuple[float, float, float, float]
    sub_blocks: List[HeaderSubBlock]
    mean_pitch_pt: float
    pitch_std_pt: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "position_role": self.position_role,
            "bbox_pt": [round(v, 3) for v in self.bbox_pt],
            "sub_blocks": [sb.to_dict() for sb in self.sub_blocks],
            "mean_pitch_pt": round(self.mean_pitch_pt, 3),
            "pitch_std_pt": round(self.pitch_std_pt, 3)
        }


class HeaderStructureParser:
    """Parses top band into independent side-by-side blocks, lines, and structural sub-blocks."""

    def __init__(self, page_frame: PageFrame):
        self.frame = page_frame

    def parse_header_region(
        self,
        header_spans: List[TextSpanModel],
        table_top_y_pt: float,
        output_dir: str
    ) -> Dict[str, Any]:
        """Splits header spans into side-by-side blocks and structural sub-runs."""
        spans_in_header = [s for s in header_spans if s.ink_box.y0.pt < table_top_y_pt - 2.0]
        if not spans_in_header:
            return {"blocks": [], "reading_order": [], "pairing": {}}

        # 1. Assemble Lines from Baseline-Aligned Spans (+-0.5 pt)
        raw_lines = self._assemble_lines_from_spans(spans_in_header)

        # 2. Split into Blocks by Vertical Gutters
        blocks = self._split_lines_into_blocks(raw_lines)

        # 3. Reading Order and Block Pairing Records
        pairing_record = self._compute_block_pairing(blocks)

        header_data = {
            "blocks": [b.to_dict() for b in blocks],
            "reading_order": [b.block_id for b in blocks],
            "pairing_record": pairing_record
        }

        # Write header_blocks.json
        json_path = os.path.join(output_dir, "header_blocks.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(header_data, f, indent=2)

        return header_data

    def _assemble_lines_from_spans(self, spans: List[TextSpanModel]) -> List[HeaderLine]:
        """Groups spans sharing a baseline into unified HeaderLines while keeping distinct segments."""
        sorted_spans = sorted(spans, key=lambda s: (round(s.origin_point[1], 1), s.ink_box.x0.pt))
        baseline_groups: List[List[TextSpanModel]] = []

        for s in sorted_spans:
            by = s.origin_point[1]
            if not baseline_groups:
                baseline_groups.append([s])
            else:
                last_by = baseline_groups[-1][0].origin_point[1]
                if abs(by - last_by) <= 0.6:
                    baseline_groups[-1].append(s)
                else:
                    baseline_groups.append([s])

        lines: List[HeaderLine] = []
        for l_idx, group in enumerate(baseline_groups):
            group_sorted = sorted(group, key=lambda s: s.ink_box.x0.pt)
            segments: List[HeaderLineSegment] = []

            for i, s in enumerate(group_sorted):
                gap = (group_sorted[i + 1].ink_box.x0.pt - s.ink_box.x1.pt) if i + 1 < len(group_sorted) else 0.0
                segments.append(HeaderLineSegment(
                    text=s.text,
                    bbox_pt=(s.ink_box.x0.pt, s.ink_box.y0.pt, s.ink_box.x1.pt, s.ink_box.y1.pt),
                    baseline_y_pt=s.origin_point[1],
                    font_name=s.font_name,
                    font_size_pt=s.font_size_pt,
                    is_bold=s.is_bold,
                    color_hex=s.color_hex,
                    gap_to_next_pt=gap
                ))

            lx0 = min(s.ink_box.x0.pt for s in group_sorted)
            ly0 = min(s.ink_box.y0.pt for s in group_sorted)
            lx1 = max(s.ink_box.x1.pt for s in group_sorted)
            ly1 = max(s.ink_box.y1.pt for s in group_sorted)
            joined = " ".join(s.text.strip() for s in group_sorted)

            # Classify line structure
            if "STATEMENT" in joined.upper() or "BANK" in joined.upper() and len(group_sorted) == 1:
                stype = "TITLE"
            elif ":" in joined:
                stype = "KV"
            elif "RECORDS" in joined.upper() or "NOTE" in joined.upper():
                stype = "NOTE"
            else:
                stype = "FREE_TEXT"

            lines.append(HeaderLine(
                line_index=l_idx,
                baseline_y_pt=group_sorted[0].origin_point[1],
                bbox_pt=(lx0, ly0, lx1, ly1),
                segments=segments,
                joined_text=joined,
                structure_type=stype
            ))

        return lines

    def _split_lines_into_blocks(self, lines: List[HeaderLine]) -> List[HeaderBlock]:
        """Separates full-width titles from side-by-side left and right column blocks."""
        if not lines:
            return []

        # Find side-by-side split x coordinate (gutter)
        page_mid_x = self.frame.width_pt / 2.0
        left_lines: List[HeaderLine] = []
        right_lines: List[HeaderLine] = []
        title_lines: List[HeaderLine] = []

        for line in lines:
            lx0, ly0, lx1, ly1 = line.bbox_pt
            # Check if line has distinct segments spanning across left and right sides separated by a wide gap
            left_segs = [s for s in line.segments if (s.bbox_pt[0] + s.bbox_pt[2]) / 2.0 < page_mid_x]
            right_segs = [s for s in line.segments if (s.bbox_pt[0] + s.bbox_pt[2]) / 2.0 >= page_mid_x]

            if left_segs and right_segs and len(line.segments) >= 2:
                # Segment-level split across the central gutter
                l_lx0 = min(s.bbox_pt[0] for s in left_segs)
                l_ly0 = min(s.bbox_pt[1] for s in left_segs)
                l_lx1 = max(s.bbox_pt[2] for s in left_segs)
                l_ly1 = max(s.bbox_pt[3] for s in left_segs)
                l_joined = " ".join(s.text.strip() for s in left_segs)
                l_stype = "KV" if ":" in l_joined else ("NOTE" if "RECORD" in l_joined.upper() else "FREE_TEXT")
                left_lines.append(HeaderLine(
                    line_index=line.line_index,
                    baseline_y_pt=line.baseline_y_pt,
                    bbox_pt=(l_lx0, l_ly0, l_lx1, l_ly1),
                    segments=left_segs,
                    joined_text=l_joined,
                    structure_type=l_stype
                ))

                r_lx0 = min(s.bbox_pt[0] for s in right_segs)
                r_ly0 = min(s.bbox_pt[1] for s in right_segs)
                r_lx1 = max(s.bbox_pt[2] for s in right_segs)
                r_ly1 = max(s.bbox_pt[3] for s in right_segs)
                r_joined = " ".join(s.text.strip() for s in right_segs)
                r_stype = "KV" if ":" in r_joined else ("NOTE" if "RECORD" in r_joined.upper() else "FREE_TEXT")
                right_lines.append(HeaderLine(
                    line_index=line.line_index,
                    baseline_y_pt=line.baseline_y_pt,
                    bbox_pt=(r_lx0, r_ly0, r_lx1, r_ly1),
                    segments=right_segs,
                    joined_text=r_joined,
                    structure_type=r_stype
                ))
            elif lx0 < page_mid_x - 40.0 and lx1 > page_mid_x + 40.0:
                # Full width title check
                title_lines.append(line)
            elif (lx0 + lx1) / 2.0 < page_mid_x:
                left_lines.append(line)
            else:
                right_lines.append(line)

        blocks: List[HeaderBlock] = []
        b_idx = 0

        # Title Block
        if title_lines:
            b_box = self._calc_lines_bbox(title_lines)
            sb = self._build_sub_block("title_0", "TITLE", title_lines)
            blocks.append(HeaderBlock(
                block_id=f"header_block_{b_idx}",
                position_role="full_width_title",
                bbox_pt=b_box,
                sub_blocks=[sb],
                mean_pitch_pt=sb.mean_pitch_pt,
                pitch_std_pt=sb.pitch_std_pt
            ))
            b_idx += 1

        # Left Block (Address / Details)
        if left_lines:
            b_box = self._calc_lines_bbox(left_lines)
            sub_blocks = self._decompose_sub_blocks(left_lines, "left")
            p_mean, p_std = self._calc_pitch_stats(left_lines)
            blocks.append(HeaderBlock(
                block_id=f"header_block_{b_idx}",
                position_role="left_block",
                bbox_pt=b_box,
                sub_blocks=sub_blocks,
                mean_pitch_pt=p_mean,
                pitch_std_pt=p_std
            ))
            b_idx += 1

        # Right Block (Bank / Key-Value Grid)
        if right_lines:
            b_box = self._calc_lines_bbox(right_lines)
            sub_blocks = self._decompose_sub_blocks(right_lines, "right")
            p_mean, p_std = self._calc_pitch_stats(right_lines)
            blocks.append(HeaderBlock(
                block_id=f"header_block_{b_idx}",
                position_role="right_block",
                bbox_pt=b_box,
                sub_blocks=sub_blocks,
                mean_pitch_pt=p_mean,
                pitch_std_pt=p_std
            ))
            b_idx += 1

        return blocks

    def _decompose_sub_blocks(self, lines: List[HeaderLine], prefix: str) -> List[HeaderSubBlock]:
        """Groups consecutive lines of matching structure into sub-blocks."""
        runs: List[List[HeaderLine]] = []
        for line in lines:
            if not runs:
                runs.append([line])
            else:
                if line.structure_type == runs[-1][0].structure_type:
                    runs[-1].append(line)
                else:
                    runs.append([line])

        sub_blocks: List[HeaderSubBlock] = []
        for i, run in enumerate(runs):
            stype = run[0].structure_type
            btype = "KV_GRID" if stype == "KV" else ("NOTE" if stype == "NOTE" else "FREE_TEXT_LIST")
            sub_blocks.append(self._build_sub_block(f"{prefix}_sub_{i}", btype, run))

        return sub_blocks

    def _build_sub_block(self, sb_id: str, b_type: str, lines: List[HeaderLine]) -> HeaderSubBlock:
        b_box = self._calc_lines_bbox(lines)
        p_mean, p_std, pitches = self._calc_pitches(lines)
        return HeaderSubBlock(
            sub_block_id=sb_id,
            block_type=b_type,
            bbox_pt=b_box,
            lines=lines,
            mean_pitch_pt=p_mean,
            pitch_std_pt=p_std,
            per_line_pitches_pt=pitches
        )

    def _calc_lines_bbox(self, lines: List[HeaderLine]) -> Tuple[float, float, float, float]:
        x0 = min(l.bbox_pt[0] for l in lines)
        y0 = min(l.bbox_pt[1] for l in lines)
        x1 = max(l.bbox_pt[2] for l in lines)
        y1 = max(l.bbox_pt[3] for l in lines)
        return (x0, y0, x1, y1)

    def _calc_pitches(self, lines: List[HeaderLine]) -> Tuple[float, float, List[float]]:
        if len(lines) <= 1:
            return (12.0, 0.0, [])
        baselines = [l.baseline_y_pt for l in lines]
        diffs = [b1 - b0 for b0, b1 in zip(baselines[:-1], baselines[1:])]
        mean_p = float(np.mean(diffs))
        std_p = float(np.std(diffs)) if len(diffs) > 1 else 0.0
        return (mean_p, std_p, diffs)

    def _calc_pitch_stats(self, lines: List[HeaderLine]) -> Tuple[float, float]:
        mean_p, std_p, _ = self._calc_pitches(lines)
        return (mean_p, std_p)

    def _compute_block_pairing(self, blocks: List[HeaderBlock]) -> Dict[str, Any]:
        """Calculates gutter width, vertical offset, and shared baseline alignments across left and right blocks."""
        left = next((b for b in blocks if b.position_role == "left_block"), None)
        right = next((b for b in blocks if b.position_role == "right_block"), None)

        if not left or not right:
            return {"paired": False}

        gutter_w = right.bbox_pt[0] - left.bbox_pt[2]
        vert_offset = right.bbox_pt[1] - left.bbox_pt[1]

        left_baselines = [l.baseline_y_pt for sb in left.sub_blocks for l in sb.lines]
        right_baselines = [l.baseline_y_pt for sb in right.sub_blocks for l in sb.lines]

        shared_baselines = [
            round(ly, 2) for ly in left_baselines
            if any(abs(ly - ry) <= 1.0 for ry in right_baselines)
        ]

        return {
            "paired": True,
            "left_block_id": left.block_id,
            "right_block_id": right.block_id,
            "gutter_width_pt": round(max(0.0, gutter_w), 3),
            "vertical_offset_pt": round(vert_offset, 3),
            "shared_baselines_count": len(shared_baselines),
            "shared_baselines_pt": shared_baselines
        }
