"""
Form GSTR-3B Pixel-Accurate HTML+CSS Layout Compiler.
Exact mathematical reproduction of the Indian GST return form (Form GSTR-3B).
All dimensions, typography, colors, borders, and watermark match the vector specification.
"""

from __future__ import annotations
import os
from typing import Dict, Any, Optional
from pdf_analyzer.gst.gstr3b_generator import get_default_gstr3b_data


def generate_gstr3b_html(data: Optional[Dict[str, Any]] = None) -> str:
    """Renders exact 3-page HTML+CSS markup for Form GSTR-3B."""
    if data is None:
        data = get_default_gstr3b_data()
    else:
        default_d = get_default_gstr3b_data()
        for k, v in default_d.items():
            if k not in data:
                data[k] = v

    gstin = data.get("gstin", "23BCHPB7336L1ZM")
    legal_name = data.get("legal_name", "PRIYANKA NARWARIYA")
    trade_name = data.get("trade_name", "ATHARV ENTERPRISES")
    arn = data.get("arn", "AA230326938530E")
    arn_date = data.get("arn_date", "22/04/2026")
    year = data.get("year", "2025-26")
    period = data.get("period", "Jan-Mar")
    verif = data.get("verification", {})
    verif_date = verif.get("date", "22/04/2026")
    verif_name = verif.get("signatory_name", "PRIYANKA NARWARIYA")
    verif_desig = verif.get("designation", "PROPRIETORSHIP")
    breakup = data.get("breakup", {"period": "March 2026", "igst": "0.00", "cgst": "766892.00", "sgst": "766892.00", "cess": "0.00"})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Form GSTR-3B — {gstin}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto:ital,wght@0,400;0,500;1,400&display=swap" rel="stylesheet">
<style>
  @page {{
    size: 595.28pt 841.89pt;
    margin: 0;
  }}
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}
  body {{
    font-family: 'Roboto', sans-serif;
    color: #000000;
    background: #525659;
    padding: 20pt 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  .page {{
    position: relative;
    width: 595.28pt;
    height: 841.89pt;
    background: #ffffff;
    margin: 0 auto 20pt auto;
    page-break-after: always;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
  }}
  @media print {{
    body {{
      background: #ffffff;
      padding: 0;
    }}
    .page {{
      margin: 0;
      box-shadow: none;
      width: 595.28pt;
      height: 841.89pt;
    }}
  }}

  /* Watermark */
  .watermark {{
    position: absolute;
    left: 195.33pt;
    top: 654.44pt;
    transform: rotate(-54.7deg);
    transform-origin: 0 0;
    font-size: 150pt;
    font-family: 'Roboto', sans-serif;
    font-weight: 400;
    color: rgba(128, 128, 128, 0.302);
    user-select: none;
    pointer-events: none;
    z-index: 1;
    white-space: nowrap;
  }}

  /* Base Typography & Layering */
  .content-layer {{
    position: absolute;
    top: 0;
    left: 0;
    width: 595.28pt;
    height: 841.89pt;
    z-index: 2;
  }}

  .section-bar {{
    position: absolute;
    left: 20.00pt;
    width: 555.28pt;
    background-color: #FDE9D9;
    border: 1pt solid #000000;
    font-family: 'Roboto', sans-serif;
    font-weight: 500;
    font-size: 10pt;
    line-height: 12pt;
    color: #000000;
    padding-left: 5.00pt;
    display: flex;
    align-items: center;
  }}

  /* Tables */
  table.gstr-table {{
    position: absolute;
    left: 20.50pt;
    width: 554.28pt;
    border-collapse: collapse;
    border: 1pt solid #000000;
    font-family: 'Roboto', sans-serif;
    font-size: 9pt;
    color: #000000;
    table-layout: fixed;
  }}
  table.gstr-table th, table.gstr-table td {{
    border: 1pt solid #000000;
    padding: 2pt 4.5pt;
    vertical-align: top;
    line-height: 10.5pt;
    word-wrap: break-word;
  }}
  table.gstr-table th {{
    background-color: #F2F2F2;
    font-weight: 500;
    text-align: left;
  }}
  .text-left {{ text-align: left; }}
  .text-right {{ text-align: right; }}
  .text-center {{ text-align: center; }}
  .section-subrow {{
    font-weight: 500;
    background-color: #ffffff;
  }}
</style>
</head>
<body>

  <!-- ========================================== -->
  <!-- PAGE 1                                     -->
  <!-- ========================================== -->
  <div class="page" id="page-1">
    <div class="watermark">FILED</div>
    <div class="content-layer">
      
      <!-- 8.1 Title -->
      <div style="position: absolute; left: 0; width: 595.28pt; top: 40.00pt; text-align: center; font-size: 18pt; font-weight: 500; line-height: 21.09pt;">
        Form GSTR-3B
      </div>

      <!-- 8.2 Subtitle -->
      <div style="position: absolute; left: 0; width: 595.28pt; top: 71.09pt; text-align: center; font-size: 12pt; font-style: italic; font-weight: 400; line-height: 14.07pt;">
        [See rule 61(5)]
      </div>

      <!-- 8.3 Year / Period Box (Top Right) -->
      <table style="position: absolute; left: 380.00pt; top: 105.41pt; width: 192.00pt; height: 30.09pt; border-collapse: collapse; border: 0.5pt solid #000000; font-size: 9pt;">
        <tr style="height: 15.05pt;">
          <td style="width: 83.50pt; background-color: #FAD2B1; font-weight: 500; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">Year</td>
          <td style="width: 108.50pt; background-color: #ffffff; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">{year}</td>
        </tr>
        <tr style="height: 15.05pt;">
          <td style="width: 83.50pt; background-color: #FAD2B1; font-weight: 500; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">Period</td>
          <td style="width: 108.50pt; background-color: #ffffff; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">{period}</td>
        </tr>
      </table>

      <!-- 8.5 GST Information Box -->
      <table style="position: absolute; left: 20.00pt; top: 155.75pt; width: 555.03pt; border-collapse: collapse; border: 0.5pt solid #000000; font-size: 8pt;">
        <tr style="height: 13.9pt;">
          <td style="width: 208.50pt; background-color: #FAD2B1; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">GSTIN of the supplier</td>
          <td style="background-color: #ffffff; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">{gstin}</td>
        </tr>
        <tr style="height: 13.9pt;">
          <td style="width: 208.50pt; background-color: #FAD2B1; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">2(a). Legal name of the registered person</td>
          <td style="background-color: #ffffff; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">{legal_name}</td>
        </tr>
        <tr style="height: 13.9pt;">
          <td style="width: 208.50pt; background-color: #FAD2B1; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">2(b). Trade name, if any</td>
          <td style="background-color: #ffffff; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">{trade_name}</td>
        </tr>
        <tr style="height: 13.9pt;">
          <td style="width: 208.50pt; background-color: #FAD2B1; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">2(c). ARN</td>
          <td style="background-color: #ffffff; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">{arn}</td>
        </tr>
        <tr style="height: 13.9pt;">
          <td style="width: 208.50pt; background-color: #FAD2B1; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">2(d). Date of ARN</td>
          <td style="background-color: #ffffff; font-weight: 400; border: 0.5pt solid #000000; padding: 2.25pt 4.25pt;">{arn_date}</td>
        </tr>
      </table>

      <!-- 8.6 Amount Note -->
      <div style="position: absolute; left: 20.00pt; width: 555.00pt; top: 230.63pt; text-align: right; padding-right: 21.09pt; font-size: 8pt; font-weight: 400;">
        (Amount in ₹ for all tables)
      </div>

      <!-- 8.7 Section 3.1 -->
      <div class="section-bar" style="top: 250.00pt; height: 15.71875pt;">
        3.1 Details of Outward supplies and inward supplies liable to reverse charge (other than those covered by Table 3.1.1)
      </div>
      <table class="gstr-table" style="top: 270.72pt;">
        <colgroup>
          <col style="width: 271.75pt;">
          <col style="width: 80.12pt;">
          <col style="width: 62.74pt;">
          <col style="width: 52.42pt;">
          <col style="width: 58.25pt;">
          <col style="width: 29.00pt;">
        </colgroup>
        <thead>
          <tr style="height: 26.09pt;">
            <th>Nature of Supplies</th>
            <th class="text-right">Total taxable value</th>
            <th class="text-right">Integrated tax</th>
            <th class="text-right">Central tax</th>
            <th class="text-right">State/UT tax</th>
            <th class="text-right">Cess</th>
          </tr>
        </thead>
        <tbody>
          <tr style="height: 26.10pt;">
            <td>(a) Outward taxable supplies (other than zero rated, nil rated and exempted)</td>
            <td class="text-right">8523048.24</td>
            <td class="text-right">0.00</td>
            <td class="text-right">766881.75</td>
            <td class="text-right">766881.75</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.54pt;">
            <td>(b) Outward taxable supplies (zero rated)</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>(c ) Other outward supplies (nil rated, exempted)</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>(d) Inward supplies (liable to reverse charge)</td>
            <td class="text-right">398.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">9.96</td>
            <td class="text-right">9.96</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.54pt;">
            <td>(e) Non-GST outward supplies</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
        </tbody>
      </table>

      <!-- 8.8 Section 3.1.1 -->
      <div class="section-bar" style="top: 411.09pt; height: 27.44pt; align-items: flex-start; padding-top: 2pt;">
        3.1.1 Details of Supplies notified under section 9(5) of the CGST Act, 2017 and corresponding provisions in IGST/UTGST/ SGST Acts
      </div>
      <table class="gstr-table" style="top: 443.53pt;">
        <colgroup>
          <col style="width: 335.22pt;">
          <col style="width: 51.96pt;">
          <col style="width: 54.60pt;">
          <col style="width: 42.23pt;">
          <col style="width: 41.27pt;">
          <col style="width: 29.00pt;">
        </colgroup>
        <thead>
          <tr style="height: 36.64pt;">
            <th>Nature of Supplies</th>
            <th class="text-right">Total taxable value</th>
            <th class="text-right">Integrated tax</th>
            <th class="text-right">Central tax</th>
            <th class="text-right">State/UT tax</th>
            <th class="text-right">Cess</th>
          </tr>
        </thead>
        <tbody>
          <tr style="height: 26.10pt;">
            <td>(i) Taxable supplies on which electronic commerce operator pays tax u/s 9(5) [to be furnished by electronic commerce operator]</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 47.18pt;">
            <td>(ii) Taxable supplies made by registered person through electronic commerce operator, on which electronic commerce operator is required to pay tax u/s 9(5) [to be furnished by registered person making supplies through electronic commerce operator]</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
        </tbody>
      </table>

      <!-- 8.9 Section 3.2 -->
      <div class="section-bar" style="top: 579.45pt; height: 15.72pt;">
        3.2 Out of supplies made in 3.1 (a) and 3.1.1 (i), details of inter-state supplies made
      </div>
      <table class="gstr-table" style="top: 600.17pt;">
        <colgroup>
          <col style="width: 184.76pt;">
          <col style="width: 184.76pt;">
          <col style="width: 184.76pt;">
        </colgroup>
        <thead>
          <tr style="height: 15.55pt;">
            <th>Nature of Supplies</th>
            <th class="text-right">Total taxable value</th>
            <th class="text-right">Integrated tax</th>
          </tr>
        </thead>
        <tbody>
          <tr style="height: 15.55pt;">
            <td>Supplies made to Unregistered Persons</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 26.09pt;">
            <td>Supplies made to Composition Taxable Persons</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>Supplies made to UIN holders</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
        </tbody>
      </table>

      <!-- 8.10 Section 4 - Eligible ITC (Page 1 Portion) -->
      <div class="section-bar" style="top: 698.91pt; height: 15.72pt;">
        4.  Eligible ITC
      </div>
      <table class="gstr-table" style="top: 719.62pt;">
        <colgroup>
          <col style="width: 289.10pt;">
          <col style="width: 70.12pt;">
          <col style="width: 70.11pt;">
          <col style="width: 70.11pt;">
          <col style="width: 54.84pt;">
        </colgroup>
        <thead>
          <tr style="height: 15.55pt;">
            <th>Details</th>
            <th class="text-right">Integrated tax</th>
            <th class="text-right">Central tax</th>
            <th class="text-right">State/UT tax</th>
            <th class="text-right">Cess</th>
          </tr>
        </thead>
        <tbody>
          <tr style="height: 15.55pt;">
            <td colspan="5" class="section-subrow">A. ITC Available (whether in full or part)</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>(1) Import of goods</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>(2) Import of services</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>(3) Inward supplies liable to reverse charge (other than 1 & 2 above)</td>
            <td class="text-right">0.00</td>
            <td class="text-right">9.96</td>
            <td class="text-right">9.96</td>
            <td class="text-right">0.00</td>
          </tr>
        </tbody>
      </table>

    </div>
  </div>


  <!-- ========================================== -->
  <!-- PAGE 2                                     -->
  <!-- ========================================== -->
  <div class="page" id="page-2">
    <div class="watermark">FILED</div>
    <div class="content-layer">
      
      <!-- Table 4 Continuation (NO repeated header) -->
      <table class="gstr-table" style="top: 40.50pt;">
        <colgroup>
          <col style="width: 289.10pt;">
          <col style="width: 70.12pt;">
          <col style="width: 70.11pt;">
          <col style="width: 70.11pt;">
          <col style="width: 54.84pt;">
        </colgroup>
        <tbody>
          <tr style="height: 15.55pt;">
            <td>(4) Inward supplies from ISD</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.54pt;">
            <td>(5) All other ITC</td>
            <td class="text-right">231510.52</td>
            <td class="text-right">400759.78</td>
            <td class="text-right">400759.78</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td colspan="5" class="section-subrow">B. ITC Reversed</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>(1) As per rules 38,42 & 43 of CGST Rules and section 17(5)</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.54pt;">
            <td>(2) Others</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td class="section-subrow">C. Net ITC available (A-B)</td>
            <td class="text-right">231510.52</td>
            <td class="text-right">400769.74</td>
            <td class="text-right">400769.74</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td class="section-subrow">(D) Other Details</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 20.82pt;">
            <td>(1) ITC reclaimed which was reversed under Table 4(B)(2) in earlier tax period</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 20.82pt;">
            <td>(2) Ineligible ITC under section 16(4) & ITC restricted due to PoS rules</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
        </tbody>
      </table>

      <!-- 9.1 Section 5 -->
      <div class="section-bar" style="top: 216.47pt; height: 15.72pt;">
        5 Values of exempt, nil-rated and non-GST inward supplies
      </div>
      <table class="gstr-table" style="top: 237.19pt;">
        <colgroup>
          <col style="width: 325.37pt;">
          <col style="width: 114.45pt;">
          <col style="width: 114.46pt;">
        </colgroup>
        <thead>
          <tr style="height: 16.04pt;">
            <th>Nature of Supplies</th>
            <th class="text-right">Inter- State supplies</th>
            <th class="text-right">Intra- State supplies</th>
          </tr>
        </thead>
        <tbody>
          <tr style="height: 15.55pt;">
            <td>From a supplier under composition scheme, Exempt, Nil rated supply</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>Non GST supply</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
        </tbody>
      </table>

      <!-- 9.2 Section 5.1 -->
      <div class="section-bar" style="top: 309.83pt; height: 15.72pt;">
        5.1 Interest and Late fee for previous tax period
      </div>
      <table class="gstr-table" style="top: 330.55pt;">
        <colgroup>
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
        </colgroup>
        <thead>
          <tr style="height: 16.04pt;">
            <th>Details</th>
            <th class="text-right">Integrated tax</th>
            <th class="text-right">Central tax</th>
            <th class="text-right">State/UT tax</th>
            <th class="text-right">Cess</th>
          </tr>
        </thead>
        <tbody>
          <tr style="height: 26.10pt;">
            <td>System computed Interest</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
          <tr style="height: 15.54pt;">
            <td>Interest Paid</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>Late fee</td>
            <td class="text-center">-</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
          </tr>
        </tbody>
      </table>

      <!-- 9.3 Section 6.1 Payment of Tax -->
      <div class="section-bar" style="top: 429.28pt; height: 15.72pt;">
        6.1 Payment of tax
      </div>
      <table class="gstr-table" style="top: 450.50pt; font-size: 7.5pt;">
        <colgroup>
          <col style="width: 49.98pt;">
          <col style="width: 49.97pt;">
          <col style="width: 54.53pt;">
          <col style="width: 49.97pt;">
          <col style="width: 49.98pt;">
          <col style="width: 49.97pt;">
          <col style="width: 49.98pt;">
          <col style="width: 49.97pt;">
          <col style="width: 49.98pt;">
          <col style="width: 49.97pt;">
          <col style="width: 49.98pt;">
        </colgroup>
        <thead>
          <tr>
            <th rowspan="2" style="vertical-align: top; padding: 2pt;">Description</th>
            <th rowspan="2" class="text-right" style="vertical-align: top; padding: 2pt;">Tax payable</th>
            <th rowspan="2" class="text-right" style="vertical-align: top; padding: 2pt;">Adjustment of negative liability of previous tax period</th>
            <th rowspan="2" class="text-right" style="vertical-align: top; padding: 2pt;">Net Tax Payable</th>
            <th colspan="4" class="text-center" style="padding: 2pt;">Tax paid through ITC</th>
            <th rowspan="2" class="text-right" style="vertical-align: top; padding: 2pt;">Tax paid in cash</th>
            <th rowspan="2" class="text-right" style="vertical-align: top; padding: 2pt;">Interest paid in cash</th>
            <th rowspan="2" class="text-right" style="vertical-align: top; padding: 2pt;">Late fee paid in cash</th>
          </tr>
          <tr>
            <th class="text-right" style="padding: 2pt;">Integrated tax</th>
            <th class="text-right" style="padding: 2pt;">Central tax</th>
            <th class="text-right" style="padding: 2pt;">State/UT tax</th>
            <th class="text-right" style="padding: 2pt;">Cess</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td colspan="11" class="section-subrow" style="font-size: 8pt; padding: 2pt 4.5pt;">(A) Other than reverse charge</td>
          </tr>
          <tr style="height: 26.09pt;">
            <td>Integrated tax</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
          </tr>
          <tr style="height: 26.10pt;">
            <td>Central tax</td>
            <td class="text-right">766882.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">766882.00</td>
            <td class="text-right">231511.00</td>
            <td class="text-right">535371.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 26.09pt;">
            <td>State/UT tax</td>
            <td class="text-right">766882.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">766882.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-right">745636.00</td>
            <td class="text-center">-</td>
            <td class="text-right">21246.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>Cess</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
          </tr>
          <tr>
            <td colspan="11" class="section-subrow" style="font-size: 8pt; padding: 2pt 4.5pt;">(B) Reverse charge and supplies made u/s 9(5)</td>
          </tr>
          <tr style="height: 26.10pt;">
            <td>Integrated tax</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
          <tr style="height: 26.09pt;">
            <td>Central tax</td>
            <td class="text-right">10.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">10.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-right">10.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
          <tr style="height: 26.09pt;">
            <td>State/UT tax</td>
            <td class="text-right">10.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">10.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-right">10.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
          <tr style="height: 15.55pt;">
            <td>Cess</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
            <td class="text-right">0.00</td>
            <td class="text-center">-</td>
            <td class="text-center">-</td>
          </tr>
        </tbody>
      </table>

      <!-- 9.4 Breakup Section Header (Header ONLY on Page 2) -->
      <div class="section-bar" style="top: 758.03pt; height: 15.72pt;">
        Breakup of tax liability declared (for interest computation)
      </div>
      <table class="gstr-table" style="top: 778.75pt;">
        <colgroup>
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
        </colgroup>
        <thead>
          <tr style="height: 16.04pt;">
            <th>Period</th>
            <th class="text-right">Integrated tax</th>
            <th class="text-right">Central tax</th>
            <th class="text-right">State/UT tax</th>
            <th class="text-right">Cess</th>
          </tr>
        </thead>
      </table>

    </div>
  </div>


  <!-- ========================================== -->
  <!-- PAGE 3                                     -->
  <!-- ========================================== -->
  <div class="page" id="page-3">
    <div class="watermark">FILED</div>
    <div class="content-layer">
      
      <!-- 10.1 Breakup Table Continuation (Data Row ONLY) -->
      <table class="gstr-table" style="top: 40.50pt;">
        <colgroup>
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
          <col style="width: 110.86pt;">
        </colgroup>
        <tbody>
          <tr style="height: 15.55pt;">
            <td>{breakup.get('period', 'March 2026')}</td>
            <td class="text-right">{breakup.get('igst', '0.00')}</td>
            <td class="text-right">{breakup.get('cgst', '766892.00')}</td>
            <td class="text-right">{breakup.get('sgst', '766892.00')}</td>
            <td class="text-right">{breakup.get('cess', '0.00')}</td>
          </tr>
        </tbody>
      </table>

      <!-- 10.3 Verification Block -->
      <div style="position: absolute; left: 20.00pt; top: 71.55pt; font-size: 10pt; font-weight: 500;">
        Verification:
      </div>
      <div style="position: absolute; left: 20.00pt; top: 83.27pt; width: 555.28pt; font-size: 9pt; font-weight: 400; line-height: 12pt;">
        I hereby solemnly affirm and declare that the information given herein above is true and correct to the best of my knowledge and belief and<br/>
        nothing has been concealed there from.
      </div>

      <!-- 10.4 Signatory Block -->
      <div style="position: absolute; left: 20.00pt; top: 118.36pt; font-size: 9pt; font-weight: 400;">
        <b>Date:</b> {verif_date}
      </div>

      <div style="position: absolute; left: 301.64pt; top: 118.36pt; font-size: 9pt; line-height: 13pt;">
        <div>Name of Authorized Signatory</div>
        <div style="font-weight: 500; margin-bottom: 8pt;">{verif_name}</div>
        <div>Designation /Status</div>
        <div>{verif_desig}</div>
      </div>

    </div>
  </div>

</body>
</html>
"""
    return html


if __name__ == '__main__':
    html_out = generate_gstr3b_html()
    os.makedirs("output", exist_ok=True)
    with open("output/Form_GSTR_3B.html", "w", encoding="utf-8") as f:
        f.write(html_out)
    print("Generated Form GSTR-3B HTML: output/Form_GSTR_3B.html")
