import json
from typing import Dict, Any
from pdf_analyzer.utils.json_sanitizer import sanitize_for_json


def export_design_spec_json(spec_dict: Dict[str, Any], output_path: str) -> None:
    """Save the full structured specification dictionary to JSON."""
    sanitized = sanitize_for_json(spec_dict)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sanitized, f, indent=2, ensure_ascii=False, allow_nan=False)

