"""
PII Detection Engine.
Detects sensitive customer data: names, account numbers, addresses,
phone numbers, emails/UPI IDs, dates, and amounts.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple, Set


@dataclass
class PIIMatch:
    """Individual detected PII match."""
    category: str  # "NAME", "ACCOUNT_NUMBER", "ADDRESS", "PHONE", "EMAIL", "DATE", "AMOUNT"
    original_text: str
    start: int
    end: int
    confidence: float
    context: str = ""
    bbox_pt: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RedactionRecord:
    """Record of a replaced or redacted piece of text."""
    category: str
    original_text: str
    replaced_text: str
    bbox_pt: Optional[List[float]] = None
    width_delta_pt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PIIReport:
    """Complete summary report of detected PII and applied privacy transformations."""
    total_detected: int
    categories: Dict[str, int]
    redactions: List[RedactionRecord]
    privacy_mode: str  # "redacted" | "synthetic" | "real"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_detected": self.total_detected,
            "categories": self.categories,
            "redactions": [r.to_dict() for r in self.redactions],
            "privacy_mode": self.privacy_mode
        }


# Regex patterns for high-precision PII detection
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
UPI_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9]{3,}\b')
PHONE_REGEX = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|\b[6-9]\d{9}\b|\b0\d{2,4}[-.\s]?\d{6,8}\b')
PAN_REGEX = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b')
IFSC_REGEX = re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b')
ACCOUNT_NUM_REGEX = re.compile(r'\b(?:[A-Z]{0,2}\d{8,18}|\d{3,6}[-\s]\d{3,6}[-\s]\d{3,6}|[X\*\.]{4,}\d{3,6})\b')
PIN_ZIP_REGEX = re.compile(r'\b(?:\d{6}|\d{5}(?:-\d{4})?)\b')
DATE_REGEX = re.compile(r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b', re.IGNORECASE)
AMOUNT_REGEX = re.compile(r'(?:[\$₹£€]\s*)?\b\d{1,3}(?:,\d{2,3})+(?:\.\d{2})?\b|\b\d+\.\d{2}\b')

# Structural keywords that signal high-confidence PII
NAME_KEYWORD_PATTERNS = [
    re.compile(r'(?:customer|holder|account\s+holder|name|m\/s|mr\.|mrs\.|ms\.|dr\.)\s*[:\-]?\s*(.+)', re.IGNORECASE),
    re.compile(r'(?:joint\s+holder|nominee)\s*[:\-]?\s*(.+)', re.IGNORECASE),
    re.compile(r'UPI-(?:[A-Z\s]+)-([A-Z\s]+)-', re.IGNORECASE),
    re.compile(r'(?:CASH DEPOSIT BY|TRANSFER TO|TRANSFER FROM|PAID TO)\s*-\s*([A-Za-z\s]+)', re.IGNORECASE),
]

ACCOUNT_KEYWORDS = ["account no", "acct no", "account number", "a/c no", "cif no", "customer id", "cust id", "card no"]
ADDRESS_KEYWORDS = ["address", "street", "road", "plot", "sector", "flat", "building", "nagar", "city", "state", "pincode", "zip"]


class PIIDetector:
    """Comprehensive multi-signal PII detector."""

    def __init__(self):
        pass

    def detect_in_text(self, text: str, field_context: str = "") -> List[PIIMatch]:
        """Detects PII tokens within a given string."""
        if not text or not isinstance(text, str):
            return []

        matches: List[PIIMatch] = []
        ctx_lower = field_context.lower()

        # 1. Check Field Context Clues
        if any(k in ctx_lower for k in ["currency", "curr"]):
            matches.append(PIIMatch(
                category="CURRENCY",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.99,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["ifsc", "rtgs", "neft"]):
            matches.append(PIIMatch(
                category="IFSC",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.99,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["micr"]):
            matches.append(PIIMatch(
                category="MICR",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.99,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["branch code", "branch name", "account branch", "branch"]):
            matches.append(PIIMatch(
                category="BRANCH",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["status", "account status"]):
            matches.append(PIIMatch(
                category="STATUS",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["account type", "acct type", "type"]):
            matches.append(PIIMatch(
                category="ACCOUNT_TYPE",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["nominee"]):
            matches.append(PIIMatch(
                category="NOMINEE",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["date", "dt"]):
            matches.append(PIIMatch(
                category="DATE",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["balance", "bal", "amount", "debit", "credit"]):
            matches.append(PIIMatch(
                category="AMOUNT",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["bank"]):
            matches.append(PIIMatch(
                category="BRANCH",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ADDRESS_KEYWORDS):
            matches.append(PIIMatch(
                category="ADDRESS",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.90,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ACCOUNT_KEYWORDS):
            matches.append(PIIMatch(
                category="ACCOUNT_NUMBER",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        if any(k in ctx_lower for k in ["name", "holder", "customer"]) and not any(k in ctx_lower for k in ["bank", "branch"]):
            matches.append(PIIMatch(
                category="NAME",
                original_text=text.strip(),
                start=0,
                end=len(text),
                confidence=0.95,
                context=field_context
            ))
            return matches

        # 2. IFSC Direct Detection
        for m in IFSC_REGEX.finditer(text):
            matches.append(PIIMatch(
                category="IFSC",
                original_text=m.group(0),
                start=m.start(),
                end=m.end(),
                confidence=0.98,
                context="ifsc_code"
            ))

        # 3. Email Detection
        for m in EMAIL_REGEX.finditer(text):
            matches.append(PIIMatch(
                category="EMAIL",
                original_text=m.group(0),
                start=m.start(),
                end=m.end(),
                confidence=0.98,
                context=field_context
            ))

        # 3. UPI ID Detection (if not already matched as email)
        for m in UPI_REGEX.finditer(text):
            if not any(match.start <= m.start() and m.end() <= match.end for match in matches):
                matches.append(PIIMatch(
                    category="EMAIL",
                    original_text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    confidence=0.95,
                    context="upi_handle"
                ))

        # 4. PAN / IFSC
        for m in PAN_REGEX.finditer(text):
            matches.append(PIIMatch(
                category="ACCOUNT_NUMBER",
                original_text=m.group(0),
                start=m.start(),
                end=m.end(),
                confidence=0.92,
                context="pan_id"
            ))

        # 5. Phone Numbers
        for m in PHONE_REGEX.finditer(text):
            if not any(match.start <= m.start() and m.end() <= match.end for match in matches):
                matches.append(PIIMatch(
                    category="PHONE",
                    original_text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    confidence=0.88,
                    context=field_context
                ))

        # 6. Account Numbers / Transaction IDs
        for m in ACCOUNT_NUM_REGEX.finditer(text):
            val = m.group(0)
            if not any(match.start <= m.start() and m.end() <= match.end for match in matches):
                # Filter out obvious years or short non-account numbers
                if len(re.sub(r'\D', '', val)) >= 6:
                    matches.append(PIIMatch(
                        category="ACCOUNT_NUMBER",
                        original_text=val,
                        start=m.start(),
                        end=m.end(),
                        confidence=0.85,
                        context=field_context
                    ))

        # 7. Name pattern detection in narration or text
        for pat in NAME_KEYWORD_PATTERNS:
            for m in pat.finditer(text):
                g = m.group(1).strip()
                if len(g) > 2 and not any(match.start <= m.start(1) and m.end(1) <= match.end for match in matches):
                    matches.append(PIIMatch(
                        category="NAME",
                        original_text=g,
                        start=m.start(1),
                        end=m.end(1),
                        confidence=0.85,
                        context="name_prefix"
                    ))

        return matches

    def detect_in_spec(self, spec: Dict[str, Any]) -> List[PIIMatch]:
        """Scans an entire specification dictionary and identifies all PII items."""
        all_matches: List[PIIMatch] = []

        # 1. Scan Account Details
        acct = spec.get("account_details", {})
        if isinstance(acct, dict):
            # Fields
            for field_item in acct.get("fields", []):
                if isinstance(field_item, dict):
                    k = field_item.get("key", "")
                    v = field_item.get("value", "")
                    if v:
                        m = self.detect_in_text(v, field_context=k)
                        all_matches.extend(m)

            # Address Box
            addr_box = acct.get("address_box", {})
            if isinstance(addr_box, dict):
                lines = addr_box.get("lines", [])
                for i, line in enumerate(lines):
                    ctx = "customer_name" if i == 0 else "customer_address"
                    m = self.detect_in_text(line, field_context=ctx)
                    all_matches.extend(m)

            # Colon Grid
            grid = acct.get("colon_grid", {})
            if isinstance(grid, dict):
                for row in grid.get("rows", []):
                    if isinstance(row, dict):
                        k = row.get("key", "")
                        v = row.get("value", "")
                        if v:
                            m = self.detect_in_text(v, field_context=k)
                            all_matches.extend(m)

        # 2. Scan Key Values
        kv_data = spec.get("key_values", {})
        kv_list = kv_data.get("entities", []) if isinstance(kv_data, dict) else (kv_data if isinstance(kv_data, list) else [])
        for kv in kv_list:
            if isinstance(kv, dict):
                k = kv.get("key", "")
                v = kv.get("value", "")
                if v:
                    m = self.detect_in_text(v, field_context=k)
                    all_matches.extend(m)

        # 3. Scan Header Blocks
        hb_data = spec.get("header_blocks", {})
        hb_list = hb_data.get("blocks", []) if isinstance(hb_data, dict) else (hb_data if isinstance(hb_data, list) else [])
        for hb in hb_list:
            if isinstance(hb, dict):
                for line in hb.get("lines", hb.get("text_lines", [])):
                    m = self.detect_in_text(line, field_context=hb.get("type", "header"))
                    all_matches.extend(m)

        # 4. Scan Table Rows & Cells
        tbl = spec.get("table_model") or spec.get("table") or {}
        rows = tbl.get("rows", [])
        for r in rows:
            if isinstance(r, dict):
                cells = r.get("cells", [])
                for c in cells:
                    c_text = c.get("text", "") if isinstance(c, dict) else str(c)
                    if c_text:
                        m = self.detect_in_text(c_text, field_context="table_cell")
                        all_matches.extend(m)
                raw_text = r.get("raw_text") or r.get("text_summary") or ""
                if raw_text:
                    m = self.detect_in_text(raw_text, field_context="table_row")
                    all_matches.extend(m)

        # 5. Scan Footer Blocks
        fb_data = spec.get("footer_blocks", {})
        fb_list = fb_data.get("sub_blocks", []) if isinstance(fb_data, dict) else (fb_data if isinstance(fb_data, list) else [])
        for fb in fb_list:
            if isinstance(fb, dict):
                f_text = fb.get("text", "")
                if f_text:
                    m = self.detect_in_text(f_text, field_context="footer")
                    all_matches.extend(m)

        return all_matches
