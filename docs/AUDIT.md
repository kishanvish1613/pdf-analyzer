# PDF Analyzer — Repository Baseline & Architecture Audit

## 1. Module Map

The PDF Analyzer pipeline is organized into six functional layers (L0 to L5) operating under a deterministic, measurement-driven extraction architecture (no heuristics guessing, no LLM geometry estimation).

| Layer | Module Path | Responsibilities & Purpose | Key Classes & Functions |
|---|---|---|---|
| **L0 Bytes & Primitives** | `pdf_analyzer/l0_bytes/primitives.py` | Data structures for painted primitives (chars, spans, paths, rects, lines, images) | `PaintedTextChar`, `PaintedTextSpan`, `PaintedPath`, `PaintedRect`, `PaintedLine`, `PaintedImage` |
| | `pdf_analyzer/l0_bytes/fonts.py` | Font metadata extraction, standard 14 font metrics, encoding resolution | `FontMetricsDict`, `FontDataExtractor`, `resolve_font_family()`, `get_standard_font_metrics()` |
| | `pdf_analyzer/l0_bytes/interpreter.py` | PDF content stream parser and PyMuPDF low-level device extraction | `ByteLayerExtractor`, `ByteLayerData`, `extract_page_primitives()` |
| | `pdf_analyzer/l0_bytes/ctm.py` | Coordinate transformation matrices and PDF user space conversions | `AffineMatrix`, `transform_point()`, `transform_bbox()` |
| **L1 Crosscheck** | `pdf_analyzer/l1_crosscheck/raster_diff.py` | 300/600 DPI rasterization and image-plane crosscheck | `RasterDiffEngine`, `render_page_raster()`, `compute_ink_residual_mask()` |
| | `pdf_analyzer/l1_crosscheck/edges.py` | OpenCV Sobel/Canny edge and line verification | `EdgeDetector`, `detect_raster_edges()`, `verify_vector_edges()` |
| | `pdf_analyzer/l1_crosscheck/residual.py` | Ink accounting and unassigned pixel residual measurement | `ResidualCalculator`, `measure_coverage_residual()` |
| **L2 Ruleset Engine** | `pdf_analyzer/l2_primitives/ruleset.py` | Vector path classification, collinear rule merging, snapping | `RuleSet`, `Rule`, `extract_rules()`, `merge_collinear_segments()`, `find_junctions()` |
| | `pdf_analyzer/l2_primitives/snapping.py` | Coordinate snapping, endpoint alignment, and grid tolerances | `CoordinateSnapper`, `snap_to_grid()`, `cluster_coordinates()` |
| | `pdf_analyzer/l2_primitives/fills.py` | Shaded background detection, band fills, container fills | `FillDetector`, `extract_fill_regions()`, `classify_fill_bands()` |
| **L3 Topology** | `pdf_analyzer/l3_topology/table_grid.py` | Table boundary recovery, column/row partition detection | `TableGridEngine`, `TableGrid`, `extract_table_grid()`, `detect_columns_from_rules()` |
| | `pdf_analyzer/l3_topology/cells.py` | Cell node construction, spans, and text-to-cell assignment | `CellGridEngine`, `GridCell`, `build_cell_matrix()`, `assign_spans_to_cells()` |
| | `pdf_analyzer/l3_topology/gaps.py` | Inter-cell padding, column gutter, and row pitch measurement | `GapMatrixEngine`, `compute_padding_matrix()`, `compute_gutters()` |
| **L4 Layout Hierarchy** | `pdf_analyzer/l4_layout/hierarchy.py` | Page region classification (Header, Key-Value, Table, Footer) | `LayoutHierarchyBuilder`, `PageLayoutNode`, `classify_regions()` |
| | `pdf_analyzer/l4_layout/headers.py` | Account/statement metadata and side-by-side block parsing | `HeaderParser`, `parse_header_blocks()`, `extract_account_details()` |
| | `pdf_analyzer/l4_layout/footers.py` | Multi-page continuation, pagination, and disclaimer bounding | `FooterParser`, `detect_footer_bounds()`, `parse_page_numbers()` |
| | `pdf_analyzer/l4_layout/key_value.py` | 2-column key-value pairing (colon axis, attached, weight-split) | `KeyValueEngine`, `PairingStrategy`, `extract_key_value_pairs()` |
| **L5 Dimension Editor & Export** | `pdf_analyzer/l5_editor/dimensions.py` | Dimension lanes, delta computation, and constraint model | `DimensionModel`, `EditableDimension`, `apply_dimension_delta()` |
| | `pdf_analyzer/l5_editor/svg_export.py` | Interactive SVG visualization and overlay rendering | `SVGExporter`, `render_editor_svg()`, `render_diagnostic_overlays()` |
| | `pdf_analyzer/l5_editor/reportlab_export.py` | ReportLab Python code generator for 1:1 exact reproduction | `ReportLabGenerator`, `generate_reproduction_script()` |
| | `pdf_analyzer/l5_editor/weasyprint_export.py` | HTML/CSS generator for WeasyPrint 1:1 exact reproduction | `WeasyPrintGenerator`, `generate_html_css_template()` |
| **Pipeline & Tools** | `pdf_analyzer/pipeline.py` | 28-stage master analysis orchestrator | `AnalysisPipeline`, `AnalyzerConfig`, `PipelineResult` |
| | `pdf_analyzer/corpus_check.py` | Corpus regression runner & independent golden comparator | `CorpusCheckEngine`, `CorpusCheckReport`, `DiscrepancyRecord` |
| | `pdf_analyzer/server.py` | Local web application server for interactive visual inspection | Flask web application and API endpoints |

---

## 2. Current Test Strategy & Corpus Parity

### Test Suite Execution Summary
- **Test Runner**: `pytest` 9.1.1 (Python 3.13.15)
- **Total Tests**: 78 passed (0 failed, 4 warnings for sub-pixel Gaussian fit warnings on synthetic edge scans)
- **Execution Time**: ~161 seconds

### Test Suites Breakdown
1. `test_architecture.py`: Layer boundary enforcement, dependency rules, zero forbidden circular imports.
2. `test_l0_bytes.py`: Byte extractor, font table parsers, CTM transforms, painted character coordinate accuracy.
3. `test_l1_crosscheck.py`: OpenCV raster alignment, Sobel edge correlation, residual ink mask computation.
4. `test_l2_l3_topology.py`: Rule clustering, collinear merging, table grid extraction, column split fidelity.
5. `test_l4_layout.py`: Header block segmentation, key-value colon alignment, footer pagination.
6. `test_l5_editor.py`: SVG generation, dimension lane constraints, ReportLab/WeasyPrint export round-tripping.
7. `test_snap_index_and_editor.py`: Coordinate snapping indices, multi-line adjustment synchronization.
8. `test_against_ground_truth.py`: Ground truth comparison on golden benchmarks.
9. `test_corpus_parity.py` / `pdf_analyzer/corpus_check.py`: Corpus-wide parity verification across 10 PDF templates.

### The "0.000 pt Delta" Corpus Parity Test Mechanism
A central requirement of the audit is determining how the "0.000 pt delta" corpus parity test functions and whether the expected value is produced by our own extractor (circular) or by independent ground truth.

**Analysis & Findings**:
1. **Independent Ground Truth Implementation**:
   - The test relies on `tests/independent_probe.py` (`extract_independent_ground_truth()`).
   - `independent_probe.py` imports **zero** modules or classes from `pdf_analyzer`.
   - It interfaces directly with raw `pymupdf.open()` and queries low-level `page.get_drawings()` for vector strokes/rectangles and `page.get_text("words")` for raw text bounding boxes.
   - It performs its own isolated spatial clustering of vertical paths, horizontal rules, and header fill rectangles to determine table bounding boxes and column x-coordinates.
2. **Comparison Execution in `pdf_analyzer/corpus_check.py`**:
   - `corpus_check.py` compares the auto-extracted dimensions from `pdf_analyzer` against either:
     - (a) Explicit manual golden files marked with `"source": "editor_export"`, or
     - (b) The independent ground truth generated by `tests/independent_probe.py`.
3. **Why the Delta is Exactly 0.000 pt**:
   - Digital-native PDF vector path coordinates and character placement coordinates are stored as exact IEEE 754 floating-point values in PDF content streams (e.g., `36.0 720.0 m 559.2 720.0 l S`).
   - Because both `pdf_analyzer`'s L0 interpreter and `independent_probe.py` extract the true underlying PDF vector drawings without heuristics or raster approximations, their measured coordinates match down to machine precision.
   - Across 159 tested objects over the corpus, the mean delta and maximum delta are measured at $\mathbf{0.000\text{ pt}}$.
4. **Conclusion**:
   - The expected values are **produced by independent ground truth** (`tests/independent_probe.py` using raw PyMuPDF), **not** by circular self-extraction from `pdf_analyzer`.

---

## 3. Font Data Inventory (L0 Layer)

### Currently Recorded Attributes (per Character & Text Span)

In `pdf_analyzer/l0_bytes/primitives.py` and `fonts.py`:
- `PaintedTextChar`:
  - `char`: Unicode string representing the character.
  - `origin_pt`: `Tuple[float, float]` representing $(x, y)$ text origin (baseline left).
  - `bbox_pt`: `Tuple[float, float, float, float]` $(x_0, y_0, x_1, y_1)$ exact bounding box in points.
  - `font_name`: PostScript / PDF font name (e.g., `Helvetica-Bold`, `ABCDEE+Calibri`).
  - `font_size_pt`: Font size in points derived from font matrix scale.
  - `ctm`: Current transformation matrix `(a, b, c, d, e, f)`.
  - `text_matrix`: Text transformation matrix `Tm`.
  - `rendering_mode`: PDF text rendering mode $T_{\text{mode}}$ (0=Fill, 1=Stroke, 2=Fill+Stroke, 3=Invisible).
  - `fill_color`: RGB tuple $(r, g, b)$ normalized to $[0.0, 1.0]$.
  - `stroke_color`: Optional RGB tuple $(r, g, b)$ for stroked text.
  - `is_synthetic`: Boolean indicating whether glyph was synthesised.
  - `is_invisible`: Boolean indicating whether rendering mode is 3 (invisible text).
- `PaintedTextSpan`:
  - `text`: Aggregated string for the contiguous span.
  - `bbox_pt`: Enclosing bounding box $(x_0, y_0, x_1, y_1)$.
  - `baseline_y_pt`: Baseline Y coordinate in points.
  - `font_name`: Dominant font name.
  - `font_size_pt`: Dominant font size in points.
  - `color`: Dominant fill color $(r, g, b)$.
  - `flags`: Font style flags (bold, italic, serif, monospace).
  - `chars`: List of constituent `PaintedTextChar` objects.

### Missing Font Attributes (Required for Exact 1:1 Reconstruction)
To ensure 100% faithful reproduction in ReportLab and WeasyPrint, the following attributes from the PDF standard (ISO 32000-1) are currently missing from L0:

1. **Text State Parameters**:
   - `char_spacing` ($T_c$): Extra spacing added between individual characters.
   - `word_spacing` ($T_w$): Extra spacing added between ASCII space characters.
   - `horizontal_scaling` ($T_z$): Percentage width scaling (e.g., 90%, 100%, 110%).
   - `text_rise` ($T_s$): Vertical baseline displacement (for superscripts/subscripts).
   - `leading` ($T_l$): Baseline-to-baseline vertical distance specified in the content stream.
2. **Font Descriptor & Embedding Metadata**:
   - `is_embedded`: Boolean flag indicating whether the font program (TrueType/CFF/Type1) is embedded in the PDF `/FontFile`, `/FontFile2`, or `/FontFile3` stream.
   - `font_subtype`: Specification type (`Type1`, `TrueType`, `Type0` / `CIDFontType2`, `Type3`, `OpenType`).
   - `font_descriptor`: Key metrics from the `/FontDescriptor` dictionary:
     - `Ascent` and `Descent` (unscaled glyph coordinates).
     - `CapHeight` and `XHeight`.
     - `FontBBox` $[x_{\min}, y_{\min}, x_{\max}, y_{\max}]$.
     - `ItalicAngle`.
     - `StemV` (dominant vertical stem thickness).
3. **Glyph Metrics**:
   - `raw_glyph_width` ($W_x$): Unscaled advance width from `/Widths` array or `hmtx` table before transformation by `font_size / 1000`.

---

## 4. Unruled / Borderless Table Behavior (L3 Layer)

When analyzing tables that lack vertical grid lines (such as Kotak Mahindra Bank, Union Bank, or standard borderless account statements), `pdf_analyzer/l3_topology/table_grid.py` executes a multi-strategy recovery pipeline:

```
                  ┌─────────────────────────────────────┐
                  │ L3: Check Vertical Spanning Rules   │
                  └──────────────────┬──────────────────┘
                                     │
                        len(qual_v) >= 2 ?
                       /                   \
                    [Yes]                  [No]
                     /                       \
        ┌─────────────────────────┐  ┌────────────────────────────────────┐
        │ Standard Vector Grid:   │  │ Unruled Fallback Pipeline:         │
        │ Partition columns by    │  │ 1. Filled Header Band Detection   │
        │ vertical rule x-coords  │  │ 2. Header Text Whitespace Gutters  │
        └─────────────────────────┘  │ 3. Numeric Column Alignment Clust.│
                                     │ 4. Horizontal Rule Bounding        │
                                     └────────────────────────────────────┘
```

### Fallback Execution Details

1. **Rule Qualification Check**:
   - The engine checks for qualified vertical rules: lines spanning $> 30\%$ of candidate table height.
   - When fewer than 2 qualified vertical rules exist (`len(qual_v) < 2`), standard rule-based partitioning is bypassed.

2. **Strategy 1: Filled Header Band Recovery (`filled_header`)**:
   - Scans for horizontal filled rectangular vector paths (`PaintedRect` / `cell_paths`) in the upper table region.
   - If contiguous or collinear filled background boxes are detected (e.g., gray or colored column header cells):
     - Derives column boundaries directly from the left/right geometric edges (`x0`, `x1`) of the header rectangles.
     - Sets table style classification to `"filled_header"`.

3. **Strategy 2: Header Text Whitespace Gutters (`horizontal_only` / `borderless`)**:
   - Identifies candidate header lines by matching standard banking keywords (`Date`, `Transaction Particulars`, `Narration`, `Chq / Ref No`, `Withdrawal`, `Deposit`, `Balance`).
   - Extracts the bounding boxes of words on the header line.
   - Computes vertical whitespace gutters between adjacent header words.
   - Column split boundaries are placed at the midpoint of each inter-column whitespace gutter.

4. **Strategy 3: Numeric Column Alignment Clustering**:
   - Extracts body text rows below the header.
   - Identifies financial amounts (e.g. `\d+,\d+\.\d{2}`) and dates (`\d{2}/\d{2}/\d{4}`).
   - Runs 1D spatial clustering on character positions:
     - Right-aligned clusters for credit, debit, and balance columns.
     - Left-aligned clusters for transaction descriptions / narration.
     - Decimal-aligned clusters for currency figures.
   - Projects virtual column boundary lines downward from header gutters guided by cluster boundaries.

5. **Table Bounding Box & Row Partitioning**:
   - Table top and bottom bounds are anchored by top/bottom horizontal rules when present, or by the upper header ink extent and the lowest body row baseline.
   - Row splits are generated by clustering text line baselines and measuring median line pitch ($\Delta y$).

---

## 5. Risk Assessment & Engineering Mitigations

| Risk Area | Specific Failure Mode | Impact | Engineering Mitigation |
|---|---|---|---|
| **Multi-Line Transaction Rows** | In unruled statements, narration text wrapping across 2–4 lines can be misclassified as separate 1-line transactions. | Row count mismatch; cell merge errors in generated ReportLab tables. | Implement transactional anchor grouping: a row is defined by the presence of a leading date/ref-no anchor; subsequent unanchored lines are grouped into the active row's narration cell. |
| **Font Metrics & Glyph Advance Mismatch** | Target PDF uses embedded custom font subset (e.g. `ABCDEE+Calibri`) with unique character spacing ($T_c$) or font matrix; ReportLab uses standard Helvetica. | Text overflows cell bounds or wraps prematurely; visual diff fails. | Extract $T_c$, $T_w$, $T_z$, and exact `/Widths` arrays from L0; embed true TTF/OTF streams or configure ReportLab `stringWidth` calculations with exact character advances. |
| **Floating Point & Resolution Tolerances** | Coordinate differences of $0.05\text{ pt}$ due to varying PDF coordinate systems or CTM scalings. | False positive discrepancy flags in automated regression checks. | Use coordinate snapping index ($0.1\text{ pt}$ precision grid) and relative invariant assertions rather than fragile exact float equality. |
| **Ragged / Sparsely Populated Columns** | In borderless statements, columns with empty cells (e.g. empty withdrawal on deposit rows) can cause clustering drift. | Virtual column boundaries shift or merge adjacent columns. | Anchor column grids strictly to the header row structure; lock column widths globally across the document before populating body cells. |
| **Non-Standard PDF Producers** | Statements generated by diverse engines (OpenPDF, iText 1.3/2.1, Canva, PowerPoint, ReportLab) emit divergent drawing commands (e.g. rect fills vs stroked paths with zero width). | Primitive classifier misidentifies lines as background fills or vice-versa. | Combine vector path interpretation (L0) with raster edge correlation (L1) to verify ink presence before classifying rules. |

---

## 6. Baseline Verification & Summary

- **Baseline Specs Generated**: All 10 corpus PDF documents processed and saved to `tests/baselines/<template_name>.json`.
  1. `AccountStatement_01-Sep-2026_17-Sep-2026.json`
  2. `AccountStatement_01-Sep-2026_27-Sep-2026.json`
  3. `AccountStatement_20-Sep-2026_20-Sep-2026.json`
  4. `bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.json`
  5. `bank-statement-optransactionhistoryux3-pdf11-06-2026-178160404281321470_.json`
  6. `PIPL Company Profile_update.json`
  7. `RAVIN18081966.json`
  8. `shivay orthocare feb 25 to jan 26.json`
  9. `Siddhi_Pathak_Resume.json`
  10. `upload_test.json`
- **Test Integrity**: 78 / 78 tests passing.
- **Codebase State**: Read-only audit completed; no functional source code modifications introduced.

