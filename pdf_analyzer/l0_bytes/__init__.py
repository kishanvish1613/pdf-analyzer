"""
L0 ByteLayer Package for PDF Design Analyzer.
Direct PDF content-stream parsing, graphics state tracking, glyph-accurate text geometry,
and device-space Shapely path vectorization with full provenance.
"""

from pdf_analyzer.l0_bytes.primitives import (
    ByteRange,
    StreamProvenance,
    Color,
    StrokeStyle,
    FontMetrics,
    PaintedPath,
    PaintedTextChar,
    InlineImageInstance,
    FormXObjectInstance,
    ClippingRegion,
    PageByteLayer,
)
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.state import GraphicsState, CTM, TextState
from pdf_analyzer.l0_bytes.geometry import (
    transform_point,
    transform_bbox,
    build_stroked_polygon,
    build_filled_polygon,
)

__all__ = [
    "ByteRange",
    "StreamProvenance",
    "Color",
    "StrokeStyle",
    "FontMetrics",
    "PaintedPath",
    "PaintedTextChar",
    "InlineImageInstance",
    "FormXObjectInstance",
    "ClippingRegion",
    "PageByteLayer",
    "ByteLayerExtractor",
    "GraphicsState",
    "CTM",
    "TextState",
    "transform_point",
    "transform_bbox",
    "build_stroked_polygon",
    "build_filled_polygon",
]
