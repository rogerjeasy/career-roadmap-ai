"""YouTube client using the YouTube Data API v3.

Searches for educational/tutorial videos. Uses two API calls:
1. ``/search`` — find videos matching the query
2. ``/videos`` — fetch duration and view counts for the returned IDs

Requires a Google Cloud API key with the YouTube Data API v3 enabled.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import structlog

from clients.base_client import BaseCourseClient
from models import Course, CourseSource, SearchCoursesParams, SkillLevel

logger = structlog.get_logger(__name__)

_YT_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeClient(BaseCourseClient):
    """Fetches educational YouTube videos via the YouTube Data API v3."""

    source = CourseSource.YOUTUBE

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._api_key = api_key

    async def _search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        query = f"{params.skill} tutorial course"
        if params.level != SkillLevel.ALL:
            query = f"{params.skill} {params.level.value} tutorial"

        search_resp = await self._get(
            f"{_YT_BASE}/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": min(params.limit, 25),
                "relevanceLanguage": params.language[:2],
                "safeSearch": "strict",
                "videoDuration": "long",
                "key": self._api_key,
            },
        )
        search_data = search_resp.json()
        items = search_data.get("items", [])
        if not items:
            return []

        video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]

        details_resp = await self._get(
            f"{_YT_BASE}/videos",
            params={
                "part": "contentDetails,statistics,snippet",
                "id": ",".join(video_ids),
                "key": self._api_key,
            },
        )
        details_data = details_resp.json()
        details_by_id: dict[str, dict[str, Any]] = {
            v["id"]: v for v in details_data.get("items", [])
        }

        courses: list[Course] = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            detail = details_by_id.get(video_id, {})
            course = _parse_youtube_item(item, detail)
            if course:
                courses.append(course)

        return courses

    async def _get_detail(
        self,
        course_id: str,
        *,
        correlation_id: str = "",
    ) -> Course | None:
        resp = await self._get(
            f"{_YT_BASE}/videos",
            params={
                "part": "contentDetails,statistics,snippet",
                "id": course_id,
                "key": self._api_key,
            },
        )
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return None
        item = items[0]
        return _parse_youtube_item(
            {"id": {"videoId": course_id}, "snippet": item.get("snippet", {})},
            item,
        )


def _parse_youtube_item(
    search_item: dict[str, Any],
    detail_item: dict[str, Any],
) -> Course | None:
    snippet = search_item.get("snippet") or detail_item.get("snippet") or {}
    video_id = search_item.get("id", {}).get("videoId") or detail_item.get("id", "")
    if not video_id:
        return None

    title = str(snippet.get("title") or "").strip()
    if not title:
        return None

    channel = str(snippet.get("channelTitle") or "")
    description = str(snippet.get("description") or "")

    thumbnail_url: str | None = None
    if thumbnails := snippet.get("thumbnails"):
        thumbnail_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

    duration_hours: float | None = None
    if content_details := detail_item.get("contentDetails"):
        duration_str = content_details.get("duration", "")
        duration_hours = _parse_iso8601_duration(duration_str)

    stats = detail_item.get("statistics", {})
    view_count_raw = stats.get("viewCount")
    num_ratings = int(view_count_raw) if view_count_raw else None

    rating: float | None = None
    likes = int(stats.get("likeCount") or 0)
    if likes and num_ratings:
        like_ratio = min(likes / max(num_ratings, 1), 1.0)
        rating = round(1.0 + like_ratio * 4.0, 1)

    published_date: date | None = None
    if published_at := snippet.get("publishedAt"):
        try:
            published_date = date.fromisoformat(str(published_at)[:10])
        except (ValueError, TypeError):
            pass

    return Course(
        id=video_id,
        title=title,
        platform=CourseSource.YOUTUBE,
        instructor=channel,
        url=f"https://www.youtube.com/watch?v={video_id}",
        description=description[:2000],
        skills=[],
        skill_level=SkillLevel.ALL,
        duration_hours=duration_hours,
        rating=rating,
        num_ratings=num_ratings,
        price=None,
        currency="USD",
        free=True,
        language="en",
        certificate=False,
        thumbnail_url=thumbnail_url,
        published_date=published_date,
    )


def _parse_iso8601_duration(duration: str) -> float | None:
    """Convert PT1H23M45S → hours as float."""
    if not duration:
        return None
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    total = hours + minutes / 60 + seconds / 3600
    return round(total, 2) if total > 0 else None
