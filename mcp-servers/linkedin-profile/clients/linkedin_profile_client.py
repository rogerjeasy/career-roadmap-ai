"""LinkedIn Profile API client via RapidAPI.

Uses the 'linkedin-data-api' endpoint on RapidAPI to fetch public profile data.
When no API key is configured the client returns None for all calls.

API: https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api
"""
from __future__ import annotations

import os
import sys
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from models import (
    ConnectionSuggestion,
    ConnectionDegree,
    LinkedInEducation,
    LinkedInExperience,
    LinkedInProfile,
)
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)


class LinkedInProfileClient:
    """Fetches LinkedIn profile data via RapidAPI."""

    def __init__(
        self,
        api_key: str,
        api_host: str = "linkedin-data-api.p.rapidapi.com",
        *,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._api_host = api_host
        self._base_url = f"https://{api_host}"
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            "linkedin_profile.rapidapi",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={
                    "Accept": "application/json",
                    "X-RapidAPI-Key": self._api_key,
                    "X-RapidAPI-Host": self._api_host,
                    "User-Agent": "CareerRoadmapAI/1.0",
                },
                follow_redirects=True,
                limits=httpx.Limits(max_connections=30, max_keepalive_connections=10),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        resp = await self._get_client().get(f"{self._base_url}{path}", params=params)
        resp.raise_for_status()
        return resp

    async def fetch_profile(
        self,
        profile_url: str,
        *,
        correlation_id: str = "",
    ) -> LinkedInProfile | None:
        """Fetch a LinkedIn profile by URL. Returns None on any failure."""
        # Extract the username / public-id from the URL
        username = _extract_username(profile_url)
        if not username:
            logger.warning(
                "linkedin_profile.invalid_url",
                url=profile_url,
                correlation_id=correlation_id,
            )
            return None

        async def _fetch() -> LinkedInProfile | None:
            try:
                resp = await self._get("/get-profile-data-by-url", params={"url": profile_url})
                data = resp.json()
                return _parse_profile(data, profile_url)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.info(
                        "linkedin_profile.not_found",
                        username=username,
                        correlation_id=correlation_id,
                    )
                    return None
                raise

        try:
            return await self._breaker.call(_fetch())
        except CircuitOpenError:
            logger.warning(
                "linkedin_profile.circuit_open",
                username=username,
                correlation_id=correlation_id,
            )
            return None
        except Exception as exc:
            logger.warning(
                "linkedin_profile.fetch_failed",
                username=username,
                error=str(exc),
                correlation_id=correlation_id,
            )
            return None

    async def search_people(
        self,
        keywords: list[str],
        location: str | None,
        limit: int,
        *,
        correlation_id: str = "",
    ) -> list[ConnectionSuggestion]:
        """Search for LinkedIn members matching skills/keywords."""
        query = " ".join(keywords[:10])

        async def _fetch() -> list[ConnectionSuggestion]:
            params: dict[str, Any] = {"keywords": query, "count": min(limit, 25)}
            if location:
                params["location"] = location

            resp = await self._get("/search-people", params=params)
            data = resp.json()
            results = data.get("items", data if isinstance(data, list) else [])

            suggestions: list[ConnectionSuggestion] = []
            for item in results[:limit]:
                sugg = _parse_suggestion(item, keywords)
                if sugg:
                    suggestions.append(sugg)
            return suggestions

        try:
            return await self._breaker.call(_fetch())
        except CircuitOpenError:
            logger.warning("linkedin_profile.people_search_circuit_open", correlation_id=correlation_id)
            return []
        except Exception as exc:
            logger.warning(
                "linkedin_profile.people_search_failed",
                error=str(exc),
                correlation_id=correlation_id,
            )
            return []


# ── Parsers ───────────────────────────────────────────────────────────────────

def _extract_username(url: str) -> str:
    parts = url.rstrip("/").split("/")
    for i, part in enumerate(parts):
        if part == "in" and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1] if parts else ""


def _parse_profile(data: dict[str, Any], profile_url: str) -> LinkedInProfile | None:
    full_name = str(
        data.get("fullName") or
        f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
    )
    if not full_name:
        return None

    profile_id = str(data.get("id") or data.get("publicIdentifier") or _extract_username(profile_url))

    experiences: list[LinkedInExperience] = []
    for exp in data.get("experience", data.get("experiences", [])):
        if not isinstance(exp, dict):
            continue
        experiences.append(
            LinkedInExperience(
                title=str(exp.get("title") or ""),
                company=str(exp.get("companyName") or exp.get("company") or ""),
                location=exp.get("location"),
                start_date=_format_date(exp.get("start") or exp.get("startDate")),
                end_date=_format_date(exp.get("end") or exp.get("endDate")),
                is_current=bool(exp.get("isCurrent") or not exp.get("end")),
                description=str(exp.get("description") or "")[:1000] or None,
            )
        )

    education: list[LinkedInEducation] = []
    for edu in data.get("education", data.get("educations", [])):
        if not isinstance(edu, dict):
            continue
        education.append(
            LinkedInEducation(
                school=str(edu.get("schoolName") or edu.get("school") or ""),
                degree=edu.get("degreeName") or edu.get("degree"),
                field_of_study=edu.get("fieldOfStudy"),
                start_date=_format_date(edu.get("start") or edu.get("startDate")),
                end_date=_format_date(edu.get("end") or edu.get("endDate")),
            )
        )

    skills_raw = data.get("skills") or []
    skills = [
        str(s.get("name") or s) if isinstance(s, dict) else str(s)
        for s in skills_raw
    ]

    return LinkedInProfile(
        id=profile_id,
        full_name=full_name,
        headline=data.get("headline"),
        summary=str(data.get("summary") or "")[:2000] or None,
        location=data.get("location") or data.get("geoLocationName"),
        profile_url=profile_url,
        avatar_url=data.get("profilePicture") or data.get("photoUrl"),
        connections=data.get("connectionsCount"),
        followers=data.get("followersCount"),
        skills=skills[:50],
        experiences=experiences,
        education=education,
        languages=[
            str(lang.get("name") or lang) if isinstance(lang, dict) else str(lang)
            for lang in (data.get("languages") or [])
        ],
        certifications=[
            str(cert.get("name") or cert) if isinstance(cert, dict) else str(cert)
            for cert in (data.get("certifications") or [])
        ],
    )


def _parse_suggestion(item: dict[str, Any], keywords: list[str]) -> ConnectionSuggestion | None:
    full_name = str(
        item.get("fullName") or
        f"{item.get('firstName', '')} {item.get('lastName', '')}".strip()
    )
    if not full_name:
        return None

    profile_id = str(item.get("id") or item.get("publicIdentifier") or full_name.replace(" ", "_").lower())
    profile_url = item.get("profileUrl") or f"https://www.linkedin.com/in/{profile_id}"

    skills_raw = item.get("skills") or []
    skills = [
        str(s.get("name") or s) if isinstance(s, dict) else str(s)
        for s in skills_raw
    ]
    keywords_lower = {k.lower() for k in keywords}
    shared = [s for s in skills if s.lower() in keywords_lower]

    return ConnectionSuggestion(
        id=profile_id,
        full_name=full_name,
        headline=item.get("headline"),
        location=item.get("location"),
        profile_url=profile_url,
        avatar_url=item.get("profilePicture") or item.get("photoUrl"),
        shared_skills=shared[:10],
        relevance_score=min(1.0, len(shared) * 0.2 + 0.1),
        reason=f"Shares {len(shared)} skills with your target profile" if shared else "Works in your target domain",
    )


def _format_date(raw: Any) -> str | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        year = raw.get("year")
        month = raw.get("month")
        if year:
            return f"{year}-{month:02d}" if month else str(year)
        return None
    return str(raw)[:10] if raw else None
