import os
import sys
sys.path.insert(0, os.path.abspath("."))
import json
import subprocess
from tools.roundtrip.roundtrip import run_all_roundtrips

def main():
    print("=== Running pytest ===")
    res = subprocess.run([sys.executable, "-m", "pytest", "tests/"], capture_output=True, text=True)
    out = res.stdout + res.stderr
    print(out[-500:] if len(out) > 500 else out)
    
    # Parse pytest results
    collected = 0
    passed = 0
    failed = 0
    for line in out.splitlines():
        if "collected" in line and "items" in line:
            try:
                collected = int(line.split("collected")[1].split("items")[0].strip())
            except Exception:
                pass
        if "passed" in line:
            import re
            m_pass = re.search(r"(\d+) passed", line)
            if m_pass:
                passed = int(m_pass.group(1))
            m_fail = re.search(r"(\d+) failed", line)
            if m_fail:
                failed = int(m_fail.group(1))

    print(f"Pytest summary: collected={collected}, passed={passed}, failed={failed}")

    print("=== Running Roundtrip Harness ===")
    output_dir = "out/fix/after_roundtrip"
    os.makedirs(output_dir, exist_ok=True)
    corpus_results, heldout_results = run_all_roundtrips(
        exporters=["reportlab"],
        output_dir=output_dir,
    )

    corpus_data = [r.to_dict() for r in corpus_results]
    after_data = {
        "pytest": {
            "collected": collected,
            "passed": passed,
            "failed": failed,
        },
        "corpus": corpus_data,
    }

    os.makedirs("out/fix", exist_ok=True)
    with open("out/fix/after_task_a1.json", "w", encoding="utf-8") as f:
        json.dump(after_data, f, indent=2)
    print("Saved out/fix/after_task_a1.json successfully.")

if __name__ == "__main__":
    main()
