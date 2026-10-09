"""Rasterization and Computer Vision extractor using OpenCV, NumPy, and Pillow."""

import cv2
import numpy as np
from PIL import Image
from typing import Tuple, List, Dict, Any, Optional
import pymupdf

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.utils.color import rgb_to_hex


class RasterExtractor:
    """Renders pages to raster images at 300 DPI and performs CV measurements."""

    def __init__(self, doc: pymupdf.Document, config: AnalyzerConfig):
        self.doc = doc
        self.config = config

    def render_page_image(self, page_index: int) -> Tuple[np.ndarray, Image.Image]:
        """Render page at configured DPI returning (cv2_bgr_array, pil_image)."""
        page = self.doc[page_index]
        pix = page.get_pixmap(dpi=self.config.dpi)
        img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # Convert to OpenCV BGR
        img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        return img_bgr, img_pil

    def detect_raster_lines(self, img_bgr: np.ndarray) -> Dict[str, List[Tuple[int, int, int, int]]]:
        """Detect horizontal and vertical line segments using morphological operations."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        # Invert: line pixels become white, background becomes black
        thresh = cv2.adaptiveThreshold(
            ~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2
        )

        h_scale = 30
        v_scale = 30
        h_size = max(1, thresh.shape[1] // h_scale)
        v_size = max(1, thresh.shape[0] // v_scale)

        # Horizontal kernel
        h_structure = cv2.getStructuringElement(cv2.MORPH_RECT, (h_size, 1))
        h_lines_img = cv2.erode(thresh, h_structure)
        h_lines_img = cv2.dilate(h_lines_img, h_structure)

        # Vertical kernel
        v_structure = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_size))
        v_lines_img = cv2.erode(thresh, v_structure)
        v_lines_img = cv2.dilate(v_lines_img, v_structure)

        # Extract contours of horizontal lines
        h_contours, _ = cv2.findContours(h_lines_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h_boxes = [cv2.boundingRect(c) for c in h_contours]  # (x, y, w, h)

        # Extract contours of vertical lines
        v_contours, _ = cv2.findContours(v_lines_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        v_boxes = [cv2.boundingRect(c) for c in v_contours]

        return {
            "horizontal": [(x, y, x + w, y + h) for (x, y, w, h) in h_boxes if w > 20],
            "vertical": [(x, y, x + w, y + h) for (x, y, w, h) in v_boxes if h > 20]
        }

    def sample_dominant_color(
        self,
        img_bgr: np.ndarray,
        bbox_px: Tuple[int, int, int, int],
        k: int = 3
    ) -> Tuple[Tuple[int, int, int], str, bool]:
        """Sample dominant color in a pixel bbox using K-means clustering.

        Returns (RGB, HEX, is_gradient_detected).
        """
        x0, y0, x1, y1 = bbox_px
        h, w, _ = img_bgr.shape
        x0 = max(0, min(w - 1, x0))
        y0 = max(0, min(h - 1, y0))
        x1 = max(x0 + 1, min(w, x1))
        y1 = max(y0 + 1, min(h, y1))

        crop = img_bgr[y0:y1, x0:x1]
        if crop.size == 0 or crop.shape[0] == 0 or crop.shape[1] == 0:
            return ((255, 255, 255), "#FFFFFF", False)

        pixels = crop.reshape(-1, 3).astype(np.float32)
        if len(pixels) < k:
            b, g, r = np.mean(pixels, axis=0) if len(pixels) > 0 else (255, 255, 255)
            rgb = (int(r), int(g), int(b))
            return (rgb, rgb_to_hex(rgb), False)

        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 5, cv2.KMEANS_RANDOM_CENTERS)

        counts = np.bincount(labels.flatten())
        dominant_idx = np.argmax(counts)
        dom_bgr = centers[dominant_idx]
        rgb = (int(dom_bgr[2]), int(dom_bgr[1]), int(dom_bgr[0]))

        # Check for gradient: significant color variance along vertical or horizontal axis
        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        std_dev = float(np.std(gray_crop))
        is_gradient = std_dev > 25.0 and len(counts) > 1 and (counts[np.argsort(counts)[-2]] / len(pixels) > 0.2)

        return (rgb, rgb_to_hex(rgb), is_gradient)

    def crop_and_save_region(
        self,
        img_pil: Image.Image,
        bbox_pt: Tuple[float, float, float, float],
        page_rect_pt: pymupdf.Rect,
        output_path: str
    ) -> bool:
        """Crop and save a specific region in points to an output image path."""
        dpi_scale = self.config.dpi / 72.0
        x0 = int(bbox_pt[0] * dpi_scale)
        y0 = int(bbox_pt[1] * dpi_scale)
        x1 = int(bbox_pt[2] * dpi_scale)
        y1 = int(bbox_pt[3] * dpi_scale)

        # Pad slightly
        pad = 4
        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(img_pil.width, x1 + pad)
        y1 = min(img_pil.height, y1 + pad)

        if x1 > x0 and y1 > y0:
            cropped = img_pil.crop((x0, y0, x1, y1))
            cropped.save(output_path, "PNG")
            return True
        return False
