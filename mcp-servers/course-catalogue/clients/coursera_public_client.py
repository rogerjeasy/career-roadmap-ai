"""Coursera public catalog client — no API key required.

Uses Coursera's public REST API v1.

  GET /api/courses.v1?q=slug&slug=<slug>  — fetch a specific course by slug
  GET /api/courses.v1?ids=<id1>,<id2>     — fetch courses by numeric ID

The q=search finder was removed by Coursera (returns 405). Search is now
handled exclusively by the curated dataset; this client only handles
get_detail lookups by slug for courses not in the curated set.

API reference: https://api.coursera.org/api/courses.v1
"""
from __future__ import annotations

import hashlib
from typing import Any

import structlog

from clients.base_client import BaseCourseClient
from models import Course, CourseSource, SearchCoursesParams, SkillLevel

logger = structlog.get_logger(__name__)

_LEVEL_MAP: dict[str, SkillLevel] = {
    "beginner": SkillLevel.BEGINNER,
    "intermediate": SkillLevel.INTERMEDIATE,
    "advanced": SkillLevel.ADVANCED,
    "mixed": SkillLevel.ALL,
}

_BASE_URL = "https://api.coursera.org/api"
_FIELDS = "name,slug,description,level,primaryLanguages,domainTypes,photo"


class CourseraPublicClient(BaseCourseClient):
    """Fetches Coursera course details via the public catalog API (no key required).

    The q=search finder is no longer available (Coursera API change — returns 405).
    _search returns an empty list; course discovery is handled by the curated dataset.
    _get_detail uses the q=slug finder which still works.
    """

    source = CourseSource.COURSERA

    async def _search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        # The Coursera public search API (q=search) was removed.
        # Search is handled by CuratedCoursesClient; this client only serves details.
        return []

    async def _get_detail(
        self,
        course_id: str,
        *,
        correlation_id: str = "",
    ) -> Course | None:
        """Fetch a Coursera course by its slug using the public catalog API."""
        try:
            resp = await self._get(
                f"{_BASE_URL}/courses.v1",
                params={
                    "q": "slug",
                    "slug": course_id,
                    "fields": _FIELDS,
                },
            )
            data = resp.json()
            items = data.get("elements", [])
            if not items:
                return None
            return _parse_item(items[0])
        except Exception as exc:
            logger.warning(
                "coursera_public.detail_failed",
                course_id=course_id,
                error=str(exc),
            )
            return None


def _parse_item(item: dict[str, Any]) -> Course | None:
    title = str(item.get("name") or "").strip()
    if not title:
        return None

    slug = str(item.get("slug") or item.get("id") or _make_id(title))
    url = f"https://www.coursera.org/learn/{slug}"

    level_raw = str(item.get("level") or "").lower()
    level = _LEVEL_MAP.get(level_raw, SkillLevel.ALL)

    domains = item.get("domainTypes") or []
    skills: list[str] = []
    for d in domains:
        if isinstance(d, dict):
            domain_id = d.get("domainId") or ""
            if domain_id:
                skills.append(str(domain_id).replace("-", " ").title())

    langs = item.get("primaryLanguages") or ["en"]
    language = langs[0].lower() if isinstance(langs, list) and langs else "en"

    photo = item.get("photo") or {}
    thumbnail = photo.get("photoUrl") if isinstance(photo, dict) else None

    return Course(
        id=slug,
        title=title,
        platform=CourseSource.COURSERA,
        instructor="",
        url=url,
        description=str(item.get("description") or "")[:2000],
        skills=skills,
        skill_level=level,
        free=True,
        language=language,
        certificate=True,
        thumbnail_url=thumbnail,
    )


def _make_id(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:16]
