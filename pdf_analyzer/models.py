"""Data models and provenance tracking with high-precision values."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union, Tuple


MeasurementSource = Literal["content_stream", "pymupdf", "pdfplumber", "raster", "inferred"]


@dataclass
class ProvenanceValue:
    """Measured value with origin tracking, cross-check delta, and strict confidence."""
    value: Union[float, int, str, None]
    unit: str
    source: MeasurementSource = "content_stream"
    confidence: float = 1.0
    cross_check_delta: float = 0.0
    warning: Optional[str] = None
    alt_sources: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        val = self.value
        if isinstance(val, float):
            if self.unit == "pt":
                val = round(val, 3)
            elif self.unit == "mm":
                val = round(val, 2)
            elif self.unit == "px":
                val = round(val, 1)
            elif self.unit == "%":
                val = round(val, 3)
            else:
                val = round(val, 4)

        res = {
            "value": val,
            "unit": self.unit,
            "source": self.source,
            "confidence": round(self.confidence, 3),
            "cross_check_delta": round(self.cross_check_delta, 4)
        }
        if self.warning:
            res["warning"] = self.warning
        if self.alt_sources:
            res["alt_sources"] = self.alt_sources
        return res


@dataclass
class MultiUnitValue:
    """Stores full float precision internally; formats with strict decimal standards."""
    pt: float
    mm: float
    px: float
    rel_pct: float
    source: MeasurementSource = "content_stream"
    confidence: float = 1.0
    cross_check_delta: float = 0.0
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "pt": round(self.pt, 3),
            "mm": round(self.mm, 2),
            "px": round(self.px, 1),
            "rel_pct": round(self.rel_pct, 3),
            "source": self.source,
            "confidence": round(self.confidence, 3)
        }
        if self.cross_check_delta != 0.0:
            res["cross_check_delta"] = round(self.cross_check_delta, 4)
        if self.warning:
            res["warning"] = self.warning
        return res


@dataclass
class BoundingBox:
    """Bounding box in standardized Top-Left coordinates with 4-unit values."""
    x0: MultiUnitValue
    y0: MultiUnitValue
    x1: MultiUnitValue
    y1: MultiUnitValue
    width: MultiUnitValue
    height: MultiUnitValue

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x0": self.x0.to_dict(),
            "y0": self.y0.to_dict(),
            "x1": self.x1.to_dict(),
            "y1": self.y1.to_dict(),
            "width": self.width.to_dict(),
            "height": self.height.to_dict()
        }

    @property
    def raw_pt(self) -> Tuple[float, float, float, float]:
        """Raw unrounded float tuple (x0, y0, x1, y1)."""
        return (self.x0.pt, self.y0.pt, self.x1.pt, self.y1.pt)


@dataclass
class FontMetricsModel:
    """Font metrics extracted via fontTools or standard font tables."""
    font_name: str
    clean_family: str
    units_per_em: int = 1000
    ascender: float = 800.0
    descender: float = -200.0
    cap_height: float = 700.0
    x_height: float = 500.0
    avg_char_width: float = 500.0
    is_embedded: bool = False
    font_type: str = "TrueType"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_name": self.font_name,
            "clean_family": self.clean_family,
            "units_per_em": self.units_per_em,
            "ascender": round(self.ascender, 3),
            "descender": round(self.descender, 3),
            "cap_height": round(self.cap_height, 3),
            "x_height": round(self.x_height, 3),
            "avg_char_width": round(self.avg_char_width, 3),
            "is_embedded": self.is_embedded,
            "font_type": self.font_type
        }


@dataclass
class TextSpanModel:
    """Text span containing BOTH Font Box and tight Ink Box."""
    text: str
    # Primary: Tight Ink Box (tight glyph bounds)
    ink_box: BoundingBox
    # Secondary: Font Box (ascent/descent from font metrics)
    font_box: BoundingBox
    origin_point: Tuple[float, float]  # (baseline_x, baseline_y)
    baseline_y: MultiUnitValue
    font_name: str
    clean_font_family: str
    font_size_pt: float  # effective font size (Tm x CTM x nominal)
    nominal_font_size_pt: float
    is_bold: bool
    is_italic: bool
    is_monospace: bool
    is_serif: bool
    inferred_weight: str
    color_rgb: Tuple[int, int, int]
    color_hex: str
    anti_aliasing_corrected_hex: str
    opacity: float
    page_number: int
    char_boxes: List[Tuple[str, Tuple[float, float, float, float]]] = field(default_factory=list)
    font_metrics: Optional[FontMetricsModel] = None

    @property
    def bbox(self) -> BoundingBox:
        """Alias to ink_box for primary measurement compliance."""
        return self.ink_box

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "ink_box": self.ink_box.to_dict(),
            "font_box": self.font_box.to_dict(),
            "origin_point_pt": [round(self.origin_point[0], 3), round(self.origin_point[1], 3)],
            "baseline_y": self.baseline_y.to_dict(),
            "font_name": self.font_name,
            "clean_font_family": self.clean_font_family,
            "font_size_pt": round(self.font_size_pt, 3),
            "nominal_font_size_pt": round(self.nominal_font_size_pt, 3),
            "is_bold": self.is_bold,
            "is_italic": self.is_italic,
            "is_monospace": self.is_monospace,
            "is_serif": self.is_serif,
            "inferred_weight": self.inferred_weight,
            "color_rgb": list(self.color_rgb),
            "color_hex": self.color_hex,
            "anti_aliasing_corrected_hex": self.anti_aliasing_corrected_hex,
            "opacity": round(self.opacity, 3),
            "page_number": self.page_number,
            "font_metrics": self.font_metrics.to_dict() if self.font_metrics else None
        }


@dataclass
class PageMeta:
    page_number: int
    total_pages: int
    width: MultiUnitValue
    height: MultiUnitValue
    orientation: str
    rotation_deg: int
    cropbox: List[float]
    mediabox: List[float]
    dpi: int
    coordinate_system: str = "Top-Left origin (x=0, y=0 at top-left; x increases right, y increases down). Unified transform applied."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "total_pages": self.total_pages,
            "width": self.width.to_dict(),
            "height": self.height.to_dict(),
            "orientation": self.orientation,
            "rotation_deg": self.rotation_deg,
            "cropbox_pt": [round(c, 3) for c in self.cropbox],
            "mediabox_pt": [round(c, 3) for c in self.mediabox],
            "dpi": self.dpi,
            "coordinate_system": self.coordinate_system
        }


@dataclass
class LayoutTreeNode:
    """Node in the hierarchical page layout tree (layout_tree.json)."""
    id: str
    type: str
    page: int
    bbox: BoundingBox
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    member_ids: List[str] = field(default_factory=list)
    classifying_rule: str = "containment_and_whitespace"
    confidence: float = 1.0
    tightness_iou: float = 1.0
    leakage_pct: float = 0.0
    sibling_overlap_area: float = 0.0
    vertical_overshoot_pt: float = 0.0
    is_container: bool = False
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "page": self.page,
            "bbox": self.bbox.to_dict(),
            "parent": self.parent_id,
            "children": self.children_ids,
            "member_ids": self.member_ids,
            "classifying_rule": self.classifying_rule,
            "confidence": round(self.confidence, 3),
            "tightness_iou": round(self.tightness_iou, 4),
            "leakage_pct": round(self.leakage_pct, 4),
            "sibling_overlap_area": round(self.sibling_overlap_area, 4),
            "vertical_overshoot_pt": round(self.vertical_overshoot_pt, 4),
            "is_container": self.is_container,
            "attributes": self.attributes
        }


@dataclass
class GuideLine:
    """Guide line segment clipped to the bounding extent of its owners."""
    axis_type: Literal["vertical", "horizontal"]
    position_pt: float  # x for vertical, y for horizontal
    range_start_pt: float  # y0 for vertical, x0 for horizontal
    range_end_pt: float  # y1 for vertical, x1 for horizontal
    owner_id: str
    member_count: int = 1
    role: str = "alignment_axis"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "axis_type": self.axis_type,
            "position_pt": round(self.position_pt, 3),
            "range_start_pt": round(self.range_start_pt, 3),
            "range_end_pt": round(self.range_end_pt, 3),
            "owner_id": self.owner_id,
            "member_count": self.member_count,
            "role": self.role
        }


@dataclass
class PhysicalLineModel:
    """Physical rendered line inside the table grid."""
    line_index: int
    page_number: int
    baseline_y_pt: float
    ink_top_pt: float
    ink_bottom_pt: float
    height_pt: float
    pitch_to_next_pt: float = 0.0
    spans_count: int = 0
    text: str = ""
    cell_values: Dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_index": self.line_index,
            "page_number": self.page_number,
            "baseline_y_pt": round(self.baseline_y_pt, 3),
            "ink_top_pt": round(self.ink_top_pt, 3),
            "ink_bottom_pt": round(self.ink_bottom_pt, 3),
            "height_pt": round(self.height_pt, 3),
            "pitch_to_next_pt": round(self.pitch_to_next_pt, 3),
            "spans_count": self.spans_count,
            "text": self.text,
            "cell_values": self.cell_values
        }


@dataclass
class LogicalTransactionModel:
    """Logical bank transaction starting with an anchor date line."""
    tx_index: int
    page_number: int
    anchor_date: str
    lines_count: int
    y_top_pt: float
    y_bottom_pt: float
    height_pt: float
    gap_to_next_pt: float = 0.0
    baseline_to_baseline_pt: float = 0.0
    is_wrapped: bool = False
    description_lines: List[str] = field(default_factory=list)
    raw_cells: Dict[str, Any] = field(default_factory=dict)
    leading_space_indent_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_index": self.tx_index,
            "page_number": self.page_number,
            "anchor_date": self.anchor_date,
            "lines_count": self.lines_count,
            "y_top_pt": round(self.y_top_pt, 3),
            "y_bottom_pt": round(self.y_bottom_pt, 3),
            "height_pt": round(self.height_pt, 3),
            "gap_to_next_pt": round(self.gap_to_next_pt, 3),
            "baseline_to_baseline_pt": round(self.baseline_to_baseline_pt, 3),
            "is_wrapped": self.is_wrapped,
            "description_lines": self.description_lines,
            "raw_cells": self.raw_cells,
            "leading_space_indent_detected": self.leading_space_indent_detected
        }


@dataclass
class ColumnModel:
    """Detailed column model from multi-signal voting (S1-S5)."""
    index: int
    x0_pt: float
    x1_pt: float
    width_pt: float
    width: MultiUnitValue
    left_rule_id: str
    right_rule_id: str
    left_boundary_evidence: List[Dict[str, Any]] = field(default_factory=list)
    right_boundary_evidence: List[Dict[str, Any]] = field(default_factory=list)
    header_text: str = ""
    boundary_type: str = "single"  # single | double | virtual
    is_double_rule: bool = False
    double_rule_info: Optional[Dict[str, Any]] = None
    coverage_pct: float = 1.0
    is_spanning_header: bool = False
    child_column_indices: List[int] = field(default_factory=list)
    confidence: float = 1.0
    semantic_type: str = "generic"
    alignment: str = "left"

    @property
    def name(self) -> str:
        return self.header_text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "x0_pt": round(self.x0_pt, 3),
            "x1_pt": round(self.x1_pt, 3),
            "width_pt": round(self.width_pt, 3),
            "width": self.width.to_dict(),
            "left_rule_id": self.left_rule_id,
            "right_rule_id": self.right_rule_id,
            "left_boundary_evidence": self.left_boundary_evidence,
            "right_boundary_evidence": self.right_boundary_evidence,
            "header_text": self.header_text,
            "boundary_type": self.boundary_type,
            "is_double_rule": self.is_double_rule,
            "double_rule_info": self.double_rule_info,
            "coverage_pct": round(self.coverage_pct, 3),
            "is_spanning_header": self.is_spanning_header,
            "child_column_indices": self.child_column_indices,
            "confidence": round(self.confidence, 3),
            "semantic_type": self.semantic_type,
            "alignment": self.alignment
        }


@dataclass
class RowModel:
    """Detailed row model evaluated across R1-R5 models."""
    index: int
    row_type: str  # HEADER | OPENING_BALANCE | BODY | CONTINUATION | SUBTOTAL | CLOSING_BALANCE | PAGE_SUMMARY
    y0_pt: float
    y1_pt: float
    height_pt: float
    height: MultiUnitValue
    boundary_type: str = "ruled"  # ruled | virtual | zebra
    rule_info: Optional[Dict[str, Any]] = None
    gap_to_next_pt: float = 0.0
    is_estimated_bottom: bool = False
    text_lines: List[str] = field(default_factory=list)
    model_evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "row_type": self.row_type,
            "y0_pt": round(self.y0_pt, 3),
            "y1_pt": round(self.y1_pt, 3),
            "height_pt": round(self.height_pt, 3),
            "height": self.height.to_dict(),
            "boundary_type": self.boundary_type,
            "rule_info": self.rule_info,
            "gap_to_next_pt": round(self.gap_to_next_pt, 3),
            "is_estimated_bottom": self.is_estimated_bottom,
            "text_lines": self.text_lines,
            "model_evidence": self.model_evidence,
            "confidence": round(self.confidence, 3)
        }


@dataclass
class CellModel:
    """Precise cell model with inner edges, text lines, ink bbox, padding, and alignment."""
    cell_id: str
    row_index: int
    col_index: int
    bbox: BoundingBox
    raw_bbox_pt: Tuple[float, float, float, float]
    inner_bbox_pt: Tuple[float, float, float, float]
    content: List[TextSpanModel] = field(default_factory=list)
    joined_text: str = ""
    is_wrapped: bool = False
    line_count: int = 0
    ink_bbox_pt: Optional[Tuple[float, float, float, float]] = None
    padding_left_pt: float = 0.0
    padding_right_pt: float = 0.0
    padding_top_pt: float = 0.0
    padding_bottom_pt: float = 0.0
    padding_left: Optional[MultiUnitValue] = None
    padding_right: Optional[MultiUnitValue] = None
    padding_top: Optional[MultiUnitValue] = None
    padding_bottom: Optional[MultiUnitValue] = None
    alignment: str = "left"  # left | right | center | decimal
    alignment_offset_pt: float = 0.0
    vertical_position: str = "top"  # top | middle | bottom
    baseline_offset_from_bottom_pt: float = 0.0
    flags: Dict[str, bool] = field(default_factory=dict)
    numeric_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "bbox": self.bbox.to_dict(),
            "raw_bbox_pt": [round(v, 3) for v in self.raw_bbox_pt],
            "inner_bbox_pt": [round(v, 3) for v in self.inner_bbox_pt],
            "joined_text": self.joined_text,
            "is_wrapped": self.is_wrapped,
            "line_count": self.line_count,
            "ink_bbox_pt": [round(v, 3) for v in self.ink_bbox_pt] if self.ink_bbox_pt else None,
            "padding_left_pt": round(self.padding_left_pt, 3),
            "padding_right_pt": round(self.padding_right_pt, 3),
            "padding_top_pt": round(self.padding_top_pt, 3),
            "padding_bottom_pt": round(self.padding_bottom_pt, 3),
            "padding_left": self.padding_left.to_dict() if self.padding_left else None,
            "padding_right": self.padding_right.to_dict() if self.padding_right else None,
            "padding_top": self.padding_top.to_dict() if self.padding_top else None,
            "padding_bottom": self.padding_bottom.to_dict() if self.padding_bottom else None,
            "alignment": self.alignment,
            "alignment_offset_pt": round(self.alignment_offset_pt, 3),
            "vertical_position": self.vertical_position,
            "baseline_offset_from_bottom_pt": round(self.baseline_offset_from_bottom_pt, 3),
            "flags": self.flags,
            "numeric_info": self.numeric_info
        }


@dataclass
class MeasurementRecord:
    """Explicit measurement record tied to named anchors in the measurement ontology."""
    id: str
    from_anchor: str
    from_element: str
    to_anchor: str
    to_element: str
    axis: str  # x | y
    value_pt: float
    value_mm: float
    value_px: float
    source: str = "content_stream"
    confidence: float = 1.0
    definition_string: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from_anchor": self.from_anchor,
            "from_element": self.from_element,
            "to_anchor": self.to_anchor,
            "to_element": self.to_element,
            "axis": self.axis,
            "value_pt": round(self.value_pt, 3),
            "value_mm": round(self.value_mm, 2),
            "value_px": round(self.value_px, 1),
            "source": self.source,
            "confidence": round(self.confidence, 3),
            "definition_string": self.definition_string
        }


@dataclass
class GapRecord:
    """Gap matrix record for precise spacing and padding measurements."""
    id: str
    from_element: str
    to_element: str
    gap_type: str
    definition_code: str  # ink_to_ink | rule_to_rule | baseline_to_baseline | ink_to_rule | inner_to_inner
    value_pt: float
    value_mm: float
    value_px: float
    definition_string: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from_element": self.from_element,
            "to_element": self.to_element,
            "gap_type": self.gap_type,
            "definition_code": self.definition_code,
            "value_pt": round(self.value_pt, 3),
            "value_mm": round(self.value_mm, 2),
            "value_px": round(self.value_px, 1),
            "definition_string": self.definition_string
        }


@dataclass
class ConsistencyCheckResult:
    """Result of consistency and closure validation (C1-C6)."""
    check_id: str
    name: str
    passed: bool
    tolerance: float
    delta: float
    offending_ids: List[str] = field(default_factory=list)
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "passed": self.passed,
            "tolerance": self.tolerance,
            "delta": round(self.delta, 4),
            "offending_ids": self.offending_ids,
            "details": self.details
        }


