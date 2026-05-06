"""Udemy client via RapidAPI.

Uses the ``udemy-paid-and-free-courses`` endpoint on RapidAPI.

API docs: https://rapidapi.com/search/udemy
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
    "beginner level": SkillLevel.BEGINNER,
    "intermediate": SkillLevel.INTERMEDIATE,
    "intermediate level": SkillLevel.INTERMEDIATE,
    "expert": SkillLevel.ADVANCED,
    "expert level": SkillLevel.ADVANCED,
    "all levels": SkillLevel.ALL,
}


class UdemyClient(BaseCourseClient):
    """Fetches Udemy courses via RapidAPI."""

    source = CourseSource.UDEMY

    def __init__(
        self,
        api_key: str,
        api_host: str = "udemy-paid-and-free-courses.p.rapidapi.com",
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
        endpoint = "/free-courses" if params.free_only else "/"
        query_params: dict[str, Any] = {
            "search": params.skill,
            "page": 1,
            "page_size": min(params.limit, 20),
        }
        if params.language != "en":
            query_params["language"] = params.language

        resp = await self._get(f"{self._base_url}{endpoint}", params=query_params)
        data = resp.json()

        courses: list[Course] = []
        items = data if isinstance(data, list) else data.get("results", data.get("courses", []))
        for item in items:
            course = _parse_udemy_item(item)
            if course:
                if params.free_only and not course.free:
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
        resp = await self._get(f"{self._base_url}/{course_id}")
        data = resp.json()
        item = data if isinstance(data, dict) else (data[0] if data else None)
        return _parse_udemy_item(item) if item else None


def _parse_udemy_item(item: dict[str, Any]) -> Course | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None

    course_id = str(item.get("id") or _make_id(title))
    url = item.get("url") or f"https://www.udemy.com/course/{_slugify(title)}/"
    if url.startswith("/"):
        url = f"https://www.udemy.com{url}"

    level_raw = str(item.get("instructional_level") or item.get("level") or "").lower()
    level = _LEVEL_MAP.get(level_raw, SkillLevel.ALL)

    instructor = ""
    if visible_instructors := item.get("visible_instructors"):
        if isinstance(visible_instructors, list) and visible_instructors:
            instructor = str(visible_instructors[0].get("display_name") or "")
    if not instructor:
        instructor = str(item.get("instructorName") or "")

    price_raw = item.get("price") or item.get("price_detail", {}).get("amount")
    is_free = item.get("is_paid") is False or str(price_raw or "").strip() in ("", "Free", "0", "0.0")
    price: float | None = None
    if not is_free and price_raw:
        try:
            price = float(str(price_raw).replace(",", "").replace("$", ""))
        except (ValueError, TypeError):
            pass

    rating_raw = item.get("rating") or item.get("avg_rating")
    rating = float(rating_raw) if rating_raw else None

    num_ratings_raw = item.get("num_reviews") or item.get("num_subscribers") or 0

    # Duration: Udemy returns content_length_video in seconds
    duration_hours: float | None = None
    if content_seconds := item.get("content_length_video"):
        try:
            duration_hours = round(int(content_seconds) / 3600, 1)
        except (ValueError, TypeError):
            pass

    published_date: date | None = None
    if date_str := item.get("published_time") or item.get("created"):
        try:
            published_date = date.fromisoformat(str(date_str)[:10])
        except (ValueError, TypeError):
            pass

    return Course(
        id=course_id,
        title=title,
        platform=CourseSource.UDEMY,
        instructor=instructor,
        url=url,
        description=str(item.get("headline") or item.get("description") or "")[:2000],
        skills=[],  # Udemy doesn't expose skills via this API
        skill_level=level,
        duration_hours=duration_hours,
        rating=rating,
        num_ratings=int(num_ratings_raw) if num_ratings_raw else None,
        price=price,
        currency="USD",
        free=is_free,
        language=str(item.get("locale", {}).get("simple_english_title") or "English").lower()[:2],
        certificate=True,  # all Udemy courses offer certificates
        thumbnail_url=item.get("image_480x270") or item.get("image_125_H"),
        published_date=published_date,
    )


def _make_id(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:16]


def _slugify(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
