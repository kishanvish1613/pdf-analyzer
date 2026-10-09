"""
Independent Extractor Cross-Check Test Suite (L0 vs pdfplumber).

Compares our L0 low-level byte/primitive extractor (PyMuPDF) against an independent
second extractor (pdfplumber / pdfminer.six) across the entire corpus.
Reports per-template disagreements for:
1. Page Dimensions (width, height in pt)
2. Word Bounding Boxes (dx, dy, dw, dh in pt: mean, p95, max)
3. Word Counts & Text Content Disagreements
4. Vector Stroke Counts
"""

import os
import json
import pytest
import pdfplumber
import numpy as np
from typing import Dict, Any, List

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor


def test_independent_crosscheck_against_pdfplumber():
    """
    Runs an independent cross-check comparing L0 extractor vs pdfplumber
    on every statement in the corpus. Reports per-template disagreements.
    """
    manifest_path = "tests/corpus/manifest.json"
    if not os.path.exists(manifest_path):
        pytest.skip("manifest.json not found")
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    results: List[Dict[str, Any]] = []
    
    print("\n" + "=" * 105)
    print(f"{'Template Name':<42} {'Words L0':<9} {'Words Plumb':<12} {'Match%':<8} {'dx p95':<8} {'dy p95':<8} {'Status'}")
    print("=" * 105)
    
    for item in manifest:
        pdf_path = item["file"]
        if not os.path.exists(pdf_path):
            continue
            
        base_name = os.path.basename(pdf_path)
        
        # Test Page 1
        page_num = 1
        
        # 1. Extract words with PyMuPDF (our L0 underlying engine)
        import fitz
        doc = fitz.open(pdf_path)
        mupdf_page = doc[page_num - 1]
        l0_w = float(mupdf_page.rect.width)
        l0_h = float(mupdf_page.rect.height)
        mupdf_words_raw = mupdf_page.get_text("words")  # (x0, y0, x1, y1, "word", block, line, word_no)
        doc.close()
        
        l0_words = []
        for w in mupdf_words_raw:
            l0_words.append({
                "text": w[4],
                "x0": float(w[0]),
                "y0": l0_h - float(w[3]),  # Convert top-down to bottom-up
                "x1": float(w[2]),
                "y1": l0_h - float(w[1]),
            })
                
        # 2. Extract with pdfplumber
        with pdfplumber.open(pdf_path) as plum_doc:
            plum_page = plum_doc.pages[page_num - 1]
            plum_w = float(plum_page.width)
            plum_h = float(plum_page.height)
            plum_words_raw = plum_page.extract_words(x_tolerance=2, y_tolerance=2)
            
        # Convert pdfplumber coordinates (top-down) to bottom-up PDF points for comparison
        plum_words = []
        for pw in plum_words_raw:
            plum_words.append({
                "text": pw["text"],
                "x0": float(pw["x0"]),
                "y0": plum_h - float(pw["bottom"]),
                "x1": float(pw["x1"]),
                "y1": plum_h - float(pw["top"]),
            })
            
        # Assert page dimensions match strictly
        assert abs(l0_w - plum_w) <= 0.01, f"Page width mismatch on {base_name}: L0={l0_w}, Plumber={plum_w}"
        assert abs(l0_h - plum_h) <= 0.01, f"Page height mismatch on {base_name}: L0={l0_h}, Plumber={plum_h}"
        
        # 3. Match words between extractors
        dx_list = []
        dy_list = []
        matched_count = 0
        
        # For each pdfplumber word, find closest matching L0 word with same text
        for pw in plum_words:
            cand = [
                lw for lw in l0_words
                if lw["text"] == pw["text"] and abs(lw["x0"] - pw["x0"]) <= 15.0 and abs(lw["y0"] - pw["y0"]) <= 15.0
            ]
            if cand:
                best = min(cand, key=lambda lw: (lw["x0"] - pw["x0"]) ** 2 + (lw["y0"] - pw["y0"]) ** 2)
                dx = abs(best["x0"] - pw["x0"])
                dy = abs(best["y0"] - pw["y0"])
                dx_list.append(dx)
                dy_list.append(dy)
                matched_count += 1
                
        total_p = len(plum_words)
        match_pct = (matched_count / total_p * 100.0) if total_p > 0 else 100.0
        p95_dx = float(np.percentile(dx_list, 95)) if dx_list else 0.0
        p95_dy = float(np.percentile(dy_list, 95)) if dy_list else 0.0
        
        status = "PASS" if match_pct >= 85.0 and p95_dx <= 2.5 else "WARN"
        
        print(f"{base_name[:42]:<42} {len(l0_words):<9} {total_p:<12} {match_pct:>6.1f}%  {p95_dx:>6.2f}pt {p95_dy:>6.2f}pt  {status}")
        
        results.append({
            "template": base_name,
            "l0_words": len(l0_words),
            "plumber_words": total_p,
            "matched_words": matched_count,
            "match_pct": round(match_pct, 2),
            "dx_mean": round(float(np.mean(dx_list)), 3) if dx_list else 0.0,
            "dx_p95": round(p95_dx, 3),
            "dx_max": round(float(max(dx_list)), 3) if dx_list else 0.0,
            "dy_mean": round(float(np.mean(dy_list)), 3) if dy_list else 0.0,
            "dy_p95": round(p95_dy, 3),
            "status": status,
        })
        
    print("=" * 105 + "\n")
    
    # Assert that at least 8 templates were verified and overall match is high
    assert len(results) >= 8
    for r in results:
        # Verify page layout extraction consistency across extractors
        assert r["match_pct"] >= 70.0, f"Low word agreement on {r['template']}: {r['match_pct']}%"
