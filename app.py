"""Web UI application for PDF Design Analyzer with Interactive Dimension Editor.

Provides a drag-and-drop web dashboard, live visual inspection,
interactive Dimension Editor with sub-pixel snapping, Focus Mode, & ROI re-detection,
and file download endpoints.

Run:
    python app.py
Open:
    http://localhost:5000
"""

import os
import json
import time
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
import pandas as pd
import pymupdf

from pdf_analyzer.gst.gstr3b_generator import generate_gstr3b_pdf, get_default_gstr3b_data, get_gstr3b_metadata, generate_gstr3b_ai_prompt
from pdf_analyzer.gst.gstr3b_html import generate_gstr3b_html

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline
from pdf_analyzer.editor_model import (
    compute_pdf_hash,
    create_default_editor_model,
    build_snap_index,
    snap_all_columns_to_rules,
    fit_table_to_outer_rules_and_ink,
    remove_near_duplicates,
    generate_fit_report,
    save_sidecar_edits,
    load_sidecar_edits,
    recompute_derived_model,
    redetect_roi,
    apply_edits_to_model,
    export_ground_truth
)
from pdf_analyzer.dimensions_export import export_dimensions
from pdf_analyzer.utils.json_sanitizer import sanitize_for_json
from generate_sample_pdf import create_synthetic_statement
from regenerator import regenerate_html_css, regenerate_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_FOLDER = os.path.join(os.path.dirname(__file__), "static")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "output")

os.makedirs(STATIC_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__, template_folder="templates")


def resolve_pdf_path(doc_id: str) -> str:
    """Resolves document identifier or filename to local PDF path."""
    if not doc_id or doc_id in ("sample", "default", "sample_statement.pdf"):
        sample_path = os.path.join(OUTPUT_FOLDER, "sample_statement.pdf")
        if not os.path.exists(sample_path):
            create_synthetic_statement(sample_path)
        return sample_path

    # Check upload folder
    upload_path = os.path.join(UPLOAD_FOLDER, doc_id)
    if os.path.exists(upload_path):
        return upload_path

    # Check output folder
    out_path = os.path.join(OUTPUT_FOLDER, doc_id)
    if os.path.exists(out_path):
        return out_path

    return os.path.join(OUTPUT_FOLDER, "sample_statement.pdf")


@app.route("/")
def index():
    """Render main Web UI dashboard."""
    return render_template("index.html")


@app.route("/editor")
def editor_page():
    """Render standalone Dimension Editor page for a given document."""
    doc_id = request.args.get("doc", "sample")
    return render_template("index.html", initial_doc_id=doc_id)


@app.route("/static/<path:filename>")
def serve_static_file(filename):
    """Serve static JS / CSS assets."""
    return send_from_directory(STATIC_FOLDER, filename)


@app.route("/output/<path:filename>")
def serve_output_file(filename):
    """Serve generated artifacts (images, json, csv, pdf, html)."""
    return send_from_directory(OUTPUT_FOLDER, filename)


@app.route("/api/pdf-info", methods=["POST", "GET"])
def get_pdf_info():
    """Returns page count and metadata for a PDF file or uploaded document."""
    try:
        if request.method == "POST" and "pdf" in request.files:
            file = request.files["pdf"]
            safe_name = os.path.basename(file.filename)
            pdf_path = os.path.join(UPLOAD_FOLDER, safe_name)
            file.save(pdf_path)
            doc_id = safe_name
        else:
            doc_id = request.args.get("doc", "sample")
            pdf_path = resolve_pdf_path(doc_id)

        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        pages_meta = []
        for idx in range(total_pages):
            p = doc[idx]
            cb = p.cropbox
            pages_meta.append({
                "page_number": idx + 1,
                "width_pt": float(cb.width),
                "height_pt": float(cb.height),
            })
        doc.close()
        return jsonify({
            "status": "success",
            "doc_id": doc_id,
            "total_pages": total_pages,
            "pages": pages_meta
        })
    except Exception as e:
        logger.exception("Failed to get PDF info")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sample", methods=["POST"])
def analyze_sample():
    """Generate and analyze the built-in synthetic bank statement for a selected page."""
    try:
        sample_pdf_path = os.path.join(OUTPUT_FOLDER, "sample_statement.pdf")
        create_synthetic_statement(sample_pdf_path)

        dpi = int(request.form.get("dpi", 300))
        page_val = request.form.get("page") or request.form.get("pages") or "1"
        try:
            page_num = int(str(page_val).lower().replace("page", "").replace("_", "").strip())
        except Exception:
            page_num = 1

        doc = pymupdf.open(sample_pdf_path)
        total_pages = len(doc)
        page_num = max(1, min(total_pages, page_num))
        doc.close()

        config = AnalyzerConfig(dpi=dpi, pages=str(page_num), output_dir=OUTPUT_FOLDER)
        pipeline = AnalysisPipeline(config)
        spec = pipeline.process_document(sample_pdf_path, OUTPUT_FOLDER, page_number=page_num)

        # Regenerate artifacts
        regenerate_html_css(spec, os.path.join(OUTPUT_FOLDER, "reproduced_layout.html"))
        regenerate_pdf(spec, os.path.join(OUTPUT_FOLDER, "reproduced_statement.pdf"))

        elements_csv = os.path.join(OUTPUT_FOLDER, "elements.csv")
        elements = []
        if os.path.exists(elements_csv):
            df = pd.read_csv(elements_csv, keep_default_na=False).fillna("")
            elements = df.to_dict(orient="records")

        md_path = os.path.join(OUTPUT_FOLDER, "design_report.md")
        md_text = ""
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()

        editor_model = create_default_editor_model(spec, elements, page_number=page_num, pdf_path=sample_pdf_path)
        editor_model["total_pages"] = total_pages

        ts = int(time.time())
        payload = {
            "status": "success",
            "doc_id": "sample_statement.pdf",
            "filename": "sample_statement.pdf",
            "page_number": page_num,
            "total_pages": total_pages,
            "spec": spec,
            "editor_model": editor_model,
            "markdown_text": md_text,
            "elements": elements,
            "urls": {
                "json": f"/output/design_spec.json?v={ts}",
                "markdown": f"/output/design_report.md?v={ts}",
                "csv": f"/output/elements.csv?v={ts}",
                "page_image": f"/output/page_{page_num}.png?v={ts}",
                "annotated_image": f"/output/annotated_page_{page_num}.png?v={ts}",
                "logo": f"/output/extracted_logo.png?v={ts}",
                "reproduced_html": f"/output/reproduced_layout.html?v={ts}",
                "reproduced_pdf": f"/output/reproduced_statement.pdf?v={ts}"
            }
        }
        return jsonify(sanitize_for_json(payload))
    except Exception as e:
        logger.exception("Sample analysis failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def upload_and_analyze():
    """Upload a bank statement PDF and execute extraction pipeline on the selected page."""
    file = request.files.get("pdf") or request.files.get("file")
    if not file:
        return jsonify({"error": "No PDF file uploaded"}), 400

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files supported"}), 400

    try:
        safe_name = os.path.basename(file.filename)
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(pdf_path)

        dpi = int(request.form.get("dpi", 300))
        page_val = request.form.get("page") or request.form.get("pages") or "1"
        try:
            page_num = int(str(page_val).lower().replace("page", "").replace("_", "").strip())
        except Exception:
            page_num = 1

        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        page_num = max(1, min(total_pages, page_num))
        doc.close()

        config = AnalyzerConfig(dpi=dpi, pages=str(page_num), output_dir=OUTPUT_FOLDER)
        pipeline = AnalysisPipeline(config)
        spec = pipeline.process_document(pdf_path, OUTPUT_FOLDER, page_number=page_num)

        # Regenerate artifacts
        regenerate_html_css(spec, os.path.join(OUTPUT_FOLDER, "reproduced_layout.html"))
        regenerate_pdf(spec, os.path.join(OUTPUT_FOLDER, "reproduced_statement.pdf"))

        elements_csv = os.path.join(OUTPUT_FOLDER, "elements.csv")
        elements = []
        if os.path.exists(elements_csv):
            df = pd.read_csv(elements_csv, keep_default_na=False).fillna("")
            elements = df.to_dict(orient="records")

        md_path = os.path.join(OUTPUT_FOLDER, "design_report.md")
        md_text = ""
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()

        editor_model = create_default_editor_model(spec, elements, page_number=page_num, pdf_path=pdf_path)
        editor_model["total_pages"] = total_pages

        ts = int(time.time())
        payload = {
            "status": "success",
            "doc_id": safe_name,
            "filename": safe_name,
            "page_number": page_num,
            "total_pages": total_pages,
            "spec": spec,
            "editor_model": editor_model,
            "template_match": editor_model.get("template_match"),
            "markdown_text": md_text,
            "elements": elements,
            "urls": {
                "json": f"/output/design_spec.json?v={ts}",
                "markdown": f"/output/design_report.md?v={ts}",
                "csv": f"/output/elements.csv?v={ts}",
                "page_image": f"/output/page_{page_num}.png?v={ts}",
                "annotated_image": f"/output/annotated_page_{page_num}.png?v={ts}",
                "logo": f"/output/extracted_logo.png?v={ts}",
                "reproduced_html": f"/output/reproduced_layout.html?v={ts}",
                "reproduced_pdf": f"/output/reproduced_statement.pdf?v={ts}"
            }
        }
        return jsonify(sanitize_for_json(payload))
    except Exception as e:
        logger.exception("Upload analysis failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze-page", methods=["POST"])
def analyze_specific_page():
    """Executes deep reverse-engineering and layout extraction on a single selected page."""
    try:
        data = request.get_json(force=True) if request.is_json else request.form
        doc_id = data.get("doc_id") or request.args.get("doc") or "sample"
        page_val = data.get("page") or data.get("page_number") or 1
        try:
            page_num = int(str(page_val).lower().replace("page", "").replace("_", "").strip())
        except Exception:
            page_num = 1
        dpi = int(data.get("dpi", 300))

        pdf_path = resolve_pdf_path(doc_id)
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        page_num = max(1, min(total_pages, page_num))
        doc.close()

        config = AnalyzerConfig(dpi=dpi, pages=str(page_num), output_dir=OUTPUT_FOLDER)
        pipeline = AnalysisPipeline(config)
        spec = pipeline.process_document(pdf_path, OUTPUT_FOLDER, page_number=page_num)

        # Regenerate artifacts
        regenerate_html_css(spec, os.path.join(OUTPUT_FOLDER, "reproduced_layout.html"))
        regenerate_pdf(spec, os.path.join(OUTPUT_FOLDER, "reproduced_statement.pdf"))

        elements_csv = os.path.join(OUTPUT_FOLDER, "elements.csv")
        elements = []
        if os.path.exists(elements_csv):
            df = pd.read_csv(elements_csv, keep_default_na=False).fillna("")
            elements = df.to_dict(orient="records")

        md_path = os.path.join(OUTPUT_FOLDER, "design_report.md")
        md_text = ""
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()

        editor_model = create_default_editor_model(spec, elements, page_number=page_num, pdf_path=pdf_path)
        editor_model["total_pages"] = total_pages

        ts = int(time.time())
        payload = {
            "status": "success",
            "doc_id": doc_id,
            "filename": os.path.basename(pdf_path),
            "page_number": page_num,
            "total_pages": total_pages,
            "spec": spec,
            "editor_model": editor_model,
            "template_match": editor_model.get("template_match"),
            "markdown_text": md_text,
            "elements": elements,
            "urls": {
                "json": f"/output/design_spec.json?v={ts}",
                "markdown": f"/output/design_report.md?v={ts}",
                "csv": f"/output/elements.csv?v={ts}",
                "page_image": f"/output/page_{page_num}.png?v={ts}",
                "annotated_image": f"/output/annotated_page_{page_num}.png?v={ts}",
                "logo": f"/output/extracted_logo.png?v={ts}",
                "reproduced_html": f"/output/reproduced_layout.html?v={ts}",
                "reproduced_pdf": f"/output/reproduced_statement.pdf?v={ts}"
            }
        }
        return jsonify(sanitize_for_json(payload))
    except Exception as e:
        logger.exception("Single page analysis failed")
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# DIMENSION EDITOR REST API ENDPOINTS
# ==============================================================================

@app.route("/api/editor/<doc_id>/page/<int:n>/model", methods=["GET"])
@app.route("/api/editor/model", methods=["GET"])
def get_editor_model_endpoint(doc_id="sample", n=1):
    """GET /api/editor/{doc_id}/page/{n}/model -> Editor model with auto & edited values."""
    try:
        page_num = int(request.args.get("page", n))
        target_doc = request.args.get("doc", doc_id)
        pdf_path = resolve_pdf_path(target_doc)

        # Check for full direct page state first
        ts = int(time.time())
        doc_hash = compute_pdf_hash(pdf_path) if pdf_path and os.path.exists(pdf_path) else "sample"
        state_file = os.path.join(OUTPUT_FOLDER, f"editor_state_{doc_hash}_page_{page_num}.json")
        if not os.path.exists(state_file) and target_doc in ("sample", "default", "sample_statement.pdf"):
            legacy_file = os.path.join(OUTPUT_FOLDER, f"editor_state_page_{page_num}.json")
            if os.path.exists(legacy_file):
                state_file = legacy_file

        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    saved_page_model = json.load(f)
                if isinstance(saved_page_model, dict) and "guides" in saved_page_model and "page_number" in saved_page_model:
                    return jsonify({
                        "status": "success",
                        "doc_id": target_doc,
                        "page_number": page_num,
                        "page_image": f"/output/page_{page_num}.png?v={ts}",
                        "editor_model": sanitize_for_json(saved_page_model),
                        "manual_edits_count": saved_page_model.get("manual_edits_count", 1)
                    })
            except Exception as e:
                logger.warning(f"Could not read state file: {e}")

        spec_file = os.path.join(OUTPUT_FOLDER, "design_spec.json")
        if not os.path.exists(spec_file):
            sample_pdf_path = resolve_pdf_path(target_doc)
            config = AnalyzerConfig(dpi=150, output_dir=OUTPUT_FOLDER)
            pipeline = AnalysisPipeline(config)
            spec = pipeline.process_document(sample_pdf_path, OUTPUT_FOLDER)
        else:
            with open(spec_file, "r", encoding="utf-8") as f:
                spec = json.load(f)

        elements_csv = os.path.join(OUTPUT_FOLDER, "elements.csv")
        elements = []
        if os.path.exists(elements_csv):
            df = pd.read_csv(elements_csv, keep_default_na=False).fillna("")
            elements = df.to_dict(orient="records")

        # Build model and automatically apply any saved sidecar edits
        model = create_default_editor_model(spec, elements, page_number=page_num, pdf_path=pdf_path)

        # Ensure raw unpadded page exists if needed
        raw_page_path = os.path.join(OUTPUT_FOLDER, f"page_{page_num}.png")
        if not os.path.exists(raw_page_path) and os.path.exists(pdf_path):
            try:
                doc = pymupdf.open(pdf_path)
                if page_num <= len(doc):
                    p = doc[page_num - 1]
                    cb = p.cropbox
                    mb = p.mediabox
                    from pdf_analyzer.stages.frame import PageFrame
                    pf = PageFrame(
                        page_number=page_num,
                        cropbox_pt=(float(cb.x0), float(cb.y0), float(cb.x1), float(cb.y1)),
                        mediabox_pt=(float(mb.x0), float(mb.y0), float(mb.x1), float(mb.y1)),
                        rotation_deg=int(p.rotation),
                        user_unit=float(getattr(p, "user_unit", 1.0) or 1.0),
                        dpi=model.get("dpi", 300)
                    )
                    _, pil = pf.render_exact_page(p)
                    pil.save(raw_page_path, "PNG")
                doc.close()
            except Exception as e:
                logger.warning(f"Could not render page_{page_num}.png on demand: {e}")

        return jsonify({
            "status": "success",
            "doc_id": target_doc,
            "page_number": page_num,
            "page_image": f"/output/page_{page_num}.png?v={ts}",
            "editor_model": sanitize_for_json(model),
            "manual_edits_count": model.get("manual_edits_count", 0)
        })
    except Exception as e:
        logger.exception("Failed to load editor model")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/snap-index", methods=["GET"])
def get_snap_index_endpoint(doc_id="sample", n=1):
    """GET /api/editor/{doc_id}/page/{n}/snap-index -> Exact vector drawing snap targets."""
    try:
        pdf_path = resolve_pdf_path(doc_id)
        s_idx = build_snap_index(pdf_path, n)
        return jsonify({
            "status": "success",
            "page_number": n,
            "snap_index": sanitize_for_json(s_idx)
        })
    except Exception as e:
        logger.exception("Failed to load snap index")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/snap-columns", methods=["POST"])
def snap_columns_endpoint(doc_id="sample", n=1):
    """POST /api/editor/{doc_id}/page/{n}/snap-columns -> Snaps all columns to real PDF rules."""
    try:
        data = request.get_json(force=True)
        model = data.get("editor_model", {})
        tol = float(data.get("tolerance_pt", 8.0))
        pdf_path = resolve_pdf_path(doc_id)
        s_idx = build_snap_index(pdf_path, n)
        res = snap_all_columns_to_rules(model, s_idx, tol_pt=tol)
        return jsonify(sanitize_for_json(res))
    except Exception as e:
        logger.exception("Snap columns failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/fit-table", methods=["POST"])
def fit_table_endpoint(doc_id="sample", n=1):
    """POST /api/editor/{doc_id}/page/{n}/fit-table -> Fits table bbox to outer rules & ink."""
    try:
        data = request.get_json(force=True)
        model = data.get("editor_model", {})
        pdf_path = resolve_pdf_path(doc_id)
        s_idx = build_snap_index(pdf_path, n)
        res = fit_table_to_outer_rules_and_ink(model, s_idx)
        return jsonify(sanitize_for_json(res))
    except Exception as e:
        logger.exception("Fit table failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/deduplicate", methods=["POST"])
def deduplicate_guides_endpoint(doc_id="sample", n=1):
    """POST /api/editor/{doc_id}/page/{n}/deduplicate -> Merges guides closer than 1.5 pt."""
    try:
        data = request.get_json(force=True)
        guides = data.get("guides", [])
        tol = float(data.get("tolerance_pt", 1.5))
        cleaned, report = remove_near_duplicates(guides, tol_pt=tol)
        return jsonify({
            "status": "success",
            "guides": sanitize_for_json(cleaned),
            "merged_count": len(report),
            "report": sanitize_for_json(report)
        })
    except Exception as e:
        logger.exception("Deduplication failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/fit-report", methods=["POST"])
def fit_report_endpoint(doc_id="sample", n=1):
    """POST /api/editor/{doc_id}/page/{n}/fit-report -> Generates comparison audit report."""
    try:
        data = request.get_json(force=True)
        model = data.get("editor_model", {})
        auto_model = data.get("initial_auto_model", {})
        report_text = generate_fit_report(model, auto_model)
        return jsonify({"status": "success", "report": report_text})
    except Exception as e:
        logger.exception("Fit report failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/edits", methods=["PUT", "POST"])
@app.route("/api/editor/save", methods=["POST"])
def save_edits_endpoint(doc_id="sample", n=1):
    """PUT /api/editor/{doc_id}/page/{n}/edits -> Save validated edits to sidecar file."""
    try:
        data = request.get_json(force=True)
        page_num = int(data.get("page_number", n))
        target_doc = data.get("doc_id", doc_id)
        pdf_path = resolve_pdf_path(target_doc)

        page_edits = data.get("edits", data.get("editor_model", {}))

        # Load or init sidecar file
        sidecar = load_sidecar_edits(pdf_path, OUTPUT_FOLDER)
        sidecar["pages"][str(page_num)] = page_edits
        sidecar["total_manual_edits"] = sum(
            len(p.get("guides", {})) + len(p.get("boxes", {})) + len(p.get("dimensions", {}))
            for p in sidecar["pages"].values() if isinstance(p, dict)
        )

        saved_path = save_sidecar_edits(pdf_path, sidecar, OUTPUT_FOLDER)

        # Also update per-page state json for quick serving
        doc_hash = compute_pdf_hash(pdf_path) if pdf_path and os.path.exists(pdf_path) else "sample"
        namespaced_state_file = os.path.join(OUTPUT_FOLDER, f"editor_state_{doc_hash}_page_{page_num}.json")
        with open(namespaced_state_file, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_json(page_edits), f, indent=2)

        state_file = os.path.join(OUTPUT_FOLDER, f"editor_state_page_{page_num}.json")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_json(page_edits), f, indent=2)

        return jsonify({
            "status": "success",
            "doc_id": target_doc,
            "page_number": page_num,
            "sidecar_file": os.path.basename(saved_path),
            "total_manual_edits": sidecar["total_manual_edits"]
        })
    except Exception as e:
        logger.exception("Failed to save edits")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/redetect", methods=["POST"])
@app.route("/api/editor/redetect", methods=["POST"])
def redetect_roi_endpoint(doc_id="sample", n=1):
    """POST /api/editor/{doc_id}/page/{n}/redetect -> ROI re-detection preview."""
    try:
        data = request.get_json(force=True)
        target_doc = data.get("doc_id", doc_id)
        pdf_path = resolve_pdf_path(target_doc)

        page_num = int(data.get("page_number", n))
        roi_bbox = tuple(data.get("roi_bbox_pt", [36.0, 150.0, 576.0, 600.0]))
        dpi = int(data.get("dpi", 300))

        result = redetect_roi(pdf_path, page_num, roi_bbox, dpi=dpi)
        return jsonify(sanitize_for_json(result))
    except Exception as e:
        logger.exception("ROI redetection failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/page/<int:n>/recompute", methods=["POST"])
def recompute_endpoint(doc_id="sample", n=1):
    """POST /api/editor/{doc_id}/page/{n}/recompute -> Recalculates derived values and consistency."""
    try:
        data = request.get_json(force=True)
        model = data.get("editor_model", {})
        recomputed = recompute_derived_model(model)
        return jsonify({
            "status": "success",
            "editor_model": sanitize_for_json(recomputed),
            "consistency": recomputed.get("consistency")
        })
    except Exception as e:
        logger.exception("Recomputation failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/copy_page_edits", methods=["POST"])
def copy_page_edits_endpoint():
    """POST /api/editor/copy_page_edits -> Propagate edits across pages."""
    try:
        data = request.get_json(force=True)
        source_page = int(data.get("source_page", 1))
        target_pages = data.get("target_pages", [])
        source_model = data.get("editor_model", {})

        for p in target_pages:
            state_file = os.path.join(OUTPUT_FOLDER, f"editor_state_page_{p}.json")
            target_model = json.loads(json.dumps(source_model))
            target_model["page_number"] = p
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(sanitize_for_json(target_model), f, indent=2)

        return jsonify({"status": "success", "updated_pages": target_pages})
    except Exception as e:
        logger.exception("Failed to copy edits to pages")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/dimensions", methods=["POST"])
def export_dimensions_endpoint(doc_id="sample"):
    """POST /api/editor/{doc_id}/dimensions -> Formats dimension inventory via dimensions_export.py."""
    try:
        data = request.get_json(force=True)
        model = data.get("editor_model", {})
        fmt = str(data.get("format", "markdown"))
        unit = str(data.get("units", data.get("unit", "pt")))
        decimals = int(data.get("decimals", 2))
        frame = str(data.get("frame", "page"))
        include_defs = bool(data.get("include_definitions", True))
        only_manual = bool(data.get("only_manual", False))
        include_header = bool(data.get("include_header", True))
        scope = str(data.get("scope", "all"))
        privacy_mode = str(data.get("privacy_mode", "synthetic"))

        output_text = export_dimensions(
            model=model,
            export_format=fmt,
            unit=unit,
            decimals=decimals,
            frame=frame,
            include_definitions=include_defs,
            only_manual=only_manual,
            include_header=include_header,
            scope=scope,
            privacy_mode=privacy_mode
        )

        return jsonify({
            "status": "success",
            "format": fmt,
            "unit": unit,
            "privacy_mode": privacy_mode,
            "text": output_text
        })
    except Exception as e:
        logger.exception("Dimensions export failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/pii-report", methods=["POST"])
def get_pii_report_endpoint(doc_id="sample"):
    """POST /api/editor/{doc_id}/pii-report -> Runs PII detection and returns redaction summary."""
    try:
        data = request.get_json(force=True)
        model = data.get("editor_model", {})
        mode = str(data.get("privacy_mode", "synthetic"))
        from pdf_analyzer.privacy.engine import apply_privacy_to_editor_model
        _, report = apply_privacy_to_editor_model(model, mode=mode)
        return jsonify({
            "status": "success",
            "report": report.to_dict()
        })
    except Exception as e:
        logger.exception("PII report failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/editor/<doc_id>/ground-truth", methods=["POST"])
def export_ground_truth_endpoint(doc_id="sample"):
    """POST /api/editor/{doc_id}/ground-truth -> Writes ground_truth.json."""
    try:
        data = request.get_json(force=True)
        model = data.get("editor_model", {})
        gt_path = export_ground_truth(model, os.path.join(OUTPUT_FOLDER, "ground_truth.json"))
        return jsonify({
            "status": "success",
            "ground_truth_file": os.path.basename(gt_path)
        })
    except Exception as e:
        logger.exception("Ground truth export failed")
        return jsonify({"error": str(e)}), 500


# =========================================================================
# Form GSTR-3B Route & API Endpoints
# =========================================================================

@app.route("/gst")
def gst_page():
    """Render Form GSTR-3B Pixel-Perfect Cloner web interface."""
    return render_template("gst.html")


@app.route("/api/gst/data", methods=["GET"])
def get_gst_data():
    """Return default or current Form GSTR-3B JSON data."""
    data = get_default_gstr3b_data()
    return jsonify(data)


@app.route("/api/gst/generate", methods=["POST", "GET"])
def generate_gst_artifacts():
    """Generate Form GSTR-3B PDF, HTML, and page preview PNGs."""
    try:
        if request.method == "POST":
            custom_data = request.get_json(silent=True)
        else:
            custom_data = None

        if not custom_data:
            custom_data = get_default_gstr3b_data()

        # 1. Compile PDF
        pdf_path = os.path.join(OUTPUT_FOLDER, "Form_GSTR_3B.pdf")
        generate_gstr3b_pdf(pdf_path, data=custom_data)

        # 2. Compile HTML
        html_content = generate_gstr3b_html(data=custom_data)
        html_path = os.path.join(OUTPUT_FOLDER, "Form_GSTR_3B.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 3. Render High-Resolution Preview PNGs (DPI=150)
        doc = pymupdf.open(pdf_path)
        preview_pages = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            img_filename = f"gstr3b_page_{i+1}.png"
            img_path = os.path.join(OUTPUT_FOLDER, img_filename)
            pix.save(img_path)
            preview_pages.append(f"/output/{img_filename}")
        doc.close()

        meta = get_gstr3b_metadata(custom_data, pdf_path)

        return jsonify({
            "status": "success",
            "pdf_url": "/output/Form_GSTR_3B.pdf",
            "html_url": "/output/Form_GSTR_3B.html",
            "preview_pages": preview_pages,
            "page_count": len(preview_pages),
            "data": custom_data,
            "metadata": meta
        })
    except Exception as e:
        logger.exception("Form GSTR-3B generation failed")
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route("/api/gst/metadata", methods=["GET"])
def get_gst_metadata():
    """Return authoritative Form GSTR-3B PDF metadata, fonts, colors, and geometry spec."""
    pdf_path = os.path.join(OUTPUT_FOLDER, "Form_GSTR_3B.pdf")
    meta = get_gstr3b_metadata(get_default_gstr3b_data(), pdf_path=pdf_path)
    return jsonify(meta)


@app.route("/api/gst/prompt", methods=["GET", "POST"])
def get_gst_ai_prompt():
    """Return authoritative Form GSTR-3B AI Layout Prompt."""
    if request.method == "POST":
        custom_data = request.get_json(silent=True) or get_default_gstr3b_data()
    else:
        custom_data = get_default_gstr3b_data()
    prompt_text = generate_gstr3b_ai_prompt(custom_data)
    return jsonify({"status": "success", "prompt": prompt_text})


@app.route("/api/gst/download-pdf", methods=["GET"])
def download_gst_pdf():
    """Download Form GSTR-3B compiled PDF file."""
    pdf_path = os.path.join(OUTPUT_FOLDER, "Form_GSTR_3B.pdf")
    if not os.path.exists(pdf_path):
        generate_gstr3b_pdf(pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name="Form_GSTR_3B.pdf")


if __name__ == "__main__":
    print("\n=======================================================")
    print("  PDF Design Analyzer Web Dashboard Running")
    print("  URL: http://127.0.0.1:5000")
    print("=======================================================\n")
    app.run(host="127.0.0.1", port=5000, debug=False)

