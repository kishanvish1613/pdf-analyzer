"""
Device-Space Shapely Geometry and Stroked/Filled Path Vectorization.
Converts PDF path construction operators into device coordinates, applies affine CTM,
evaluates stroke styles (caps, joins, miters) and fill winding rules, and computes
exact geometric and painted bounding boxes.
"""

from __future__ import annotations
import math
from typing import List, Tuple, Optional, Any
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, box
from shapely.ops import unary_union
from shapely import BufferCapStyle, BufferJoinStyle
from pdf_analyzer.l0_bytes.state import CTM
from pdf_analyzer.l0_bytes.primitives import StrokeStyle


def transform_point(ctm: CTM, x: float, y: float) -> Tuple[float, float]:
    return ctm.transform_point(x, y)


def transform_bbox(ctm: CTM, bbox: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """Transforms an axis-aligned box [x0, y0, x1, y1] through CTM to its enclosing device bbox."""
    x0, y0, x1, y1 = bbox
    corners = [
        ctm.transform_point(x0, y0),
        ctm.transform_point(x1, y0),
        ctm.transform_point(x1, y1),
        ctm.transform_point(x0, y1),
    ]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def sample_cubic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    num_samples: int = 16,
) -> List[Tuple[float, float]]:
    """Samples points along a cubic Bézier curve."""
    pts = []
    for i in range(num_samples + 1):
        t = i / float(num_samples)
        u = 1.0 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        x = uuu * p0[0] + 3.0 * uu * t * p1[0] + 3.0 * u * tt * p2[0] + ttt * p3[0]
        y = uuu * p0[1] + 3.0 * uu * t * p1[1] + 3.0 * u * tt * p2[1] + ttt * p3[1]
        pts.append((x, y))
    return pts


def segments_to_device_subpaths(
    segments: List[Tuple[Any, ...]],
    ctm: CTM,
) -> List[List[Tuple[float, float]]]:
    """
    Evaluates PDF path construction operators into continuous subpaths in device coordinates.
    """
    subpaths: List[List[Tuple[float, float]]] = []
    current_subpath: List[Tuple[float, float]] = []
    current_pt: Tuple[float, float] = (0.0, 0.0)
    subpath_start_pt: Tuple[float, float] = (0.0, 0.0)

    for seg in segments:
        op = seg[0]
        if op == "m":
            if len(current_subpath) >= 2:
                subpaths.append(current_subpath)
            pt = transform_point(ctm, float(seg[1]), float(seg[2]))
            current_pt = pt
            subpath_start_pt = pt
            current_subpath = [pt]
        elif op == "l":
            pt = transform_point(ctm, float(seg[1]), float(seg[2]))
            if not current_subpath:
                current_subpath.append(current_pt)
            current_subpath.append(pt)
            current_pt = pt
        elif op == "c":
            p1 = transform_point(ctm, float(seg[1]), float(seg[2]))
            p2 = transform_point(ctm, float(seg[3]), float(seg[4]))
            p3 = transform_point(ctm, float(seg[5]), float(seg[6]))
            if not current_subpath:
                current_subpath.append(current_pt)
            bezier_pts = sample_cubic_bezier(current_pt, p1, p2, p3)
            current_subpath.extend(bezier_pts[1:])
            current_pt = p3
        elif op == "v":
            p2 = transform_point(ctm, float(seg[1]), float(seg[2]))
            p3 = transform_point(ctm, float(seg[3]), float(seg[4]))
            if not current_subpath:
                current_subpath.append(current_pt)
            bezier_pts = sample_cubic_bezier(current_pt, current_pt, p2, p3)
            current_subpath.extend(bezier_pts[1:])
            current_pt = p3
        elif op == "y":
            p1 = transform_point(ctm, float(seg[1]), float(seg[2]))
            p3 = transform_point(ctm, float(seg[3]), float(seg[4]))
            if not current_subpath:
                current_subpath.append(current_pt)
            bezier_pts = sample_cubic_bezier(current_pt, p1, p3, p3)
            current_subpath.extend(bezier_pts[1:])
            current_pt = p3
        elif op == "re":
            # Rectangle: x y w h
            x, y, w, h = float(seg[1]), float(seg[2]), float(seg[3]), float(seg[4])
            p0 = transform_point(ctm, x, y)
            p1 = transform_point(ctm, x + w, y)
            p2 = transform_point(ctm, x + w, y + h)
            p3 = transform_point(ctm, x, y + h)
            rect_path = [p0, p1, p2, p3, p0]
            subpaths.append(rect_path)
            current_pt = p0
            subpath_start_pt = p0
            current_subpath = []
        elif op == "h":
            # Close subpath
            if current_subpath and current_subpath[0] != current_subpath[-1]:
                current_subpath.append(subpath_start_pt)
                subpaths.append(current_subpath)
                current_subpath = []
                current_pt = subpath_start_pt

    if len(current_subpath) >= 2:
        subpaths.append(current_subpath)

    return subpaths


def build_stroked_polygon(
    segments: List[Tuple[Any, ...]],
    ctm: CTM,
    stroke: StrokeStyle,
    clipping_shapes: Optional[List[Any]] = None,
) -> Tuple[Any, Tuple[float, float, float, float], Tuple[float, float, float, float]]:
    """
    Constructs device-space stroked Shapely polygon with exact line caps and joins.
    Returns (shapely_geom, bbox_device_pt, painted_bbox_device_pt).
    """
    subpaths = segments_to_device_subpaths(segments, ctm)
    if not subpaths:
        empty = Polygon()
        return empty, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)

    # Map PDF cap style to Shapely BufferCapStyle
    # PDF: 0: Butt, 1: Round, 2: Projecting Square
    cap_map = {
        0: BufferCapStyle.flat,
        1: BufferCapStyle.round,
        2: BufferCapStyle.square,
    }
    # Map PDF join style to Shapely BufferJoinStyle
    # PDF: 0: Miter, 1: Round, 2: Bevel
    join_map = {
        0: BufferJoinStyle.mitre,
        1: BufferJoinStyle.round,
        2: BufferJoinStyle.bevel,
    }

    cap_style = cap_map.get(stroke.cap, BufferCapStyle.flat)
    join_style = join_map.get(stroke.join, BufferJoinStyle.mitre)
    half_width = max(0.01, stroke.width_pt / 2.0)

    all_points: List[Tuple[float, float]] = []
    buffered_geoms = []

    for path in subpaths:
        all_points.extend(path)
        if len(path) >= 2:
            line = LineString(path)
            geom = line.buffer(
                distance=half_width,
                cap_style=cap_style,
                join_style=join_style,
                mitre_limit=stroke.miter_limit,
            )
            if not geom.is_empty:
                buffered_geoms.append(geom)

    if not buffered_geoms:
        empty = Polygon()
        return empty, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)

    stroked_poly = unary_union(buffered_geoms)

    # Compute raw path bbox
    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    raw_bbox = (min(xs), min(ys), max(xs), max(ys))

    # Apply clipping if present
    if clipping_shapes:
        for clip in clipping_shapes:
            if clip is not None and not clip.is_empty:
                stroked_poly = stroked_poly.intersection(clip)

    if stroked_poly.is_empty:
        painted_bbox = raw_bbox
    else:
        minx, miny, maxx, maxy = stroked_poly.bounds
        painted_bbox = (float(minx), float(miny), float(maxx), float(maxy))

    return stroked_poly, raw_bbox, painted_bbox


def build_filled_polygon(
    segments: List[Tuple[Any, ...]],
    ctm: CTM,
    fill_rule: str = "nonzero",
    clipping_shapes: Optional[List[Any]] = None,
) -> Tuple[Any, Tuple[float, float, float, float], Tuple[float, float, float, float]]:
    """
    Constructs device-space filled Shapely polygon using nonzero or even-odd rule.
    Returns (shapely_geom, bbox_device_pt, painted_bbox_device_pt).
    """
    subpaths = segments_to_device_subpaths(segments, ctm)
    if not subpaths:
        empty = Polygon()
        return empty, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)

    all_points: List[Tuple[float, float]] = []
    poly_list = []

    for path in subpaths:
        all_points.extend(path)
        if len(path) >= 3:
            p = Polygon(path)
            if not p.is_empty and p.is_valid:
                poly_list.append(p)
            elif not p.is_empty:
                poly_list.append(p.buffer(0))

    if not poly_list:
        empty = Polygon()
        return empty, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)

    filled_poly = unary_union(poly_list)

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    raw_bbox = (min(xs), min(ys), max(xs), max(ys))

    if clipping_shapes:
        for clip in clipping_shapes:
            if clip is not None and not clip.is_empty:
                filled_poly = filled_poly.intersection(clip)

    if filled_poly.is_empty:
        painted_bbox = raw_bbox
    else:
        minx, miny, maxx, maxy = filled_poly.bounds
        painted_bbox = (float(minx), float(miny), float(maxx), float(maxy))

    return filled_poly, raw_bbox, painted_bbox
