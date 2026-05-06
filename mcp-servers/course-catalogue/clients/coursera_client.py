"""Coursera client via RapidAPI.

Uses the ``coursera`` endpoint on RapidAPI. Falls back to an empty result set
when the API key is absent.

API docs: https://rapidapi.com/search/coursera
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

import structlog

from clients.base_client import BaseCourseClient
from models import Course, CourseSource, SearchCoursesParams, SkillLevel

logger = structlog.get_logger(__name__)

_DIFFICULTY_MAP: dict[str, SkillLevel] = {
    "beginner": SkillLevel.BEGINNER,
    "intermediate": SkillLevel.INTERMEDIATE,
    "advanced": SkillLevel.ADVANCED,
    "mixed": SkillLevel.ALL,
}


class CourseraClient(BaseCourseClient):
    """Fetches Coursera courses via RapidAPI."""

    source = CourseSource.COURSERA

    def __init__(
        self,
        api_key: str,
        api_host: str = "coursera.p.rapidapi.com",
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
            "courseName": params.skill,
            "pageSize": min(params.limit, 20),
        }
        if params.language != "all":
            query_params["language"] = params.language
        if params.level != SkillLevel.ALL:
            query_params["difficulty"] = params.level.value

        resp = await self._get(f"{self._base_url}/", params=query_params)
        data = resp.json()

        courses: list[Course] = []
        items = data if isinstance(data, list) else data.get("elements", [])
        for item in items:
            course = _parse_coursera_item(item)
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
        resp = await self._get(f"{self._base_url}/{course_id}")
        data = resp.json()
        item = data if isinstance(data, dict) else (data[0] if data else None)
        return _parse_coursera_item(item) if item else None


def _parse_coursera_item(item: dict[str, Any]) -> Course | None:
    title = str(item.get("name") or item.get("title") or "").strip()
    if not title:
        return None

    slug = str(item.get("slug") or item.get("id") or _make_id(title))
    url = item.get("courseUrl") or item.get("url") or f"https://www.coursera.org/learn/{slug}"

    difficulty_raw = str(item.get("difficultyLevel") or item.get("difficulty") or "").lower()
    level = _DIFFICULTY_MAP.get(difficulty_raw, SkillLevel.ALL)

    # Partners/instructors
    partners = item.get("partners") or item.get("partnerIds") or []
    if isinstance(partners, list) and partners and isinstance(partners[0], dict):
        instructor = str(partners[0].get("name") or "")
    else:
        instructor = str(item.get("instructorName") or "")

    skills: list[str] = []
    if raw_skills := item.get("skills") or item.get("domainTypes"):
        if isinstance(raw_skills, list):
            skills = [str(s.get("name") or s) if isinstance(s, dict) else str(s) for s in raw_skills]

    # Coursera courses are free to audit but paid for certificates
    certificates = item.get("certificates") or []
    has_certificate = bool(certificates) or item.get("hasCertificate", False)

    rating_raw = item.get("rating") or item.get("avgRating")
    rating = float(rating_raw) if rating_raw else None
    if rating and rating > 5:  # some APIs return 0–100 scale
        rating = round(rating / 20, 1)

    num_ratings_raw = item.get("totalEnrolledLearners") or item.get("ratingCount") or 0

    published_date: date | None = None
    if date_str := item.get("createdAt") or item.get("launchDate"):
        try:
            published_date = date.fromisoformat(str(date_str)[:10])
        except (ValueError, TypeError):
            pass

    return Course(
        id=slug,
        title=title,
        platform=CourseSource.COURSERA,
        instructor=instructor,
        url=url,
        description=str(item.get("description") or item.get("headline") or "")[:2000],
        skills=skills,
        skill_level=level,
        rating=rating,
        num_ratings=int(num_ratings_raw) if num_ratings_raw else None,
        free=True,  # Coursera courses are free to audit
        language=str(item.get("primaryLanguages", ["en"])[0] if isinstance(item.get("primaryLanguages"), list) else item.get("language") or "en"),
        certificate=has_certificate,
        thumbnail_url=item.get("photoUrl") or item.get("imageUrl"),
        published_date=published_date,
    )


def _make_id(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:16]
