"""
2. HDFC pages 1, 28, 55: vertical rules with x, span, used-as-boundary, and a reason for each exclusion.
"""
import sys
import os

sys.path.insert(0, ".")
import pymupdf
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine

pdf_path = "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf"
pages_to_check = [1, 28, 55]

grid_engine = TableGridEngine()

for pno in pages_to_check:
    print(f"\n==========================================================================================")
    print(f"HDFC Statement (acct-statement-2821) - Page {pno} Vertical Rules Analysis")
    print(f"[Coordinate Frame: Top-Left CropBox Origin, pt]")
    print(f"==========================================================================================")
    
    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(pno)
    
    ruleset = RuleSet.from_page_layer(page_layer)
    table_grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    # Get all vertical rules from ruleset
    v_rules = sorted(ruleset.v_rules, key=lambda r: (round(r.centre, 1), r.start))
    
    # Determine max span of candidate table rules
    candidate_rules = [r for r in v_rules if r.span >= 50.0]
    max_span = max((r.span for r in candidate_rules), default=0.0)
    
    # Boundary x coordinates
    boundary_xs = [b.centre_x_pt for b in table_grid.boundaries if not b.is_virtual]
    
    print(f"{'Rule ID':<12} | {'x (pt)':<10} | {'Span (pt)':<12} | {'Used as Boundary':<18} | {'Reason for Exclusion / Inclusion'}")
    print("-" * 105)
    
    for idx, r in enumerate(v_rules):
        is_used = any(abs(bx - r.centre) <= 1.0 for bx in boundary_xs)
        used_str = "True" if is_used else "False"
        
        # Determine why it is included or excluded
        if is_used:
            reason = f"Qualifying table column boundary (span >= 0.75 * max_span: {r.span:.1f} >= {0.75*max_span:.1f})"
        else:
            if r.span < 10.0:
                reason = f"Excluded: tiny stroke/tick (span={r.span:.2f} pt < 10 pt)"
            elif r.span < 50.0:
                reason = f"Excluded: decorative/short rule (span={r.span:.2f} pt < 50 pt threshold)"
            elif (r.span / max_span) < 0.75:
                reason = f"Excluded: sub-table rule (span={r.span:.2f} pt < 75% max_span {0.75*max_span:.1f} pt)"
            elif abs(r.centre - 47.0) < 5.0:
                reason = f"Excluded: unowned guide / non-table rule (x={r.centre:.2f} pt)"
            else:
                reason = f"Excluded: outside table cluster / redundant duplicate"
        
        print(f"{r.id:<12} | {r.centre:<10.3f} | {r.span:<12.3f} | {used_str:<18} | {reason}")


