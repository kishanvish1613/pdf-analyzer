"""Master Roundtrip Verification Harness Execution Engine.

Executes the closed-loop verification pipeline:
original.pdf -> spec (JSON) -> generated PDF (ReportLab / WeasyPrint)
-> 300 DPI rasterization -> SSIM / pixel diff / geometry metrics / failure attribution
-> evaluation against thresholds.yaml.
"""

from __future__ import annotations
import os
import glob
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import yaml

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline
from tools.roundtrip.exporters.reportlab_exporter import generate_reportlab_pdf
from tools.roundtrip.exporters.weasyprint_exporter import generate_weasyprint_pdf
from tools.roundtrip.metrics import (
    PixelMetrics,
    GeometryMetrics,
    WordBox,
    extract_words_from_l0,
    compute_geometry_metrics,
    compute_pixel_metrics_and_heatmap,
    rasterize_page_at_dpi,
)

logger = logging.getLogger(__name__)


@dataclass
class RoundtripResult:
    template_name: str
    pdf_path: str
    exporter: str
    page_number: int
    spec_path: str
    generated_pdf_path: str
    generated_html_path: Optional[str]
    diff_heatmap_path: str
    pixel_metrics: PixelMetrics
    geometry_metrics: GeometryMetrics
    failure_attribution: Dict[str, int]
    thresholds: Dict[str, Any]
    passed: bool
    failure_reasons: List[str] = field(default_factory=list)
    is_heldout: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_name": self.template_name,
            "pdf_path": self.pdf_path,
            "exporter": self.exporter,
            "page_number": self.page_number,
            "is_heldout": self.is_heldout,
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
            "pixel_metrics": {
                "ssim": self.pixel_metrics.ssim,
                "diff_percent": self.pixel_metrics.diff_percent,
                "differing_pixels": self.pixel_metrics.differing_pixels_count,
                "total_pixels": self.pixel_metrics.total_pixels,
                "heatmap_path": self.pixel_metrics.heatmap_path,
            },
            "geometry_metrics": {
                "total_orig_words": self.geometry_metrics.total_orig_words,
                "total_gen_words": self.geometry_metrics.total_gen_words,
                "matched_words": self.geometry_metrics.matched_words_count,
                "unmatched_orig_words_count": len(self.geometry_metrics.unmatched_orig_words),
                "unmatched_gen_words_count": len(self.geometry_metrics.unmatched_gen_words),
                "dx_pt": self.geometry_metrics.dx_pt,
                "dy_pt": self.geometry_metrics.dy_pt,
                "dw_pt": self.geometry_metrics.dw_pt,
                "dh_pt": self.geometry_metrics.dh_pt,
            },
            "failure_attribution": self.failure_attribution,
            "thresholds_applied": self.thresholds,
        }


def load_thresholds(thresholds_path: Optional[str] = None) -> Dict[str, Any]:
    """Load pass/fail threshold limits from YAML file."""
    if thresholds_path is None:
        thresholds_path = os.path.join(os.path.dirname(__file__), "thresholds.yaml")

    if os.path.exists(thresholds_path):
        try:
            with open(thresholds_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data or {}
        except Exception as e:
            logger.warning(f"Could not load thresholds from {thresholds_path}: {e}")

    # Default fallback limits (conservative)
    return {
        "default": {
            "ssim_min": 0.70,
            "diff_percent_max": 25.0,
            "word_dx_p95_max_pt": 30.0,
            "word_dy_p95_max_pt": 30.0,
        }
    }


def get_threshold_for_template(thresholds_data: Dict[str, Any], template_name: str, exporter: str) -> Dict[str, float]:
    """Get the specific or fallback thresholds for a given template and exporter."""
    templates = thresholds_data.get("templates", {})
    t_cfg = templates.get(template_name, {})
    exp_cfg = t_cfg.get(exporter, t_cfg)

    default_cfg = thresholds_data.get("default", {})
    return {
        "ssim_min": float(exp_cfg.get("ssim_min", default_cfg.get("ssim_min", 0.70))),
        "diff_percent_max": float(exp_cfg.get("diff_percent_max", default_cfg.get("diff_percent_max", 25.0))),
        "word_dx_p95_max_pt": float(exp_cfg.get("word_dx_p95_max_pt", default_cfg.get("word_dx_p95_max_pt", 30.0))),
        "word_dy_p95_max_pt": float(exp_cfg.get("word_dy_p95_max_pt", default_cfg.get("word_dy_p95_max_pt", 30.0))),
    }


def run_roundtrip(
    pdf_path: str,
    exporter: str = "reportlab",
    output_dir: str = "out",
    page_number: int = 1,
    diff_threshold: float = 16.0 / 255.0,
    config: Optional[AnalyzerConfig] = None,
    thresholds_file: Optional[str] = None,
    is_heldout: bool = False,
) -> RoundtripResult:
    """Execute complete closed-loop roundtrip verification for a single PDF document.

    Flow:
        1. Extract design spec JSON via AnalysisPipeline.
        2. Generate reproduced PDF using specified exporter (ReportLab or WeasyPrint).
        3. Rasterize original and reproduced PDF at 300 DPI.
        4. Extract words using L0 ByteLayerExtractor on both PDFs and match words.
        5. Compute SSIM, diff percentage, diff heatmap, and failure attribution.
        6. Evaluate metrics against thresholds.yaml.

    Returns:
        RoundtripResult object containing all metrics and pass/fail evaluation.
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf_path}")

    template_name = pdf_file.stem
    template_out_dir = os.path.join(output_dir, template_name)
    os.makedirs(template_out_dir, exist_ok=True)

    # 1. Run pipeline to extract JSON spec
    if config is None:
        config = AnalyzerConfig(dpi=300, output_dir=template_out_dir)
    pipeline = AnalysisPipeline(config)
    pipeline_result = pipeline.process_document(str(pdf_file), output_dir=template_out_dir, page_number=page_number)
    spec = pipeline_result if isinstance(pipeline_result, dict) else getattr(pipeline_result, "spec", {})


    spec_path = os.path.join(template_out_dir, "spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, default=str)

    # 2. Generate PDF via selected exporter
    gen_pdf_path = os.path.join(template_out_dir, f"{exporter}_generated.pdf")
    gen_html_path: Optional[str] = None

    if exporter.lower() == "reportlab":
        generate_reportlab_pdf(spec, gen_pdf_path)
    elif exporter.lower() == "weasyprint":
        gen_html_path = os.path.join(template_out_dir, "weasyprint_template.html")
        generate_weasyprint_pdf(spec, gen_pdf_path, gen_html_path)
    else:
        raise ValueError(f"Unsupported exporter: {exporter}. Must be 'reportlab' or 'weasyprint'.")

    # 3. Rasterize at 300 DPI
    orig_bgr, (orig_w, orig_h) = rasterize_page_at_dpi(str(pdf_file), page_number=page_number, dpi=config.dpi)
    gen_bgr, _ = rasterize_page_at_dpi(gen_pdf_path, page_number=page_number, dpi=config.dpi)

    # 4. Geometry metrics from L0
    orig_words, orig_layer = extract_words_from_l0(str(pdf_file), page_number=page_number)
    gen_words, _ = extract_words_from_l0(gen_pdf_path, page_number=page_number)
    geom_metrics = compute_geometry_metrics(orig_words, gen_words)

    # 5. Pixel metrics, diff heatmap, failure attribution
    heatmap_path = os.path.join(template_out_dir, f"{exporter}_diff.png")
    page_height_pt = float(orig_layer.mediabox_pt[3] if orig_layer and orig_layer.mediabox_pt else 792.0)
    pixel_metrics, attribution = compute_pixel_metrics_and_heatmap(
        orig_img_bgr=orig_bgr,
        gen_img_bgr=gen_bgr,
        heatmap_path=heatmap_path,
        orig_layer=orig_layer,
        diff_threshold=diff_threshold,
        dpi=config.dpi,
        page_height_pt=page_height_pt,
    )

    # 6. Threshold evaluation
    thresholds_data = load_thresholds(thresholds_file)
    applied_thresh = get_threshold_for_template(thresholds_data, template_name, exporter)

    passed = True
    failure_reasons: List[str] = []

    if pixel_metrics.ssim < applied_thresh["ssim_min"]:
        passed = False
        failure_reasons.append(
            f"SSIM {pixel_metrics.ssim:.4f} < min {applied_thresh['ssim_min']:.4f}"
        )

    if pixel_metrics.diff_percent > applied_thresh["diff_percent_max"]:
        passed = False
        failure_reasons.append(
            f"Diff {pixel_metrics.diff_percent:.2f}% > max {applied_thresh['diff_percent_max']:.2f}%"
        )

    if geom_metrics.dx_pt["p95"] > applied_thresh["word_dx_p95_max_pt"]:
        passed = False
        failure_reasons.append(
            f"Word dx p95 {geom_metrics.dx_pt['p95']:.2f} pt > max {applied_thresh['word_dx_p95_max_pt']:.2f} pt"
        )

    if geom_metrics.dy_pt["p95"] > applied_thresh["word_dy_p95_max_pt"]:
        passed = False
        failure_reasons.append(
            f"Word dy p95 {geom_metrics.dy_pt['p95']:.2f} pt > max {applied_thresh['word_dy_p95_max_pt']:.2f} pt"
        )

    return RoundtripResult(
        template_name=template_name,
        pdf_path=str(pdf_file),
        exporter=exporter,
        page_number=page_number,
        spec_path=spec_path,
        generated_pdf_path=gen_pdf_path,
        generated_html_path=gen_html_path,
        diff_heatmap_path=heatmap_path,
        pixel_metrics=pixel_metrics,
        geometry_metrics=geom_metrics,
        failure_attribution=attribution,
        thresholds=applied_thresh,
        passed=passed,
        failure_reasons=failure_reasons,
        is_heldout=is_heldout,
    )


def generate_summary_markdown(
    results: List[RoundtripResult],
    heldout_results: Optional[List[RoundtripResult]] = None,
) -> str:
    """Generate a clean Markdown summary table from a list of RoundtripResults."""
    lines: List[str] = []
    lines.append("# Closed-Loop Roundtrip Verification Summary")
    lines.append("")
    lines.append("## Corpus Verification Results")
    lines.append("")
    lines.append("| Template | Exporter | SSIM | Diff % | p95 dx (pt) | p95 dy (pt) | Fail Attribution (TEXT/RULE/FILL/OTHER) | Status |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in results:
        attr = r.failure_attribution
        attr_str = f"{attr.get('TEXT', 0)} / {attr.get('RULE', 0)} / {attr.get('FILL', 0)} / {attr.get('OTHER', 0)}"
        status_str = "✅ PASS" if r.passed else f"❌ FAIL ({', '.join(r.failure_reasons)})"
        lines.append(
            f"| `{r.template_name}` | `{r.exporter}` | {r.pixel_metrics.ssim:.4f} | {r.pixel_metrics.diff_percent:.2f}% | {r.geometry_metrics.dx_pt['p95']:.2f} | {r.geometry_metrics.dy_pt['p95']:.2f} | {attr_str} | {status_str} |"
        )

    if heldout_results:
        lines.append("")
        lines.append("## Held-out Evaluation (corpus/heldout/)")
        lines.append("")
        lines.append("> [!NOTE] Held-out PDFs are excluded from all rule/threshold tuning.")
        lines.append("")
        lines.append("| Template | Exporter | SSIM | Diff % | p95 dx (pt) | p95 dy (pt) | Fail Attribution | Status |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in heldout_results:
            attr = r.failure_attribution
            attr_str = f"{attr.get('TEXT', 0)} / {attr.get('RULE', 0)} / {attr.get('FILL', 0)} / {attr.get('OTHER', 0)}"
            status_str = "✅ PASS" if r.passed else f"❌ FAIL ({', '.join(r.failure_reasons)})"
            lines.append(
                f"| `{r.template_name}` | `{r.exporter}` | {r.pixel_metrics.ssim:.4f} | {r.pixel_metrics.diff_percent:.2f}% | {r.geometry_metrics.dx_pt['p95']:.2f} | {r.geometry_metrics.dy_pt['p95']:.2f} | {attr_str} | {status_str} |"
            )

    return "\n".join(lines)


def run_all_roundtrips(
    manifest_path: str = "tests/corpus/manifest.json",
    corpus_dir: str = "uploads",
    heldout_dir: str = "corpus/heldout",
    output_dir: str = "out",
    exporters: Optional[List[str]] = None,
    thresholds_file: Optional[str] = None,
) -> Tuple[List[RoundtripResult], List[RoundtripResult]]:
    """Run roundtrip across all templates in corpus and held-out folder, generating summary.md."""
    if exporters is None:
        exporters = ["reportlab", "weasyprint"]

    pdf_entries: List[str] = []

    # 1. Read manifest if present
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                items = json.load(f)
                for it in items:
                    f_path = it.get("file", "")
                    if os.path.exists(f_path):
                        pdf_entries.append(f_path)
        except Exception as e:
            logger.warning(f"Error reading manifest {manifest_path}: {e}")

    # Fallback to corpus_dir
    if not pdf_entries and os.path.exists(corpus_dir):
        pdf_entries = sorted(glob.glob(os.path.join(corpus_dir, "*.pdf")))

    corpus_results: List[RoundtripResult] = []
    for pdf_p in pdf_entries:
        for exp in exporters:
            logger.info(f"Running roundtrip on {pdf_p} with {exp}...")
            try:
                res = run_roundtrip(
                    pdf_path=pdf_p,
                    exporter=exp,
                    output_dir=output_dir,
                    thresholds_file=thresholds_file,
                    is_heldout=False,
                )
                corpus_results.append(res)
            except Exception as e:
                logger.error(f"Failed roundtrip for {pdf_p} ({exp}): {e}", exc_info=True)

    # 2. Check heldout folder
    heldout_results: List[RoundtripResult] = []
    for h_dir in [heldout_dir, os.path.join("tests", heldout_dir), os.path.join("tests", "heldout")]:
        if os.path.exists(h_dir):
            for pdf_p in sorted(glob.glob(os.path.join(h_dir, "*.pdf"))):
                for exp in exporters:
                    logger.info(f"Running held-out roundtrip on {pdf_p} with {exp}...")
                    try:
                        res = run_roundtrip(
                            pdf_path=pdf_p,
                            exporter=exp,
                            output_dir=output_dir,
                            thresholds_file=thresholds_file,
                            is_heldout=True,
                        )
                        heldout_results.append(res)
                    except Exception as e:
                        logger.error(f"Failed heldout roundtrip for {pdf_p} ({exp}): {e}", exc_info=True)
            break

    # 3. Write summary.md
    summary_md = generate_summary_markdown(corpus_results, heldout_results)
    summary_path = os.path.join(output_dir, "summary.md")
    os.makedirs(output_dir, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_md)

    logger.info(f"Wrote summary to {summary_path}")
    return corpus_results, heldout_results

