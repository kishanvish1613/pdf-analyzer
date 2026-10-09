"""
L0 ByteLayer Primitives.
Defines immutable data structures representing direct PDF content-stream objects,
graphics state parameters, painted vectors, glyph instances, and provenance tags.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Any


@dataclass(frozen=True)
class ByteRange:
    start_offset: int
    end_offset: int

    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start_offset, "end": self.end_offset}


@dataclass(frozen=True)
class StreamProvenance:
    stream_name: str
    byte_range: ByteRange
    operator_index: int
    operator_name: str
    xobject_stack: Tuple[str, ...] = ()
    marked_content_tag: Optional[str] = None
    mcid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stream_name": self.stream_name,
            "byte_range": self.byte_range.to_dict(),
            "operator_index": self.operator_index,
            "operator_name": self.operator_name,
            "xobject_stack": list(self.xobject_stack),
            "marked_content_tag": self.marked_content_tag,
            "mcid": self.mcid,
        }


@dataclass(frozen=True)
class Color:
    space: str  # 'DeviceGray', 'DeviceRGB', 'DeviceCMYK', 'ICCBased', etc.
    components: Tuple[float, ...]
    alpha: float = 1.0

    @property
    def rgb(self) -> Tuple[float, float, float]:
        """Convert any color to normalized RGB (0.0 - 1.0)."""
        if self.space == "DeviceGray" and len(self.components) >= 1:
            g = max(0.0, min(1.0, self.components[0]))
            return (g, g, g)
        elif self.space == "DeviceRGB" and len(self.components) >= 3:
            return (
                max(0.0, min(1.0, self.components[0])),
                max(0.0, min(1.0, self.components[1])),
                max(0.0, min(1.0, self.components[2])),
            )
        elif self.space == "DeviceCMYK" and len(self.components) >= 4:
            c, m, y, k = [max(0.0, min(1.0, v)) for v in self.components[:4]]
            r = (1.0 - c) * (1.0 - k)
            g = (1.0 - m) * (1.0 - k)
            b = (1.0 - y) * (1.0 - k)
            return (r, g, b)
        elif len(self.components) == 1:
            g = max(0.0, min(1.0, self.components[0]))
            return (g, g, g)
        elif len(self.components) >= 3:
            return (
                max(0.0, min(1.0, self.components[0])),
                max(0.0, min(1.0, self.components[1])),
                max(0.0, min(1.0, self.components[2])),
            )
        return (0.0, 0.0, 0.0)

    @property
    def hex(self) -> str:
        r, g, b = self.rgb
        return f"#{int(round(r * 255)):02x}{int(round(g * 255)):02x}{int(round(b * 255)):02x}"

    def to_hex(self) -> str:
        return self.hex

    def to_dict(self) -> Dict[str, Any]:
        return {
            "space": self.space,
            "components": list(self.components),
            "alpha": self.alpha,
            "hex": self.hex,
        }


@dataclass(frozen=True)
class StrokeStyle:
    width_pt: float
    cap: int = 0  # 0: Butt, 1: Round, 2: Projecting Square
    join: int = 0  # 0: Miter, 1: Round, 2: Bevel
    miter_limit: float = 10.0
    dash_pattern: Tuple[float, ...] = ()
    dash_phase: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width_pt": self.width_pt,
            "cap": self.cap,
            "join": self.join,
            "miter_limit": self.miter_limit,
            "dash_pattern": list(self.dash_pattern),
            "dash_phase": self.dash_phase,
        }


@dataclass
class FontMetrics:
    font_name: str
    base_font: str
    subset_prefix: Optional[str] = None
    clean_family: str = ""
    is_embedded: bool = False
    is_type3: bool = False
    is_type0: bool = False
    font_type: str = "TrueType"
    units_per_em: float = 1000.0
    ascent: float = 800.0
    descent: float = -200.0
    cap_height: float = 700.0
    x_height: float = 500.0
    bbox: Tuple[float, float, float, float] = (-200.0, -200.0, 1200.0, 900.0)
    default_width: float = 1000.0
    widths: Dict[int, float] = field(default_factory=dict)
    glyph_bboxes: Dict[int, Tuple[float, float, float, float]] = field(default_factory=dict)
    to_unicode_map: Dict[int, str] = field(default_factory=dict)
    missing_glyphs: List[str] = field(default_factory=list)
    fallback_font: str = "Helvetica"
    expected_width_error_pt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_name": self.font_name,
            "base_font": self.base_font,
            "subset_prefix": self.subset_prefix,
            "clean_family": self.clean_family or self.base_font,
            "is_embedded": self.is_embedded,
            "is_type3": self.is_type3,
            "is_type0": self.is_type0,
            "font_type": self.font_type,
            "units_per_em": self.units_per_em,
            "ascent": self.ascent,
            "descent": self.descent,
            "cap_height": self.cap_height,
            "x_height": self.x_height,
            "bbox": list(self.bbox),
            "default_width": self.default_width,
            "widths_count": len(self.widths),
            "to_unicode_count": len(self.to_unicode_map),
            "missing_glyphs_count": len(self.missing_glyphs),
            "fallback_font": self.fallback_font,
            "expected_width_error_pt": round(self.expected_width_error_pt, 4),
        }


@dataclass
class PaintedPath:
    path_id: str
    segments: List[Tuple[Any, ...]]  # ('m', x, y), ('l', x, y), ('c', x1,y1,x2,y2,x3,y3), ('re', x,y,w,h), ('h',)
    stroke: Optional[StrokeStyle] = None
    stroke_color: Optional[Color] = None
    fill_rule: Optional[str] = None  # 'nonzero', 'even-odd', or None
    fill_color: Optional[Color] = None
    ctm: Tuple[float, float, float, float, float, float] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    bbox_device_pt: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    painted_bbox_device_pt: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    shapely_geom: Any = None
    clipping_id: Optional[str] = None
    provenance: Optional[StreamProvenance] = None
    ocg_name: Optional[str] = None
    ocg_visible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "segments": [list(s) for s in self.segments],
            "stroke": self.stroke.to_dict() if self.stroke else None,
            "stroke_color": self.stroke_color.to_dict() if self.stroke_color else None,
            "fill_rule": self.fill_rule,
            "fill_color": self.fill_color.to_dict() if self.fill_color else None,
            "ctm": list(self.ctm),
            "bbox_device_pt": list(self.bbox_device_pt),
            "painted_bbox_device_pt": list(self.painted_bbox_device_pt),
            "clipping_id": self.clipping_id,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "ocg_name": self.ocg_name,
            "ocg_visible": self.ocg_visible,
        }


@dataclass
class PaintedTextChar:
    char_id: str
    char_code: int
    char_text: str
    unicode_text: str
    font_name: str
    font_size_pt: float
    text_matrix: Tuple[float, float, float, float, float, float]
    ctm: Tuple[float, float, float, float, float, float]
    origin_device_pt: Tuple[float, float]
    advance_pt: float
    font_bbox_device_pt: Tuple[float, float, float, float]
    ink_bbox_device_pt: Tuple[float, float, float, float]
    fill_color: Optional[Color] = None
    stroke_color: Optional[Color] = None
    rendering_mode: int = 0
    char_spacing_pt: float = 0.0
    word_spacing_pt: float = 0.0
    horiz_scaling: float = 100.0
    rise_pt: float = 0.0
    clipping_id: Optional[str] = None
    provenance: Optional[StreamProvenance] = None
    ocg_name: Optional[str] = None
    ocg_visible: bool = True

    @property
    def baseline_y(self) -> float:
        return self.origin_device_pt[1]

    @property
    def baseline_y_pt(self) -> float:
        return self.origin_device_pt[1]

    @property
    def origin_x(self) -> float:
        return self.origin_device_pt[0]

    @property
    def origin_y(self) -> float:
        return self.origin_device_pt[1]

    @property
    def x0(self) -> float:
        return self.ink_bbox_device_pt[0]

    @property
    def y0(self) -> float:
        return self.ink_bbox_device_pt[1]

    @property
    def x1(self) -> float:
        return self.ink_bbox_device_pt[2]

    @property
    def y1(self) -> float:
        return self.ink_bbox_device_pt[3]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "char_id": self.char_id,
            "char_code": self.char_code,
            "char_text": self.char_text,
            "unicode_text": self.unicode_text,
            "font_name": self.font_name,
            "font_size_pt": self.font_size_pt,
            "text_matrix": list(self.text_matrix),
            "ctm": list(self.ctm),
            "origin_device_pt": list(self.origin_device_pt),
            "advance_pt": self.advance_pt,
            "font_bbox_device_pt": list(self.font_bbox_device_pt),
            "ink_bbox_device_pt": list(self.ink_bbox_device_pt),
            "fill_color": self.fill_color.to_dict() if self.fill_color else None,
            "stroke_color": self.stroke_color.to_dict() if self.stroke_color else None,
            "rendering_mode": self.rendering_mode,
            "char_spacing_pt": self.char_spacing_pt,
            "word_spacing_pt": self.word_spacing_pt,
            "horiz_scaling": self.horiz_scaling,
            "rise_pt": self.rise_pt,
            "clipping_id": self.clipping_id,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "ocg_name": self.ocg_name,
            "ocg_visible": self.ocg_visible,
        }


@dataclass
class InlineImageInstance:
    image_id: str
    width_px: int
    height_px: int
    bits_per_component: int
    color_space: str
    ctm: Tuple[float, float, float, float, float, float]
    bbox_device_pt: Tuple[float, float, float, float]
    provenance: Optional[StreamProvenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "bits_per_component": self.bits_per_component,
            "color_space": self.color_space,
            "ctm": list(self.ctm),
            "bbox_device_pt": list(self.bbox_device_pt),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass
class FormXObjectInstance:
    xobject_id: str
    matrix: Tuple[float, float, float, float, float, float]
    bbox_pt: Tuple[float, float, float, float]
    paths_count: int
    chars_count: int
    provenance: Optional[StreamProvenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xobject_id": self.xobject_id,
            "matrix": list(self.matrix),
            "bbox_pt": list(self.bbox_pt),
            "paths_count": self.paths_count,
            "chars_count": self.chars_count,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass
class ClippingRegion:
    clip_id: str
    path_segments: List[Tuple[Any, ...]]
    winding_rule: str  # 'nonzero' or 'even-odd'
    shapely_geom: Any
    parent_clip_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "segments_count": len(self.path_segments),
            "winding_rule": self.winding_rule,
            "parent_clip_id": self.parent_clip_id,
        }


@dataclass
class PageByteLayer:
    page_number: int
    mediabox_pt: Tuple[float, float, float, float]
    cropbox_pt: Tuple[float, float, float, float]
    rotation_deg: int
    paths: List[PaintedPath] = field(default_factory=list)
    chars: List[PaintedTextChar] = field(default_factory=list)
    images: List[InlineImageInstance] = field(default_factory=list)
    xobjects: List[FormXObjectInstance] = field(default_factory=list)
    clips: Dict[str, ClippingRegion] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    non_text_glyphs: List[Dict[str, Any]] = field(default_factory=list)
    fonts: Dict[str, FontMetrics] = field(default_factory=dict)
    pdf_path: Optional[str] = None

    @property
    def cropbox(self) -> Tuple[float, float, float, float]:
        return self.cropbox_pt

    @property
    def mediabox(self) -> Tuple[float, float, float, float]:
        return self.mediabox_pt

    @property
    def painted_paths(self) -> List[PaintedPath]:
        return self.paths

    @property
    def text_chars(self) -> List[PaintedTextChar]:
        return self.chars

    @property
    def width_pt(self) -> float:
        return abs(self.cropbox_pt[2] - self.cropbox_pt[0])

    @property
    def height_pt(self) -> float:
        return abs(self.cropbox_pt[3] - self.cropbox_pt[1])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "mediabox_pt": list(self.mediabox_pt),
            "cropbox_pt": list(self.cropbox_pt),
            "rotation_deg": self.rotation_deg,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "paths": [p.to_dict() for p in self.paths],
            "chars": [c.to_dict() for c in self.chars],
            "images": [img.to_dict() for img in self.images],
            "xobjects": [x.to_dict() for x in self.xobjects],
            "clips": {k: v.to_dict() for k, v in self.clips.items()},
            "non_text_glyphs": list(self.non_text_glyphs),
            "fonts": {k: v.to_dict() for k, v in self.fonts.items()},
            "errors": list(self.errors),
        }
