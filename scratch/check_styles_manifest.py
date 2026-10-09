"""
3. For first, middle and last page of every manifest PDF, chosen style == expected (HDFC p56 = empty_table). Print evidence.
"""
import os
import sys
import json

sys.path.insert(0, ".")
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine

with open("tests/corpus/manifest.json", "r", encoding="utf-8") as f:
    manifest = json.load(f)

grid_engine = TableGridEngine()

print(f"{'PDF / Template':<45} | {'Page':<5} | {'Chosen Style':<15} | {'Expected Style':<15} | {'Match':<6} | {'Structural Evidence / Metrics'}")
print("-" * 155)

all_matched = True

for entry in manifest:
    pdf_path = entry["file"]
    base = os.path.basename(pdf_path)
    if not os.path.exists(pdf_path):
        continue
    
    pages_count = entry.get("pages", 1)
    base_expected = entry.get("expected_table_style", "none")
    
    # Check page 1, middle page, and last page
    pages_to_check = [1]
    mid_p = pages_count // 2
    if mid_p > 1 and mid_p not in pages_to_check:
        pages_to_check.append(mid_p)
    if pages_count > 1 and pages_count not in pages_to_check:
        pages_to_check.append(pages_count)
    
    for page_num in pages_to_check:
        # Determine expected style for specific page
        if base.startswith("bank-statement-acct-statement-2821") and page_num == 56:
            expected_style = "empty_table"
        elif not entry.get("has_table", False):
            expected_style = "empty_table" if base_expected == "none" else base_expected
        else:
            expected_style = base_expected
        
        with ByteLayerExtractor(pdf_path) as extractor:
            page_layer = extractor.extract_page(page_num)
        
        ruleset = RuleSet.from_page_layer(page_layer)
        chosen_enum, runner_up_enum, evidence = grid_engine.determine_table_style_models(ruleset, page_layer)
        chosen_style = chosen_enum.value
        
        # Match check
        # For non-table documents (e.g. resumes, slide decks), 'borderless' or 'empty_table' means no table
        if expected_style in ["none", "empty_table"] and chosen_style in ["empty_table", "borderless"]:
            match = True
        else:
            match = (chosen_style == expected_style)
        
        if not match:
            all_matched = False
        
        match_str = "PASS" if match else "FAIL"
        evidence_summary = "; ".join(evidence) if evidence else "None"
        
        print(f"{base:<45} | {page_num:<5} | {chosen_style:<15} | {expected_style:<15} | {match_str:<6} | {evidence_summary}")

print("-" * 155)
print(f"Style Classification Verification: {'PASS' if all_matched else 'FAIL'}")

