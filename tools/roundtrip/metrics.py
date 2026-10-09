"""Metrics Engine for Closed-Loop Roundtrip Verification Harness.

Computes:
1. Pixel metrics: SSIM (grayscale, scikit-image), diff percentage, difference heatmap PNG.
2. Geometry metrics: L0 word extraction, sequence matching, per-word delta (dx, dy, dw, dh) in pt.
3. Failure attribution: classifies large pixel diff regions as TEXT, RULE, FILL, or OTHER.
"""

from __future__ import annotations
import os
import difflib
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
import cv2
import pymupdf
from skimage.metrics import structural_similarity as ssim

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, PaintedPath


@dataclass
class WordBox:
    text: str
    x0_pt: float
    y0_pt: float
    x1_pt: float
    y1_pt: float
    width_pt: float
    height_pt: float
    page_number: int = 1

    @property
    def bbox_pt(self) -> Tuple[float, float, float, float]:
        return (self.x0_pt, self.y0_pt, self.x1_pt, self.y1_pt)


@dataclass
class PixelMetrics:
    ssim: float
    diff_percent: float
    differing_pixels_count: int
    total_pixels: int
    heatmap_path: str
    diff_threshold: float = 16.0 / 255.0


@dataclass
class GeometryMetrics:
    total_orig_words: int
    total_gen_words: int
    matched_words_count: int
    unmatched_orig_words: List[str] = field(default_factory=list)
    unmatched_gen_words: List[str] = field(default_factory=list)
    dx_pt: Dict[str, float] = field(default_factory=lambda: {"mean": 0.0, "p95": 0.0, "max": 0.0})
    dy_pt: Dict[str, float] = field(default_factory=lambda: {"mean": 0.0, "p95": 0.0, "max": 0.0})
    dw_pt: Dict[str, float] = field(default_factory=lambda: {"mean": 0.0, "p95": 0.0, "max": 0.0})
    dh_pt: Dict[str, float] = field(default_factory=lambda: {"mean": 0.0, "p95": 0.0, "max": 0.0})


def extract_words_from_l0(pdf_path: str, page_number: int = 1) -> Tuple[List[WordBox], PageByteLayer]:
    """Extract ordered words and underlying L0 layer from PDF using ByteLayerExtractor."""
    with ByteLayerExtractor(pdf_path) as extractor:
        layer = extractor.extract_page(page_number)

    chars = layer.text_chars
    words: List[WordBox] = []
    cur_chars: List[PaintedTextChar] = []

    def flush_word(char_list: List[PaintedTextChar]):
        if not char_list:
            return
        w_text = "".join(ch.unicode_text for ch in char_list).strip()
        if not w_text:
            return
        min_x = min(ch.font_bbox_device_pt[0] for ch in char_list)
        min_y = min(ch.font_bbox_device_pt[1] for ch in char_list)
        max_x = max(ch.font_bbox_device_pt[2] for ch in char_list)
        max_y = max(ch.font_bbox_device_pt[3] for ch in char_list)
        words.append(
            WordBox(
                text=w_text,
                x0_pt=round(min_x, 3),
                y0_pt=round(min_y, 3),
                x1_pt=round(max_x, 3),
                y1_pt=round(max_y, 3),
                width_pt=round(max_x - min_x, 3),
                height_pt=round(max_y - min_y, 3),
                page_number=page_number,
            )
        )

    for c in chars:
        if c.unicode_text.isspace():
            if cur_chars:
                flush_word(cur_chars)
                cur_chars = []
            continue

        if cur_chars:
            prev_c = cur_chars[-1]
            dy = abs(c.origin_device_pt[1] - prev_c.origin_device_pt[1])
            dx = c.origin_device_pt[0] - (prev_c.origin_device_pt[0] + prev_c.advance_pt)
            if dy > 2.0 or dx > 0.35 * max(c.font_size_pt, 1.0) or dx < -2.0:
                flush_word(cur_chars)
                cur_chars = []

        cur_chars.append(c)

    if cur_chars:
        flush_word(cur_chars)

    return words, layer


def compute_geometry_metrics(orig_words: List[WordBox], gen_words: List[WordBox]) -> GeometryMetrics:
    """Match words between original and generated PDFs by text and order, reporting deltas."""
    orig_texts = [w.text for w in orig_words]
    gen_texts = [w.text for w in gen_words]

    matcher = difflib.SequenceMatcher(None, orig_texts, gen_texts)
    matching_blocks = matcher.get_matching_blocks()

    matched_pairs: List[Tuple[WordBox, WordBox]] = []
    matched_orig_indices = set()
    matched_gen_indices = set()

    for block in matching_blocks:
        for offset in range(block.size):
            i_orig = block.a + offset
            i_gen = block.b + offset
            matched_pairs.append((orig_words[i_orig], gen_words[i_gen]))
            matched_orig_indices.add(i_orig)
            matched_gen_indices.add(i_gen)

    unmatched_orig = [orig_words[i].text for i in range(len(orig_words)) if i not in matched_orig_indices]
    unmatched_gen = [gen_words[i].text for i in range(len(gen_words)) if i not in matched_gen_indices]

    if not matched_pairs:
        return GeometryMetrics(
            total_orig_words=len(orig_words),
            total_gen_words=len(gen_words),
            matched_words_count=0,
            unmatched_orig_words=unmatched_orig,
            unmatched_gen_words=unmatched_gen,
        )

    dx_list = [abs(g.x0_pt - o.x0_pt) for o, g in matched_pairs]
    dy_list = [abs(g.y0_pt - o.y0_pt) for o, g in matched_pairs]
    dw_list = [abs(g.width_pt - o.width_pt) for o, g in matched_pairs]
    dh_list = [abs(g.height_pt - o.height_pt) for o, g in matched_pairs]

    def calc_stats(vals: List[float]) -> Dict[str, float]:
        arr = np.array(vals)
        return {
            "mean": round(float(np.mean(arr)), 3),
            "p95": round(float(np.percentile(arr, 95)), 3),
            "max": round(float(np.max(arr)), 3),
        }

    return GeometryMetrics(
        total_orig_words=len(orig_words),
        total_gen_words=len(gen_words),
        matched_words_count=len(matched_pairs),
        unmatched_orig_words=unmatched_orig,
        unmatched_gen_words=unmatched_gen,
        dx_pt=calc_stats(dx_list),
        dy_pt=calc_stats(dy_list),
        dw_pt=calc_stats(dw_list),
        dh_pt=calc_stats(dh_list),
    )


def rasterize_page_at_dpi(pdf_path: str, page_number: int = 1, dpi: int = 300) -> Tuple[np.ndarray, Tuple[int, int]]:
    """Rasterize PDF page to BGR numpy array at specified DPI."""
    doc = pymupdf.open(pdf_path)
    page_idx = min(len(doc) - 1, max(0, page_number - 1))
    page = doc[page_idx]
    pix = page.get_pixmap(dpi=dpi)
    img_rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
    if pix.n == 4:
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    else:
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_GRAY2BGR)
    doc.close()
    return img_bgr, (pix.width, pix.height)


def _box_overlaps(b1: Tuple[float, float, float, float], b2: Tuple[float, float, float, float]) -> bool:
    """Checks whether two bounding boxes (x0, y0, x1, y1) overlap."""
    if not b1 or not b2 or len(b1) < 4 or len(b2) < 4:
        return False
    x_overlap = max(0.0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
    y_overlap = max(0.0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
    return (x_overlap > 0.1) and (y_overlap > 0.1)


def attribute_failures(
    diff_mask: np.ndarray,
    orig_layer: PageByteLayer,
    dpi: int = 300,
    page_height_pt: float = 792.0,
    min_region_area_px: int = 25
) -> Dict[str, int]:
    """Classify large pixel-difference regions as TEXT, RULE, FILL, or OTHER."""
    counts = {"TEXT": 0, "RULE": 0, "FILL": 0, "OTHER": 0}

    contours, _ = cv2.findContours(diff_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pt_per_px = 72.0 / float(dpi)

    char_boxes = [c.font_bbox_device_pt for c in orig_layer.text_chars if c.font_bbox_device_pt]
    rule_boxes = [
        (p.painted_bbox_device_pt or p.bbox_device_pt)
        for p in orig_layer.paths
        if p.stroke and (p.painted_bbox_device_pt or p.bbox_device_pt)
    ]
    fill_boxes = [
        (p.painted_bbox_device_pt or p.bbox_device_pt)
        for p in orig_layer.paths
        if p.fill_color and (p.painted_bbox_device_pt or p.bbox_device_pt)
    ]

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_region_area_px:
            continue

        x_px, y_px, w_px, h_px = cv2.boundingRect(cnt)
        x0_pt = x_px * pt_per_px
        y0_pt = y_px * pt_per_px
        x1_pt = (x_px + w_px) * pt_per_px
        y1_pt = (y_px + h_px) * pt_per_px
        diff_box_top = (x0_pt, y0_pt, x1_pt, y1_pt)
        diff_box_bottom = (x0_pt, page_height_pt - y1_pt, x1_pt, page_height_pt - y0_pt)

        def test_overlap(boxes: List[Tuple[float, float, float, float]]) -> bool:
            return any(_box_overlaps(diff_box_top, b) or _box_overlaps(diff_box_bottom, b) for b in boxes)

        if test_overlap(char_boxes):
            counts["TEXT"] += 1
        elif test_overlap(rule_boxes):
            counts["RULE"] += 1
        elif test_overlap(fill_boxes):
            counts["FILL"] += 1
        else:
            counts["OTHER"] += 1

    return counts


def compute_pixel_metrics_and_heatmap(
    orig_img_bgr: np.ndarray,
    gen_img_bgr: np.ndarray,
    heatmap_path: str,
    orig_layer: PageByteLayer,
    diff_threshold: float = 16.0 / 255.0,
    dpi: int = 300,
    page_height_pt: float = 792.0,
) -> Tuple[PixelMetrics, Dict[str, int]]:
    """Compute SSIM, pixel diff percentage, difference heatmap, and failure attribution."""
    os.makedirs(os.path.dirname(os.path.abspath(heatmap_path)), exist_ok=True)

    orig_h, orig_w = orig_img_bgr.shape[:2]
    gen_h, gen_w = gen_img_bgr.shape[:2]

    # Align dimensions if slight pixel rounding occurred
    if (gen_h, gen_w) != (orig_h, orig_w):
        gen_img_bgr = cv2.resize(gen_img_bgr, (orig_w, orig_h), interpolation=cv2.INTER_AREA)

    gray_orig = cv2.cvtColor(orig_img_bgr, cv2.COLOR_BGR2GRAY)
    gray_gen = cv2.cvtColor(gen_img_bgr, cv2.COLOR_BGR2GRAY)

    # Compute grayscale SSIM
    ssim_val, diff_map = ssim(gray_orig, gray_gen, full=True)
    ssim_score = float(np.clip(ssim_val, 0.0, 1.0))

    # Thresholded pixel difference
    abs_diff = np.abs(gray_orig.astype(np.int16) - gray_gen.astype(np.int16))
    threshold_int = int(diff_threshold * 255.0 if diff_threshold <= 1.0 else diff_threshold)
    diff_mask = (abs_diff > threshold_int).astype(np.uint8)

    diff_count = int(np.count_nonzero(diff_mask))
    total_pixels = int(diff_mask.size)
    diff_percent = (diff_count / total_pixels) * 100.0 if total_pixels > 0 else 0.0

    # Render difference heatmap blended with original
    err_map = (255 - (diff_map * 255.0)).astype(np.uint8)
    heatmap_colored = cv2.applyColorMap(err_map, cv2.COLORMAP_JET)
    blended = cv2.addWeighted(orig_img_bgr, 0.6, heatmap_colored, 0.4, 0)
    cv2.imwrite(heatmap_path, blended)

    # Failure attribution
    attribution = attribute_failures(
        diff_mask=diff_mask,
        orig_layer=orig_layer,
        dpi=dpi,
        page_height_pt=page_height_pt,
    )

    pixel_metrics = PixelMetrics(
        ssim=round(ssim_score, 4),
        diff_percent=round(diff_percent, 3),
        differing_pixels_count=diff_count,
        total_pixels=total_pixels,
        heatmap_path=heatmap_path,
        diff_threshold=diff_threshold,
    )

    return pixel_metrics, attribution
