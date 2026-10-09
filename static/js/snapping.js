/**
 * Vector Magnetic Snapping Engine for Interactive Dimension Editor.
 * Snaps to REAL PDF drawings from SnapIndex: rule centers, painted inner/outer edges,
 * box edges, text ink bboxes, baselines, and page boundaries.
 * Snap calculations performed in screen pixel distance at active zoom.
 */

export class SnappingEngine {
  /**
   * @param {number} thresholdScreenPx - Snap radius in client screen pixels (default 8px)
   */
  constructor(thresholdScreenPx = 8.0) {
    this.thresholdScreenPx = thresholdScreenPx;
    this.enabled = true;
  }

  /**
   * Resolves magnetic snap coordinates against the real PDF SnapIndex.
   * @param {number} rawXPt - Unsnapped cursor X in PDF points
   * @param {number} rawYPt - Unsnapped cursor Y in PDF points
   * @param {Object} model - EditorModel containing snap_index and guides
   * @param {number} zoom - Current zoom scale factor
   * @param {boolean} ctrlHeld - If true, temporarily bypass snapping
   * @returns {{x: number, y: number, snappedX: boolean, snappedY: boolean, targets: Array<{desc: string, type: string}>}}
   */
  resolveSnap(rawXPt, rawYPt, model, zoom = 1.0, ctrlHeld = false) {
    if (!this.enabled || ctrlHeld || !model) {
      return { x: rawXPt, y: rawYPt, snappedX: false, snappedY: false, targets: [] };
    }

    const snapIndex = model.snap_index || {};
    const maxDistPt = this.thresholdScreenPx / Math.max(0.1, zoom);

    let snappedX = rawXPt;
    let snappedY = rawYPt;
    let isSnappedX = false;
    let isSnappedY = false;
    let minDeltaX = maxDistPt;
    let minDeltaY = maxDistPt;
    const matchedTargets = [];

    // Check raw_targets_x
    const targetsX = snapIndex.raw_targets_x || snapIndex.targets_x || [];
    for (const t of targetsX) {
      const coord = Number(t.coord !== undefined ? t.coord : t.x);
      const d = Math.abs(rawXPt - coord);
      if (d < minDeltaX) {
        minDeltaX = d;
        snappedX = coord;
        isSnappedX = true;
        matchedTargets.length = 0;
        matchedTargets.push({
          desc: t.label || t.desc || `Snap X = ${coord.toFixed(3)} pt`,
          type: t.target_type || 'x_snap',
          target_id: t.target_id
        });
      }
    }

    // Check raw_targets_y
    const targetsY = snapIndex.raw_targets_y || snapIndex.targets_y || [];
    for (const t of targetsY) {
      const coord = Number(t.coord !== undefined ? t.coord : t.y);
      const d = Math.abs(rawYPt - coord);
      if (d < minDeltaY) {
        minDeltaY = d;
        snappedY = coord;
        isSnappedY = true;
        matchedTargets.push({
          desc: t.label || t.desc || `Snap Y = ${coord.toFixed(3)} pt`,
          type: t.target_type || 'y_snap',
          target_id: t.target_id
        });
      }
    }

    // Fallback checking rule centers and edges
    if (!isSnappedX) {
      for (const r of (snapIndex.rule_centers_v || [])) {
        const rx = Number(r.coord !== undefined ? r.coord : r.x);
        const d = Math.abs(rawXPt - rx);
        if (d < minDeltaX) {
          minDeltaX = d;
          snappedX = rx;
          isSnappedX = true;
          matchedTargets.push({ desc: r.label || r.desc || `Rule center x = ${rx.toFixed(3)} pt`, type: 'rule_v' });
        }
      }
    }

    if (!isSnappedY) {
      for (const hr of (snapIndex.rule_centers_h || [])) {
        const hry = Number(hr.coord !== undefined ? hr.coord : hr.y);
        const d = Math.abs(rawYPt - hry);
        if (d < minDeltaY) {
          minDeltaY = d;
          snappedY = hry;
          isSnappedY = true;
          matchedTargets.push({ desc: hr.label || hr.desc || `H-Rule center y = ${hry.toFixed(3)} pt`, type: 'rule_h' });
        }
      }
    }

    return {
      x: snappedX,
      y: snappedY,
      snappedX: isSnappedX,
      snappedY: isSnappedY,
      targets: matchedTargets
    };
  }
}
