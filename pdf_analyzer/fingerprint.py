"""
Template Fingerprinting, Matching, and Regression Diffing Engine.

1. Fingerprint = normalized anchor phrases (bank name, header labels, footer text)
   + coarse geometry hash (page size, rounded table bbox, column count, header row y-band).
   Stored as JSON in templates/fingerprints/.
2. match_template(pdf_or_path_or_spec) returns best match and similarity score;
   below threshold returns "unknown".
3. On a match, loads stored spec as a PRIOR and diffs it against fresh extraction.
   Reports each difference as either "new template version" or "possible extraction regression"
   with the numeric delta.
4. Integrated into L5 Editor Model and regression test suites.
"""

from __future__ import annotations
import os
import re
import glob
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Optional, Union
import pymupdf
import numpy as np

from pdf_analyzer.utils.json_sanitizer import sanitize_for_json

logger = logging.getLogger(__name__)

DEFAULT_FINGERPRINTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "fingerprints")
DEFAULT_BASELINES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "baselines")


def normalize_anchor_text(text: str) -> str:
    """Normalizes text: lowercase, removes variable numbers/dates/symbols, trims whitespace."""
    if not text:
        return ""
    t = text.lower().strip()
    # Replace dates like DD/MM/YYYY, DD-MMM-YYYY, YYYY-MM-DD
    t = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "", t)
    t = re.sub(r"\b\d{1,2}-[a-z]{3}-\d{2,4}\b", "", t)
    t = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", t)
    # Replace long numbers (account numbers, reference numbers, amounts)
    t = re.sub(r"\b\d{4,}\b", "", t)
    t = re.sub(r"\b\d+([.,]\d+)+\b", "", t)
    # Keep alphanumeric, basic slashes, dashes, parentheses, ampersands
    t = re.sub(r"[^a-z0-9\s/()\-&.]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


@dataclass
class CoarseGeometryHash:
    page_width_pt: float
    page_height_pt: float
    column_count: int
    table_bbox_rounded: Optional[List[float]] = None  # [x0, y0, x1, y1] rounded to 1 pt
    header_y_band_rounded: Optional[List[float]] = None  # [y0, y1] rounded to 1 pt

    def to_hash_str(self) -> str:
        w = round(self.page_width_pt, 1)
        h = round(self.page_height_pt, 1)
        c = int(self.column_count)
        tb_str = "_".join(str(round(v, 1)) for v in self.table_bbox_rounded) if self.table_bbox_rounded else "NONE"
        hb_str = "_".join(str(round(v, 1)) for v in self.header_y_band_rounded) if self.header_y_band_rounded else "NONE"
        return f"W{w}_H{h}_C{c}_TB_{tb_str}_HB_{hb_str}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_width_pt": round(self.page_width_pt, 2),
            "page_height_pt": round(self.page_height_pt, 2),
            "column_count": self.column_count,
            "table_bbox_rounded": self.table_bbox_rounded,
            "header_y_band_rounded": self.header_y_band_rounded,
            "hash_str": self.to_hash_str(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CoarseGeometryHash:
        return cls(
            page_width_pt=float(data.get("page_width_pt", 0.0)),
            page_height_pt=float(data.get("page_height_pt", 0.0)),
            column_count=int(data.get("column_count", 0)),
            table_bbox_rounded=data.get("table_bbox_rounded"),
            header_y_band_rounded=data.get("header_y_band_rounded"),
        )


@dataclass
class DiffRecord:
    property_name: str
    prior_value: Any
    current_value: Any
    delta_pt: Optional[float]
    classification: str  # "new template version" | "possible extraction regression"
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property_name": self.property_name,
            "prior_value": self.prior_value,
            "current_value": self.current_value,
            "delta_pt": round(self.delta_pt, 4) if self.delta_pt is not None else None,
            "classification": self.classification,
            "reason": self.reason,
        }


@dataclass
class TemplateFingerprint:
    template_id: str
    bank_name: str
    anchor_phrases: List[str]
    geometry: CoarseGeometryHash
    description: str = ""
    version: str = "1.0"
    prior_baseline_filename: Optional[str] = None
    prior_spec: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "bank_name": self.bank_name,
            "description": self.description,
            "version": self.version,
            "anchor_phrases": self.anchor_phrases,
            "geometry": self.geometry.to_dict(),
            "prior_baseline_filename": self.prior_baseline_filename,
            "prior_spec": self.prior_spec,
        }

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_json(self.to_dict()), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> TemplateFingerprint:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TemplateFingerprint:
        geom_data = data.get("geometry", {})
        geometry = CoarseGeometryHash.from_dict(geom_data)
        return cls(
            template_id=data.get("template_id", "unknown"),
            bank_name=data.get("bank_name", "Unknown Bank"),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            anchor_phrases=data.get("anchor_phrases", []),
            geometry=geometry,
            prior_baseline_filename=data.get("prior_baseline_filename"),
            prior_spec=data.get("prior_spec"),
        )


@dataclass
class TemplateMatchResult:
    template_id: str
    similarity_score: float
    anchor_score: float
    geometry_score: float
    matched_anchors: List[str]
    is_match: bool
    bank_name: str = "Unknown"
    prior_spec: Optional[Dict[str, Any]] = None
    diffs: List[DiffRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "similarity_score": round(self.similarity_score, 4),
            "anchor_score": round(self.anchor_score, 4),
            "geometry_score": round(self.geometry_score, 4),
            "matched_anchors": self.matched_anchors,
            "is_match": self.is_match,
            "bank_name": self.bank_name,
            "diff_count": len(self.diffs),
            "diffs": [d.to_dict() for d in self.diffs],
        }


class FingerprintExtractor:
    """Extracts anchor phrases, text corpus, and coarse geometry hash from PDFs or specs."""

    @staticmethod
    def extract_from_pdf(pdf_path: str, page_number: int = 1) -> Tuple[str, List[str], CoarseGeometryHash, Optional[str]]:
        doc = pymupdf.open(pdf_path)
        if len(doc) == 0:
            return "", [], CoarseGeometryHash(0, 0, 0), None

        p_idx = max(0, min(len(doc) - 1, page_number - 1))
        page = doc[p_idx]
        cb = page.cropbox
        width_pt = cb.width
        height_pt = cb.height

        # Extract text across first 2 pages for robust document-level anchors
        pages_to_scan = [doc[i] for i in range(min(2, len(doc)))]
        full_text = " ".join(p.get_text("text") for p in pages_to_scan)
        norm_full_text = normalize_anchor_text(full_text)

        # Extract individual line-level phrases
        raw_phrases = []
        for p in pages_to_scan:
            for b in p.get_text("blocks"):
                if len(b) > 4 and isinstance(b[4], str):
                    for line in b[4].split("\n"):
                        norm = normalize_anchor_text(line)
                        if norm and len(norm) >= 3 and not norm.isdigit():
                            raw_phrases.append(norm)

        doc.close()

        # Identify unique anchor phrases
        anchors = []
        seen = set()
        for p in raw_phrases:
            if p not in seen:
                seen.add(p)
                anchors.append(p)

        geometry = CoarseGeometryHash(
            page_width_pt=round(width_pt, 1),
            page_height_pt=round(height_pt, 1),
            column_count=0,
            table_bbox_rounded=None,
            header_y_band_rounded=None,
        )

        # Infer bank name from text if available
        detected_bank = None
        if "state bank of india" in norm_full_text or "sbi.16450" in norm_full_text:
            detected_bank = "State Bank of India"
        elif "kotak" in norm_full_text or "kkbk" in norm_full_text:
            detected_bank = "Kotak Mahindra Bank"
        elif "bank of india" in norm_full_text or "bkid" in norm_full_text:
            detected_bank = "Bank of India"
        elif "hdfc" in norm_full_text:
            detected_bank = "HDFC Bank"
        elif "union bank of india" in norm_full_text or "ubin" in norm_full_text:
            detected_bank = "Union Bank of India"

        return norm_full_text, anchors, geometry, detected_bank

    @staticmethod
    def extract_from_spec(spec: Dict[str, Any]) -> Tuple[str, List[str], CoarseGeometryHash, Optional[str]]:
        meta = spec.get("meta", {})
        width_pt = float(meta.get("width", {}).get("pt", meta.get("width_pt", 595.0)))
        height_pt = float(meta.get("height", {}).get("pt", meta.get("height_pt", 842.0)))

        # Extract table geometry
        table = spec.get("table", {})
        t_bbox = table.get("bbox", {})
        table_bbox_rounded = None
        if t_bbox:
            x0 = float(t_bbox.get("x0", {}).get("pt", 0.0))
            y0 = float(t_bbox.get("y0", {}).get("pt", 0.0))
            x1 = float(t_bbox.get("x1", {}).get("pt", 0.0))
            y1 = float(t_bbox.get("y1", {}).get("pt", 0.0))
            if x1 > x0 and y1 > y0:
                table_bbox_rounded = [round(x0), round(y0), round(x1), round(y1)]

        cols = table.get("columns", [])
        col_count = len(cols) if cols else 0
        if not col_count and "table_model" in spec:
            col_count = len(spec.get("table_model", {}).get("columns", []))

        # Extract header y-band
        header_y_band_rounded = None
        header_reg = spec.get("layout", {}).get("regions", [])
        for r in header_reg:
            if r.get("region_type") == "header" and "bbox" in r:
                hb = r["bbox"]
                hy0 = float(hb.get("y0", {}).get("pt", 0.0))
                hy1 = float(hb.get("y1", {}).get("pt", 0.0))
                if hy1 > hy0:
                    header_y_band_rounded = [round(hy0), round(hy1)]
                break

        # Extract anchor phrases
        anchors = []
        seen = set()
        text_tokens = []

        # 1. Bank name from account details / header
        acct = spec.get("account_details", {})
        bank_name = acct.get("bank_name", {}).get("value", "")
        if bank_name:
            norm_b = normalize_anchor_text(bank_name)
            if norm_b:
                text_tokens.append(norm_b)
                if norm_b not in seen:
                    seen.add(norm_b)
                    anchors.append(norm_b)

        # 2. Table column header texts
        for c in cols:
            ht = c.get("header_text", "")
            if ht:
                norm_ht = normalize_anchor_text(ht)
                if norm_ht:
                    text_tokens.append(norm_ht)
                    if norm_ht not in seen:
                        seen.add(norm_ht)
                        anchors.append(norm_ht)

        # 3. Typography titles or header lines
        typo = spec.get("typography", {}).get("styles", [])
        for s in typo:
            txt = s.get("sample_text", "")
            if txt:
                norm_t = normalize_anchor_text(txt)
                if norm_t:
                    text_tokens.append(norm_t)
                    if len(norm_t) >= 4 and norm_t not in seen:
                        seen.add(norm_t)
                        anchors.append(norm_t)

        norm_full_text = " ".join(text_tokens)

        geometry = CoarseGeometryHash(
            page_width_pt=round(width_pt, 1),
            page_height_pt=round(height_pt, 1),
            column_count=col_count,
            table_bbox_rounded=table_bbox_rounded,
            header_y_band_rounded=header_y_band_rounded,
        )

        return norm_full_text, anchors, geometry, bank_name or None


def compute_anchor_similarity(norm_doc_text: str, query_anchors: List[str], target_anchors: List[str]) -> Tuple[float, List[str]]:
    """
    Computes text phrase overlap similarity between document text/anchors and target template anchors.
    Checks presence of target anchor phrases inside document text or phrase list.
    Returns (score, matched_phrases).
    """
    if not target_anchors:
        return 0.0, []

    matched = []
    query_set = set(query_anchors)

    for target_a in target_anchors:
        norm_ta = normalize_anchor_text(target_a)
        if not norm_ta:
            continue

        # Direct phrase match in document text or query anchors
        if norm_ta in norm_doc_text or norm_ta in query_set:
            matched.append(target_a)
            continue

        # Token set match
        ta_tokens = set(norm_ta.split())
        if len(ta_tokens) >= 2:
            if all(tok in norm_doc_text for tok in ta_tokens):
                matched.append(target_a)
                continue
            for qa in query_anchors:
                qa_tokens = set(qa.split())
                if len(qa_tokens) >= 2:
                    jaccard = len(ta_tokens & qa_tokens) / len(ta_tokens | qa_tokens)
                    if jaccard >= 0.7:
                        matched.append(target_a)
                        break

    score = len(matched) / len(target_anchors)
    return float(np.clip(score, 0.0, 1.0)), matched


def compute_geometry_similarity(query_geom: CoarseGeometryHash, target_geom: CoarseGeometryHash) -> float:
    """Computes similarity of coarse geometry (page size, column count, bbox, header band)."""
    # 1. Page Dimensions Match (within 2 pt)
    w_match = 1.0 if abs(query_geom.page_width_pt - target_geom.page_width_pt) <= 2.0 else 0.0
    h_match = 1.0 if abs(query_geom.page_height_pt - target_geom.page_height_pt) <= 2.0 else 0.0
    size_score = (w_match + h_match) / 2.0

    # 2. Column Count Match
    if query_geom.column_count > 0 and target_geom.column_count > 0:
        if query_geom.column_count == target_geom.column_count:
            col_score = 1.0
        else:
            diff = abs(query_geom.column_count - target_geom.column_count)
            col_score = max(0.0, 1.0 - (diff / max(query_geom.column_count, target_geom.column_count)))
    else:
        col_score = 0.5  # Neutral when column count not yet determined in query

    # 3. Table Bounding Box Match
    tbl_score = 0.5
    if query_geom.table_bbox_rounded and target_geom.table_bbox_rounded:
        q_tb = query_geom.table_bbox_rounded
        t_tb = target_geom.table_bbox_rounded
        dx0 = abs(q_tb[0] - t_tb[0])
        dy0 = abs(q_tb[1] - t_tb[1])
        dx1 = abs(q_tb[2] - t_tb[2])
        dy1 = abs(q_tb[3] - t_tb[3])
        avg_err = (dx0 + dy0 + dx1 + dy1) / 4.0
        if avg_err <= 5.0:
            tbl_score = 1.0
        elif avg_err <= 25.0:
            tbl_score = max(0.0, 1.0 - (avg_err / 25.0))
        else:
            tbl_score = 0.0

    # 4. Header Y-band Match
    hdr_score = 0.5
    if query_geom.header_y_band_rounded and target_geom.header_y_band_rounded:
        q_hb = query_geom.header_y_band_rounded
        t_hb = target_geom.header_y_band_rounded
        dy0 = abs(q_hb[0] - t_hb[0])
        dy1 = abs(q_hb[1] - t_hb[1])
        avg_err = (dy0 + dy1) / 2.0
        if avg_err <= 5.0:
            hdr_score = 1.0
        elif avg_err <= 20.0:
            hdr_score = max(0.0, 1.0 - (avg_err / 20.0))
        else:
            hdr_score = 0.0

    total_geom_score = 0.40 * size_score + 0.35 * col_score + 0.15 * tbl_score + 0.10 * hdr_score
    return float(np.clip(total_geom_score, 0.0, 1.0))


def diff_spec_against_prior(prior_spec: Dict[str, Any], current_spec: Dict[str, Any]) -> List[DiffRecord]:
    """
    Diffs fresh extraction specification against stored PRIOR specification.
    Classifies differences as 'new template version' (structural/large) or
    'possible extraction regression' (geometric drift/small deltas).
    """
    diffs: List[DiffRecord] = []
    if not prior_spec or not current_spec:
        return diffs

    # 1. Compare Column Counts
    p_cols = prior_spec.get("table", {}).get("columns", [])
    if not p_cols and "table_model" in prior_spec:
        p_cols = prior_spec.get("table_model", {}).get("columns", [])

    c_cols = current_spec.get("table", {}).get("columns", [])
    if not c_cols and "table_model" in current_spec:
        c_cols = current_spec.get("table_model", {}).get("columns", [])

    if len(p_cols) != len(c_cols):
        diffs.append(DiffRecord(
            property_name="table.column_count",
            prior_value=len(p_cols),
            current_value=len(c_cols),
            delta_pt=None,
            classification="new template version",
            reason=f"Column count changed structurally from {len(p_cols)} to {len(c_cols)}",
        ))
    else:
        # 2. Compare Per-Column Widths
        for i in range(len(p_cols)):
            p_c = p_cols[i]
            c_c = c_cols[i]
            p_w = float(p_c.get("width", {}).get("pt", p_c.get("width_pt", 0.0)))
            c_w = float(c_c.get("width", {}).get("pt", c_c.get("width_pt", 0.0)))
            delta_w = abs(c_w - p_w)

            if delta_w > 0.05:
                if delta_w > 15.0:
                    cls_type = "new template version"
                    reason = f"Column {i+1} width changed by {delta_w:.2f} pt (> 15 pt threshold)"
                else:
                    cls_type = "possible extraction regression"
                    reason = f"Column {i+1} width drifted by {delta_w:.2f} pt from baseline ({p_w:.2f} -> {c_w:.2f} pt)"

                diffs.append(DiffRecord(
                    property_name=f"table.columns[{i}].width_pt",
                    prior_value=round(p_w, 2),
                    current_value=round(c_w, 2),
                    delta_pt=round(delta_w, 3),
                    classification=cls_type,
                    reason=reason,
                ))

    # 3. Compare Table Bounding Box
    p_t_bbox = prior_spec.get("table", {}).get("bbox", {})
    c_t_bbox = current_spec.get("table", {}).get("bbox", {})
    if p_t_bbox and c_t_bbox:
        for coord in ["x0", "y0", "x1", "y1"]:
            p_val = float(p_t_bbox.get(coord, {}).get("pt", 0.0))
            c_val = float(c_t_bbox.get(coord, {}).get("pt", 0.0))
            delta = abs(c_val - p_val)
            if delta > 0.5:
                if delta > 20.0:
                    cls_type = "new template version"
                    reason = f"Table {coord} shifted by {delta:.2f} pt (> 20 pt threshold)"
                else:
                    cls_type = "possible extraction regression"
                    reason = f"Table {coord} position delta {delta:.2f} pt ({p_val:.2f} -> {c_val:.2f} pt)"

                diffs.append(DiffRecord(
                    property_name=f"table.bbox.{coord}_pt",
                    prior_value=round(p_val, 2),
                    current_value=round(c_val, 2),
                    delta_pt=round(delta, 3),
                    classification=cls_type,
                    reason=reason,
                ))

    # 4. Compare Page Margins
    p_margins = prior_spec.get("margins_spacing", {}).get("page_margins", {})
    c_margins = current_spec.get("margins_spacing", {}).get("page_margins", {})
    if p_margins and c_margins:
        for m_name in ["top", "bottom", "left", "right"]:
            p_m = float(p_margins.get(m_name, {}).get("pt", 0.0))
            c_m = float(c_margins.get(m_name, {}).get("pt", 0.0))
            delta_m = abs(c_m - p_m)
            if delta_m > 1.0:
                if delta_m > 25.0:
                    cls_type = "new template version"
                    reason = f"Page {m_name} margin changed by {delta_m:.2f} pt (> 25 pt threshold)"
                else:
                    cls_type = "possible extraction regression"
                    reason = f"Page {m_name} margin drifted by {delta_m:.2f} pt ({p_m:.2f} -> {c_m:.2f} pt)"

                diffs.append(DiffRecord(
                    property_name=f"margins.{m_name}_pt",
                    prior_value=round(p_m, 2),
                    current_value=round(c_m, 2),
                    delta_pt=round(delta_m, 3),
                    classification=cls_type,
                    reason=reason,
                ))

    # 5. Compare Table Style Verdict
    p_style = prior_spec.get("dossier", {}).get("table_style_verdict") or prior_spec.get("template_profile", {}).get("style")
    c_style = current_spec.get("dossier", {}).get("table_style_verdict") or current_spec.get("template_profile", {}).get("style")
    if p_style and c_style and p_style != c_style:
        diffs.append(DiffRecord(
            property_name="table.style_verdict",
            prior_value=p_style,
            current_value=c_style,
            delta_pt=None,
            classification="new template version",
            reason=f"Table style verdict changed from {p_style} to {c_style}",
        ))

    return diffs


def load_all_fingerprints(fingerprints_dir: str = DEFAULT_FINGERPRINTS_DIR) -> List[TemplateFingerprint]:
    """Loads all template fingerprints from disk. If folder empty, creates standard library."""
    os.makedirs(fingerprints_dir, exist_ok=True)
    json_files = glob.glob(os.path.join(fingerprints_dir, "*.json"))
    if not json_files:
        _generate_standard_fingerprints(fingerprints_dir)
        json_files = glob.glob(os.path.join(fingerprints_dir, "*.json"))

    fps: List[TemplateFingerprint] = []
    for f_path in sorted(json_files):
        try:
            fp = TemplateFingerprint.load(f_path)
            # Check if prior spec needs loading from baselines
            if not fp.prior_spec and fp.prior_baseline_filename:
                base_p = os.path.join(DEFAULT_BASELINES_DIR, fp.prior_baseline_filename)
                if os.path.exists(base_p):
                    try:
                        with open(base_p, "r", encoding="utf-8") as bf:
                            fp.prior_spec = json.load(bf)
                    except Exception as be:
                        logger.debug(f"Could not load baseline {base_p}: {be}")
            fps.append(fp)
        except Exception as e:
            logger.warning(f"Failed to load fingerprint {f_path}: {e}")
    return fps


def match_template(
    pdf_or_path_or_spec: Union[str, Dict[str, Any], pymupdf.Document],
    fingerprints_dir: str = DEFAULT_FINGERPRINTS_DIR,
    threshold: float = 0.50,
    current_spec: Optional[Dict[str, Any]] = None,
) -> TemplateMatchResult:
    """
    Matches an input PDF or spec dictionary against stored template fingerprints.
    Returns best match with similarity score; if score < threshold, returns 'unknown'.
    On match, loads stored spec as a PRIOR and diffs against fresh extraction.
    """
    fingerprints = load_all_fingerprints(fingerprints_dir)
    if not fingerprints:
        return TemplateMatchResult(
            template_id="unknown",
            similarity_score=0.0,
            anchor_score=0.0,
            geometry_score=0.0,
            matched_anchors=[],
            is_match=False,
            bank_name="Unknown",
        )

    # Extract query anchors and geometry
    if isinstance(pdf_or_path_or_spec, dict):
        norm_doc_text, query_anchors, query_geom, query_bank = FingerprintExtractor.extract_from_spec(pdf_or_path_or_spec)
        target_spec = current_spec or pdf_or_path_or_spec
    elif isinstance(pdf_or_path_or_spec, str) and os.path.exists(pdf_or_path_or_spec):
        norm_doc_text, query_anchors, query_geom, query_bank = FingerprintExtractor.extract_from_pdf(pdf_or_path_or_spec)
        target_spec = current_spec
    else:
        return TemplateMatchResult(
            template_id="unknown",
            similarity_score=0.0,
            anchor_score=0.0,
            geometry_score=0.0,
            matched_anchors=[],
            is_match=False,
        )

    best_fp: Optional[TemplateFingerprint] = None
    best_total_score = -1.0
    best_anchor_score = 0.0
    best_geom_score = 0.0
    best_matched_anchors: List[str] = []

    for fp in fingerprints:
        a_score, m_anchors = compute_anchor_similarity(norm_doc_text, query_anchors, fp.anchor_phrases)
        g_score = compute_geometry_similarity(query_geom, fp.geometry)

        # Combined similarity score: 75% anchors + 25% geometry
        total_score = 0.75 * a_score + 0.25 * g_score

        # Boost score if known bank name is explicitly matched in text or query
        if a_score > 0.0 and fp.bank_name:
            norm_b = normalize_anchor_text(fp.bank_name)
            if norm_b in norm_doc_text or (query_bank and norm_b in normalize_anchor_text(query_bank)):
                total_score = min(1.0, total_score + 0.10)

        # If zero anchors matched, do not allow false match purely on page dimensions
        if a_score == 0.0:
            total_score = 0.0

        if total_score > best_total_score:
            best_total_score = total_score
            best_fp = fp
            best_anchor_score = a_score
            best_geom_score = g_score
            best_matched_anchors = m_anchors

    if best_fp and best_total_score >= threshold:
        diffs = []
        if best_fp.prior_spec and target_spec:
            diffs = diff_spec_against_prior(best_fp.prior_spec, target_spec)

        return TemplateMatchResult(
            template_id=best_fp.template_id,
            similarity_score=round(best_total_score, 4),
            anchor_score=round(best_anchor_score, 4),
            geometry_score=round(best_geom_score, 4),
            matched_anchors=best_matched_anchors,
            is_match=True,
            bank_name=best_fp.bank_name,
            prior_spec=best_fp.prior_spec,
            diffs=diffs,
        )

    return TemplateMatchResult(
        template_id="unknown",
        similarity_score=round(max(0.0, best_total_score), 4),
        anchor_score=round(best_anchor_score, 4),
        geometry_score=round(best_geom_score, 4),
        matched_anchors=[],
        is_match=False,
        bank_name="Unknown",
        diffs=[],
    )


def _generate_standard_fingerprints(output_dir: str) -> None:
    """Generates initial seed fingerprints for known corpus templates."""
    os.makedirs(output_dir, exist_ok=True)

    # 1. State Bank of India (Full Grid)
    sbi = TemplateFingerprint(
        template_id="state_bank_of_india_full_grid",
        bank_name="State Bank of India",
        description="SBI Standard Retail Statement with full grid table borders",
        anchor_phrases=[
            "state bank of india",
            "account summary",
            "cif number",
            "date of statement",
            "clear balance",
            "drawing power",
            "monthly avg balance",
            "sbi.16450",
        ],
        geometry=CoarseGeometryHash(
            page_width_pt=595.0,
            page_height_pt=842.0,
            column_count=7,
            table_bbox_rounded=[20.0, 150.0, 575.0, 735.0],
            header_y_band_rounded=[150.0, 175.0],
        ),
        prior_baseline_filename="RAVIN18081966.json",
    )
    sbi.save(os.path.join(output_dir, "state_bank_of_india.json"))

    # 2. Kotak Mahindra Bank (Filled Header)
    kotak = TemplateFingerprint(
        template_id="kotak_mahindra_filled_header",
        bank_name="Kotak Mahindra Bank",
        description="Kotak Mahindra Bank statement with filled header band and zebra striping",
        anchor_phrases=[
            "account statement",
            "crn",
            "kkbk",
            "account no",
            "withdrawal (dr",
            "deposit (cr",
            "chq/ref",
            "savings account transactions",
        ],
        geometry=CoarseGeometryHash(
            page_width_pt=595.0,
            page_height_pt=842.0,
            column_count=6,
            table_bbox_rounded=[44.0, 310.0, 551.0, 770.0],
            header_y_band_rounded=[310.0, 335.0],
        ),
        prior_baseline_filename="AccountStatement_01-Sep-2026_17-Sep-2026.json",
    )
    kotak.save(os.path.join(output_dir, "kotak_mahindra.json"))

    # 3. Bank of India (Full Grid)
    boi = TemplateFingerprint(
        template_id="bank_of_india_full_grid",
        bank_name="Bank of India",
        description="Bank of India Statement with 7-column full grid layout",
        anchor_phrases=[
            "bank of india",
            "bkid",
            "custid",
            "opening balance",
            "statement of account",
            "tran date",
            "debits",
            "credits",
            "balance",
            "sno",
        ],
        geometry=CoarseGeometryHash(
            page_width_pt=792.0,
            page_height_pt=842.0,
            column_count=7,
            table_bbox_rounded=[36.0, 140.0, 756.0, 780.0],
            header_y_band_rounded=[140.0, 165.0],
        ),
        prior_baseline_filename="shivay orthocare feb 25 to jan 26.json",
    )
    boi.save(os.path.join(output_dir, "bank_of_india.json"))

    # 4. HDFC Bank (Vertical Only)
    hdfc = TemplateFingerprint(
        template_id="hdfc_bank_vertical_only",
        bank_name="HDFC Bank",
        description="HDFC Bank statement with vertical column rules and no horizontal rules",
        anchor_phrases=[
            "narration",
            "chq./ref",
            "value dt",
            "withdrawal amt",
            "deposit amt",
            "closing balance",
            "hdfc",
            "account statement",
        ],
        geometry=CoarseGeometryHash(
            page_width_pt=638.0,
            page_height_pt=842.0,
            column_count=7,
            table_bbox_rounded=[30.0, 200.0, 608.0, 780.0],
            header_y_band_rounded=[200.0, 225.0],
        ),
        prior_baseline_filename="bank-statement-acct-statement-2821-18082026-14-33-43-178774592089581590_.json",
    )
    hdfc.save(os.path.join(output_dir, "hdfc_bank.json"))

    # 5. Union Bank of India (Filled Header)
    ubi = TemplateFingerprint(
        template_id="union_bank_of_india_filled_header",
        bank_name="Union Bank of India",
        description="Union Bank of India wide landscape format statement",
        anchor_phrases=[
            "union bank of india",
            "ubin",
            "statement of account",
            "customer id",
            "account no",
            "tran id",
            "remarks",
            "utr number",
            "ckyc number",
        ],
        geometry=CoarseGeometryHash(
            page_width_pt=782.0,
            page_height_pt=1100.0,
            column_count=8,
            table_bbox_rounded=[40.0, 220.0, 742.0, 1000.0],
            header_y_band_rounded=[220.0, 245.0],
        ),
        prior_baseline_filename="bank-statement-optransactionhistoryux3-pdf11-06-2026-178160404281321470_.json",
    )
    ubi.save(os.path.join(output_dir, "union_bank_of_india.json"))
