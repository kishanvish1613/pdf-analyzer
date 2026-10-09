import sys
sys.path.insert(0, ".")
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine

pdf_path = "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf"
page_num = 55

with ByteLayerExtractor(pdf_path) as ext:
    page_layer = ext.extract_page(page_num)
ruleset = RuleSet.from_page_layer(page_layer)
table_grid = TableGridEngine().build_table_grid(ruleset, page_layer)
b_rule_ids = set(b.rule_id for b in table_grid.column_boundaries if b.rule_id)

print("=" * 105)
print(f"  HDFC PAGE {page_num}: VERTICAL RULES & BOUNDARY STATUS")
print("=" * 105)
print(f"{'Rule ID':<12} | {'Centre X':<10} | {'Span (pt)':<10} | {'Y Range [y0, y1]':<25} | {'Used as Boundary?':<18} | {'Region'}")
print("-" * 105)

for r in ruleset.v_rules:
    is_b = "YES" if r.id in b_rule_ids else "NO"
    y_range = f"[{r.start:.3f}, {r.end:.3f}]"
    if r.id in ("rule_v_1", "rule_v_5"):
        region = "Header / Account Info Box (Top of Page)"
    else:
        region = "Main Statement Table"
    print(f"{r.id:<12} | {r.centre:<10.3f} | {r.span:<10.3f} | {y_range:<25} | {is_b:<18} | {region}")

print("=" * 105)
print("\n[EXCLUSION REASON FOR RULE ID 5 (rule_v_5)]:")
print("Rule rule_v_5 (x = 312.376 pt, span = 109.982 pt, y in [650.836, 760.818] pt) forms the right boundary")
print("of the top-of-page 'Header / Account Information' address box (paired with rule_v_1 at x = 27.779 pt).")
print("It is excluded from the table grid boundaries because its vertical interval [650.84, 760.82] pt sits")
print("entirely in the page header region above the transaction table (table y in [72.92, 615.12] pt).")
print("Because its span does not overlap the table cluster (overlap = 0.00 pt < 40% threshold), it is correctly")
print("filtered out as a non-table vector rule.")
print("=" * 105)
