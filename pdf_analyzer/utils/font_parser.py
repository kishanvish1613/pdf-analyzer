"""Font name parsing and typographic style inference."""

import re
from typing import Tuple


SUBSET_PREFIX_REGEX = re.compile(r"^[A-Z]{6}\+(.+)$")


def clean_font_name(font_name: str) -> str:
    """Strip 6-character random subset prefix (e.g. 'BAAAAA+ArialMT' -> 'ArialMT')."""
    if not font_name:
        return "UnknownFont"
    match = SUBSET_PREFIX_REGEX.match(font_name)
    if match:
        return match.group(1)
    return font_name


def parse_font_properties(font_name: str, flags: int = 0) -> Tuple[str, str, bool, bool, bool, bool, str]:
    """Parse font name and flags into cleaned name, family, bold, italic, mono, serif, weight.

    Returns:
        (clean_name, family, is_bold, is_italic, is_mono, is_serif, weight)
    """
    clean_name = clean_font_name(font_name)
    lower_name = clean_name.lower()

    # PyMuPDF flags: bit 0: italic, bit 1: serif, bit 2: fixed-pitch (mono), bit 4: bold
    flag_italic = bool(flags & 2 ** 0)
    flag_serif = bool(flags & 2 ** 1)
    flag_mono = bool(flags & 2 ** 2)
    flag_bold = bool(flags & 2 ** 4)

    is_bold = flag_bold or any(w in lower_name for w in ["bold", "black", "heavy", "demi", "semibold", "b"])
    is_italic = flag_italic or any(w in lower_name for w in ["italic", "oblique", "it", "slant"])
    is_mono = flag_mono or any(w in lower_name for w in ["mono", "courier", "consolas", "menlo", "typewriter"])
    is_serif = flag_serif or any(w in lower_name for w in ["times", "roman", "georgia", "garamond", "serif", "cambria", "minion"])

    # Inferred weight
    if any(w in lower_name for w in ["black", "heavy", "extrabold", "ultra"]):
        weight = "black"
    elif any(w in lower_name for w in ["bold", "b"]):
        weight = "bold"
    elif any(w in lower_name for w in ["semibold", "demi", "demibold"]):
        weight = "semibold"
    elif any(w in lower_name for w in ["medium", "med"]):
        weight = "medium"
    elif any(w in lower_name for w in ["light", "thin", "hairline"]):
        weight = "light"
    else:
        weight = "bold" if flag_bold else "regular"

    # Inferred base family name
    family_candidate = re.split(r"[-_, ]", clean_name)[0]
    # Strip standard MT/PS suffixes
    family = re.sub(r"(MT|PS|BT|LT|OTF|TTF)$", "", family_candidate, flags=re.IGNORECASE)
    if not family:
        family = clean_name

    return clean_name, family, is_bold, is_italic, is_mono, is_serif, weight
