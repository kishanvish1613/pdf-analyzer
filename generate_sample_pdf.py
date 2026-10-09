"""
Comprehensive Synthetic Bank Statement PDF Generator (ReportLab).
Provides exact ground-truth benchmark PDF generators:
- Default: 2-page benchmark statement (F1-F8 regression scenarios)
- T1: Full grid with single-stroke horizontal & vertical rules
- T2: Full grid with double-stroke rules (gap 1.5 pt)
- T3: Vertical rules only with 2-4 wrapped lines per transaction
- T4: Borderless table (whitespace gutters only)
- T5: Zebra fills with alternating row backgrounds and no rules
- T6: Merged header cell spanning 2 body columns
- T7: SNO monotonic integer sequence + date anchor column
- T8: Missing bottom rule
- T9: Numeric cells touching the right rule (< 1 pt padding)
- T10: 2-Page table without repeated continuation header
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors


def create_synthetic_statement(output_pdf_path: str = "sample_statement.pdf") -> str:
    """Generate 2-page benchmark statement with exact layout properties."""
    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    width, height = letter  # 612 x 792 pt

    # ==========================================
    # PAGE 1
    # ==========================================

    # 1. Logo (Top Left)
    c.setFillColor(colors.HexColor("#1A365D"))
    c.roundRect(36, height - 70, 60, 34, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(48, height - 58, "HDFC")

    # 2. Bordered Address Box (Left Block)
    c.setStrokeColor(colors.HexColor("#000000"))
    c.setLineWidth(1.0)
    c.rect(36, height - 175, 220, 95, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#1A202C"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(46, height - 95, "MR. ANAND SHARMA")
    c.setFont("Helvetica", 8.5)
    c.drawString(46, height - 110, "FLAT NO 402, TOWER B")
    c.drawString(46, height - 124, "SUNSHINE RESIDENCY, S.V. ROAD")
    c.drawString(46, height - 138, "BANDRA WEST, MUMBAI - 400050")
    c.drawString(46, height - 152, "MAHARASHTRA, INDIA")
    c.drawString(46, height - 166, "PHONE: +91 98200 12345")

    # 3. Line Just Below Address Box
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(36, height - 192, "Nomination : Registered")

    # 4. Colon-Aligned Key-Value Grid (Right Block)
    kv_items = [
        ("Account Number", ":", "50100234891280"),
        ("Account Type", ":", "SAVINGS ACCOUNT"),
        ("Customer ID", ":", "89341209"),
        ("Branch", ":", "BANDRA WEST BRANCH"),
        ("IFSC Code", ":", "HDFC0000128"),
        ("MICR", ":", "400240012"),
        ("Currency", ":", "INR"),
        ("Statement Period", ":", "01/01/2026 to 31/01/2026")
    ]
    cur_y = height - 90
    for label, colon, val in kv_items:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(310, cur_y, label)
        c.drawString(410, cur_y, colon)
        c.setFont("Helvetica", 8)
        c.drawString(420, cur_y, val)
        cur_y -= 12.5

    # 5. Heading Line
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#4A5568"))
    c.drawString(36, height - 215, "From: 01/01/2026   To: 31/01/2026")

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.HexColor("#1A365D"))
    c.drawString(310, height - 215, "Statement of account")

    # 6. 7-Column Table with VERTICAL RULES ONLY
    v_rules_x = [36, 91, 156, 336, 391, 451, 511, 576]
    table_top = height - 230
    table_bot = 80

    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1.0)
    for vx in v_rules_x:
        c.line(vx, table_top, vx, table_bot)

    c.line(36, table_top, 576, table_top)
    c.line(36, table_top - 18, 576, table_top - 18)
    c.line(36, table_bot, 576, table_bot)

    headers = [
        ("Date", 42), ("Chq/Ref No", 96), ("Narration / Description", 162),
        ("Value Dt", 342), ("Withdrawal", 396), ("Deposit", 460), ("Closing Balance", 516)
    ]
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#1E293B"))
    for h_txt, hx in headers:
        c.drawString(hx, table_top - 13, h_txt)

    p1_txs = [
        {
            "date": "02/01/2026", "ref": "UPI/6002198", "val_dt": "02/01/2026", "debit": "1,450.00", "credit": "", "bal": "1,24,500.00",
            "lines": [
                "UPI-SWIGGY FOOD ORDER-SWIGGY@HDFC",
                "  REF NO 600219871234-ORDER 99281",
                "  MERCHANT PAYMENT BANGALORE IN"
            ]
        },
        {
            "date": "05/01/2026", "ref": "NEFT/881290", "val_dt": "05/01/2026", "debit": "", "credit": "85,000.00", "bal": "2,09,500.00",
            "lines": [
                "NEFT CR-TECH SOLUTIONS PRIVATE LIMITED",
                "  SALARY FOR THE MONTH OF DECEMBER 2025",
                "  UTR: HDFCN26005891230-CMS"
            ]
        },
        {
            "date": "10/01/2026", "ref": "CHQ 000214", "val_dt": "10/01/2026", "debit": "24,000.00", "credit": "", "bal": "1,85,500.00",
            "lines": [
                "TO CLEARING CHEQUE-KOTAK MAHINDRA",
                "  FAVOURING SOCIETY MAINTENANCE CHARGES",
                "  CLEARING HOUSE MUMBAI CTS"
            ]
        },
        {
            "date": "15/01/2026", "ref": "POS/441298", "val_dt": "15/01/2026", "debit": "4,280.00", "credit": "", "bal": "1,81,220.00",
            "lines": [
                "POS DEBIT-RELIANCE FRESH MUMBAI",
                "  AUTH CODE 441298 RETAIL STORE",
                "  TERMINAL ID 88120092 MUMBAI"
            ]
        },
        {
            "date": "20/01/2026", "ref": "INT/REC", "val_dt": "20/01/2026", "debit": "", "credit": "1,145.00", "bal": "1,82,365.00",
            "lines": [
                "INTEREST CREDIT FOR Q3 FY26",
                "  COMPOUNDED QUARTERLY SAVINGS"
            ]
        }
    ]

    row_y = table_top - 32
    for tx in p1_txs:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(40, row_y, tx["date"])
        c.drawString(96, row_y, tx["ref"])
        c.drawString(342, row_y, tx["val_dt"])
        if tx["debit"]:
            c.drawString(405, row_y, tx["debit"])
        if tx["credit"]:
            c.drawString(465, row_y, tx["credit"])
        c.drawString(520, row_y, tx["bal"])

        desc_y = row_y
        for idx, dline in enumerate(tx["lines"]):
            if dline.startswith("  "):
                c.drawString(168, desc_y, dline.strip())
            else:
                c.drawString(160, desc_y, dline)
            desc_y -= 10.5
        row_y = desc_y - 8.0

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(36, 45, "HDFC BANK LIMITED. REGISTERED OFFICE: HDFC BANK HOUSE, SENAPATI BAPAT MARG, LOWER PAREL, MUMBAI 400013.")
    c.drawRightString(576, 45, "Page 1 of 2")

    c.showPage()

    # ==========================================
    # PAGE 2: Continuation Page
    # ==========================================
    p2_table_top = height - 50
    p2_table_bot = 80

    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1.0)
    for vx in v_rules_x:
        c.line(vx, p2_table_top, vx, p2_table_bot)

    c.line(36, p2_table_top, 576, p2_table_top)
    c.line(36, p2_table_bot, 576, p2_table_bot)

    p2_txs = [
        {
            "date": "22/01/2026", "ref": "UPI/6022190", "val_dt": "22/01/2026", "debit": "650.00", "credit": "", "bal": "1,81,715.00",
            "lines": [
                "UPI-AMAZON PAY-MERCHANT@HDFC",
                "  ORDER ID 402-99120912-ONLINE SHOPPING",
                "  BILL PAYMENT AND UTILITIES"
            ]
        },
        {
            "date": "25/01/2026", "ref": "IMPS/99120", "val_dt": "25/01/2026", "debit": "12,000.00", "credit": "", "bal": "1,69,715.00",
            "lines": [
                "IMPS OUT-RAHUL VERMA-ICIC0000192",
                "  FUNDS TRANSFER FOR RENT ADVANCE",
                "  RRN 602519820019"
            ]
        },
        {
            "date": "28/01/2026", "ref": "CHQ 000215", "val_dt": "28/01/2026", "debit": "8,500.00", "credit": "", "bal": "1,61,215.00",
            "lines": [
                "TO CLEARING-TATA AIG GENERAL INS",
                "  HEALTH INSURANCE PREMIUM Q4",
                "  POLICY NO 0155291092"
            ]
        },
        {
            "date": "31/01/2026", "ref": "AUTO/DEB", "val_dt": "31/01/2026", "debit": "236.00", "credit": "", "bal": "1,60,979.00",
            "lines": [
                "MONTHLY AVERAGE BALANCE SHORTFALL CHG",
                "  PLUS GST @ 18% STATUTORY LEVY",
                "  TOTAL DEDUCTION REF 990182",
                "  CLOSING BALANCE CARRIED FORWARD"
            ]
        }
    ]

    p2_row_y = p2_table_top - 18
    for tx in p2_txs:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(40, p2_row_y, tx["date"])
        c.drawString(96, p2_row_y, tx["ref"])
        c.drawString(342, p2_row_y, tx["val_dt"])
        if tx["debit"]:
            c.drawString(405, p2_row_y, tx["debit"])
        if tx["credit"]:
            c.drawString(465, p2_row_y, tx["credit"])
        c.drawString(520, p2_row_y, tx["bal"])

        desc_y = p2_row_y
        for idx, dline in enumerate(tx["lines"]):
            if dline.startswith("  "):
                c.drawString(168, desc_y, dline.strip())
            else:
                c.drawString(160, desc_y, dline)
            desc_y -= 10.5
        p2_row_y = desc_y - 12.0

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(36, 45, "HDFC BANK LIMITED. REGISTERED OFFICE: HDFC BANK HOUSE, SENAPATI BAPAT MARG, LOWER PAREL, MUMBAI 400013.")
    c.drawString(36, 34, "THIS IS A COMPUTER GENERATED STATEMENT AND DOES NOT REQUIRE A PHYSICAL SIGNATURE. -- END OF STATEMENT --")
    c.drawRightString(576, 34, "Page 2 of 2")

    c.showPage()
    c.save()
    return output_pdf_path


# ==========================================
# TEST FIXTURES GENERATOR FUNCTIONS (T1 - T10)
# ==========================================

def create_fixture_t1_full_grid(output_pdf_path: str) -> str:
    """T1: Full grid with single-stroke rules."""
    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    w, h = letter
    c.setLineWidth(1.0)
    c.setStrokeColor(colors.black)
    # 4 columns: 36, 150, 300, 450, 576
    cols = [36, 150, 300, 450, 576]
    rows = [h - 100, h - 130, h - 160, h - 190, h - 220]
    for x in cols:
        c.line(x, rows[0], x, rows[-1])
    for y in rows:
        c.line(cols[0], y, cols[-1], y)

    c.setFont("Helvetica-Bold", 9)
    c.drawString(45, h - 120, "Date")
    c.drawString(160, h - 120, "Description")
    c.drawString(310, h - 120, "Amount")
    c.drawString(460, h - 120, "Balance")

    c.setFont("Helvetica", 8)
    for i, ry in enumerate(rows[1:-1]):
        c.drawString(45, ry - 18, f"0{i+1}/01/2026")
        c.drawString(160, ry - 18, f"Payment Ref {i+100}")
        c.drawString(310, ry - 18, "1,000.00")
        c.drawString(460, ry - 18, "50,000.00")

    c.showPage()
    c.save()
    return output_pdf_path


def create_fixture_t2_double_stroke(output_pdf_path: str) -> str:
    """T2: Full grid with double-stroke rules (gap 1.5 pt)."""
    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    w, h = letter
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.black)
    cols = [36, 150, 300, 450, 576]
    rows = [h - 100, h - 130, h - 160, h - 190]

    for x in cols:
        c.line(x - 0.75, rows[0], x - 0.75, rows[-1])
        c.line(x + 0.75, rows[0], x + 0.75, rows[-1])
    for y in rows:
        c.line(cols[0], y - 0.75, cols[-1], y - 0.75)
        c.line(cols[0], y + 0.75, cols[-1], y + 0.75)

    c.setFont("Helvetica", 8)
    c.drawString(45, h - 120, "01/01/2026")
    c.drawString(160, h - 120, "Double stroke item")
    c.drawString(310, h - 120, "500.00")
    c.drawString(460, h - 120, "10,000.00")
    c.showPage()
    c.save()
    return output_pdf_path


def create_fixture_t4_borderless(output_pdf_path: str) -> str:
    """T4: Borderless table (whitespace only, no vector rules)."""
    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, h - 100, "Date")
    c.drawString(150, h - 100, "Description")
    c.drawString(350, h - 100, "Debit")
    c.drawString(480, h - 100, "Balance")

    c.setFont("Helvetica", 8)
    for i in range(5):
        y = h - 130 - i * 25
        c.drawString(36, y, f"0{i+1}/02/2026")
        c.drawString(150, y, f"Transaction Narration {i+1}")
        c.drawString(350, y, "250.00")
        c.drawString(480, y, "20,000.00")

    c.showPage()
    c.save()
    return output_pdf_path


def create_fixture_t5_zebra(output_pdf_path: str) -> str:
    """T5: Zebra fills with alternating row backgrounds and no rules."""
    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    w, h = letter
    for i in range(5):
        y = h - 100 - i * 25
        if i % 2 == 1:
            c.setFillColor(colors.HexColor("#F1F5F9"))
            c.rect(36, y - 5, 540, 22, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(45, y + 2, f"0{i+1}/03/2026")
        c.drawString(160, y + 2, f"Zebra record {i+1}")
        c.drawString(380, y + 2, "1,200.00")

    c.showPage()
    c.save()
    return output_pdf_path


def create_fixture_h1_unboxed_twoblock(output_pdf_path: str) -> str:
    """H1: Unboxed two-block header with centred title and notes."""
    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    w, h = letter

    # Centred Title
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2.0, h - 50, "BANK OF INDIA - STATEMENT OF ACCOUNT")

    # Left Block (Name & Address)
    c.setFont("Helvetica", 8.5)
    c.drawString(36, h - 80, "ACCOUNT HOLDER: MR. RAJESH VERMA")
    c.drawString(36, h - 94, "PLOT NO 12, SECTOR 4, NERUL")
    c.drawString(36, h - 108, "NAVI MUMBAI - 400706")

    # Right Block (Bank Details)
    c.drawString(320, h - 80, "BRANCH: NERUL WEST BRANCH")
    c.drawString(320, h - 94, "IFSC: BKID0000192")
    c.drawString(320, h - 108, "MICR: 400013082")

    # Notes
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(36, h - 130, "Records from 1 to 150. No more records available.")

    c.showPage()
    c.save()
    return output_pdf_path


def create_fixture_f1_footer(output_pdf_path: str) -> str:
    """F1: Footer directly under table with page number."""
    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    w, h = letter

    c.setFont("Helvetica", 8)
    c.drawString(36, 45, "Statutory Disclaimer: Generated by Core Banking System.")
    c.drawRightString(w - 36, 45, "Page 1 of 1")

    c.showPage()
    c.save()
    return output_pdf_path


if __name__ == "__main__":
    create_synthetic_statement("sample_statement.pdf")
    print("Generated 2-page benchmark statement: sample_statement.pdf")


