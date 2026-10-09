import math
from typing import Any

def sanitize_for_json(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (bool, str, int)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    # Handle numpy types if present
    type_name = type(obj).__name__
    module_name = type(obj).__module__
    if "numpy" in module_name:
        if hasattr(obj, "tolist"):
            return sanitize_for_json(obj.tolist())
        if hasattr(obj, "item"):
            return sanitize_for_json(obj.item())
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(x) for x in obj]
    if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
        return sanitize_for_json(obj.to_dict())
    if hasattr(obj, '__dict__'):
        return sanitize_for_json(obj.__dict__)
    return str(obj)
