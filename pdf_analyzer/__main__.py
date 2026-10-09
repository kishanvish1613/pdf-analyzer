"""
PDF Design Analyzer CLI.
Entrypoint for command-line diagnostics, L0 content-stream dumping, template dossiers,
closed-loop SSIM evaluation, and corpus regression checking.
"""

from __future__ import annotations
import sys
import os
import json
from typing import Optional
import click
from pdf_analyzer.l0_bytes.interpreter import ByteLayerExtractor
from pdf_analyzer.l1_crosscheck.audit import run_l1_audit, print_audit_terminal_report
from pdf_analyzer.dossier import generate_template_dossier
from pdf_analyzer.closed_loop import ClosedLoopEngine
from pdf_analyzer.corpus_check import CorpusCheckEngine, print_corpus_check_report
from pdf_analyzer.utils.json_sanitizer import sanitize_for_json


@click.group()
def cli():
    """PDF Design Analyzer - Reference-grade PDF visual design recovery system."""
    pass


@cli.command("dump-l0")
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--page", "-p", default=1, type=int, help="1-indexed page number to inspect.")
@click.option("--format", "-f", "output_format", default="summary", type=click.Choice(["summary", "json"]), help="Output format.")
def dump_l0(pdf_path: str, page: int, output_format: str):
    """
    Directly extracts and dumps L0 ByteLayer primitives (paths, text glyphs, Form XObjects, clips).
    """
    try:
        with ByteLayerExtractor(pdf_path) as extractor:
            page_layer = extractor.extract_page(page_number=page)

        if output_format == "json":
            out_dict = sanitize_for_json(page_layer.to_dict())
            click.echo(json.dumps(out_dict, indent=2))
        else:
            click.echo("=" * 80)
            click.echo(f"  L0 BYTELAYER DUMP - Page {page} of {os.path.basename(pdf_path)}")
            click.echo("=" * 80)
            click.echo(f"MediaBox (pt)   : {page_layer.mediabox_pt}")
            click.echo(f"CropBox (pt)    : {page_layer.cropbox_pt}  (Width: {page_layer.width_pt:.2f} pt, Height: {page_layer.height_pt:.2f} pt)")
            click.echo(f"Rotation (deg)  : {page_layer.rotation_deg}°")
            click.echo(f"Painted Paths   : {len(page_layer.paths)}")
            click.echo(f"Text Characters : {len(page_layer.chars)}")
            click.echo(f"Images (Inline) : {len(page_layer.images)}")
            click.echo(f"Form XObjects   : {len(page_layer.xobjects)}")
            click.echo(f"Clipping Regions: {len(page_layer.clips)}")
            click.echo("-" * 80)

            click.echo("Sample Vector Paths (first 5):")
            for i, p in enumerate(page_layer.paths[:5]):
                stroke_info = f"stroke={p.stroke.width_pt}pt {p.stroke_color.hex if p.stroke_color else ''}" if p.stroke else "no stroke"
                fill_info = f"fill={p.fill_rule} {p.fill_color.hex if p.fill_color else ''}" if p.fill_rule else "no fill"
                prov_str = f"[{p.provenance.stream_name} op#{p.provenance.operator_index}:{p.provenance.operator_name}]" if p.provenance else ""
                click.echo(f"  [{i+1}] {p.path_id:<12} | Segs: {len(p.segments):<3} | BBox: {p.bbox_device_pt} | {stroke_info} | {fill_info} {prov_str}")

            click.echo("-" * 80)
            click.echo("Sample Text Glyphs (first 10):")
            for i, c in enumerate(page_layer.chars[:10]):
                prov_str = f"[{c.provenance.stream_name} op#{c.provenance.operator_index}:{c.provenance.operator_name}]" if c.provenance else ""
                click.echo(f"  [{i+1}] Char: {c.char_text!r:<4} ({c.unicode_text!r}) | Font: {c.font_name} @ {c.font_size_pt}pt | Origin: ({c.origin_device_pt[0]:.2f}, {c.origin_device_pt[1]:.2f}) | Adv: {c.advance_pt:.2f}pt {prov_str}")

            if page_layer.errors:
                click.echo("-" * 80)
                click.echo(f"Parser Warnings/Errors ({len(page_layer.errors)}):")
                for err in page_layer.errors:
                    click.echo(f"  * {err}")

            click.echo("=" * 80)

    except Exception as e:
        click.echo(f"Error extracting L0 ByteLayer: {e}", err=True)
        sys.exit(1)


@cli.command("audit")
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--page", "-p", default=1, type=int, help="1-indexed page number to audit.")
@click.option("--strict", is_flag=True, default=False, help="Fail loud with non-zero exit if any gate fails.")
@click.option("--output-dir", "-o", default=None, type=click.Path(), help="Directory to save audit.json and artifacts.")
def audit(pdf_path: str, page: int, strict: bool, output_dir: Optional[str]):
    """
    Performs L1 Cross-Check & Gate Audit against dual 600 DPI renders and independent parsers.
    """
    try:
        passed, audit_dict = run_l1_audit(
            pdf_path=pdf_path,
            page_number=page,
            strict=strict,
            output_dir=output_dir,
        )
        print_audit_terminal_report(audit_dict)

        if strict and not passed:
            click.echo(click.style("ERROR: Strict mode enabled and one or more gates failed.", fg="red", bold=True), err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Audit execution failed: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command("dossier")
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--page", "-p", default=None, type=int, help="Optional 1-indexed page number (default: all pages).")
@click.option("--output-dir", "-o", default=None, type=click.Path(), help="Directory to save dossier.json and dossier.md.")
def dossier(pdf_path: str, page: Optional[int], output_dir: Optional[str]):
    """
    Generates template dossier (dossier.json + dossier.md) covering producer, fonts, rules, fills, stream-order rows, and verdicts.
    """
    try:
        dossier_obj = generate_template_dossier(
            pdf_path=pdf_path,
            page_number=page,
            output_dir=output_dir,
        )
        from pdf_analyzer.dossier import TemplateDossierEngine
        engine = TemplateDossierEngine()
        click.echo(engine.render_markdown_report(dossier_obj))

    except Exception as e:
        click.echo(f"Dossier generation failed: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command("closed-loop")
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--page", "-p", default=1, type=int, help="1-indexed page number to evaluate.")
@click.option("--output-dir", "-o", default=None, type=click.Path(), help="Directory to save artifacts.")
def closed_loop(pdf_path: str, page: int, output_dir: Optional[str]):
    """
    Runs closed-loop synthesis from model and measures SSIM per region.
    """
    try:
        engine = ClosedLoopEngine()
        report = engine.evaluate_closed_loop(pdf_path, page, output_dir)
        click.echo("\n" + "=" * 80)
        click.echo(f"  CLOSED-LOOP RECONSTRUCTION SSIM REPORT (Page {page} of {os.path.basename(pdf_path)})")
        click.echo("=" * 80)
        click.echo(f"Chosen Model: {report.chosen_model} | Runner-Up: {report.runner_up_model} | Winning Model: {report.winning_model}")
        click.echo(f"Overall SSIM: {report.overall_ssim:.4f} (Threshold >= 0.97: {'PASS' if report.overall_passed else 'FAIL'})")
        click.echo("-" * 80)
        for r in report.region_scores:
            st = click.style("[PASS]", fg="green") if r.passed else click.style("[FAIL]", fg="red")
            click.echo(f"Region {r.region_name:<15}: SSIM = {r.ssim_score:.4f}  {st}")
        click.echo("=" * 80 + "\n")
    except Exception as e:
        click.echo(f"Closed-loop check failed: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command("corpus-check")
@click.option("--golden-dir", default="tests/golden", help="Path to golden json files.")
@click.option("--ground-truth-dir", default="tests/ground_truth", help="Path to ground truth json files.")
def corpus_check(golden_dir: str, ground_truth_dir: str):
    """
    Compares auto-extracted models against golden ground truth JSONs.
    Exits non-zero if: max_delta>0.10, identical constant delta, or golden==auto on >90% objects.
    """
    from pdf_analyzer.corpus_check import corpus_check_exit_code
    try:
        engine = CorpusCheckEngine()
        report = engine.run_corpus_check(golden_dir, ground_truth_dir)
        print_corpus_check_report(report)
        rc = corpus_check_exit_code(report)
        if rc != 0:
            sys.exit(rc)
    except Exception as e:
        click.echo(f"Corpus check failed: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli()
