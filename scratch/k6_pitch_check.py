import sys
sys.path.insert(0, ".")
import pymupdf
import numpy as np
from scipy import stats
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l3_topology.table_grid import TableGridEngine

pdf_path = "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf"

# 1. Pipeline pitch mode for narration column (x 68..255) across all pages
grid_engine = TableGridEngine()
pipeline_pitches = []

with ByteLayerExtractor(pdf_path) as ext:
    # Check pages with transactions (pages 1 to 55)
    for p_num in range(1, 15):  # Sample first 14 pages
        pl = ext.extract_page(p_num)
        narr_chars = [
            c for c in pl.chars
            if 67.8 <= c.origin_device_pt[0] <= 254.8
            and (c.unicode_text or c.char_text).strip()
        ]
        lines = grid_engine.logical_rows.group_into_lines(narr_chars)
        lines.sort(key=lambda l: l.baseline_y_pt, reverse=True)
        for i in range(len(lines) - 1):
            pitch = lines[i].baseline_y_pt - lines[i + 1].baseline_y_pt
            if 8.0 <= pitch <= 35.0:
                pipeline_pitches.append(round(pitch, 2))

pipeline_mode = float(stats.mode(pipeline_pitches, keepdims=False)[0])

# 2. PyMuPDF baseline origins: span["origin"][1]
doc = pymupdf.open(pdf_path)
mupdf_pitches = []

for p_num in range(14):
    page = doc[p_num]
    text_dict = page.get_text("dict")
    span_origins_y = []
    for b in text_dict.get("blocks", []):
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                ox, oy = s["origin"]
                txt = s["text"].strip()
                if txt and 67.8 <= ox <= 254.8:
                    span_origins_y.append(oy)
    
    # Unique baselines sorted top-to-bottom
    baselines = sorted(list(set(round(y, 2) for y in span_origins_y)))
    for i in range(len(baselines) - 1):
        pitch = baselines[i + 1] - baselines[i]
        if 8.0 <= pitch <= 35.0:
            mupdf_pitches.append(round(pitch, 2))

doc.close()

mupdf_mode = float(stats.mode(mupdf_pitches, keepdims=False)[0])
delta = abs(pipeline_mode - mupdf_mode)

print("=" * 80)
print("  K6 LINE PITCH VERIFICATION: PIPELINE vs PyMuPDF span['origin'][1]")
print("=" * 80)
print(f"HDFC Narration Column: x in [67.8, 254.8] pt")
print(f"Pipeline Line Pitch Mode:           {pipeline_mode:.4f} pt (samples={len(pipeline_pitches)})")
print(f"PyMuPDF span['origin'][1] Mode:     {mupdf_mode:.4f} pt (samples={len(mupdf_pitches)})")
print(f"Delta:                              {delta:.4f} pt (tolerance <= 0.01 pt)")
print(f"Check Passed (delta <= 0.01 pt):   {delta <= 0.01}")
print("=" * 80)

