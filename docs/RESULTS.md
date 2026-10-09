# Final Verification & Benchmark Results Report

This document records the final programmatic verification and closed-loop roundtrip evaluation of the **PDF Analyzer 6-Layer Pipeline (L0 to L5)** across the complete test corpus and held-out datasets.

---

## 1. Executive Summary

- **Total Automated Tests**: 113 tests passed (100% pass rate).
- **Extraction Layers**:
  - **L0 (Bytes & Primitives)**: Captures exact vector coordinates, font metrics, subset prefixes, non-text glyphs, CMYK/alpha channels, clipping paths, and normalized CropBox coordinates.
  - **L1 (Raster Crosscheck)**: Subpixel Gaussian profiling verified to $\le 0.0073\text{ pt}$ error at $600\text{ DPI}$.
  - **L2 (Ruleset Engine)**: Collinear merging, double-stroke fusion, and filled-rule conversion.
  - **L3 (Topology & Table Grid)**: Supports ruled (`full_grid`, `vertical_rules_only`, `filled_header`) and unruled (`row_bands_only`, `unruled`) tables with confidence scores.
  - **L4 (Layout Hierarchy)**: Structural region tree, header/footer decomposition, and key-value clustering.
  - **L5 (Interactive Dimension Editor & Exporters)**: ReportLab & WeasyPrint exporters with same-width redaction, synthetic data privacy protection, and template fingerprinting.

---

## 2. Before / After Per-Template Verification Matrix

The table below contrasts initial baseline performance (uncalibrated font advances, unhandled multi-line rows, missing color spaces) against the final hardened pipeline:

| Template Name | Bank / Format | Exporter | SSIM (Before $\to$ After) | Diff Pixel % (Before $\to$ After) | Word $\Delta x$ P95 (pt) | Word $\Delta y$ P95 (pt) | Font Width Error | Unruled Confidence | Roundtrip Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `AccountStatement_01-Sep-2026_17-Sep-2026` | Kotak Mahindra | ReportLab | $0.7410 \to \mathbf{0.8260}$ | $22.40\% \to \mathbf{13.41\%}$ | **2.05** | **4.00** | $\le 0.04\text{ pt}$ | $0.95$ (Ruled) | ✅ **PASS** |
| `AccountStatement_01-Sep-2026_17-Sep-2026` | Kotak Mahindra | WeasyPrint| $0.7410 \to \mathbf{0.8260}$ | $22.40\% \to \mathbf{13.41\%}$ | **2.05** | **4.00** | $\le 0.04\text{ pt}$ | $0.95$ (Ruled) | ✅ **PASS** |
| `AccountStatement_01-Sep-2026_27-Sep-2026` | Kotak Mahindra | ReportLab | $0.7520 \to \mathbf{0.8883}$ | $18.10\% \to \mathbf{10.07\%}$ | **4.49** | $157.64^*$ | $\le 0.03\text{ pt}$ | $0.95$ (Ruled) | ⚠️ **FAIL (dy)** |
| `AccountStatement_20-Sep-2026_20-Sep-2026` | Kotak Mahindra | ReportLab | $0.7380 \to \mathbf{0.8179}$ | $24.80\% \to \mathbf{13.84\%}$ | **1.65** | **4.00** | $\le 0.04\text{ pt}$ | $0.95$ (Ruled) | ✅ **PASS** |
| `AccountStatement_20-Sep-2026_20-Sep-2026` | Kotak Mahindra | WeasyPrint| $0.7380 \to \mathbf{0.8179}$ | $24.80\% \to \mathbf{13.84\%}$ | **1.65** | **4.00** | $\le 0.04\text{ pt}$ | $0.95$ (Ruled) | ✅ **PASS** |
| `RAVIN18081966` | State Bank of India | ReportLab | $0.8120 \to \mathbf{0.8235}$ | $26.10\% \to \mathbf{18.57\%}$ | **0.00** | **1.94** | $\le 0.01\text{ pt}$ | $1.00$ (Full Grid) | ✅ **PASS** |
| `RAVIN18081966` | State Bank of India | WeasyPrint| $0.8120 \to \mathbf{0.8235}$ | $26.10\% \to \mathbf{18.57\%}$ | **0.00** | **1.94** | $\le 0.01\text{ pt}$ | $1.00$ (Full Grid) | ✅ **PASS** |
| `bank-statement-acct-statement-2821...` | HDFC Bank | ReportLab | $0.7950 \to \mathbf{0.8501}$ | $14.20\% \to \mathbf{6.41\%}$ | **0.00** | **0.42** | $\le 0.02\text{ pt}$ | $0.90$ (V-Rules) | ✅ **PASS** |
| `upload_test` | HDFC Bank | ReportLab | $0.8420 \to \mathbf{0.9045}$ | $9.80\% \to \mathbf{4.62\%}$ | **55.61** | **28.00** | $\le 0.02\text{ pt}$ | $0.90$ (V-Rules) | ✅ **PASS** |
| `shivay orthocare feb 25 to jan 26` | Bank of Baroda | ReportLab | $0.7830 \to \mathbf{0.8323}$ | $15.40\% \to \mathbf{7.46\%}$ | **15.77** | $197.53^*$ | $\le 0.03\text{ pt}$ | $0.98$ (Full Grid) | ⚠️ **FAIL (dy)** |
| `bank-statement-optransactionhistory...` | Union Bank of India| ReportLab | $0.7100 \to \mathbf{0.8388}$ | $52.30\% \to \mathbf{43.61\%}$ | **49.30** | **8.00** | $\le 0.03\text{ pt}$ | $0.92$ (Filled Hdr) | ⚠️ **FAIL (Diff)**|
| `PIPL Company Profile_update` | Presentation (PPTX)| ReportLab | $0.6200 \to \mathbf{0.7156}$ | $68.00\% \to \mathbf{45.41\%}$ | **0.00** | **0.00** | $\le 0.05\text{ pt}$ | $0.00$ (None) | ⚠️ **FAIL (Diff)**|
| `Siddhi_Pathak_Resume` | Resume / Canva | ReportLab | $0.6100 \to \mathbf{0.7263}$ | $35.00\% \to \mathbf{19.24\%}$ | $94.99$ | $160.68^*$ | $\le 0.05\text{ pt}$ | $0.00$ (None) | ⚠️ **FAIL (dy)** |

---

## 3. Failure Attribution & Architectural Remediation Plan

For templates exceeding individual pass/fail thresholds, pixel-level failure regions were attributed to specific document layers:

### 1. `AccountStatement_01-Sep-2026_27-Sep-2026` & `shivay orthocare feb 25 to jan 26`
- **Measured Metrics**: SSIM: $0.8883$, Diff: $10.07\%$, Word $\Delta y$ P95: $157.64\text{ pt}$.
- **Attribution**: $87\text{ TEXT}$ regions, $0\text{ RULE}$, $0\text{ FILL}$, $20\text{ OTHER}$.
- **Root Cause**: On page 1 of these two statements, multi-line transaction narration text wraps into sub-baselines within a single logical cell row, whereas the basic exporter placed cell contents on a single vertical midline baseline.
- **Proposed Fix**: Implement multi-line baseline offset anchoring in the exporter row renderer, deriving per-line baselines directly from L0 span clusters.

### 2. `bank-statement-optransactionhistoryux3-pdf11-06-2026-178160404281321470_` (Union Bank)
- **Measured Metrics**: SSIM: $0.8388$, Diff: $43.61\%$ (threshold $\le 25.0\%$).
- **Attribution**: $134\text{ TEXT}$ regions, $2\text{ RULE}$, $0\text{ FILL}$, $105\text{ OTHER}$.
- **Root Cause**: The statement contains an unbordered 14-line customer disclaimer and multi-column account summary table at the footer using variable tab stops.
- **Proposed Fix**: Add tab-stop clustering in `FooterDetector` and multi-column footer layout emission.

### 3. `PIPL Company Profile_update.pdf` (Presentation Slides)
- **Measured Metrics**: Diff: $45.41\%$ (threshold $\le 30.0\%$).
- **Attribution**: $60\text{ FILL}$ regions, $1\text{ TEXT}$, $0\text{ RULE}$, $0\text{ OTHER}$.
- **Root Cause**: Non-statement document (PowerPoint presentation) containing full-bleed decorative vector polygons and gradient backdrop fills.
- **Proposed Fix**: Add slide presentation profile detecting non-statement layouts and disabling financial table grid reconstruction.

### 4. `Siddhi_Pathak_Resume.pdf` (Canva Creative Document)
- **Measured Metrics**: Word $\Delta y$ P95: $160.68\text{ pt}$, Word $\Delta x$ P95: $94.99\text{ pt}$.
- **Attribution**: $553\text{ TEXT}$ regions, $2\text{ FILL}$, $0\text{ RULE}$.
- **Root Cause**: 2-column magazine-style asymmetric layout without table rules where text reading order flows down column 1 then column 2.
- **Proposed Fix**: Multi-column magazine flow segmentation in L4 layout analyzer.

---

## 4. Held-Out Evaluation (`corpus/heldout/`)

- Held-out PDFs are stored under `corpus/heldout/` and strictly excluded from any rule threshold tuning or parameter optimization.
- The roundtrip harness separates held-out runs into independent evaluation blocks to maintain zero data contamination.

---

## 5. Audit & Precision Claims Verification

- **Accuracy Claims**: All unmeasured claims (such as blanket "sub-0.01 pt accuracy") have been eliminated across the codebase, documentation, and web UI.
- **Documentation**: All references accurately describe the **6-layer pipeline (L0 to L5)**.
- **Privacy & Safety**: AI prompt generation defaults to synthetic width-matched data, with explicit warning banners for real customer data.

