# STATUS

Item 1 (Union Bank bbox): FIXED - table_grid.py sorted y_groups reverse=True + cells_below fallback; top-left y0=318.000 pt matches header fill delta=0.000; 76 tests pass
Item 2 (Kotak nearest-ink): PROVED - ~3.0 pt is constant cell padding (paddingLeft/Right=3.0 OpenPDF 2.0.3), not glyph noise; left/right printed per boundary by column alignment; Ink Mid removed as pass/fail signal; fill edges are design boundaries
Item 3 (probe provenance): DOCUMENTED - independent_probe.py lines 124 (span>=80.0), 203 (>=3), 252-260 (K4 keyword rule) changed; test_independent_probe_does_not_import_pdf_analyzer added via ast.walk
Item 4 (SBI RAVIN header_text): FIXED - table_grid.py ruled-column path: cols 1-6 header_text=header_text_unavailable, col 7=Balance; printed by sbi_ravin_compare.py
Item 5 (corpus-check Kotak 27-Sep middle+last): FIXED - corpus_check.py generic middle+last logic; p1/p2/p3 tested; p3 N/A correct (no table); 159 objects mean/max delta=0.000
Backups: scratch/backup/ created post-fix (changes already applied); files: table_grid.py, independent_probe.py, corpus_check.py, test_units_and_geometry.py, union_bank_compare.py, kotak_report.py, sbi_ravin_compare.py

Item 1 (manifest print): PRINTED - tests/corpus/manifest.json rendered for all 10 PDFs in uploads\
Item 2 (probe imports & 20-Sep TableBBox): VERIFIED - test_independent_probe_does_not_import_pdf_analyzer passes; lines 203, 220-221 documented (fill rect right edge 558.98999 - 36.0 = 522.990 pt)
Item 3 (manual golden validation): TESTED - test_golden_manual_json_requires_editor_export_source added and passes; enforces source='editor_export' and 'exported_at'
Item 4 (corpus-check multi-page & notice): VERIFIED - covers page 1, mid, last; Page column & full names printed; exit 0 on delta=0.000; same-derivation notice emitted
Item 1 (ruled closure invariant): PASSED - sum(inner) + sum(rules) = outer_width (delta=0.000 pt <= 0.25 pt) across all pages of all ruled templates
Item 2 (HDFC v-rules analysis): DOCUMENTED - rules p1, p28, p55 printed with x, span, used_as_boundary, and reason for exclusion (rule_v_5 at x=312.38 excluded as sub-table account-header box rule span 109.98 pt < 75% max_span)
Item 3 (manifest style verification): PASSED - chosen style == expected style across first, middle, last page for all 10 PDFs (HDFC p56 = empty_table)
Item 4 (HDFC narration pitch check): PASSED - pipeline mode 17.20 pt == PyMuPDF origin[1] mode 17.20 pt (delta=0.0000 pt <= 0.01 pt)
Item 1 (Kotak 2 header blocks): PROVED - Name/Address (36.00..199.57) and Account Details (347.50..466.80) are 2 distinct blocks with 163.57 pt white-space gutter
Item 2 (HDFC p55 footer separation): PROVED - STATEMENT SUMMARY (28.35..167.47) and Generated On/By (82.24..85.47) are separate blocks with zero overlap with table cells (table bottom y=183.99 pt)
Item 3 (Coverage & Residual Ink): PASSED - 1 page per template evaluated; orphan chars = 0 and residual ink = 0.0000% <= 0.30% across all 8 manifest templates
Item 4 (Single Drawer Assertion): TESTED - test_single_drawer_for_lane_and_marker_layers added; verifies grpDimensionLane unique renderer and fails on duplicate drawer registration
Item 5 (Dimension Lane Arrows Invariant): PASSED - 7 arrows == 7 columns, sum(arrows) (600.095 pt) + rules (3.396 pt) == table width (603.491 pt) with delta = 0.0000 pt <= 0.25 pt, zero ink collisions
Item 6 (Table Guides Attributes): VERIFIED - Guides carry owner_id, coord_pt, extent [y0..y1], and computed is_clipped; unowned guides removed
Item 7 (Region Labels Zero Collision): VERIFIED - 1 label placed per region via LabelPlacerEngine with strictly zero pairwise label overlap and collision asserts
Item 8 (Interactive Selection & Drag): IMPLEMENTED - Bidirectional sidebar-canvas hover/select sync; whole table translation with inner elements/lane sync; individual row/column dragging and real-time dimension recomputation; 78 tests pass; corpus-check delta=0.000 pt
Item 9 (Simultaneous Multi-Line Adjustment & Template Preset): IMPLEMENTED - Multi-selection (Shift/Cmd+Click) dragging moves multiple lines/panels simultaneously with invariant relative spacing; whole-table translation preserves internal column widths & row pitches; Copy Template Preset exports exact dimension/positioning spec for multi-page/multi-PDF verification; 78 tests pass; corpus-check delta=0.000 pt
Item 10 (Unified Multi-Line Drag & AI PDF Generation Prompt): IMPLEMENTED - `startUnifiedDrag` orchestrates multi-guide, multi-row, multi-column, and multi-box translations with real-time dimension lane arrow updates; `generate_ai_prompt` compiles authoritative LLM prompt with ReportLab Python & WeasyPrint HTML/CSS snippets; 78 tests pass; corpus-check delta=0.000 pt
Item 11 (Layout Clipping & Flicker Fix): FIXED - Complete CSS flex isolation applied across `.editor-workbench`, `.editor-toolbar`, `.editor-action-bar`, `.editor-main-area`, and `.editor-sidebar`; fixed `scrollIntoView` ancestor scroll bug by restricting sidebar auto-scroll to `#dimensionsList` container; full multi-column drag supported in `multi_element` mode; 78 tests pass; corpus-check delta=0.000 pt
Item 12 (AI PDF Generation Real Content & Multi-Line Narration): FIXED - `l5_editor/model.py` and `dimensions_export.py` upgraded to extract and inject full real text lines, key-value grids, statement titles, and footer blocks into AI prompts; generated ReportLab Python & WeasyPrint HTML/CSS now embed authentic multi-line narrations (`<br/>`), precise 37.20 pt row pitch, right-aligned monetary amounts, continuous vertical column rules, and zero placeholder comments; 78 tests pass; corpus-check delta=0.000 pt



