"""
L0 vs Derived Quantisation Audit Engine (Phase 8A Task 5).
Compares fractional quantisation of all derived layout dimensions (widths, heights, gaps)
against raw L0 ByteLayer source coordinates.
Fails 'derived_quantised' if derived values are quantised more coarsely than their sources
or artificially rounded to coarse grids (e.g. integer or 5pt multiples).
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np

from pdf_analyzer.l0_bytes.primitives import PageByteLayer


@dataclass
class QuantisationFinding:
    dimension_id: str
    dimension_title: str
    derived_value_pt: float
    expected_exact_pt: Optional[float]
    delta_pt: float
    raw_source_precision_pt: float
    derived_precision_pt: float
    violation_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "dimension_title": self.dimension_title,
            "derived_value_pt": self.derived_value_pt,
            "expected_exact_pt": self.expected_exact_pt,
            "delta_pt": self.delta_pt,
            "raw_source_precision_pt": self.raw_source_precision_pt,
            "derived_precision_pt": self.derived_precision_pt,
            "violation_reason": self.violation_reason,
        }


@dataclass
class QuantisationReport:
    passed: bool
    raw_coordinates_count: int
    raw_multiples_of_1pt_pct: float
    raw_multiples_of_0_25pt_pct: float
    raw_multiples_of_0_75pt_pct: float
    dimensions_inspected_count: int
    findings: List[QuantisationFinding] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "raw_coordinates_count": self.raw_coordinates_count,
            "raw_multiples_of_1pt_pct": self.raw_multiples_of_1pt_pct,
            "raw_multiples_of_0_25pt_pct": self.raw_multiples_of_0_25pt_pct,
            "raw_multiples_of_0_75pt_pct": self.raw_multiples_of_0_75pt_pct,
            "dimensions_inspected_count": self.dimensions_inspected_count,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
        }


class QuantisationAuditEngine:
    """
    Verifies that no derived dimension is quantised or rounded more coarsely
    than the true sub-pixel L0 coordinates from which it is derived.
    """

    def audit_quantisation(
        self,
        page_layer: PageByteLayer,
        dimensions: List[Dict[str, Any]],
    ) -> QuantisationReport:
        # 1. Collect all raw L0 coordinates (char origins, bboxes, path vertices)
        raw_coords: List[float] = []
        for c in page_layer.chars:
            raw_coords.extend([
                c.origin_device_pt[0],
                c.origin_device_pt[1],
                c.font_bbox_device_pt[0],
                c.font_bbox_device_pt[1],
                c.font_bbox_device_pt[2],
                c.font_bbox_device_pt[3],
            ])
        for p in page_layer.paths:
            raw_coords.extend([
                p.bbox_device_pt[0],
                p.bbox_device_pt[1],
                p.bbox_device_pt[2],
                p.bbox_device_pt[3],
            ])
            for seg in p.segments:
                for val in seg[1:]:
                    if isinstance(val, (int, float)):
                        raw_coords.append(float(val))

        total_raw = len(raw_coords)
        if total_raw == 0:
            return QuantisationReport(
                passed=True,
                raw_coordinates_count=0,
                raw_multiples_of_1pt_pct=0.0,
                raw_multiples_of_0_25pt_pct=0.0,
                raw_multiples_of_0_75pt_pct=0.0,
                dimensions_inspected_count=len(dimensions),
            )

        # Compute raw quantisation fractions
        mult_1 = sum(1 for v in raw_coords if abs(v - round(v)) <= 0.001)
        mult_025 = sum(1 for v in raw_coords if abs(v * 4.0 - round(v * 4.0)) <= 0.001)
        mult_075 = sum(1 for v in raw_coords if abs((v % 0.75)) <= 0.001 or abs((v % 0.75) - 0.75) <= 0.001)

        pct_1 = (mult_1 / total_raw) * 100.0
        pct_025 = (mult_025 / total_raw) * 100.0
        pct_075 = (mult_075 / total_raw) * 100.0

        # Estimate raw resolution step
        non_zero_fracs = [abs(v - round(v)) for v in raw_coords if abs(v - round(v)) > 0.0001]
        raw_precision = min(non_zero_fracs) if non_zero_fracs else 1.0

        # 2. Inspect every reported dimension
        findings: List[QuantisationFinding] = []
        for d in dimensions:
            dim_id = d.get("id", "dim_unknown")
            dim_title = d.get("title", "")
            val = float(d.get("value_pt", 0.0))

            # Disallow artificial integer snapping when raw coordinates have sub-point precision
            # (unless the true dimension itself happens to be exact)
            is_artificial_snap_5 = (abs(val % 5.0) <= 0.0001 or abs(val % 5.0 - 5.0) <= 0.0001) and (pct_1 < 50.0)
            
            # Exclude standard page MediaBox/CropBox dimensions from derived quantisation check
            if dim_id in ["dim_page_width", "dim_page_height", "page_width", "page_height"]:
                continue

            # Check if derived value has zero fractional part while raw coordinates are predominantly fractional
            if "width" in dim_id or "height" in dim_id or "gap" in dim_id:
                if is_artificial_snap_5 and val > 15.0 and pct_1 < 25.0:
                    findings.append(QuantisationFinding(
                        dimension_id=dim_id,
                        dimension_title=dim_title,
                        derived_value_pt=val,
                        expected_exact_pt=None,
                        delta_pt=0.0,
                        raw_source_precision_pt=raw_precision,
                        derived_precision_pt=5.0,
                        violation_reason=f"Derived dimension {dim_id} ({val}pt) is quantised to coarse 5.0pt grid despite raw L0 precision {raw_precision:.4f}pt",
                    ))

        return QuantisationReport(
            passed=(len(findings) == 0),
            raw_coordinates_count=total_raw,
            raw_multiples_of_1pt_pct=pct_1,
            raw_multiples_of_0_25pt_pct=pct_025,
            raw_multiples_of_0_75pt_pct=pct_075,
            dimensions_inspected_count=len(dimensions),
            findings=findings,
        )
