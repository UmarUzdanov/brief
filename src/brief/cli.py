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


if __name__ == "__main__":
    main()
