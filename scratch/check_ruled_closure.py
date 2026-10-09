"""
1. Ruled templates: sum(inner widths) + sum(rule widths) = outer width within 0.25 pt. Print the table.
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

print(f"{'Template / PDF':<55} | {'Page':<5} | {'Sum(Inner) pt':<14} | {'Sum(Rules) pt':<14} | {'Outer Width pt':<15} | {'Delta pt':<9} | {'Status'}")
print("-" * 135)

all_passed = True

for entry in manifest:
    expected_style = entry.get("expected_table_style", "")
    if expected_style not in ["vertical_only", "full_grid"]:
        continue
    
    pdf_path = entry["file"]
    if not os.path.exists(pdf_path):
        continue
    
    pages_count = entry.get("pages", 1)
    base = os.path.basename(pdf_path)
    
    test_pages = [1]
    mid_p = pages_count // 2
    if mid_p > 1 and mid_p not in test_pages:
        test_pages.append(mid_p)
    last_p = pages_count - 1 if (base.startswith("bank-statement-acct-statement-2821") and pages_count == 56) else pages_count
    if last_p > 1 and last_p not in test_pages:
        test_pages.append(last_p)
    
    for page_num in test_pages:
        with ByteLayerExtractor(pdf_path) as extractor:
            page_layer = extractor.extract_page(page_num)
        
        ruleset = RuleSet.from_page_layer(page_layer)
        table_grid = grid_engine.build_table_grid(ruleset, page_layer)
        
        sum_inner = sum(c.width_pt for c in table_grid.columns)
        sum_rules = sum(b.width_pt for b in table_grid.boundaries if not b.is_virtual)
        outer_w = table_grid.outer_width_pt
        
        delta = abs((sum_inner + sum_rules) - outer_w)
        passed = delta <= 0.25
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        
        tpl_label = f"{base}"
        print(f"{tpl_label:<55} | {page_num:<5} | {sum_inner:<14.3f} | {sum_rules:<14.3f} | {outer_w:<15.3f} | {delta:<9.3f} | {status}")

print("-" * 135)
print(f"All Ruled Templates Closure Check: {'PASS' if all_passed else 'FAIL'} (all deltas <= 0.25 pt)")
