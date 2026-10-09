import json

with open("tests/corpus/manifest.json", "r", encoding="utf-8") as f:
    manifest = json.load(f)

print(f"{'File':<65} | {'Bank':<22} | {'Producer':<35} | {'Pages':<5} | {'Page Size':<24} | {'Expected Style':<15} | {'Has Table'}")
print("-" * 185)
for entry in manifest:
    file_path = entry.get("file", "")
    bank = entry.get("bank", "None")
    producer = entry.get("producer", "")
    pages = str(entry.get("pages", 0))
    page_size = str(entry.get("page_size", []))
    expected_style = entry.get("expected_table_style", "")
    has_table = str(entry.get("has_table", False))
    print(f"{file_path:<65} | {bank:<22} | {producer:<35} | {pages:<5} | {page_size:<24} | {expected_style:<15} | {has_table}")

