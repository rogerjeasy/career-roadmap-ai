"""Secure fetching of a remote CV document for URL-based import.

Fetching a user-supplied URL server-side is an SSRF risk, so this module is
deliberately strict:

* only ``http`` / ``https`` schemes;
* the URL's host must resolve to a **public** IP — loopback, private, link-local
  (incl. cloud metadata ``169.254.169.254``), reserved and multicast ranges are
  rejected;
* redirects are followed **manually**, re-validating the host at every hop
  (httpx auto-redirects would bypass the per-hop check);
* the download is streamed and hard-capped at 10 MB;
* only PDF / DOCX / TXT / MD documents are accepted.

DNS-rebinding (TOCTOU between resolve and connect) is not fully mitigated here;
that would require pinning the resolved IP into a custom transport. The checks
above cover the common SSRF vectors for a public contact-style import.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import unquote, urljoin, urlparse

import httpx

ALLOWED_EXTS = {"pdf", "docx", "txt", "md"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB — matches the file-upload cap
MAX_REDIRECTS = 3
_TIMEOUT = httpx.Timeout(15.0)

_CONTENT_TYPE_EXT = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
}


class UrlImportError(Exception):
    """A client-correctable problem fetching the document (→ HTTP 422)."""


def _ext_from(url: str, content_type: str | None) -> str:
    """Resolve the document extension from the URL path, falling back to MIME."""
    path = urlparse(url).path
    if "." in path:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ALLOWED_EXTS:
            return ext
    ct = (content_type or "").split(";")[0].strip().lower()
    return _CONTENT_TYPE_EXT.get(ct, "")


def _filename_from(url: str, ext: str) -> str:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1]) or "cv"
    if "." not in name and ext:
        name = f"{name}.{ext}"
    return name


async def _assert_public_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlImportError("Only http and https URLs are supported.")
    host = parsed.hostname
    if not host:
        raise UrlImportError("That doesn't look like a valid URL.")

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror as exc:
        raise UrlImportError("Couldn't resolve that URL's host.") from exc

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UrlImportError("That URL points to a non-public address.")


async def fetch_remote_document(url: str, client: httpx.AsyncClient) -> tuple[bytes, str]:
    """Download a CV from ``url`` safely. Returns ``(bytes, filename)``.

    Raises ``UrlImportError`` for any disallowed URL, unsupported type, oversized
    body, or network failure.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await _assert_public_host(current)
        try:
            async with client.stream(
                "GET",
                current,
                follow_redirects=False,
                timeout=_TIMEOUT,
                headers={"Accept": "*/*"},
            ) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise UrlImportError("The URL redirected without a destination.")
                    current = urljoin(current, location)
                    continue

                if resp.status_code != 200:
                    raise UrlImportError(
                        f"The URL returned HTTP {resp.status_code}."
                    )

                ext = _ext_from(str(resp.url), resp.headers.get("content-type"))
                if ext not in ALLOWED_EXTS:
                    raise UrlImportError(
                        "Unsupported document type. Link to a PDF, DOCX, TXT, or MD file."
                    )

                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                    raise UrlImportError("That document exceeds the 10 MB limit.")

                buffer = bytearray()
                async for chunk in resp.aiter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > MAX_BYTES:
                        raise UrlImportError("That document exceeds the 10 MB limit.")

                if not buffer:
                    raise UrlImportError("The URL returned an empty document.")

                return bytes(buffer), _filename_from(str(resp.url), ext)
        except httpx.HTTPError as exc:
            raise UrlImportError("Couldn't fetch the document from that URL.") from exc

    raise UrlImportError("Too many redirects while fetching the document.")
