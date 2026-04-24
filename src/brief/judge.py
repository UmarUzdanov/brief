"""Claude judgment over Docling-extracted items.

Uses the Claude Code CLI (`claude -p`) so we authenticate via the user's
Pro/Max subscription instead of an API key. Each call is a one-shot
non-persistent session; the only tool we whitelist is Read (so vision can
ingest a temp image file).

Three single-purpose functions:
    alt_text(image_bytes)                  -> str | "DECORATIVE"
    header_rows(cells)                     -> list[int]
    link_purpose(text, surrounding, url)   -> str | "KEEP"
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

DEFAULT_MODEL = "haiku"  # haiku-4-5 latest; fast + cheap for short calls


def _claude_p(
    prompt: str,
    *,
    allowed_tools: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    timeout_s: int = 120,
) -> str:
    """Run one prompt via `claude -p`, return stripped stdout.

    Raises RuntimeError on non-zero exit.
    """
    if not shutil.which("claude"):
        raise RuntimeError("`claude` CLI not on PATH; install Claude Code first.")
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "text",
        "--model",
        model,
        "--no-session-persistence",
        "--permission-mode",
        "bypassPermissions",
    ]
    if allowed_tools is not None:
        cmd += ["--allowed-tools", ",".join(allowed_tools) if allowed_tools else ""]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if result.returncode != 0:
        raise RuntimeError(
            f"claude -p exited {result.returncode}: {result.stderr.strip()[:300]}"
        )
    return result.stdout.strip()


def alt_text(image_bytes: bytes, media_type: str = "image/png") -> str:
    """Screen-reader-quality description. Returns 'DECORATIVE' for non-meaningful."""
    suffix = ".png" if "png" in media_type else ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="brief-img-")
    try:
        with open(fd, "wb") as f:
            f.write(image_bytes)
        prompt = (
            f"Read the image at {tmp_path}. "
            "Describe it for a screen reader user in ONE sentence. "
            "State what it depicts and any visible text. "
            "If purely decorative (border, divider, blank, ornament, generic background), "
            "reply with the single word: DECORATIVE. "
            "Reply with ONLY the description, no preamble."
        )
        return _claude_p(prompt, allowed_tools=["Read"])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_header_rows(text: str) -> list[int]:
    """Parse Claude's header-row response. NONE -> []; comma-separated ints kept."""
    text = text.strip()
    if text.upper() == "NONE":
        return []
    out: list[int] = []
    for tok in text.split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out


def header_rows(cells: list[list[str]]) -> list[int]:
    """Given a 2D table of cell text, return 0-indexed header row indices."""
    rendered = "\n".join(
        f"row {i}: " + " | ".join((c or "").strip() for c in row)
        for i, row in enumerate(cells)
    )
    prompt = (
        "Below is a table extracted from a PDF. Return ONLY the row indices "
        "(0-indexed, comma-separated) that are header rows. If no header rows, "
        "reply: NONE\n\n"
        f"{rendered}"
    )
    return _parse_header_rows(_claude_p(prompt, allowed_tools=[]))


def link_purpose(visible_text: str, surrounding_text: str, target_url: str) -> str:
    """Rewrite link text to be self-describing. Returns 'KEEP' if already clear."""
    prompt = (
        "Screen reader users navigate by link list. Generic text like 'click here' "
        "or 'link' fails them. Rewrite the link text to be self-describing in context.\n\n"
        f"Current link text: {visible_text!r}\n"
        f"Target URL: {target_url}\n"
        f"Surrounding paragraph: {surrounding_text}\n\n"
        "Reply with ONLY the replacement link text, max 80 chars. "
        "If the current text is already self-describing, reply: KEEP"
    )
    return _claude_p(prompt, allowed_tools=[]).strip()
