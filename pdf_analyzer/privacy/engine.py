"""
Privacy Transformation Engine.
Applies redaction or synthetic data substitution to document specifications,
editor models, and layout geometries while preserving layout invariance.
"""

from __future__ import annotations
import copy
from typing import Dict, Any, List, Optional, Tuple

from pdf_analyzer.privacy.pii_detector import PIIDetector, PIIMatch, RedactionRecord, PIIReport
from pdf_analyzer.privacy.redactor import RedactionEngine
from pdf_analyzer.privacy.synthetic import SyntheticDataEngine


class PrivacyEngine:
    """Orchestrates PII detection, redaction, and synthetic substitution."""

    def __init__(self, seed: int = 42, default_font: str = "Helvetica", default_size_pt: float = 8.0):
        self.detector = PIIDetector()
        self.redactor = RedactionEngine(default_font=default_font, default_size_pt=default_size_pt)
        self.synthetic = SyntheticDataEngine(seed=seed, default_font=default_font, default_size_pt=default_size_pt)

    def transform_text(
        self,
        text: str,
        category: str,
        mode: str = "synthetic",
        font_name: Optional[str] = None,
        font_size_pt: Optional[float] = None
    ) -> Tuple[str, float]:
        """Transforms a single text item according to privacy mode."""
        if not text or not isinstance(text, str):
            return text, 0.0

        if mode == "real":
            return text, 0.0

        if mode == "redacted":
            return self.redactor.redact_text(text, font_name=font_name, font_size_pt=font_size_pt)
        elif mode == "synthetic":
            return self.synthetic.substitute_text(text, category=category, font_name=font_name, font_size_pt=font_size_pt)
        return text, 0.0

    def apply_privacy_transform(
        self,
        spec: Dict[str, Any],
        mode: str = "synthetic",
        font_name: str = "Helvetica",
        font_size_pt: float = 8.0
    ) -> Tuple[Dict[str, Any], PIIReport]:
        """
        Deep-transforms a specification dictionary into a privacy-protected spec.
        Returns: (transformed_spec, pii_report)
        """
        if not spec or not isinstance(spec, dict):
            empty_report = PIIReport(total_detected=0, categories={}, redactions=[], privacy_mode=mode)
            return spec, empty_report

        new_spec = copy.deepcopy(spec)
        redactions: List[RedactionRecord] = []
        category_counts: Dict[str, int] = {}

        def record_redaction(cat: str, orig: str, repl: str, bbox: Optional[List[float]] = None, w_delta: float = 0.0):
            category_counts[cat] = category_counts.get(cat, 0) + 1
            redactions.append(RedactionRecord(
                category=cat,
                original_text=orig,
                replaced_text=repl,
                bbox_pt=bbox,
                width_delta_pt=w_delta
            ))

        # 1. Transform Account Details
        acct = new_spec.get("account_details", {})
        if isinstance(acct, dict):
            # Fields
            for field_item in acct.get("fields", []):
                if isinstance(field_item, dict):
                    k = field_item.get("key", "")
                    v = field_item.get("value", "")
                    if v:
                        matches = self.detector.detect_in_text(v, field_context=k)
                        cat = matches[0].category if matches else ("ACCOUNT_NUMBER" if "account" in k.lower() else "GENERAL")
                        new_v, w_delta = self.transform_text(v, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                        field_item["value"] = new_v
                        record_redaction(cat, v, new_v, field_item.get("bbox_pt"), w_delta)

            # Address Box
            addr_box = acct.get("address_box", {})
            if isinstance(addr_box, dict):
                lines = addr_box.get("lines", [])
                new_lines = []
                for i, line in enumerate(lines):
                    cat = "NAME" if i == 0 else "ADDRESS"
                    new_l, w_delta = self.transform_text(line, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                    new_lines.append(new_l)
                    record_redaction(cat, line, new_l, w_delta=w_delta)
                addr_box["lines"] = new_lines

            # Colon Grid
            grid = acct.get("colon_grid", {})
            if isinstance(grid, dict):
                for row in grid.get("rows", []):
                    if isinstance(row, dict):
                        k = row.get("key", "")
                        v = row.get("value", "")
                        if v:
                            cat = "ACCOUNT_NUMBER" if "acc" in k.lower() or "cif" in k.lower() else ("NAME" if "name" in k.lower() else "GENERAL")
                            new_v, w_delta = self.transform_text(v, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                            row["value"] = new_v
                            record_redaction(cat, v, new_v, w_delta=w_delta)

        # 2. Transform Key Values
        kv_data = new_spec.get("key_values", {})
        kv_list = kv_data.get("entities", []) if isinstance(kv_data, dict) else (kv_data if isinstance(kv_data, list) else [])
        for kv in kv_list:
            if isinstance(kv, dict):
                k = kv.get("key") or kv.get("key_text", "")
                v = kv.get("value") or kv.get("value_text") or kv.get("val_text", "")
                if v:
                    matches = self.detector.detect_in_text(v, field_context=k)
                    cat = matches[0].category if matches else ("ACCOUNT_NUMBER" if "acc" in k.lower() else "GENERAL")
                    new_v, w_delta = self.transform_text(v, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                    if "value" in kv:
                        kv["value"] = new_v
                    if "value_text" in kv:
                        kv["value_text"] = new_v
                    if "val_text" in kv:
                        kv["val_text"] = new_v
                    record_redaction(cat, v, new_v, kv.get("bbox_pt") or kv.get("value_bbox_pt"), w_delta)

        # 3. Transform Header Blocks
        hb_data = new_spec.get("header_blocks", {})
        hb_list = hb_data.get("blocks", []) if isinstance(hb_data, dict) else (hb_data if isinstance(hb_data, list) else [])
        for hb in hb_list:
            if isinstance(hb, dict):
                sub_blocks = hb.get("sub_blocks", [hb])
                for sb in sub_blocks:
                    if isinstance(sb, dict):
                        lines = sb.get("lines", sb.get("text_lines", []))
                        if isinstance(lines, list):
                            new_lines = []
                            for ln in lines:
                                if isinstance(ln, dict):
                                    if "segments" in ln and isinstance(ln["segments"], list):
                                        for seg in ln["segments"]:
                                            stxt = seg.get("text", "")
                                            if stxt:
                                                matches = self.detector.detect_in_text(stxt)
                                                cat = matches[0].category if matches else "GENERAL"
                                                new_s, w_delta = self.transform_text(
                                                    stxt, category=cat, mode=mode,
                                                    font_name=seg.get("font_name", font_name),
                                                    font_size_pt=float(seg.get("font_size_pt", font_size_pt))
                                                )
                                                seg["text"] = new_s
                                                record_redaction(cat, stxt, new_s, seg.get("bbox_pt"), w_delta)
                                    if "text" in ln and ln["text"]:
                                        matches = self.detector.detect_in_text(ln["text"])
                                        cat = matches[0].category if matches else "GENERAL"
                                        new_lt, w_delta = self.transform_text(ln["text"], category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                                        ln["text"] = new_lt
                                    if "raw_text" in ln and ln["raw_text"]:
                                        matches = self.detector.detect_in_text(ln["raw_text"])
                                        cat = matches[0].category if matches else "GENERAL"
                                        new_rt, w_delta = self.transform_text(ln["raw_text"], category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                                        ln["raw_text"] = new_rt
                                    new_lines.append(ln)
                                elif isinstance(ln, str):
                                    matches = self.detector.detect_in_text(ln)
                                    cat = matches[0].category if matches else "GENERAL"
                                    new_l, w_delta = self.transform_text(ln, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                                    new_lines.append(new_l)
                                    record_redaction(cat, ln, new_l, w_delta=w_delta)
                            if "lines" in sb:
                                sb["lines"] = new_lines
                            if "text_lines" in sb:
                                sb["text_lines"] = new_lines


        # 4. Transform Table Rows & Cells
        for tbl_key in ["table_model", "table"]:
            tbl = new_spec.get(tbl_key)
            if isinstance(tbl, dict):
                rows = tbl.get("rows", [])
                for r in rows:
                    if isinstance(r, dict):
                        cells = r.get("cells", [])
                        for c in cells:
                            if isinstance(c, dict):
                                c_text = c.get("text", "")
                                if c_text:
                                    matches = self.detector.detect_in_text(c_text, field_context="table_cell")
                                    cat = matches[0].category if matches else ("AMOUNT" if re.match(r'^\d+[\.,]\d+$', c_text.strip()) else "GENERAL")
                                    new_c, w_delta = self.transform_text(c_text, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                                    c["text"] = new_c
                                    record_redaction(cat, c_text, new_c, c.get("bbox_pt"), w_delta)
                        if "raw_text" in r and r["raw_text"]:
                            matches = self.detector.detect_in_text(r["raw_text"])
                            cat = matches[0].category if matches else "GENERAL"
                            new_rt, w_delta = self.transform_text(r["raw_text"], category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                            r["raw_text"] = new_rt
                        if "text_summary" in r and r["text_summary"]:
                            matches = self.detector.detect_in_text(r["text_summary"])
                            cat = matches[0].category if matches else "GENERAL"
                            new_ts, w_delta = self.transform_text(r["text_summary"], category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                            r["text_summary"] = new_ts

        # 5. Transform Footer Blocks
        fb_data = new_spec.get("footer_blocks", {})
        fb_list = fb_data.get("sub_blocks", []) if isinstance(fb_data, dict) else (fb_data if isinstance(fb_data, list) else [])
        for fb in fb_list:
            if isinstance(fb, dict) and "text" in fb:
                f_text = fb["text"]
                matches = self.detector.detect_in_text(f_text, field_context="footer")
                if matches:
                    cat = matches[0].category
                    new_ft, w_delta = self.transform_text(f_text, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                    fb["text"] = new_ft
                    record_redaction(cat, f_text, new_ft, fb.get("bbox_pt"), w_delta)

        # Build final report
        report = PIIReport(
            total_detected=len(redactions),
            categories=category_counts,
            redactions=redactions,
            privacy_mode=mode
        )
        new_spec["pii_report"] = report.to_dict()
        new_spec["privacy_mode"] = mode

        return new_spec, report

    def apply_privacy_to_editor_model(
        self,
        model: Dict[str, Any],
        mode: str = "synthetic",
        font_name: str = "Helvetica",
        font_size_pt: float = 8.0
    ) -> Tuple[Dict[str, Any], PIIReport]:
        """Transforms an EditorModel dictionary so exports and prompts contain protected data."""
        if not model or not isinstance(model, dict):
            empty_report = PIIReport(total_detected=0, categories={}, redactions=[], privacy_mode=mode)
            return model, empty_report

        new_model = copy.deepcopy(model)
        redactions: List[RedactionRecord] = []
        category_counts: Dict[str, int] = {}

        def record_redaction(cat: str, orig: str, repl: str, bbox: Optional[List[float]] = None, w_delta: float = 0.0):
            category_counts[cat] = category_counts.get(cat, 0) + 1
            redactions.append(RedactionRecord(
                category=cat,
                original_text=orig,
                replaced_text=repl,
                bbox_pt=bbox,
                width_delta_pt=w_delta
            ))

        # 1. Transform Boxes
        boxes = new_model.get("boxes", [])
        for b in boxes:
            if isinstance(b, dict):
                # Text lines in customer card or header
                if "text_lines" in b and isinstance(b["text_lines"], list):
                    new_lines = []
                    for i, line in enumerate(b["text_lines"]):
                        cat = "NAME" if i == 0 else "ADDRESS"
                        new_l, w_delta = self.transform_text(line, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                        new_lines.append(new_l)
                        record_redaction(cat, line, new_l, w_delta=w_delta)
                    b["text_lines"] = new_lines

                # Key-value entries
                if "kv_entries" in b and isinstance(b["kv_entries"], list):
                    for kv in b["kv_entries"]:
                        if isinstance(kv, dict):
                            k = kv.get("key", "")
                            v = kv.get("value", "")
                            if v:
                                matches = self.detector.detect_in_text(v, field_context=k)
                                cat = matches[0].category if matches else ("ACCOUNT_NUMBER" if "acc" in k.lower() or "cif" in k.lower() else "GENERAL")
                                new_v, w_delta = self.transform_text(v, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                                kv["value"] = new_v
                                record_redaction(cat, v, new_v, w_delta=w_delta)

        # 2. Transform Rows and Cells
        rows = new_model.get("rows", [])
        for r in rows:
            if isinstance(r, dict):
                for cell in r.get("cells", []):
                    if isinstance(cell, dict):
                        c_text = cell.get("text", "")
                        if c_text:
                            matches = self.detector.detect_in_text(c_text)
                            cat = matches[0].category if matches else "GENERAL"
                            new_c, w_delta = self.transform_text(c_text, category=cat, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
                            cell["text"] = new_c
                            record_redaction(cat, c_text, new_c, w_delta=w_delta)

        report = PIIReport(
            total_detected=len(redactions),
            categories=category_counts,
            redactions=redactions,
            privacy_mode=mode
        )
        new_model["pii_report"] = report.to_dict()
        new_model["privacy_mode"] = mode

        return new_model, report


def apply_privacy_transform(
    spec: Dict[str, Any],
    mode: str = "synthetic",
    font_name: str = "Helvetica",
    font_size_pt: float = 8.0
) -> Tuple[Dict[str, Any], PIIReport]:
    """Top-level convenience function for applying privacy transformations."""
    engine = PrivacyEngine(default_font=font_name, default_size_pt=font_size_pt)
    return engine.apply_privacy_transform(spec, mode=mode, font_name=font_name, font_size_pt=font_size_pt)


def apply_privacy_to_editor_model(
    model: Dict[str, Any],
    mode: str = "synthetic",
    font_name: str = "Helvetica",
    font_size_pt: float = 8.0
) -> Tuple[Dict[str, Any], PIIReport]:
    """Top-level convenience function for applying privacy transformations to an editor model."""
    engine = PrivacyEngine(default_font=font_name, default_size_pt=font_size_pt)
    return engine.apply_privacy_to_editor_model(model, mode=mode, font_name=font_name, font_size_pt=font_size_pt)
