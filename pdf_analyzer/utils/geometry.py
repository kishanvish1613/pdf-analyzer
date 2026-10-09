"""Geometry, bounding box math, and clustering utilities."""

import math
from typing import List, Tuple, Dict, Any, Optional


def cluster_1d_coordinates(values: List[float], tolerance: float = 2.0) -> List[List[float]]:
    """Cluster 1D float coordinates within a tolerance window."""
    if not values:
        return []
    sorted_vals = sorted(values)
    clusters: List[List[float]] = [[sorted_vals[0]]]
    for v in sorted_vals[1:]:
        if abs(v - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return clusters


def cluster_representatives(values: List[float], tolerance: float = 2.0) -> List[float]:
    """Return median/mean representative coordinate for each 1D cluster."""
    clusters = cluster_1d_coordinates(values, tolerance)
    return [sum(c) / len(c) for c in clusters]


def bbox_intersection(b1: Tuple[float, float, float, float], b2: Tuple[float, float, float, float]) -> Optional[Tuple[float, float, float, float]]:
    """Compute rectangle intersection (x0, y0, x1, y1) or None if no overlap."""
    x0 = max(b1[0], b2[0])
    y0 = max(b1[1], b2[1])
    x1 = min(b1[2], b2[2])
    y1 = min(b1[3], b2[3])
    if x1 > x0 and y1 > y0:
        return (x0, y0, x1, y1)
    return None


def bbox_area(b: Tuple[float, float, float, float]) -> float:
    """Area of (x0, y0, x1, y1)."""
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def bbox_iou(b1: Tuple[float, float, float, float], b2: Tuple[float, float, float, float]) -> float:
    """Intersection over Union (IoU) of two bounding boxes."""
    inter = bbox_intersection(b1, b2)
    if not inter:
        return 0.0
    inter_area = bbox_area(inter)
    union_area = bbox_area(b1) + bbox_area(b2) - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def bbox_contains(parent: Tuple[float, float, float, float], child: Tuple[float, float, float, float], tolerance: float = 1.0) -> bool:
    """Check if parent bbox contains child bbox within a small tolerance."""
    return (
        child[0] >= parent[0] - tolerance and
        child[1] >= parent[1] - tolerance and
        child[2] <= parent[2] + tolerance and
        child[3] <= parent[3] + tolerance
    )


def horizontal_overlap_fraction(b1: Tuple[float, float, float, float], b2: Tuple[float, float, float, float]) -> float:
    """Compute 1D horizontal overlap fraction relative to minimum box width."""
    x0 = max(b1[0], b2[0])
    x1 = min(b1[2], b2[2])
    overlap_w = max(0.0, x1 - x0)
    w_min = min(b1[2] - b1[0], b2[2] - b2[0])
    return overlap_w / w_min if w_min > 0 else 0.0


def vertical_overlap_fraction(b1: Tuple[float, float, float, float], b2: Tuple[float, float, float, float]) -> float:
    """Compute 1D vertical overlap fraction relative to minimum box height."""
    y0 = max(b1[1], b2[1])
    y1 = min(b1[3], b2[3])
    overlap_h = max(0.0, y1 - y0)
    h_min = min(b1[3] - b1[1], b2[3] - b2[1])
    return overlap_h / h_min if h_min > 0 else 0.0
