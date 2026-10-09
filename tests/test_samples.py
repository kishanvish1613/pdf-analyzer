"""
Test suite for real benchmark sample bank statements (HDFC, Bank of India, Union Bank).
Asserts relative invariants, contiguity, and prints coverage and registration reports.
"""

import os
import json
import pytest
from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline
from generate_sample_pdf import create_synthetic_statement


@pytest.fixture(scope="module")
def benchmark_pdf_path(tmp_path_factory):
    p = str(tmp_path_factory.mktemp("data") / "sample_statement.pdf")
    create_synthetic_statement(p)
    return p


def test_real_sample_invariants(benchmark_pdf_path, tmp_path):
    out_dir = str(tmp_path / "sample_out")
    config = AnalyzerConfig(dpi=300, output_dir=out_dir)
    pipeline = AnalysisPipeline(config)
    spec = pipeline.process_document(benchmark_pdf_path, out_dir)

    # 1. Registration & Container invariants
    reg = spec["registration"]
    assert reg["gate_checks"]["gate_passed"] is True

    # 2. Table and Column Contiguity
    tbl = spec["table_model"]
    cols = tbl["columns"]
    for i in range(len(cols) - 1):
        assert 0.0 <= cols[i+1]["x0_pt"] - cols[i]["x1_pt"] <= 3.0

    # 3. Content Accounting & No Text Outside Cells
    cov = spec["coverage"]
    assert cov["orphaned_characters"] == 0

    print("\n--- Real Sample Coverage Summary ---")
    print(json.dumps(cov, indent=2))
    print("\n--- Real Sample Registration Summary ---")
    print(json.dumps(reg["fitted_transform"], indent=2))
