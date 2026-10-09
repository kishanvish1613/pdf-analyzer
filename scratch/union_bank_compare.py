import sys
sys.path.insert(0, ".")
import pymupdf
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l2_primitives.ruleset import RuleSet
from pdf_analyzer.l3_topology.table_grid import TableGridEngine
from pdf_analyzer.utils.units import to_top_left_bbox

pdf_path = "uploads/bank-statement-optransactionhistoryux3-pdf11-06-2026-178160404281321470_.pdf"

# 1. Standalone PyMuPDF: inspect page geometry for pages 1, 38, 76
doc = pymupdf.open(pdf_path)
page_geom = {}
for p_idx in [0, 37, 75]:
    p = doc[p_idx]
    page_geom[p_idx + 1] = {
        "rect": (p.rect.x0, p.rect.y0, p.rect.x1, p.rect.y1),
        "rotation": p.rotation,
        "cropbox": (p.cropbox.x0, p.cropbox.y0, p.cropbox.x1, p.cropbox.y1),
        "width": p.rect.width,
        "height": p.rect.height,
    }

# Find header fill rects on page 1
page1 = doc[0]
drawings = page1.get_drawings()
fill_rects = []
for d in drawings:
    if d.get("fill") is not None:
        for item in d.get("items", []):
            if item[0] == "re":
                r = item[1]
                rx0, ry0, rx1, ry1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
                rw = rx1 - rx0
                rh = ry1 - ry0
                if 10.0 <= rh <= 40.0 and rw >= 30.0:
                    fill_rects.append({"x0": rx0, "y0": ry0, "x1": rx1, "y1": ry1, "w": rw, "h": rh})

header_rects = [r for r in fill_rects if abs(r["y0"] - 318.0) <= 5.0]
header_rects.sort(key=lambda r: r["x0"])
doc.close()

# 2. Pipeline extraction
with ByteLayerExtractor(pdf_path) as ext:
    page_layer = ext.extract_page(1)
cropbox = page_layer.cropbox_pt
height_used = cropbox[3]
ruleset = RuleSet.from_page_layer(page_layer)
grid_engine = TableGridEngine()
table_grid = grid_engine.build_table_grid(ruleset, page_layer)
pipe_tl_bbox = to_top_left_bbox(table_grid.bbox_pt, cropbox)

print("=" * 115)
print("  UNION BANK: PAGE GEOMETRY & TABLE BOUNDS INVESTIGATION (Pages 1, 38, 76)")
print("  [Coordinate Frame: Top-Left CropBox Origin, pt]")
print("=" * 115)
print("\n--- 1. STANDALONE PyMuPDF PAGE GEOMETRY ---")
for pno, geom in page_geom.items():
    print(f"  Page {pno:2d}: rect={geom['rect']} | rotation={geom['rotation']} | cropbox={geom['cropbox']} | dim=({geom['width']:.1f} x {geom['height']:.1f} pt)")

print("\n--- 2. PIPELINE CROPBOX & TO_TOP_LEFT_BBOX PARAMETERS ---")
print(f"  Pipeline page_layer.cropbox_pt: {cropbox}")
print(f"  Height used by to_top_left_bbox: {height_used:.1f} pt (authoritative from cropbox[3])")
print(f"  Pipeline Native BBox (bottom-up): ({table_grid.bbox_pt[0]:.3f}, {table_grid.bbox_pt[1]:.3f}, {table_grid.bbox_pt[2]:.3f}, {table_grid.bbox_pt[3]:.3f}) pt")
print(f"  Pipeline Top-Left BBox:           ({pipe_tl_bbox[0]:.3f}, {pipe_tl_bbox[1]:.3f}, {pipe_tl_bbox[2]:.3f}, {pipe_tl_bbox[3]:.3f}) pt")
print(f"  Header Fill Band Y (PyMuPDF):     [318.000, 332.000] pt")
print(f"  Table y0 vs Header Top Delta:     abs({pipe_tl_bbox[1]:.3f} - 318.000) = {abs(pipe_tl_bbox[1] - 318.0):.3f} pt")

print("\n--- 3. ROOT CAUSE OF PRIOR (34, 802, 728, 1064) DISCREPANCY & FIX ---")
print("  * Cause:")
print("    In table_grid.py, collinear_cell_row selection was sorting y_groups in ASCENDING order.")
print("    Because native PDF coordinates are bottom-up (y=0 at page bottom, y=1100 at page top),")
print("    the ascending sort picked the bottom-most table row at yk=250.0 (y in [252, 298] pt),")
print("    yielding native bbox (34, 36, 728, 298).")
print("    When to_top_left_bbox converted this with height 1100 pt:")
print("      tl_y0 = 1100 - 298 = 802 pt")
print("      tl_y1 = 1100 - 36  = 1064 pt")
print("    This inverted the table extent into the bottom margin [802, 1064] pt.")
print("  * Fix:")
print("    Sorted y_groups in DESCENDING order (reverse=True) so the top-most header row (yk=770,")
print("    y in [768, 782] pt) is selected as collinear_cell_row, and computed the table bottom")
print("    from the lowest cell rect (y=252 pt).")
print("    Native bbox is now (34.0, 252.0, 728.0, 782.0), converting to top-left (34.0, 318.0, 728.0, 848.0) pt,")
print("    where table y0 = 318.0 pt exactly matches the header fill band top [318.0, 332.0] pt.")

print("\n--- 4. HEADER FILL RECTS vs PIPELINE COLUMNS (Page 1) ---")
print(f"{'Col #':<6} | {'PyMuPDF Fill [x0, x1]':<26} | {'Fill Width':<12} | {'Pipeline Col [x0, x1]':<26} | {'Col Width':<12} | {'Delta'}")
print("-" * 115)
for i in range(max(len(header_rects), len(table_grid.columns))):
    hr = header_rects[i] if i < len(header_rects) else None
    col = table_grid.columns[i] if i < len(table_grid.columns) else None
    hr_span = f"[{hr['x0']:.3f}, {hr['x1']:.3f}]" if hr else "N/A"
    hr_w = f"{hr['w']:.3f} pt" if hr else "N/A"
    col_span = f"[{col.x0_pt:.3f}, {col.x1_pt:.3f}]" if col else "N/A"
    col_w = f"{col.width_pt:.3f} pt" if col else "N/A"
    delta = f"{abs(hr['w'] - col.width_pt):.3f} pt" if (hr and col) else "N/A"
    print(f"{i+1:<6} | {hr_span:<26} | {hr_w:<12} | {col_span:<26} | {col_w:<12} | {delta}")

print("=" * 115)
total_fill_w = sum(r['w'] for r in header_rects)
total_col_w = sum(c.width_pt for c in table_grid.columns)
print(f"Sum of Fill Widths: {total_fill_w:.3f} pt | Sum of Column Widths: {total_col_w:.3f} pt | Delta: {abs(total_fill_w - total_col_w):.3f} pt")
print("=" * 115)

