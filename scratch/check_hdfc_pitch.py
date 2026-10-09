"""
4. HDFC narration column x 68..255: pitch mode from the pipeline == PyMuPDF span["origin"][1] mode within 0.01 pt (expect 17.2).
"""
import sys
import os
from collections import Counter
import numpy as np

sys.path.insert(0, ".")
import pymupdf
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor

pdf_path = "uploads/bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.pdf"

# 1. PyMuPDF baselines in narration column x: 68..255 across all pages
doc = pymupdf.open(pdf_path)
mupdf_pitches = []

for page_idx in range(len(doc)):
    page = doc[page_idx]
    text_page = page.get_text("dict")
    baselines = []
    for block in text_page.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                origin_x = span["origin"][0]
                origin_y = span["origin"][1]
                # Filter to narration column x in [68, 255] and body y in [100, page.rect.height - 80]
                if 68.0 <= origin_x <= 255.0 and 100.0 <= origin_y <= page.rect.height - 80.0:
                    baselines.append(round(origin_y, 3))
    
    # Sort distinct baselines descending (or ascending)
    unique_b = sorted(list(set(baselines)))
    for i in range(len(unique_b) - 1):
        delta_y = abs(unique_b[i+1] - unique_b[i])
        if 8.0 <= delta_y <= 30.0:
            mupdf_pitches.append(round(delta_y, 1))

doc.close()

# 2. Pipeline content-stream Tm/Td operands / ByteLayerExtractor chars
pipeline_pitches = []
with ByteLayerExtractor(pdf_path) as extractor:
    for pno in range(1, len(extractor.pdf.pages) + 1):
        pl = extractor.extract_page(pno)
        chars = [
            c for c in pl.chars
            if 68.0 <= c.origin_device_pt[0] <= 255.0
            and 100.0 <= (pl.height_pt - c.origin_device_pt[1]) <= pl.height_pt - 80.0
        ]
        baselines = sorted(list(set(round(pl.height_pt - c.origin_device_pt[1], 3) for c in chars)))
        for i in range(len(baselines) - 1):
            delta_y = abs(baselines[i+1] - baselines[i])
            if 8.0 <= delta_y <= 30.0:
                pipeline_pitches.append(round(delta_y, 1))

mupdf_counter = Counter(mupdf_pitches)
pipeline_counter = Counter(pipeline_pitches)

mupdf_mode = mupdf_counter.most_common(1)[0][0]
pipeline_mode = pipeline_counter.most_common(1)[0][0]

delta_mode = abs(pipeline_mode - mupdf_mode)
passed = delta_mode <= 0.01

print(f"==========================================================================================")
print(f"HDFC Narration Column (x in [68..255] pt) Line Pitch Analysis Across All 56 Pages")
print(f"==========================================================================================")
print(f"Pipeline Pitch Mode (from ByteLayerExtractor/Content-Stream): {pipeline_mode:.2f} pt (count={pipeline_counter[pipeline_mode]})")
print(f"PyMuPDF Pitch Mode  (from span['origin'][1] Baselines)     : {mupdf_mode:.2f} pt (count={mupdf_counter[mupdf_mode]})")
print(f"Delta Mode                                                 : {delta_mode:.4f} pt")
print(f"Expected Target                                            : 17.20 pt")
print(f"Status                                                     : {'PASS' if passed and abs(pipeline_mode - 17.2) < 0.05 else 'FAIL'}")
print(f"==========================================================================================")
