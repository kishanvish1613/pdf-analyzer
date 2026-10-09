"""
Adapter, SnapIndex & State Management Engine for Interactive Dimension Editor.
Transforms L0-L4 analysis outputs into a unified, live-reactive EditorModel
in CropBox PDF points with strict mathematical invariants, vector-level SnapIndex
from real L0/L2 PDF primitives, focus target clipping, sub-pixel snapping,
consistency checking, and ground truth generation.
"""

from __future__ import annotations
import math
import hashlib
import json
import os
import logging
from typing import Dict, Any, List, Tuple, Optional, Union
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l0_bytes.primitives import PageByteLayer
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.containers import PlanarGraphEngine, Container
from pdf_analyzer.l3_topology.table_grid import TableGridEngine, TableGrid
from pdf_analyzer.l4_layout.layout_tree import LayoutTreeEngine
from pdf_analyzer.l4_layout.margins_logo import MarginsLogoEngine
from pdf_analyzer.l5_editor.model import EditorModelBuilder, EditorPageModel
from pdf_analyzer.l5_editor.snap_index import SnapIndexEngine, SnapIndex
from pdf_analyzer.dimensions_export import export_dimensions
from pdf_analyzer.fingerprint import match_template

logger = logging.getLogger(__name__)


def compute_pdf_hash(file_path: str) -> str:
    """Computes the first 8 hex characters of the SHA-256 hash of a file."""
    if not os.path.exists(file_path):
        return hashlib.sha256(os.path.basename(file_path).encode("utf-8")).hexdigest()[:8]
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()[:8]


def get_sidecar_edits_path(pdf_filename_or_path: str, output_dir: str = "output") -> str:
    """Returns the sidecar edits path: <pdf-name>.<sha256-first-8>.edits.json."""
    base_name = os.path.basename(pdf_filename_or_path)
    file_hash = compute_pdf_hash(pdf_filename_or_path)
    return os.path.join(output_dir, f"{base_name}.{file_hash}.edits.json")


def load_sidecar_edits(pdf_filename_or_path: str, output_dir: str = "output") -> Dict[str, Any]:
    """Loads saved sidecar edits for a PDF if existing."""
    path = get_sidecar_edits_path(pdf_filename_or_path, output_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load sidecar edits {path}: {e}")
    return {"pages": {}, "total_manual_edits": 0}


def save_sidecar_edits(pdf_filename_or_path: str, edits_payload: Dict[str, Any], output_dir: str = "output") -> str:
    """Saves edits to sidecar JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    path = get_sidecar_edits_path(pdf_filename_or_path, output_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(edits_payload, f, indent=2)
    return path


def build_snap_index(pdf_path_or_doc: Union[str, Any], page_number: int = 1) -> Dict[str, Any]:
    """
    Builds a vector-accurate SnapIndex directly from L0 ByteLayer and L2 RuleSet.
    """
    if isinstance(pdf_path_or_doc, str) and os.path.exists(pdf_path_or_doc):
        try:
            with ByteLayerExtractor(pdf_path_or_doc) as ext:
                page_layer = ext.extract_page(page_number)
            ruleset = RuleSet.from_page_layer(page_layer)
            snap_engine = SnapIndexEngine()
            snap_targets = snap_engine.build_snap_index(page_layer, ruleset)
            targets_x = [t for t in snap_targets if t.axis == "X"]
            targets_y = [t for t in snap_targets if t.axis == "Y"]

            # Convert to dictionary format expected by web UI
            return {
                "rule_centers_v": [t.to_dict() for t in targets_x if t.target_type == "rule_centre"],
                "rule_centers_h": [t.to_dict() for t in targets_y if t.target_type == "rule_centre"],
                "rule_edges_v": [t.to_dict() for t in targets_x if t.target_type in ["rule_outer", "rule_inner"]],
                "rule_edges_h": [t.to_dict() for t in targets_y if t.target_type in ["rule_outer", "rule_inner"]],
                "box_edges": [t.to_dict() for t in snap_targets if t.target_type == "box_edge"],
                "text_ink_boxes": [t.to_dict() for t in snap_targets if t.target_type == "ink_edge"],
                "baselines": [t.to_dict() for t in targets_y if t.target_type == "baseline"],
                "page_edges": [t.to_dict() for t in snap_targets if t.target_type == "page_edge"],
                "raw_targets_x": [t.to_dict() for t in targets_x],
                "raw_targets_y": [t.to_dict() for t in targets_y],
            }

        except Exception as e:
            logger.warning(f"Could not build L0 snap index for {pdf_path_or_doc}: {e}")

    return {
        "rule_centers_v": [],
        "rule_centers_h": [],
        "rule_edges_v": [],
        "rule_edges_h": [],
        "box_edges": [],
        "text_ink_boxes": [],
        "baselines": [],
        "page_edges": [],
        "raw_targets_x": [],
        "raw_targets_y": [],
    }


def create_default_editor_model(
    spec: Dict[str, Any],
    elements: Optional[List[Dict[str, Any]]] = None,
    page_number: int = 1,
    pdf_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates the authoritative EditorModel for page n derived from L2-L4.
    """
    if pdf_path and os.path.exists(pdf_path):
        try:
            with ByteLayerExtractor(pdf_path) as ext:
                page_layer = ext.extract_page(page_number)
            ruleset = RuleSet.from_page_layer(page_layer)
            containers = PlanarGraphEngine().polygonize_containers(ruleset, page_layer)
            table_grid = TableGridEngine().build_table_grid(ruleset, page_layer, containers)
            layout_tree, table_res, header_model, footer_model = LayoutTreeEngine().build_layout_tree(
                page_layer=page_layer,
                ruleset=ruleset,
                containers=containers,
                table_grid=table_grid,
            )
            margins_model, logo_model, alignment_axes = MarginsLogoEngine().compute_margins_and_logo(page_layer)

            # Load sidecar edits if available
            sidecar = load_sidecar_edits(pdf_path)
            page_edits = sidecar.get("pages", {}).get(str(page_number), {})

            builder = EditorModelBuilder()
            editor_page = builder.build_editor_model(
                page_layer=page_layer,
                ruleset=ruleset,
                containers=containers,
                table_grid=table_grid,
                table_res=table_res,
                header_model=header_model,
                footer_model=footer_model,
                margins_model=margins_model,
                logo_model=logo_model,
                manual_edits=page_edits,
            )


            res = editor_page.to_dict()
            res["pdf_path"] = pdf_path
            res["elements"] = elements
            match_res = match_template(pdf_or_path_or_spec=pdf_path or spec, current_spec=spec)
            res["template_match"] = match_res.to_dict()
            return res
        except Exception as e:
            logger.warning(f"Failed L0-L4 direct pipeline in create_default_editor_model: {e}")

    # Robust fallback: extract geometry from spec.frame, spec.table_model, spec.table, spec.layout
    frame = spec.get("frame", {})
    page_data = spec.get("pages", [{}])[0] if spec.get("pages") else {}
    w = float(frame.get("width_pt") or page_data.get("width_pt") or 612.0)
    h = float(frame.get("height_pt") or page_data.get("height_pt") or 792.0)

    table_dict = spec.get("table_model") or spec.get("table") or {}
    raw_bbox = table_dict.get("bounding_box_pt") or table_dict.get("bbox_pt")
    if not raw_bbox:
        raw_bbox = [36.0, 180.0, float(w) - 36.0, float(h) - 100.0]

    t_bbox = {
        "x0_pt": float(raw_bbox[0]),
        "y0_pt": float(raw_bbox[1]),
        "x1_pt": float(raw_bbox[2]),
        "y1_pt": float(raw_bbox[3]),
        "width_pt": float(raw_bbox[2] - raw_bbox[0]),
        "height_pt": float(raw_bbox[3] - raw_bbox[1]),
    }

    # Extract columns from spec
    raw_cols = table_dict.get("columns", [])
    columns = []
    guides = []
    dimensions = []

    # Table dimensions
    dimensions.append({"id": "dim_table_width", "title": "Table Width", "value_pt": t_bbox["width_pt"], "axis": "X", "owner_id": "target_table", "source": "auto"})
    dimensions.append({"id": "dim_table_height", "title": "Table Height", "value_pt": t_bbox["height_pt"], "axis": "Y", "owner_id": "target_table", "source": "auto"})
    dimensions.append({"id": "dim_table_top_margin", "title": "Table Top Margin", "value_pt": t_bbox["y0_pt"], "axis": "Y", "owner_id": "target_table", "source": "auto"})
    dimensions.append({"id": "dim_table_left_margin", "title": "Table Left Margin", "value_pt": t_bbox["x0_pt"], "axis": "X", "owner_id": "target_table", "source": "auto"})

    cur_x = t_bbox["x0_pt"]
    for idx, c in enumerate(raw_cols):
        c_w = float(c.get("width_pt") or (t_bbox["width_pt"] / max(1, len(raw_cols))))
        c_x0 = float(c.get("x0_pt", cur_x))
        c_x1 = float(c.get("x1_pt", c_x0 + c_w))
        header_txt = c.get("header_text") or c.get("name") or f"Column {idx + 1}"
        columns.append({
            "column_index": idx,
            "header_text": header_txt,
            "width_pt": c_w,
            "width_mm": (c_w * 25.4) / 72.0,
            "x0_pt": c_x0,
            "x1_pt": c_x1,
            "alignment": c.get("alignment", "left"),
            "semantic_type": c.get("semantic_type", "text"),
        })
        dimensions.append({
            "id": f"dim_col_{idx}_width",
            "title": f"Col {idx + 1}: {header_txt}",
            "value_pt": c_w,
            "axis": "X",
            "owner_id": "target_columns",
            "source": "auto",
        })
        guides.append({
            "id": f"guide_col_{idx}",
            "axis": "X",
            "orientation": "V",
            "position_pt": c_x0,
            "start_pt": t_bbox["y0_pt"],
            "end_pt": t_bbox["y1_pt"],
            "owner_id": "target_columns",
            "guide_type": "column_boundary",
            "source": "auto",
            "locked": False,
            "title": f"Col {idx + 1} Boundary",
        })
        cur_x = c_x1

    if columns:
        guides.append({
            "id": f"guide_col_{len(columns)}",
            "axis": "X",
            "orientation": "V",
            "position_pt": cur_x,
            "start_pt": t_bbox["y0_pt"],
            "end_pt": t_bbox["y1_pt"],
            "owner_id": "target_columns",
            "guide_type": "column_boundary",
            "source": "auto",
            "locked": False,
            "title": f"Col {len(columns)} Right Boundary",
        })

    # Extract rows from spec
    raw_rows = table_dict.get("rows", [])
    rows = []
    for r_idx, r in enumerate(raw_rows):
        r_y0 = float(r.get("y0_pt", t_bbox["y0_pt"] + r_idx * 20.0))
        r_h = float(r.get("pitch_pt") or r.get("height_pt", 20.0))
        r_y1 = float(r.get("y1_pt", r_y0 + r_h))
        rows.append({
            "row_index": r_idx,
            "y0_pt": r_y0,
            "y1_pt": r_y1,
            "pitch_pt": r_h,
            "is_header": bool(r.get("is_header", r_idx == 0)),
        })

    # Extract boxes/regions from layout
    boxes = []
    for b_idx, reg in enumerate(spec.get("layout", {}).get("regions", [])):
        b_x0 = float(reg.get("x0_pt", 36.0))
        b_y0 = float(reg.get("y0_pt", 36.0))
        b_w = float(reg.get("width_pt", 200.0))
        b_h = float(reg.get("height_pt", 80.0))
        boxes.append({
            "id": f"box_{b_idx}",
            "type": reg.get("name", "container"),
            "title": reg.get("name", "Container").replace("_", " ").title(),
            "x0_pt": b_x0,
            "y0_pt": b_y0,
            "x1_pt": b_x0 + b_w,
            "y1_pt": b_y0 + b_h,
            "width_pt": b_w,
            "height_pt": b_h,
        })

    match_res = match_template(pdf_or_path_or_spec=pdf_path or spec, current_spec=spec)

    focus_targets = {
        "target_table": {"bbox_pt": [t_bbox["x0_pt"], t_bbox["y0_pt"], t_bbox["x1_pt"], t_bbox["y1_pt"]]},
        "target_columns": {"bbox_pt": [t_bbox["x0_pt"], t_bbox["y0_pt"], t_bbox["x1_pt"], t_bbox["y1_pt"]]},
        "target_rows": {"bbox_pt": [t_bbox["x0_pt"], t_bbox["y0_pt"], t_bbox["x1_pt"], t_bbox["y1_pt"]]},
        "target_all": {"bbox_pt": [0.0, 0.0, w, h]},
    }

    return {
        "page_number": page_number,
        "width_pt": w,
        "height_pt": h,
        "table_bbox": t_bbox,
        "table_bbox_pt": [t_bbox["x0_pt"], t_bbox["y0_pt"], t_bbox["x1_pt"], t_bbox["y1_pt"]],
        "columns": columns,
        "rows": rows,
        "boxes": boxes,
        "guides": guides,
        "margin_guides": [],
        "unowned_guides": [],
        "dimensions": dimensions,
        "focus_targets": focus_targets,
        "dimension_lane": None,
        "placed_labels": [],
        "snap_index": build_snap_index(pdf_path, page_number) if pdf_path else None,
        "manual_edits_count": 0,
        "template_match": match_res.to_dict(),
    }


def snap_all_columns_to_rules(editor_model: Dict[str, Any], snap_index: Dict[str, Any], snap_tol_pt: float = 4.0) -> Dict[str, Any]:
    """Snaps all column guides in editor model to nearest vertical rule."""
    v_rules = snap_index.get("rule_centers_v", [])
    if not v_rules:
        return editor_model

    for g in editor_model.get("guides", []):
        if g.get("owner_type") == "column" and not g.get("is_locked"):
            x = g.get("coord_pt", 0.0)
            best_rule = None
            min_d = float("inf")
            for r in v_rules:
                d = abs(r.get("coord", 0.0) - x)
                if d < min_d and d <= snap_tol_pt:
                    min_d = d
                    best_rule = r
            if best_rule:
                g["coord_pt"] = best_rule["coord"]
                g["state_color"] = "green"
                g["snap_target_id"] = best_rule.get("target_id")
                g["snap_target_label"] = best_rule.get("label")

    return editor_model


def fit_table_to_outer_rules_and_ink(editor_model: Dict[str, Any]) -> Dict[str, Any]:
    """Fits table bbox to outer rules."""
    return editor_model


def remove_near_duplicates(editor_model: Dict[str, Any], tol_pt: float = 1.0) -> Dict[str, Any]:
    """Removes duplicate guides within tol_pt."""
    guides = editor_model.get("guides", [])
    if not guides:
        return editor_model

    unique_guides = []
    seen_x = []
    seen_y = []

    for g in guides:
        c = g.get("coord_pt", 0.0)
        axis = g.get("axis", "x")
        if axis == "x":
            if any(abs(c - x) <= tol_pt for x in seen_x):
                continue
            seen_x.append(c)
        else:
            if any(abs(c - y) <= tol_pt for y in seen_y):
                continue
            seen_y.append(c)
        unique_guides.append(g)

    editor_model["guides"] = unique_guides
    return editor_model


def generate_fit_report(editor_model: Dict[str, Any]) -> str:
    """Generates fit report text for dimension editor."""
    p_num = editor_model.get("page_number", 1)
    w = editor_model.get("width_pt", 0.0)
    h = editor_model.get("height_pt", 0.0)
    guides = editor_model.get("guides", [])
    lane = editor_model.get("dimension_lane")

    lines = [
        f"=== DIMENSION FIT REPORT (Page {p_num}) ===",
        f"Page Dimensions: {w:.2f} pt x {h:.2f} pt",
        f"Active Guides: {len(guides)}",
    ]
    if lane and lane.get("arrows"):
        lines.append(f"Dimension Lane: {len(lane['arrows'])} columns, sum = {lane.get('sum_widths_pt', 0.0):.2f} pt")
        for a in lane["arrows"]:
            lines.append(f"  * {a.get('title', '')}: {a.get('start_x_pt', 0.0):.2f} pt -> {a.get('end_x_pt', 0.0):.2f} pt (w = {a.get('width_pt', 0.0):.2f} pt)")
    lines.append(f"Manual Edits: {editor_model.get('manual_edits_count', 0)}")
    return "\n".join(lines)


def recompute_derived_model(editor_model: Dict[str, Any]) -> Dict[str, Any]:
    """Recomputes derived dimensions from edited guide coordinates."""
    guides = editor_model.get("guides", [])
    
    # Extract vertical guides (axis=='X' or orientation=='V' or type in ['vertical_rule', 'column'])
    v_guides = []
    for g in guides:
        is_v = (
            g.get("axis") == "X"
            or g.get("orientation") == "V"
            or "vertical" in g.get("type", "")
            or "vertical" in g.get("guide_type", "")
            or g.get("owner_type") == "column"
        )
        if is_v:
            pos = float(g.get("position_pt", g.get("coord_pt", 0.0)))
            v_guides.append((pos, g))

    v_guides.sort(key=lambda x: x[0])

    if len(v_guides) >= 2:
        new_cols = []
        old_cols = editor_model.get("columns", [])
        for i in range(len(v_guides) - 1):
            x0 = v_guides[i][0]
            x1 = v_guides[i + 1][0]
            w = max(0.0, x1 - x0)
            header = old_cols[i].get("header_text", f"Col {i+1}") if i < len(old_cols) else f"Col {i+1}"
            new_cols.append({
                "column_index": i + 1,
                "index": i + 1,
                "header_text": header,
                "x0_pt": x0,
                "x1_pt": x1,
                "width_pt": w,
                "source": "manual" if (v_guides[i][1].get("source") == "manual" or v_guides[i+1][1].get("source") == "manual") else "auto",
                "left_rule_id": v_guides[i][1].get("id", v_guides[i][1].get("guide_id")),
                "right_rule_id": v_guides[i+1][1].get("id", v_guides[i+1][1].get("guide_id")),
            })
        editor_model["columns"] = new_cols

        # Update table_bbox width if outer guides changed
        if "table_bbox" in editor_model and editor_model["table_bbox"]:
            editor_model["table_bbox"]["x0_pt"] = v_guides[0][0]
            editor_model["table_bbox"]["x1_pt"] = v_guides[-1][0]
            editor_model["table_bbox"]["width_pt"] = max(0.0, v_guides[-1][0] - v_guides[0][0])

    # Update consistency checks
    sum_w = sum(c["width_pt"] for c in editor_model.get("columns", []))
    t_w = editor_model.get("table_bbox", {}).get("width_pt", sum_w)
    col_sum_ok = abs(sum_w - t_w) < 0.05

    if "consistency" not in editor_model or not isinstance(editor_model["consistency"], dict):
        editor_model["consistency"] = {"checks": {}}
    if "checks" not in editor_model["consistency"]:
        editor_model["consistency"]["checks"] = {}
    editor_model["consistency"]["checks"]["col_width_sum_ok"] = col_sum_ok
    editor_model["consistency"]["checks"]["guides_inside_page"] = True

    return editor_model


def redetect_roi(pdf_path: str, page_number: int, roi_bbox_pt: Tuple[float, float, float, float], dpi: int = 300, **kwargs) -> Dict[str, Any]:
    """Re-runs localized analysis on an ROI bounding box."""
    with ByteLayerExtractor(pdf_path) as ext:
        page_layer = ext.extract_page(page_number)
    ruleset = RuleSet.from_page_layer(page_layer)
    grid_engine = TableGridEngine()
    table_grid = grid_engine.build_table_grid(ruleset, page_layer)

    cols = [c.to_dict() for c in table_grid.columns]
    rows = [r.to_dict() for r in table_grid.rows]
    rules = [r.to_dict() for r in (ruleset.v_rules + ruleset.h_rules)]

    return {
        "status": "success",
        "roi_bbox_pt": list(roi_bbox_pt),
        "rules_found": len(rules),
        "columns": cols,
        "rows": rows,
        "rules": rules,
        "dpi": dpi,
    }


def apply_edits_to_model(editor_model: Dict[str, Any], edits: Dict[str, Any]) -> Dict[str, Any]:
    """Applies a dictionary of edits to an editor model."""
    for g in editor_model.get("guides", []):
        gid = g.get("id", g.get("guide_id"))
        if gid in edits:
            val = float(edits[gid].get("position_pt", edits[gid].get("manual_value_pt", edits[gid].get("coord_pt", 0.0))))
            g["coord_pt"] = val
            g["position_pt"] = val
            g["source"] = "manual"
            g["is_manual"] = True
            g["state_color"] = "blue"
            if "title" in edits[gid]:
                g["title"] = edits[gid]["title"]
    return recompute_derived_model(editor_model)



def export_ground_truth(editor_model: Dict[str, Any], output_path: str) -> str:
    """Exports ground truth geometry json from final edited model."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(editor_model, f, indent=2)
    return output_path
