# PDF Design Analyzer

A production-grade Python document layout and design analysis engine specialized for financial documents, bank statements, and structured tabular PDFs. It reverse-engineers the exact visual design specification—including page geometry, typography hierarchy, margins, column partitions, row height statistics, numeric alignments, vector strokes, and background shading—so layouts can be recreated pixel-accurately in web templates (HTML/CSS) or programmatic PDF generators (ReportLab, Typst, Weasyprint).

---

## 1. System Architecture & 6-Layer Pipeline (L0 to L5)

The PDF Analyzer reverse-engineers digital-native documents through a deterministic, strictly measured **6-layer pipeline (L0 to L5)**:

```
+-----------------------------------------------------------------------------------------+
|                                    INPUT: Document.pdf                                  |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
     +-------------------------------------------------------------------------------+
     |  L0: Bytes & Primitives (PyMuPDF / fitz)                                      |
     |  - Content stream text spans, character baselines, glyph advances, font XREFs  |
     |  - Vector paths, line segments, rects, fill operations, non-text glyph flags  |
     +-------------------------------------------------------------------------------+
                                             |
                                             v
     +-------------------------------------------------------------------------------+
     |  L1: Raster Crosscheck (OpenCV & NumPy)                                       |
     |  - 300 / 600 DPI morphological rendering & sub-pixel Gaussian peak fitting    |
     |  - FWHM stroke thickness validation and K-Means dominant fill sampling        |
     +-------------------------------------------------------------------------------+
                                             |
                                             v
     +-------------------------------------------------------------------------------+
     |  L2: Ruleset Engine                                                           |
     |  - Stroke width consolidation, collinear rule merging, fill band bounding     |
     +-------------------------------------------------------------------------------+
                                             |
                                             v
     +-------------------------------------------------------------------------------+
     |  L3: Topology & Table Grid Engine                                             |
     |  - Multi-style classification (full_grid, vertical_only, unruled, row_bands)  |
     |  - Ink-free vertical projection gutters, baseline clustering, row pitch stats |
     +-------------------------------------------------------------------------------+
                                             |
                                             v
     +-------------------------------------------------------------------------------+
     |  L4: Layout Hierarchy & Semantics                                             |
     |  - Semantic region nesting (header, account_info, table, footer)              |
     |  - Key-value pairing, numeric alignment (decimal/right), Indian/Intl formats  |
     +-------------------------------------------------------------------------------+
                                             |
                                             v
     +-------------------------------------------------------------------------------+
     |  L5: Dimension Editor & Exporters                                             |
     |  - Interactive SVG dimension lane editor with low-confidence visual flags     |
     |  - 1:1 ReportLab Python and WeasyPrint HTML/CSS code generators               |
     +-------------------------------------------------------------------------------+
                                             |
                     +-----------------------+-----------------------+
                     |                       |                       |
                     v                       v                       v
          +--------------------+  +--------------------+  +--------------------+
          |  design_spec.json  |  |  design_report.md  |  | annotated_page.png |
          | (Full JSON Spec)   |  | (Human Summary)    |  | (Visual Overlays)  |
          +--------------------+  +--------------------+  +--------------------+
```

---

## 2. Measured Precision & Accuracy

All precision values are verified against programmatic synthetic ground truth and empirical raster cross-checks (see [docs/PRECISION.md](docs/PRECISION.md) for full methodology and per-template reports):

| Pipeline Layer | Measurement Target | Benchmark Method | Mean Error | P95 Error | Max Error | Pass Criterion |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **L0: Bytes & Primitives** | Vector H-Rule Coordinates | Synthetic Ground Truth | **0.0000 pt** | **0.0000 pt** | **0.0000 pt** | $\le 0.05\text{ pt}$ |
| **L0: Bytes & Primitives** | Vector V-Rule Coordinates | Synthetic Ground Truth | **0.0000 pt** | **0.0000 pt** | **0.0000 pt** | $\le 0.05\text{ pt}$ |
| **L0: Bytes & Primitives** | Text String Origin $(x, y)$ | Synthetic Ground Truth | **0.0000 pt** | **0.0000 pt** | **0.0000 pt** | $\le 0.05\text{ pt}$ |
| **L1: Raster Crosscheck** | Rule Center ($600\text{ DPI}$) | Subpixel Gaussian Profiling | **0.0041 pt** | **0.0064 pt** | **0.0073 pt** | $\le 0.15\text{ pt}$ |
| **L1: Raster Crosscheck** | Rule Center ($300\text{ DPI}$) | Subpixel Gaussian Profiling | **0.0064 pt** | **0.0132 pt** | **0.0140 pt** | $\le 0.30\text{ pt}$ |
| **L1: Raster Crosscheck** | FWHM Stroke Thickness ($600\text{ DPI}$)| FWHM Intensity Peak Fit | **0.0059 pt** | **0.0115 pt** | **0.0115 pt** | $\le 0.20\text{ pt}$ |
| **L3: Table Grid** | Ruled Closure Invariant | Ruled Statements Corpus | **0.0000 pt** | **0.0000 pt** | **0.0000 pt** | $\le 0.25\text{ pt}$ |
| **L3: Table Grid** | Virtual Column Gutters | Synthetic Unruled Benchmarks | **0.0010 pt** | **0.0020 pt** | **0.0035 pt** | $\le 0.50\text{ pt}$ |
| **L5: Exporters / Roundtrip**| Ruled Word Position $\Delta x$ | ReportLab & WeasyPrint Harness | **0.65 pt** | **0.85 pt** | **1.20 pt** | $p95 \le 2.0\text{ pt}$ |
| **L5: Exporters / Roundtrip**| Virtual/Unruled Word $\Delta x$ | ReportLab & WeasyPrint Harness | **1.45 pt** | **2.05 pt** | **2.80 pt** | $p95 \le 3.0\text{ pt}$ |

---

## 3. Tech Stack & Prerequisites

- **Python 3.10+** (Tested on Python 3.10, 3.11, 3.12, 3.13)
- **PyMuPDF (`fitz`)**: Low-level text span extraction, character baselines, font descriptor flags, embedded images, and vector paths.
- **pdfplumber**: Independent vector edge and table cell boundary cross-validation.
- **OpenCV (`cv2`) + NumPy + Pillow**: 300 DPI rasterization, morphological line detection, and K-Means color clustering.
- **pandas**: Tabular data structuring and CSV exporting.
- **Click**: Command-line interface.
- **ReportLab**: Synthetic statement generation and PDF template regeneration.
- **pytest**: Test suite verifying geometry tolerances.

---

## 4. Installation

```bash
git clone https://github.com/example/pdf-analyzer.git
cd pdf-analyzer
pip install -r requirements.txt
```

---

## 5. Web UI & CLI Usage

### A. Launch the Interactive Web Dashboard (Recommended)

Start the local web application:
```bash
python app.py
```
Then open your browser to **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

#### Features in the Web Dashboard:
- **Drag & Drop Upload Zone**: Drop any bank statement PDF directly into the browser.
- **"Try Sample Statement" Demo**: 1-click button that generates a sample bank statement and analyzes it immediately.
- **Annotated Visual Overlay**: View the 300 DPI high-resolution page with margin guides, column bounds, and region highlights.
- **Tabbed Spec Explorer**:
  - 📊 **Table & Alignment**: Column widths in `pt`, `mm`, `px`, `%`, and standard deviation alignment scores for debit/credit/balance.
  - 🔤 **Typography & Colors**: Font family, weight, HEX swatches, and CSS snippet copy.
  - 📐 **Margins & Spacing**: 4-unit measurements and inter-section gaps.
  - 🎨 **HTML/CSS Sandbox**: Live iframe reproduction of the extracted design.
  - 📋 **Elements Table**: Filterable table of all text spans and coordinates.
- **Download Center**: 1-click download for `design_spec.json`, `design_report.md`, `elements.csv`, `annotated_page_1.png`, and reproduced PDF.

---

### B. Command-Line Interface (CLI)

```bash
# Analyze a PDF at 300 DPI and output to ./output
python analyzer.py input.pdf --dpi 300 --out ./output --pages all

# Analyze only specific pages (e.g. page 1 or pages 1 to 3)
python analyzer.py input.pdf --pages 1 --out ./output
python analyzer.py input.pdf --pages 1-3 --out ./output

# Enable verbose debug logging
python analyzer.py input.pdf -v
```

### Generated Artifacts

1. `design_spec.json`: Machine-readable specification adhering to the strict JSON schema.
2. `design_report.md`: Formatted Markdown summary with geometry tables, typography inventories, and alignment scores.
3. `annotated_page_N.png`: Visual layout verification overlays displaying margins, regions, column dividers, and measurements.
4. `elements.csv`: Comprehensive CSV dataset with every text span measured in `pt`, `mm`, `px`, and `%`.
5. `extracted_logo.png`: Cropped and isolated bank emblem / logo.

---

## 6. Template Regeneration

Verify visual fidelity by regenerating the extracted specification into HTML/CSS or a ReportLab PDF:

```bash
# Convert design_spec.json into HTML/CSS and ReportLab PDF
python regenerator.py ./output/design_spec.json --out-html reproduced.html --out-pdf reproduced.pdf
```

---

## 7. Detailed Module Specifications (A through M)

| Module | Name | Key Capabilities |
| :--- | :--- | :--- |
| **A** | **Overall Layout & Structure** | Identifies page size, orientation, cropbox vs mediabox, region hierarchy (`header`, `account_details`, `transaction_table`, `footer`), repeating running headers across pages, and multi-column body structures. |
| **B** | **Exact Positioning & Alignment** | Computes bounding boxes, character baselines, classifies horizontal alignment (`left`, `right`, `center`, `justified`), clusters shared alignment axes, and measures element-to-element offsets. |
| **C** | **Margins, Padding & Spacing** | Measures top, right, bottom, and left page margins, inter-section gaps (header-to-account, account-to-table, table-to-footer), line leading, character spacing, and whitespace maps. |
| **D** | **Table Column & Row Geometry** | Detects ruled and borderless tables; computes column widths, headers, alignment, and cell padding; calculates row heights (min, max, mean, median, std dev); detects multi-line wrapped cells. |
| **E** | **Transaction Vertical Spacing** | Calculates baseline-to-baseline distances, row gaps, spacing differences between single-line vs wrapped transactions, zebra striping, and flags spacing outliers (> 2σ). |
| **F** | **Header & Account Details** | Generic regex/spatial key-value extractor for Bank Name, Statement Period, Account Holder, Account Number, IFSC, Branch, and Currency. Detects 2-column grids and enclosure boxes. |
| **G** | **Typography & Font Roles** | Strips subset prefixes (e.g. `ABCDEF+`), extracts font family, size, flags (bold, italic, serif, mono), inferred weight (`regular`, `medium`, `semibold`, `bold`), colors (HEX/RGB), and builds a role hierarchy (H1, H2, Table Header, Body, Footer). |
| **H** | **Borders, Lines & Cell Grid** | Vector stroke extractor classifying horizontal rules, vertical rules, cell borders, dash patterns, line caps, stroke widths, and table grid structure (`full_grid`, `horizontal_only`, `borderless`). |
| **I** | **Background Colors & Shading** | Vector fill extraction cross-validated with OpenCV K-Means pixel sampling; identifies page background, table header fills, alternating zebra striping, and flags gradients. |
| **J** | **Logo Positioning & Extraction** | Identifies raster images or vector curve emblems in header, calculates bounding box, aspect ratio, distances from margins and header text, and saves `extracted_logo.png`. |
| **K** | **Key Placements (Date & Heading)** | Regex detection for date formats (`DD/MM/YYYY`, `DD-MMM-YYYY`, `ISO 8601`), title centering math against page center line, and account details grid matrix. |
| **L** | **Debit / Credit / Balance Alignment** | Classifies right vs decimal-point alignment with standard deviation validation; detects currency symbols, number systems (Indian vs International), negative conventions, and empty-cell indicators. |
| **M** | **Pixel Measurements & CV Validation**| Cross-checks vector points against raster pixels (`pt × DPI / 72`), runs OpenCV morphological line detection, computes relative dimensional ratios, and provides unit calibration constants. |

---

## 8. JSON Schema (`design_spec.json`)

Every measurement in `design_spec.json` includes four units (`pt`, `mm`, `px`, `rel_pct`), measurement source (`vector`, `text`, `raster`, or `inferred`), and a confidence rating:

```json
{
  "meta": {
    "page_number": 1,
    "total_pages": 1,
    "width": { "pt": 612.0, "mm": 215.9, "px": 2550.0, "rel_pct": 100.0, "source": "vector", "confidence": 1.0 },
    "height": { "pt": 792.0, "mm": 279.4, "px": 3300.0, "rel_pct": 100.0, "source": "vector", "confidence": 1.0 },
    "orientation": "portrait",
    "rotation_deg": 0,
    "dpi": 300,
    "coordinate_system": "top-left origin (x=0, y=0 at top-left; x increases right, y increases down)"
  },
  "layout": {
    "regions": [
      {
        "region_type": "header",
        "bbox": { "x0": {"pt": 44.0}, "y0": {"pt": 43.7}, "x1": {"pt": 505.4}, "y1": {"pt": 144.1}, "width": {"pt": 461.4}, "height": {"pt": 100.4} },
        "element_count": 10,
        "description": "Top document header containing bank branding/title"
      }
    ],
    "columns": { "type": "single_column", "count": 1, "column_left_edges_pt": [44.0] }
  },
  "margins_spacing": {
    "page_margins": {
      "top": { "pt": 43.74, "mm": 15.43, "px": 182.2, "rel_pct": 5.52, "source": "vector", "confidence": 1.0 },
      "right": { "pt": 42.0, "mm": 14.82, "px": 175.0, "rel_pct": 6.86, "source": "vector", "confidence": 1.0 },
      "bottom": { "pt": 296.9, "mm": 104.74, "px": 1237.1, "rel_pct": 37.49, "source": "vector", "confidence": 1.0 },
      "left": { "pt": 42.0, "mm": 14.82, "px": 175.0, "rel_pct": 6.86, "source": "vector", "confidence": 1.0 }
    }
  },
  "table": {
    "columns": [
      {
        "column_index": 0,
        "header_text": "Txn Date",
        "semantic_type": "date",
        "alignment": "left",
        "width": { "pt": 59.45, "mm": 20.97, "px": 247.7, "rel_pct": 9.71 }
      }
    ],
    "row_height_stats": {
      "mean_height_pt": 17.71,
      "median_height_pt": 11.68,
      "min_height_pt": 9.62,
      "max_height_pt": 37.18,
      "is_uniform_height": false
    }
  },
  "typography": {
    "styles": [
      {
        "role": "document_title_h1",
        "clean_font_family": "Helvetica",
        "font_size_pt": 18.0,
        "inferred_weight": "bold",
        "color_hex": "#1A365D",
        "recommended_leading_pt": 22.0
      }
    ]
  },
  "alignment": {
    "numeric_columns": {
      "numeric_column_details": {
        "Withdrawal (Dr)": {
          "alignment_type": "decimal_point_aligned",
          "right_edge_std_dev_pt": 11.103,
          "thousand_separator_system": "International (100,000)",
          "negative_format": "minus_prefix: -1,234.50",
          "empty_cell_convention": "hyphen ('-')"
        }
      }
    }
  },
  "pixel_measurements": {
    "calibration": {
      "target_dpi": 300,
      "px_per_pt": 4.1667,
      "px_per_mm": 11.811
    }
  },
  "confidence": {
    "layout_structure": 0.95,
    "typography_extraction": 0.98,
    "table_geometry": 0.95,
    "numeric_alignment": 0.92,
    "pixel_cross_validation": 1.0
  }
}
```

---

## 9. Known Limitations & Accuracy Improvements

1. **Complex Vector Emblems vs Raster Logos**:
   - *Limitation:* Bank logos created from dozens of disjoint Bézier paths require spatial clustering to group into a single bounding box.
   - *Improvement:* Group overlapping vector path clusters using DBSCAN with a 5 pt radius window in the header region.
2. **Dense Multi-Line Wrapped Transactions**:
   - *Limitation:* In borderless statements with no horizontal lines, distinguishing between a wrapped description line and a closely spaced next transaction relies on the presence of a date or reference number in column 1.
   - *Improvement:* If date parsing is ambiguous, the engine combines baseline projection clustering with vertical whitespace projection profiles.
3. **Scanned / Degraded PDFs**:
   - *Limitation:* Scanned documents lack vector text streams, fonts, and bounding boxes.
   - *Improvement:* The engine activates Tesseract OCR fallback with connected-component bounding box estimation, adjusting the confidence rating to `~0.65` and reporting `source: "raster"`.

---

## 10. Running Tests

```bash
# Run complete test suite with pytest
python -m pytest -v
```
