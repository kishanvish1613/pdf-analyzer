"""Probe AccountStatement_20-Sep fill rects to understand 523.000->522.990 TableBBox change."""
import pymupdf

doc = pymupdf.open('uploads/AccountStatement_20-Sep-2026_20-Sep-2026.pdf')
page = doc[0]
drawings = page.get_drawings()
fill_rects = []
for d in drawings:
    for item in d.get("items", []):
        if item[0] == "re":
            r = item[1]
            rx0, ry0, rx1, ry1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
            rw = rx1 - rx0
            rh = ry1 - ry0
            if d.get("fill") is not None:
                fill_rects.append({"x0": rx0, "y0": ry0, "x1": rx1, "y1": ry1, "w": rw, "h": rh})

sorted_fills = sorted([fr for fr in fill_rects if 15.0 <= fr["h"] <= 45.0],
                      key=lambda r: (round(r["y0"], 1), r["x0"]))
fill_rows = {}
for fr in sorted_fills:
    y_key = round(fr["y0"] / 5.0) * 5.0
    fill_rows.setdefault(y_key, []).append(fr)
best_y = max(fill_rows.keys(), key=lambda k: len(fill_rows[k]))
hdr = sorted(fill_rows[best_y], key=lambda r: r["x0"])
print(f"header y_key={best_y}, rects={len(hdr)}")
for r in hdr:
    print(f"  x0={r['x0']:.6f}  x1={r['x1']:.6f}  w={r['w']:.6f}")
t_x0 = hdr[0]["x0"]
t_x1 = hdr[-1]["x1"]
width = t_x1 - t_x0
print(f"probe t_x0={t_x0:.6f}  t_x1={t_x1:.6f}  width={width:.6f}")

# Also run get_text words to find rightmost ink in page
words = page.get_text("words")
if words:
    max_x1 = max(float(w[2]) for w in words)
    print(f"max word x1 from words = {max_x1:.6f}")

doc.close()

