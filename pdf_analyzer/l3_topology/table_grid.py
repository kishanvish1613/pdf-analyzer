"""
Table Grid & Multi-Style Column / Row Reconstruction Engine (Phase 8C Tasks 1, 2, 4, 5).
Recovers table grids for all 6 table styles:
- full_grid: Complete vertical and horizontal vector rule grid
- vertical_only: Vertical rules present, horizontal rules absent / sparse
- horizontal_only: Horizontal rules present, vertical rules absent (e.g. Kotak)
- filled_header: Filled header background band / cell rects present (e.g. SBI, Kotak)
- borderless: No rules or header fills
- empty_table: Table header with 0 body rows or empty body with single rule (e.g. HDFC last page)

Virtual Column Extraction in strict priority:
(a) Tagged Structure Tree TH/TD geometry
(b) Filled header cells (fill rects) and header text boxes
(c) Stream-order cell grouping
(d) Alignment evidence: right-aligned numeric tokens and left-aligned text tokens (tolerance 0.5 pt)
    plus ink-free vertical gutters asserted across ALL body rows.

Band typing: TABLE_TITLE_BAND, HEADER, OPENING_BALANCE, BODY, EMPTY_BAND, CLOSING.
"""

from __future__ import annotations
import os
import math
import re
import logging
import click
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

logger = logging.getLogger(__name__)
import numpy as np
from shapely.geometry import box as shapely_box, LineString
from shapely.strtree import STRtree

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, PaintedPath
from pdf_analyzer.l2_primitives.ruleset import Rule, RuleSet
from pdf_analyzer.l3_topology.logical_rows import LogicalRowEngine, CLOSING_PATTERNS


class TableStyleVerdict(str, Enum):
    FULL_GRID = "full_grid"
    VERTICAL_ONLY = "vertical_only"
    HORIZONTAL_ONLY = "horizontal_only"
    FILLED_HEADER = "filled_header"
    ROW_BANDS_ONLY = "row_bands_only"
    UNRULED = "unruled"
    BORDERLESS = "borderless"
    EMPTY_TABLE = "empty_table"


class RowBandType(str, Enum):
    TABLE_TITLE_BAND = "TABLE_TITLE_BAND"
    HEADER = "HEADER"
    OPENING_BALANCE = "OPENING_BALANCE"
    BODY = "BODY"
    EMPTY_BAND = "EMPTY_BAND"
    CLOSING = "CLOSING"


@dataclass
class ColumnBoundary:
    rule_id: str
    centre_x_pt: float
    width_pt: float
    span_y0_pt: float
    span_y1_pt: float
    coverage_pct: float
    is_virtual: bool = False
    evidence: List[str] = field(default_factory=list)
    boundary_source: str = "vector_rule"  # 'vector_rule' | 'header_fill' | 'ink_gutter' | 'projection_profile' | 'alignment_edge'
    fill_edge_pt: Optional[float] = None
    ink_midpoint_pt: Optional[float] = None
    delta_fill_vs_ink_pt: Optional[float] = None
    gap_left_pt: Optional[float] = None
    gap_right_pt: Optional[float] = None
    nearest_ink_dist_pt: Optional[float] = None
    flagged_tight_ink: bool = False
    confidence: float = 1.0
    confidence_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "rule_id": self.rule_id,
            "centre_x_pt": self.centre_x_pt,
            "width_pt": self.width_pt,
            "span_y0_pt": self.span_y0_pt,
            "span_y1_pt": self.span_y1_pt,
            "coverage_pct": self.coverage_pct,
            "is_virtual": self.is_virtual,
            "evidence": self.evidence,
            "boundary_source": self.boundary_source,
            "flagged_tight_ink": self.flagged_tight_ink,
            "confidence": round(self.confidence, 3),
            "confidence_reasons": self.confidence_reasons,
        }
        if self.fill_edge_pt is not None:
            d["fill_edge_pt"] = self.fill_edge_pt
        if self.ink_midpoint_pt is not None:
            d["ink_midpoint_pt"] = self.ink_midpoint_pt
        if self.delta_fill_vs_ink_pt is not None:
            d["delta_fill_vs_ink_pt"] = self.delta_fill_vs_ink_pt
        if self.gap_left_pt is not None:
            d["gap_left_pt"] = self.gap_left_pt
        if self.gap_right_pt is not None:
            d["gap_right_pt"] = self.gap_right_pt
        if self.nearest_ink_dist_pt is not None:
            d["nearest_ink_dist_pt"] = self.nearest_ink_dist_pt
        return d


@dataclass
class ColumnModel:
    index: int
    x0_pt: float
    x1_pt: float
    width_pt: float
    left_rule_id: str
    right_rule_id: str
    header_text: Optional[str] = None
    alignment: str = "left"  # 'left' | 'right' | 'center'
    is_numeric: bool = False
    evidence: List[str] = field(default_factory=list)
    header_source: str = "text"  # 'text' | 'inferred' | 'non_text'
    header_text_suggested: Optional[str] = None
    header_span_of: Optional[int] = None
    header_baselines: List[float] = field(default_factory=list)
    header_span_ids: List[str] = field(default_factory=list)
    header_confidence: float = 1.0
    header_bbox_pt: Optional[Tuple[float, float, float, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "column_index": self.index,
            "x0_pt": self.x0_pt,
            "x1_pt": self.x1_pt,
            "width_pt": self.width_pt,
            "header_text": self.header_text,
            "alignment": self.alignment,
            "is_numeric": self.is_numeric,
            "evidence": self.evidence,
            "left_rule_id": self.left_rule_id,
            "right_rule_id": self.right_rule_id,
            "header_source": self.header_source,
            "header_text_suggested": self.header_text_suggested,
            "header_span_of": self.header_span_of,
            "header_baselines": self.header_baselines,
            "header_span_ids": self.header_span_ids,
            "header_confidence": round(self.header_confidence, 3),
            "header_bbox_pt": list(self.header_bbox_pt) if self.header_bbox_pt else None,
        }


@dataclass
class HeaderSpan:
    span_id: str
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

    @property
    def center_x(self) -> float:
        return (self.bbox_pt[0] + self.bbox_pt[2]) / 2.0


@dataclass
class RowModel:
    index: int
    y0_pt: float
    y1_pt: float
    height_pt: float
    is_header: bool = False
    row_type: RowBandType = RowBandType.BODY
    lines_count: int = 1
    pitch_pt: float = 0.0
    text_content: str = ""
    top_rule_id: Optional[str] = None
    bottom_rule_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "row_index": self.index,
            "y0_pt": self.y0_pt,
            "y1_pt": self.y1_pt,
            "height_pt": self.height_pt,
            "is_header": self.is_header,
            "row_type": self.row_type.value,
            "lines_count": self.lines_count,
            "pitch_pt": self.pitch_pt,
            "text_content": self.text_content,
            "top_rule_id": self.top_rule_id,
            "bottom_rule_id": self.bottom_rule_id,
        }


@dataclass
class TableGrid:
    table_bbox_pt: Tuple[float, float, float, float]
    columns: List[ColumnModel] = field(default_factory=list)
    rows: List[RowModel] = field(default_factory=list)
    boundaries: List[ColumnBoundary] = field(default_factory=list)
    is_borderless: bool = False
    outer_width_pt: float = 0.0
    outer_height_pt: float = 0.0
    sum_column_widths_pt: float = 0.0
    contiguity_passed: bool = True
    table_style_chosen: str = "full_grid"
    table_style_runner_up: str = "vertical_only"
    unused_qualifying_rules: List[str] = field(default_factory=list)
    table_confidence: float = 1.0
    confidence_reasons: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.outer_width_pt == 0.0 and self.table_bbox_pt[2] > self.table_bbox_pt[0]:
            self.outer_width_pt = self.table_bbox_pt[2] - self.table_bbox_pt[0]
        if self.outer_height_pt == 0.0 and self.table_bbox_pt[3] > self.table_bbox_pt[1]:
            self.outer_height_pt = self.table_bbox_pt[3] - self.table_bbox_pt[1]
        if self.sum_column_widths_pt == 0.0 and self.columns:
            self.sum_column_widths_pt = sum(c.width_pt for c in self.columns)

    @property
    def bbox_pt(self) -> Tuple[float, float, float, float]:
        return self.table_bbox_pt

    @property
    def column_boundaries(self) -> List[ColumnBoundary]:
        return self.boundaries

    @property
    def body_rows_count(self) -> int:
        return sum(1 for r in self.rows if r.row_type == RowBandType.BODY)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_bbox_pt": list(self.table_bbox_pt),
            "outer_width_pt": self.outer_width_pt,
            "outer_height_pt": self.outer_height_pt,
            "columns_count": len(self.columns),
            "rows_count": len(self.rows),
            "body_rows_count": self.body_rows_count,
            "is_borderless": self.is_borderless,
            "table_style_chosen": self.table_style_chosen,
            "table_style_runner_up": self.table_style_runner_up,
            "sum_column_widths_pt": self.sum_column_widths_pt,
            "contiguity_passed": self.contiguity_passed,
            "unused_qualifying_rules": self.unused_qualifying_rules,
            "table_confidence": round(self.table_confidence, 3),
            "confidence_reasons": self.confidence_reasons,
            "boundaries": [b.to_dict() for b in self.boundaries],
            "columns": [c.to_dict() for c in self.columns],
            "rows": [r.to_dict() for r in self.rows],
        }


class TableGridEngine:
    """
    Recovers authoritative table grids, virtual column models, multi-line wrapped rows,
    and band types for all 6 table style models.
    """

    def __init__(self):
        self.logical_rows = LogicalRowEngine()

    def determine_table_style_models(
        self,
        ruleset: RuleSet,
        page_layer: PageByteLayer,
    ) -> Tuple[TableStyleVerdict, TableStyleVerdict, List[str]]:
        """
        K5: Determines table style via structural tests — no additive scores.

        Decision tree:
          empty_table  : < 2 header keywords AND no spanning v-rules
          full_grid    : spanning v-rules >= 3  AND inter-body h-rules >= 1
          vertical_only: spanning v-rules >= 3  AND inter-body h-rules == 0
          filled_header: fill band present (spanning >= 35% page width)
          horizontal_only: >= 2 qualifying h-rules, no spanning v-rules, no fill band
          borderless   : fallback

        "inter-body h-rule" = a qual_h rule whose centre falls strictly between
        two consecutive body baselines separated by 2..30 pt.
        """
        v_rules = ruleset.v_rules
        h_rules = ruleset.h_rules
        evidence = []

        # 1. Spanning vertical rules cluster (>= 4 rules sharing >= 40% Y-interval overlap to form >= 3 columns)
        qual_v_candidates = [r for r in v_rules if r.span >= 100.0]
        v_clusters: List[List[Rule]] = []
        for r in qual_v_candidates:
            placed = False
            for cl in v_clusters:
                ov_start = max(r.start, cl[0].start)
                ov_end = min(r.end, cl[0].end)
                if (ov_end - ov_start) >= 0.4 * min(r.span, cl[0].span):
                    cl.append(r)
                    placed = True
                    break
            if not placed:
                v_clusters.append([r])

        max_v_cluster = max(v_clusters, key=len) if v_clusters else []
        qual_v = max_v_cluster if len(max_v_cluster) >= 3 else []
        has_spanning_v = len(qual_v) >= 3

        # 2. Spanning horizontal rules (span >= 35% page width)
        qual_h = [r for r in h_rules if r.span >= 0.35 * page_layer.width_pt]

        # 3. Fill band evidence (must be in header/body region, not footer < 25% page height)
        filled_paths = [
            p for p in page_layer.paths
            if p.fill_color is not None
            and 8.0 <= (p.bbox_device_pt[3] - p.bbox_device_pt[1]) <= 60.0
            and p.bbox_device_pt[1] >= 0.25 * page_layer.height_pt
        ]
        has_fill_band = False
        fill_coverage = 0.0
        for p in filled_paths:
            pw = p.bbox_device_pt[2] - p.bbox_device_pt[0]
            if pw >= 0.35 * page_layer.width_pt:
                has_fill_band = True
                fill_coverage = pw / page_layer.width_pt
                break

        if not has_fill_band and len(filled_paths) >= 3:
            y_groups: Dict[float, List[Any]] = {}
            for p in filled_paths:
                yk = round(p.bbox_device_pt[1] / 5.0) * 5.0
                y_groups.setdefault(yk, []).append(p)
            for yk, grp in y_groups.items():
                tot_w = sum(p.bbox_device_pt[2] - p.bbox_device_pt[0] for p in grp)
                if tot_w >= 0.35 * page_layer.width_pt:
                    has_fill_band = True
                    fill_coverage = tot_w / page_layer.width_pt
                    break

        # Check for zebra row bands across multiple distinct Y levels in body region
        body_fill_paths = [
            p for p in page_layer.paths
            if p.fill_color is not None
            and 6.0 <= (p.bbox_device_pt[3] - p.bbox_device_pt[1]) <= 60.0
            and (p.bbox_device_pt[2] - p.bbox_device_pt[0]) >= 0.30 * page_layer.width_pt
            and 0.10 * page_layer.height_pt <= p.bbox_device_pt[1] <= 0.85 * page_layer.height_pt
        ]
        body_fill_y_levels = set(round(p.bbox_device_pt[1] / 8.0) * 8.0 for p in body_fill_paths)
        has_row_bands = len(body_fill_y_levels) >= 2

        # 4. Table column keywords
        keywords = [
            "date", "txn", "narration", "particulars", "description", "balance",
            "withdrawal", "deposit", "chq", "ref", "debit", "credit", "amount", "#"
        ]
        text_lower = "".join(
            (c.unicode_text or c.char_text).lower()
            for c in page_layer.chars
            if 80.0 <= c.origin_device_pt[1] <= page_layer.height_pt - 80.0
        )
        matched_kws = [kw for kw in keywords if kw in text_lower]

        # 5. K5 STRUCTURAL KEY TEST — count inter-body h-rules.
        # Body baselines = distinct y-origins in the inner 80% of page height.
        # For each consecutive pair separated 2..30 pt (body line pitch range),
        # count qualifying h-rules whose centre falls strictly between them.
        body_baselines: List[float] = sorted(set(
            round(c.origin_device_pt[1], 1)
            for c in page_layer.chars
            if 0.1 * page_layer.height_pt <= c.origin_device_pt[1] <= 0.9 * page_layer.height_pt
        ), reverse=True)

        if has_spanning_v:
            # Common overlap interval of the spanning vertical rules cluster defines table y0..y1
            v_y0 = max(r.start for r in qual_v)
            v_y1 = min(r.end for r in qual_v)
            # Exclude header band (top 25 pt below table top v_y1) and footer margin (bottom 10 pt)
            table_body_baselines = [b for b in body_baselines if v_y0 + 10.0 < b < v_y1 - 25.0]
            interior_h = [r for r in qual_h if v_y0 + 5.0 < r.centre < v_y1 - 25.0]
        else:
            table_body_baselines = body_baselines
            b_min = min(body_baselines) if body_baselines else 0.0
            b_max = max(body_baselines) if body_baselines else page_layer.height_pt
            interior_h = [r for r in qual_h if b_min + 5.0 < r.centre < b_max - 5.0]

        inter_body_h_rules = 0
        if len(table_body_baselines) >= 2 and interior_h:
            for i in range(len(table_body_baselines) - 1):
                b_high = table_body_baselines[i]
                b_low = table_body_baselines[i + 1]
                gap = b_high - b_low
                if 2.0 < gap < 30.0:
                    for r in interior_h:
                        if b_low < r.centre < b_high:
                            inter_body_h_rules += 1

        # 6. STRUCTURAL DECISION TREE
        evidence_dict: Dict[str, str] = {
            "full_grid": (
                f"{len(qual_v)} spanning v-rules, {inter_body_h_rules} inter-body h-rules "
                f"(>=1 required for full_grid), {len(qual_h)} qual_h, {len(matched_kws)} kws"
            ),
            "vertical_only": (
                f"{len(qual_v)} spanning v-rules, {inter_body_h_rules} inter-body h-rules "
                f"(0 = vertical_only), {len(matched_kws)} kws"
            ),
            "row_bands_only": (
                f"row_bands={has_row_bands} ({len(body_fill_y_levels)} zebra levels), "
                f"no spanning v-rules, {len(matched_kws)} kws"
            ),
            "filled_header": (
                f"fill_band={has_fill_band} (cov={fill_coverage:.2f}), "
                f"{len(qual_h)} h-rules, {len(matched_kws)} kws"
            ),
            "horizontal_only": (
                f"{len(qual_h)} spanning h-rules, no spanning v-rules, {len(matched_kws)} kws"
            ),
            "unruled": (
                f"{len(matched_kws)} kws, no rules/fills, ink projection gutters"
            ),
            "borderless": (
                f"{len(matched_kws)} kws, no spanning v-rules, no fill band"
            ),
            "empty_table": (
                f"{len(matched_kws)} kws (<2 needed), {len(qual_v)} v-rules (0 for empty)"
            ),
        }

        # Check for transaction date anchors in body rows (to distinguish empty table from continuation pages)
        date_pattern = re.compile(r'\d{2}[-/]\d{2}[-/]\d{2,4}')
        body_chars_lower = [c for c in page_layer.chars if 80.0 <= c.origin_device_pt[1] <= 0.75 * page_layer.height_pt]
        y_lines_map: Dict[float, List[Any]] = {}
        for c in body_chars_lower:
            yk = round(c.origin_device_pt[1], 1)
            y_lines_map.setdefault(yk, []).append(c)
        body_date_rows = sum(
            1 for yk, chars in y_lines_map.items()
            if date_pattern.search(''.join(c.unicode_text or c.char_text for c in sorted(chars, key=lambda ch: ch.origin_device_pt[0])))
        )

        if len(matched_kws) < 2 and not has_spanning_v and body_date_rows < 2:
            verdict_order = [
                TableStyleVerdict.EMPTY_TABLE,
                TableStyleVerdict.UNRULED,
                TableStyleVerdict.BORDERLESS,
                TableStyleVerdict.HORIZONTAL_ONLY,
                TableStyleVerdict.ROW_BANDS_ONLY,
                TableStyleVerdict.VERTICAL_ONLY,
                TableStyleVerdict.FULL_GRID,
                TableStyleVerdict.FILLED_HEADER,
            ]
        elif has_spanning_v and (not has_fill_band or len(qual_v) >= 5):
            if inter_body_h_rules >= 1:
                verdict_order = [
                    TableStyleVerdict.FULL_GRID,
                    TableStyleVerdict.VERTICAL_ONLY,
                    TableStyleVerdict.FILLED_HEADER,
                    TableStyleVerdict.ROW_BANDS_ONLY,
                    TableStyleVerdict.HORIZONTAL_ONLY,
                    TableStyleVerdict.UNRULED,
                    TableStyleVerdict.BORDERLESS,
                    TableStyleVerdict.EMPTY_TABLE,
                ]
            else:
                # KEY K5 FIX: zero inter-body h-rules -> vertical_only
                verdict_order = [
                    TableStyleVerdict.VERTICAL_ONLY,
                    TableStyleVerdict.FULL_GRID,
                    TableStyleVerdict.FILLED_HEADER,
                    TableStyleVerdict.ROW_BANDS_ONLY,
                    TableStyleVerdict.HORIZONTAL_ONLY,
                    TableStyleVerdict.UNRULED,
                    TableStyleVerdict.BORDERLESS,
                    TableStyleVerdict.EMPTY_TABLE,
                ]
        elif has_row_bands:
            verdict_order = [
                TableStyleVerdict.ROW_BANDS_ONLY,
                TableStyleVerdict.FILLED_HEADER,
                TableStyleVerdict.HORIZONTAL_ONLY,
                TableStyleVerdict.UNRULED,
                TableStyleVerdict.BORDERLESS,
                TableStyleVerdict.VERTICAL_ONLY,
                TableStyleVerdict.FULL_GRID,
                TableStyleVerdict.EMPTY_TABLE,
            ]
        elif has_fill_band:
            verdict_order = [
                TableStyleVerdict.FILLED_HEADER,
                TableStyleVerdict.ROW_BANDS_ONLY,
                TableStyleVerdict.HORIZONTAL_ONLY,
                TableStyleVerdict.UNRULED,
                TableStyleVerdict.BORDERLESS,
                TableStyleVerdict.VERTICAL_ONLY,
                TableStyleVerdict.FULL_GRID,
                TableStyleVerdict.EMPTY_TABLE,
            ]
        elif len(qual_h) >= 2:
            verdict_order = [
                TableStyleVerdict.HORIZONTAL_ONLY,
                TableStyleVerdict.ROW_BANDS_ONLY,
                TableStyleVerdict.FILLED_HEADER,
                TableStyleVerdict.UNRULED,
                TableStyleVerdict.BORDERLESS,
                TableStyleVerdict.VERTICAL_ONLY,
                TableStyleVerdict.FULL_GRID,
                TableStyleVerdict.EMPTY_TABLE,
            ]
        else:
            verdict_order = [
                TableStyleVerdict.UNRULED,
                TableStyleVerdict.BORDERLESS,
                TableStyleVerdict.HORIZONTAL_ONLY,
                TableStyleVerdict.ROW_BANDS_ONLY,
                TableStyleVerdict.FILLED_HEADER,
                TableStyleVerdict.VERTICAL_ONLY,
                TableStyleVerdict.FULL_GRID,
                TableStyleVerdict.EMPTY_TABLE,
            ]

        chosen = verdict_order[0]
        runner_up = verdict_order[1]

        # Print structural evidence per page (K5)
        click.echo(f"\n[table_style] Page {page_layer.page_number} Structural Evidence:")
        click.echo(
            f"  has_spanning_v={has_spanning_v} ({len(qual_v)} v-rules) | "
            f"inter_body_h={inter_body_h_rules} | "
            f"has_row_bands={has_row_bands} | "
            f"has_fill_band={has_fill_band} (cov={fill_coverage:.2f}) | "
            f"qual_h={len(qual_h)} | matched_kws={len(matched_kws)} | "
            f"body_baselines={len(body_baselines)}"
        )
        for style in verdict_order:
            marker = " <-- CHOSEN" if style == chosen else (" <-- runner-up" if style == runner_up else "")
            click.echo(f"  * {style.value:<16}: {evidence_dict[style.value]}{marker}")
        click.echo(f"  Verdict: {chosen.value.upper()} (Runner-Up: {runner_up.value})\n")

        evidence.append(evidence_dict[chosen.value])
        return chosen, runner_up, evidence

    def build_table_grid(
        self,
        ruleset: RuleSet,
        page_layer: PageByteLayer,
        containers: Optional[Any] = None,
        min_table_height_pt: float = 40.0,
        forced_style: Optional[Any] = None,
        **kwargs,
    ) -> TableGrid:
        if isinstance(containers, (TableStyleVerdict, str)):
            if isinstance(containers, str):
                try:
                    forced_style = TableStyleVerdict(containers)
                except ValueError:
                    forced_style = None
            else:
                forced_style = containers
            containers = None

        chosen_style, runner_up, evidence = self.determine_table_style_models(ruleset, page_layer)
        if forced_style is not None:
            chosen_style = forced_style

        if chosen_style == TableStyleVerdict.EMPTY_TABLE:
            return self._build_empty_table_grid(ruleset, page_layer, chosen_style.value, runner_up.value)
        elif chosen_style in (TableStyleVerdict.FULL_GRID, TableStyleVerdict.VERTICAL_ONLY):
            return self._build_ruled_table_grid(ruleset, page_layer, chosen_style.value, runner_up.value, min_table_height_pt)
        else:
            return self._build_virtual_table_grid(ruleset, page_layer, chosen_style.value, runner_up.value)

    def _build_empty_table_grid(
        self,
        ruleset: RuleSet,
        page_layer: PageByteLayer,
        chosen: str,
        runner_up: str,
    ) -> TableGrid:
        c_x0, c_y0, c_x1, c_y1 = page_layer.cropbox_pt
        t_bbox = (36.0, 100.0, (c_x1 - c_x0) - 36.0, (c_y1 - c_y0) - 100.0)
        return TableGrid(
            table_bbox_pt=t_bbox,
            columns=[],
            rows=[],
            boundaries=[],
            is_borderless=True,
            outer_width_pt=t_bbox[2] - t_bbox[0],
            outer_height_pt=t_bbox[3] - t_bbox[1],
            sum_column_widths_pt=0.0,
            contiguity_passed=True,
            table_style_chosen=chosen,
            table_style_runner_up=runner_up,
            table_confidence=1.0,
            confidence_reasons=["empty_table_structure"],
        )

    def _build_ruled_table_grid(
        self,
        ruleset: RuleSet,
        page_layer: PageByteLayer,
        chosen: str,
        runner_up: str,
        min_table_height_pt: float,
    ) -> TableGrid:
        v_rules = ruleset.v_rules
        h_rules = ruleset.h_rules

        if not v_rules:
            return self._build_virtual_table_grid(ruleset, page_layer, chosen, runner_up)

        # Cluster candidate vertical rules by Y-interval overlap (>= 40%)
        candidate_rules = [r for r in v_rules if r.span >= 50.0]
        y_clusters: List[List[Rule]] = []
        for r in candidate_rules:
            placed = False
            for cl in y_clusters:
                ov_start = max(r.start, cl[0].start)
                ov_end = min(r.end, cl[0].end)
                if (ov_end - ov_start) >= 0.4 * min(r.span, cl[0].span):
                    cl.append(r)
                    placed = True
                    break
            if not placed:
                y_clusters.append([r])

        valid_clusters = []
        for cl in y_clusters:
            cl_sorted = sorted(cl, key=lambda r: r.centre)
            x_spread = cl_sorted[-1].centre - cl_sorted[0].centre
            if len(cl_sorted) >= 3 and x_spread >= 40.0:
                valid_clusters.append((len(cl_sorted), max(r.span for r in cl), cl))

        if valid_clusters:
            valid_clusters.sort(key=lambda t: (t[0], t[1]), reverse=True)
            best_rules = valid_clusters[0][2]
            max_v_span = max(r.span for r in best_rules)
            qualifying_rules = [r for r in best_rules if (r.span / max_v_span) >= 0.75]
        else:
            max_v_span = max([r.span for r in v_rules])
            qualifying_rules = [r for r in v_rules if (r.span / max_v_span) >= 0.6]

        if len(qualifying_rules) < 2:
            return self._build_virtual_table_grid(ruleset, page_layer, chosen, runner_up)

        boundary_clusters: List[List[Rule]] = []
        qualifying_rules.sort(key=lambda r: r.centre)

        for r in qualifying_rules:
            placed = False
            for cluster in boundary_clusters:
                if abs(cluster[0].centre - r.centre) <= 1.0:
                    cluster.append(r)
                    placed = True
                    break
            if not placed:
                boundary_clusters.append([r])

        boundaries: List[ColumnBoundary] = []
        for cluster in boundary_clusters:
            avg_x = float(np.mean([r.centre for r in cluster]))
            max_w = max([r.width for r in cluster])
            min_y0 = min([r.start for r in cluster])
            max_y1 = max([r.end for r in cluster])
            cov = (abs(max_y1 - min_y0) / max_v_span) * 100.0
            prim_id = cluster[0].id

            boundaries.append(ColumnBoundary(
                rule_id=prim_id,
                centre_x_pt=avg_x,
                width_pt=max_w,
                span_y0_pt=min_y0,
                span_y1_pt=max_y1,
                coverage_pct=cov,
                is_virtual=False,
                evidence=["vector_vertical_rule"],
                confidence=1.0,
                confidence_reasons=["vector_vertical_rule", f"coverage_{cov:.1f}%"],
            ))

        boundaries.sort(key=lambda b: b.centre_x_pt)

        table_x0 = boundaries[0].centre_x_pt - boundaries[0].width_pt / 2.0
        table_x1 = boundaries[-1].centre_x_pt + boundaries[-1].width_pt / 2.0
        table_y0 = min([b.span_y0_pt for b in boundaries])
        table_y1 = max([b.span_y1_pt for b in boundaries])

        # If outer boundary rules extend past interior column dividers (e.g. bounding footer summary),
        # snap table_y0 to the consensus interior column divider start and its dividing horizontal rule
        if len(boundaries) > 2:
            interior_y0 = min(b.span_y0_pt for b in boundaries[1:-1])
            if interior_y0 > table_y0 + 20.0:
                sep_rules = [r for r in h_rules if abs(r.centre - interior_y0) <= 5.0 and r.end >= table_x1 - 5.0]
                if sep_rules:
                    table_y0 = sep_rules[0].centre - sep_rules[0].width / 2.0
                else:
                    table_y0 = interior_y0

        matching_top = [r for r in h_rules if abs(r.centre - table_y1) <= 2.0 and r.end >= table_x1 - 5.0]
        matching_bot = [r for r in h_rules if abs(r.centre - table_y0) <= 2.0 and r.end >= table_x1 - 5.0]

        if matching_top:
            table_y1 = max(table_y1, matching_top[0].centre + matching_top[0].width / 2.0)
        if matching_bot:
            table_y0 = min(table_y0, matching_bot[0].centre - matching_bot[0].width / 2.0)

        table_bbox = (table_x0, table_y0, table_x1, table_y1)
        outer_w = table_x1 - table_x0
        outer_h = table_y1 - table_y0

        columns: List[ColumnModel] = []
        sum_widths = 0.0

        for i in range(len(boundaries) - 1):
            b_left = boundaries[i]
            b_right = boundaries[i + 1]

            col_x0 = b_left.centre_x_pt + b_left.width_pt / 2.0
            col_x1 = b_right.centre_x_pt - b_right.width_pt / 2.0
            col_w = col_x1 - col_x0

            sum_widths += col_w
            columns.append(ColumnModel(
                index=i + 1,
                x0_pt=col_x0,
                x1_pt=col_x1,
                width_pt=col_w,
                left_rule_id=b_left.rule_id,
                right_rule_id=b_right.rule_id,
                evidence=["vector_rule_bounded"],
            ))

        total_rule_widths = sum(b.width_pt for b in boundaries)
        sum_delta = abs((sum_widths + total_rule_widths) - outer_w)
        contiguity_ok = sum_delta <= 0.25

        rows = self.logical_rows.extract_logical_rows(
            page_layer=page_layer,
            table_bbox_pt=table_bbox,
            columns=columns,
            h_rules=h_rules,
        )

        # Header text detection per column with multi-line, offset, and spanning support
        self._detect_column_headers(
            page_layer=page_layer,
            table_bbox=table_bbox,
            columns=columns,
            rows=rows,
            h_rules=h_rules,
            boundaries=boundaries,
        )

        return TableGrid(
            table_bbox_pt=table_bbox,
            columns=columns,
            rows=rows,
            boundaries=boundaries,
            is_borderless=False,
            outer_width_pt=outer_w,
            outer_height_pt=outer_h,
            sum_column_widths_pt=sum_widths,
            contiguity_passed=contiguity_ok,
            table_style_chosen=chosen,
            table_style_runner_up=runner_up,
            unused_qualifying_rules=[],
            table_confidence=1.0,
            confidence_reasons=["vector_vertical_rules", "contiguity_passed"],
        )

    def _build_virtual_table_grid(
        self,
        ruleset: RuleSet,
        page_layer: PageByteLayer,
        chosen: str,
        runner_up: str,
    ) -> TableGrid:
        """
        Extracts virtual columns and wrapped rows for tables without vertical rules.
        Implements 5-step column inference:
        (a) Find header row via banking keyword matching
        (b) Extract header label x-positions and text tokens
        (c) Compute vertical projection profile over body-text glyph boxes to find whitespace gutters
        (d) Detect left/right/center alignment edges per column (numeric right-aligned)
        (e) Merge evidence into column boundaries placed in the gutter midpoints with confidence scoring
        """
        # Determine table vertical span
        qual_h = [r for r in ruleset.h_rules if r.span >= 0.35 * page_layer.width_pt]

        # Check for collinear row of filled header/table cells (Kotak zebra cells, SBI, Union Bank)
        cell_paths = [
            p for p in page_layer.paths
            if p.fill_color is not None and 8.0 <= (p.bbox_device_pt[3] - p.bbox_device_pt[1]) <= 60.0
            and 20.0 <= (p.bbox_device_pt[2] - p.bbox_device_pt[0]) <= 300.0
        ]
        y_groups: Dict[float, List[Any]] = {}
        for cp in cell_paths:
            yk = round(cp.bbox_device_pt[1] / 5.0) * 5.0
            y_groups.setdefault(yk, []).append(cp)

        collinear_cell_row = []
        for yk, grp in sorted(y_groups.items(), reverse=True):
            tot_w = sum(p.bbox_device_pt[2] - p.bbox_device_pt[0] for p in grp)
            if tot_w >= 0.5 * page_layer.width_pt and len(grp) >= 3:
                collinear_cell_row = sorted(grp, key=lambda p: p.bbox_device_pt[0])
                break

        wide_fill_bands = []
        for p in page_layer.paths:
            px0, py0, px1, py1 = p.bbox_device_pt
            pw = px1 - px0
            ph = py1 - py0
            if pw >= 180.0 and 8.0 <= ph <= 50.0 and p.fill_color is not None:
                wide_fill_bands.append(p)

        filled_header_paths = collinear_cell_row if collinear_cell_row else wide_fill_bands

        t_y0 = 36.0
        t_y1 = page_layer.height_pt - 36.0
        t_x0 = 36.0
        t_x1 = page_layer.width_pt - 36.0

        if wide_fill_bands:
            hp_x0 = min(p.bbox_device_pt[0] for p in wide_fill_bands)
            hp_x1 = max(p.bbox_device_pt[2] for p in wide_fill_bands)
            hp_y1 = max(p.bbox_device_pt[3] for p in wide_fill_bands)
            t_x0 = hp_x0
            t_x1 = hp_x1
            t_y1 = hp_y1
            if collinear_cell_row:
                t_x0 = collinear_cell_row[0].bbox_device_pt[0]
                t_x1 = collinear_cell_row[-1].bbox_device_pt[2]
            table_w = t_x1 - t_x0
            table_h = [r for r in qual_h if abs(r.span - table_w) <= 25.0 and r.centre <= hp_y1 + 5.0]
            if table_h:
                t_y0 = min(r.centre for r in table_h)
            else:
                cells_below = [
                    p for p in cell_paths
                    if t_x0 - 2.0 <= p.bbox_device_pt[0] and p.bbox_device_pt[2] <= t_x1 + 2.0 and p.bbox_device_pt[3] <= t_y1
                ]
                if cells_below:
                    t_y0 = min(p.bbox_device_pt[1] for p in cells_below)
                else:
                    t_y0 = 36.0
        elif collinear_cell_row:
            t_x0 = collinear_cell_row[0].bbox_device_pt[0]
            t_x1 = collinear_cell_row[-1].bbox_device_pt[2]
            t_y1 = max(p.bbox_device_pt[3] for p in collinear_cell_row)
            table_w = t_x1 - t_x0
            table_h = [r for r in qual_h if abs(r.span - table_w) <= 25.0 and r.centre <= t_y1 + 5.0]
            if table_h:
                t_y0 = min(r.centre for r in table_h)
            else:
                cells_below = [
                    p for p in cell_paths
                    if t_x0 - 2.0 <= p.bbox_device_pt[0] and p.bbox_device_pt[2] <= t_x1 + 2.0 and p.bbox_device_pt[3] <= t_y1
                ]
                if cells_below:
                    t_y0 = min(p.bbox_device_pt[1] for p in cells_below)
                else:
                    t_y0 = 36.0
        elif qual_h:
            t_y0 = min(r.centre for r in qual_h)
            t_y1 = max(r.centre for r in qual_h)
            t_x0 = min(min(r.start, r.end) for r in qual_h)
            t_x1 = max(max(r.start, r.end) for r in qual_h)
        else:
            t_y0 = 36.0
            t_y1 = page_layer.height_pt - 36.0
            t_x0 = 36.0
            t_x1 = page_layer.width_pt - 36.0

        # Find characters inside the table vertical band
        chars_in_table = [
            c for c in page_layer.chars
            if (t_y0 - 5.0 <= c.origin_device_pt[1] <= t_y1 + 5.0)
            and (t_x0 - 5.0 <= c.origin_device_pt[0] <= t_x1 + 5.0)
        ]

        if not chars_in_table:
            return self._build_empty_table_grid(ruleset, page_layer, chosen, runner_up)

        # Update bounds from text if wider/taller only if not bounded by rules/fill bands
        if not qual_h and not filled_header_paths:
            t_y1 = max(t_y1, max(c.font_bbox_device_pt[3] for c in chars_in_table))
            t_y0 = min(t_y0, min(c.font_bbox_device_pt[1] for c in chars_in_table))
            t_x0 = min(t_x0, min(c.font_bbox_device_pt[0] for c in chars_in_table))
            t_x1 = max(t_x1, max(c.font_bbox_device_pt[2] for c in chars_in_table))

        table_bbox = (t_x0, t_y0, t_x1, t_y1)

        # 1. Step (a) & (b): Identify Header Line & Header Label Tokens
        table_lines = self.logical_rows.group_into_lines(chars_in_table)
        table_lines.sort(key=lambda l: l.baseline_y_pt, reverse=True)

        header_tokens: List[Tuple[float, float, str]] = []
        header_line = None

        HEADER_KEYWORDS = [
            "date", "value date", "post date", "txn date",
            "narration", "particulars", "description", "details",
            "balance", "withdrawal", "deposit", "chq", "ref",
            "debit", "credit", "amount", "#", "s.no", "cheque",
        ]
        for l in table_lines:
            txt_clean = l.text.lower().strip()
            matched = sum(1 for k in HEADER_KEYWORDS if k in txt_clean)
            if matched >= 2:
                header_line = l
                break

        if header_line:
            # If table top is not bounded by explicit rules/fills, snap top to header row (or title band above it)
            if not qual_h and not filled_header_paths:
                title_line = next(
                    (l for l in table_lines if l.baseline_y_pt > header_line.baseline_y_pt
                     and abs(l.baseline_y_pt - header_line.baseline_y_pt) <= 30.0
                     and re.search(r"(savings|account|transaction|statement)", l.text, re.IGNORECASE)),
                    None
                )
                if title_line:
                    t_y1 = title_line.y1 + 4.0
                else:
                    t_y1 = header_line.y1 + 4.0
                table_bbox = (t_x0, t_y0, t_x1, t_y1)

            sorted_chars = sorted(header_line.chars, key=lambda c: c.origin_device_pt[0])
            word_chunks: List[List[PaintedTextChar]] = []
            cur_c: List[PaintedTextChar] = []
            for ch in sorted_chars:
                if not cur_c:
                    cur_c.append(ch)
                else:
                    prev = cur_c[-1]
                    gap = ch.font_bbox_device_pt[0] - prev.font_bbox_device_pt[2]
                    if gap >= 8.0:
                        word_chunks.append(cur_c)
                        cur_c = [ch]
                    else:
                        cur_c.append(ch)
            if cur_c:
                word_chunks.append(cur_c)

            # Assemble phrases (e.g. merge 'Chq/Ref.' and 'No.', 'Withdrawal' and '(Dr.)')
            i = 0
            while i < len(word_chunks):
                chunk = word_chunks[i]
                txt = "".join(c.unicode_text or c.char_text for c in chunk).strip()
                wx0 = min(c.font_bbox_device_pt[0] for c in chunk)
                wx1 = max(c.font_bbox_device_pt[2] for c in chunk)

                if i + 1 < len(word_chunks):
                    next_chunk = word_chunks[i + 1]
                    next_txt = "".join(c.unicode_text or c.char_text for c in next_chunk).strip()
                    next_wx0 = min(c.font_bbox_device_pt[0] for c in next_chunk)
                    next_wx1 = max(c.font_bbox_device_pt[2] for c in next_chunk)
                    if next_txt.lower() in ["no.", "no", "(dr.)", "(dr)", "(cr.)", "(cr)"] and (next_wx0 - wx1) <= 15.0:
                        txt = f"{txt} {next_txt}"
                        wx1 = next_wx1
                        i += 1

                header_tokens.append((wx0, wx1, txt))
                i += 1

        # 2. Step (c): Vertical Projection Profile & Alignment Evidence
        body_chars = [
            c for c in chars_in_table
            if (header_line is None or c.origin_device_pt[1] < header_line.baseline_y_pt - 4.0)
        ]

        all_body_chars = list(body_chars)
        rows_checked = len(set(round(c.origin_device_pt[1], 1) for c in body_chars))
        if hasattr(page_layer, "pdf_path") and page_layer.pdf_path and os.path.exists(page_layer.pdf_path):
            try:
                from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
                with ByteLayerExtractor(page_layer.pdf_path) as doc_ext:
                    total_pages = len(doc_ext.pdf.pages)
                    max_p = total_pages + 1 if total_pages <= 5 else 6
                    for p_num in range(1, max_p):
                        if p_num == page_layer.page_number:
                            continue
                        other_pl = doc_ext.extract_page(p_num)
                        if collinear_cell_row:
                            other_cell_paths = [
                                p for p in other_pl.paths
                                if p.fill_rule and 20.0 <= (p.bbox_device_pt[2] - p.bbox_device_pt[0]) <= 250.0
                                and 8.0 <= (p.bbox_device_pt[3] - p.bbox_device_pt[1]) <= 50.0
                            ]
                            other_y_groups: Dict[float, List[Any]] = {}
                            for cp in other_cell_paths:
                                yk = round(cp.bbox_device_pt[1] / 5.0) * 5.0
                                other_y_groups.setdefault(yk, []).append(cp)
                            matching_rows = [
                                sorted(g, key=lambda x: x.bbox_device_pt[0])
                                for yk, g in other_y_groups.items()
                                if len(g) >= 4 and sum(x.bbox_device_pt[2] - x.bbox_device_pt[0] for x in g) >= 0.5 * other_pl.width_pt
                            ]
                            if matching_rows:
                                o_y0 = min(p.bbox_device_pt[1] for row in matching_rows for p in row)
                                o_y1 = max(p.bbox_device_pt[3] for row in matching_rows for p in row)
                                other_chars = [
                                    c for c in other_pl.chars
                                    if (o_y0 - 2.0 <= c.origin_device_pt[1] <= o_y1 + 2.0)
                                    and (t_x0 - 5.0 <= c.origin_device_pt[0] <= t_x1 + 5.0)
                                    and (c.unicode_text or c.char_text).strip()
                                ]
                                all_body_chars.extend(other_chars)
                                rows_checked += len(set(round(c.origin_device_pt[1], 1) for c in other_chars))
            except Exception as e:
                logger.debug(f"Could not load all pages for document-level virtual boundaries: {e}")

        # Check for vertical separator lines or header rect edges in header band
        header_y_min = t_y0
        header_y_max = header_line.baseline_y_pt + 30.0 if header_line else t_y0 + 50.0
        sep_lines = []
        if len(filled_header_paths) >= 3:
            fill_edges = []
            for fp in filled_header_paths[:-1]:
                fx1 = round(fp.bbox_device_pt[2], 3)
                if t_x0 + 10.0 <= fx1 <= t_x1 - 10.0:
                    fill_edges.append(fx1)
            fill_edges = sorted(list(set(fill_edges)))
            if len(fill_edges) >= 2:
                sep_lines = fill_edges
        else:
            for p in page_layer.paths:
                bx0, by0, bx1, by1 = p.bbox_device_pt
                if (bx1 - bx0) <= 2.0 and (by1 - by0) >= 8.0:
                    if (by0 >= header_y_min - 30.0 and by1 <= header_y_max + 30.0):
                        if t_x0 + 10.0 <= bx0 <= t_x1 - 10.0:
                            sep_lines.append(float(round((bx0 + bx1) / 2.0, 3)))

        sep_lines = sorted(list(set(sep_lines)))

        col_splits: List[float] = [t_x0]
        evidence_list: List[str] = []

        # ---- Vertical projection profile and ink-free midpoint helper ----
        def _ink_free_midpoint(
            nominal_x: float,
            body_chars_list: List[PaintedTextChar],
            fallback_x: float,
            boundary_label: str,
            rows_chk: int,
        ) -> float:
            if not body_chars_list:
                return fallback_x

            # Left ink: rightmost edge of any char that lies entirely LEFT of nominal_x
            gap_left = max(
                (c.font_bbox_device_pt[2] for c in body_chars_list
                 if c.font_bbox_device_pt[2] < nominal_x),
                default=t_x0,
            )
            # Right ink: leftmost edge of any char that lies entirely RIGHT of nominal_x
            gap_right = min(
                (c.font_bbox_device_pt[0] for c in body_chars_list
                 if c.font_bbox_device_pt[0] > nominal_x),
                default=t_x1,
            )

            if gap_right > gap_left:
                mid = (gap_left + gap_right) / 2.0
                click.echo(
                    f"[virtual_boundary] {boundary_label}: "
                    f"gap_left={gap_left:.3f} gap_right={gap_right:.3f} "
                    f"midpoint={mid:.3f} rows_checked={rows_chk}"
                )
                return mid
            else:
                for delta in [3.0, 6.0, 10.0, 15.0]:
                    lo = nominal_x - delta
                    hi = nominal_x + delta
                    gl = max(
                        (c.font_bbox_device_pt[2] for c in body_chars_list
                         if c.font_bbox_device_pt[2] < lo),
                        default=t_x0,
                    )
                    gr = min(
                        (c.font_bbox_device_pt[0] for c in body_chars_list
                         if c.font_bbox_device_pt[0] > hi),
                        default=t_x1,
                    )
                    if gr > gl:
                        mid = (gl + gr) / 2.0
                        click.echo(
                            f"[virtual_boundary] {boundary_label} (widened ±{delta:.0f}): "
                            f"gap_left={gl:.3f} gap_right={gr:.3f} midpoint={mid:.3f} rows_checked={rows_chk}"
                        )
                        return mid
                return fallback_x

        def _evaluate_boundary_confidence(
            b_x: float,
            gap_l: Optional[float],
            gap_r: Optional[float],
            tok_l: Optional[Tuple[float, float, str]],
            tok_r: Optional[Tuple[float, float, str]],
            src: str,
        ) -> Tuple[float, List[str]]:
            reasons = []
            score = 0.0
            if src == "header_fill":
                score += 0.40
                reasons.append("header_fill_aligned")
            elif src in ("ink_gutter", "projection_profile"):
                score += 0.35
                reasons.append(f"source_{src}")

            if gap_l is not None and gap_r is not None:
                w = gap_r - gap_l
                if w >= 4.0:
                    score += 0.35
                    reasons.append(f"gutter width {w:.2f}pt")
                elif w >= 2.0:
                    score += 0.25
                    reasons.append(f"gutter width {w:.2f}pt")
                elif w > 0.0:
                    score += 0.15
                    reasons.append(f"narrow gutter {w:.2f}pt")
                else:
                    reasons.append("zero_or_negative_gutter")

            if tok_l is not None and tok_r is not None:
                if tok_l[1] <= b_x <= tok_r[0]:
                    score += 0.25
                    reasons.append(f"header aligned ({tok_l[2]} | {tok_r[2]})")
                else:
                    score += 0.10
                    reasons.append(f"near header ({tok_l[2]} | {tok_r[2]})")
            elif tok_l is not None or tok_r is not None:
                score += 0.15
                reasons.append("outer_header_aligned")
            else:
                score += 0.10

            conf = min(1.0, max(0.2, score))
            return conf, reasons

        boundary_meta: Dict[float, Dict[str, Any]] = {}

        if len(sep_lines) >= 2 and (len(header_tokens) == 0 or len(sep_lines) >= len(header_tokens) - 2):
            evidence_list.append(f"header_structural_separators({len(sep_lines)})")
            for k, sep_x in enumerate(sep_lines):
                lbl_left = header_tokens[k][2] if k < len(header_tokens) else f"Col_{k+1}"
                lbl_right = header_tokens[k + 1][2] if k + 1 < len(header_tokens) else f"Col_{k+2}"
                label = f"Boundary {k+1} ({lbl_left} | {lbl_right})"

                ink_chars = [c for c in all_body_chars if (c.unicode_text or c.char_text).strip()]
                gl = max((c.font_bbox_device_pt[2] for c in ink_chars if c.font_bbox_device_pt[2] < sep_x), default=t_x0)
                gr = min((c.font_bbox_device_pt[0] for c in ink_chars if c.font_bbox_device_pt[0] > sep_x), default=t_x1)
                mid = (gl + gr) / 2.0
                delta_ink = abs(sep_x - mid)
                nearest_dist = min(abs(sep_x - gl), abs(gr - sep_x))
                flagged_tight = nearest_dist < 1.5

                if collinear_cell_row:
                    col_splits.append(sep_x)
                    src = "header_fill"
                    chosen_x = sep_x
                else:
                    gutter_x = _ink_free_midpoint(sep_x, all_body_chars, sep_x, label, rows_checked)
                    col_splits.append(gutter_x)
                    src = "ink_gutter"
                    chosen_x = gutter_x

                tok_l = header_tokens[k] if k < len(header_tokens) else None
                tok_r = header_tokens[k + 1] if k + 1 < len(header_tokens) else None
                conf, reasons = _evaluate_boundary_confidence(chosen_x, gl, gr, tok_l, tok_r, src)

                boundary_meta[chosen_x] = {
                    "source": src,
                    "fill_edge": sep_x,
                    "ink_midpoint": mid,
                    "delta": delta_ink,
                    "gap_left": gl,
                    "gap_right": gr,
                    "nearest_ink_dist": nearest_dist,
                    "flagged_tight": flagged_tight,
                    "confidence": conf,
                    "confidence_reasons": reasons,
                }
            col_splits.append(t_x1)
        elif len(header_tokens) >= 2:
            evidence_list.append(f"header_tokens_detected({len(header_tokens)})")
            for k in range(len(header_tokens) - 1):
                tok_left = header_tokens[k]
                tok_right = header_tokens[k + 1]
                nominal = (tok_left[1] + tok_right[0]) / 2.0
                label = f"Boundary {k+1} ({tok_left[2]} | {tok_right[2]})"
                gutter_x = _ink_free_midpoint(nominal, all_body_chars, nominal, label, rows_checked)
                col_splits.append(float(gutter_x))

                ink_chars = [c for c in all_body_chars if (c.unicode_text or c.char_text).strip()]
                gl = max((c.font_bbox_device_pt[2] for c in ink_chars if c.font_bbox_device_pt[2] < nominal), default=t_x0)
                gr = min((c.font_bbox_device_pt[0] for c in ink_chars if c.font_bbox_device_pt[0] > nominal), default=t_x1)
                mid = (gl + gr) / 2.0
                nearest_dist = min(abs(gutter_x - gl), abs(gr - gutter_x))
                conf, reasons = _evaluate_boundary_confidence(float(gutter_x), gl, gr, tok_left, tok_right, "ink_gutter")

                boundary_meta[float(gutter_x)] = {
                    "source": "ink_gutter",
                    "fill_edge": None,
                    "ink_midpoint": mid,
                    "delta": abs(nominal - mid),
                    "gap_left": gl,
                    "gap_right": gr,
                    "nearest_ink_dist": nearest_dist,
                    "flagged_tight": nearest_dist < 1.5,
                    "confidence": conf,
                    "confidence_reasons": reasons,
                }
            col_splits.append(t_x1)
        else:
            other_splits = None
            if hasattr(page_layer, "pdf_path") and page_layer.pdf_path and os.path.exists(page_layer.pdf_path):
                try:
                    from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
                    with ByteLayerExtractor(page_layer.pdf_path) as doc_ext:
                        for p_cand in range(1, min(len(doc_ext.pdf.pages) + 1, 5)):
                            if p_cand == page_layer.page_number:
                                continue
                            p_layer = doc_ext.extract_page(p_cand)
                            p_ruleset = RuleSet.from_page_layer(p_layer)
                            cand_grid = self.build_table_grid(p_ruleset, p_layer)
                            if cand_grid and len(cand_grid.columns) >= 2:
                                other_splits = [b.centre_x_pt for b in cand_grid.boundaries]
                                click.echo(
                                    f"[continuation_page] Page {page_layer.page_number} has no header row; "
                                    f"using column boundaries from page {p_cand} of same document ({len(cand_grid.columns)} columns)"
                                )
                                evidence_list.append(f"continuation_page_from_page_{p_cand}")
                                break
                except Exception as e:
                    logger.debug(f"Could not load continuation boundaries from other page: {e}")

            if other_splits and len(other_splits) >= 2:
                col_splits = other_splits
            else:
                evidence_list.append("projection_profile_gutters")
                gutters = self._find_body_ink_gutters(body_chars, t_x0, t_x1)
                for g_mid in gutters:
                    boundary_meta[float(g_mid)] = {
                        "source": "projection_profile",
                        "fill_edge": None,
                        "ink_midpoint": g_mid,
                        "delta": 0.0,
                        "gap_left": None,
                        "gap_right": None,
                        "nearest_ink_dist": 5.0,
                        "flagged_tight": False,
                        "confidence": 0.90,
                        "confidence_reasons": ["projection_profile_gutter"],
                    }
                col_splits = [t_x0] + gutters + [t_x1]

        # Outer boundary metadata for t_x0 and t_x1
        ink_chars = [c for c in all_body_chars if (c.unicode_text or c.char_text).strip()]
        if ink_chars:
            right_ink_0 = min((c.font_bbox_device_pt[0] for c in ink_chars if c.font_bbox_device_pt[0] > t_x0), default=t_x0)
            dist_0 = abs(right_ink_0 - t_x0)
            boundary_meta[t_x0] = {
                "source": "header_fill" if collinear_cell_row else "ink_gutter",
                "fill_edge": t_x0,
                "ink_midpoint": None,
                "delta": None,
                "gap_left": None,
                "gap_right": right_ink_0,
                "nearest_ink_dist": dist_0,
                "flagged_tight": dist_0 < 1.5,
                "confidence": 1.0,
                "confidence_reasons": ["outer_table_left_boundary"],
            }
            left_ink_1 = max((c.font_bbox_device_pt[2] for c in ink_chars if c.font_bbox_device_pt[2] < t_x1), default=t_x1)
            dist_1 = abs(t_x1 - left_ink_1)
            boundary_meta[t_x1] = {
                "source": "header_fill" if collinear_cell_row else "ink_gutter",
                "fill_edge": t_x1,
                "ink_midpoint": None,
                "delta": None,
                "gap_left": left_ink_1,
                "gap_right": None,
                "nearest_ink_dist": dist_1,
                "flagged_tight": dist_1 < 1.5,
                "confidence": 1.0,
                "confidence_reasons": ["outer_table_right_boundary"],
            }

        # 3. Construct Virtual Boundaries and Columns
        col_splits = sorted(list(set(col_splits)))
        boundaries: List[ColumnBoundary] = []
        columns: List[ColumnModel] = []
        sum_w = 0.0

        for i, split_x in enumerate(col_splits):
            meta = boundary_meta.get(float(split_x), {})
            boundaries.append(ColumnBoundary(
                rule_id=f"virtual_v_{i + 1}",
                centre_x_pt=float(split_x),
                width_pt=0.0,
                span_y0_pt=t_y0,
                span_y1_pt=t_y1,
                coverage_pct=100.0,
                is_virtual=True,
                evidence=list(evidence_list),
                boundary_source=meta.get("source", "header_fill" if collinear_cell_row else "ink_gutter"),
                fill_edge_pt=meta.get("fill_edge"),
                ink_midpoint_pt=meta.get("ink_midpoint"),
                delta_fill_vs_ink_pt=meta.get("delta"),
                gap_left_pt=meta.get("gap_left"),
                gap_right_pt=meta.get("gap_right"),
                nearest_ink_dist_pt=meta.get("nearest_ink_dist"),
                flagged_tight_ink=meta.get("flagged_tight", False),
                confidence=meta.get("confidence", 0.95),
                confidence_reasons=meta.get("confidence_reasons", ["virtual_boundary_inferred"]),
            ))

        # Step (d): Detect column alignment edges per column
        for i in range(len(col_splits) - 1):
            cx0 = col_splits[i]
            cx1 = col_splits[i + 1]
            cw = cx1 - cx0
            sum_w += cw

            title = header_tokens[i][2] if i < len(header_tokens) else None
            col_body_chars = [c for c in body_chars if cx0 <= c.origin_device_pt[0] <= cx1]

            # Detect right-aligned numeric patterns
            col_lines = self.logical_rows.group_into_lines(col_body_chars)
            right_edges = [l.x1 for l in col_lines if l.chars]
            left_edges = [l.x0 for l in col_lines if l.chars]

            is_num = any(
                re.search(r"\d+\.\d{2}", l.text)
                or any(t in l.text.split() for t in ["Cr.", "Dr.", "CR", "DR", "Cr", "Dr"])
                for l in col_lines
            ) or (title is not None and any(k in title.lower() for k in ["amount", "balance", "debit", "credit", "withdrawal", "deposit", "dr", "cr"]))

            is_right_aligned = is_num or (len(right_edges) >= 2 and np.std(right_edges) <= 1.5)
            is_left_aligned = len(left_edges) >= 2 and np.std(left_edges) <= 1.5

            if is_right_aligned:
                col_alignment = "right"
            elif is_left_aligned:
                col_alignment = "left"
            elif title and any(k in title.lower() for k in ["date", "chq", "ref", "s.no", "#"]):
                col_alignment = "center"
            else:
                col_alignment = "left"

            columns.append(ColumnModel(
                index=i + 1,
                x0_pt=cx0,
                x1_pt=cx1,
                width_pt=cw,
                left_rule_id=f"virtual_v_{i + 1}",
                right_rule_id=f"virtual_v_{i + 2}",
                header_text=title,
                alignment=col_alignment,
                is_numeric=is_num,
                evidence=list(evidence_list) + [f"alignment_{col_alignment}"],
            ))

        # 4. Extract Multi-Line Wrapped Rows with Band Typing
        rows = self.logical_rows.extract_logical_rows(
            page_layer=page_layer,
            table_bbox_pt=table_bbox,
            columns=columns,
            h_rules=ruleset.h_rules,
        )

        # Refine header text, baselines, and provenance for unruled table columns
        self._detect_column_headers(
            page_layer=page_layer,
            table_bbox=table_bbox,
            columns=columns,
            rows=rows,
            h_rules=ruleset.h_rules,
            boundaries=boundaries,
        )

        outer_w = t_x1 - t_x0
        outer_h = t_y1 - t_y0

        # Overall Table Confidence
        mean_conf = float(np.mean([b.confidence for b in boundaries])) if boundaries else 0.95
        tbl_reasons = [f"mean_boundary_confidence_{mean_conf:.2f}"]
        if mean_conf < 0.85:
            tbl_reasons.append("flagged_low_confidence_review_recommended")

        return TableGrid(
            table_bbox_pt=table_bbox,
            columns=columns,
            rows=rows,
            boundaries=boundaries,
            is_borderless=True,
            outer_width_pt=outer_w,
            outer_height_pt=outer_h,
            sum_column_widths_pt=sum_w,
            contiguity_passed=abs(sum_w - outer_w) <= 0.25,
            table_style_chosen=chosen,
            table_style_runner_up=runner_up,
            unused_qualifying_rules=[],
            table_confidence=mean_conf,
            confidence_reasons=tbl_reasons,
        )

    def _find_body_ink_gutters(
        self,
        chars: List[PaintedTextChar],
        t_x0: float,
        t_x1: float,
    ) -> List[float]:
        """
        Runs a vertical projection profile across [t_x0, t_x1] to find ink-free vertical whitespace gutters.
        """
        if not chars:
            return []

        x_spans = [(c.font_bbox_device_pt[0], c.font_bbox_device_pt[2]) for c in chars]

        gutters = []
        in_gap = False
        gap_start = 0.0

        for x in np.arange(t_x0 + 20.0, t_x1 - 20.0, 1.0):
            has_ink = any(s0 - 0.5 <= x <= s1 + 0.5 for s0, s1 in x_spans)
            if not has_ink:
                if not in_gap:
                    in_gap = True
                    gap_start = x
            else:
                if in_gap:
                    gap_w = x - gap_start
                    if gap_w >= 3.0:
                        gutters.append(float((gap_start + x) / 2.0))
                    in_gap = False

        if in_gap and (t_x1 - 20.0 - gap_start) >= 3.0:
            gutters.append(float((gap_start + t_x1 - 20.0) / 2.0))

        return gutters

    def _detect_column_headers(
        self,
        page_layer: PageByteLayer,
        table_bbox: Tuple[float, float, float, float],
        columns: List[ColumnModel],
        rows: List[RowModel],
        h_rules: Optional[List[Rule]] = None,
        boundaries: Optional[List[ColumnBoundary]] = None,
    ) -> None:
        """
        Detects and associates column headers using geometric header band identification,
        horizontal center span mapping, multi-line top-to-bottom concatenation,
        spanning/merged header tracking, non-text glyph detection, and semantic inference.
        """
        if not columns:
            return

        t_x0, t_y0, t_x1, t_y1 = table_bbox

        hdr_row = next((r for r in rows if r.is_header), None)
        first_body_row = next((r for r in rows if not r.is_header and r.row_type == RowBandType.BODY), None)
        if not first_body_row:
            first_body_row = next((r for r in rows if not r.is_header and r.row_type not in (RowBandType.TABLE_TITLE_BAND,)), None)
        title_row = next((r for r in rows if r.row_type == RowBandType.TABLE_TITLE_BAND), None)

        # 1. Header row band bounds
        if title_row:
            band_y1 = title_row.y0_pt
        elif hdr_row:
            band_y1 = max(t_y1, hdr_row.y1_pt + 3.0)
        else:
            band_y1 = t_y1 + 1.0

        hdr_bottom_rule = None
        if h_rules and hdr_row:
            if hdr_row.bottom_rule_id:
                hdr_bottom_rule = next((r for r in h_rules if r.id == hdr_row.bottom_rule_id), None)
            if not hdr_bottom_rule:
                cands = [r for r in h_rules if r.centre <= hdr_row.y1_pt and r.centre >= hdr_row.y0_pt - 8.0]
                if cands:
                    hdr_bottom_rule = max(cands, key=lambda r: r.centre)

        if hdr_bottom_rule:
            band_y0 = hdr_bottom_rule.centre - 1.0
        elif first_body_row:
            band_y0 = first_body_row.y1_pt - 1.0
        elif hdr_row:
            band_y0 = hdr_row.y0_pt - 4.0
        else:
            band_y0 = max(t_y0, t_y1 - 40.0)

        # Vertical baseline offset tolerance (+- 3.0 pt)
        eff_y1 = band_y1 + 3.0 if not title_row else title_row.y0_pt - 0.5
        eff_y0 = band_y0 - 3.0
        if first_body_row:
            eff_y0 = max(eff_y0, first_body_row.y1_pt - 1.5)

        # Collect characters in the header band
        header_chars = [
            ch for ch in page_layer.chars
            if (t_x0 - 5.0 <= ch.origin_device_pt[0] <= t_x1 + 5.0)
            and (eff_y0 <= ch.origin_device_pt[1] <= eff_y1
                 or (ch.font_bbox_device_pt[1] <= eff_y1 and ch.font_bbox_device_pt[3] >= eff_y0))
        ]
        if title_row:
            header_chars = [c for c in header_chars if c.origin_device_pt[1] < title_row.y0_pt - 0.5]
        if first_body_row:
            header_chars = [c for c in header_chars if c.origin_device_pt[1] > first_body_row.y1_pt - 1.5]

        spans = self._extract_header_spans(header_chars, boundaries=boundaries, columns=columns)

        # Map spans to columns
        col_spans_map: Dict[int, List[HeaderSpan]] = {col.index: [] for col in columns}

        for span in spans:
            s_x0 = span.x0
            s_x1 = span.x1
            s_center = span.center_x

            # Check overlapping columns (overlap > 1.5 pt)
            overlapping_cols = [
                c for c in columns
                if max(0.0, min(s_x1, c.x1_pt) - max(s_x0, c.x0_pt)) > 1.5
            ]

            is_spanning = False
            if len(overlapping_cols) > 1:
                other_has_span = False
                for other_c in overlapping_cols[1:]:
                    if any(
                        s is not span
                        and abs(s.baseline_y_pt - span.baseline_y_pt) <= 2.0
                        and other_c.x0_pt - 1.5 <= s.center_x <= other_c.x1_pt + 1.5
                        for s in spans
                    ):
                        other_has_span = True
                        break
                if not other_has_span:
                    is_spanning = True

            if is_spanning:
                first_c = overlapping_cols[0]
                col_spans_map[first_c.index].append(span)
                for other_c in overlapping_cols[1:]:
                    other_c.header_span_of = first_c.index
            elif len(overlapping_cols) == 1:
                col_spans_map[overlapping_cols[0].index].append(span)
            else:
                # Assign by center_x allowing 1.5 pt edge tolerance
                assigned = False
                for c in columns:
                    if c.x0_pt - 1.5 <= s_center <= c.x1_pt + 1.5:
                        col_spans_map[c.index].append(span)
                        assigned = True
                        break
                if not assigned:
                    closest_c = min(columns, key=lambda c: min(abs(s_center - c.x0_pt), abs(s_center - c.x1_pt)))
                    col_spans_map[closest_c.index].append(span)

        # 3. Assemble headers per column
        for col in columns:
            col_spans = col_spans_map.get(col.index, [])
            if col_spans:
                # Group spans by baseline (tol = 2.0 pt)
                sorted_spans = sorted(col_spans, key=lambda s: s.baseline_y_pt, reverse=True)
                line_groups: List[List[HeaderSpan]] = []
                for s in sorted_spans:
                    placed = False
                    for g in line_groups:
                        if abs(g[0].baseline_y_pt - s.baseline_y_pt) <= 2.0:
                            g.append(s)
                            placed = True
                            break
                    if not placed:
                        line_groups.append([s])

                # Sort lines top-to-bottom
                line_groups.sort(key=lambda g: float(np.mean([s.baseline_y_pt for s in g])), reverse=True)

                line_texts = []
                line_baselines = []
                for g in line_groups:
                    g.sort(key=lambda s: s.x0)
                    l_txt = " ".join(s.text for s in g if s.text).strip()
                    if l_txt:
                        line_texts.append(l_txt)
                        line_baselines.append(float(np.mean([s.baseline_y_pt for s in g])))

                joined_text = " ".join(line_texts).strip()
                if joined_text:
                    col.header_text = joined_text
                    col.header_source = "text"
                    col.header_confidence = 1.0
                    col.header_baselines = [round(b, 2) for b in line_baselines]
                    col.header_span_ids = [s.span_id for s in col_spans]
                    col.header_bbox_pt = (
                        round(min(s.x0 for s in col_spans), 2),
                        round(min(s.y0 for s in col_spans), 2),
                        round(max(s.x1 for s in col_spans), 2),
                        round(max(s.y1 for s in col_spans), 2),
                    )
                    continue

            # If header_text was already set (e.g. from title tokens) and no new spans found
            if col.header_text and col.header_text.strip():
                col.header_source = "text"
                col.header_confidence = 1.0
                continue

            # Spanning header target column
            if col.header_span_of is not None:
                col.header_text = None
                col.header_source = "text"
                col.header_confidence = 1.0
                continue

            # 5. Non-text headers (vector glyphs, icon, or image)
            non_text_box = self._find_non_text_in_header(page_layer, col, eff_y0, eff_y1)
            if non_text_box is not None:
                col.header_text = None
                col.header_source = "non_text"
                col.header_confidence = 0.0
                col.header_bbox_pt = non_text_box
                continue

            # 6. Inferred headers for columns lacking text
            suggested = self._infer_semantic_header(page_layer, col, columns, eff_y0)
            col.header_text = None
            col.header_text_suggested = suggested
            col.header_source = "inferred"
            col.header_confidence = 0.5

    def _extract_header_spans(
        self,
        chars: List[PaintedTextChar],
        boundaries: Optional[List[ColumnBoundary]] = None,
        columns: Optional[List[ColumnModel]] = None,
    ) -> List[HeaderSpan]:
        if not chars:
            return []

        sorted_chars = sorted(chars, key=lambda c: c.origin_device_pt[1], reverse=True)
        baseline_clusters: List[List[PaintedTextChar]] = []
        for c in sorted_chars:
            placed = False
            for cluster in baseline_clusters:
                if abs(cluster[0].origin_device_pt[1] - c.origin_device_pt[1]) <= 2.5:
                    cluster.append(c)
                    placed = True
                    break
            if not placed:
                baseline_clusters.append([c])

        physical_v_rules = []
        if boundaries:
            physical_v_rules = [b.centre_x_pt for b in boundaries if not b.is_virtual]

        spans: List[HeaderSpan] = []
        span_counter = 1

        for cluster in baseline_clusters:
            cluster.sort(key=lambda c: c.font_bbox_device_pt[0])
            curr_span_chars: List[PaintedTextChar] = []

            for c in cluster:
                c_txt = c.unicode_text or c.char_text
                if not curr_span_chars:
                    if c_txt.strip():
                        curr_span_chars.append(c)
                    continue

                prev = curr_span_chars[-1]
                gap = c.font_bbox_device_pt[0] - prev.font_bbox_device_pt[2]

                has_v_rule = any(prev.font_bbox_device_pt[2] <= vx <= c.font_bbox_device_pt[0] for vx in physical_v_rules)
                across_col_boundary = False
                if columns and not physical_v_rules:
                    for col in columns[:-1]:
                        if prev.font_bbox_device_pt[2] <= col.x1_pt <= c.font_bbox_device_pt[0]:
                            if gap >= 3.0:
                                across_col_boundary = True
                                break

                max_word_gap = max(6.0, 0.6 * prev.font_size_pt)

                if has_v_rule or across_col_boundary or (gap > max_word_gap and c_txt.strip()):
                    if curr_span_chars:
                        spans.append(self._create_span_object(curr_span_chars, span_counter))
                        span_counter += 1
                    curr_span_chars = [c] if c_txt.strip() else []
                else:
                    curr_span_chars.append(c)

            if curr_span_chars:
                spans.append(self._create_span_object(curr_span_chars, span_counter))
                span_counter += 1

        return spans

    def _create_span_object(self, span_chars: List[PaintedTextChar], span_idx: int) -> HeaderSpan:
        txt_tokens = []
        for idx, c in enumerate(span_chars):
            ch_txt = c.unicode_text or c.char_text
            if idx > 0:
                prev = span_chars[idx - 1]
                c_gap = c.origin_device_pt[0] - prev.font_bbox_device_pt[2]
                if c_gap >= max(0.8, 0.08 * prev.font_size_pt) and not ch_txt.startswith(" "):
                    txt_tokens.append(" ")
            txt_tokens.append(ch_txt)
        text = "".join(txt_tokens).strip()

        x0 = min(c.font_bbox_device_pt[0] for c in span_chars)
        y0 = min(c.font_bbox_device_pt[1] for c in span_chars)
        x1 = max(c.font_bbox_device_pt[2] for c in span_chars)
        y1 = max(c.font_bbox_device_pt[3] for c in span_chars)
        avg_base_y = float(np.mean([c.origin_device_pt[1] for c in span_chars]))

        min_cid = span_chars[0].char_id
        max_cid = span_chars[-1].char_id
        span_id = f"hspan_{min_cid}_{max_cid}"

        return HeaderSpan(
            span_id=span_id,
            text=text,
            bbox_pt=(x0, y0, x1, y1),
            baseline_y_pt=avg_base_y,
            chars=span_chars,
        )

    def _find_non_text_in_header(
        self,
        page_layer: PageByteLayer,
        col: ColumnModel,
        band_y0: float,
        band_y1: float,
    ) -> Optional[Tuple[float, float, float, float]]:
        cx0 = col.x0_pt - 1.5
        cx1 = col.x1_pt + 1.5

        for img in getattr(page_layer, "images", []):
            ib = img.bbox_device_pt
            if (cx0 <= ib[0] and ib[2] <= cx1 and band_y0 <= ib[1] and ib[3] <= band_y1):
                return (round(ib[0], 2), round(ib[1], 2), round(ib[2], 2), round(ib[3], 2))

        for g in getattr(page_layer, "non_text_glyphs", []):
            gb = g.get("bbox_pt") or g.get("bbox_device_pt")
            if gb and cx0 <= gb[0] and gb[2] <= cx1 and band_y0 <= gb[1] and gb[3] <= band_y1:
                return (round(gb[0], 2), round(gb[1], 2), round(gb[2], 2), round(gb[3], 2))

        cell_w = col.width_pt
        cell_h = abs(band_y1 - band_y0)
        for p in getattr(page_layer, "paths", []):
            pb = p.bbox_device_pt
            pw = pb[2] - pb[0]
            ph = pb[3] - pb[1]
            if pw <= 1.0 or ph <= 1.0:
                continue
            if pw >= 0.92 * cell_w and ph >= 0.85 * cell_h:
                continue
            if (
                cx0 <= pb[0]
                and pb[2] <= cx1
                and band_y0 - 1.0 <= pb[1]
                and pb[3] <= band_y1 + 1.0
                and 2.0 <= pw <= 40.0
                and 2.0 <= ph <= 40.0
            ):
                return (round(pb[0], 2), round(pb[1], 2), round(pb[2], 2), round(pb[3], 2))

        return None

    def _infer_semantic_header(
        self,
        page_layer: PageByteLayer,
        col: ColumnModel,
        columns: List[ColumnModel],
        band_y0: float,
    ) -> str:
        from pdf_analyzer.l3_topology.logical_rows import DATE_PATTERNS

        col_body_chars = [
            ch for ch in page_layer.chars
            if col.x0_pt - 1.0 <= ch.origin_device_pt[0] <= col.x1_pt + 1.0
            and ch.origin_device_pt[1] < band_y0
        ]

        sample_texts: List[str] = []
        if col_body_chars:
            lines = self.logical_rows.group_into_lines(col_body_chars)
            for l in lines[:15]:
                t = l.text.strip()
                if t:
                    sample_texts.append(t)

        date_matches = sum(1 for s in sample_texts if any(p.match(s) for p in DATE_PATTERNS) or re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", s, re.I))
        if date_matches >= max(1, len(sample_texts) // 3):
            if any(c.index != col.index and c.header_text and "date" in c.header_text.lower() for c in columns):
                return "Value Date"
            return "Date"

        if sample_texts and all(re.match(r"^\d{1,5}$", s) for s in sample_texts):
            return "S.No"

        has_amount = any(re.search(r"\d+\.\d{2}", s) for s in sample_texts)
        has_cr_dr = any(re.search(r"\b(Cr|Dr)\b", s, re.I) for s in sample_texts)
        if col.is_numeric or has_amount or has_cr_dr:
            if col.index == len(columns):
                return "Balance"
            if col.index == len(columns) - 1:
                return "Deposit" if len(columns) >= 6 else "Amount"
            if col.index == len(columns) - 2:
                return "Withdrawal"
            return "Amount"

        if sample_texts and any(re.search(r"\b(chq|ref|cheque|neft|rtgs|upi|txn)\b", s, re.I) for s in sample_texts):
            return "Chq / Ref No."

        avg_len = float(np.mean([len(s) for s in sample_texts])) if sample_texts else 0.0
        if avg_len > 12.0:
            return "Narration" if col.index <= 2 else "Description"

        num_cols = len(columns)
        idx = col.index - 1
        schemas = {
            7: ["Date", "Narration", "Chq / Ref No.", "Value Date", "Withdrawal", "Deposit", "Balance"],
            6: ["Date", "Narration", "Chq / Ref No.", "Withdrawal", "Deposit", "Balance"],
            5: ["Date", "Narration", "Withdrawal", "Deposit", "Balance"],
            4: ["Date", "Description", "Amount", "Balance"],
        }
        if num_cols in schemas and 0 <= idx < len(schemas[num_cols]):
            return schemas[num_cols][idx]

        return f"Column {col.index}"
