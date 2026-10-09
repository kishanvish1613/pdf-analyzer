import sys
import os
from pathlib import Path

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine
from pdf_analyzer.l4_layout.header import HeaderEngine
from pdf_analyzer.l4_layout.footer import FooterEngine
from pdf_analyzer.l5_editor.model import EditorModelBuilder

def print_page_guides(pdf_path: str, page_num: int, label: str):
    print(f"\n=======================================================")
    print(f"  {label} (Page {page_num})")
    print(f"  File: {Path(pdf_path).name}")
    print(f"=======================================================")
    
    with ByteLayerExtractor(pdf_path) as extractor:
        page_layer = extractor.extract_page(page_number=page_num)
        
    ruleset = RuleSet.from_page_layer(page_layer)
    
    grid_engine = TableGridEngine()
    table_grid = grid_engine.build_table_grid(ruleset, page_layer)
    
    header_engine = HeaderEngine()
    header_model = header_engine.build_header_model(page_layer, table_grid.table_bbox_pt[3])
    
    footer_engine = FooterEngine()
    footer_model = footer_engine.build_footer_model(page_layer, table_grid.table_bbox_pt[1])
    
    builder = EditorModelBuilder(dpi=300)
    # Candidate guides can include text alignments
    model = builder.build_editor_model(
        page_layer=page_layer,
        ruleset=ruleset,
        table_grid=table_grid,
        header_model=header_model,
        footer_model=footer_model,
        containers=[],
        candidate_guides=[
            {"id": "cand_x_47.78", "axis": "X", "position_pt": 47.78, "start_pt": 200.0, "end_pt": 600.0}
        ]
    )
    
    print(f"Table BBox: {model.table_bbox}")
    print(f"Table Guides (total guides: {len(model.guides)}):")
    print(f"{'ID':<22} {'Axis':<5} {'Type':<18} {'Coord (pt)':<12} {'Extent (start..end)':<24} {'Owner':<16} {'Clipped':<8} {'Nearest Rule Dist':<18}")
    print("-" * 125)
    for g in model.guides:
        if g.owner_id == "target_table":
            print(f"{g.id:<22} {g.axis:<5} {g.guide_type:<18} {g.coord_pt:<12.3f} {g.start_pt:6.2f}..{g.end_pt:6.2f} pt   {g.owner_id:<16} {str(g.is_clipped):<8} {g.distance_to_nearest_rule_pt:<18.3f}")
            
    print(f"\nUnowned Guides ({len(model.unowned_guides)}):")
    for ug in model.unowned_guides:
        print(f"  * Guide ID: {ug.guide_id:<15} Axis: {ug.axis:<2} Coord: {ug.coord_pt:<8.2f} Nearest Rule Dist: {ug.distance_to_nearest_rule_pt:<6.2f} Reason: {ug.reason}")

def main():
    corpus_dir = Path("uploads")
    
    # 1. HDFC page 55
    hdfc_path = corpus_dir / "bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf"
    print_page_guides(str(hdfc_path), 55, "HDFC Statement Page 55")
    
    # 2. Kotak page 1
    kotak_path = corpus_dir / "AccountStatement_01-Sep-2026_17-Sep-2026.pdf"
    print_page_guides(str(kotak_path), 1, "Kotak Statement Page 1")

if __name__ == "__main__":
    main()
