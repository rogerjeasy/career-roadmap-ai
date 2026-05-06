"""edX client using the public edX Discovery API.

No API key required. Uses the discovery.edx.org catalog search endpoint.

API docs: https://discovery.edx.org/api/v1/
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

import structlog

from clients.base_client import BaseCourseClient
from models import Course, CourseSource, SearchCoursesParams, SkillLevel

logger = structlog.get_logger(__name__)

_LEVEL_MAP: dict[str, SkillLevel] = {
    "introductory": SkillLevel.BEGINNER,
    "beginner": SkillLevel.BEGINNER,
    "intermediate": SkillLevel.INTERMEDIATE,
    "advanced": SkillLevel.ADVANCED,
    "": SkillLevel.ALL,
}


class EdxClient(BaseCourseClient):
    """Fetches edX courses via the public discovery catalog API."""

    source = CourseSource.EDX

    def __init__(
        self,
        discovery_base_url: str = "https://discovery.edx.org",
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._base_url = discovery_base_url.rstrip("/")

    async def _search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        query_params: dict[str, Any] = {
            "q": params.skill,
            "content_type": "course",
            "page_size": min(params.limit, 20),
            "page": 1,
        }
        if params.level != SkillLevel.ALL:
            query_params["level_type"] = params.level.value.capitalize()
        if params.language and params.language != "en":
            query_params["language"] = params.language

        resp = await self._get(
            f"{self._base_url}/api/v1/search/all/",
            params=query_params,
        )
        data = resp.json()

        courses: list[Course] = []
        items = data.get("results", [])
        for item in items:
            course = _parse_edx_item(item)
            if course:
                if params.free_only and not course.free:
                    continue
                courses.append(course)
            if len(courses) >= params.limit:
                break
        return courses

    async def _get_detail(
        self,
        course_id: str,
        *,
        correlation_id: str = "",
    ) -> Course | None:
        resp = await self._get(f"{self._base_url}/api/v1/courses/{course_id}/")
        data = resp.json()
        return _parse_edx_item(data) if data else None


def _parse_edx_item(item: dict[str, Any]) -> Course | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None

    course_key = str(item.get("key") or item.get("uuid") or _make_id(title))
    marketing_url = str(item.get("marketing_url") or item.get("course_url") or "")
    if not marketing_url:
        marketing_url = f"https://www.edx.org/course/{_slugify(title)}"

    level_raw = str(item.get("level_type") or "").lower()
    level = _LEVEL_MAP.get(level_raw, SkillLevel.ALL)

    # Owners are the universities/orgs
    owners = item.get("owners") or []
    instructor = ""
    if isinstance(owners, list) and owners:
        instructor = str(owners[0].get("name") or owners[0].get("key") or "")

    # Subjects as skills proxy
    subjects = item.get("subjects") or []
    skills: list[str] = [s.get("name") or s if isinstance(s, dict) else str(s) for s in subjects]

    published_date: date | None = None
    for date_field in ("start", "enrollment_start", "modified"):
        if date_str := item.get(date_field):
            try:
                published_date = date.fromisoformat(str(date_str)[:10])
                break
            except (ValueError, TypeError):
                continue

    # edX courses are free to audit
    entitlements = item.get("entitlements") or []
    has_paid = any(e.get("mode") == "verified" for e in entitlements if isinstance(e, dict))

    image = item.get("image") or {}
    thumbnail_url = image.get("src") if isinstance(image, dict) else None

    return Course(
        id=course_key,
        title=title,
        platform=CourseSource.EDX,
        instructor=instructor,
        url=marketing_url,
        description=str(item.get("full_description") or item.get("short_description") or "")[:2000],
        skills=skills,
        skill_level=level,
        duration_hours=None,  # not exposed in catalog search
        rating=None,
        num_ratings=None,
        price=None,
        currency="USD",
        free=True,  # edX audit track is free
        language=str(item.get("language") or "en"),
        certificate=has_paid,
        thumbnail_url=thumbnail_url,
        published_date=published_date,
    )


def _make_id(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:16]


def _slugify(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
