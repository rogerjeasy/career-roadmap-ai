"""Open-Source Contribution Finder — service layer.

Searches GitHub's public Issues Search API for open "good first issue" tickets,
defaulting the language filter to the languages implied by the user's real
skills (from the session profile) and ranking results by skill overlap. Also
manages bookmarks so a user can track issues they intend to contribute to.
"""
from __future__ import annotations

import httpx
from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import ExternalServiceError, NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.http import get_http_client
from src.domains.oss.firestore_repository import FirestoreOssRepository
from src.domains.oss.schemas import (
    OssBookmarkCreate,
    OssBookmarkOut,
    OssIssue,
    OssSearchResult,
)
from src.domains.oss.skill_map import derive_languages, keyword_hints
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_GITHUB_SEARCH = "https://api.github.com/search/issues"
_GOOD_FIRST_LABELS = ('"good first issue"', '"good-first-issue"', '"help wanted"')


class OssService:
    def __init__(
        self,
        repo: FirestoreOssRepository,
        http: httpx.AsyncClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._http = http
        self._sessions = sessions

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(
        self, user_id: str, language: str | None, query: str | None
    ) -> OssSearchResult:
        skills = await self._user_skills(user_id)
        languages = [language] if language else derive_languages(skills)[:3]
        hints = keyword_hints(skills)

        q_parts = ['label:"good first issue"', "state:open", "type:issue"]
        if languages:
            # GitHub OR-style: one language qualifier per call works best; pick first.
            q_parts.append(f"language:{languages[0]}")
        if query:
            q_parts.append(query.strip())
        q = " ".join(q_parts)

        try:
            resp = await self._http.get(
                _GITHUB_SEARCH,
                params={"q": q, "sort": "updated", "order": "desc", "per_page": 30},
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "career-roadmap-ai",
                },
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            logger.warning("oss.github_unreachable", error=str(exc))
            raise ExternalServiceError("Couldn't reach GitHub. Please try again shortly.")

        if resp.status_code == 403:
            return OssSearchResult(
                issues=[],
                languages_used=languages,
                query_used=q,
                note="GitHub's anonymous search rate limit was hit. Try again in a minute.",
            )
        if resp.status_code >= 400:
            logger.warning("oss.github_error", status=resp.status_code)
            raise ExternalServiceError("GitHub search failed. Please try again shortly.")

        items = resp.json().get("items", [])
        issues = [self._to_issue(it, skills, languages) for it in items]
        issues = [i for i in issues if i is not None]
        issues.sort(key=lambda i: (i.match_score, i.comments), reverse=True)
        return OssSearchResult(
            issues=issues[:25],
            languages_used=languages,
            query_used=q,
            note="" if issues else "No matching issues right now — try a different language or keyword.",
        )

    # ── Bookmarks ─────────────────────────────────────────────────────────────

    async def list_bookmarks(self, user_id: str) -> list[OssBookmarkOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [OssBookmarkOut.from_doc(d) for d in docs]

    async def add_bookmark(
        self, user_id: str, payload: OssBookmarkCreate
    ) -> OssBookmarkOut:
        doc = await self._repo.create(user_id, payload.model_dump())
        logger.info("oss.bookmarked", user_id=user_id, issue_id=payload.issue_id)
        return OssBookmarkOut.from_doc(doc)

    async def update_bookmark_status(
        self, user_id: str, bookmark_id: str, status: str
    ) -> OssBookmarkOut:
        doc = await self._repo.update(bookmark_id, user_id, {"status": status})
        if doc is None:
            raise NotFoundError("Bookmark not found.")
        return OssBookmarkOut.from_doc(doc)

    async def remove_bookmark(self, user_id: str, bookmark_id: str) -> None:
        removed = await self._repo.soft_delete(bookmark_id, user_id)
        if not removed:
            raise NotFoundError("Bookmark not found.")

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _user_skills(self, user_id: str) -> list[str]:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        return list(profile.skills) if profile and profile.skills else []

    @staticmethod
    def _to_issue(item: dict, skills: list[str], languages: list[str]) -> OssIssue | None:
        if "pull_request" in item:  # the search endpoint mixes in PRs
            return None
        repo_url = item.get("repository_url", "")
        repo = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
        labels = [
            lb.get("name", "")
            for lb in item.get("labels", [])
            if isinstance(lb, dict) and lb.get("name")
        ]
        # Score: base for being a good-first-issue, plus label/keyword overlap.
        score = 50
        reasons: list[str] = []
        lower_skills = {s.lower() for s in skills}
        label_text = " ".join(labels).lower()
        title_text = str(item.get("title", "")).lower()
        matched = [s for s in lower_skills if s and (s in label_text or s in title_text)]
        if matched:
            score += min(40, 10 * len(matched))
            reasons.append("mentions " + ", ".join(sorted(matched)[:3]))
        if languages:
            reasons.append(f"{languages[0]} repo")
            score += 5
        return OssIssue(
            issue_id=int(item.get("id", 0)),
            title=str(item.get("title", "")),
            url=str(item.get("html_url", "")),
            repo=repo,
            repo_url=repo_url.replace("api.github.com/repos", "github.com"),
            language=languages[0] if languages else "",
            labels=labels,
            comments=int(item.get("comments", 0)),
            updated_at=str(item.get("updated_at", "")),
            match_score=min(100, score),
            match_reason="A solid starter issue" + (" — " + "; ".join(reasons) if reasons else ""),
        )


async def get_oss_service(
    db: AsyncClient = Depends(get_firestore_client),
    http: httpx.AsyncClient = Depends(get_http_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> OssService:
    return OssService(FirestoreOssRepository(db), http, sessions)
