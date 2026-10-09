import json

with open("out/fix/before_task_a1.json", "r", encoding="utf-8") as f:
    b = json.load(f)
with open("out/fix/after_task_a1.json", "r", encoding="utf-8") as f:
    a = json.load(f)

print(f"Pytest Before: {b['pytest']}")
print(f"Pytest After:  {a['pytest']}")

b_map = {item["template_name"]: item for item in b["corpus"]}
a_map = {item["template_name"]: item for item in a["corpus"]}

print("\n| Template | SSIM (Before -> After) | Diff % (Before -> After) | Matched Words (Before -> After) | Word dx P95 (Before -> After) | Word dy P95 (Before -> After) |")
print("|---|---|---|---|---|---|")

for name in sorted(b_map.keys()):
    b_item = b_map[name]
    a_item = a_map.get(name, {})
    
    b_ssim = b_item.get("pixel_metrics", {}).get("ssim", 0.0)
    a_ssim = a_item.get("pixel_metrics", {}).get("ssim", 0.0)
    
    b_diff = b_item.get("pixel_metrics", {}).get("diff_percent", 0.0)
    a_diff = a_item.get("pixel_metrics", {}).get("diff_percent", 0.0)
    
    b_words = b_item.get("geometry_metrics", {}).get("matched_words", 0)
    a_words = a_item.get("geometry_metrics", {}).get("matched_words", 0)
    
    b_dx = b_item.get("geometry_metrics", {}).get("dx_pt", {}).get("p95", 0.0)
    a_dx = a_item.get("geometry_metrics", {}).get("dx_pt", {}).get("p95", 0.0)
    
    b_dy = b_item.get("geometry_metrics", {}).get("dy_pt", {}).get("p95", 0.0)
    a_dy = a_item.get("geometry_metrics", {}).get("dy_pt", {}).get("p95", 0.0)
    
    print(f"| {name} | {b_ssim:.3f} -> {a_ssim:.3f} | {b_diff:.2f}% -> {a_diff:.2f}% | {b_words} -> {a_words} | {b_dx:.3f} -> {a_dx:.3f} | {b_dy:.3f} -> {a_dy:.3f} |")

