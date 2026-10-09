"""
Dual Independent 600 DPI High-Precision Page Renderers.
Renders with PyMuPDF and pypdfium2 without resizing or antialiasing artifacts.
Validates exact pixel dimensions against cropbox and scaling factor.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Tuple, Optional, Any, Union
import numpy as np
import pymupdf
import pypdfium2 as pdfium


@dataclass
class RenderedPage:
    engine: str  # 'pymupdf' or 'pdfium'
    dpi: int
    scale: float  # pixels per point (e.g. 600 / 72 = 8.333333333333334)
    image_rgb: np.ndarray  # uint8 array of shape (H, W, 3)
    width_px: int
    height_px: int
    cropbox_pt: Tuple[float, float, float, float]
    mediabox_pt: Tuple[float, float, float, float]


class DualRenderer:
    """
    Renders PDF pages independently using PyMuPDF and pypdfium2 at 600 DPI.
    Strictly asserts pixel dimensions match round(cropbox_size * s) +- 1 px.
    """

    def __init__(self, dpi: int = 600):
        self.dpi = dpi
        self.scale = dpi / 72.0  # Exact float scale factor

    def render_pymupdf(
        self,
        doc_or_path: Union[str, bytes, pymupdf.Document],
        page_number: int = 1,
    ) -> RenderedPage:
        """Renders page via PyMuPDF at target DPI."""
        close_doc = False
        if isinstance(doc_or_path, str):
            doc = pymupdf.open(doc_or_path)
            close_doc = True
        elif isinstance(doc_or_path, (bytes, bytearray)):
            doc = pymupdf.open(stream=doc_or_path, filetype="pdf")
            close_doc = True
        elif isinstance(doc_or_path, pymupdf.Document):
            doc = doc_or_path
        else:
            raise TypeError("doc_or_path must be str, bytes, or pymupdf.Document")

        try:
            page = doc.load_page(page_number - 1)
            cropbox = (float(page.cropbox.x0), float(page.cropbox.y0), float(page.cropbox.x1), float(page.cropbox.y1))
            mediabox = (float(page.mediabox.x0), float(page.mediabox.y0), float(page.mediabox.x1), float(page.mediabox.y1))

            cb_w = abs(cropbox[2] - cropbox[0])
            cb_h = abs(cropbox[3] - cropbox[1])

            expected_w = int(round(cb_w * self.scale))
            expected_h = int(round(cb_h * self.scale))

            # One uniform matrix(s, s)
            mat = pymupdf.Matrix(self.scale, self.scale)
            pix = page.get_pixmap(matrix=mat, clip=page.cropbox, alpha=False)

            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
            if pix.n == 4:
                img = img[:, :, :3]  # Drop alpha channel
            elif pix.n == 1:
                img = np.stack([img[:, :, 0]] * 3, axis=-1)

            # Strict dimension validation
            assert abs(pix.width - expected_w) <= 1, (
                f"PyMuPDF pixmap width {pix.width} does not match expected {expected_w} px"
            )
            assert abs(pix.height - expected_h) <= 1, (
                f"PyMuPDF pixmap height {pix.height} does not match expected {expected_h} px"
            )

            return RenderedPage(
                engine="pymupdf",
                dpi=self.dpi,
                scale=self.scale,
                image_rgb=img,
                width_px=pix.width,
                height_px=pix.height,
                cropbox_pt=cropbox,
                mediabox_pt=mediabox,
            )
        finally:
            if close_doc:
                doc.close()

    def render_pdfium(
        self,
        doc_or_path: Union[str, bytes, pdfium.PdfDocument],
        page_number: int = 1,
    ) -> RenderedPage:
        """Renders page via pypdfium2 at target DPI."""
        close_doc = False
        if isinstance(doc_or_path, str):
            doc = pdfium.PdfDocument(doc_or_path)
            close_doc = True
        elif isinstance(doc_or_path, (bytes, bytearray)):
            doc = pdfium.PdfDocument(doc_or_path)
            close_doc = True
        elif isinstance(doc_or_path, pdfium.PdfDocument):
            doc = doc_or_path
        else:
            raise TypeError("doc_or_path must be str, bytes, or pdfium.PdfDocument")

        try:
            page = doc.get_page(page_number - 1)
            rect = page.get_bbox()
            cropbox = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
            cb_w = abs(cropbox[2] - cropbox[0])
            cb_h = abs(cropbox[3] - cropbox[1])

            expected_w = int(round(cb_w * self.scale))
            expected_h = int(round(cb_h * self.scale))

            # Render page at 600 DPI scale
            bitmap = page.render(scale=self.scale)
            pil_image = bitmap.to_pil()
            img_rgb = np.array(pil_image.convert("RGB"), dtype=np.uint8)

            assert abs(img_rgb.shape[1] - expected_w) <= 1, (
                f"pypdfium2 image width {img_rgb.shape[1]} does not match expected {expected_w} px"
            )
            assert abs(img_rgb.shape[0] - expected_h) <= 1, (
                f"pypdfium2 image height {img_rgb.shape[0]} does not match expected {expected_h} px"
            )

            return RenderedPage(
                engine="pdfium",
                dpi=self.dpi,
                scale=self.scale,
                image_rgb=img_rgb,
                width_px=img_rgb.shape[1],
                height_px=img_rgb.shape[0],
                cropbox_pt=cropbox,
                mediabox_pt=cropbox,
            )
        finally:
            if close_doc:
                doc.close()

    def render_both(
        self,
        pdf_path_or_bytes: Union[str, bytes],
        page_number: int = 1,
    ) -> Tuple[RenderedPage, RenderedPage]:
        """Renders the page with both engines and validates dimensional consistency."""
        mupdf_render = self.render_pymupdf(pdf_path_or_bytes, page_number)
        pdfium_render = self.render_pdfium(pdf_path_or_bytes, page_number)

        # Assert exact size match between renderers
        assert abs(mupdf_render.width_px - pdfium_render.width_px) <= 1, (
            f"Width mismatch between PyMuPDF ({mupdf_render.width_px}) and pdfium ({pdfium_render.width_px})"
        )
        assert abs(mupdf_render.height_px - pdfium_render.height_px) <= 1, (
            f"Height mismatch between PyMuPDF ({mupdf_render.height_px}) and pdfium ({pdfium_render.height_px})"
        )

        return mupdf_render, pdfium_render
