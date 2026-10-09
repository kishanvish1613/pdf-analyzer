"""Unified coordinate transformation and unit conversion utilities.

Standard PDF coordinate system:
- Bottom-left PDF native coordinates (Y increases UP)
- Mediabox & Cropbox offsets (x_offset, y_offset)
- Page Rotation (0, 90, 180, 270 degrees)
- Output: Standardized Top-Left Origin (X increases RIGHT, Y increases DOWN)

All overlays, measurements, and bounding boxes in the analyzer must pass through CoordinateTransform.
"""

from typing import Tuple, List
from pdf_analyzer.models import MultiUnitValue, BoundingBox, MeasurementSource


PT_TO_MM: float = 25.4 / 72.0
MM_TO_PT: float = 72.0 / 25.4


def pt_to_mm(pt: float) -> float:
    """Convert points to millimeters (exact float precision)."""
    return pt * PT_TO_MM


def mm_to_pt(mm: float) -> float:
    """Convert millimeters to points (exact float precision)."""
    return mm * MM_TO_PT


def pt_to_px(pt: float, dpi: int = 600) -> float:
    """Convert points to pixels at given DPI."""
    return pt * (dpi / 72.0)


def px_to_pt(px: float, dpi: int = 600) -> float:
    """Convert pixels at given DPI to points."""
    return px / (dpi / 72.0)


def to_top_left_point(x: float, y: float, cropbox: Tuple[float, float, float, float] | List[float]) -> Tuple[float, float]:
    """Convert bottom-up native PDF point (x, y) to standardized top-left CropBox origin (Rule 6)."""
    cb_x0, cb_y0, cb_x1, cb_y1 = cropbox
    return (float(x - cb_x0), float(cb_y1 - y))


def to_top_left_bbox(
    bbox: Tuple[float, float, float, float] | List[float],
    cropbox: Tuple[float, float, float, float] | List[float],
) -> Tuple[float, float, float, float]:
    """Convert bottom-up native PDF bbox [x0, y0, x1, y1] to standardized top-left CropBox origin (Rule 6).
    Page height is taken authoritative from cropbox[3] (or cb_y1 - cb_y0).
    """
    cb_x0, cb_y0, cb_x1, cb_y1 = cropbox
    x0, y0, x1, y1 = bbox
    min_x = float(min(x0, x1) - cb_x0)
    max_x = float(max(x0, x1) - cb_x0)
    tl_y0 = float(cb_y1 - max(y0, y1))
    tl_y1 = float(cb_y1 - min(y0, y1))
    return (min_x, tl_y0, max_x, tl_y1)


class CoordinateTransform:
    """Single authoritative coordinate transform handler for PDF pages.

    Handles mediabox vs cropbox origin, page rotation, and maps native PDF points
    to standardized top-left origin coordinates.
    """

    def __init__(
        self,
        cropbox: List[float],
        mediabox: List[float],
        rotation: int = 0,
        dpi: int = 600
    ):
        self.cropbox = cropbox
        self.mediabox = mediabox
        self.rotation = rotation % 360
        self.dpi = dpi

        # Cropbox bounds in native PDF coords
        self.cb_x0, self.cb_y0, self.cb_x1, self.cb_y1 = cropbox
        self.raw_width = abs(self.cb_x1 - self.cb_x0)
        self.raw_height = abs(self.cb_y1 - self.cb_y0)

        # Swapped dimensions if rotated by 90 or 270
        if self.rotation in (90, 270):
            self.page_width = self.raw_height
            self.page_height = self.raw_width
        else:
            self.page_width = self.raw_width
            self.page_height = self.raw_height

    def native_to_top_left_point(self, x: float, y: float) -> Tuple[float, float]:
        """Convert PyMuPDF point (x, y) with cropbox offset and rotation to standardized top-left (x_tl, y_tl)."""
        nx = x - self.cb_x0
        ny = y - self.cb_y0

        if self.rotation == 0:
            tl_x = nx
            tl_y = ny
        elif self.rotation == 90:
            tl_x = ny
            tl_y = self.raw_width - nx
        elif self.rotation == 180:
            tl_x = self.raw_width - nx
            tl_y = self.raw_height - ny
        elif self.rotation == 270:
            tl_x = self.raw_height - ny
            tl_y = nx
        else:
            tl_x = nx
            tl_y = ny

        return (tl_x, tl_y)

    def native_to_top_left_bbox(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float
    ) -> Tuple[float, float, float, float]:
        """Convert a native PDF bounding box (x0, y0, x1, y1) to standardized top-left bbox."""
        p1_x, p1_y = self.native_to_top_left_point(x0, y0)
        p2_x, p2_y = self.native_to_top_left_point(x1, y1)
        p3_x, p3_y = self.native_to_top_left_point(x0, y1)
        p4_x, p4_y = self.native_to_top_left_point(x1, y0)

        min_x = min(p1_x, p2_x, p3_x, p4_x)
        max_x = max(p1_x, p2_x, p3_x, p4_x)
        min_y = min(p1_y, p2_y, p3_y, p4_y)
        max_y = max(p1_y, p2_y, p3_y, p4_y)

        return (min_x, min_y, max_x, max_y)

    def top_left_to_pixel_bbox(
        self,
        bbox_pt: Tuple[float, float, float, float]
    ) -> Tuple[int, int, int, int]:
        """Convert top-left point bbox to pixel coordinates at configured DPI."""
        scale = self.dpi / 72.0
        x0 = int(round(bbox_pt[0] * scale))
        y0 = int(round(bbox_pt[1] * scale))
        x1 = int(round(bbox_pt[2] * scale))
        y1 = int(round(bbox_pt[3] * scale))
        return (x0, y0, x1, y1)

    def pt_to_px(self, pt: float) -> float:
        """Convert point to pixel at configured DPI."""
        return pt_to_px(pt, self.dpi)

    def px_to_pt(self, px: float) -> float:
        """Convert pixel to point at configured DPI."""
        return px_to_pt(px, self.dpi)

    def create_multi_unit(
        self,
        val_pt: float,
        is_vertical: bool = False,
        source: MeasurementSource = "content_stream",
        confidence: float = 1.0,
        cross_check_delta: float = 0.0,
        warning: str = None
    ) -> MultiUnitValue:
        """Create a full float precision MultiUnitValue relative to page dimension."""
        ref_dim = self.page_height if is_vertical else self.page_width
        rel_pct = (val_pt / ref_dim * 100.0) if ref_dim > 0 else 0.0
        return MultiUnitValue(
            pt=float(val_pt),
            mm=pt_to_mm(val_pt),
            px=pt_to_px(val_pt, self.dpi),
            rel_pct=rel_pct,
            source=source,
            confidence=confidence,
            cross_check_delta=cross_check_delta,
            warning=warning
        )

    def create_bbox(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        source: MeasurementSource = "content_stream",
        confidence: float = 1.0,
        cross_check_delta: float = 0.0,
        warning: str = None
    ) -> BoundingBox:
        """Create a standardized BoundingBox using full float precision."""
        min_x = min(x0, x1)
        max_x = max(x0, x1)
        min_y = min(y0, y1)
        max_y = max(y0, y1)
        width = max_x - min_x
        height = max_y - min_y

        return BoundingBox(
            x0=self.create_multi_unit(min_x, is_vertical=False, source=source, confidence=confidence, cross_check_delta=cross_check_delta, warning=warning),
            y0=self.create_multi_unit(min_y, is_vertical=True, source=source, confidence=confidence, cross_check_delta=cross_check_delta, warning=warning),
            x1=self.create_multi_unit(max_x, is_vertical=False, source=source, confidence=confidence, cross_check_delta=cross_check_delta, warning=warning),
            y1=self.create_multi_unit(max_y, is_vertical=True, source=source, confidence=confidence, cross_check_delta=cross_check_delta, warning=warning),
            width=self.create_multi_unit(width, is_vertical=False, source=source, confidence=confidence, cross_check_delta=cross_check_delta, warning=warning),
            height=self.create_multi_unit(height, is_vertical=True, source=source, confidence=confidence, cross_check_delta=cross_check_delta, warning=warning),
        )


def create_multi_unit_value(
    val_pt: float,
    page_ref_dim_pt: float,
    dpi: int = 600,
    source: MeasurementSource = "content_stream",
    confidence: float = 1.0,
    cross_check_delta: float = 0.0,
    warning: str = None
) -> MultiUnitValue:
    """Helper for standalone multi-unit conversion."""
    rel_pct = (val_pt / page_ref_dim_pt * 100.0) if page_ref_dim_pt > 0 else 0.0
    return MultiUnitValue(
        pt=float(val_pt),
        mm=pt_to_mm(val_pt),
        px=pt_to_px(val_pt, dpi),
        rel_pct=rel_pct,
        source=source,
        confidence=confidence,
        cross_check_delta=cross_check_delta,
        warning=warning
    )


def create_bbox_from_pt(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page_width_pt: float,
    page_height_pt: float,
    dpi: int = 600,
    source: MeasurementSource = "content_stream",
    confidence: float = 1.0,
    cross_check_delta: float = 0.0,
    warning: str = None
) -> BoundingBox:
    """Helper for standalone BoundingBox creation."""
    min_x, max_x = min(x0, x1), max(x0, x1)
    min_y, max_y = min(y0, y1), max(y0, y1)
    width = max_x - min_x
    height = max_y - min_y

    return BoundingBox(
        x0=create_multi_unit_value(min_x, page_width_pt, dpi, source, confidence, cross_check_delta, warning),
        y0=create_multi_unit_value(min_y, page_height_pt, dpi, source, confidence, cross_check_delta, warning),
        x1=create_multi_unit_value(max_x, page_width_pt, dpi, source, confidence, cross_check_delta, warning),
        y1=create_multi_unit_value(max_y, page_height_pt, dpi, source, confidence, cross_check_delta, warning),
        width=create_multi_unit_value(width, page_width_pt, dpi, source, confidence, cross_check_delta, warning),
        height=create_multi_unit_value(height, page_height_pt, dpi, source, confidence, cross_check_delta, warning),
    )

