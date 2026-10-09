"""
PDF Graphics State and Text State Machine.
Tracks affine transformations (CTM, Tm, Tlm), clipping paths, line/stroke styles,
colorspaces, font sizes, spacing, and OCG visibility across q/Q nesting stacks.
"""

from __future__ import annotations
import math
from typing import Tuple, List, Optional, Any
from pdf_analyzer.l0_bytes.primitives import StrokeStyle, Color


class CTM:
    """Affine 2D transformation matrix: [a, b, c, d, e, f]."""
    __slots__ = ("a", "b", "c", "d", "e", "f")

    def __init__(self, a: float = 1.0, b: float = 0.0, c: float = 0.0, d: float = 1.0, e: float = 0.0, f: float = 0.0):
        self.a = float(a)
        self.b = float(b)
        self.c = float(c)
        self.d = float(d)
        self.e = float(e)
        self.f = float(f)

    @classmethod
    def identity(cls) -> CTM:
        return cls(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def multiply(self, other: CTM) -> CTM:
        """
        Matrix concatenation: self * other (PDF standard: [a b c d e f] * CTM).
        """
        return CTM(
            self.a * other.a + self.b * other.c,
            self.a * other.b + self.b * other.d,
            self.c * other.a + self.d * other.c,
            self.c * other.b + self.d * other.d,
            self.e * other.a + self.f * other.c + other.e,
            self.e * other.b + self.f * other.d + other.f,
        )

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        """Apply transformation to point (x, y)."""
        tx = self.a * x + self.c * y + self.e
        ty = self.b * x + self.d * y + self.f
        return (tx, ty)

    def transform_vector(self, dx: float, dy: float) -> Tuple[float, float]:
        """Apply transformation to directional vector without translation."""
        tx = self.a * dx + self.c * dy
        ty = self.b * dx + self.d * dy
        return (tx, ty)

    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverse(self) -> CTM:
        det = self.determinant()
        if abs(det) < 1e-12:
            return CTM.identity()
        inv_det = 1.0 / det
        return CTM(
            self.d * inv_det,
            -self.b * inv_det,
            -self.c * inv_det,
            self.a * inv_det,
            (self.c * self.f - self.d * self.e) * inv_det,
            (self.b * self.e - self.a * self.f) * inv_det,
        )

    def to_tuple(self) -> Tuple[float, float, float, float, float, float]:
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    def __repr__(self) -> str:
        return f"CTM({self.a:.4f}, {self.b:.4f}, {self.c:.4f}, {self.d:.4f}, {self.e:.4f}, {self.f:.4f})"


class TextState:
    """PDF Text State parameters: Tf, Tc, Tw, Tz, TL, Tr, Ts, Tm, Tlm."""
    __slots__ = (
        "font_name",
        "font_size",
        "char_spacing",
        "word_spacing",
        "horizontal_scaling",
        "leading",
        "rendering_mode",
        "rise",
        "text_matrix",
        "line_matrix",
    )

    def __init__(self):
        self.font_name: str = "Helvetica"
        self.font_size: float = 12.0
        self.char_spacing: float = 0.0  # Tc
        self.word_spacing: float = 0.0  # Tw
        self.horizontal_scaling: float = 100.0  # Tz in percent
        self.leading: float = 0.0  # TL
        self.rendering_mode: int = 0  # Tr
        self.rise: float = 0.0  # Ts
        self.text_matrix: CTM = CTM.identity()  # Tm
        self.line_matrix: CTM = CTM.identity()  # Tlm

    def clone(self) -> TextState:
        s = TextState()
        s.font_name = self.font_name
        s.font_size = self.font_size
        s.char_spacing = self.char_spacing
        s.word_spacing = self.word_spacing
        s.horizontal_scaling = self.horizontal_scaling
        s.leading = self.leading
        s.rendering_mode = self.rendering_mode
        s.rise = self.rise
        s.text_matrix = CTM(*self.text_matrix.to_tuple())
        s.line_matrix = CTM(*self.line_matrix.to_tuple())
        return s


class GraphicsState:
    """Complete graphics state preserved on q and restored on Q."""

    def __init__(self):
        self.ctm: CTM = CTM.identity()
        self.stroke_style: StrokeStyle = StrokeStyle(width_pt=1.0, cap=0, join=0, miter_limit=10.0, dash_pattern=(), dash_phase=0.0)
        self.stroke_color: Color = Color(space="DeviceGray", components=(0.0,))
        self.fill_color: Color = Color(space="DeviceGray", components=(0.0,))
        self.stroke_color_space: str = "DeviceGray"
        self.fill_color_space: str = "DeviceGray"
        self.stroke_alpha: float = 1.0
        self.fill_alpha: float = 1.0
        self.blend_mode: str = "Normal"
        self.clip_polygons: List[Any] = []
        self.clip_id: Optional[str] = None
        self.text_state: TextState = TextState()
        self.ocg_name: Optional[str] = None
        self.ocg_visible: bool = True

    def clone(self) -> GraphicsState:
        gs = GraphicsState()
        gs.ctm = CTM(*self.ctm.to_tuple())
        gs.stroke_style = StrokeStyle(
            width_pt=self.stroke_style.width_pt,
            cap=self.stroke_style.cap,
            join=self.stroke_style.join,
            miter_limit=self.stroke_style.miter_limit,
            dash_pattern=tuple(self.stroke_style.dash_pattern),
            dash_phase=self.stroke_style.dash_phase,
        )
        gs.stroke_color = Color(
            space=self.stroke_color.space,
            components=tuple(self.stroke_color.components),
            alpha=self.stroke_color.alpha,
        )
        gs.fill_color = Color(
            space=self.fill_color.space,
            components=tuple(self.fill_color.components),
            alpha=self.fill_color.alpha,
        )
        gs.stroke_color_space = self.stroke_color_space
        gs.fill_color_space = self.fill_color_space
        gs.stroke_alpha = self.stroke_alpha
        gs.fill_alpha = self.fill_alpha
        gs.blend_mode = self.blend_mode
        gs.clip_polygons = list(self.clip_polygons)
        gs.clip_id = self.clip_id
        gs.text_state = self.text_state.clone()
        gs.ocg_name = self.ocg_name
        gs.ocg_visible = self.ocg_visible
        return gs
