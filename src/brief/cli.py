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
@click.option("--with-images", is_flag=True, help="Include base64 PNGs (for later render).")
def augment_cmd(pdf: Path, out: Path | None, with_images: bool) -> None:
    """Docling extract + Claude judgment over pictures and tables."""
    from brief.augment import augment

    result = augment(pdf, with_images=with_images)
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
@click.option(
    "--save-json",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Also write the augment JSON here (so render can re-run without Claude).",
)
def report_cmd(pdf: Path, out: Path, save_json: Path | None) -> None:
    """Run augment and write a self-contained HTML report (images embedded)."""
    from brief.augment import augment
    from brief.report import render

    result = augment(pdf, with_images=True)
    if save_json:
        save_json.write_text(json.dumps(asdict(result), indent=2))
        click.echo(f"wrote {save_json}")
    out.write_text(render(result))
    click.echo(f"wrote {out}")


@main.command(name="render")
@click.argument("augment_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("report.html"),
    show_default=True,
)
def render_cmd(augment_json: Path, out: Path) -> None:
    """Re-render an HTML report from a saved augment JSON. No Claude calls."""
    from brief.augment import Augmented, AugmentedPicture, AugmentedTable
    from brief.report import render

    data = json.loads(augment_json.read_text())
    aug = Augmented(
        pdf=data["pdf"],
        pages=data["pages"],
        pictures=[AugmentedPicture(**p) for p in data["pictures"]],
        tables=[AugmentedTable(**t) for t in data["tables"]],
    )
    out.write_text(render(aug))
    click.echo(f"wrote {out}")


@main.command(name="alt")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def alt_cmd(image: Path) -> None:
    """Alt-text for a single image (no PDF needed). Smallest possible demo."""
    from brief.judge import alt_text

    suffix = image.suffix.lower()
    media_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    click.echo(alt_text(image.read_bytes(), media_type=media_type))


if __name__ == "__main__":
    main()
