"""Configuration module for PDF Design Analyzer with strict tolerances."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ToleranceConfig:
    """Tolerance thresholds for coordinate clustering, alignment, and snap math (in PDF points)."""
    # Strict alignment snap tolerance (points)
    alignment_tolerance_pt: float = 0.5
    # Strict axis clustering tolerance for common margins/columns (points)
    axis_cluster_tolerance_pt: float = 0.5
    # Line merging tolerance for collinear near-duplicate strokes
    line_merge_collinear_tolerance_pt: float = 0.5
    # Tolerance for matching vector borders with text boxes
    border_snap_tolerance_pt: float = 1.0
    # Tolerance for decimal alignment comparison
    decimal_alignment_tolerance_pt: float = 1.0
    # Centering tolerance relative to container center
    centering_tolerance_pt: float = 1.5
    # Threshold for thin filled rect to be treated as a line
    thin_rect_as_line_max_dim_pt: float = 2.0
    # Line thickness deviation warning threshold between vector and sub-pixel FWHM
    thickness_deviation_threshold_pt: float = 0.10
    # Minimum padding threshold before flagging touching border
    min_padding_touching_threshold_pt: float = 1.0
    # Minimum IoU for self-check vector vs overlay validation
    min_self_check_iou: float = 0.98
    # Gap threshold between table bottom and footer
    footer_min_gap_below_table_pt: float = 15.0
    # Minimum whitespace gap for horizontal/vertical cuts
    column_gap_min_pt: float = 12.0
    whitespace_cut_ratio: float = 1.5
    cluster_x_tol_pt: float = 1.0


@dataclass
class RasterConfig:
    """Settings for rasterization and sub-pixel computer vision measurements."""
    dpi: int = 600  # High-res 600 DPI for sub-pixel accuracy
    preview_dpi: int = 300
    color_palette_k: int = 6
    color_mode_percentile: float = 20.0  # Darkest/most saturated 20%
    subpixel_profile_samples: int = 40
    ocr_enabled_fallback: bool = True
    ocr_min_char_count: int = 15


@dataclass
class AnalyzerConfig:
    """Root configuration for PDF Design Analyzer pipeline."""
    dpi: int = 600
    preview_dpi: int = 300
    pages: str = "all"
    output_dir: str = "./output"
    include_visual_overlays: bool = True
    include_multi_layer_overlays: bool = True
    include_closed_loop_verification: bool = True
    max_closed_loop_iterations: int = 3
    ssim_re_measure_threshold: float = 0.92
    tolerances: ToleranceConfig = field(default_factory=ToleranceConfig)
    raster: RasterConfig = field(default_factory=RasterConfig)
    
    header_keywords: List[str] = field(default_factory=lambda: [
        "statement", "account", "bank", "summary", "activity", "period", "transaction"
    ])
    account_field_keywords: List[str] = field(default_factory=lambda: [
        "account number", "account no", "a/c no", "account name", "customer name",
        "account holder", "statement period", "date range", "branch", "ifsc", "ifsc code",
        "micr", "swift", "currency", "opening balance", "closing balance", "available balance",
        "address", "pan", "gstin", "customer id", "cif"
    ])
    table_column_keywords: List[str] = field(default_factory=lambda: [
        "date", "txn date", "value date", "details", "description", "particulars",
        "narrative", "narration", "ref", "chq / ref no", "withdrawal", "debit", "dr",
        "deposit", "credit", "cr", "balance", "closing balance"
    ])

