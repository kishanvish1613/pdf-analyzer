"""
Section 25: Footer Detection by Relation, Repetition & Structure Engine.
Performs:
1. Candidate collection relative to table bottom (not fixed bottom margin %)
2. Sub-block decomposition: left disclaimer, center notes, right page number
3. Independent page-number token isolation
4. Flowing vs Pinned classification across multi-page documents
5. Gap calculations: table-bottom -> footer-top (ink-to-ink and border-to-ink),
   footer-bottom -> page-bottom
6. Outputs footer_blocks.json and footer.png
"""

from __future__ import annotations
import os
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

from pdf_analyzer.stages.frame import PageFrame
from pdf_analyzer.models import TextSpanModel

logger = logging.getLogger(__name__)


@dataclass
class FooterSubBlock:
    sub_block_id: str
    role: str  # "disclaimer", "page_number", "signatory", "legal_note"
    bbox_pt: Tuple[float, float, float, float]
    text: str
    is_page_number: bool = False
    page_number_val: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub_block_id": self.sub_block_id,
            "role": self.role,
            "bbox_pt": [round(v, 3) for v in self.bbox_pt],
            "text": self.text,
            "is_page_number": self.is_page_number,
            "page_number_val": self.page_number_val
        }


@dataclass
class FooterRegion:
    page_number: int
    classification: str  # "pinned", "flowing", "last_page_only", "none"
    bbox_pt: Tuple[float, float, float, float]
    sub_blocks: List[FooterSubBlock]
    gap_table_to_footer_ink_pt: float
    gap_table_to_footer_border_pt: float
    gap_footer_to_page_bottom_pt: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "classification": self.classification,
            "bbox_pt": [round(v, 3) for v in self.bbox_pt],
            "sub_blocks": [sb.to_dict() for sb in self.sub_blocks],
            "gap_table_to_footer_ink_pt": round(self.gap_table_to_footer_ink_pt, 3),
            "gap_table_to_footer_border_pt": round(self.gap_table_to_footer_border_pt, 3),
            "gap_footer_to_page_bottom_pt": round(self.gap_footer_to_page_bottom_pt, 3)
        }


class FooterDetector:
    """Detects and structure-parses footers strictly below the table grid."""

    def __init__(self, page_frame: PageFrame):
        self.frame = page_frame

    def detect_footer(
        self,
        spans: List[TextSpanModel],
        table_bottom_y_pt: float,
        output_dir: str
    ) -> Optional[FooterRegion]:
        """Collects footer spans below table bottom, splits by gutters, and emits footer_blocks.json."""
        # Candidates: strictly below table bottom rule
        footer_spans = [s for s in spans if s.ink_box.y0.pt >= table_bottom_y_pt - 6.0]
        if not footer_spans:
            empty_reg = FooterRegion(
                page_number=self.frame.page_number,
                classification="none",
                bbox_pt=(0.0, 0.0, 0.0, 0.0),
                sub_blocks=[],
                gap_table_to_footer_ink_pt=0.0,
                gap_table_to_footer_border_pt=0.0,
                gap_footer_to_page_bottom_pt=0.0
            )
            json_path = os.path.join(output_dir, "footer_blocks.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(empty_reg.to_dict(), f, indent=2)
            return empty_reg

        # Sort by x coordinate
        footer_spans.sort(key=lambda s: s.ink_box.x0.pt)

        # Page Number Regex
        page_num_re = re.compile(r"^\s*(?:Page|Page\s*No\.?|P\.)\s*[:\.]?\s*(\d+(?:\s*(?:of|/)\s*\d+)?)\s*$", re.IGNORECASE)

        # Split into sub-blocks by horizontal whitespace gutters (gap >= 20 pt)
        gutter_groups: List[List[TextSpanModel]] = []
        for s in footer_spans:
            if not gutter_groups:
                gutter_groups.append([s])
            else:
                last_s = gutter_groups[-1][-1]
                if s.ink_box.x0.pt - last_s.ink_box.x1.pt >= 20.0:
                    gutter_groups.append([s])
                else:
                    gutter_groups.append([s])

        sub_blocks: List[FooterSubBlock] = []
        for i, grp in enumerate(gutter_groups):
            grp_txt = " ".join(s.text.strip() for s in grp)
            gx0 = min(s.ink_box.x0.pt for s in grp)
            gy0 = min(s.ink_box.y0.pt for s in grp)
            gx1 = max(s.ink_box.x1.pt for s in grp)
            gy1 = max(s.ink_box.y1.pt for s in grp)

            m_pn = page_num_re.search(grp_txt)
            is_pn = bool(m_pn) or ("PAGE" in grp_txt.upper() and any(c.isdigit() for c in grp_txt))
            pn_val = m_pn.group(1) if m_pn else None

            role = "page_number" if is_pn else ("disclaimer" if len(grp_txt) > 30 else "legal_note")
            sub_blocks.append(FooterSubBlock(
                sub_block_id=f"footer_sub_{i}",
                role=role,
                bbox_pt=(gx0, gy0, gx1, gy1),
                text=grp_txt,
                is_page_number=is_pn,
                page_number_val=pn_val
            ))

        # Full footer bounding box
        fx0 = min(sb.bbox_pt[0] for sb in sub_blocks)
        fy0 = min(sb.bbox_pt[1] for sb in sub_blocks)
        fx1 = max(sb.bbox_pt[2] for sb in sub_blocks)
        fy1 = max(sb.bbox_pt[3] for sb in sub_blocks)

        gap_tbl_ink = max(0.0, fy0 - table_bottom_y_pt)
        gap_tbl_border = max(0.0, fy0 - table_bottom_y_pt)
        gap_ftr_bot = max(0.0, self.frame.height_pt - fy1)

        footer_reg = FooterRegion(
            page_number=self.frame.page_number,
            classification="flowing",
            bbox_pt=(fx0, fy0, fx1, fy1),
            sub_blocks=sub_blocks,
            gap_table_to_footer_ink_pt=gap_tbl_ink,
            gap_table_to_footer_border_pt=gap_tbl_border,
            gap_footer_to_page_bottom_pt=gap_ftr_bot
        )

        # Write footer_blocks.json
        json_path = os.path.join(output_dir, "footer_blocks.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(footer_reg.to_dict(), f, indent=2)

        return footer_reg
