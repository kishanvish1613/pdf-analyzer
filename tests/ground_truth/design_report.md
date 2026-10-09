# PDF Visual Design Specification Report (High-Fidelity)

> Generated automatically by **PDF Design Analyzer v2.0**

## 1. Closed-Loop SSIM Verification & Quality Gate

- **Overall SSIM Quality Score:** `0.8045` / `1.0000`
- **Self-Check Status:** `PASSED` (Mean Element IoU: `1.000`)

## 2. Document Geometry & Coordinate System

- **Coordinate System:** `Top-Left origin (x=0, y=0 at top-left; x increases right, y increases down). Unified transform applied.`
- **Total Pages:** `2` | **Analysis DPI:** `300`
- **Page Dimensions:** `612.000 pt` × `792.000 pt` (`215.90 mm` × `279.40 mm` | `2550.0 px` × `3300.0 px` @ 300 DPI)
- **Orientation:** `Portrait` | **Rotation:** `0°`

## 3. Page Margins & Attributed Source Elements

| Margin Edge | Comprehensive (pt) | Text-Only (pt) | Millimeters (mm) | Pixels (px @ 600 DPI) | Attributed Source Element |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Top** | **36.000 pt** | 43.020 pt | 12.70 mm | 150.0 px | `Vector Drawing/Rule` |
| **Right** | **33.760 pt** | 33.760 pt | 11.91 mm | 140.7 px | `Text: 'Closing Balance'` |
| **Bottom** | **42.907 pt** | 42.907 pt | 15.14 mm | 178.8 px | `Text: 'HDFC BANK LIMITED. R'` |
| **Left** | **36.000 pt** | 36.000 pt | 12.70 mm | 150.0 px | `Text: 'Nomination : Registe'` |

## 4. Detected Layout Regions (Containment Hierarchy)

| Region Type | Top-Left (x0, y0) pt | Dimensions (W × H) pt | Spans | Implicit Left / Right Axis | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `container_block` | (36.00, 36.00) | 60.00 × 34.00 | 1 | 36.00 / 96.00 pt |  |
| `address_block` | (36.00, 80.00) | 220.00 × 95.00 | 6 | 36.00 / 256.00 pt |  |
| `transaction_table` | (36.00, 230.00) | 542.24 × 482.00 | 46 | 36.00 / 578.24 pt |  |
| `key_value_grid` | (36.00, 182.91) | 142.07 × 34.86 | 2 | 36.00 / 178.07 pt |  |
| `key_value_grid` | (310.00, 81.44) | 65.79 × 98.52 | 8 | 310.00 / 375.79 pt |  |
| `key_value_grid` | (410.00, 81.40) | 104.67 × 98.56 | 16 | 410.00 / 514.67 pt |  |
| `table_heading` | (310.00, 200.02) | 142.35 × 19.28 | 1 | 310.00 / 452.35 pt |  |
| `disclaimer` | (36.00, 739.48) | 418.15 × 9.62 | 1 | 36.00 / 454.15 pt |  |
| `page_number` | (540.20, 739.48) | 35.80 × 9.62 | 1 | 540.20 / 576.00 pt |  |

## 5. Transaction Table Architecture

### Table Column Partitions

| # | Header Text | Semantic Type | Width (pt) | Width (%) | Left Rule | Right Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0 | **** | `generic` | 55.000 pt | 8.99% | `rule_v_1` | `rule_v_2` |
| 0 | **Chq/Ref No UPI/6002198** | `generic` | 64.000 pt | 10.46% | `rule_v_2` | `rule_v_4` |
| 0 | **UPI-SWIGGY FOOD ORDER-SWIGGY@HDFC Narration / Description REF NO 600219871234-ORDER 99281** | `generic` | 179.000 pt | 29.25% | `rule_v_4` | `rule_v_5` |
| 0 | **Value Dt 02/01/2026** | `generic` | 54.000 pt | 8.82% | `rule_v_5` | `rule_v_6` |
| 0 | **Withdrawal 1,450.00** | `generic` | 59.000 pt | 9.64% | `rule_v_6` | `rule_v_7` |
| 0 | **Deposit** | `generic` | 59.000 pt | 9.64% | `rule_v_7` | `rule_v_8` |
| 0 | **1,24,500.00** | `generic` | 65.000 pt | 10.62% | `rule_v_8` | `rule_v_9` |

### Full Per-Row / Line Vertical Metrics Table

| Line # | Y Top (pt) | Height (pt) | Baseline Y | Gap to Next | B2B Dist | Snippet |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 234.44 | 11.02 | 243.00 | 8.48 pt | 19.00 pt | `Date Chq/Ref No Narration / Description ` |
| 2 | 253.94 | 10.30 | 262.00 | 0.20 pt | 10.50 pt | `02/01/2026 UPI/6002198 UPI-SWIGGY FOOD O` |
| 3 | 264.44 | 10.30 | 272.50 | 0.20 pt | 10.50 pt | `REF NO 600219871234-ORDER 99281` |
| 4 | 274.94 | 10.30 | 283.00 | 8.20 pt | 18.50 pt | `MERCHANT PAYMENT BANGALORE IN` |
| 5 | 293.44 | 10.30 | 301.50 | 0.20 pt | 10.50 pt | `05/01/2026 NEFT/881290 NEFT CR-TECH SOLU` |
| 6 | 303.94 | 10.30 | 312.00 | 0.20 pt | 10.50 pt | `SALARY FOR THE MONTH OF DECEMBER 2025` |
| 7 | 314.44 | 10.30 | 322.50 | 8.20 pt | 18.50 pt | `UTR: HDFCN26005891230-CMS` |
| 8 | 332.94 | 10.30 | 341.00 | 0.20 pt | 10.50 pt | `10/01/2026 CHQ 000214 TO CLEARING CHEQUE` |
| 9 | 343.44 | 10.30 | 351.50 | 0.20 pt | 10.50 pt | `FAVOURING SOCIETY MAINTENANCE CHARGES` |
| 10 | 353.94 | 10.30 | 362.00 | 8.20 pt | 18.50 pt | `CLEARING HOUSE MUMBAI CTS` |
| 11 | 372.44 | 10.30 | 380.50 | 0.20 pt | 10.50 pt | `15/01/2026 POS/441298 POS DEBIT-RELIANCE` |
| 12 | 382.94 | 10.30 | 391.00 | 0.20 pt | 10.50 pt | `AUTH CODE 441298 RETAIL STORE` |
| 13 | 393.44 | 10.30 | 401.50 | 8.20 pt | 18.50 pt | `TERMINAL ID 88120092 MUMBAI` |
| 14 | 411.94 | 10.30 | 420.00 | 0.20 pt | 10.50 pt | `20/01/2026 INT/REC INTEREST CREDIT FOR Q` |
| 15 | 422.44 | 10.30 | 430.50 | - | - | `COMPOUNDED QUARTERLY SAVINGS` |

## 6. Numeric Alignment & Digits vs Suffix Split

| Column | Alignment Type | Digits StdDev (pt) | Suffix StdDev (pt) | Decimal StdDev (pt) | Number Format | Negative Convention |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **** | `right_aligned (digits-locked)` | `0.000 pt` | `N/A` | `N/A` | None / Unformatted | `unsigned_column` |
| **Chq/Ref No UPI/6002198** | `right_aligned_approximate` | `1.422 pt` | `N/A` | `N/A` | None / Unformatted | `unsigned_column` |
| **UPI-SWIGGY FOOD ORDER-SWIGGY@HDFC Narration / Description REF NO 600219871234-ORDER 99281** | `right_aligned_approximate` | `43.541 pt` | `0.000` | `N/A` | None / Unformatted | `unsigned_column` |
| **Value Dt 02/01/2026** | `right_aligned (digits-locked)` | `0.000 pt` | `N/A` | `N/A` | None / Unformatted | `unsigned_column` |
| **Withdrawal 1,450.00** | `right_aligned_approximate` | `1.966 pt` | `N/A` | `1.966` | International (100,000) | `unsigned_column` |
| **Deposit** | `right_aligned_approximate` | `2.085 pt` | `N/A` | `2.085` | International (100,000) | `unsigned_column` |
| **1,24,500.00** | `decimal_point_aligned` | `0.000 pt` | `N/A` | `0.000` | Indian (1,00,000) | `unsigned_column` |

## 7. Typography Hierarchy & Font Box vs Ink Box Specs

| Role | Font Family | Size (pt) | Weight | Color (HEX) | AA Corrected | Recommended Leading | CSS Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `section_heading_h2` | Helvetica | 14.00 pt | bold | `#FFFFFF` | `#FFFFFF` | 17.50 pt | `font-family: 'Helvetica', sans-serif; font-size: 14.0pt; font-weight: bold; color: #FFFFFF; line-height: 17.5pt;` |
| `section_heading_h2` | Helvetica | 14.00 pt | bold | `#1A365D` | `#1A365D` | 17.50 pt | `font-family: 'Helvetica', sans-serif; font-size: 14.0pt; font-weight: bold; color: #1A365D; line-height: 17.5pt;` |
| `table_header_or_field_label` | Helvetica | 9.00 pt | bold | `#1A202C` | `#1A202C` | 11.25 pt | `font-family: 'Helvetica', sans-serif; font-size: 9.0pt; font-weight: bold; color: #1A202C; line-height: 11.25pt;` |
| `table_header_or_field_label` | Helvetica | 9.00 pt | bold | `#4A5568` | `#4A5568` | 11.25 pt | `font-family: 'Helvetica', sans-serif; font-size: 9.0pt; font-weight: bold; color: #4A5568; line-height: 11.25pt;` |
| `text_style_8pt_regular` | Helvetica | 8.50 pt | regular | `#1A202C` | `#1A202C` | 14.00 pt | `font-family: 'Helvetica', sans-serif; font-size: 8.5pt; font-weight: normal; color: #1A202C; line-height: 14.0pt;` |
| `table_header_or_field_label` | Helvetica | 8.50 pt | bold | `#1A202C` | `#1A202C` | 10.62 pt | `font-family: 'Helvetica', sans-serif; font-size: 8.5pt; font-weight: bold; color: #1A202C; line-height: 10.62pt;` |
| `table_header_or_field_label` | Helvetica | 8.00 pt | bold | `#1A202C` | `#1A202C` | 12.50 pt | `font-family: 'Helvetica', sans-serif; font-size: 8.0pt; font-weight: bold; color: #1A202C; line-height: 12.5pt;` |
| `text_style_8pt_regular` | Helvetica | 8.00 pt | regular | `#1A202C` | `#1A202C` | 12.50 pt | `font-family: 'Helvetica', sans-serif; font-size: 8.0pt; font-weight: normal; color: #1A202C; line-height: 12.5pt;` |
| `table_header_or_field_label` | Helvetica | 8.00 pt | bold | `#1E293B` | `#1E293B` | 10.00 pt | `font-family: 'Helvetica', sans-serif; font-size: 8.0pt; font-weight: bold; color: #1E293B; line-height: 10.0pt;` |
| `table_body_text` | Helvetica | 7.50 pt | regular | `#0F172A` | `#0F172A` | 10.50 pt | `font-family: 'Helvetica', sans-serif; font-size: 7.5pt; font-weight: normal; color: #0F172A; line-height: 10.5pt;` |

## 8. Logo & Alignment Offsets

- **Placement:** `top-left` | **Type:** `vector_drawn_emblem` | **Effective DPI:** `300.0`
- **Dimensions:** `60.00 pt` × `34.00 pt` (Aspect Ratio: `1.765`)
- **Offsets to Axes:** Header Baseline: `12.00 pt` | Table Right Edge: `482.24 pt`
- **Nearby Caption:** 'MR. ANAND SHARMA' (Distance: `15.37 pt`)
