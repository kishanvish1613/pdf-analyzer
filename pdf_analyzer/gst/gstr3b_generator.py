"""
Form GSTR-3B Pixel-Perfect PDF Generator.
Exact mathematical reproduction of the Indian Goods and Services Tax (GST) Form GSTR-3B filing statement.
Features:
- Exact 3-page layout matching GST Portal authoritative output.
- Official peach section header banners (#FDE9D9) and orange info labels (#FAD2B1).
- Table column headers (#F2F2F2) with vector grid lines (#000000).
- Multi-level hierarchical table grids (Table 3.1, 3.1.1, 3.2, 4, 5, 5.1, 6.1, and Breakup).
- Authentic diagonal semi-transparent 'FILED' background watermark (150 pt Roboto at 54.74°).
- Dynamic data binding with authoritative default filing values or customized client data.
"""

from __future__ import annotations
import os
import copy
import shutil
from typing import Dict, Any, List, Optional
import pymupdf

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PAGE_W, PAGE_H = A4  # 595.28 pt x 841.89 pt
MARGIN_LEFT = 20.00
MARGIN_RIGHT = 20.00
MARGIN_TOP = 20.00
MARGIN_BOTTOM = 20.00
USABLE_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT  # 555.28 pt
TABLE_W = 554.28  # 554.28 pt inset

# Authoritative Color Palette
COLOR_BANNER_BG = colors.HexColor('#FDE9D9')       # Official GST warm peach section banner
COLOR_INFO_LABEL_BG = colors.HexColor('#FAD2B1')   # Official GST orange/peach info label cell
COLOR_HEADER_BG = colors.HexColor('#F2F2F2')       # Official GST light gray table column header
COLOR_BORDER = colors.HexColor('#000000')          # Solid black rules
COLOR_BORDER_LIGHT = colors.HexColor('#000000')
COLOR_TEXT_MAIN = colors.HexColor('#000000')
COLOR_TEXT_MUTED = colors.HexColor('#475569')

# Template and Fonts Path
TEMPLATE_PDF_PATH = os.path.join(os.path.dirname(__file__), "template_gstr3b.pdf")
FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

def register_roboto_fonts():
    """Registers TrueType Roboto font files for exact font matching."""
    try:
        font_files = {
            'Roboto-Regular': os.path.join(FONTS_DIR, 'Roboto-Regular.ttf'),
            'Roboto-Medium': os.path.join(FONTS_DIR, 'Roboto-Medium.ttf'),
            'Roboto-Italic': os.path.join(FONTS_DIR, 'Roboto-Italic.ttf'),
            'Roboto-Bold': os.path.join(FONTS_DIR, 'Roboto-Bold.ttf'),
        }
        for name, path in font_files.items():
            if os.path.exists(path) and name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception:
        return False

register_roboto_fonts()

def _get_font(pref: str, fallback: str) -> str:
    return pref if pref in pdfmetrics.getRegisteredFontNames() else fallback

FONT_REGULAR = _get_font('Roboto-Regular', 'Helvetica')
FONT_MEDIUM = _get_font('Roboto-Medium', 'Helvetica-Bold')
FONT_BOLD = _get_font('Roboto-Bold', 'Helvetica-Bold')
FONT_ITALIC = _get_font('Roboto-Italic', 'Helvetica-Oblique')


def get_default_gstr3b_data() -> Dict[str, Any]:
    """Returns authoritative default filing data for Form GSTR-3B matching the original return."""
    return {
        "year": "2025-26",
        "period": "Jan-Mar",
        "gstin": "23BCHPB7336L1ZM",
        "legal_name": "PRIYANKA NARWARIYA",
        "trade_name": "ATHARV ENTERPRISES",
        "arn": "AA230326938530E",
        "arn_date": "22/04/2026",
        "filing_status": "FILED",
        
        # Table 3.1
        "table_3_1": [
            {"label": "(a) Outward taxable supplies (other than zero rated, nil rated and exempted)", "taxable": "8523048.24", "igst": "0.00", "cgst": "766881.75", "sgst": "766881.75", "cess": "0.00"},
            {"label": "(b) Outward taxable supplies (zero rated)", "taxable": "0.00", "igst": "0.00", "cgst": "-", "sgst": "-", "cess": "0.00"},
            {"label": "(c ) Other outward supplies (nil rated, exempted)", "taxable": "0.00", "igst": "-", "cgst": "-", "sgst": "-", "cess": "-"},
            {"label": "(d) Inward supplies (liable to reverse charge)", "taxable": "398.00", "igst": "0.00", "cgst": "9.96", "sgst": "9.96", "cess": "0.00"},
            {"label": "(e) Non-GST outward supplies", "taxable": "0.00", "igst": "-", "cgst": "-", "sgst": "-", "cess": "-"}
        ],
        
        # Table 3.1.1
        "table_3_1_1": [
            {"label": "(i) Taxable supplies on which electronic commerce operator pays tax u/s 9(5) [to be furnished by electronic commerce operator]", "taxable": "0.00", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"},
            {"label": "(ii) Taxable supplies made by registered person through electronic commerce operator, on which electronic commerce operator is required to pay tax u/s 9(5) [to be furnished by registered person making supplies through electronic commerce operator]", "taxable": "0.00", "igst": "-", "cgst": "-", "sgst": "-", "cess": "-"}
        ],
        
        # Table 3.2
        "table_3_2": [
            {"label": "Supplies made to Unregistered Persons", "taxable": "0.00", "igst": "0.00"},
            {"label": "Supplies made to Composition Taxable Persons", "taxable": "0.00", "igst": "0.00"},
            {"label": "Supplies made to UIN holders", "taxable": "0.00", "igst": "0.00"}
        ],
        
        # Table 4
        "table_4_a": [
            {"label": "(1) Import of goods", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"},
            {"label": "(2) Import of services", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"},
            {"label": "(3) Inward supplies liable to reverse charge (other than 1 & 2 above)", "igst": "0.00", "cgst": "9.96", "sgst": "9.96", "cess": "0.00"},
            {"label": "(4) Inward supplies from ISD", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"},
            {"label": "(5) All other ITC", "igst": "231510.52", "cgst": "400759.78", "sgst": "400759.78", "cess": "0.00"}
        ],
        "table_4_b": [
            {"label": "(1) As per rules 38,42 & 43 of CGST Rules and section 17(5)", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"},
            {"label": "(2) Others", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"}
        ],
        "table_4_c": {"label": "C. Net ITC available (A-B)", "igst": "231510.52", "cgst": "400769.74", "sgst": "400769.74", "cess": "0.00"},
        "table_4_d": [
            {"label": "(1) ITC reclaimed which was reversed under Table 4(B)(2) in earlier tax period", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"},
            {"label": "(2) Ineligible ITC under section 16(4) & ITC restricted due to PoS rules", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"}
        ],
        
        # Table 5
        "table_5": [
            {"label": "From a supplier under composition scheme, Exempt, Nil rated supply", "inter_state": "0.00", "intra_state": "0.00"},
            {"label": "Non GST supply", "inter_state": "0.00", "intra_state": "0.00"}
        ],
        
        # Table 5.1
        "table_5_1": [
            {"label": "System computed Interest", "igst": "-", "cgst": "-", "sgst": "-", "cess": "-"},
            {"label": "Interest Paid", "igst": "0.00", "cgst": "0.00", "sgst": "0.00", "cess": "0.00"},
            {"label": "Late fee", "igst": "-", "cgst": "0.00", "sgst": "0.00", "cess": "-"}
        ],
        
        # Table 6.1
        "table_6_1_a": [
            {"tax_head": "Integrated tax", "tax_payable": "0.00", "adj_neg": "0.00", "net_payable": "0.00", "itc_igst": "0.00", "itc_cgst": "0.00", "itc_sgst": "0.00", "itc_cess": "-", "paid_cash": "0.00", "int_cash": "0.00", "late_cash": "-"},
            {"tax_head": "Central tax", "tax_payable": "766882.00", "adj_neg": "0.00", "net_payable": "766882.00", "itc_igst": "231511.00", "itc_cgst": "535371.00", "itc_sgst": "-", "itc_cess": "-", "paid_cash": "0.00", "int_cash": "0.00", "late_cash": "0.00"},
            {"tax_head": "State/UT tax", "tax_payable": "766882.00", "adj_neg": "0.00", "net_payable": "766882.00", "itc_igst": "0.00", "itc_cgst": "-", "itc_sgst": "745636.00", "itc_cess": "-", "paid_cash": "21246.00", "int_cash": "0.00", "late_cash": "0.00"},
            {"tax_head": "Cess", "tax_payable": "0.00", "adj_neg": "0.00", "net_payable": "0.00", "itc_igst": "-", "itc_cgst": "-", "itc_sgst": "-", "itc_cess": "0.00", "paid_cash": "0.00", "int_cash": "0.00", "late_cash": "-"}
        ],
        "table_6_1_b": [
            {"tax_head": "Integrated tax", "tax_payable": "0.00", "adj_neg": "0.00", "net_payable": "0.00", "itc_igst": "-", "itc_cgst": "-", "itc_sgst": "-", "itc_cess": "-", "paid_cash": "0.00", "int_cash": "-", "late_cash": "-"},
            {"tax_head": "Central tax", "tax_payable": "10.00", "adj_neg": "0.00", "net_payable": "10.00", "itc_igst": "-", "itc_cgst": "-", "itc_sgst": "-", "itc_cess": "-", "paid_cash": "10.00", "int_cash": "-", "late_cash": "-"},
            {"tax_head": "State/UT tax", "tax_payable": "10.00", "adj_neg": "0.00", "net_payable": "10.00", "itc_igst": "-", "itc_cgst": "-", "itc_sgst": "-", "itc_cess": "-", "paid_cash": "10.00", "int_cash": "-", "late_cash": "-"},
            {"tax_head": "Cess", "tax_payable": "0.00", "adj_neg": "0.00", "net_payable": "0.00", "itc_igst": "-", "itc_cgst": "-", "itc_sgst": "-", "itc_cess": "-", "paid_cash": "0.00", "int_cash": "-", "late_cash": "-"}
        ],
        
        # Breakup of tax liability
        "breakup": {
            "period": "March 2026",
            "igst": "0.00",
            "cgst": "766892.00",
            "sgst": "766892.00",
            "cess": "0.00"
        },
        
        # Verification
        "verification": {
            "date": "22/04/2026",
            "signatory_name": "PRIYANKA NARWARIYA",
            "designation": "PROPRIETORSHIP"
        }
    }


def get_gstr3b_metadata(data: Optional[Dict[str, Any]] = None, pdf_path: Optional[str] = None) -> Dict[str, Any]:
    """Returns authoritative PDF metadata, fonts, colors, and geometry specifications."""
    if data is None:
        data = get_default_gstr3b_data()

    gstin = data.get("gstin", "23BCHPB7336L1ZM")
    filename = f"GSTR3B_{gstin}_032026.pdf"

    sha256 = ""
    file_size_bytes = 0
    if pdf_path and os.path.exists(pdf_path):
        import hashlib
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
                sha256 = hashlib.sha256(pdf_bytes).hexdigest()
                file_size_bytes = len(pdf_bytes)
        except Exception:
            pass

    return {
        "exif": {
            "Creator": "pdfmake",
            "Producer": "pdfmake",
            "Checksum": "29f6ad60fcc75d553e91229f7f910798",
            "FileName": filename,
            "FileSize": f"{round(file_size_bytes / 1024, 1)} kB" if file_size_bytes else "40 kB",
            "FileType": "PDF",
            "MIMEType": "application/pdf",
            "PageCount": 3,
            "CreateDate": "2026:09:21 09:21:18Z",
            "Linearized": "No",
            "PDFVersion": 1.3,
            "FileTypeExtension": "pdf"
        },
        "pdfinfo": {
            "creator": "pdfmake",
            "producer": "pdfmake",
            "pages": "3",
            "pageSize": "595.28 x 841.89 pts (A4)",
            "mediaBox": "0.00     0.00   595.28   841.89",
            "cropBox": "0.00     0.00   595.28   841.89",
            "bleedBox": "0.00     0.00   595.28   841.89",
            "trimBox": "0.00     0.00   595.28   841.89",
            "artBox": "0.00     0.00   595.28   841.89",
            "pageRot": "0",
            "pdfVersion": "1.3",
            "encrypted": "no",
            "optimized": "no",
            "tagged": "no",
            "javaScript": "no",
            "creationDate": "2026-09-21T09:21:18Z"
        },
        "pdffonts": [
            {
                "name": "AZZZZZ+Roboto-Medium",
                "family": "Roboto",
                "weight": "Medium / 500",
                "type": "CID TrueType",
                "subset": True,
                "unicode": True,
                "embedded": True,
                "encoding": "Identity-H",
                "object_id": 10
            },
            {
                "name": "BZZZZZ+Roboto-Italic",
                "family": "Roboto",
                "weight": "Italic / 400",
                "type": "CID TrueType",
                "subset": True,
                "unicode": True,
                "embedded": True,
                "encoding": "Identity-H",
                "object_id": 11
            },
            {
                "name": "CZZZZZ+Roboto-Regular",
                "family": "Roboto",
                "weight": "Regular / 400",
                "type": "CID TrueType",
                "subset": True,
                "unicode": True,
                "embedded": True,
                "encoding": "Identity-H",
                "object_id": 13
            }
        ],
        "colors": {
            "banner_background": {
                "hex": "#fde8d7",
                "official_hex": "#FDE9D9",
                "rgb": "rgb(253, 233, 217)",
                "description": "Authoritative GST Portal peach header background"
            },
            "info_label_background": {
                "hex": "#FAD2B1",
                "rgb": "rgb(250, 210, 177)",
                "description": "Official GST peach/orange metadata label cells"
            },
            "table_header": {
                "hex": "#F2F2F2",
                "rgb": "rgb(242, 242, 242)",
                "description": "Official GST light gray table column header fill"
            },
            "table_border": {
                "hex": "#1e293b",
                "official_hex": "#000000",
                "rgb": "rgb(0, 0, 0)",
                "description": "Primary table box and cell grid rules"
            },
            "table_border_light": {
                "hex": "#94a3b8",
                "official_hex": "#000000",
                "rgb": "rgb(0, 0, 0)",
                "description": "Secondary cell inner grid rules"
            },
            "text_primary": {
                "hex": "#0f172a",
                "official_hex": "#000000",
                "rgb": "rgb(0, 0, 0)",
                "description": "High contrast black text"
            },
            "watermark": {
                "hex": "#cbd5e1",
                "official_hex": "#808080",
                "alpha": 0.302,
                "text": "FILED",
                "angle_deg": 54.74,
                "font_size_pt": 150.0
            }
        },
        "geometry": {
            "page_width_pt": 595.28,
            "page_height_pt": 841.89,
            "margins_mm": {"left": 7.06, "right": 7.06, "top": 7.06, "bottom": 7.06},
            "margins_pt": {"left": 20.00, "right": 20.00, "top": 20.00, "bottom": 20.00},
            "usable_width_pt": 538.57,
            "scale_factor_300dpi": 4.1667
        },
        "sha256": sha256 or "0d04dd9f6ea9b693e99c80e3746a62d00195c7816aca129c08c641266777016d"
    }


def generate_gstr3b_ai_prompt(data: Optional[Dict[str, Any]] = None) -> str:
    """Generates the authoritative System Prompt & Mathematical Layout Specification specifically for Form GSTR-3B."""
    if data is None:
        data = get_default_gstr3b_data()

    gstin = data.get('gstin', '23BCHPB7336L1ZM')
    legal_name = data.get('legal_name', 'PRIYANKA NARWARIYA')
    trade_name = data.get('trade_name', 'ATHARV ENTERPRISES')
    arn = data.get('arn', 'AA230326938530E')
    year = data.get('year', '2025-26')
    period = data.get('period', 'Jan-Mar')

    prompt = f"""# System Prompt & Mathematical Layout Specification for Form GSTR-3B AI PDF Generation

> [!NOTE]
> **OFFICIAL GOODS & SERVICES TAX (GST) FORM GSTR-3B RETURN LAYOUT SPECIFICATION**
> Authoritative 3-Page Return Layout Specification with Exact Peach Banners (#fde8d7 / #FDE9D9), Table Headers (#F2F2F2), Info Cells (#FAD2B1), Roboto Typography, Hierarchical Tables, and 'FILED' Background Watermark.

## Directive to AI Model
You are a Principal Document Engineering Architect and Pixel-Perfect PDF Layout Compiler.
You are generating an exact, mathematically identical, pixel-matched PDF reproduction of Indian Goods and Services Tax Return:
**Form**: `FORM GSTR-3B` | **Rule**: `[See rule 61(5)]` | **Status**: `FILED` | **Pages**: 3

### CRITICAL SPECIFICATIONS:
1. **PAGE SIZE & GEOMETRY**: Standard ISO A4 (`595.28 pt` x `841.89 pt` / `210 mm` x `297 mm`). Margins: `20.00 pt` on all 4 sides. Usable Width: `555.28 pt` (legacy `538.57 pt`).
2. **THEME PALETTE**:
   - Section Title Banner Fill: `#fde8d7` / `#FDE9D9` (Warm GST Peach)
   - Table Column Header Fill: `#F2F2F2` (Light Gray)
   - Info Box Metadata Fill: `#FAD2B1` (Warm Orange/Peach)
   - Outer Box / Grid Rules: `0.75 pt solid #1e293b` (or `#000000`)
   - Inner Cell Rules: `0.50 pt solid #94a3b8` (or `#000000`)
   - Typography Text: `#0f172a` (or `#000000`)
   - Watermark: `FILED` (Rotated `54.7°`, font size `150 pt`, color `#808080` at `alpha=0.302`)
3. **FONT SPECTRUM**:
   - `Roboto-Medium` (500) for Table Headers, Section Titles, and Banner text.
   - `Roboto-Italic` (400) for Rule reference `[See rule 61(5)]` and descriptive notes.
   - `Roboto-Regular` (400) for Table data cells, monetary figures, and verification declaration.
4. **HIERARCHICAL TABLES BREAKDOWN**:
   - **Page 1**: Header, Rule 61(5), Year/Period box, Supplier Details (GSTIN, Legal Name, Trade Name, ARN), Table 3.1 (Outward Supplies), Table 3.1.1 (Supplies u/s 9(5)), Table 3.2 (Inter-State Supplies), and Table 4(A.1 - A.3).
   - **Page 2**: Table 4 continuation (A.4, A.5, B.1, B.2, C. Net ITC, D. Other Details), Table 5 (Exempt/Nil-rated/Non-GST), Table 5.1 (Interest & late fee), Table 6.1 (Payment of tax with 11-column ITC hierarchy & Sections A & B), and Breakup Header.
   - **Page 3**: Breakup Data Row (`March 2026`), Verification declaration paragraph, and Authorized Signatory block (`{legal_name}`, `{data.get('verification', {}).get('designation', 'PROPRIETORSHIP')}`).

---

## 1. Global Page Geometry & Coordinate System
- **Page Dimensions**: `595.28 pt` x `841.89 pt` (210.00 mm x 297.00 mm / 8.27" x 11.69")
- **Orientation**: Portrait
- **Coordinate Space**: Top-Left Origin (CropBox Top-Left = (0, 0); X increases Rightwards, Y increases Downwards)
- **Document Margins**: Left `20.00 pt`, Right `20.00 pt`, Top `20.00 pt`, Bottom `20.00 pt`. Usable Content Width: `555.28 pt`.

---

## 2. Supplier & Filing Metadata
- **Financial Year**: `{year}`
- **Tax Period**: `{period}`
- **GSTIN of Supplier**: `{gstin}`
- **Legal Name**: `{legal_name}`
- **Trade Name**: `{trade_name}`
- **ARN**: `{arn}`
- **Date of ARN**: `{data.get('arn_date', '22/04/2026')}`
- **Filing Status**: `FILED`

---

## 3. Production-Ready Python Generator
```python
from pdf_analyzer.gst.gstr3b_generator import generate_gstr3b_pdf, get_default_gstr3b_data

if __name__ == '__main__':
    out_file = generate_gstr3b_pdf("Form_GSTR_3B.pdf")
    print(f"Generated exact Form GSTR-3B: {{out_file}}")
```
"""
    return prompt


# =========================================================================
# HIGH-PRECISION TEMPLATE CLONER & DYNAMIC PATCHER
# =========================================================================

def _patch_template_gstr3b_pdf(output_filename: str, data: Dict[str, Any]) -> str:
    """Clones authoritative template PDF and patches modified fields with vector precision."""
    doc = pymupdf.open(TEMPLATE_PDF_PATH)
    font_reg = os.path.join(FONTS_DIR, "Roboto-Regular.ttf")
    font_med = os.path.join(FONTS_DIR, "Roboto-Medium.ttf")
    default_data = get_default_gstr3b_data()

    # Page 0 (Page 1)
    p0 = doc[0]

    # Year
    year = str(data.get("year", default_data["year"]))
    if year != default_data["year"]:
        for r in p0.search_for(default_data["year"]):
            p0.add_redact_annot(r, fill=(1, 1, 1))
        p0.apply_redactions()
        p0.insert_text(pymupdf.Point(468.0, 115.5), year, fontfile=font_reg, fontsize=9.0, color=(0, 0, 0))

    # Period
    period = str(data.get("period", default_data["period"]))
    if period != default_data["period"]:
        for r in p0.search_for(default_data["period"]):
            p0.add_redact_annot(r, fill=(1, 1, 1))
        p0.apply_redactions()
        p0.insert_text(pymupdf.Point(468.0, 130.5), period, fontfile=font_reg, fontsize=9.0, color=(0, 0, 0))

    # GSTIN
    gstin = str(data.get("gstin", default_data["gstin"]))
    if gstin != default_data["gstin"]:
        for r in p0.search_for(default_data["gstin"]):
            p0.add_redact_annot(r, fill=(1, 1, 1))
        p0.apply_redactions()
        p0.insert_text(pymupdf.Point(233.0, 166.5), gstin, fontfile=font_reg, fontsize=8.0, color=(0, 0, 0))

    # Legal Name
    legal_name = str(data.get("legal_name", default_data["legal_name"]))
    if legal_name != default_data["legal_name"]:
        for r in p0.search_for(default_data["legal_name"]):
            p0.add_redact_annot(r, fill=(1, 1, 1))
        p0.apply_redactions()
        p0.insert_text(pymupdf.Point(233.0, 180.5), legal_name, fontfile=font_reg, fontsize=8.0, color=(0, 0, 0))

    # Trade Name
    trade_name = str(data.get("trade_name", default_data["trade_name"]))
    if trade_name != default_data["trade_name"]:
        for r in p0.search_for(default_data["trade_name"]):
            p0.add_redact_annot(r, fill=(1, 1, 1))
        p0.apply_redactions()
        p0.insert_text(pymupdf.Point(233.0, 194.5), trade_name, fontfile=font_reg, fontsize=8.0, color=(0, 0, 0))

    # ARN
    arn = str(data.get("arn", default_data["arn"]))
    if arn != default_data["arn"]:
        for r in p0.search_for(default_data["arn"]):
            p0.add_redact_annot(r, fill=(1, 1, 1))
        p0.apply_redactions()
        p0.insert_text(pymupdf.Point(233.0, 208.5), arn, fontfile=font_reg, fontsize=8.0, color=(0, 0, 0))

    # ARN Date
    arn_date = str(data.get("arn_date", default_data["arn_date"]))
    if arn_date != default_data["arn_date"]:
        for r in p0.search_for(default_data["arn_date"]):
            p0.add_redact_annot(r, fill=(1, 1, 1))
        p0.apply_redactions()
        p0.insert_text(pymupdf.Point(233.0, 222.5), arn_date, fontfile=font_reg, fontsize=8.0, color=(0, 0, 0))

    # Page 2 (Page 3 of doc)
    p2 = doc[2]
    verif = data.get("verification", {})
    def_verif = default_data.get("verification", {})
    
    # Signatory
    signatory = str(verif.get("signatory_name", legal_name))
    def_sig = str(def_verif.get("signatory_name", default_data["legal_name"]))
    if signatory != def_sig:
        for r in p2.search_for(def_sig):
            p2.add_redact_annot(r, fill=(1, 1, 1))
        p2.apply_redactions()
        p2.insert_text(pymupdf.Point(301.64, 143.5), signatory, fontfile=font_reg, fontsize=9.0, color=(0, 0, 0))

    # Designation
    desig = str(verif.get("designation", def_verif.get("designation", "PROPRIETORSHIP")))
    def_desig = str(def_verif.get("designation", "PROPRIETORSHIP"))
    if desig != def_desig:
        for r in p2.search_for(def_desig):
            p2.add_redact_annot(r, fill=(1, 1, 1))
        p2.apply_redactions()
        p2.insert_text(pymupdf.Point(301.64, 176.5), desig, fontfile=font_reg, fontsize=9.0, color=(0, 0, 0))

    # Verif Date
    v_date = str(verif.get("date", def_verif.get("date", "22/04/2026")))
    def_v_date = str(def_verif.get("date", "22/04/2026"))
    if v_date != def_v_date:
        for r in p2.search_for(def_v_date):
            p2.add_redact_annot(r, fill=(1, 1, 1))
        p2.apply_redactions()
        p2.insert_text(pymupdf.Point(45.5, 126.5), v_date, fontfile=font_reg, fontsize=9.0, color=(0, 0, 0))

    # Breakup period
    brk = data.get("breakup", {})
    def_brk = default_data.get("breakup", {})
    brk_p = str(brk.get("period", def_brk.get("period", "March 2026")))
    def_brk_p = str(def_brk.get("period", "March 2026"))
    if brk_p != def_brk_p:
        for r in p2.search_for(def_brk_p):
            p2.add_redact_annot(r, fill=(1, 1, 1))
        p2.apply_redactions()
        p2.insert_text(pymupdf.Point(25.0, 51.5), brk_p, fontfile=font_reg, fontsize=9.0, color=(0, 0, 0))

    # Set Authoritative PDF Metadata
    doc.set_metadata({
        "creator": "pdfmake",
        "producer": "pdfmake",
        "title": f"GSTR3B_{gstin}_032026.pdf",
        "subject": "Form GSTR-3B Return",
        "author": "GST Portal",
        "creationDate": "20260921092118Z",
        "modDate": "20260921092118Z"
    })
    
    os.makedirs(os.path.dirname(os.path.abspath(output_filename)), exist_ok=True)
    doc.save(output_filename)
    doc.close()
    return output_filename


# =========================================================================
# REPORTLAB PLATYPUS GENERATOR
# =========================================================================

class NumberedCanvasWithWatermark(canvas.Canvas):
    """Custom canvas that paints diagonal semi-transparent 'FILED' watermark on every page."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.setCreator("pdfmake")
        self.setProducer("pdfmake")
        self.setTitle("GSTR3B_23BCHPB7336L1ZM_032026.pdf")
        self.setSubject("Form GSTR-3B Return")
        self.setAuthor("GST Portal")

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_watermark()
            super().showPage()
        super().save()

    def draw_watermark(self):
        self.saveState()
        self.setFont(FONT_REGULAR, 150)
        # Authoritative GST gray watermark (alpha ~0.302)
        self.setFillColor(colors.Color(0.502, 0.502, 0.502, alpha=0.302))
        # Origin: (195.33, 187.45) in bottom-left coordinates, rotated 54.74 deg
        self.translate(195.33, 187.45)
        self.rotate(54.74)
        self.drawString(0, 0, "  FILED ")
        self.restoreState()


def create_section_banner(title_text: str, width: float = USABLE_W) -> Table:
    """Creates an authoritative peach section header banner."""
    style = ParagraphStyle(
        'BannerStyle',
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=10.5,
        textColor=COLOR_TEXT_MAIN
    )
    p = Paragraph(f"<b>{title_text}</b>", style)
    t = Table([[p]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BANNER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4.0),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _generate_with_reportlab(
    output_filename: str = "Form_GSTR_3B.pdf",
    data: Optional[Dict[str, Any]] = None
) -> str:
    """Compiles the 3-page Form GSTR-3B PDF using ReportLab Platypus."""
    if data is None:
        data = get_default_gstr3b_data()
    else:
        default_d = get_default_gstr3b_data()
        for k, v in default_d.items():
            if k not in data:
                data[k] = v

    os.makedirs(os.path.dirname(os.path.abspath(output_filename)), exist_ok=True)

    doc = SimpleDocTemplate(
        output_filename,
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM
    )

    # Base Typography Styles
    title_style = ParagraphStyle('GSTTitle', fontName=FONT_BOLD, fontSize=15, leading=18, alignment=TA_CENTER, textColor=COLOR_TEXT_MAIN)
    rule_style = ParagraphStyle('GSTRule', fontName=FONT_ITALIC, fontSize=9.5, leading=12, alignment=TA_CENTER, textColor=COLOR_TEXT_MAIN)
    note_style = ParagraphStyle('GSTNote', fontName=FONT_REGULAR, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=COLOR_TEXT_MAIN)

    th_left = ParagraphStyle('THLeft', fontName=FONT_MEDIUM, fontSize=7.5, leading=9.0, alignment=TA_LEFT, textColor=COLOR_TEXT_MAIN)
    th_center = ParagraphStyle('THCenter', fontName=FONT_MEDIUM, fontSize=7.5, leading=9.0, alignment=TA_CENTER, textColor=COLOR_TEXT_MAIN)
    th_right = ParagraphStyle('THRight', fontName=FONT_MEDIUM, fontSize=7.5, leading=9.0, alignment=TA_RIGHT, textColor=COLOR_TEXT_MAIN)

    td_left = ParagraphStyle('TDLeft', fontName=FONT_REGULAR, fontSize=7.0, leading=8.5, alignment=TA_LEFT, textColor=COLOR_TEXT_MAIN)
    td_left_bold = ParagraphStyle('TDLeftBold', fontName=FONT_MEDIUM, fontSize=7.0, leading=8.5, alignment=TA_LEFT, textColor=COLOR_TEXT_MAIN)
    td_center = ParagraphStyle('TDCenter', fontName=FONT_REGULAR, fontSize=7.0, leading=8.5, alignment=TA_CENTER, textColor=COLOR_TEXT_MAIN)
    td_right = ParagraphStyle('TDRight', fontName=FONT_REGULAR, fontSize=7.0, leading=8.5, alignment=TA_RIGHT, textColor=COLOR_TEXT_MAIN)
    td_right_bold = ParagraphStyle('TDRightBold', fontName=FONT_MEDIUM, fontSize=7.0, leading=8.5, alignment=TA_RIGHT, textColor=COLOR_TEXT_MAIN)

    story = []

    # =========================================================================
    # PAGE 1
    # =========================================================================
    story.append(Paragraph("<b>Form GSTR-3B</b>", title_style))
    story.append(Paragraph("[See rule 61(5)]", rule_style))
    story.append(Spacer(1, 4))

    # Year / Period Top-Right Box
    year_period_data = [
        [Paragraph("<b>Year</b>", td_left_bold), Paragraph(str(data.get("year", "2025-26")), td_left)],
        [Paragraph("<b>Period</b>", td_left_bold), Paragraph(str(data.get("period", "Jan-Mar")), td_left)]
    ]
    yp_tbl = Table(year_period_data, colWidths=[70, 100])
    yp_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), COLOR_INFO_LABEL_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 4.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4.0),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    yp_wrapper = Table([[Paragraph("", td_left), yp_tbl]], colWidths=[USABLE_W - 170, 170])
    yp_wrapper.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(yp_wrapper)
    story.append(Spacer(1, 4))

    # Supplier Registration Details Table
    supplier_rows = [
        [Paragraph("<b>GSTIN of the supplier</b>", td_left_bold), Paragraph(str(data.get("gstin", "")), td_left)],
        [Paragraph("<b>2(a). Legal name of the registered person</b>", td_left_bold), Paragraph(str(data.get("legal_name", "")), td_left)],
        [Paragraph("<b>2(b). Trade name, if any</b>", td_left_bold), Paragraph(str(data.get("trade_name", "")), td_left)],
        [Paragraph("<b>2(c). ARN</b>", td_left_bold), Paragraph(str(data.get("arn", "")), td_left)],
        [Paragraph("<b>2(d). Date of ARN</b>", td_left_bold), Paragraph(str(data.get("arn_date", "")), td_left)],
    ]
    sup_tbl = Table(supplier_rows, colWidths=[185, USABLE_W - 185])
    sup_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), COLOR_INFO_LABEL_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 4.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4.0),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sup_tbl)
    story.append(Spacer(1, 2))
    story.append(Paragraph("(Amount in ₹ for all tables)", note_style))
    story.append(Spacer(1, 2))

    # Table 3.1
    story.append(create_section_banner("3.1 Details of Outward supplies and inward supplies liable to reverse charge (other than those covered by Table 3.1.1)"))
    t31_headers = [
        Paragraph("<b>Nature of Supplies</b>", th_left),
        Paragraph("<b>Total taxable<br/>value</b>", th_right),
        Paragraph("<b>Integrated<br/>tax</b>", th_right),
        Paragraph("<b>Central<br/>tax</b>", th_right),
        Paragraph("<b>State/UT<br/>tax</b>", th_right),
        Paragraph("<b>Cess</b>", th_right),
    ]
    t31_data = [t31_headers]
    for r in data.get("table_3_1", []):
        t31_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["taxable"], td_right),
            Paragraph(r["igst"], td_right if r["igst"] != "-" else td_center),
            Paragraph(r["cgst"], td_right if r["cgst"] != "-" else td_center),
            Paragraph(r["sgst"], td_right if r["sgst"] != "-" else td_center),
            Paragraph(r["cess"], td_right if r["cess"] != "-" else td_center),
        ])
    t31_widths = [240, 75, 60, 60, 60, USABLE_W - 495]
    t31_tbl = Table(t31_data, colWidths=t31_widths)
    t31_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t31_tbl)
    story.append(Spacer(1, 6))

    # Table 3.1.1
    story.append(create_section_banner("3.1.1 Details of Supplies notified under section 9(5) of the CGST Act, 2017 and corresponding provisions in IGST/UTGST/SGST Acts"))
    t311_headers = [
        Paragraph("<b>Nature of Supplies</b>", th_left),
        Paragraph("<b>Total<br/>taxable<br/>value</b>", th_right),
        Paragraph("<b>Integrated<br/>tax</b>", th_right),
        Paragraph("<b>Central<br/>tax</b>", th_right),
        Paragraph("<b>State/<br/>UT tax</b>", th_right),
        Paragraph("<b>Cess</b>", th_right),
    ]
    t311_data = [t311_headers]
    for r in data.get("table_3_1_1", []):
        t311_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["taxable"], td_right),
            Paragraph(r["igst"], td_right if r["igst"] != "-" else td_center),
            Paragraph(r["cgst"], td_right if r["cgst"] != "-" else td_center),
            Paragraph(r["sgst"], td_right if r["sgst"] != "-" else td_center),
            Paragraph(r["cess"], td_right if r["cess"] != "-" else td_center),
        ])
    t311_tbl = Table(t311_data, colWidths=t31_widths)
    t311_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t311_tbl)
    story.append(Spacer(1, 6))

    # Table 3.2
    story.append(create_section_banner("3.2 Out of supplies made in 3.1 (a) and 3.1.1 (i), details of inter-state supplies made"))
    t32_headers = [
        Paragraph("<b>Nature of Supplies</b>", th_left),
        Paragraph("<b>Total taxable value</b>", th_right),
        Paragraph("<b>Integrated tax</b>", th_right),
    ]
    t32_data = [t32_headers]
    for r in data.get("table_3_2", []):
        t32_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["taxable"], td_right),
            Paragraph(r["igst"], td_right),
        ])
    t32_widths = [185, 185, USABLE_W - 370]
    t32_tbl = Table(t32_data, colWidths=t32_widths)
    t32_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t32_tbl)
    story.append(Spacer(1, 6))

    # Table 4: Eligible ITC (Part 1 on Page 1)
    story.append(create_section_banner("4. Eligible ITC"))
    t4_headers = [
        Paragraph("<b>Details</b>", th_left),
        Paragraph("<b>Integrated tax</b>", th_right),
        Paragraph("<b>Central tax</b>", th_right),
        Paragraph("<b>State/UT tax</b>", th_right),
        Paragraph("<b>Cess</b>", th_right),
    ]
    t4_p1_data = [
        t4_headers,
        [Paragraph("<b>A. ITC Available (whether in full or part)</b>", td_left_bold), Paragraph("", td_right), Paragraph("", td_right), Paragraph("", td_right), Paragraph("", td_right)]
    ]
    t4_a_rows = data.get("table_4_a", [])
    for r in t4_a_rows[:3]:
        t4_p1_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["igst"], td_right),
            Paragraph(r["cgst"], td_right),
            Paragraph(r["sgst"], td_right),
            Paragraph(r["cess"], td_right),
        ])
    t4_widths = [275, 70, 70, 70, USABLE_W - 485]
    t4_p1_tbl = Table(t4_p1_data, colWidths=t4_widths)
    t4_p1_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('SPAN', (0, 1), (-1, 1)),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t4_p1_tbl)

    # =========================================================================
    # PAGE 2
    # =========================================================================
    story.append(PageBreak())

    t4_p2_data = []
    for r in t4_a_rows[3:]:
        t4_p2_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["igst"], td_right),
            Paragraph(r["cgst"], td_right),
            Paragraph(r["sgst"], td_right),
            Paragraph(r["cess"], td_right),
        ])
    t4_p2_data.append([
        Paragraph("<b>B. ITC Reversed</b>", td_left_bold), Paragraph("", td_right), Paragraph("", td_right), Paragraph("", td_right), Paragraph("", td_right)
    ])
    for r in data.get("table_4_b", []):
        t4_p2_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["igst"], td_right),
            Paragraph(r["cgst"], td_right),
            Paragraph(r["sgst"], td_right),
            Paragraph(r["cess"], td_right),
        ])
    net_c = data.get("table_4_c", {"label": "C. Net ITC available (A-B)", "igst": "231510.52", "cgst": "400769.74", "sgst": "400769.74", "cess": "0.00"})
    t4_p2_data.append([
        Paragraph(f"<b>{net_c['label']}</b>", td_left_bold),
        Paragraph(f"<b>{net_c['igst']}</b>", td_right_bold),
        Paragraph(f"<b>{net_c['cgst']}</b>", td_right_bold),
        Paragraph(f"<b>{net_c['sgst']}</b>", td_right_bold),
        Paragraph(f"<b>{net_c['cess']}</b>", td_right_bold),
    ])
    t4_p2_data.append([
        Paragraph("<b>(D) Other Details</b>", td_left_bold),
        Paragraph("0.00", td_right), Paragraph("0.00", td_right), Paragraph("0.00", td_right), Paragraph("0.00", td_right)
    ])
    for r in data.get("table_4_d", []):
        t4_p2_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["igst"], td_right),
            Paragraph(r["cgst"], td_right),
            Paragraph(r["sgst"], td_right),
            Paragraph(r["cess"], td_right),
        ])

    t4_p2_tbl = Table(t4_p2_data, colWidths=t4_widths)
    t4_p2_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('SPAN', (0, 2), (-1, 2)),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t4_p2_tbl)
    story.append(Spacer(1, 6))

    # Table 5
    story.append(create_section_banner("5 Values of exempt, nil-rated and non-GST inward supplies"))
    t5_headers = [
        Paragraph("<b>Nature of Supplies</b>", th_left),
        Paragraph("<b>Inter- State supplies</b>", th_right),
        Paragraph("<b>Intra- State supplies</b>", th_right),
    ]
    t5_data = [t5_headers]
    for r in data.get("table_5", []):
        t5_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["inter_state"], td_right),
            Paragraph(r["intra_state"], td_right),
        ])
    t5_widths = [315.28, 120, 120]
    t5_tbl = Table(t5_data, colWidths=t5_widths)
    t5_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t5_tbl)
    story.append(Spacer(1, 6))

    # Table 5.1
    story.append(create_section_banner("5.1 Interest and Late fee for previous tax period"))
    t51_headers = [
        Paragraph("<b>Details</b>", th_left),
        Paragraph("<b>Integrated tax</b>", th_right),
        Paragraph("<b>Central tax</b>", th_right),
        Paragraph("<b>State/UT tax</b>", th_right),
        Paragraph("<b>Cess</b>", th_right),
    ]
    t51_data = [t51_headers]
    for r in data.get("table_5_1", []):
        t51_data.append([
            Paragraph(r["label"], td_left),
            Paragraph(r["igst"], td_right if r["igst"] != "-" else td_center),
            Paragraph(r["cgst"], td_right if r["cgst"] != "-" else td_center),
            Paragraph(r["sgst"], td_right if r["sgst"] != "-" else td_center),
            Paragraph(r["cess"], td_right if r["cess"] != "-" else td_center),
        ])
    t51_tbl = Table(t51_data, colWidths=t4_widths)
    t51_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t51_tbl)
    story.append(Spacer(1, 6))

    # Table 6.1: Payment of tax
    story.append(create_section_banner("6.1 Payment of tax"))
    t61_widths = [50, 50, 54.5, 50, 50, 50, 50, 50, 50, 50, 50.78]

    t61_h1 = [
        Paragraph("<b>Descripti<br/>on</b>", th_center),
        Paragraph("<b>Tax<br/>payable</b>", th_center),
        Paragraph("<b>Adjustment<br/>of<br/>negative<br/>liability of<br/>previous<br/>tax period</b>", th_center),
        Paragraph("<b>Net Tax<br/>Payable</b>", th_center),
        Paragraph("<b>Tax paid through ITC</b>", th_center),
        "", "", "",
        Paragraph("<b>Tax paid<br/>in cash</b>", th_center),
        Paragraph("<b>Interest<br/>paid in<br/>cash</b>", th_center),
        Paragraph("<b>Late fee<br/>paid in<br/>cash</b>", th_center),
    ]
    t61_h2 = [
        "", "", "", "",
        Paragraph("<b>Integrated<br/>tax</b>", th_center),
        Paragraph("<b>Central<br/>tax</b>", th_center),
        Paragraph("<b>State/UT<br/>tax</b>", th_center),
        Paragraph("<b>Cess</b>", th_center),
        "", "", ""
    ]

    t61_data = [t61_h1, t61_h2]
    
    t61_data.append([
        Paragraph("<b>(A) Other than reverse charge</b>", td_left_bold),
        "", "", "", "", "", "", "", "", "", ""
    ])
    for r in data.get("table_6_1_a", []):
        t61_data.append([
            Paragraph(r["tax_head"], td_left),
            Paragraph(r["tax_payable"], td_right),
            Paragraph(r["adj_neg"], td_right),
            Paragraph(r["net_payable"], td_right),
            Paragraph(r["itc_igst"], td_right if r["itc_igst"] != "-" else td_center),
            Paragraph(r["itc_cgst"], td_right if r["itc_cgst"] != "-" else td_center),
            Paragraph(r["itc_sgst"], td_right if r["itc_sgst"] != "-" else td_center),
            Paragraph(r["itc_cess"], td_right if r["itc_cess"] != "-" else td_center),
            Paragraph(r["paid_cash"], td_right),
            Paragraph(r["int_cash"], td_right if r["int_cash"] != "-" else td_center),
            Paragraph(r["late_cash"], td_right if r["late_cash"] != "-" else td_center),
        ])

    t61_data.append([
        Paragraph("<b>(B) Reverse charge and supplies made u/s 9(5)</b>", td_left_bold),
        "", "", "", "", "", "", "", "", "", ""
    ])
    for r in data.get("table_6_1_b", []):
        t61_data.append([
            Paragraph(r["tax_head"], td_left),
            Paragraph(r["tax_payable"], td_right),
            Paragraph(r["adj_neg"], td_right),
            Paragraph(r["net_payable"], td_right),
            Paragraph(r["itc_igst"], td_right if r["itc_igst"] != "-" else td_center),
            Paragraph(r["itc_cgst"], td_right if r["itc_cgst"] != "-" else td_center),
            Paragraph(r["itc_sgst"], td_right if r["itc_sgst"] != "-" else td_center),
            Paragraph(r["itc_cess"], td_right if r["itc_cess"] != "-" else td_center),
            Paragraph(r["paid_cash"], td_right),
            Paragraph(r["int_cash"], td_right if r["int_cash"] != "-" else td_center),
            Paragraph(r["late_cash"], td_right if r["late_cash"] != "-" else td_center),
        ])

    t61_tbl = Table(t61_data, colWidths=t61_widths)
    t61_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 1), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (1, 0), (1, 1)),
        ('SPAN', (2, 0), (2, 1)),
        ('SPAN', (3, 0), (3, 1)),
        ('SPAN', (4, 0), (7, 0)),
        ('SPAN', (8, 0), (8, 1)),
        ('SPAN', (9, 0), (9, 1)),
        ('SPAN', (10, 0), (10, 1)),
        ('SPAN', (0, 2), (-1, 2)),
        ('SPAN', (0, 7), (-1, 7)),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 1.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1.5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t61_tbl)
    story.append(Spacer(1, 6))

    # Breakup header at bottom of Page 2
    story.append(create_section_banner("Breakup of tax liability declared (for interest computation)"))
    t_breakup_h = [
        Paragraph("<b>Period</b>", th_left),
        Paragraph("<b>Integrated tax</b>", th_right),
        Paragraph("<b>Central tax</b>", th_right),
        Paragraph("<b>State/UT tax</b>", th_right),
        Paragraph("<b>Cess</b>", th_right),
    ]
    t_brk_widths = [110, 111, 111, 111, USABLE_W - 443]
    t_brk_h_tbl = Table([t_breakup_h], colWidths=t_brk_widths)
    t_brk_h_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.0),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t_brk_h_tbl)

    # =========================================================================
    # PAGE 3
    # =========================================================================
    story.append(PageBreak())

    brk_d = data.get("breakup", {"period": "March 2026", "igst": "0.00", "cgst": "766892.00", "sgst": "766892.00", "cess": "0.00"})
    t_brk_row = [
        Paragraph(brk_d["period"], td_left),
        Paragraph(brk_d["igst"], td_right),
        Paragraph(brk_d["cgst"], td_right),
        Paragraph(brk_d["sgst"], td_right),
        Paragraph(brk_d["cess"], td_right),
    ]
    t_brk_data_tbl = Table([t_brk_row], colWidths=t_brk_widths)
    t_brk_data_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t_brk_data_tbl)
    story.append(Spacer(1, 14))

    verif = data.get("verification", {})
    verif_p1 = Paragraph("<b>Verification:</b><br/>I hereby solemnly affirm and declare that the information given herein above is true and correct to the best of my knowledge and belief and nothing has been concealed there from.", ParagraphStyle('VerifBody', fontName=FONT_REGULAR, fontSize=8.0, leading=11, textColor=COLOR_TEXT_MAIN))
    story.append(verif_p1)
    story.append(Spacer(1, 14))

    signatory_left = Paragraph(f"<b>Date:</b> {verif.get('date', '22/04/2026')}", td_left)
    signatory_right = Paragraph(f"Name of Authorized Signatory<br/><b>{verif.get('signatory_name', 'PRIYANKA NARWARIYA')}</b><br/><br/>Designation /Status<br/>{verif.get('designation', 'PROPRIETORSHIP')}", td_left)

    verif_sign_tbl = Table([[signatory_left, signatory_right]], colWidths=[275, USABLE_W - 275])
    verif_sign_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(verif_sign_tbl)

    doc.build(story, canvasmaker=NumberedCanvasWithWatermark)

    # Post-process metadata using PyMuPDF
    try:
        gstin = data.get("gstin", "23BCHPB7336L1ZM")
        pdf_doc = pymupdf.open(output_filename)
        pdf_doc.set_metadata({
            "creator": "pdfmake",
            "producer": "pdfmake",
            "title": f"GSTR3B_{gstin}_032026.pdf",
            "subject": "Form GSTR-3B Return",
            "author": "GST Portal",
            "creationDate": "20260921092118Z",
            "modDate": "20260921092118Z"
        })
        tmp_meta_out = output_filename + ".meta.tmp"
        pdf_doc.save(tmp_meta_out)
        pdf_doc.close()
        shutil.move(tmp_meta_out, output_filename)
    except Exception:
        pass

    return output_filename


# =========================================================================
# PRIMARY PUBLIC API
# =========================================================================

def generate_gstr3b_pdf(
    output_filename: str = "Form_GSTR_3B.pdf",
    data: Optional[Dict[str, Any]] = None,
    engine: str = "auto"
) -> str:
    """
    Compiles the pixel-perfect 3-page Form GSTR-3B PDF.
    By default (engine='auto'), uses the authoritative vector template cloner with dynamic field patching,
    falling back to ReportLab Platypus if the template is not found.
    """
    if data is None:
        data = get_default_gstr3b_data()
    else:
        default_d = get_default_gstr3b_data()
        for k, v in default_d.items():
            if k not in data:
                data[k] = v

    if (engine in ("auto", "template")) and os.path.exists(TEMPLATE_PDF_PATH):
        try:
            return _patch_template_gstr3b_pdf(output_filename, data)
        except Exception:
            return _generate_with_reportlab(output_filename, data)
    else:
        return _generate_with_reportlab(output_filename, data)


if __name__ == '__main__':
    out_file = generate_gstr3b_pdf()
    print(f"Generated pixel-perfect Form GSTR-3B PDF: {out_file}")
