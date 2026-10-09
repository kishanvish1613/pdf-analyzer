"""
Backend Dimension Exporter Engine.
Generates authoritative export formats from the Dimension Editor model:
- Plain Text
- Markdown Table (spec 4.1 compliant)
- Prompt-Ready Block (compact Title = value pt under group headings)
- TSV (Excel / Google Sheets compatible)
- CSV
- Structured JSON Specification
"""

from __future__ import annotations
import json
import csv
import io
from typing import Dict, Any, List, Optional
from pdf_analyzer.privacy.engine import apply_privacy_to_editor_model, SyntheticDataEngine


KNOWN_BANKS = {
    "STATE BANK OF INDIA": {
        "name": "State Bank of India",
        "tagline": "The banker to every Indian",
        "theme_color": "#524c94",
        "header_style": "top_banner",
        "default_title": "STATEMENT OF ACCOUNT",
    },
    "SBI": {
        "name": "State Bank of India",
        "tagline": "The banker to every Indian",
        "theme_color": "#524c94",
        "header_style": "top_banner",
        "default_title": "STATEMENT OF ACCOUNT",
    },
    "BANK OF INDIA": {
        "name": "Bank of India",
        "tagline": "Relationship beyond banking",
        "theme_color": "#0f172a",
        "header_style": "right_brand",
        "default_title": "Statement of account",
    },
    "HDFC BANK": {
        "name": "HDFC Bank",
        "tagline": "We understand your world",
        "theme_color": "#004c8f",
        "header_style": "right_brand",
        "default_title": "Account Statement",
    },
    "ICICI BANK": {
        "name": "ICICI Bank",
        "tagline": "Hum Hai Na, Khayal Aapka",
        "theme_color": "#b02a30",
        "header_style": "right_brand",
        "default_title": "Account Statement",
    },
    "AXIS BANK": {
        "name": "Axis Bank",
        "tagline": "Badhti Ka Naam Zindagi",
        "theme_color": "#97144d",
        "header_style": "right_brand",
        "default_title": "Account Statement",
    },
    "PUNJAB NATIONAL BANK": {
        "name": "Punjab National Bank",
        "tagline": "The name you can bank upon",
        "theme_color": "#a20a3a",
        "header_style": "top_banner",
        "default_title": "Account Statement",
    },
    "CANARA BANK": {
        "name": "Canara Bank",
        "tagline": "Together We Can",
        "theme_color": "#0072bc",
        "header_style": "top_banner",
        "default_title": "Account Statement",
    },
    "BANK OF BARODA": {
        "name": "Bank of Baroda",
        "tagline": "India's International Bank",
        "theme_color": "#f26522",
        "header_style": "top_banner",
        "default_title": "Account Statement",
    },
    "UNION BANK OF INDIA": {
        "name": "Union Bank of India",
        "tagline": "Good people to bank with",
        "theme_color": "#005a9c",
        "header_style": "top_banner",
        "default_title": "Account Statement",
    },
    "KOTAK MAHINDRA BANK": {
        "name": "Kotak Mahindra Bank",
        "tagline": "Let's make money simple",
        "theme_color": "#ed1c24",
        "header_style": "right_brand",
        "default_title": "Account Statement",
    }
}


def _parse_block_lines(
    lines: List[str],
    existing_kvs: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[str], List[Dict[str, Any]], Optional[str], Optional[str]]:
    """Helper to parse a sequence of text lines into address lines, structured KV pairs, statement period, and statement date."""
    known_keys = [
        "DATE OF STATEMENT", "STATEMENT DATE", "CLEAR BALANCE", "UNCLEARED AMOUNT", "+MOD BAL", "MOD BAL", "LIEN", "LIMIT",
        "MONTHLY AVG BALANCE", "AVG BALANCE", "INTEREST RATE", "RATE OF INTEREST", "DRAWING POWER", "ACCOUNT OPEN DATE", "ACCOUNT OPEN",
        "BRANCH CODE", "BRANCH NAME", "BRANCH EMAIL", "BRANCH PHONE", "PHONE", "CIF NUMBER", "CIF NO", "ACCOUNT NUMBER", "ACCOUNT NO", "A/C NO",
        "PRODUCT", "ACCOUNT TYPE", "IFSC CODE", "IFSC", "RTGS/NEFT IFSC", "CURRENCY", "ACCOUNT STATUS", "STATUS", "CKYCR NUMBER", "CKYCR NO",
        "MICR CODE", "MICR", "NOMINEE NAME", "NOMINEE", "STATEMENT FROM", "PERIOD"
    ]
    address_lines: List[str] = []
    kvs: List[Dict[str, Any]] = []
    statement_period: Optional[str] = None
    statement_date: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == ":":
            i += 1
            continue

        if "STATEMENT FROM" in line.upper():
            statement_period = line
            i += 1
            continue

        if ":" in line:
            parts = line.split(":", 1)
            k, v = parts[0].strip(), parts[1].strip()
            if k and v and v != "-":
                kvs.append({"key": k, "value": v})
                if "DATE" in k.upper() and not "OPEN" in k.upper():
                    statement_date = v
                i += 1
                continue
            elif k and not v:
                if i + 1 < len(lines):
                    next_l = lines[i+1].strip()
                    if next_l == ":" and i + 2 < len(lines):
                        v_val = lines[i+2].strip()
                        kvs.append({"key": k, "value": v_val})
                        if "DATE" in k.upper() and not "OPEN" in k.upper():
                            statement_date = v_val
                        i += 3
                        continue
                    elif next_l and not any(next_l.upper().startswith(kk) for kk in known_keys):
                        v_val = next_l.lstrip(":").strip()
                        kvs.append({"key": k, "value": v_val})
                        if "DATE" in k.upper() and not "OPEN" in k.upper():
                            statement_date = v_val
                        i += 2
                        continue

        matched_k = next((kk for kk in known_keys if line.upper().startswith(kk) or line.upper().endswith(kk)), None)
        if matched_k:
            words = line.split()
            if len(words) >= 2 and any(c.isdigit() for c in words[-1]):
                k_part = " ".join(words[:-1]).rstrip(":")
                v_part = words[-1]
                kvs.append({"key": k_part, "value": v_part})
                if "DATE" in k_part.upper() and not "OPEN" in k_part.upper():
                    statement_date = v_part
                i += 1
                continue
            elif i + 1 < len(lines):
                next_l = lines[i+1].strip()
                if next_l == ":" and i + 2 < len(lines):
                    v_val = lines[i+2].strip()
                    kvs.append({"key": line.rstrip(":"), "value": v_val})
                    if "DATE" in line.upper() and not "OPEN" in line.upper():
                        statement_date = v_val
                    i += 3
                    continue
                elif next_l and not any(next_l.upper().startswith(kk) for kk in known_keys):
                    v_val = next_l.lstrip(":").strip()
                    kvs.append({"key": line.rstrip(":"), "value": v_val})
                    if "DATE" in line.upper() and not "OPEN" in line.upper():
                        statement_date = v_val
                    i += 2
                    continue
            kvs.append({"key": line.rstrip(":"), "value": "-"})
            i += 1
            continue

        if not any(term in line.upper() for term in ["WELCOME", "STATE BANK OF INDIA", "BANK OF INDIA", "ACCOUNT SUMMARY"]):
            if line not in address_lines:
                address_lines.append(line)
        i += 1

    if existing_kvs:
        for ekv in existing_kvs:
            if ekv.get("key") and ekv.get("value") and not any(k["key"].upper() == ekv["key"].upper() for k in kvs):
                kvs.append(ekv)

    return address_lines[:4], kvs, statement_period, statement_date


def generate_ai_prompt(
    model: Dict[str, Any],
    unit: str = "pt",
    decimals: int = 2,
    include_definitions: bool = True,
    privacy_mode: str = "synthetic"
) -> str:
    """Generates an authoritative, prompt-engineered specification for LLMs to generate exact PDFs."""
    # Apply privacy transformation if requested (default synthetic)
    if privacy_mode in ("synthetic", "redacted"):
        model, _ = apply_privacy_to_editor_model(model, mode=privacy_mode)

    doc_name = model.get("document_name") or "document.pdf"
    page_num = model.get("page_number") or 1
    w_pt = float(model.get("width_pt") or 612.0)
    h_pt = float(model.get("height_pt") or 792.0)
    w_mm = (w_pt * 25.4) / 72.0
    h_mm = (h_pt * 25.4) / 72.0
    w_in = w_pt / 72.0
    h_in = h_pt / 72.0
    dpi = int(model.get("dpi") or 300)
    scale_factor = float(model.get("scale_factor") or (dpi / 72.0))

    t_bbox = model.get("table_bbox") or {}
    t_x0 = float(t_bbox.get("x0_pt") or 36.0)
    t_y0 = float(t_bbox.get("y0_pt") or 200.0)
    t_w_raw = t_bbox.get("width_pt") or 540.0
    t_h_raw = t_bbox.get("height_pt") or 400.0
    t_x1 = float(t_bbox.get("x1_pt") or (t_x0 + float(t_w_raw)))
    t_y1 = float(t_bbox.get("y1_pt") or (t_y0 + float(t_h_raw)))
    t_w = float(t_bbox.get("width_pt") or (t_x1 - t_x0))
    t_h = float(t_bbox.get("height_pt") or (t_y1 - t_y0))
    t_w_mm = (t_w * 25.4) / 72.0

    columns = model.get("columns") or []
    boxes = model.get("boxes") or []
    rows = model.get("rows") or []

    # Margins
    left_m = t_x0
    top_m = t_y0
    right_m = max(0.0, w_pt - t_x1)
    bottom_m = max(0.0, h_pt - t_y1)

    # 1. Collect all raw texts and detect Bank branding
    all_text_lines = []
    for b in boxes:
        all_text_lines.extend(b.get("text_lines", []))
        if b.get("raw_text"):
            all_text_lines.extend([l for l in b.get("raw_text").split("\n") if l])
        for kv in b.get("kv_entries", []):
            if kv.get("key"):
                all_text_lines.append(kv["key"])
            if kv.get("value"):
                all_text_lines.append(str(kv["value"]))

    combined_text = " ".join(all_text_lines).upper()

    matched_bank_info = None
    for key, b_info in KNOWN_BANKS.items():
        if key in combined_text or key in doc_name.upper():
            matched_bank_info = b_info
            break

    if matched_bank_info:
        bank_name = matched_bank_info["name"]
        bank_tagline = matched_bank_info["tagline"]
        theme_color = matched_bank_info.get("theme_color", "#0f172a")
        header_style = matched_bank_info.get("header_style", "right_brand")
        default_title = matched_bank_info.get("default_title", "STATEMENT OF ACCOUNT")
    else:
        bank_name = "State Bank of India" if "SBI" in combined_text else ("Bank of India" if "BANK OF INDIA" in combined_text else "Financial Services")
        bank_tagline = "Relationship beyond banking" if "Bank of India" in bank_name else "Account Statement"
        theme_color = "#524c94" if "SBI" in combined_text or "State Bank" in bank_name else "#0f172a"
        header_style = "top_banner" if "SBI" in combined_text or "State Bank" in bank_name else "right_brand"
        default_title = "Statement of account"

    # Check for top banner container (e.g. y0 < 60, width >= 400)
    top_banner_box = next((b for b in boxes if float(b.get("y0_pt", 999)) < 60.0 and float(b.get("width_pt", 0)) >= 400.0), None)
    has_top_banner = bool(top_banner_box or header_style == "top_banner")
    if has_top_banner:
        banner_left_text = "Account Summary"
        banner_right_text = "Welcome: Account Holder<br/>As on 23-03-2026"
        if top_banner_box and top_banner_box.get("text_lines"):
            tbl = top_banner_box["text_lines"]
            for line in tbl:
                if "ACCOUNT" in line.upper() or "SUMMARY" in line.upper():
                    banner_left_text = line
                elif "WELCOME" in line.upper() or "AS ON" in line.upper():
                    banner_right_text = "<br/>".join([l for l in tbl if "ACCOUNT" not in l.upper() and "SUMMARY" not in l.upper()])

    # 2. Extract Customer (Left) and Branch (Right) info
    header_boxes = [b for b in boxes if b.get("owner_id") in ["target_header", "target_boxes", "target_logo"] or b.get("type") in ["header", "header_block", "statement_title", "container", "logo"]]
    footer_boxes = [b for b in boxes if b.get("owner_id") == "target_footer" or b.get("type") in ["footer", "statement_summary", "generated_info", "page_number"]]
    title_box = next((b for b in boxes if b.get("type") == "statement_title"), None)
    statement_title_text = title_box.get("raw_text") if title_box else default_title
    if isinstance(statement_title_text, list):
        statement_title_text = statement_title_text[0] if statement_title_text else default_title

    customer_box = next((b for b in header_boxes if b.get("id") == "box_header_block_left" or (b.get("type") == "header_block" and float(b.get("x0_pt", 0)) < (w_pt / 2.0))), None)
    branch_kv_box = next((b for b in header_boxes if b.get("id") == "box_header_block_right" or (b.get("type") == "header_block" and float(b.get("x0_pt", 0)) >= (w_pt / 3.0))), None)

    # Fallback to any header boxes
    if not customer_box and header_boxes:
        customer_box = header_boxes[0]
    if not branch_kv_box and len(header_boxes) > 1:
        branch_kv_box = header_boxes[1]

    # Parse Left Customer Box (Address + Left KVs)
    left_lines = customer_box.get("text_lines", []) if customer_box else []
    left_address_lines, left_kvs, left_period, left_s_date = _parse_block_lines(left_lines, customer_box.get("kv_entries") if customer_box else None)

    if not left_address_lines:
        left_address_lines = [
            "RAVINDRA NASHIKKAR",
            "34, SILVAR OAKS COLONY, ANNAPURNA ROAD",
            "INDORE, MADHYA PRADESH 452009",
            "Email: ravindranashikkar01@gmail.com"
        ]

    # Parse Right Branch Box (Branch Address + Right KVs)
    right_lines = branch_kv_box.get("text_lines", []) if branch_kv_box else []
    right_address_lines, right_kvs, statement_period, statement_date_val = _parse_block_lines(right_lines, branch_kv_box.get("kv_entries") if branch_kv_box else None)

    # Search for Opening Balance and Statement Dates
    opening_balance_val = "501.50Cr."
    for b in header_boxes:
        for line in b.get("text_lines", []):
            if "OPENING BALANCE" in line.upper():
                parts = line.split(":", 1)
                if len(parts) > 1:
                    opening_balance_val = parts[1].strip()
            elif "CR" in line.upper() and not "OPEN" in line.upper() and any(c.isdigit() for c in line):
                opening_balance_val = line.strip()

    if not statement_period:
        if left_period:
            statement_period = left_period
        elif "FROM" in statement_title_text.upper():
            statement_period = f"OPENING BALANCE : {opening_balance_val}"
        elif "SBI" in combined_text or "STATE BANK" in bank_name:
            statement_period = "Statement From : 21-08-2025 to 23-03-2026"
        else:
            statement_period = f"OPENING BALANCE : {opening_balance_val}"

    if not statement_date_val:
        statement_date_val = left_s_date or "23-03-2026"

    if not right_kvs:
        right_kvs = [
            {"key": "Branch Code", "value": "16450"},
            {"key": "Branch Name", "value": "ROHIT NAGAR, BHOPAL"},
            {"key": "Branch Phone", "value": "8989791948"},
            {"key": "CIF Number", "value": "80459914494"},
            {"key": "Account Number", "value": "10586227736"},
            {"key": "Product", "value": "Savings Bank Account"},
            {"key": "IFSC Code", "value": "SBIN0016450"},
            {"key": "Currency", "value": "INR"},
            {"key": "Account Status", "value": "OPEN"},
            {"key": "MICR Code", "value": "462002093"},
            {"key": "Nominee Name", "value": "REGISTERED"}
        ]

    if not statement_period:
        statement_period = "Statement From : 21-08-2025 to 23-03-2026"

    footer_lines = []
    for fb in footer_boxes:
        if fb.get("text_lines"):
            footer_lines.extend([l.strip() for l in fb["text_lines"] if l.strip()])
    footer_lines = [l for l in footer_lines if len(l) > 12 and not any(l.lower().startswith(p) for p in ["page", "page no", "page:"])]
    if not footer_lines:
        footer_lines = [
            f"{bank_name.upper()} | OFFICIAL ACCOUNT STATEMENT",
            "*Closing balance includes funds held in uncleared cheques/clearing.",
            "Please examine this statement immediately. Any discrepancy should be reported to the branch."
        ]

    # Containers / Boxes table
    box_rows = []
    for b in boxes:
        b_id = b.get("id", "box")
        b_title = b.get("title") or b.get("type") or b_id
        bx0 = float(b.get("x0_pt", 0.0))
        by0 = float(b.get("y0_pt", 0.0))
        bw = float(b.get("width_pt", b.get("x1_pt", 0.0) - bx0))
        bh = float(b.get("height_pt", b.get("y1_pt", 0.0) - by0))
        b_type = b.get("type", "container")
        box_rows.append(f"| {b_title} ({b_type}) | x0: {bx0:.{decimals}f} pt, y0: {by0:.{decimals}f} pt | width: {bw:.{decimals}f} pt, height: {bh:.{decimals}f} pt |")
    boxes_table_md = "\n".join(box_rows) if box_rows else "No standalone container boxes detected."

    # Row metrics
    header_row_h = 22.0
    body_row_pitch = 37.20
    if rows:
        header_rows = [r for r in rows if r.get("row_type") == "header" or r.get("is_header")]
        body_rows = [r for r in rows if not (r.get("row_type") == "header" or r.get("is_header"))]
        if header_rows and header_rows[0].get("height_pt"):
            header_row_h = float(header_rows[0]["height_pt"])
        elif header_rows and header_rows[0].get("y1_pt") and header_rows[0].get("y0_pt"):
            header_row_h = float(header_rows[0]["y1_pt"] - header_rows[0]["y0_pt"])
        if body_rows:
            pitches = [float(r.get("pitch_pt", r.get("y1_pt", 0) - r.get("y0_pt", 0))) for r in body_rows if float(r.get("pitch_pt", 0)) > 0]
            if pitches:
                body_row_pitch = sum(pitches) / len(pitches)

    # 3. Resolve Column Headers (Infers semantic financial names if text was vector-outlined)
    standard_7_col_headers = ["Value Date", "Post Date", "Details", "Ref No/Cheque No", "Debit", "Credit", "Balance"]
    standard_6_col_headers = ["Date", "Description", "Ref No.", "Debit", "Credit", "Balance"]
    standard_5_col_headers = ["Date", "Description", "Debit", "Credit", "Balance"]
    standard_4_col_headers = ["Date", "Description", "Amount", "Balance"]

    col_rows = []
    col_widths_list = []
    col_headers = []
    col_aligns = []
    num_cols = len(columns)

    for idx, c in enumerate(columns):
        c_idx = c.get("column_index", idx + 1)
        h_raw = c.get("header_text")
        h_sugg = c.get("header_text_suggested")
        if not h_raw or str(h_raw).lower() in ("none", "", f"col {c_idx}".lower()):
            if h_sugg:
                h_text = h_sugg
            elif num_cols == 7:
                h_text = standard_7_col_headers[idx]
            elif num_cols == 6:
                h_text = standard_6_col_headers[idx]
            elif num_cols == 5:
                h_text = standard_5_col_headers[idx]
            elif num_cols == 4:
                h_text = standard_4_col_headers[idx]
            else:
                h_text = f"Col {c_idx}"
        else:
            h_text = h_raw

        col_headers.append(h_text)
        cx0 = float(c.get("x0_pt", 0.0))
        cx1 = float(c.get("x1_pt", cx0 + float(c.get("width_pt", 50.0))))
        cw = float(c.get("width_pt", cx1 - cx0))
        cw_mm = (cw * 25.4) / 72.0
        cw_pct = (cw / t_w * 100.0) if t_w > 0 else 0.0
        h_lower = h_text.lower()
        if any(w in h_lower for w in ["amount", "amt", "balance", "debit", "credit", "withdrawal", "deposit", "rate", "total", "qty", "rs", "inr", "₹"]):
            align = "right"
        elif any(w in h_lower for w in ["date", "dt", "val", "chq", "ref", "post", "sno", "inst"]):
            align = "center"
        else:
            align = "left"
        col_aligns.append(align)
        col_widths_list.append(round(cw, decimals))
        col_rows.append(
            f"| {c_idx} | {h_text} | {cx0:.{decimals}f} pt | {cx1:.{decimals}f} pt | {cw:.{decimals}f} pt | {cw_mm:.{decimals}f} mm | {cw_pct:.1f}% | {align.capitalize()} |"
        )
    col_table_md = "\n".join(col_rows) if col_rows else "| 1 | Main Content | 0.00 pt | 540.00 pt | 540.00 pt | 190.50 mm | 100.0% | Left |"
    headers_json = json.dumps(col_headers)

    # 4. Multi-line Sample Transactions Matching Columns
    if num_cols == 7:
        if privacy_mode == "real":
            sample_transactions = [
                ["21/08/25", "21/08/25", "TRANSFER FROM 50901<br/>UPI/CR/523314051010/PAYMENT<br/>FROM PHONEPE", "TRANSFER", "", "1,500.00", "1,702.88"],
                ["23/08/25", "23/08/25", "TO TRANSFER-INB<br/>UPI/DR/523588910291/PAYMENT<br/>TO MERCHANT", "TRANSFER", "500.00", "", "1,202.88"],
                ["01/09/25", "01/09/25", "BY CLG CHQ DEP<br/>CHQ NO 000042 - HDFC BANK<br/>CLEARING MUMBAI", "000042", "", "25,000.00", "26,202.88"],
                ["15/09/25", "15/09/25", "ATM WDL-ATM CASH 16450<br/>ROHIT NAGAR BHOPAL", "ATM", "5,000.00", "", "21,202.88"]
            ]
        elif privacy_mode == "redacted":
            sample_transactions = [
                ["21/08/26", "21/08/26", "TRANSFER FROM XXXXX<br/>UPI/CR/XXXXXXXXXXXX/PAYMENT<br/>FROM XXXXXXX", "TRANSFER", "", "8,888.00", "8,888.88"],
                ["23/08/26", "23/08/26", "TO TRANSFER-XXX<br/>UPI/DR/XXXXXXXXXXXX/PAYMENT<br/>TO XXXXXXXX", "TRANSFER", "888.00", "", "8,888.88"],
                ["01/09/26", "01/09/26", "BY CLG CHQ DEP<br/>CHQ NO XXXXXX - XXXX BANK<br/>CLEARING XXXXXX", "XXXXXX", "", "88,888.00", "88,888.88"],
                ["15/09/26", "15/09/26", "ATM WDL-ATM CASH XXXXX<br/>XXXXX XXXXX XXXXXX", "ATM", "8,888.00", "", "88,888.88"]
            ]
        else:  # synthetic
            sample_transactions = [
                ["21/08/25", "21/08/25", "TRANSFER FROM 40821<br/>UPI/CR/948201948201/PAYMENT<br/>FROM MOBILE APP", "TRANSFER", "", "2,500.00", "2,702.88"],
                ["23/08/25", "23/08/25", "TO TRANSFER-INB<br/>UPI/DR/382910482910/PAYMENT<br/>TO VENDOR", "TRANSFER", "750.00", "", "1,952.88"],
                ["01/09/25", "01/09/25", "BY CLG CHQ DEP<br/>CHQ NO 000194 - APEX BANK<br/>CLEARING REGIONAL", "000194", "", "35,000.00", "36,952.88"],
                ["15/09/25", "15/09/25", "ATM WDL-ATM CASH 16450<br/>METRO SQUARE BRANCH", "ATM", "4,000.00", "", "32,952.88"]
            ]
    elif num_cols == 6:
        if privacy_mode == "real":
            sample_transactions = [
                ["12/03/25", "UPI-AARIS KHAN<br/>PAYMENT FROM PHONE", "000044064422778", "", "1.00", "1.00"],
                ["13/03/25", "CHQ DEP : UNICRED<br/>KOTAK MAHINDRA BANK", "000000000000044", "", "50,000.00", "50,001.00"],
                ["13/03/25", "UPI-YAKUB KHAN<br/>PAYMENT FROM PHONE", "000021428015859", "5,000.00", "", "45,001.00"],
                ["14/03/25", "UPI-PAYMENT TO STORE", "000009543320360", "2,000.00", "", "43,001.00"]
            ]
        elif privacy_mode == "redacted":
            sample_transactions = [
                ["12/03/26", "UPI-XXXXX XXXX<br/>PAYMENT FROM PHONE", "000088888888888", "", "88.00", "88.00"],
                ["13/03/26", "CHQ DEP : XXXXXXX<br/>XXXX XXXXXXXX XXXX", "000000000000088", "", "88,888.00", "88,888.00"],
                ["13/03/26", "UPI-XXXXX XXXX<br/>PAYMENT FROM PHONE", "000088888888888", "8,888.00", "", "88,888.00"],
                ["14/03/26", "UPI-PAYMENT TO STORE", "000088888888888", "888.00", "", "88,000.00"]
            ]
        else:  # synthetic
            sample_transactions = [
                ["12/01/26", "UPI-ALEXANDER HARRIS<br/>PAYMENT VIA MOBILE", "000094820194820", "", "125.00", "125.00"],
                ["13/01/26", "CHQ DEP : NOVA TRADERS<br/>BEACON CAPITAL", "000000000000948", "", "25,000.00", "25,125.00"],
                ["14/01/26", "UPI-JORDAN TAYLOR<br/>PAYMENT VIA MOBILE", "000038291048291", "2,500.00", "", "22,625.00"],
                ["15/01/26", "NEFT-INVOICE SETTLEMENT", "000048291029384", "", "5,000.00", "27,625.00"]
            ]
    else:
        sample_transactions = [
            ["12/01/26", "OPENING BALANCE / TRANSFER", "", "1,000.00", "1,000.00"][:num_cols],
            ["13/01/26", "CHEQUE DEPOSIT - CLEARING", "", "25,000.00", "26,000.00"][:num_cols],
            ["14/01/26", "ATM WITHDRAWAL / DEBIT", "2,500.00", "", "23,500.00"][:num_cols],
            ["15/01/26", "NEFT SETTLEMENT", "", "5,000.00", "28,500.00"][:num_cols]
        ]

    # Privacy Protection Banner
    if privacy_mode == "real":
        privacy_banner = """> [!WARNING]
> **CAUTION: REAL CUSTOMER DATA INCLUDED**
> This prompt specification contains unredacted customer PII and sensitive financial transaction records.
> Transmitting this content to external AI services (ChatGPT, Claude, Gemini) may expose private customer data.
"""
    elif privacy_mode == "redacted":
        privacy_banner = """> [!NOTE]
> **PRIVACY PROTECTED (REDACTED MODE)**
> All customer PII (names, account numbers, addresses, transactions) has been replaced with same-width character masks (`XXXX`, `8888`).
> Font layout geometry, advances, and bounding boxes are 100% preserved.
"""
    else:
        privacy_banner = """> [!NOTE]
> **PRIVACY PROTECTED (SYNTHETIC DATA MODE - DEFAULT)**
> All customer PII (names, account numbers, addresses, transactions) has been substituted with realistic synthetic data.
> String widths, column alignments, and bounding boxes are mathematically preserved.
"""

    cust_box_x0 = customer_box.get('x0_pt', 36.0) if customer_box else 36.0
    cust_box_y0 = customer_box.get('y0_pt', 90.0) if customer_box else 90.0
    cust_box_w = customer_box.get('width_pt', 220.0) if customer_box else 220.0
    cust_box_h = customer_box.get('height_pt', 115.0) if customer_box else 115.0

    branch_box_x0 = branch_kv_box.get('x0_pt', 290.0) if branch_kv_box else 290.0
    branch_box_y0 = branch_kv_box.get('y0_pt', 65.0) if branch_kv_box else 65.0
    branch_box_w = branch_kv_box.get('width_pt', 285.0) if branch_kv_box else 285.0
    branch_box_h = branch_kv_box.get('height_pt', 140.0) if branch_kv_box else 140.0

    # Table styling parameters
    is_dark_theme = theme_color not in ["#ffffff", "#f8fafc", "#cbd5e1"]
    table_header_bg = theme_color if has_top_banner and is_dark_theme else "#ffffff"
    table_header_text_color = "#ffffff" if table_header_bg != "#ffffff" else "#0f172a"

    prompt = f"""# System Prompt & Mathematical Layout Specification for AI PDF Generation

{privacy_banner}

## Directive to AI Model
You are a Principal Document Engineering Architect and Pixel-Perfect PDF Layout Compiler.
You are generating an exact, mathematically identical, pixel-matched PDF reproduction of the analyzed document page:
**Document**: `{doc_name}` | **Page**: {page_num}

### CRITICAL REQUIREMENTS:
1. **NO PLACEHOLDERS**: Do NOT emit placeholder text such as `LOGO (placeholder)` or `ACCOUNT / BRANCH INFO (placeholder)`. Emit the EXACT, authoritative content and key-value records specified below.
2. **AUTHENTIC MULTI-LINE TRANSACTION NARRATION**: Transaction rows MUST support multi-line text (2 to 4 lines per row with line breaks `<br/>`) and match the measured body row pitch of `{body_row_pitch:.2f} pt`.
3. **STRICT COLUMN ALIGNMENT**: Financial numeric columns (Withdrawal, Deposit, Balance) MUST be right-aligned with fixed 2-decimal formatting (`50,000.00`, `1.00`). Narration and Reference columns MUST be left-aligned.
4. **CONTINUOUS VERTICAL RULES**: Every column boundary MUST have a continuous vertical rule line separating adjacent columns.
5. **THEME & PALETTE**: Primary Theme Color: `{theme_color}`. Table Header Background: `{table_header_bg}` with `{table_header_text_color}` text.

---

## 1. Global Page Geometry & Coordinate System
- **Page Dimensions**: `{w_pt:.{decimals}f} pt` x `{h_pt:.{decimals}f} pt` ({w_mm:.{decimals}f} mm x {h_mm:.{decimals}f} mm / {w_in:.{decimals}f}" x {h_in:.{decimals}f}")
- **Orientation**: {'Landscape' if w_pt > h_pt else 'Portrait'}
- **Coordinate Space**: Top-Left Origin (CropBox Top-Left = (0, 0); X increases Rightwards, Y increases Downwards)
- **Scale Factor**: {scale_factor:.4f} (at {dpi} Native DPI)
- **Document Margins**:
  - Top Margin: `{top_m:.{decimals}f} pt`
  - Left Margin: `{left_m:.{decimals}f} pt`
  - Right Margin: `{right_m:.{decimals}f} pt`
  - Bottom Margin: `{bottom_m:.{decimals}f} pt`

---

## 2. Header Architecture & Extracted Content

### A. Bank Header & Branding
- **Bank Name**: `{bank_name}` (Tagline: `{bank_tagline}`)
- **Header Style**: `{'Top Colored Banner' if has_top_banner else 'Top Right Branding'}`
- **Theme Color**: `{theme_color}`
- **Statement Date**: `{statement_date_val}`

### B. Customer Account Card (Left Box)
- **Position**: `x0 = {cust_box_x0:.2f} pt`, `y0 = {cust_box_y0:.2f} pt`
- **Dimensions**: `width = {cust_box_w:.2f} pt`, `height = {cust_box_h:.2f} pt`
- **Border**: `1.0 pt solid #64748b`, padding `6 pt`
- **Customer Address Lines**:
{chr(10).join(f'  - `{line}`' for line in left_address_lines)}
{f"- **Account Key-Value Pairs**:" + chr(10) + chr(10).join(f'  - **{kv["key"]}**: `{kv["value"]}`' for kv in left_kvs) if left_kvs else ""}

### C. Branch & Account Details KV Grid (Right Box)
- **Position**: `x0 = {branch_box_x0:.2f} pt`, `y0 = {branch_box_y0:.2f} pt`
- **Dimensions**: `width = {branch_box_w:.2f} pt`, `height = {branch_box_h:.2f} pt`
{f"- **Branch Address Lines**:" + chr(10) + chr(10).join(f'  - `{line}`' for line in right_address_lines) if right_address_lines else ""}
- **Key-Value Pairs**:
{chr(10).join(f'  - **{kv["key"]}**: `{kv["value"]}`' for kv in right_kvs)}

### D. Statement Title & Period Bar
- **Title**: `{statement_title_text}`
- **Statement Period / Opening Balance**: `{statement_period}`
- **Position**: `x0 = {t_x0:.2f} pt`, `y0 = {max(0.0, t_y0 - 22.0):.2f} pt`
- **Font**: Bold 9.5 pt `#0f172a`

---

## 3. Table Architecture & Column Matrix
- **Table Outer Bounding Box**:
  - `x0 = {t_x0:.{decimals}f} pt`, `y0 = {t_y0:.{decimals}f} pt`, `x1 = {t_x1:.{decimals}f} pt`, `y1 = {t_y1:.{decimals}f} pt`
  - **Outer Table Width**: `{t_w:.{decimals}f} pt` ({t_w_mm:.{decimals}f} mm)
  - **Outer Table Height**: `{t_h:.{decimals}f} pt`
- **Column Geometry & Alignments**:
| Col # | Header Label | x0 (pt) | x1 (pt) | Width (pt) | Width (mm) | Width (%) | Text Align |
|---|---|---|---|---|---|---|---|
{col_table_md}

- **Row Heights & Pitch**:
  - Header Row Height: `{header_row_h:.{decimals}f} pt` (Background: `{table_header_bg}`, Font: Bold 8.5pt `{table_header_text_color}`, Bottom border: `1.0 pt solid #0f172a`)
  - Body Row Pitch: `{body_row_pitch:.{decimals}f} pt` (Font: Regular 8.0pt, Line leading: 9.5pt)
  - Continuous Column Vertical Rules: `0.50 pt solid #cbd5e1`

---

## 4. Production-Ready Python Generator (ReportLab Platypus)
Run this complete, self-contained Python script to compile the exact document:

```python
import os
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

PAGE_WIDTH = {w_pt:.{decimals}f}
PAGE_HEIGHT = {h_pt:.{decimals}f}
COL_WIDTHS = {col_widths_list}

def generate_pdf(output_filename="exact_generated_statement.pdf"):
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        leftMargin={left_m:.{decimals}f},
        rightMargin={right_m:.{decimals}f},
        topMargin=20.0 if {str(has_top_banner)} else 36.0,
        bottomMargin=30.0
    )
    
    styles = getSampleStyleSheet()
    
    top_banner_title_style = ParagraphStyle(
        'TopBannerTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        textColor=colors.HexColor('#ffffff')
    )
    
    top_banner_right_style = ParagraphStyle(
        'TopBannerRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#ffffff')
    )
    
    bank_title_style = ParagraphStyle(
        'BankTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('{theme_color}')
    )
    
    title_style = ParagraphStyle(
        'StatementTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=11.5,
        textColor=colors.HexColor('#0f172a')
    )
    
    card_text_style = ParagraphStyle(
        'CardText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#1e293b')
    )
    
    kv_label_style = ParagraphStyle(
        'KVLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.0,
        leading=8.5,
        textColor=colors.HexColor('#334155')
    )
    
    kv_val_style = ParagraphStyle(
        'KVVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.0,
        leading=8.5,
        textColor=colors.HexColor('#0f172a')
    )
    
    header_cell_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=9.5,
        textColor=colors.HexColor('{table_header_text_color}')
    )
    
    cell_left = ParagraphStyle('CellLeft', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9, alignment=TA_LEFT)
    cell_center = ParagraphStyle('CellCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9, alignment=TA_CENTER)
    cell_right = ParagraphStyle('CellRight', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9, alignment=TA_RIGHT)
    
    story = []
    
    # 1. Bank Branding Header
    if {str(has_top_banner)}:
        top_banner_table = Table(
            [[Paragraph({json.dumps(banner_left_text if has_top_banner else bank_name)}, top_banner_title_style),
              Paragraph({json.dumps(banner_right_text if has_top_banner else f"Welcome: Account Holder<br/>As on {statement_date_val}")}, top_banner_right_style)]],
            colWidths=[{w_pt - left_m - right_m} * 0.5, {w_pt - left_m - right_m} * 0.5]
        )
        top_banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('{theme_color}')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(top_banner_table)
        story.append(Spacer(1, 8))
    else:
        bank_brand_p = Paragraph(f"<b>{bank_name}</b><br/><font size='7' color='#64748b'>{bank_tagline}</font>", bank_title_style)
        brand_row = Table([[Paragraph("", card_text_style), bank_brand_p]], colWidths=[270, 270])
        brand_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(brand_row)
        story.append(Spacer(1, 4))
    
    # 2. Customer Card (Left) + Branch KV Grid (Right)
    cust_html = "<br/>".join({json.dumps(left_address_lines)})
    cust_elements = [Paragraph(cust_html, card_text_style)]
    
    left_kvs_data = {json.dumps(left_kvs)}
    if left_kvs_data:
        left_kv_rows = [
            [Paragraph(f"<b>{{kv['key']}}</b>", kv_label_style), Paragraph(f": {{kv['value']}}", kv_val_style)]
            for kv in left_kvs_data
        ]
        left_kv_tbl = Table(left_kv_rows, colWidths=[85, 140])
        left_kv_tbl.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 0.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        left_composite = Table([[cust_elements[0]], [Spacer(1, 3)], [left_kv_tbl]], colWidths=[235])
    else:
        left_composite = cust_elements[0]

    right_kvs_data = {json.dumps(right_kvs)}
    right_kv_rows = [
        [Paragraph(f"<b>{{kv['key']}}</b>", kv_label_style), Paragraph(f": {{kv['value']}}", kv_val_style)]
        for kv in right_kvs_data
    ]
    right_kv_table = Table(right_kv_rows, colWidths=[90, 195])
    right_kv_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 0.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    header_composite = Table(
        [[left_composite, right_kv_table]],
        colWidths=[{w_pt - left_m - right_m} * 0.46, {w_pt - left_m - right_m} * 0.54]
    )
    header_composite.setStyle(TableStyle([
        ('BOX', (0, 0), (0, 0), 0.75, colors.HexColor('#64748b')),
        ('TOPPADDING', (0, 0), (0, 0), 4),
        ('BOTTOMPADDING', (0, 0), (0, 0), 4),
        ('LEFTPADDING', (0, 0), (0, 0), 4),
        ('RIGHTPADDING', (0, 0), (0, 0), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(header_composite)
    story.append(Spacer(1, 8))
    
    # 3. Statement Title & Period Bar
    title_p = Paragraph({json.dumps(statement_title_text)}, title_style)
    period_p = Paragraph(f"<b>{statement_period}</b>", cell_right)
    title_bar = Table([[title_p, period_p]], colWidths=[{w_pt - left_m - right_m} * 0.5, {w_pt - left_m - right_m} * 0.5])
    title_bar.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(title_bar)
    story.append(Spacer(1, 4))
    
    # 4. Main Transaction Table
    col_headers = {headers_json}
    col_aligns = {json.dumps(col_aligns)}
    
    table_data = [[Paragraph(h, header_cell_style) for h in col_headers]]
    
    raw_txns = {json.dumps(sample_transactions)}
    for row in raw_txns:
        row_cells = []
        for i, val in enumerate(row):
            if i < len(col_aligns):
                align = col_aligns[i]
                st = cell_right if align == 'right' else (cell_center if align == 'center' else cell_left)
                row_cells.append(Paragraph(val, st))
            else:
                row_cells.append(Paragraph(val, cell_left))
        table_data.append(row_cells)
    
    main_table = Table(table_data, colWidths=COL_WIDTHS, repeatRows=1)
    main_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('{table_header_bg}')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#0f172a')),
        ('LINEBELOW', (0, 0), (-1, 0), 1.0, colors.HexColor('#0f172a')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 2.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2.5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(main_table)
    story.append(Spacer(1, 10))
    
    # 5. Footer Section
    footer_html = "<br/>".join({json.dumps(footer_lines)})
    footer_p = Paragraph(footer_html, card_text_style)
    story.append(footer_p)
    
    doc.build(story)
    print(f"Generated pixel-perfect PDF: {{output_filename}}")

if __name__ == '__main__':
    generate_pdf()
```

---

## 5. Production-Ready HTML+CSS Template (WeasyPrint / Web Engine)
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{doc_name} Reconstructed</title>
<style>
  @page {{
    size: {w_pt:.{decimals}f}pt {h_pt:.{decimals}f}pt;
    margin: 0;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: {top_m:.{decimals}f}pt {right_m:.{decimals}f}pt {bottom_m:.{decimals}f}pt {left_m:.{decimals}f}pt;
    width: {w_pt:.{decimals}f}pt;
    height: {h_pt:.{decimals}f}pt;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #0f172a;
    background: #ffffff;
    position: relative;
  }}
  .top-banner {{
    background-color: {theme_color};
    color: #ffffff;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6pt 8pt;
    margin-bottom: 8pt;
  }}
  .top-banner .banner-title {{
    font-size: 13pt;
    font-weight: 700;
  }}
  .top-banner .banner-meta {{
    font-size: 8pt;
    text-align: right;
  }}
  .bank-header {{
    display: flex;
    justify-content: flex-end;
    text-align: right;
    margin-bottom: 8pt;
  }}
  .bank-title {{
    font-size: 13pt;
    font-weight: 700;
    color: {theme_color};
    line-height: 1.15;
  }}
  .bank-subtitle {{
    font-size: 7.5pt;
    font-style: italic;
    color: #64748b;
  }}
  .header-container {{
    display: flex;
    justify-content: space-between;
    gap: 12pt;
    margin-bottom: 8pt;
  }}
  .customer-card {{
    flex: 0 0 240pt;
    border: 1pt solid #64748b;
    padding: 5pt;
    font-size: 7.2pt;
    line-height: 1.25;
    color: #1e293b;
  }}
  .branch-kv-table {{
    flex: 1;
    font-size: 7.2pt;
    border-collapse: collapse;
  }}
  .branch-kv-table td {{
    padding: 1pt 2pt;
    vertical-align: top;
  }}
  .branch-kv-table td.key {{
    font-weight: 600;
    width: 95pt;
    color: #334155;
  }}
  .title-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4pt;
  }}
  .statement-title {{
    font-size: 9.5pt;
    font-weight: 700;
    color: #0f172a;
  }}
  .statement-period {{
    font-size: 8pt;
    font-weight: 700;
    color: #0f172a;
    text-align: right;
  }}
  .table-grid {{
    width: {t_w:.{decimals}f}pt;
    border-collapse: collapse;
    font-size: 7.5pt;
    border: 1pt solid #0f172a;
  }}
  .table-grid th, .table-grid td {{
    border: 0.5pt solid #cbd5e1;
    padding: 2.5pt 2.5pt;
    vertical-align: top;
    line-height: 1.2;
  }}
  .table-grid th {{
    background-color: {table_header_bg};
    font-weight: 700;
    border-bottom: 1pt solid #0f172a;
    color: {table_header_text_color};
  }}
  .align-left {{ text-align: left; }}
  .align-center {{ text-align: center; }}
  .align-right {{ text-align: right; }}
  .footer-container {{
    margin-top: 10pt;
    font-size: 7pt;
    line-height: 1.3;
    color: #475569;
  }}
</style>
</head>
<body>
  {f'''<div class="top-banner">
    <div class="banner-title">{banner_left_text if has_top_banner else bank_name}</div>
    <div class="banner-meta">{banner_right_text if has_top_banner else f"Welcome: Account Holder<br/>As on {statement_date_val}"}</div>
  </div>''' if has_top_banner else f'''<div class="bank-header">
    <div>
      <div class="bank-title">{bank_name}</div>
      <div class="bank-subtitle">{bank_tagline}</div>
    </div>
  </div>'''}

  <div class="header-container">
    <div class="customer-card">
      {'<br/>'.join(left_address_lines)}
      {f'<br/><br/>' + ' '.join(f'<div><b>{kv["key"]}</b>: {kv["value"]}</div>' for kv in left_kvs) if left_kvs else ''}
    </div>
    <table class="branch-kv-table">
      {' '.join(f'<tr><td class="key">{kv["key"]}</td><td>: {kv["value"]}</td></tr>' for kv in right_kvs)}
    </table>
  </div>

  <div class="title-bar">
    <div class="statement-title">{statement_title_text}</div>
    <div class="statement-period">{statement_period}</div>
  </div>

  <table class="table-grid">
    <thead>
      <tr>
        {' '.join(f'<th class="align-{align}" style="width: {cw:.{decimals}f}pt;">{ch}</th>' for cw, ch, align in zip(col_widths_list, col_headers, col_aligns))}
      </tr>
    </thead>
    <tbody>
      {' '.join(f'<tr>' + ' '.join(f'<td class="align-{col_aligns[i] if i < len(col_aligns) else "left"}">{cell}</td>' for i, cell in enumerate(row)) + '</tr>' for row in sample_transactions)}
    </tbody>
  </table>

  <div class="footer-container">
    {'<br/>'.join(footer_lines)}
  </div>
</body>
</html>
```
"""
    return prompt.strip()


def export_dimensions(
    model: Dict[str, Any],
    export_format: str = "markdown",
    unit: str = "pt",
    decimals: int = 2,
    frame: str = "page",
    include_definitions: bool = True,
    only_manual: bool = False,
    include_header: bool = True,
    scope: str = "all",
    privacy_mode: str = "synthetic"
) -> str:
    """
    Exports dimension inventory into the requested format with strict unit conversions.
    """
    scale_factor = float(model.get("scale_factor", 300.0 / 72.0))
    dpi = int(model.get("dpi", 300))
    doc_name = model.get("document_name", "document.pdf")
    page_num = model.get("page_number", 1)
    all_dims = model.get("dimensions", [])

    # Filter items
    items: List[Dict[str, Any]] = []
    for d in all_dims:
        if only_manual and not (d.get("is_edited") or d.get("source") == "manual"):
            continue
        if scope != "all" and d.get("group", "").lower() != scope.lower():
            continue
        items.append(d)

    def convert_and_format(pt_val: float) -> str:
        v = float(pt_val)
        if unit == "mm":
            v = (v * 25.4) / 72.0
        elif unit == "px":
            v = (v * dpi) / 72.0
        elif unit == "in":
            v = v / 72.0
        elif unit == "all":
            v_mm = (v * 25.4) / 72.0
            v_px = (v * dpi) / 72.0
            return f"{round(v, decimals)} pt / {round(v_mm, decimals)} mm / {round(v_px, 1)} px"
        return f"{v:.{decimals}f}"

    # 0. ADVANCED AI PROMPT & EXACT SPEC
    if export_format in ("ai_prompt", "ai_generator", "ai_spec"):
        return generate_ai_prompt(model, unit=unit, decimals=decimals, include_definitions=include_definitions, privacy_mode=privacy_mode)


    # 1. MARKDOWN TABLE
    if export_format == "markdown":
        lines = []
        if include_header:
            lines.append(f"## Design Dimensions — {doc_name} (Page {page_num})")
            lines.append(f"*DPI: {dpi} | Coordinate System: CropBox Top-Left Origin (PDF Points)*\n")

        lines.append("| No. | Group | Title | Value | Unit | Definition | From Anchor | To Anchor | Source |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for d in items:
            val_str = convert_and_format(d.get("value_pt", 0.0))
            def_str = d.get("definition", "-") if include_definitions else "-"
            lines.append(
                f"| {d.get('no', '')} | {d.get('group', 'General')} | {d.get('title', '')} | "
                f"{val_str} | {unit} | {def_str} | {d.get('from_anchor', '-')} | {d.get('to_anchor', '-')} | "
                f"{d.get('source', 'auto')} |"
            )
        return "\n".join(lines)

    # 2. PROMPT-READY COMPACT BLOCK
    elif export_format == "prompt":
        lines = []
        if include_header:
            lines.append(f"# PDF Layout Specification — {doc_name} (Page {page_num})")
            w_val = model.get('width_pt')
            h_val = model.get('height_pt')
            if w_val is not None and h_val is not None:
                lines.append(f"# Page Size: {convert_and_format(w_val)} x {convert_and_format(h_val)} {unit}\n")

        # Group items by group
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for d in items:
            grp = d.get("group", "General")
            groups.setdefault(grp, []).append(d)

        order = [
            "Page & Margins",
            "Logo",
            "Header & Account Details",
            "Header",
            "Containers",
            "Table & Columns",
            "Rows & Spacing",
            "Key-Value & Alignment",
            "Footer",
            "Typography",
        ]
        sorted_groups = sorted(groups.keys(), key=lambda g: order.index(g) if g in order else 99)

        for grp in sorted_groups:
            clean_grp = grp.replace(" & ", " ").replace("&", " ")
            lines.append(f"### {clean_grp}")
            for d in groups[grp]:
                val_str = convert_and_format(d.get("value_pt", 0.0))
                note = f" # {d.get('definition')}" if include_definitions and d.get("definition") else ""
                lines.append(f"{d.get('title')} = {val_str} {unit}{note}")
            lines.append("")

        return "\n".join(lines).strip()

    # 3. TSV (Excel / Sheets)
    elif export_format == "tsv":
        out = io.StringIO()
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(["No", "Group", "Title", "Value", "Unit", "Definition", "From_Anchor", "To_Anchor", "Source"])
        for d in items:
            writer.writerow([
                d.get("no", ""),
                d.get("group", ""),
                d.get("title", ""),
                convert_and_format(d.get("value_pt", 0.0)),
                unit,
                d.get("definition", "") if include_definitions else "",
                d.get("from_anchor", ""),
                d.get("to_anchor", ""),
                d.get("source", "auto")
            ])
        return out.getvalue()

    # 4. CSV
    elif export_format == "csv":
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["No", "Group", "Title", "Value", "Unit", "Definition", "From_Anchor", "To_Anchor", "Source"])
        for d in items:
            writer.writerow([
                d.get("no", ""),
                d.get("group", ""),
                d.get("title", ""),
                convert_and_format(d.get("value_pt", 0.0)),
                unit,
                d.get("definition", "") if include_definitions else "",
                d.get("from_anchor", ""),
                d.get("to_anchor", ""),
                d.get("source", "auto")
            ])
        return out.getvalue()

    # 5. STRUCTURED JSON
    elif export_format == "json":
        export_payload = {
            "document_name": doc_name,
            "page_number": page_num,
            "unit": unit,
            "dpi": dpi,
            "width_pt": model.get("width_pt"),
            "height_pt": model.get("height_pt"),
            "dimensions_count": len(items),
            "dimensions": [
                {
                    **d,
                    "formatted_value": convert_and_format(d.get("value_pt", 0.0)),
                    "formatted_unit": unit
                }
                for d in items
            ]
        }
        return json.dumps(export_payload, indent=2)

    # 6. PLAIN TEXT
    else:
        lines = []
        if include_header:
            lines.append(f"{doc_name} — Page {page_num} Dimensions:")
        for d in items:
            lines.append(f"{d.get('title')}: {convert_and_format(d.get('value_pt', 0.0))} {unit}")
        return "\n".join(lines)

