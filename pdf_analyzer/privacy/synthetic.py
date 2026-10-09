"""
Synthetic Data Engine.
Substitutes realistic fake names, account numbers, dates, amounts, addresses,
phones, and emails while preserving string width within tolerance.
"""

from __future__ import annotations
import re
import random
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from pdf_analyzer.privacy.redactor import get_string_width_pt
from pdf_analyzer.l0_bytes.font_manager import calculate_string_width_parity

# Synthetic Name Pools categorized by length
SYNTHETIC_NAMES = [
    "Alex Doe",
    "John Smith",
    "Sam Taylor",
    "Chris Jordan",
    "David Miller",
    "Morgan Bailey",
    "Rachel Green",
    "Michael Scott",
    "Samantha Davis",
    "Alexander Harris",
    "Nova Retail Traders",
    "Apex Global Logistics",
    "Zenith Holdings Pvt Ltd",
    "Summit Tech Solutions",
    "Beacon Capital Partners",
    "Metropolitan Enterprises"
]

SYNTHETIC_ADDRESS_LINES = [
    "PLOT NO 42, PHASE 2, INDUSTRIAL AREA",
    "SUITE 300, METRO BUSINESS TOWER",
    "SECTOR 18, NEAR COMMERCIAL COMPLEX",
    "104 MAIN ROAD, TECHNOLOGY PARK",
    "NEW DELHI, DELHI 110001",
    "MUMBAI, MAHARASHTRA 400051",
    "BENGALURU, KARNATAKA 560001"
]

SYNTHETIC_BRANCHES = [
    "CENTRAL BUSINESS BRANCH",
    "METRO MAIN BRANCH",
    "FINANCIAL DISTRICT BRANCH",
    "AIRPORT ROAD BRANCH"
]


class SyntheticDataEngine:
    """Substitutes realistic synthetic financial and personal data."""

    def __init__(self, seed: int = 42, default_font: str = "Helvetica", default_size_pt: float = 8.0):
        self.rng = random.Random(seed)
        self.default_font = default_font
        self.default_size_pt = default_size_pt

    def _hash_seed(self, text: str) -> int:
        """Deterministic seed per input string to ensure consistent replacement within a document."""
        return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)

    def generate_synthetic_name(self, original_name: str, target_width_pt: Optional[float] = None, font_name: str = "Helvetica", font_size_pt: float = 8.0) -> Tuple[str, float]:
        """Returns a realistic synthetic name closely matching the length/width."""
        seed = self._hash_seed(original_name)
        orig_len = len(original_name)

        # Sort candidates by length difference to original
        candidates = sorted(SYNTHETIC_NAMES, key=lambda n: abs(len(n) - orig_len))
        # Deterministically pick best match
        idx = seed % min(3, len(candidates))
        synth = candidates[idx]

        orig_w = target_width_pt or get_string_width_pt(original_name, font_name, font_size_pt)
        synth_w = get_string_width_pt(synth, font_name, font_size_pt)
        return synth, abs(orig_w - synth_w)

    def generate_synthetic_account(self, original_acct: str) -> str:
        """Generates synthetic account number preserving masking or punctuation."""
        seed = self._hash_seed(original_acct)
        rng = random.Random(seed)

        result = []
        for ch in original_acct:
            if ch.isdigit():
                result.append(str(rng.randint(0, 9)))
            elif ch.isalpha():
                result.append(chr(rng.randint(ord('A'), ord('Z'))))
            else:
                result.append(ch)
        return "".join(result)

    def generate_synthetic_date(self, original_date: str) -> str:
        """Generates realistic synthetic date keeping format intact."""
        seed = self._hash_seed(original_date)
        rng = random.Random(seed)

        day = rng.randint(1, 28)
        month = rng.randint(1, 12)
        year = rng.randint(2024, 2026)

        if "/" in original_date:
            parts = original_date.split("/")
            if len(parts) == 3:
                y_str = f"{year % 100:02d}" if len(parts[2].strip()) == 2 else f"{year}"
                return f"{day:02d}/{month:02d}/{y_str}"
        elif "-" in original_date:
            parts = original_date.split("-")
            if len(parts) == 3:
                months_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                if any(c.isalpha() for c in parts[1]):
                    m_str = months_abbr[month - 1]
                else:
                    m_str = f"{month:02d}"
                y_str = f"{year % 100:02d}" if len(parts[2].strip()) == 2 else f"{year}"
                return f"{day:02d}-{m_str}-{y_str}"

        return f"{day:02d}/01/2026"

    def generate_synthetic_amount(self, original_amount: str) -> str:
        """Generates realistic synthetic amount keeping currency/decimal structure."""
        seed = self._hash_seed(original_amount)
        rng = random.Random(seed)

        cleaned = re.sub(r'[^\d.]', '', original_amount)
        try:
            val = float(cleaned)
            # Scale slightly while keeping magnitude
            factor = rng.uniform(0.7, 1.3)
            new_val = round(max(1.0, val * factor), 2)
        except Exception:
            new_val = round(rng.uniform(10.0, 5000.0), 2)

        has_comma = "," in original_amount
        prefix = ""
        for p in ["$", "₹", "INR ", "Rs. ", "£", "€"]:
            if original_amount.startswith(p):
                prefix = p
                break

        if has_comma:
            fmt = f"{new_val:,.2f}"
        else:
            fmt = f"{new_val:.2f}"

        return f"{prefix}{fmt}"

    def generate_synthetic_address(self, original_address: str) -> str:
        """Generates synthetic address line."""
        seed = self._hash_seed(original_address)
        idx = seed % len(SYNTHETIC_ADDRESS_LINES)
        return SYNTHETIC_ADDRESS_LINES[idx]

    def generate_synthetic_phone(self, original_phone: str) -> str:
        """Generates synthetic phone number."""
        seed = self._hash_seed(original_phone)
        rng = random.Random(seed)
        digits = [str(rng.randint(0, 9)) for _ in range(10)]
        if original_phone.startswith("+"):
            return f"+1 555 {''.join(digits[:3])}-{''.join(digits[3:7])}"
        elif "-" in original_phone:
            return f"022-{''.join(digits[:4])}{''.join(digits[4:8])}"
        return f"98{''.join(digits[:8])}"

    def generate_synthetic_email(self, original_email: str) -> str:
        """Generates synthetic email or UPI handle."""
        seed = self._hash_seed(original_email)
        rng = random.Random(seed)
        domains = ["example.com", "finmail.test", "corpdomain.org", "samplebank.net"]
        handles = ["user", "customer", "account", "billing", "client"]
        d = domains[seed % len(domains)]
        h = handles[seed % len(handles)]
        num = rng.randint(100, 999)
        if "@" in original_email and not "." in original_email.split("@")[1]:
            # UPI handle
            return f"{h}{num}@samplebank"
        return f"{h}.{num}@{d}"

    def generate_synthetic_ifsc(self, original_ifsc: str) -> str:
        """Generates realistic synthetic IFSC maintaining bank prefix structure."""
        seed = self._hash_seed(original_ifsc)
        rng = random.Random(seed)
        banks = ["BKID", "HDFC", "SBIN", "ICIC", "PUNB", "BARB", "UTIB"]
        bank = banks[seed % len(banks)]
        branch_num = "".join(str(rng.randint(0, 9)) for _ in range(6))
        return f"{bank}0{branch_num}"

    def generate_synthetic_micr(self, original_micr: str) -> str:
        """Generates realistic 9-digit synthetic MICR code."""
        seed = self._hash_seed(original_micr)
        rng = random.Random(seed)
        return "".join(str(rng.randint(0, 9)) for _ in range(9))

    def generate_synthetic_branch(self, original_branch: str) -> str:
        """Generates realistic synthetic branch name or code."""
        seed = self._hash_seed(original_branch)
        if original_branch.strip().isdigit():
            return f"{seed % 9999:04d}"
        idx = seed % len(SYNTHETIC_BRANCHES)
        return SYNTHETIC_BRANCHES[idx]

    def generate_synthetic_currency(self, original_curr: str) -> str:
        """Preserves or normalizes currency code."""
        c = original_curr.strip().upper()
        if c in ["INR", "USD", "EUR", "GBP", "CAD", "AUD", "JPY"]:
            return c
        return "INR"

    def generate_synthetic_acct_type(self, original_type: str) -> str:
        """Generates standard realistic account type."""
        orig_u = original_type.strip().upper()
        if "SAV" in orig_u:
            return "SAVINGS"
        elif "CURR" in orig_u:
            return "CURRENT- GENERAL"
        elif "OD" in orig_u or "OVER" in orig_u:
            return "OVERDRAFT"
        return "SAVINGS"

    def generate_synthetic_nominee(self, original_nominee: str) -> str:
        """Generates realistic nominee status."""
        orig_u = original_nominee.strip().upper()
        if any(w in orig_u for w in ["REG", "YES"]):
            return "REGISTERED"
        elif any(w in orig_u for w in ["NOT", "NO", "NONE"]):
            return "NOT REGISTERED"
        return "REGISTERED"

    def substitute_text(
        self,
        text: str,
        category: str = "GENERAL",
        font_name: Optional[str] = None,
        font_size_pt: Optional[float] = None
    ) -> Tuple[str, float]:
        """Substitutes a text string based on its PII category."""
        fn = font_name or self.default_font
        fs = font_size_pt or self.default_size_pt

        orig_w = get_string_width_pt(text, fn, fs)

        if category == "NAME":
            synth, w_delta = self.generate_synthetic_name(text, orig_w, fn, fs)
        elif category == "ACCOUNT_NUMBER":
            synth = self.generate_synthetic_account(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "DATE":
            synth = self.generate_synthetic_date(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "AMOUNT":
            synth = self.generate_synthetic_amount(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "ADDRESS":
            synth = self.generate_synthetic_address(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "PHONE":
            synth = self.generate_synthetic_phone(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "EMAIL":
            synth = self.generate_synthetic_email(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "IFSC":
            synth = self.generate_synthetic_ifsc(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "MICR":
            synth = self.generate_synthetic_micr(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "BRANCH":
            synth = self.generate_synthetic_branch(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "CURRENCY":
            synth = self.generate_synthetic_currency(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "ACCOUNT_TYPE":
            synth = self.generate_synthetic_acct_type(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "STATUS":
            synth = "Regular" if text.strip().capitalize() in ["Regular", "Active"] else text.strip()
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        elif category == "NOMINEE":
            synth = self.generate_synthetic_nominee(text)
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)
        else:
            synth = self.generate_synthetic_name(text, orig_w, fn, fs)[0]
            synth_w = get_string_width_pt(synth, fn, fs)
            w_delta = abs(orig_w - synth_w)

        return synth, w_delta
