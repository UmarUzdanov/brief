"""Claude judgment over Docling-extracted items.

Three single-purpose functions. Each one is one Claude call. Stateless —
takes what it needs, returns the judgment. Orchestration lives elsewhere.

Functions:
    alt_text(client, image_bytes)          -> str   (or "DECORATIVE")
    header_rows(client, cells)             -> list[int]
    link_purpose(client, text, ctx, url)   -> str   (or "KEEP")
"""
from __future__ import annotations

import base64

import anthropic

MODEL = "claude-sonnet-4-6"


def alt_text(
    client: anthropic.Anthropic,
    image_bytes: bytes,
    media_type: str = "image/png",
) -> str:
    """Screen-reader-quality description. Returns 'DECORATIVE' for non-meaningful."""
    msg = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image_bytes).decode(),
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Describe this image for a screen reader user in one sentence. "
                            "State what it depicts and any visible text. "
                            "If purely decorative (border, divider, blank, ornament), "
                            "reply with the single word: DECORATIVE"
                        ),
                    },
                ],
            }
        ],
    )
    return msg.content[0].text.strip()


def header_rows(client: anthropic.Anthropic, cells: list[list[str]]) -> list[int]:
    """Given a 2D table of cell text, return 0-indexed header row indices."""
    rendered = "\n".join(
        f"row {i}: " + " | ".join((c or "").strip() for c in row)
        for i, row in enumerate(cells)
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=80,
        messages=[
            {
                "role": "user",
                "content": (
                    "Below is a table extracted from a PDF. Return ONLY the row "
                    "indices (0-indexed, comma-separated) that are header rows. "
                    "If no header rows, reply: NONE\n\n"
                    f"{rendered}"
                ),
            }
        ],
    )
    text = msg.content[0].text.strip()
    if text.upper() == "NONE":
        return []
    out: list[int] = []
    for tok in text.split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out


def link_purpose(
    client: anthropic.Anthropic,
    visible_text: str,
    surrounding_text: str,
    target_url: str,
) -> str:
    """Rewrite link text to be self-describing. Returns 'KEEP' if already clear."""
    msg = client.messages.create(
        model=MODEL,
        max_tokens=120,
        messages=[
            {
                "role": "user",
                "content": (
                    "Screen reader users navigate by link list. Generic text "
                    "like 'click here' or 'link' fails them. Rewrite the link "
                    "text to be self-describing in context.\n\n"
                    f"Current link text: {visible_text!r}\n"
                    f"Target URL: {target_url}\n"
                    f"Surrounding paragraph: {surrounding_text}\n\n"
                    "Reply with ONLY the replacement link text, max 80 chars. "
                    "If the current text is already self-describing, reply: KEEP"
                ),
            }
        ],
    )
    return msg.content[0].text.strip()
