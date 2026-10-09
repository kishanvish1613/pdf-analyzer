"""
Standalone Independent Probe for PDF Ground Truth Extraction.
Uses ONLY PyMuPDF (pymupdf) directly to probe drawing paths, vector rules,
header words, and table extents. Imports NOTHING from pdf_analyzer.
"""

import os
import json
from typing import Dict, Any, List, Optional
import numpy as np
import pymupdf


def extract_independent_ground_truth(pdf_path: str, page_number: int = 1) -> dict:
    doc = pymupdf.open(pdf_path)
    if page_number < 1 or page_number > len(doc):
        doc.close()
        raise ValueError(f"Invalid page number {page_number}")

    page = doc[page_number - 1]
    rect = page.rect
    w, h = rect.width, rect.height

    # 1. Probe Vector Drawings
    drawings = page.get_drawings()
    v_lines = []
    h_lines = []
    fill_rects = []

    for d in drawings:
        for item in d.get("items", []):
            op = item[0]
            if op == "l":
                p1, p2 = item[1], item[2]
                dx = abs(p2.x - p1.x)
                dy = abs(p2.y - p1.y)
                lw = float(d.get("width") or 1.0)
                if dx < 1.0 and dy >= 5.0:
                    v_lines.append({
                        "x": float((p1.x + p2.x) / 2.0),
                        "y0": float(min(p1.y, p2.y)),
                        "y1": float(max(p1.y, p2.y)),
                        "width": lw,
                        "span": float(dy),
                    })
                elif dy < 1.0 and dx >= 5.0:
                    h_lines.append({
                        "y": float((p1.y + p2.y) / 2.0),
                        "x0": float(min(p1.x, p2.x)),
                        "x1": float(max(p1.x, p2.x)),
                        "width": lw,
                        "span": float(dx),
                    })
            elif op == "re":
                r = item[1]
                rx0, ry0, rx1, ry1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
                rw = rx1 - rx0
                rh = ry1 - ry0
                if d.get("fill") is not None:
                    fill_rects.append({"x0": rx0, "y0": ry0, "x1": rx1, "y1": ry1, "w": rw, "h": rh})
                if rw < 3.0 and rh >= 5.0:
                    v_lines.append({
                        "x": (rx0 + rx1) / 2.0,
                        "y0": ry0,
                        "y1": ry1,
                        "width": rw,
                        "span": rh,
                    })
                elif rh < 3.0 and rw >= 5.0:
                    h_lines.append({
                        "y": (ry0 + ry1) / 2.0,
                        "x0": rx0,
                        "x1": rx1,
                        "width": rh,
                        "span": rw,
                    })

    # 2. Probe Words in Page
    words = page.get_text("words")
    doc.close()

    # Determine if page contains a transaction table
    has_grid_v = len(v_lines) >= 2
    has_grid_h = len(h_lines) >= 2
    has_hdr_fill = any(fr["w"] >= 180.0 and 8.0 <= fr["h"] <= 40.0 for fr in fill_rects)
    has_adjacent_rects = False
    # Check if multiple filled rects form a header row
    sorted_fills = sorted([fr for fr in fill_rects if 15.0 <= fr["h"] <= 45.0], key=lambda r: (round(r["y0"], 1), r["x0"]))
    if len(sorted_fills) >= 3:
        # Check collinear fills
        for i in range(len(sorted_fills) - 2):
            if abs(sorted_fills[i]["y0"] - sorted_fills[i+1]["y0"]) < 2.0 and abs(sorted_fills[i+1]["y0"] - sorted_fills[i+2]["y0"]) < 2.0:
                has_adjacent_rects = True
                break

    if not (has_grid_v or (has_grid_h and len(words) > 10) or has_hdr_fill or has_adjacent_rects):
        return {
            "source": "independent_probe_pymupdf",
            "pdf_path": os.path.abspath(pdf_path),
            "page_number": page_number,
            "has_table": False,
            "table_bbox": None,
            "columns": [],
        }

    # Merge collinear vertical segments that touch or connect vertically
    v_lines.sort(key=lambda l: (round(l["x"], 1), l["y0"]))
    continuous_v = []
    for vl in v_lines:
        merged = False
        for cl in continuous_v:
            if abs(cl["x"] - vl["x"]) <= 0.2 and vl["y0"] <= cl["y1"] + 3.0 and vl["y1"] >= cl["y0"] - 3.0:
                cl["x"] = (cl["x"] + vl["x"]) / 2.0
                cl["y0"] = min(cl["y0"], vl["y0"])
                cl["y1"] = max(cl["y1"], vl["y1"])
                cl["width"] = max(cl["width"], vl["width"])
                cl["span"] = cl["y1"] - cl["y0"]
                merged = True
                break
        if not merged:
            continuous_v.append(dict(vl))

    # Cluster continuous vertical lines by Y-interval overlap (>= 40%)
    long_rules = [r for r in continuous_v if r["span"] >= 80.0]
    v_clusters = []
    for r in long_rules:
        matched = False
        for cl in v_clusters:
            y_min = max(cl["y0"], r["y0"])
            y_max = min(cl["y1"], r["y1"])
            overlap = max(0.0, y_max - y_min)
            min_span = min(cl["span"], r["span"])
            if min_span > 0 and (overlap / min_span) >= 0.4:
                cl["rules"].append(r)
                cl["y0"] = min(cl["y0"], r["y0"])
                cl["y1"] = max(cl["y1"], r["y1"])
                cl["span"] = cl["y1"] - cl["y0"]
                matched = True
                break
        if not matched:
            v_clusters.append({"y0": r["y0"], "y1": r["y1"], "span": r["span"], "rules": [r]})

    qual_v_clusters = []
    if v_clusters:
        valid_clusters = []
        for c in v_clusters:
            rules_sorted = sorted(c["rules"], key=lambda r: r["x"])
            x_spread = rules_sorted[-1]["x"] - rules_sorted[0]["x"]
            if len(rules_sorted) >= 3 and x_spread >= 150.0:
                valid_clusters.append((len(rules_sorted), c["span"], c))
        if valid_clusters:
            valid_clusters.sort(key=lambda t: (t[0], t[1]), reverse=True)
            best_cluster = valid_clusters[0][2]
            best_rules = sorted(best_cluster["rules"], key=lambda r: r["x"])
            table_height = max(r["span"] for r in best_rules)
            for idx, r in enumerate(best_rules):
                if r["span"] >= 0.75 * table_height:
                    rule_id = f"rule_v_{idx + 1}"
                    print(f"[independent_probe] Rule {rule_id}: x={r['x']:.3f}, span={r['span']:.3f}")
                    qual_v_clusters.append({
                        "rule_id": rule_id,
                        "centre_x": r["x"],
                        "width": r["width"],
                        "y0": r["y0"],
                        "y1": r["y1"],
                        "span": r["span"],
                    })

    qual_v_clusters.sort(key=lambda b: b["centre_x"])

    columns = []
    if len(qual_v_clusters) >= 2 and qual_v_clusters[-1]["centre_x"] - qual_v_clusters[0]["centre_x"] >= 150.0:
        # Table with explicit vertical rules (J3: only >= 75% spanning rules)
        t_x0 = qual_v_clusters[0]["centre_x"] - qual_v_clusters[0]["width"] / 2.0
        t_x1 = qual_v_clusters[-1]["centre_x"] + qual_v_clusters[-1]["width"] / 2.0
        t_y0 = min(b["y0"] for b in qual_v_clusters)
        t_y1 = max(b["y1"] for b in qual_v_clusters)

        for i in range(len(qual_v_clusters) - 1):
            b0 = qual_v_clusters[i]
            b1 = qual_v_clusters[i + 1]
            cx0 = b0["centre_x"] + b0["width"] / 2.0
            cx1 = b1["centre_x"] - b1["width"] / 2.0
            columns.append({
                "column_index": i + 1,
                "x0_pt": cx0,
                "x1_pt": cx1,
                "width_pt": max(0.0, cx1 - cx0),
            })
    else:
        # Table without vertical rules (Kotak / SBI style)
        # J3: for ruleless tables use header-word x-starts and ink-free gutters.
        # Check if adjacent header filled rectangles define column cells
        hdr_rect_row = []
        if len(sorted_fills) >= 3:
            # Group by y0
            fill_rows = {}
            for fr in sorted_fills:
                y_key = round(fr["y0"] / 5.0) * 5.0
                fill_rows.setdefault(y_key, []).append(fr)
            # Find row with most columns
            best_y = max(fill_rows.keys(), key=lambda k: len(fill_rows[k]))
            if len(fill_rows[best_y]) >= 3:
                hdr_rect_row = sorted(fill_rows[best_y], key=lambda r: r["x0"])

        # Table words in table region
        table_words = [w for w in words if 100.0 <= w[1] <= h - 50.0]
        if not table_words:
            return {
                "source": "independent_probe_pymupdf",
                "pdf_path": os.path.abspath(pdf_path),
                "page_number": page_number,
                "has_table": False,
                "table_bbox": None,
                "columns": [],
            }

        if hdr_rect_row:
            # Filled header cells (Kotak / SBI style)
            t_x0 = hdr_rect_row[0]["x0"]
            t_x1 = hdr_rect_row[-1]["x1"]
            t_y0 = min(r["y0"] for r in hdr_rect_row)
            t_y1 = max(w[3] for w in table_words)
            if h_lines:
                table_h_lines = [l for l in h_lines if l["y"] >= t_y0]
                if table_h_lines:
                    t_y1 = max(t_y1, max(l["y"] for l in table_h_lines))

            # Column splits from header rectangles
            splits = [hdr_rect_row[0]["x0"]] + [r["x1"] for r in hdr_rect_row]
            for i in range(len(splits) - 1):
                cx0 = splits[i]
                cx1 = splits[i + 1]
                columns.append({
                    "column_index": i + 1,
                    "x0_pt": cx0,
                    "x1_pt": cx1,
                    "width_pt": cx1 - cx0,
                })
        else:
            # Whitespace / borderless table: find header row words and ink-free gutters
            table_lines_map = {}
            for w in table_words:
                y_bin = round(w[1] / 3.0) * 3.0
                table_lines_map.setdefault(y_bin, []).append(w)

            # Find header line with keywords
            keywords = ["date", "particulars", "narration", "description", "balance", "withdrawal", "deposit", "chq", "ref", "debit", "credit", "amount", "#"]
            hdr_y = None
            for y_bin, lwords in sorted(table_lines_map.items()):
                txt_joined = " ".join(w[4].lower() for w in lwords)
                matches = sum(1 for kw in keywords if kw in txt_joined)
                if matches >= 4 or (matches >= 2 and any(k in txt_joined for k in ["particulars", "description", "narration", "details"])):
                    hdr_y = y_bin
                    break

            if hdr_y is None:
                return {
                    "source": "independent_probe_pymupdf",
                    "pdf_path": os.path.abspath(pdf_path),
                    "page_number": page_number,
                    "has_table": False,
                    "table_bbox": None,
                    "columns": [],
                }

            hdr_words = sorted(table_lines_map[hdr_y], key=lambda w: w[0])
            body_words = [w for w in table_words if w[1] > hdr_y + 10.0]

            t_x0 = min(w[0] for w in table_words)
            t_x1 = max(w[2] for w in table_words)
            t_y0 = min(w[1] for w in hdr_words)
            t_y1 = max(w[3] for w in table_words)
            if h_lines:
                t_y1 = max(t_y1, max(l["y"] for l in h_lines))

            # Assemble header tokens (grouping words with small gap < 8 pt)
            hdr_tokens = []
            cur_tok = [hdr_words[0]]
            for w in hdr_words[1:]:
                if w[0] - cur_tok[-1][2] < 8.0:
                    cur_tok.append(w)
                else:
                    hdr_tokens.append(cur_tok)
                    cur_tok = [w]
            hdr_tokens.append(cur_tok)

            # Use header-word x-starts and ink-free gutters
            col_splits = [t_x0]
            for i in range(len(hdr_tokens) - 1):
                tok_left_x1 = max(w[2] for w in hdr_tokens[i])
                tok_right_x0 = min(w[0] for w in hdr_tokens[i + 1])
                mid_cut = (tok_left_x1 + tok_right_x0) / 2.0
                # Check body words between
                left_ink = max((w[2] for w in body_words if w[2] <= mid_cut + 15.0), default=tok_left_x1)
                right_ink = min((w[0] for w in body_words if w[0] >= mid_cut - 15.0), default=tok_right_x0)
                if right_ink > left_ink:
                    col_splits.append((left_ink + right_ink) / 2.0)
                else:
                    col_splits.append(mid_cut)
            col_splits.append(t_x1)

            col_splits = sorted(list(set(col_splits)))
            for i in range(len(col_splits) - 1):
                cx0 = col_splits[i]
                cx1 = col_splits[i + 1]
                columns.append({
                    "column_index": i + 1,
                    "x0_pt": cx0,
                    "x1_pt": cx1,
                    "width_pt": cx1 - cx0,
                })

    return {
        "source": "independent_probe_pymupdf",
        "pdf_path": os.path.abspath(pdf_path),
        "page_number": page_number,
        "has_table": True,
        "table_bbox": {
            "x0_pt": t_x0,
            "y0_pt": t_y0,
            "x1_pt": t_x1,
            "y1_pt": t_y1,
            "width_pt": t_x1 - t_x0,
            "height_pt": t_y1 - t_y0,
        },
        "columns": columns,
    }
