/**
 * Coordinate Transformation & Precision Math Engine for PDF Dimension Editor.
 * Single Source of Truth: PDF Points (pt), Top-Left Origin of CropBox.
 * Provides bidirectional mapping between Screen (client/viewport pixels) and Document (pt)
 * with strict Float64 mathematical precision across all zoom levels (25% - 3200%).
 */

export class CoordinateTransform {
  /**
   * @param {number} pageWidthPt - Page CropBox width in points
   * @param {number} pageHeightPt - Page CropBox height in points
   * @param {number} dpi - Analysis DPI (e.g. 300)
   */
  constructor(pageWidthPt = 612.0, pageHeightPt = 792.0, dpi = 300) {
    this.pageWidthPt = Number(pageWidthPt);
    this.pageHeightPt = Number(pageHeightPt);
    this.dpi = Number(dpi);
    this.scaleFactor = this.dpi / 72.0; // px per pt at native raster DPI
  }

  /**
   * Converts point in PDF points to continuous screen viewport coordinates.
   * @param {number} xPt - X in PDF points
   * @param {number} yPt - Y in PDF points
   * @param {DOMRect} svgRect - Bounding client rect of the SVG element
   * @param {number} zoom - Current zoom multiplier (1.0 = 100%)
   * @param {number} panX - Pan offset X in screen pixels
   * @param {number} panY - Pan offset Y in screen pixels
   * @returns {{x: number, y: number}}
   */
  ptToScreen(xPt, yPt, svgRect, zoom = 1.0, panX = 0.0, panY = 0.0) {
    if (!svgRect || svgRect.width <= 0 || svgRect.height <= 0) {
      return { x: xPt, y: yPt };
    }
    // Fraction along SVG viewBox
    const fracX = xPt / this.pageWidthPt;
    const fracY = yPt / this.pageHeightPt;

    const screenX = svgRect.left + (fracX * svgRect.width);
    const screenY = svgRect.top + (fracY * svgRect.height);

    return { x: screenX, y: screenY };
  }

  /**
   * Converts screen viewport coordinates (e.g. mouse event clientX, clientY) to exact PDF points.
   * @param {number} screenX - Screen client X in pixels
   * @param {number} screenY - Screen client Y in pixels
   * @param {DOMRect} svgRect - Bounding client rect of the SVG element
   * @returns {{x: number, y: number}}
   */
  screenToPt(screenX, screenY, svgRect) {
    if (!svgRect || svgRect.width <= 0 || svgRect.height <= 0) {
      return { x: 0.0, y: 0.0 };
    }
    const relX = screenX - svgRect.left;
    const relY = screenY - svgRect.top;

    const fracX = Math.max(0.0, Math.min(1.0, relX / svgRect.width));
    const fracY = Math.max(0.0, Math.min(1.0, relY / svgRect.height));

    const xPt = fracX * this.pageWidthPt;
    const yPt = fracY * this.pageHeightPt;

    return {
      x: Math.max(0.0, Math.min(this.pageWidthPt, xPt)),
      y: Math.max(0.0, Math.min(this.pageHeightPt, yPt))
    };
  }

  /**
   * Unit conversions
   */
  ptToMm(pt) {
    return (Number(pt) * 25.4) / 72.0;
  }

  mmToPt(mm) {
    return (Number(mm) * 72.0) / 25.4;
  }

  ptToPx(pt, dpi = null) {
    const activeDpi = dpi || this.dpi;
    return (Number(pt) * activeDpi) / 72.0;
  }

  pxToPt(px, dpi = null) {
    const activeDpi = dpi || this.dpi;
    return (Number(px) * 72.0) / activeDpi;
  }

  ptToInches(pt) {
    return Number(pt) / 72.0;
  }

  inchesToPt(inches) {
    return Number(inches) * 72.0;
  }

  /**
   * Self-test invariant: Round-trip transformation check
   * Clicking raster pixel (xPt, yPt) must return xPt within 0.01 pt.
   */
  testPrecision(testPoints = [[100.5, 200.25], [36.0, 72.0], [300.123, 450.789]], mockRect = { left: 50, top: 100, width: 612 * 2, height: 792 * 2 }) {
    for (const [x, y] of testPoints) {
      const scr = this.ptToScreen(x, y, mockRect);
      const back = this.screenToPt(scr.x, scr.y, mockRect);
      const deltaX = Math.abs(back.x - x);
      const deltaY = Math.abs(back.y - y);
      if (deltaX > 0.01 || deltaY > 0.01) {
        console.error(`Precision check failed for (${x}, ${y}): delta=(${deltaX}, ${deltaY})`);
        return false;
      }
    }
    return true;
  }
}
