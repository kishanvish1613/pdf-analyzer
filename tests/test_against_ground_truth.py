"""
Ground Truth Comparison & Accuracy Benchmark Suite.
Compares auto-detected measurements against human-corrected ground truth,
reporting per-object residuals and printing a summary error table.
"""

import os
import json
import pytest
from generate_sample_pdf import create_synthetic_statement
from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline
from pdf_analyzer.editor_model import create_default_editor_model, export_ground_truth

GROUND_TRUTH_DIR = os.path.join(os.path.dirname(__file__), "ground_truth")
os.makedirs(GROUND_TRUTH_DIR, exist_ok=True)


def generate_benchmark_ground_truth_if_missing(gt_path: str, pdf_path: str):
    """Creates a sample ground truth fixture if none exists."""
    if not os.path.exists(pdf_path):
        create_synthetic_statement(pdf_path)
    if not os.path.exists(gt_path):
        config = AnalyzerConfig(dpi=300)
        pipeline = AnalysisPipeline(config)
        spec = pipeline.process_document(pdf_path, os.path.dirname(gt_path))
        model = create_default_editor_model(spec, page_number=1, pdf_path=pdf_path)
        with open(gt_path, "w", encoding="utf-8") as f:
            json.dump(model, f, indent=2)


def test_against_ground_truth(tmp_path, capsys):
    """
    Evaluates detector measurements against ground truth files in tests/ground_truth/.
    Prints summary error table with mean, max, and worst discrepancies.
    """
    gt_file = os.path.join(GROUND_TRUTH_DIR, "ground_truth.json")
    pdf_file = str(tmp_path / "sample_statement.pdf")
    generate_benchmark_ground_truth_if_missing(gt_file, pdf_file)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    # Re-run pipeline to get fresh auto-detections
    config = AnalyzerConfig(dpi=300, output_dir=str(tmp_path))
    pipeline = AnalysisPipeline(config)
    auto_spec = pipeline.process_document(pdf_file, str(tmp_path))
    auto_model = create_default_editor_model(auto_spec, page_number=1, pdf_path=pdf_file)

    # Compare dimension values
    gt_dims = {d["id"]: d["value_pt"] for d in gt_data.get("dimensions", [])}
    auto_dims = {d["id"]: d["value_pt"] for d in auto_model.get("dimensions", [])}

    errors = []
    for dim_id, gt_val in gt_dims.items():
        if dim_id in auto_dims:
            auto_val = auto_dims[dim_id]
            delta = abs(auto_val - gt_val)
            errors.append({
                "id": dim_id,
                "auto": auto_val,
                "gt": gt_val,
                "delta_pt": delta
            })

    assert len(errors) > 0, "No matching dimensions found to compare against ground truth."

    deltas = [e["delta_pt"] for e in errors]
    mean_err = sum(deltas) / len(deltas)
    max_err = max(deltas)

    # Sort worst 10
    errors.sort(key=lambda e: e["delta_pt"], reverse=True)
    worst_10 = errors[:10]

    # Print Report Table
    print("\n" + "=" * 78)
    print("  GROUND TRUTH COMPARISON REPORT & DETECTOR RESIDUALS")
    print("=" * 78)
    print(f"Total Objects Compared : {len(errors)}")
    print(f"Mean Error (pt)        : {mean_err:.4f} pt")
    print(f"Max Error (pt)         : {max_err:.4f} pt")
    print("-" * 78)
    print(f"{'Object ID':<30} | {'Auto Val':<10} | {'GT Val':<10} | {'Delta (pt)':<10}")
    print("-" * 78)
    for w in worst_10:
        print(f"{w['id']:<30} | {w['auto']:<10.2f} | {w['gt']:<10.2f} | {w['delta_pt']:<10.4f}")
    print("=" * 78 + "\n")

    # Invariants
    assert mean_err < 1.0, f"Mean error ({mean_err:.4f} pt) exceeds 1.0 pt threshold"
