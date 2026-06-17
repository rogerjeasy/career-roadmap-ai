"""Unit tests for the CV URL-import SSRF guard and helpers.

``socket.getaddrinfo`` is monkeypatched so no real DNS happens.
"""
from __future__ import annotations

import socket

import pytest

from src.domains.cv.url_import import (
    UrlImportError,
    _assert_public_host,
    _ext_from,
    _filename_from,
)


def _addrinfo(ip: str):
    """Build a getaddrinfo-shaped result for a single address."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


# ── Pure helpers ────────────────────────────────────────────────────────────


def test_ext_from_path() -> None:
    assert _ext_from("https://x.com/cv.pdf", None) == "pdf"
    assert _ext_from("https://x.com/resume.DOCX", None) == "docx"


def test_ext_from_content_type_fallback() -> None:
    assert _ext_from("https://x.com/download", "application/pdf") == "pdf"
    assert _ext_from("https://x.com/d", "text/plain; charset=utf-8") == "txt"


def test_ext_from_unknown_is_empty() -> None:
    assert _ext_from("https://x.com/page", "text/html") == ""


def test_filename_from_appends_ext_when_missing() -> None:
    assert _filename_from("https://x.com/download", "pdf") == "download.pdf"
    assert _filename_from("https://x.com/my%20cv.pdf", "pdf") == "my cv.pdf"


# ── SSRF host guard ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rejects_non_http_scheme() -> None:
    with pytest.raises(UrlImportError):
        await _assert_public_host("ftp://example.com/cv.pdf")


@pytest.mark.asyncio
@pytest.mark.parametrize("private_ip", ["127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254"])
async def test_rejects_private_and_loopback_and_metadata(
    monkeypatch: pytest.MonkeyPatch, private_ip: str
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo(private_ip))
    with pytest.raises(UrlImportError):
        await _assert_public_host("https://malicious.example/cv.pdf")


@pytest.mark.asyncio
async def test_allows_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    # Should not raise.
    await _assert_public_host("https://example.com/cv.pdf")


@pytest.mark.asyncio
async def test_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a, **_k):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    with pytest.raises(UrlImportError):
        await _assert_public_host("https://does-not-exist.example/cv.pdf")
