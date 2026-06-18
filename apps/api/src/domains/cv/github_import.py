"""Build a CV-like text profile from a public GitHub account.

Unlike LinkedIn, GitHub exposes a clean, documented public REST API, so this is
a first-party integration — no scraping. Given a username (or a github.com
profile URL) we fetch the user record and their public repositories, then
synthesise a plain-text "CV" that the existing CV-analysis pipeline can parse
exactly like an uploaded document.

Only public data is read. An optional ``GITHUB_API_TOKEN`` raises the
unauthenticated rate limit (60 → 5000 req/hr) but is never required.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from src.config import settings

_API = "https://api.github.com"
_TIMEOUT = httpx.Timeout(15.0)
_MAX_REPOS = 12  # top repos by stars included in the synthesised profile
_HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


class GithubImportError(Exception):
    """A client-correctable problem importing a GitHub profile (→ HTTP 422)."""


def parse_handle(raw: str) -> str:
    """Extract a GitHub username from a handle or a github.com profile URL.

    Accepts ``octocat``, ``@octocat``, ``github.com/octocat``,
    ``https://github.com/octocat/``. Raises ``GithubImportError`` if no valid
    handle can be derived.
    """
    value = (raw or "").strip()
    if not value:
        raise GithubImportError("Enter a GitHub username or profile URL.")

    if "github.com" in value:
        # Tolerate a missing scheme so urlparse finds the host.
        parsed = urlparse(value if "//" in value else f"https://{value}")
        if (parsed.hostname or "").lower() not in ("github.com", "www.github.com"):
            raise GithubImportError("That doesn't look like a github.com profile URL.")
        segments = [s for s in parsed.path.split("/") if s]
        if not segments:
            raise GithubImportError("That GitHub URL has no username.")
        value = segments[0]

    value = value.lstrip("@")
    if not _HANDLE_RE.match(value):
        raise GithubImportError("That isn't a valid GitHub username.")
    return value


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "career-roadmap-ai",
    }
    token = settings.github_api_token
    if token:
        headers["Authorization"] = f"Bearer {token.get_secret_value()}"
    return headers


async def _get(client: httpx.AsyncClient, path: str, **params: object) -> object:
    try:
        resp = await client.get(
            f"{_API}{path}",
            headers=_headers(),
            params=params,
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        raise GithubImportError("Couldn't reach GitHub — please try again.") from exc

    if resp.status_code == 404:
        raise GithubImportError("No public GitHub profile found for that username.")
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        raise GithubImportError("GitHub rate limit reached — please try again later.")
    if resp.status_code != 200:
        raise GithubImportError(f"GitHub returned HTTP {resp.status_code}.")
    return resp.json()


def _render_profile(user: dict, repos: list[dict]) -> str:
    """Render the fetched data as a plain-text CV the analyser can parse."""
    lines: list[str] = []
    name = user.get("name") or user.get("login") or "GitHub User"
    lines.append(name)
    headline_bits = [b for b in (user.get("company"), user.get("location")) if b]
    if headline_bits:
        lines.append(" · ".join(str(b) for b in headline_bits))
    lines.append(f"GitHub: https://github.com/{user.get('login', '')}")
    if user.get("blog"):
        lines.append(f"Website: {user['blog']}")
    lines.append("")

    if user.get("bio"):
        lines.append("SUMMARY")
        lines.append(str(user["bio"]).strip())
        lines.append("")

    lines.append("GITHUB ACTIVITY")
    lines.append(
        f"Public repositories: {user.get('public_repos', 0)} · "
        f"Followers: {user.get('followers', 0)}"
    )
    lines.append("")

    # Aggregate the languages across the included repos as a skills signal.
    languages = sorted(
        {str(r["language"]) for r in repos if r.get("language")},
    )
    if languages:
        lines.append("SKILLS (from repository languages)")
        lines.append(", ".join(languages))
        lines.append("")

    if repos:
        lines.append("NOTABLE PROJECTS")
        for r in repos:
            stars = r.get("stargazers_count", 0)
            lang = f" [{r['language']}]" if r.get("language") else ""
            header = f"- {r.get('name', 'repo')}{lang} — {stars}★"
            lines.append(header)
            if r.get("description"):
                lines.append(f"  {str(r['description']).strip()}")
            if r.get("topics"):
                lines.append(f"  Topics: {', '.join(str(t) for t in r['topics'][:8])}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


async def build_profile_document(
    raw_handle: str, client: httpx.AsyncClient
) -> tuple[bytes, str]:
    """Fetch a GitHub profile and return ``(text_bytes, filename)``.

    The returned bytes are a UTF-8 ``.txt`` document so they flow through the
    same parse → analyse → store pipeline as a file upload. Raises
    ``GithubImportError`` for unknown users, rate limits, or network failures.
    """
    handle = parse_handle(raw_handle)

    user = await _get(client, f"/users/{handle}")
    if not isinstance(user, dict):
        raise GithubImportError("Unexpected response from GitHub.")

    repos_raw = await _get(
        client,
        f"/users/{handle}/repos",
        per_page=100,
        sort="updated",
        type="owner",
    )
    repos: list[dict] = repos_raw if isinstance(repos_raw, list) else []
    # Exclude forks, rank by stars, keep the top N.
    own = [r for r in repos if isinstance(r, dict) and not r.get("fork")]
    own.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    top = own[:_MAX_REPOS]

    text = _render_profile(user, top)
    if len(text.strip()) < 20:
        raise GithubImportError(
            "That GitHub profile has too little public information to import."
        )
    return text.encode("utf-8"), f"{handle}-github.txt"
