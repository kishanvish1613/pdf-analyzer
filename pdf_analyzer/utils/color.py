"""Color processing utilities for PDF Design Analyzer."""

from typing import Tuple, Union


def int_or_float_to_rgb(color_val: Union[int, Tuple, list, float, None]) -> Tuple[int, int, int]:
    """Convert various PyMuPDF color representations (integer sRGB, float tuples, etc.) to (R, G, B) [0-255]."""
    if color_val is None:
        return (0, 0, 0)

    if isinstance(color_val, int):
        r = (color_val >> 16) & 0xFF
        g = (color_val >> 8) & 0xFF
        b = color_val & 0xFF
        return (r, g, b)

    if isinstance(color_val, (tuple, list)):
        if len(color_val) == 0:
            return (0, 0, 0)
        if len(color_val) == 1:
            # Grayscale float 0.0 - 1.0 or 0 - 255
            v = color_val[0]
            iv = int(v * 255) if isinstance(v, float) and v <= 1.0 else int(v)
            iv = max(0, min(255, iv))
            return (iv, iv, iv)
        if len(color_val) >= 3:
            # RGB floats (0.0-1.0) or ints (0-255)
            r, g, b = color_val[0], color_val[1], color_val[2]
            ir = int(r * 255) if isinstance(r, float) and r <= 1.0 else int(r)
            ig = int(g * 255) if isinstance(g, float) and g <= 1.0 else int(g)
            ib = int(b * 255) if isinstance(b, float) and b <= 1.0 else int(b)
            return (max(0, min(255, ir)), max(0, min(255, ig)), max(0, min(255, ib)))

    return (0, 0, 0)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert (R, G, B) tuple to '#RRGGBB' uppercase hex string."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert '#RRGGBB' or 'RRGGBB' hex string to (R, G, B)."""
    clean = hex_str.lstrip("#")
    if len(clean) == 3:
        clean = "".join([c * 2 for c in clean])
    if len(clean) != 6:
        return (0, 0, 0)
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def calculate_luminance(rgb: Tuple[int, int, int]) -> float:
    """Calculate relative luminance (0.0 = darkest black, 1.0 = brightest white)."""
    return 0.299 * (rgb[0] / 255.0) + 0.587 * (rgb[1] / 255.0) + 0.114 * (rgb[2] / 255.0)


def is_near_white(rgb: Tuple[int, int, int], threshold: int = 245) -> bool:
    """Check if color is nearly white."""
    return rgb[0] >= threshold and rgb[1] >= threshold and rgb[2] >= threshold


def is_near_black(rgb: Tuple[int, int, int], threshold: int = 35) -> bool:
    """Check if color is nearly black."""
    return rgb[0] <= threshold and rgb[1] <= threshold and rgb[2] <= threshold
