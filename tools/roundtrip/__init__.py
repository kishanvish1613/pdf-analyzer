"""Closed-loop roundtrip verification harness.

Flow: original.pdf -> our spec (JSON) -> generated PDF via ReportLab / WeasyPrint
      -> rasterize at 300 DPI -> compare pixel & geometry metrics.
"""

from tools.roundtrip.roundtrip import (
    run_roundtrip,
    run_all_roundtrips,
    RoundtripResult,
    generate_summary_markdown,
)
from tools.roundtrip.metrics import (
    PixelMetrics,
    GeometryMetrics,
    WordBox,
    extract_words_from_l0,
    compute_geometry_metrics,
    compute_pixel_metrics_and_heatmap,
)

__all__ = [
    "run_roundtrip",
    "run_all_roundtrips",
    "RoundtripResult",
    "generate_summary_markdown",
    "PixelMetrics",
    "GeometryMetrics",
    "WordBox",
    "extract_words_from_l0",
    "compute_geometry_metrics",
    "compute_pixel_metrics_and_heatmap",
]

