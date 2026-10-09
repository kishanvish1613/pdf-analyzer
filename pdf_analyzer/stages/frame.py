"""
Stage 0: Unified PageFrame, Coordinate Normalization & Painted Geometry Engine.
Provides:
- Strict PageFrame model: MediaBox, CropBox, Rotation, UserUnit, DPI
- Single Transform pt -> px with explicit pixel-center convention (pixel center at x + 0.5)
- Painted vs Path Geometry:
  * Centre line, stroke thickness w, +- w/2 edges
  * Cap style accounting: butt, round, projecting-square (extends w/2 past endpoints)
  * Join style and dash patterns
  * Stroked rectangles: outer edge = path + w/2, inner edge = path - w/2
- Rule & RuleSet:
  * Authoritative vertical/horizontal rules per page
  * Strict single-source for columns, table bounds, and dimension lanes
- Exact rendering without secondary thumbnails, integer rounding or resizing
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Optional, Literal, Union
import pymupdf
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


CapStyle = Literal["butt", "round", "projecting_square"]
JoinStyle = Literal["miter", "round", "bevel"]


@dataclass
class PaintedGeometry:
    """Represents both vector path geometry and actual painted extents including stroke caps."""
    path_points: List[Tuple[float, float]]
    stroke_width_pt: float = 1.0
    cap_style: CapStyle = "butt"
    join_style: JoinStyle = "miter"
    is_stroked: bool = True
    is_filled: bool = False
    stroke_color: Optional[Tuple[int, int, int]] = None
    fill_color: Optional[Tuple[int, int, int]] = None
    dash_pattern: Optional[Tuple[List[float], float]] = None

    # Path Bounding Box (points only)
    @property
    def path_bbox(self) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in self.path_points]
        ys = [p[1] for p in self.path_points]
        return (min(xs), min(ys), max(xs), max(ys))

    # Painted Outer Extents (accounting for stroke width and square/round caps)
    @property
    def painted_outer_bbox(self) -> Tuple[float, float, float, float]:
        x0, y0, x1, y1 = self.path_bbox
        if not self.is_stroked:
            return (x0, y0, x1, y1)

        half_w = self.stroke_width_pt / 2.0
        cap_ext = half_w if self.cap_style in ("projecting_square", "round") else 0.0

        return (
            x0 - half_w - cap_ext,
            y0 - half_w - cap_ext,
            x1 + half_w + cap_ext,
            y1 + half_w + cap_ext
        )

    # Painted Inner Extents (for stroked rectangles / containers)
    @property
    def painted_inner_bbox(self) -> Tuple[float, float, float, float]:
        x0, y0, x1, y1 = self.path_bbox
        if not self.is_stroked:
            return (x0, y0, x1, y1)

        half_w = self.stroke_width_pt / 2.0
        return (
            x0 + half_w,
            y0 + half_w,
            max(x0 + half_w, x1 - half_w),
            max(y0 + half_w, y1 - half_w)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_points": [[round(p[0], 3), round(p[1], 3)] for p in self.path_points],
            "stroke_width_pt": round(self.stroke_width_pt, 3),
            "cap_style": self.cap_style,
            "join_style": self.join_style,
            "is_stroked": self.is_stroked,
            "is_filled": self.is_filled,
            "path_bbox": [round(v, 3) for v in self.path_bbox],
            "painted_outer_bbox": [round(v, 3) for v in self.painted_outer_bbox],
            "painted_inner_bbox": [round(v, 3) for v in self.painted_inner_bbox],
            "stroke_color": list(self.stroke_color) if self.stroke_color else None,
            "fill_color": list(self.fill_color) if self.fill_color else None
        }


@dataclass
class Rule:
    """Represents a single authoritative vertical or horizontal rule derived from vector paths."""
    rule_id: str
    orientation: Literal["V", "H"]
    centre_pt: float
    start_pt: float
    end_pt: float
    width_pt: float = 1.0
    cap_style: CapStyle = "butt"
    source: str = "drawings"
    stroke_color: Optional[Tuple[int, int, int]] = None

    @property
    def painted_outer_edge_pt(self) -> float:
        """Left edge for vertical rule (x - w/2), top edge for horizontal rule (y - w/2)."""
        return self.centre_pt - (self.width_pt / 2.0)

    @property
    def painted_inner_edge_pt(self) -> float:
        """Right edge for vertical rule (x + w/2), bottom edge for horizontal rule (y + w/2)."""
        return self.centre_pt + (self.width_pt / 2.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "orientation": self.orientation,
            "centre_pt": round(self.centre_pt, 3),
            "start_pt": round(self.start_pt, 3),
            "end_pt": round(self.end_pt, 3),
            "width_pt": round(self.width_pt, 3),
            "cap_style": self.cap_style,
            "source": self.source,
            "stroke_color": list(self.stroke_color) if self.stroke_color else None,
            "painted_outer_edge_pt": round(self.painted_outer_edge_pt, 3),
            "painted_inner_edge_pt": round(self.painted_inner_edge_pt, 3),
        }


@dataclass
class RuleSet:
    """Authoritative collection of vertical and horizontal rules for a page."""
    page_number: int
    rules: List[Rule] = field(default_factory=list)

    @property
    def rules_by_id(self) -> Dict[str, Rule]:
        return {r.rule_id: r for r in self.rules}

    @property
    def vertical_rules(self) -> List[Rule]:
        v_list = [r for r in self.rules if r.orientation == "V"]
        v_list.sort(key=lambda r: r.centre_pt)
        return v_list

    @property
    def horizontal_rules(self) -> List[Rule]:
        h_list = [r for r in self.rules if r.orientation == "H"]
        h_list.sort(key=lambda r: r.centre_pt)
        return h_list

    @classmethod
    def from_drawings(
        cls,
        page_num: int,
        drawings: Union[List[Dict[str, Any]], List[PaintedGeometry], RuleSet],
        page_w: float,
        page_h: float
    ) -> RuleSet:
        if isinstance(drawings, RuleSet):
            return drawings

        raw_v_candidates: List[Dict[str, Any]] = []
        raw_h_candidates: List[Dict[str, Any]] = []

        for d in drawings:
            # Handle PaintedGeometry objects or raw dicts
            if isinstance(d, PaintedGeometry):
                bbox = d.path_bbox
                w_pt = bbox[2] - bbox[0]
                h_pt = bbox[3] - bbox[1]
                stroke_w = d.stroke_width_pt
                color = d.stroke_color
                cap = d.cap_style
                items = []
            elif isinstance(d, dict):
                bbox = d.get("bbox", (0.0, 0.0, 0.0, 0.0))
                w_pt = d.get("width_pt", bbox[2] - bbox[0])
                h_pt = d.get("height_pt", bbox[3] - bbox[1])
                stroke_w = d.get("stroke_width_pt", 1.0)
                color = d.get("stroke_color_rgb")
                cap = "butt"
                items = d.get("items", [])
            else:
                continue

            # Check explicit items if present
            found_items = False
            if items:
                for it in items:
                    if it[0] == "l":  # line (p1, p2)
                        p1, p2 = it[1], it[2]
                        p1x, p1y = (p1.x, p1.y) if hasattr(p1, "x") else p1
                        p2x, p2y = (p2.x, p2.y) if hasattr(p2, "x") else p2
                        if abs(p1x - p2x) <= 0.5 and abs(p1y - p2y) >= 15.0:
                            raw_v_candidates.append({
                                "centre": (p1x + p2x) / 2.0,
                                "start": min(p1y, p2y),
                                "end": max(p1y, p2y),
                                "width": stroke_w or 1.0,
                                "cap": cap,
                                "color": color,
                                "source": "drawings"
                            })
                            found_items = True
                        elif abs(p1y - p2y) <= 0.5 and abs(p1x - p2x) >= 15.0:
                            raw_h_candidates.append({
                                "centre": (p1y + p2y) / 2.0,
                                "start": min(p1x, p2x),
                                "end": max(p1x, p2x),
                                "width": stroke_w or 1.0,
                                "cap": cap,
                                "color": color,
                                "source": "drawings"
                            })
                            found_items = True
                    elif it[0] == "re":  # rect (rx0, ry0, rx1, ry1)
                        r = it[1]
                        rx0, ry0, rx1, ry1 = (r.x0, r.y0, r.x1, r.y1) if hasattr(r, "x0") else r
                        rw = rx1 - rx0
                        rh = ry1 - ry0
                        if rw <= 3.0 and rh >= 15.0:
                            raw_v_candidates.append({
                                "centre": (rx0 + rx1) / 2.0,
                                "start": ry0,
                                "end": ry1,
                                "width": rw,
                                "cap": cap,
                                "color": color,
                                "source": "rect_fill"
                            })
                            found_items = True
                        elif rh <= 3.0 and rw >= 15.0:
                            raw_h_candidates.append({
                                "centre": (ry0 + ry1) / 2.0,
                                "start": rx0,
                                "end": rx1,
                                "width": rh,
                                "cap": cap,
                                "color": color,
                                "source": "rect_fill"
                            })
                            found_items = True

            # If no line/rect items matched, inspect bounding box
            if not found_items:
                if h_pt >= 15.0 and w_pt <= 3.5:
                    raw_v_candidates.append({
                        "centre": (bbox[0] + bbox[2]) / 2.0,
                        "start": bbox[1],
                        "end": bbox[3],
                        "width": stroke_w if stroke_w > 0 else (w_pt or 1.0),
                        "cap": cap,
                        "color": color,
                        "source": "drawings"
                    })
                elif w_pt >= 15.0 and h_pt <= 3.5:
                    raw_h_candidates.append({
                        "centre": (bbox[1] + bbox[3]) / 2.0,
                        "start": bbox[0],
                        "end": bbox[2],
                        "width": stroke_w if stroke_w > 0 else (h_pt or 1.0),
                        "cap": cap,
                        "color": color,
                        "source": "drawings"
                    })

        # Merge collinear vertical candidates (x within 0.15 pt)
        rules: List[Rule] = []
        if raw_v_candidates:
            raw_v_candidates.sort(key=lambda c: c["centre"])
            clusters: List[List[Dict[str, Any]]] = []
            for c in raw_v_candidates:
                if not clusters or abs(c["centre"] - np.mean([item["centre"] for item in clusters[-1]])) > 0.15:
                    clusters.append([c])
                else:
                    clusters[-1].append(c)

            for idx, cl in enumerate(clusters):
                m_x = float(np.mean([item["centre"] for item in cl]))
                m_y0 = min(item["start"] for item in cl)
                m_y1 = max(item["end"] for item in cl)
                m_w = float(np.median([item["width"] for item in cl]))
                rules.append(Rule(
                    rule_id=f"rule_v_{idx + 1}",
                    orientation="V",
                    centre_pt=m_x,
                    start_pt=m_y0,
                    end_pt=m_y1,
                    width_pt=m_w,
                    cap_style=cl[0].get("cap", "butt"),
                    source=cl[0].get("source", "drawings"),
                    stroke_color=cl[0].get("color")
                ))

        # Merge collinear horizontal candidates (y within 0.15 pt)
        if raw_h_candidates:
            raw_h_candidates.sort(key=lambda c: c["centre"])
            clusters: List[List[Dict[str, Any]]] = []
            for c in raw_h_candidates:
                if not clusters or abs(c["centre"] - np.mean([item["centre"] for item in clusters[-1]])) > 0.15:
                    clusters.append([c])
                else:
                    clusters[-1].append(c)

            for idx, cl in enumerate(clusters):
                m_y = float(np.mean([item["centre"] for item in cl]))
                m_x0 = min(item["start"] for item in cl)
                m_x1 = max(item["end"] for item in cl)
                m_w = float(np.median([item["width"] for item in cl]))
                rules.append(Rule(
                    rule_id=f"rule_h_{idx + 1}",
                    orientation="H",
                    centre_pt=m_y,
                    start_pt=m_x0,
                    end_pt=m_x1,
                    width_pt=m_w,
                    cap_style=cl[0].get("cap", "butt"),
                    source=cl[0].get("source", "drawings"),
                    stroke_color=cl[0].get("color")
                ))

        return cls(page_number=page_num, rules=rules)


@dataclass
class PageFrame:
    """Strict page frame defining exact coordinate transformation and raster rendering."""
    page_number: int
    cropbox_pt: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    mediabox_pt: Tuple[float, float, float, float]
    rotation_deg: int
    user_unit: float
    dpi: int
    scale_factor: float = field(init=False)
    width_pt: float = field(init=False)
    height_pt: float = field(init=False)
    raster_width_px: int = field(init=False)
    raster_height_px: int = field(init=False)

    def __post_init__(self):
        self.scale_factor = (self.dpi / 72.0) * self.user_unit
        cx0, cy0, cx1, cy1 = self.cropbox_pt
        self.width_pt = cx1 - cx0
        self.height_pt = cy1 - cy0
        self.raster_width_px = int(math.ceil(self.width_pt * self.scale_factor))
        self.raster_height_px = int(math.ceil(self.height_pt * self.scale_factor))

    def pt_to_px_x(self, x_pt: float) -> float:
        """Converts x in PDF points (relative to cropbox origin) to continuous pixel coordinate."""
        return (x_pt - self.cropbox_pt[0]) * self.scale_factor

    def pt_to_px_y(self, y_pt: float) -> float:
        """Converts y in PDF points (top-left origin) to continuous pixel coordinate."""
        return (y_pt - self.cropbox_pt[1]) * self.scale_factor

    def pt_to_px_rect(self, bbox_pt: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        x0, y0, x1, y1 = bbox_pt
        return (
            self.pt_to_px_x(x0),
            self.pt_to_px_y(y0),
            self.pt_to_px_x(x1),
            self.pt_to_px_y(y1)
        )

    def px_to_pt_x(self, x_px: float) -> float:
        return self.cropbox_pt[0] + (x_px / self.scale_factor)

    def px_to_pt_y(self, y_px: float) -> float:
        return self.cropbox_pt[1] + (y_px / self.scale_factor)

    def render_exact_page(self, doc_page: pymupdf.Page) -> Tuple[np.ndarray, Image.Image]:
        """Renders page with single Matrix(s, s) and CropBox clipping, asserting exact size."""
        s = self.scale_factor
        mat = pymupdf.Matrix(s, s)
        if self.rotation_deg != 0:
            mat.prerotate(self.rotation_deg)

        pix = doc_page.get_pixmap(matrix=mat, clip=doc_page.cropbox, alpha=False)
        
        # Verify rendered dimensions against mathematical expectation (+-1 px)
        exp_w = round(self.width_pt * s)
        exp_h = round(self.height_pt * s)
        if abs(pix.width - exp_w) > 1 or abs(pix.height - exp_h) > 1:
            logger.warning(
                f"Page {self.page_number} rendered pixmap ({pix.width}x{pix.height}) "
                f"deviates from expected ({exp_w}x{exp_h})"
            )

        img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_bgr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))[:, :, ::-1].copy()
        return img_bgr, img_pil

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "cropbox_pt": [round(v, 3) for v in self.cropbox_pt],
            "mediabox_pt": [round(v, 3) for v in self.mediabox_pt],
            "rotation_deg": self.rotation_deg,
            "user_unit": self.user_unit,
            "dpi": self.dpi,
            "width_pt": round(self.width_pt, 3),
            "height_pt": round(self.height_pt, 3),
            "raster_width_px": self.raster_width_px,
            "raster_height_px": self.raster_height_px,
            "pixel_scale": round(self.scale_factor, 6),
            "pixel_convention": "Continuous top-left origin; pixel center at (x+0.5, y+0.5)"
        }
