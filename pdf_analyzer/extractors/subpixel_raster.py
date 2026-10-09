"""Sub-pixel raster measurement engine and anti-aliasing color corrector at 600 DPI."""

from typing import Tuple, List, Dict, Any, Optional
import numpy as np
import cv2
from scipy.optimize import curve_fit

from pdf_analyzer.utils.color import rgb_to_hex


def gaussian_func(x, a, x0, sigma, offset):
    """1D Gaussian function for sub-pixel peak fitting."""
    return a * np.exp(-((x - x0) ** 2) / (2 * sigma ** 2 + 1e-6)) + offset


class SubpixelRasterEngine:
    """Performs sub-pixel edge detection, FWHM stroke width measurement, and anti-aliased color extraction."""

    def __init__(self, dpi: int = 600):
        self.dpi = dpi
        self.scale = dpi / 72.0  # px per pt (8.333 px/pt at 600 DPI)

    def measure_line_subpixel_fwhm(
        self,
        img_bgr: np.ndarray,
        p_start_pt: Tuple[float, float],
        p_end_pt: Tuple[float, float],
        vector_stroke_pt: float
    ) -> Dict[str, Any]:
        """Compute line thickness as FWHM of perpendicular gradient profile at 600 DPI."""
        x0_px = int(p_start_pt[0] * self.scale)
        y0_px = int(p_start_pt[1] * self.scale)
        x1_px = int(p_end_pt[0] * self.scale)
        y1_px = int(p_end_pt[1] * self.scale)

        h_img, w_img, _ = img_bgr.shape
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # Determine line orientation
        dx = x1_px - x0_px
        dy = y1_px - y0_px
        length = np.hypot(dx, dy)
        if length < 10:
            return {
                "fwhm_px": vector_stroke_pt * self.scale,
                "fwhm_pt": vector_stroke_pt,
                "deviation_pt": 0.0,
                "flagged_deviation": False
            }

        # Take perpendicular slices across the midpoint of the line
        mid_x = (x0_px + x1_px) / 2.0
        mid_y = (y0_px + y1_px) / 2.0

        # Normal unit vector
        nx = -dy / length
        ny = dx / length

        # Sample 31 points across perpendicular profile (-15 to +15 pixels)
        sample_range = np.linspace(-15, 15, 31)
        sampled_intensities = []

        for offset in sample_range:
            sx = int(round(mid_x + nx * offset))
            sy = int(round(mid_y + ny * offset))
            if 0 <= sx < w_img and 0 <= sy < h_img:
                sampled_intensities.append(float(255 - gray[sy, sx]))  # inverted: line is bright peak
            else:
                sampled_intensities.append(0.0)

        intensities = np.array(sampled_intensities)
        peak_idx = np.argmax(intensities)
        max_val = intensities[peak_idx]
        min_val = np.min(intensities)
        half_max = min_val + (max_val - min_val) / 2.0

        # Fit Gaussian for sub-pixel accuracy
        fwhm_px = vector_stroke_pt * self.scale
        try:
            p0 = [max_val - min_val, sample_range[peak_idx], 2.0, min_val]
            popt, _ = curve_fit(gaussian_func, sample_range, intensities, p0=p0, maxfev=400)
            sigma = abs(popt[2])
            # FWHM = 2.355 * sigma
            fwhm_px = 2.355 * sigma
        except Exception:
            # Fallback to direct half-max interpolation
            above_half = np.where(intensities >= half_max)[0]
            if len(above_half) >= 2:
                fwhm_px = float(sample_range[above_half[-1]] - sample_range[above_half[0]])

        fwhm_pt = fwhm_px / self.scale
        deviation_pt = abs(fwhm_pt - vector_stroke_pt)

        return {
            "fwhm_px": round(fwhm_px, 2),
            "fwhm_pt": round(fwhm_pt, 3),
            "deviation_pt": round(deviation_pt, 4),
            "flagged_deviation": deviation_pt > 0.10
        }

    def extract_anti_aliased_color(
        self,
        img_bgr: np.ndarray,
        bbox_pt: Tuple[float, float, float, float],
        percentile: float = 20.0
    ) -> Tuple[Tuple[int, int, int], str]:
        """Extract exact anti-aliased color by computing mode of darkest/most saturated 20% pixels."""
        x0_px = max(0, int(bbox_pt[0] * self.scale))
        y0_px = max(0, int(bbox_pt[1] * self.scale))
        x1_px = min(img_bgr.shape[1], int(bbox_pt[2] * self.scale))
        y1_px = min(img_bgr.shape[0], int(bbox_pt[3] * self.scale))

        if x1_px <= x0_px or y1_px <= y0_px:
            return ((0, 0, 0), "#000000")

        crop = img_bgr[y0_px:y1_px, x0_px:x1_px]
        if crop.size == 0:
            return ((0, 0, 0), "#000000")

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # Select the darkest 20% pixels (true core ink / stroke pixels, ignoring anti-aliased edge halos)
        threshold_val = np.percentile(gray, percentile)
        mask = gray <= threshold_val

        core_pixels = crop[mask]
        if len(core_pixels) == 0:
            core_pixels = crop.reshape(-1, 3)

        # Median of core ink pixels
        b, g, r = np.median(core_pixels, axis=0)
        rgb = (int(r), int(g), int(b))
        return (rgb, rgb_to_hex(rgb))

