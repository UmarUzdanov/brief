"""brief CLI."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from brief.extract import extract


@click.group()
def main() -> None:
    """brief: judgment layer for PDF accessibility."""


@main.command(name="extract")
@click.argument("pdf", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def extract_cmd(pdf: Path, as_json: bool) -> None:
    """Run Docling on PDF and print what it found."""
    result = extract(pdf)
    if as_json:
        click.echo(json.dumps(asdict(result), indent=2))
        return
    click.echo(f"pages:       {result.pages}")
    click.echo(f"text blocks: {result.text_blocks}")
    click.echo(f"pictures:    {len(result.pictures)}")
    for i, pic in enumerate(result.pictures, 1):
        click.echo(f"  [{i}] page {pic.page}, bbox {pic.bbox}")
    click.echo(f"tables:      {len(result.tables)}")
    for i, tbl in enumerate(result.tables, 1):
        click.echo(f"  [{i}] page {tbl.page}, {tbl.rows}x{tbl.cols}, bbox {tbl.bbox}")


@main.command(name="augment")
@click.argument("pdf", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), help="Write JSON here.")
def augment_cmd(pdf: Path, out: Path | None) -> None:
    """Docling extract + Claude judgment over pictures and tables."""
    from brief.augment import augment

    result = augment(pdf)
    payload = json.dumps(asdict(result), indent=2)
    if out:
        out.write_text(payload)
        click.echo(f"wrote {out}")
    else:
        click.echo(payload)


@main.command(name="report")
@click.argument("pdf", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("report.html"),
    show_default=True,
)
def report_cmd(pdf: Path, out: Path) -> None:
    """Run augment and write a self-contained HTML report (images embedded)."""
    from brief.augment import augment
    from brief.report import render

    result = augment(pdf, with_images=True)
    out.write_text(render(result))
    click.echo(f"wrote {out}")


if __name__ == "__main__":
    main()
