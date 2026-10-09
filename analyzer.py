"""CLI entry point for PDF Design Analyzer with Stage 0-28 Engine and --explain flag.

Usage:
    python analyzer.py input.pdf --dpi 600 --out ./output --pages all
    python analyzer.py input.pdf --explain cell_r1_c2
"""

import os
import sys
import json
import logging
import click

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.pipeline import AnalysisPipeline


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.argument("input_pdf", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("--dpi", default=600, type=int, show_default=True, help="Rasterization resolution for sub-pixel measurements.")
@click.option("--out", "output_dir", default="./output", show_default=True, help="Directory to save analysis artifacts.")
@click.option("--pages", default="all", show_default=True, help="Pages to analyze: 'all', '1', '1,2', or '1-3'.")
@click.option("--explain", default=None, help="Element ID to explain (prints evidence trail, sources, deltas, and rules).")
@click.option("-v", "--verbose", is_flag=True, help="Enable detailed debug logging.")
def main(input_pdf: str, dpi: int, output_dir: str, pages: str, explain: str, verbose: bool):
    """PDF Design Analyzer: Extracts pixel-accurate visual design specifications
    from bank-statement-style PDFs with registration, box recovery, and full content accounting.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

    if explain:
        # Check if design_spec.json or table_model.json already exists in output_dir
        spec_file = os.path.join(output_dir, "table_model.json")
        if os.path.exists(spec_file):
            with open(spec_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cells = {c["cell_id"]: c for c in data.get("cells", [])}
            cols = {f"col_{c['index']}": c for c in data.get("columns", [])}
            rows = {f"row_{r['index']}": r for r in data.get("rows", [])}

            if explain in cells:
                click.secho(f"\n=== Evidence Trail for Cell: {explain} ===", fg="cyan", bold=True)
                click.echo(json.dumps(cells[explain], indent=2))
                return
            elif explain in cols:
                click.secho(f"\n=== Evidence Trail for Column: {explain} ===", fg="cyan", bold=True)
                click.echo(json.dumps(cols[explain], indent=2))
                return
            elif explain in rows:
                click.secho(f"\n=== Evidence Trail for Row: {explain} ===", fg="cyan", bold=True)
                click.echo(json.dumps(rows[explain], indent=2))
                return

    click.echo(f"=== PDF Design Analyzer ===")
    click.echo(f"Input:   {input_pdf}")
    click.echo(f"DPI:     {dpi}")
    click.echo(f"Pages:   {pages}")
    click.echo(f"Output:  {output_dir}\n")

    config = AnalyzerConfig(
        dpi=dpi,
        pages=pages,
        output_dir=output_dir
    )

    pipeline = AnalysisPipeline(config)
    try:
        spec = pipeline.process_document(input_pdf, output_dir)
        click.secho("\n[SUCCESS] Document analysis finished successfully!", fg="green", bold=True)
        click.echo("Generated Artifacts:")
        click.echo(f"  - 1. Registration:          {output_dir}/registration.json & registration.png")
        click.echo(f"  - 2. Containers:            {output_dir}/containers.json & containers.png")
        click.echo(f"  - 3. Header Blocks:         {output_dir}/header_blocks.json & header_blocks.png")
        click.echo(f"  - 4. Table Model:           {output_dir}/table_model.json")
        click.echo(f"  - 5. Footer Blocks:         {output_dir}/footer_blocks.json & footer.png")
        click.echo(f"  - 6. Content Coverage:      {output_dir}/coverage.json & orphans.png")
        click.echo(f"  - 7. Template Profile:      {output_dir}/template_profile.json")
        click.echo(f"  - 8. Design Specification:  {output_dir}/design_spec.json")
        click.echo(f"  - 9. Markdown Report:       {output_dir}/design_report.md")
    except Exception as e:
        click.secho(f"\n[ERROR] Analysis failed: {e}", fg="red", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
