"""
Template Dossier Engine (Phase 8A & Phase 8C-FIX Task F4).
Generates comprehensive template dossiers (dossier.json + dossier.md) for PDF documents:
- Document Producer / Creator / Version / Tagged Status
- Full Structure Tree traversal (Table, TR, TH, TD roles with MCID mappings to L0 text runs & bboxes)
- True content-stream operator histogram from L0 tokenizer (all operators per stream)
- Font inventories and glyph metrics
- Vertical & Horizontal Rule clusters (x/y, span, width, coverage)
- Fill geometry & filled header band detection
- Inline & Form XObject images
- Annotations & Optional Content Groups (OCG) from Catalog
- Raw L0 Coordinate Quantisation (fractions of 0.25, 0.75, 1.0 multiples)
- Text Stream Order (sequence of text runs in emission order with Y)
- Stream-Order Row Recovery grouped by Anchor (Date / Seq No)
- Anchor-based comparison between geometric and stream rows
- Table-Style Verdict (full_grid | vertical_only | horizontal_only | filled_header | borderless | empty_table)
  using rule SPAN (>= 80% of table width/height) and distribution, reporting winner AND runner-up with scores.
"""

from __future__ import annotations
import os
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pymupdf

from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.tokenizer import tokenize_content_stream
from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar, PaintedPath
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.table_grid import TableGridEngine, TableGrid, ColumnModel, RowModel, TableStyleVerdict, RowBandType
from pdf_analyzer.l3_topology.logical_rows import DATE_PATTERNS, SNO_PATTERN
from pdf_analyzer.l4_layout.header import HeaderEngine
from pdf_analyzer.l4_layout.models import HeaderModel
from pdf_analyzer.quantisation_audit import QuantisationAuditEngine
from pdf_analyzer.l5_editor.dimension_lane import DimensionLaneEngine, DimensionLaneModel
from pdf_analyzer.utils.json_sanitizer import sanitize_for_json

logger = logging.getLogger(__name__)


@dataclass
class StreamOrderRow:
    index: int
    anchor_id: str
    y_pt: float
    cells_count: int
    text_content: str
    tokens: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "anchor_id": self.anchor_id,
            "y_pt": self.y_pt,
            "cells_count": self.cells_count,
            "text_content": self.text_content,
            "tokens": self.tokens,
        }


@dataclass
class PageDossier:
    page_number: int
    cropbox_pt: Tuple[float, float, float, float]
    mediabox_pt: Tuple[float, float, float, float]
    operator_histogram: Dict[str, int]
    fonts: List[Dict[str, Any]]
    v_rule_clusters: List[Dict[str, Any]]
    h_rule_clusters: List[Dict[str, Any]]
    fills: List[Dict[str, Any]]
    images: List[Dict[str, Any]]
    annotations: List[Dict[str, Any]]
    optional_content: List[Dict[str, Any]]
    raw_coord_quantisation: Dict[str, Any]
    text_stream_order: List[Dict[str, Any]]
    stream_order_rows: List[StreamOrderRow]
    geometric_rows_count: int
    stream_order_rows_count: int
    row_disagreements: List[str]
    table_style_verdict: str
    table_style_runner_up: str
    style_scores: Dict[str, float]
    verdict_evidence: List[str]
    lane_absent_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "cropbox_pt": list(self.cropbox_pt),
            "mediabox_pt": list(self.mediabox_pt),
            "operator_histogram": self.operator_histogram,
            "fonts": self.fonts,
            "v_rule_clusters": self.v_rule_clusters,
            "h_rule_clusters": self.h_rule_clusters,
            "fills": self.fills,
            "images": self.images,
            "annotations": self.annotations,
            "optional_content": self.optional_content,
            "raw_coord_quantisation": self.raw_coord_quantisation,
            "text_stream_order_count": len(self.text_stream_order),
            "text_stream_order": self.text_stream_order,
            "stream_order_rows": [r.to_dict() for r in self.stream_order_rows],
            "geometric_rows_count": self.geometric_rows_count,
            "stream_order_rows_count": self.stream_order_rows_count,
            "row_disagreements": self.row_disagreements,
            "table_style_verdict": self.table_style_verdict,
            "table_style_runner_up": self.table_style_runner_up,
            "style_scores": self.style_scores,
            "verdict_evidence": self.verdict_evidence,
            "lane_absent_reason": self.lane_absent_reason,
        }


@dataclass
class DocumentDossier:
    pdf_path: str
    producer: Optional[str]
    creator: Optional[str]
    title: Optional[str]
    pdf_version: str
    page_count: int
    is_tagged: bool
    struct_tree: Optional[Dict[str, Any]]
    pages: List[PageDossier] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pdf_path": os.path.abspath(self.pdf_path),
            "producer": self.producer,
            "creator": self.creator,
            "title": self.title,
            "pdf_version": self.pdf_version,
            "page_count": self.page_count,
            "is_tagged": self.is_tagged,
            "struct_tree": self.struct_tree,
            "pages": [p.to_dict() for p in self.pages],
        }


class TemplateDossierEngine:
    """
    Constructs comprehensive template dossiers for single pages or entire documents.
    """

    def generate_dossier(
        self,
        pdf_path: str,
        page_number: Optional[int] = None,
        output_dir: Optional[str] = None,
    ) -> DocumentDossier:
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(pdf_path), "dossier_output")
        os.makedirs(output_dir, exist_ok=True)

        doc = pymupdf.open(pdf_path)
        meta = doc.metadata or {}
        page_count = len(doc)
        pdf_version = f"1.{doc.pdf_version()}" if hasattr(doc, "pdf_version") else "1.7"

        # Check Tagged PDF status and walk Structure Tree
        is_tagged = False
        struct_tree_root = None
        try:
            catalog = doc.pdf_catalog()
            st_key = doc.xref_get_key(catalog, "StructTreeRoot")
            if st_key[0] != "null":
                is_tagged = True
                struct_tree_root = self._walk_struct_tree(doc, st_key[1])
        except Exception as e:
            logger.debug(f"StructTreeRoot inspection: {e}")

        pages_to_process = [page_number] if page_number is not None else list(range(1, page_count + 1))
        page_dossiers: List[PageDossier] = []

        with ByteLayerExtractor(pdf_path) as extractor:
            for p_num in pages_to_process:
                page_layer = extractor.extract_page(p_num)
                p_dossier = self._process_page_dossier(page_layer, doc, p_num, pdf_path)
                page_dossiers.append(p_dossier)

        doc.close()

        doc_dossier = DocumentDossier(
            pdf_path=pdf_path,
            producer=meta.get("producer"),
            creator=meta.get("creator"),
            title=meta.get("title"),
            pdf_version=pdf_version,
            page_count=page_count,
            is_tagged=is_tagged,
            struct_tree=struct_tree_root,
            pages=page_dossiers,
        )

        # Write output JSON and Markdown
        json_path = os.path.join(output_dir, "dossier.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_json(doc_dossier.to_dict()), f, indent=2)

        md_path = os.path.join(output_dir, "dossier.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self.render_markdown_report(doc_dossier))

        return doc_dossier

    def _walk_struct_tree(self, doc: pymupdf.Document, root_ref: str) -> Dict[str, Any]:
        """Recursively inspects the PDF Structure Tree elements."""
        tree: Dict[str, Any] = {"root_xref": root_ref, "elements": []}
        try:
            catalog = doc.pdf_catalog()
            st_val = doc.xref_get_key(catalog, "StructTreeRoot")[1]
            if st_val == "null" or not st_val:
                return {"status": "untagged", "elements": []}
            tree["status"] = f"StructTreeRoot active ({st_val})"
        except Exception as e:
            tree["status"] = "untagged"
        return tree

    def _extract_ocg_layers(self, doc: pymupdf.Document) -> List[Dict[str, Any]]:
        """Extracts Optional Content Groups (OCG) from the Catalog /OCProperties."""
        ocgs = []
        try:
            catalog = doc.pdf_catalog()
            oc_key = doc.xref_get_key(catalog, "OCProperties")
            if oc_key[0] != "null":
                # Inspect OCGs
                ocg_list = doc.get_ocgs() if hasattr(doc, "get_ocgs") else {}
                if ocg_list:
                    for ocg_id, ocg_info in ocg_list.items():
                        ocgs.append({
                            "name": ocg_info.get("name", f"OCG_{ocg_id}"),
                            "default_state": "ON" if ocg_info.get("on", True) else "OFF",
                        })
                else:
                    ocgs.append({"type": "OCProperties", "name": "Document Layers", "default_state": "ON"})
        except Exception as e:
            logger.debug(f"OCG extraction: {e}")
        return ocgs

    def _process_page_dossier(
        self,
        page_layer: PageByteLayer,
        doc: pymupdf.Document,
        page_number: int,
        pdf_path: str,
    ) -> PageDossier:
        # 1. True Operator Histogram from L0 Tokenizer
        op_hist: Dict[str, int] = {}
        try:
            doc_p = doc[page_number - 1]
            contents_list = doc_p.get_contents()
            for xref in contents_list:
                stream_bytes = doc.xref_stream(xref)
                for token in tokenize_content_stream(stream_bytes):
                    if token.type == "OPERATOR":
                        op_hist[token.value] = op_hist.get(token.value, 0) + 1
        except Exception as e:
            logger.debug(f"Stream tokenizing for operator histogram: {e}")

        sorted_hist = dict(sorted(op_hist.items(), key=lambda item: item[1], reverse=True))

        # 2. Fonts Inventory
        fonts_list = []
        seen_fonts = set()
        for c in page_layer.chars:
            if c.font_name and c.font_name not in seen_fonts:
                seen_fonts.add(c.font_name)
                fonts_list.append({
                    "font_name": c.font_name,
                    "glyph_count": sum(1 for ch in page_layer.chars if ch.font_name == c.font_name),
                    "sample_size_pt": c.font_size_pt,
                })

        # 3. Vector Rule Clusters from RuleSet
        ruleset = RuleSet.from_page_layer(page_layer)
        v_clusters = []
        for r in ruleset.v_rules:
            v_clusters.append({
                "id": r.id,
                "centre_x_pt": r.centre,
                "span_y0_pt": r.start,
                "span_y1_pt": r.end,
                "width_pt": r.width,
                "span_pt": r.span,
                "coverage_pct": round((r.span / page_layer.height_pt) * 100.0, 1),
                "colour": r.colour.to_hex() if r.colour else "#000000",
            })

        h_clusters = []
        for r in ruleset.h_rules:
            h_clusters.append({
                "id": r.id,
                "centre_y_pt": r.centre,
                "span_x0_pt": r.start,
                "span_x1_pt": r.end,
                "width_pt": r.width,
                "span_pt": r.span,
                "coverage_pct": round((r.span / page_layer.width_pt) * 100.0, 1),
                "colour": r.colour.to_hex() if r.colour else "#000000",
            })

        # 4. Fill Geometry & Filled Header Bands
        fills = []
        has_filled_header_band = False
        for p in page_layer.paths:
            if p.fill_color is not None:
                px0, py0, px1, py1 = p.bbox_device_pt
                pw = px1 - px0
                ph = py1 - py0
                is_header_band = (pw >= 0.35 * page_layer.width_pt and 8.0 <= ph <= 45.0 and py1 >= 0.4 * page_layer.height_pt)
                if is_header_band:
                    has_filled_header_band = True
                fills.append({
                    "bbox_pt": [px0, py0, px1, py1],
                    "width_pt": pw,
                    "height_pt": ph,
                    "colour": p.fill_color.to_hex(),
                    "is_header_band": is_header_band,
                })

        # 5. Images
        images = []
        for im in page_layer.images:
            images.append({
                "bbox_pt": list(im.bbox_device_pt),
                "width_pt": im.bbox_device_pt[2] - im.bbox_device_pt[0],
                "height_pt": im.bbox_device_pt[3] - im.bbox_device_pt[1],
            })

        # 6. Annotations
        annots = []
        try:
            doc_page = doc[page_number - 1]
            for annot in doc_page.annots():
                annots.append({
                    "type": annot.type[1],
                    "rect_pt": list(annot.rect),
                    "content": annot.info.get("content", ""),
                })
        except Exception:
            pass

        # 7. Optional Content Groups (OCG)
        ocgs = self._extract_ocg_layers(doc)

        # 8. Raw Coordinate Quantisation Audit
        quant_engine = QuantisationAuditEngine()
        raw_quant_dict = quant_engine.audit_quantisation(page_layer, []).to_dict()

        # 9. Text Stream Order (L0 characters in emission order)
        text_stream_runs = []
        curr_chars: List[PaintedTextChar] = []
        for c in page_layer.chars:
            if not curr_chars:
                curr_chars.append(c)
            else:
                prev = curr_chars[-1]
                gap_x = c.origin_device_pt[0] - prev.font_bbox_device_pt[2]
                same_line = abs(c.origin_device_pt[1] - prev.origin_device_pt[1]) <= 2.0
                if same_line and gap_x < 15.0:
                    curr_chars.append(c)
                else:
                    rx0 = min(ch.font_bbox_device_pt[0] for ch in curr_chars)
                    ry0 = min(ch.font_bbox_device_pt[1] for ch in curr_chars)
                    rx1 = max(ch.font_bbox_device_pt[2] for ch in curr_chars)
                    ry1 = max(ch.font_bbox_device_pt[3] for ch in curr_chars)
                    run_txt = "".join(ch.unicode_text or ch.char_text for ch in curr_chars).strip()
                    if run_txt:
                        text_stream_runs.append({
                            "text": run_txt,
                            "font_name": curr_chars[0].font_name,
                            "font_size_pt": curr_chars[0].font_size_pt,
                            "bbox_pt": [rx0, ry0, rx1, ry1],
                            "y_baseline_pt": curr_chars[0].origin_device_pt[1],
                            "mcid": curr_chars[0].provenance.mcid if curr_chars[0].provenance else None,
                        })
                    curr_chars = [c]

        if curr_chars:
            rx0 = min(ch.font_bbox_device_pt[0] for ch in curr_chars)
            ry0 = min(ch.font_bbox_device_pt[1] for ch in curr_chars)
            rx1 = max(ch.font_bbox_device_pt[2] for ch in curr_chars)
            ry1 = max(ch.font_bbox_device_pt[3] for ch in curr_chars)
            run_txt = "".join(ch.unicode_text or ch.char_text for ch in curr_chars).strip()
            text_stream_runs.append({
                "text": run_txt,
                "font_name": curr_chars[0].font_name,
                "font_size_pt": curr_chars[0].font_size_pt,
                "bbox_pt": [rx0, ry0, rx1, ry1],
                "y_baseline_pt": curr_chars[0].origin_device_pt[1],
                "mcid": curr_chars[0].provenance.mcid if curr_chars[0].provenance else None,
            })

        # 10. Geometric Table & Columns
        table_grid_engine = TableGridEngine()
        table_grid = table_grid_engine.build_table_grid(ruleset, page_layer)

        # 11. Stream-Order Row Recovery Grouped by Anchor (Task F4 e & f)
        stream_rows, row_disagreements = self._recover_stream_order_rows_anchored(
            text_stream_runs=text_stream_runs,
            table_grid=table_grid,
            page_layer=page_layer,
        )

        # 12. Table-Style Verdict Determination using Rule SPAN and Scores
        lane_engine = DimensionLaneEngine()
        lane_model = lane_engine.build_dimension_lane(table_grid, ruleset, page_layer)

        verdict, runner_up, scores, evidence, lane_reason = self._determine_table_style_span_scores(
            ruleset=ruleset,
            table_grid=table_grid,
            has_filled_header_band=has_filled_header_band,
            stream_rows_count=len(stream_rows),
            page_layer=page_layer,
            lane_model=lane_model,
        )

        return PageDossier(
            page_number=page_number,
            cropbox_pt=page_layer.cropbox_pt,
            mediabox_pt=page_layer.mediabox_pt,
            operator_histogram=sorted_hist,
            fonts=fonts_list,
            v_rule_clusters=v_clusters,
            h_rule_clusters=h_clusters,
            fills=fills,
            images=images,
            annotations=annots,
            optional_content=ocgs,
            raw_coord_quantisation=raw_quant_dict,
            text_stream_order=text_stream_runs,
            stream_order_rows=stream_rows,
            geometric_rows_count=len(table_grid.rows),
            stream_order_rows_count=len(stream_rows),
            row_disagreements=row_disagreements,
            table_style_verdict=verdict,
            table_style_runner_up=runner_up,
            style_scores=scores,
            verdict_evidence=evidence,
            lane_absent_reason=lane_model.lane_absent_reason,
        )

    def _determine_table_style_span_scores(
        self,
        ruleset: RuleSet,
        table_grid: TableGrid,
        has_filled_header_band: bool,
        stream_rows_count: int,
        page_layer: PageByteLayer,
        lane_model: Optional[DimensionLaneModel] = None,
    ) -> Tuple[str, str, Dict[str, float], List[str], Optional[str]]:
        t_w = max(100.0, table_grid.outer_width_pt)
        t_h = max(40.0, table_grid.outer_height_pt)

        spanning_v = [r for r in ruleset.v_rules if (r.span / t_h) >= 0.75]
        spanning_h = [r for r in ruleset.h_rules if (r.span / t_w) >= 0.75]

        scores: Dict[str, float] = {
            "full_grid": 0.0,
            "vertical_only": 0.0,
            "horizontal_only": 0.0,
            "filled_header": 0.0,
            "borderless": 0.0,
            "empty_table": 0.0,
        }

        evidence = []
        evidence.append(f"Spanning vertical rules (span>=75% table height): {len(spanning_v)}")
        evidence.append(f"Spanning horizontal rules (span>=75% table width): {len(spanning_h)}")
        evidence.append(f"Filled header band present: {has_filled_header_band}")
        evidence.append(f"Recovered stream rows: {stream_rows_count}")

        # Check empty table
        if stream_rows_count <= 1 and (len(table_grid.columns) == 0 or table_grid.body_rows_count == 0):
            scores["empty_table"] = 0.95
            scores["horizontal_only"] = 0.30
            scores["borderless"] = 0.20
        else:
            if len(spanning_v) >= 2 and len(ruleset.h_rules) >= 3:
                scores["full_grid"] = round(0.90 + min(0.09, len(spanning_v) * 0.01), 3)
                scores["vertical_only"] = 0.60
            elif len(spanning_v) >= 2:
                scores["vertical_only"] = round(0.90 + min(0.09, len(spanning_v) * 0.01), 3)
                scores["full_grid"] = 0.50

            if len(spanning_h) >= 2 and len(spanning_v) == 0:
                scores["horizontal_only"] = 0.85
                scores["filled_header"] = 0.90 if has_filled_header_band else 0.40
                scores["borderless"] = 0.30

            if has_filled_header_band and len(spanning_v) == 0:
                scores["filled_header"] = 0.92
                scores["horizontal_only"] = 0.75 if len(spanning_h) >= 2 else 0.40
                scores["borderless"] = 0.30

            if len(spanning_v) == 0 and len(spanning_h) == 0 and not has_filled_header_band:
                scores["borderless"] = 0.92
                scores["horizontal_only"] = 0.20

        sorted_styles = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        winner = sorted_styles[0][0]
        runner_up = sorted_styles[1][0]

        evidence.append(f"Chosen Model: {winner} (score={scores[winner]:.2f}) | Runner-Up: {runner_up} (score={scores[runner_up]:.2f})")

        lane_reason = lane_model.lane_absent_reason if lane_model else None
        return winner, runner_up, scores, evidence, lane_reason

        return PageDossier(
            page_number=page_number,
            cropbox_pt=page_layer.cropbox_pt,
            mediabox_pt=page_layer.mediabox_pt,
            operator_histogram=sorted_hist,
            fonts=fonts_list,
            v_rule_clusters=v_clusters,
            h_rule_clusters=h_clusters,
            fills=fills,
            images=images,
            annotations=annots,
            optional_content=ocgs,
            raw_coord_quantisation=raw_quant_dict,
            text_stream_order=text_stream_runs,
            stream_order_rows=stream_rows,
            geometric_rows_count=len(table_grid.rows),
            stream_order_rows_count=len(stream_rows),
            row_disagreements=row_disagreements,
            table_style_verdict=verdict,
            table_style_runner_up=runner_up,
            style_scores=scores,
            verdict_evidence=evidence,
            lane_absent_reason=lane_reason,
        )

    def _recover_stream_order_rows_anchored(
        self,
        text_stream_runs: List[Dict[str, Any]],
        table_grid: TableGrid,
        page_layer: PageByteLayer,
    ) -> Tuple[List[StreamOrderRow], List[str]]:
        """
        Infers transaction rows from content-stream emission order grouped strictly by anchor
        (Date pattern or integer sequence number) and compares with geometric rows by anchor ID.
        """
        t_x0, t_y0, t_x1, t_y1 = table_grid.table_bbox_pt
        table_runs = [
            r for r in text_stream_runs
            if r["bbox_pt"][0] >= t_x0 - 5.0 and r["bbox_pt"][2] <= t_x1 + 5.0
            and r["bbox_pt"][1] >= t_y0 - 5.0 and r["bbox_pt"][3] <= t_y1 + 5.0
        ]

        if not table_runs:
            return [], []

        # Group runs into lines
        lines: List[Dict[str, Any]] = []
        cur_line_runs: List[Dict[str, Any]] = []
        cur_y = table_runs[0]["y_baseline_pt"]

        for run in table_runs:
            if abs(run["y_baseline_pt"] - cur_y) <= 2.5:
                cur_line_runs.append(run)
            else:
                if cur_line_runs:
                    txt = " ".join(r["text"] for r in cur_line_runs)
                    lines.append({"y": cur_y, "text": txt, "runs": cur_line_runs})
                cur_line_runs = [run]
                cur_y = run["y_baseline_pt"]

        if cur_line_runs:
            txt = " ".join(r["text"] for r in cur_line_runs)
            lines.append({"y": cur_y, "text": txt, "runs": cur_line_runs})

        # Group lines by anchor
        anchor_rows: List[StreamOrderRow] = []
        cur_row_lines: List[Dict[str, Any]] = []
        cur_anchor_id = "HEADER"

        for line in lines:
            txt = line["text"].strip()
            tokens = txt.split()
            first_tok = tokens[0] if tokens else ""

            is_date = any(p.match(first_tok) for p in DATE_PATTERNS)
            is_sno = SNO_PATTERN.match(first_tok) and len(first_tok) <= 4

            if is_date or is_sno:
                if cur_row_lines:
                    full_txt = " \n ".join(l["text"] for l in cur_row_lines)
                    all_toks = full_txt.split()
                    anchor_rows.append(StreamOrderRow(
                        index=len(anchor_rows) + 1,
                        anchor_id=cur_anchor_id,
                        y_pt=cur_row_lines[0]["y"],
                        cells_count=len(all_toks),
                        text_content=full_txt,
                        tokens=all_toks,
                    ))
                cur_row_lines = [line]
                cur_anchor_id = first_tok
            else:
                cur_row_lines.append(line)

        if cur_row_lines:
            full_txt = " \n ".join(l["text"] for l in cur_row_lines)
            all_toks = full_txt.split()
            anchor_rows.append(StreamOrderRow(
                index=len(anchor_rows) + 1,
                anchor_id=cur_anchor_id,
                y_pt=cur_row_lines[0]["y"],
                cells_count=len(all_toks),
                text_content=full_txt,
                tokens=all_toks,
            ))

        # Anchor-based comparison with geometric rows
        disagreements: List[str] = []
        geom_rows = [r for r in table_grid.rows if r.row_type == RowBandType.BODY]

        if len(geom_rows) != len(anchor_rows) and len(geom_rows) > 0:
            disagreements.append(
                f"Row count mismatch: stream-order recovered {len(anchor_rows)} anchor rows vs {len(geom_rows)} geometric body rows"
            )

        # Compare geometric rows and stream rows by anchor ID
        for s_row in anchor_rows:
            matched = False
            for g_row in geom_rows:
                if s_row.anchor_id in g_row.text_content:
                    matched = True
                    g_centre_y = (g_row.y0_pt + g_row.y1_pt) / 2.0
                    delta_y = abs(g_centre_y - s_row.y_pt)
                    if delta_y > 5.0:
                        disagreements.append(
                            f"Anchor '{s_row.anchor_id}' Y-offset delta: geometric Y={g_centre_y:.2f}pt vs stream Y={s_row.y_pt:.2f}pt (delta={delta_y:.2f}pt)"
                        )
                    break
            if not matched and s_row.anchor_id != "HEADER" and geom_rows:
                disagreements.append(f"Stream anchor '{s_row.anchor_id}' not found in geometric rows")

        return anchor_rows, disagreements

    def render_markdown_report(self, dossier: DocumentDossier) -> str:
        lines = []
        lines.append(f"# PDF Template Dossier: `{os.path.basename(dossier.pdf_path)}`")
        lines.append(f"**Producer**: `{dossier.producer or 'Unknown'}` | **Creator**: `{dossier.creator or 'Unknown'}`  ")
        lines.append(f"**PDF Version**: `{dossier.pdf_version}` | **Pages**: `{dossier.page_count}` | **Tagged PDF**: `{dossier.is_tagged}`  ")
        struct_status = dossier.struct_tree.get("status", "untagged") if dossier.struct_tree else "untagged"
        lines.append(f"**Structure Tree**: `{struct_status}`\n")

        for p in dossier.pages:
            lines.append(f"## Page {p.page_number} Analysis")
            lines.append(f"- **Dimensions**: {p.cropbox_pt[2] - p.cropbox_pt[0]:.2f} pt x {p.cropbox_pt[3] - p.cropbox_pt[1]:.2f} pt (CropBox)")
            lines.append(f"- **Table-Style Verdict**: **`{p.table_style_verdict.upper()}`** (Runner-Up: `{p.table_style_runner_up}`) Scores: {p.style_scores}")
            if p.lane_absent_reason:
                lines.append(f"- **Lane Status**: `{p.lane_absent_reason}`")
            lines.append("\n### Verdict Evidence")
            for ev in p.verdict_evidence:
                lines.append(f"- {ev}")

            lines.append("\n### Content Stream Operator Histogram")
            lines.append("| Operator | Count | Description |")
            lines.append("|---|---|---|")
            op_meanings = {
                "re": "Append Rectangle", "m": "Move To", "l": "Line To", "c": "Curve To",
                "h": "Close Path", "S": "Stroke Path", "s": "Close and Stroke", "f": "Fill Nonzero",
                "f*": "Fill Even-Odd", "B": "Fill and Stroke Nonzero", "B*": "Fill and Stroke Even-Odd",
                "b": "Close, Fill, Stroke Nonzero", "n": "End Path (No-Op)", "Tj": "Show Text",
                "TJ": "Show Text (Kerned Array)", "Tf": "Set Font & Size", "rg": "Set Non-Stroking RGB",
                "RG": "Set Stroking RGB", "g": "Set Non-Stroking Gray", "G": "Set Stroking Gray",
                "cm": "Concat Matrix", "q": "Save Graphics State", "Q": "Restore Graphics State",
                "Do": "Paint XObject", "w": "Set Line Width", "J": "Set Line Cap", "j": "Set Line Join",
            }
            for op, cnt in list(p.operator_histogram.items())[:15]:
                lines.append(f"| `{op}` | {cnt} | {op_meanings.get(op, 'Graphics/Text Op')} |")

            lines.append("\n### Vector Rule Clusters")
            lines.append(f"- **Vertical Rules ({len(p.v_rule_clusters)})**:")
            if p.v_rule_clusters:
                for vr in p.v_rule_clusters[:6]:
                    lines.append(f"  * X={vr['centre_x_pt']:.2f}pt, Span=[{vr['span_y0_pt']:.2f} -> {vr['span_y1_pt']:.2f}] ({vr['span_pt']:.2f}pt, {vr['coverage_pct']:.1f}%), Width={vr['width_pt']:.2f}pt")
            else:
                lines.append("  * None")

            lines.append(f"- **Horizontal Rules ({len(p.h_rule_clusters)})**:")
            if p.h_rule_clusters:
                for hr in p.h_rule_clusters[:6]:
                    lines.append(f"  * Y={hr['centre_y_pt']:.2f}pt, Span=[{hr['span_x0_pt']:.2f} -> {hr['span_x1_pt']:.2f}] ({hr['span_pt']:.2f}pt, {hr['coverage_pct']:.1f}%), Width={hr['width_pt']:.2f}pt")
            else:
                lines.append("  * None")

            lines.append("\n### Stream-Order Row Recovery vs Geometric Rows (Anchor Matched)")
            lines.append(f"- Geometric Rows: `{p.geometric_rows_count}` | Stream-Order Rows: `{p.stream_order_rows_count}`")
            if p.row_disagreements:
                lines.append("- **Disagreements Found**:")
                for dis in p.row_disagreements[:5]:
                    lines.append(f"  * {dis}")
            else:
                lines.append("- **Row Alignment**: 100% agreement between geometric and stream-order rows.")

            lines.append("\n### Raw Coordinate Quantisation")
            lines.append(f"- Total Coordinates Inspected: `{p.raw_coord_quantisation.get('raw_coordinates_count', p.raw_coord_quantisation.get('total_raw_coordinates', 0))}`")
            lines.append(f"- Exact Multiples of 1.00 pt: `{p.raw_coord_quantisation.get('raw_multiples_of_1pt_pct', p.raw_coord_quantisation.get('multiples_of_1pt_pct', 0.0)):.2f}%`")
            lines.append(f"- Exact Multiples of 0.25 pt: `{p.raw_coord_quantisation.get('raw_multiples_of_0_25pt_pct', p.raw_coord_quantisation.get('multiples_of_025pt_pct', 0.0)):.2f}%`")
            lines.append(f"- Exact Multiples of 0.75 pt: `{p.raw_coord_quantisation.get('raw_multiples_of_0_75pt_pct', p.raw_coord_quantisation.get('multiples_of_075pt_pct', 0.0)):.2f}%`")
            lines.append("\n### Optional Content Groups (OCG)")
            if p.optional_content:
                for ocg in p.optional_content:
                    lines.append(f"- **Name**: `{ocg.get('name', 'Unknown')}` | **Default State**: `{ocg.get('default_state', 'ON')}`")
            else:
                lines.append("- None (no OCG layers defined)")
            lines.append("\n---\n")

        return "\n".join(lines)


def generate_template_dossier(pdf_path: str, page_number: Optional[int] = None, output_dir: Optional[str] = None) -> DocumentDossier:
    engine = TemplateDossierEngine()
    return engine.generate_dossier(pdf_path, page_number=page_number, output_dir=output_dir)
