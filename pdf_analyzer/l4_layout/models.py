"""
L4 Layout Models & Data Structures.
Defines immutable representations for LayoutTree, LayoutNode, TextSegment, TextLine,
KVEntry, KVGrid, HeaderModel, FooterModel, MarginsModel, LogoModel, ContentAccounting,
and TitleScoreRecord for Title classification scoring (Phase 8B Task 4).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any, Set
from enum import Enum

from pdf_analyzer.l0_bytes.primitives import PaintedTextChar, PaintedPath, Color


class RegionType(str, Enum):
    PAGE = "page"
    MARGINS = "margins"
    HEADER = "header"
    TABLE = "table"
    FOOTER = "footer"
    SIDEBAR = "sidebar"
    CONTAINER = "container"
    UNCLASSIFIED = "unclassified"


class BlockType(str, Enum):
    FREE_TEXT_LIST = "free_text_list"
    KV_GRID = "kv_grid"
    INLINE_PAIRS = "inline_pairs"
    TITLE = "title"
    NOTE = "note"
    SUMMARY_LINE = "summary_line"
    PAGE_NUMBER = "page_number"
    DISCLAIMER = "disclaimer"


@dataclass
class TitleScoreRecord:
    line_id: str
    text: str
    font_size_pt: float
    font_size_score: float
    centering_score: float
    above_table_score: float
    container_penalty: float
    address_kv_penalty: float
    title_keywords_boost: float
    total_score: float
    is_classified_title: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_id": self.line_id,
            "text": self.text,
            "font_size_pt": self.font_size_pt,
            "font_size_score": self.font_size_score,
            "centering_score": self.centering_score,
            "above_table_score": self.above_table_score,
            "container_penalty": self.container_penalty,
            "address_kv_penalty": self.address_kv_penalty,
            "title_keywords_boost": self.title_keywords_boost,
            "total_score": self.total_score,
            "is_classified_title": self.is_classified_title,
        }


@dataclass
class TextSegment:
    text: str
    bbox_pt: Tuple[float, float, float, float]
    font_name: str
    font_size_pt: float
    is_bold: bool = False
    is_italic: bool = False
    colour: Optional[Color] = None
    chars: List[PaintedTextChar] = field(default_factory=list)
    gap_to_next_pt: float = 0.0

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

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "bbox_pt": list(self.bbox_pt),
            "font_name": self.font_name,
            "font_size_pt": self.font_size_pt,
            "is_bold": self.is_bold,
            "is_italic": self.is_italic,
            "colour": self.colour.to_dict() if self.colour else None,
            "gap_to_next_pt": self.gap_to_next_pt,
            "chars_count": len(self.chars),
        }


@dataclass
class TextLine:
    line_id: str
    segments: List[TextSegment] = field(default_factory=list)
    baseline_y_pt: float = 0.0
    bbox_pt: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments if s.text)

    @property
    def chars(self) -> List[PaintedTextChar]:
        res = []
        for s in self.segments:
            res.extend(s.chars)
        return res

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_id": self.line_id,
            "text": self.text,
            "baseline_y_pt": self.baseline_y_pt,
            "bbox_pt": list(self.bbox_pt),
            "segments": [s.to_dict() for s in self.segments],
        }


@dataclass
class KVEntry:
    key_text: str
    value_text: Optional[str]
    key_bbox_pt: Tuple[float, float, float, float]
    value_bbox_pt: Optional[Tuple[float, float, float, float]]
    separator_type: str
    value_start_x_pt: Optional[float] = None
    jitter_pt: float = 0.0
    numeric_value: Optional[float] = None
    suffix: Optional[str] = None
    continuation_lines: List[str] = field(default_factory=list)
    sub_pairs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_text": self.key_text,
            "value_text": self.value_text,
            "key_bbox_pt": list(self.key_bbox_pt),
            "value_bbox_pt": list(self.value_bbox_pt) if self.value_bbox_pt else None,
            "separator_type": self.separator_type,
            "value_start_x_pt": self.value_start_x_pt,
            "jitter_pt": self.jitter_pt,
            "numeric_value": self.numeric_value,
            "suffix": self.suffix,
            "continuation_lines": self.continuation_lines,
            "sub_pairs": self.sub_pairs,
        }


@dataclass
class KVGrid:
    grid_id: str
    entries: List[KVEntry] = field(default_factory=list)
    value_axis_x_pt: Optional[float] = None
    label_left_x_pt: Optional[float] = None
    max_jitter_pt: float = 0.0
    rows_count: int = 0
    is_valid_grid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grid_id": self.grid_id,
            "value_axis_x_pt": self.value_axis_x_pt,
            "label_left_x_pt": self.label_left_x_pt,
            "max_jitter_pt": self.max_jitter_pt,
            "rows_count": len(self.entries),
            "is_valid_grid": self.is_valid_grid,
            "entries": [e.to_dict() for e in self.entries],
        }


@dataclass
class HeaderBlock:
    block_id: str
    block_type: BlockType
    bbox_pt: Tuple[float, float, float, float]
    lines: List[TextLine] = field(default_factory=list)
    kv_grid: Optional[KVGrid] = None
    mean_pitch_pt: float = 0.0
    std_pitch_pt: float = 0.0
    pitch_list_pt: List[float] = field(default_factory=list)
    reading_order_rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_type": self.block_type.value,
            "bbox_pt": list(self.bbox_pt),
            "lines_count": len(self.lines),
            "lines": [l.to_dict() for l in self.lines],
            "kv_grid": self.kv_grid.to_dict() if self.kv_grid else None,
            "mean_pitch_pt": self.mean_pitch_pt,
            "std_pitch_pt": self.std_pitch_pt,
            "pitch_list_pt": self.pitch_list_pt,
            "reading_order_rank": self.reading_order_rank,
        }


@dataclass
class HeaderModel:
    header_bbox_pt: Tuple[float, float, float, float]
    blocks: List[HeaderBlock] = field(default_factory=list)
    is_two_block: bool = False
    gutter_width_pt: float = 0.0
    vertical_offset_pt: float = 0.0
    shared_baselines_count: int = 0
    full_width_title: Optional[HeaderBlock] = None
    statement_title: Optional[HeaderBlock] = None
    gap_account_to_title_pt: float = 0.0
    gap_title_to_table_pt: float = 0.0
    account_to_table_gap_pt: float = 0.0
    title_scores: List[TitleScoreRecord] = field(default_factory=list)

    @property
    def bbox_pt(self) -> Tuple[float, float, float, float]:
        return self.header_bbox_pt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "header_bbox_pt": list(self.header_bbox_pt),
            "is_two_block": self.is_two_block,
            "gutter_width_pt": self.gutter_width_pt,
            "vertical_offset_pt": self.vertical_offset_pt,
            "shared_baselines_count": self.shared_baselines_count,
            "blocks_count": len(self.blocks),
            "full_width_title": self.full_width_title.to_dict() if self.full_width_title else None,
            "statement_title": self.statement_title.to_dict() if self.statement_title else None,
            "gap_account_to_title_pt": self.gap_account_to_title_pt,
            "gap_title_to_table_pt": self.gap_title_to_table_pt,
            "account_to_table_gap_pt": self.account_to_table_gap_pt,
            "title_scores": [ts.to_dict() for ts in self.title_scores],
            "blocks": [b.to_dict() for b in self.blocks],
        }


@dataclass
class FooterModel:
    footer_bbox_pt: Tuple[float, float, float, float]
    blocks: List[HeaderBlock] = field(default_factory=list)
    page_number_text: Optional[str] = None
    page_number_bbox_pt: Optional[Tuple[float, float, float, float]] = None
    is_pinned: bool = True
    gap_table_ink_to_footer_ink_pt: float = 0.0
    gap_table_border_to_footer_ink_pt: float = 0.0
    gap_footer_ink_to_page_bottom_pt: float = 0.0

    @property
    def bbox_pt(self) -> Tuple[float, float, float, float]:
        return self.footer_bbox_pt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "footer_bbox_pt": list(self.footer_bbox_pt),
            "blocks_count": len(self.blocks),
            "page_number_text": self.page_number_text,
            "page_number_bbox_pt": list(self.page_number_bbox_pt) if self.page_number_bbox_pt else None,
            "is_pinned": self.is_pinned,
            "gap_table_ink_to_footer_ink_pt": self.gap_table_ink_to_footer_ink_pt,
            "gap_table_border_to_footer_ink_pt": self.gap_table_border_to_footer_ink_pt,
            "gap_footer_ink_to_page_bottom_pt": self.gap_footer_ink_to_page_bottom_pt,
            "blocks": [b.to_dict() for b in self.blocks],
        }


@dataclass
class MarginsModel:
    left_margin_pt: float
    right_margin_pt: float
    top_margin_pt: float
    bottom_margin_pt: float
    left_source: str = "content_ink"
    right_source: str = "content_ink"
    top_source: str = "content_ink"
    bottom_source: str = "content_ink"
    text_only_margins_pt: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left_margin_pt": self.left_margin_pt,
            "right_margin_pt": self.right_margin_pt,
            "top_margin_pt": self.top_margin_pt,
            "bottom_margin_pt": self.bottom_margin_pt,
            "sources": {
                "left": self.left_source,
                "right": self.right_source,
                "top": self.top_source,
                "bottom": self.bottom_source,
            },
            "text_only_margins_pt": list(self.text_only_margins_pt),
        }


@dataclass
class LogoModel:
    logo_id: str
    bbox_pt: Tuple[float, float, float, float]
    effective_dpi: float
    caption_text: Optional[str] = None
    offset_to_left_margin_pt: float = 0.0
    offset_to_top_margin_pt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logo_id": self.logo_id,
            "bbox_pt": list(self.bbox_pt),
            "effective_dpi": self.effective_dpi,
            "caption_text": self.caption_text,
            "offset_to_left_margin_pt": self.offset_to_left_margin_pt,
            "offset_to_top_margin_pt": self.offset_to_top_margin_pt,
        }


@dataclass
class LayoutNode:
    node_id: str
    region_type: RegionType
    bbox_pt: Tuple[float, float, float, float]
    children: List[LayoutNode] = field(default_factory=list)
    chars: List[PaintedTextChar] = field(default_factory=list)
    paths: List[PaintedPath] = field(default_factory=list)
    container_id: Optional[str] = None
    header_model: Optional[HeaderModel] = None
    footer_model: Optional[FooterModel] = None
    block: Optional[HeaderBlock] = None

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "region_type": self.region_type.value,
            "bbox_pt": list(self.bbox_pt),
            "is_leaf": self.is_leaf,
            "chars_count": len(self.chars),
            "paths_count": len(self.paths),
            "container_id": self.container_id,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class LayoutTree:
    page_number: int
    root: LayoutNode
    orphans_count: int = 0
    invariants_passed: bool = True
    invariant_violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "orphans_count": self.orphans_count,
            "invariants_passed": self.invariants_passed,
            "invariant_violations": self.invariant_violations,
            "root": self.root.to_dict(),
        }


@dataclass
class AccountingReport:
    total_chars: int
    accounted_chars: int
    orphan_chars_count: int
    invisible_chars_count: int
    residual_ink_pct: float
    residual_ink_passed: bool
    unclassified_ink_boxes: List[Tuple[float, float, float, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chars": self.total_chars,
            "accounted_chars": self.accounted_chars,
            "orphan_chars_count": self.orphan_chars_count,
            "invisible_chars_count": self.invisible_chars_count,
            "residual_ink_pct": self.residual_ink_pct,
            "residual_ink_passed": self.residual_ink_passed,
            "unclassified_ink_boxes_count": len(self.unclassified_ink_boxes),
        }
