"""
3. Orphan chars = 0 and residual ink <= 0.3% on one page per template.
"""
import os
import sys
import json

sys.path.insert(0, ".")
from pdf_analyzer.l1_crosscheck.audit import run_l1_audit

with open("tests/corpus/manifest.json", "r", encoding="utf-8") as f:
    manifest = json.load(f)

print("=" * 125)
print("  CONTENT ACCOUNTING & RESIDUAL INK AUDIT (1 PAGE PER TEMPLATE)")
print("=" * 125)
print(f"{'PDF / Template':<48} | {'Page':<5} | {'Total Chars':<12} | {'Orphans':<8} | {'Residual Ink %':<15} | {'Status'}")
print("-" * 125)

all_passed = True

for entry in manifest:
    if not entry.get("has_table", False):
        continue
    pdf_path = entry["file"]
    if not os.path.exists(pdf_path):
        continue
    
    base = os.path.basename(pdf_path)
    
    success, audit_dict = run_l1_audit(pdf_path, page_number=1, strict=False, output_dir="scratch/audit_temp")
    
    acct = audit_dict["accounting_report"]
    total_chars = acct["total_chars"]
    orphans = acct["orphan_chars_count"]
    res_ink = acct["residual_ink_pct"]
    
    orphan_ok = orphans == 0
    ink_ok = res_ink <= 0.30
    passed = orphan_ok and ink_ok
    if not passed:
        all_passed = False
    
    status_str = "PASS" if passed else "FAIL"
    print(f"{base:<48} | {1:<5} | {total_chars:<12} | {orphans:<8} | {res_ink:<15.4f}% | {status_str}")

print("-" * 125)
print(f"Overall Coverage & Content Accounting Result: {'PASS' if all_passed else 'FAIL'}")
print("=" * 125)

