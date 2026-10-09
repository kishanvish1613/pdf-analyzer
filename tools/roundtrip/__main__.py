"""CLI entrypoint for tools.roundtrip.

Usage:
    python -m tools.roundtrip --all
    python -m tools.roundtrip --pdf uploads/upload_test.pdf --exporter reportlab
    python -m tools.roundtrip --heldout
"""

from __future__ import annotations
import sys
import os
import argparse
import logging
from tools.roundtrip.roundtrip import run_roundtrip, run_all_roundtrips, generate_summary_markdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("roundtrip")


def main():
    parser = argparse.ArgumentParser(description="Closed-Loop Roundtrip Verification Harness")
    parser.add_argument("--all", action="store_true", help="Run roundtrip across all corpus documents and held-out templates")
    parser.add_argument("--pdf", type=str, default=None, help="Path to a single PDF document to test")
    parser.add_argument("--exporter", type=str, choices=["reportlab", "weasyprint", "all"], default="all", help="Exporter to test (default: all)")
    parser.add_argument("--heldout", action="store_true", help="Run only held-out templates in corpus/heldout/")
    parser.add_argument("--manifest", type=str, default="tests/corpus/manifest.json", help="Path to corpus manifest")
    parser.add_argument("--corpus-dir", type=str, default="uploads", help="Corpus directory fallback")
    parser.add_argument("--heldout-dir", type=str, default="corpus/heldout", help="Held-out documents directory")
    parser.add_argument("--output-dir", type=str, default="out", help="Output directory for generated PDFs, diffs, and summary.md")
    parser.add_argument("--thresholds", type=str, default=None, help="Path to thresholds.yaml")
    args = parser.parse_args()

    exporters = ["reportlab", "weasyprint"] if args.exporter == "all" else [args.exporter]

    if args.pdf:
        results = []
        for exp in exporters:
            logger.info(f"Running roundtrip on {args.pdf} [{exp}]...")
            res = run_roundtrip(
                pdf_path=args.pdf,
                exporter=exp,
                output_dir=args.output_dir,
                thresholds_file=args.thresholds,
            )
            results.append(res)
            print(f"\n--- Result: {res.template_name} ({exp}) ---")
            print(f"Status: {'PASS' if res.passed else 'FAIL'}")
            print(f"SSIM: {res.pixel_metrics.ssim:.4f}")
            print(f"Diff %: {res.pixel_metrics.diff_percent:.2f}%")
            print(f"Word dx p95: {res.geometry_metrics.dx_pt['p95']:.2f} pt | dy p95: {res.geometry_metrics.dy_pt['p95']:.2f} pt")
            print(f"Failure attribution: {res.failure_attribution}")
            if res.failure_reasons:
                print(f"Failures: {', '.join(res.failure_reasons)}")

        summary_md = generate_summary_markdown(results)
        summary_path = os.path.join(args.output_dir, "summary.md")
        os.makedirs(args.output_dir, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_md)
        print(f"\nWrote summary to {summary_path}")

    elif args.heldout:
        logger.info("Running held-out evaluation...")
        _, heldout_res = run_all_roundtrips(
            manifest_path="none",
            corpus_dir="none",
            heldout_dir=args.heldout_dir,
            output_dir=args.output_dir,
            exporters=exporters,
            thresholds_file=args.thresholds,
        )
        print(f"Evaluated {len(heldout_res)} held-out runs. Wrote {os.path.join(args.output_dir, 'summary.md')}")

    else:
        # Run all
        logger.info("Running complete corpus & held-out roundtrip suite...")
        corpus_res, heldout_res = run_all_roundtrips(
            manifest_path=args.manifest,
            corpus_dir=args.corpus_dir,
            heldout_dir=args.heldout_dir,
            output_dir=args.output_dir,
            exporters=exporters,
            thresholds_file=args.thresholds,
        )
        print(f"\nCompleted {len(corpus_res)} corpus runs and {len(heldout_res)} held-out runs.")
        print(f"Summary generated at: {os.path.join(args.output_dir, 'summary.md')}")


if __name__ == "__main__":
    main()

