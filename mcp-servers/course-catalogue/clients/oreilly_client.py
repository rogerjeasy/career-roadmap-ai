"""O'Reilly Learning client via RapidAPI.

Uses the O'Reilly Learning API on RapidAPI to search books and video courses.
Falls back to an empty result set when the API key is absent.

API docs: https://rapidapi.com/search/oreilly
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
    "beginner": SkillLevel.BEGINNER,
    "intermediate": SkillLevel.INTERMEDIATE,
    "advanced": SkillLevel.ADVANCED,
}


class OReillyClient(BaseCourseClient):
    """Fetches O'Reilly Learning content via RapidAPI."""

    source = CourseSource.OREILLY

    def __init__(
        self,
        api_key: str,
        api_host: str = "oreilly-learning.p.rapidapi.com",
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._api_key = api_key
        self._api_host = api_host
        self._base_url = f"https://{api_host}"

    def _default_headers(self) -> dict[str, str]:
        return {
            **super()._default_headers(),
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": self._api_host,
        }

    async def _search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        query_params: dict[str, Any] = {
            "query": params.skill,
            "formats": "video,learning_path",
            "page_size": min(params.limit, 20),
            "page": 1,
            "language": params.language,
        }
        if params.level != SkillLevel.ALL:
            query_params["level"] = params.level.value

        resp = await self._get(f"{self._base_url}/search", params=query_params)
        data = resp.json()

        courses: list[Course] = []
        items = data.get("results", data if isinstance(data, list) else [])
        for item in items:
            course = _parse_oreilly_item(item)
            if course:
                # O'Reilly is subscription-based, never free
                if params.free_only:
                    continue
                if params.level != SkillLevel.ALL and course.skill_level not in (
                    params.level, SkillLevel.ALL
                ):
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
        resp = await self._get(f"{self._base_url}/content/{course_id}")
        data = resp.json()
        item = data if isinstance(data, dict) else (data[0] if data else None)
        return _parse_oreilly_item(item) if item else None


def _parse_oreilly_item(item: dict[str, Any]) -> Course | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None

    content_id = str(item.get("id") or item.get("isbn") or _make_id(title))
    url = (
        item.get("url")
        or item.get("web_url")
        or f"https://learning.oreilly.com/library/view/-/{content_id}/"
    )

    # Authors
    authors = item.get("authors") or []
    instructor = ""
    if isinstance(authors, list) and authors:
        if isinstance(authors[0], dict):
            instructor = str(authors[0].get("name") or authors[0].get("full_name") or "")
        else:
            instructor = str(authors[0])

    # Topics as skills
    topics = item.get("topics") or item.get("tags") or []
    skills: list[str] = []
    for t in topics:
        if isinstance(t, dict):
            if name := t.get("name") or t.get("slug"):
                skills.append(str(name))
        else:
            skills.append(str(t))

    level_raw = str(item.get("difficulty") or item.get("level") or "").lower()
    level = _LEVEL_MAP.get(level_raw, SkillLevel.ALL)

    # Duration: O'Reilly reports minutes
    duration_hours: float | None = None
    if minutes_raw := item.get("duration_seconds") or item.get("minutes_of_content"):
        try:
            # handle both seconds and minutes
            key = item.get("duration_seconds")
            if key:
                duration_hours = round(int(minutes_raw) / 3600, 1)
            else:
                duration_hours = round(int(minutes_raw) / 60, 1)
        except (ValueError, TypeError):
            pass

    rating_raw = item.get("average_rating") or item.get("rating")
    rating = float(rating_raw) if rating_raw else None
    if rating and rating > 5:
        rating = round(rating / 20, 1)

    published_date: date | None = None
    for date_field in ("issued", "published", "publication_date"):
        if date_str := item.get(date_field):
            try:
                published_date = date.fromisoformat(str(date_str)[:10])
                break
            except (ValueError, TypeError):
                continue

    cover_image = item.get("cover_image") or item.get("thumbnail_url")

    return Course(
        id=content_id,
        title=title,
        platform=CourseSource.OREILLY,
        instructor=instructor,
        url=url,
        description=str(item.get("description") or item.get("headline") or "")[:2000],
        skills=skills,
        skill_level=level,
        duration_hours=duration_hours,
        rating=rating,
        num_ratings=None,  # O'Reilly doesn't expose rating counts
        price=None,  # subscription-based
        currency="USD",
        free=False,
        language=str(item.get("language") or "en"),
        certificate=False,
        thumbnail_url=cover_image,
        published_date=published_date,
    )


def _make_id(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:16]
