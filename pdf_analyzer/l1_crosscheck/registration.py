"""
Least-Squares 2D Affine Registration Engine.
Samples >= 20 isolated rules across the page at >= 5 positions, solves for scale (sx, sy)
and translation offsets (dx, dy), checks Gate G1 invariants, flags endpoint overshoots (>0.3 pt),
and renders diagnostic registration.png with 20x magnified displacement vectors.
"""

from __future__ import annotations
import math
import os
import json
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Any
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedPath, Color
from pdf_analyzer.l1_crosscheck.subpixel import SubpixelProfileEngine, SubpixelLineFit


@dataclass
class RegistrationResult:
    dx_pt: float
    dy_pt: float
    sx: float
    sy: float
    max_residual_pt: float
    mean_residual_pt: float
    sampled_rules_count: int
    sampled_points_count: int
    gate_g1_passed: bool
    endpoint_flags_count: int
    rule_fits: List[SubpixelLineFit] = field(default_factory=list)
    endpoint_flags: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dx_pt": self.dx_pt,
            "dy_pt": self.dy_pt,
            "sx": self.sx,
            "sy": self.sy,
            "max_residual_pt": self.max_residual_pt,
            "mean_residual_pt": self.mean_residual_pt,
            "sampled_rules_count": self.sampled_rules_count,
            "sampled_points_count": self.sampled_points_count,
            "gate_g1_passed": self.gate_g1_passed,
            "endpoint_flags_count": self.endpoint_flags_count,
            "endpoint_flags": self.endpoint_flags,
            "rule_fits": [rf.to_dict() for rf in self.rule_fits],
        }


def color_luminance(c: Optional[Color]) -> float:
    """Calculates perceived luminance (0.0 to 1.0)."""
    if not c:
        return 0.0
    r, g, b = c.rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


class RegistrationEngine:
    """
    Performs affine least-squares registration between L0 vector coordinates and 600 DPI raster.
    """

    def __init__(self, dpi: int = 600):
        self.dpi = dpi
        self.scale = dpi / 72.0
        self.subpixel = SubpixelProfileEngine(dpi=dpi)

    def solve_registration(
        self,
        page_layer: PageByteLayer,
        raster_rgb: np.ndarray,
        output_dir: Optional[str] = None,
    ) -> RegistrationResult:
        """
        Extracts isolated H/V rules from page_layer, samples perpendicular profiles,
        solves affine fit, evaluates Gate G1, and outputs registration.json & registration.png.
        """
        gray_img = cv2.cvtColor(raster_rgb, cv2.COLOR_RGB2GRAY)
        h_px, w_px = gray_img.shape

        # 1. Collect candidate dark stroke/fill rules
        h_rules, v_rules = self._extract_stroke_rules(page_layer)

        # Sort by span descending
        h_rules.sort(key=lambda r: abs(r[3] - r[2]), reverse=True)
        v_rules.sort(key=lambda r: abs(r[3] - r[2]), reverse=True)

        selected_h = h_rules[:15]
        selected_v = v_rules[:15]

        rule_fits: List[SubpixelLineFit] = []
        x_vector_pts: List[float] = []
        x_raster_pts: List[float] = []
        y_vector_pts: List[float] = []
        y_raster_pts: List[float] = []

        endpoint_flags: List[Dict[str, Any]] = []

        # Fit vertical rules (measures X positions)
        for i, (path_id, x_pt, y0_pt, y1_pt, width_pt) in enumerate(selected_v):
            fit = self.subpixel.fit_vertical_rule(
                gray_img=gray_img,
                x_pt=x_pt,
                y0_pt=y0_pt,
                y1_pt=y1_pt,
                stroke_width_pt=width_pt,
                num_samples=7,
                line_id=f"v_{path_id}_{i+1}",
            )
            rule_fits.append(fit)
            x_vector_pts.append(fit.vector_center_pt)
            x_raster_pts.append(fit.raster_center_pt)

            if fit.start_delta_pt > 0.3 or fit.end_delta_pt > 0.3:
                endpoint_flags.append({
                    "line_id": fit.line_id,
                    "orientation": "V",
                    "start_delta_pt": fit.start_delta_pt,
                    "end_delta_pt": fit.end_delta_pt,
                })

        # Fit horizontal rules (measures Y positions)
        for i, (path_id, y_pt, x0_pt, x1_pt, width_pt) in enumerate(selected_h):
            fit = self.subpixel.fit_horizontal_rule(
                gray_img=gray_img,
                y_pt=y_pt,
                x0_pt=x0_pt,
                x1_pt=x1_pt,
                stroke_width_pt=width_pt,
                num_samples=7,
                line_id=f"h_{path_id}_{i+1}",
            )
            rule_fits.append(fit)
            y_vector_pts.append(fit.vector_center_pt)
            y_raster_pts.append(fit.raster_center_pt)

            if fit.start_delta_pt > 0.3 or fit.end_delta_pt > 0.3:
                endpoint_flags.append({
                    "line_id": fit.line_id,
                    "orientation": "H",
                    "start_delta_pt": fit.start_delta_pt,
                    "end_delta_pt": fit.end_delta_pt,
                })

        # Solve affine parameters: x_raster = sx * x_vec + dx
        dx, sx, x_residuals = self._solve_1d_affine(x_vector_pts, x_raster_pts)
        dy, sy, y_residuals = self._solve_1d_affine(y_vector_pts, y_raster_pts)

        all_residuals = x_residuals + y_residuals
        max_residual = max(all_residuals) if all_residuals else 0.0
        mean_residual = float(np.mean(all_residuals)) if all_residuals else 0.0

        g1_passed = (
            abs(dx) <= 0.1
            and abs(dy) <= 0.1
            and abs(sx - 1.0) <= 0.0005
            and abs(sy - 1.0) <= 0.0005
            and max_residual <= 0.15
        )

        res = RegistrationResult(
            dx_pt=dx,
            dy_pt=dy,
            sx=sx,
            sy=sy,
            max_residual_pt=max_residual,
            mean_residual_pt=mean_residual,
            sampled_rules_count=len(rule_fits),
            sampled_points_count=len(all_residuals),
            gate_g1_passed=g1_passed,
            endpoint_flags_count=len(endpoint_flags),
            rule_fits=rule_fits,
            endpoint_flags=endpoint_flags,
        )

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, "registration.json"), "w", encoding="utf-8") as f:
                json.dump(res.to_dict(), f, indent=2)

            self._render_registration_png(
                raster_rgb=raster_rgb,
                rule_fits=rule_fits,
                output_path=os.path.join(output_dir, "registration.png"),
            )

        return res

    def _extract_stroke_rules(
        self,
        page_layer: PageByteLayer,
    ) -> Tuple[List[Tuple[str, float, float, float, float]], List[Tuple[str, float, float, float, float]]]:
        """
        Finds candidate dark H rules: (path_id, y, x0, x1, width)
        and V rules: (path_id, x, y0, y1, width) from L0 paths.
        """
        h_rules = []
        v_rules = []

        for p in page_layer.paths:
            # 1. Thin filled rectangles
            if p.fill_rule:
                lum = color_luminance(p.fill_color)
                if lum > 0.85:
                    continue  # Ignore pale background boxes
                b = p.bbox_device_pt
                w = abs(b[2] - b[0])
                h = abs(b[3] - b[1])
                if w <= 3.0 and h >= 10.0:  # Thin vertical rect rule
                    v_rules.append((p.path_id, (b[0] + b[2]) / 2.0, min(b[1], b[3]), max(b[1], b[3]), w))
                elif h <= 3.0 and w >= 10.0:  # Thin horizontal rect rule
                    h_rules.append((p.path_id, (b[1] + b[3]) / 2.0, min(b[0], b[2]), max(b[0], b[2]), h))
                continue

            # 2. Stroked paths
            if not p.stroke:
                continue

            lum = color_luminance(p.stroke_color)
            if lum > 0.85:
                continue

            width = p.stroke.width_pt
            for seg in p.segments:
                if seg[0] == "re":
                    rx, ry, rw, rh = float(seg[1]), float(seg[2]), float(seg[3]), float(seg[4])
                    if rh <= 3.0 and rw >= 10.0:
                        h_rules.append((p.path_id, ry + rh / 2.0, rx, rx + rw, rh))
                    elif rw <= 3.0 and rh >= 10.0:
                        v_rules.append((p.path_id, rx + rw / 2.0, ry, ry + rh, rw))
                    else:
                        h_rules.append((p.path_id, ry, rx, rx + rw, width))
                        h_rules.append((p.path_id, ry + rh, rx, rx + rw, width))
                        v_rules.append((p.path_id, rx, ry, ry + rh, width))
                        v_rules.append((p.path_id, rx + rw, ry, ry + rh, width))
                elif seg[0] == "l" and len(p.segments) == 2 and p.segments[0][0] == "m":
                    x0, y0 = float(p.segments[0][1]), float(p.segments[0][2])
                    x1, y1 = float(seg[1]), float(seg[2])
                    if abs(x1 - x0) < 1.0 and abs(y1 - y0) >= 10.0:
                        v_rules.append((p.path_id, (x0 + x1) / 2.0, min(y0, y1), max(y0, y1), width))
                    elif abs(y1 - y0) < 1.0 and abs(x1 - x0) >= 10.0:
                        h_rules.append((p.path_id, (y0 + y1) / 2.0, min(x0, x1), max(x0, x1), width))

        return h_rules, v_rules

    def _solve_1d_affine(
        self,
        vec_pts: List[float],
        rast_pts: List[float],
    ) -> Tuple[float, float, List[float]]:
        if len(vec_pts) < 2:
            return 0.0, 1.0, [0.0]

        vec_arr = np.array(vec_pts)
        rast_arr = np.array(rast_pts)

        # Initial least-squares solve
        A = np.vstack([vec_arr, np.ones(len(vec_arr))]).T
        res = np.linalg.lstsq(A, rast_arr, rcond=None)
        s, d = res[0]

        # Inlier filtering (reject non-isolated profile fits with > 0.20 pt discrepancy)
        initial_res = np.abs(s * vec_arr + d - rast_arr)
        inliers = initial_res <= 0.20
        if np.sum(inliers) >= 3 and np.sum(inliers) < len(vec_arr):
            A_in = A[inliers]
            b_in = rast_arr[inliers]
            res_in = np.linalg.lstsq(A_in, b_in, rcond=None)
            s, d = res_in[0]
            fitted = s * vec_arr[inliers] + d
            residuals = [float(abs(f - r)) for f, r in zip(fitted, rast_arr[inliers])]
        else:
            fitted = s * vec_arr + d
            residuals = [float(abs(f - r)) for f, r in zip(fitted, rast_arr)]

        return float(d), float(s), residuals

    def _render_registration_png(
        self,
        raster_rgb: np.ndarray,
        rule_fits: List[SubpixelLineFit],
        output_path: str,
    ) -> None:
        img = Image.fromarray(raster_rgb).convert("RGBA")
        draw = ImageDraw.Draw(img)
        h_px = raster_rgb.shape[0]
        page_height_pt = h_px / self.scale

        MAG_FACTOR = 20.0

        for fit in rule_fits:
            if fit.orientation == "V":
                x_nom_px = fit.vector_center_pt * self.scale
                y0_img_px = (page_height_pt - fit.vector_end_pt) * self.scale
                y1_img_px = (page_height_pt - fit.vector_start_pt) * self.scale
                delta_px = (fit.raster_center_pt - fit.vector_center_pt) * self.scale

                draw.line([(x_nom_px, y0_img_px), (x_nom_px, y1_img_px)], fill=(0, 255, 255, 180), width=2)
                arrow_x = x_nom_px + delta_px * MAG_FACTOR
                mid_y = (y0_img_px + y1_img_px) / 2.0
                draw.line([(x_nom_px, mid_y), (arrow_x, mid_y)], fill=(255, 0, 0, 255), width=3)
            else:
                y_nom_img_px = (page_height_pt - fit.vector_center_pt) * self.scale
                x0_px = fit.vector_start_pt * self.scale
                x1_px = fit.vector_end_pt * self.scale
                delta_px = (fit.raster_center_pt - fit.vector_center_pt) * self.scale

                draw.line([(x0_px, y_nom_img_px), (x1_px, y_nom_img_px)], fill=(0, 255, 255, 180), width=2)
                arrow_y = y_nom_img_px - delta_px * MAG_FACTOR
                mid_x = (x0_px + x1_px) / 2.0
                draw.line([(mid_x, y_nom_img_px), (mid_x, arrow_y)], fill=(255, 0, 0, 255), width=3)

        img.convert("RGB").save(output_path, "PNG")
