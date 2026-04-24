"""Unit tests for links._coerce_url (no Docling required)."""
from __future__ import annotations

from types import SimpleNamespace as N

from brief.links import _coerce_url


def test_str_hyperlink_attr():
    assert _coerce_url(N(hyperlink="https://example.com")) == "https://example.com"


def test_url_attr():
    assert _coerce_url(N(url="https://example.org/path")) == "https://example.org/path"


def test_object_with_https_str():
    class Target:
        def __str__(self) -> str:
            return "https://example.com/x"

    assert _coerce_url(N(hyperlink=Target())) == "https://example.com/x"


def test_no_url_returns_none():
    assert _coerce_url(N()) is None
    assert _coerce_url(N(hyperlink=None)) is None


def test_non_url_str_object_rejected():
    class T:
        def __str__(self) -> str:
            return "not-a-url"

    assert _coerce_url(N(hyperlink=T())) is None
