"""Indeed Jobs client via RapidAPI.

Uses the ``indeed12`` endpoint on RapidAPI which provides structured job data
without violating Indeed's Terms of Service for direct scraping.

API docs: https://rapidapi.com/Pat92/api/indeed12
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

import structlog

from clients.base_client import BaseJobBoardClient
from models import (
    EmploymentType,
    ExperienceLevel,
    JobPosting,
    JobSource,
    SearchJobsParams,
    TrendingRole,
)

logger = structlog.get_logger(__name__)

_INDEED_BASE = "https://indeed12.p.rapidapi.com"

_COUNTRY_CURRENCY: dict[str, str] = {
    "CH": "CHF", "DE": "EUR", "FR": "EUR", "AT": "EUR",
    "NL": "EUR", "ES": "EUR", "IT": "EUR", "BE": "EUR",
    "US": "USD", "CA": "CAD", "AU": "AUD", "GB": "GBP",
}


def _fix_encoding(s: str) -> str:
    """Fix double-encoded UTF-8 strings (e.g. ZÃ¼rich → Zürich)."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s

_COUNTRY_DOMAIN: dict[str, str] = {
    "CH": "ch",
    "DE": "de",
    "FR": "fr",
    "AT": "at",
    "NL": "nl",
    "ES": "es",
    "IT": "it",
    "US": "www",
    "GB": "uk",
    "CA": "ca",
    "AU": "au",
}


class IndeedClient(BaseJobBoardClient):
    """Fetches Indeed job postings via RapidAPI."""

    source = JobSource.INDEED

    def __init__(
        self,
        api_key: str,
        api_host: str = "indeed12.p.rapidapi.com",
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._api_key = api_key
        self._api_host = api_host

    def _default_headers(self) -> dict[str, str]:
        return {
            **super()._default_headers(),
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": self._api_host,
        }

    async def _search(
        self,
        params: SearchJobsParams,
        *,
        correlation_id: str = "",
    ) -> list[JobPosting]:
        country_domain = _COUNTRY_DOMAIN.get(params.country.upper(), "www")
        location = params.location or _country_to_city(params.country)

        query_params: dict[str, Any] = {
            "query": params.role,
            "location": location,
            "page_id": "1",
            "country": country_domain,
            "locality": params.country.lower(),
        }
        if params.remote:
            query_params["query"] = f"{params.role} remote"

        resp = await self._get(f"https://{self._api_host}/jobs/search", params=query_params)
        data = resp.json()

        postings: list[JobPosting] = []
        for item in data.get("hits", []):
            posting = _parse_indeed_item(item, params.country)
            if posting:
                postings.append(posting)
            if len(postings) >= params.limit:
                break

        return postings

    async def _get_trending_roles(
        self,
        country: str,
        limit: int,
        *,
        correlation_id: str = "",
    ) -> list[TrendingRole]:
        import asyncio

        country_domain = _COUNTRY_DOMAIN.get(country.upper(), "www")
        location = _country_to_city(country)
        candidate_roles = [
            "Software Engineer", "Data Engineer", "Machine Learning Engineer",
            "DevOps Engineer", "Platform Engineer", "AI Engineer",
            "Backend Developer", "Cloud Architect", "Data Scientist",
            "Security Engineer", "Frontend Developer", "Site Reliability Engineer",
            "MLOps Engineer", "Product Manager", "Full Stack Developer",
        ]

        async def _probe_role(role: str) -> TrendingRole | None:
            try:
                resp = await self._get(
                    f"https://{self._api_host}/jobs/search",
                    params={
                        "query": role,
                        "location": location,
                        "page_id": "1",
                        "country": country_domain,
                        "locality": country.lower(),
                    },
                )
                data = resp.json()
            except Exception:
                return None

            hits = data.get("hits", [])
            total = data.get("total", {})
            if isinstance(total, dict):
                posting_count = int(total.get("value", len(hits)))
            elif isinstance(total, (int, float)):
                posting_count = int(total)
            else:
                posting_count = len(hits)

            if posting_count == 0:
                return None

            skill_freq: dict[str, int] = {}
            for item in hits:
                desc = str(item.get("description") or item.get("snippet") or "")
                for skill in _extract_skills_from_description(desc):
                    skill_freq[skill] = skill_freq.get(skill, 0) + 1
            top_skills = [s for s, _ in sorted(skill_freq.items(), key=lambda x: -x[1])[:5]]

            return TrendingRole(
                title=role,
                posting_count=posting_count,
                growth_percent=None,
                top_skills=top_skills,
                country=country,
                sources=[JobSource.INDEED],
            )

        results: list[TrendingRole] = []
        batch_size = 3
        for i in range(0, min(len(candidate_roles), limit * 2), batch_size):
            batch = candidate_roles[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[_probe_role(role) for role in batch],
                return_exceptions=True,
            )
            for r in batch_results:
                if isinstance(r, TrendingRole):
                    results.append(r)
            if i + batch_size < len(candidate_roles):
                await asyncio.sleep(0.3)

        results.sort(key=lambda r: -r.posting_count)
        return results[:limit]


def _parse_indeed_item(item: dict[str, Any], country: str) -> JobPosting | None:
    title = _fix_encoding(str(item.get("title") or "").strip())
    if not title:
        return None

    job_id = str(item.get("id") or item.get("job_id") or _make_id(title, item.get("company", "")))

    posted_date: date | None = None
    for date_field in ("posted_at", "date", "posted_date"):
        if raw := item.get(date_field):
            try:
                posted_date = date.fromisoformat(str(raw)[:10])
                break
            except (ValueError, TypeError):
                pass

    salary_min: int | None = None
    salary_max: int | None = None
    currency = _COUNTRY_CURRENCY.get(country.upper(), "USD")
    if salary_raw := item.get("salary"):
        if isinstance(salary_raw, dict):
            salary_min = _to_int(salary_raw.get("min"))
            salary_max = _to_int(salary_raw.get("max"))
            api_currency = str(salary_raw.get("currency") or "").strip()
            if api_currency:
                currency = api_currency

    description = _fix_encoding(str(item.get("description") or item.get("snippet") or ""))[:2000]

    return JobPosting(
        id=job_id,
        title=title,
        company=_fix_encoding(str(item.get("company") or item.get("employer") or "Unknown")),
        location=_fix_encoding(str(item.get("location") or item.get("city") or "")),
        country=country,
        remote="remote" in description.lower() or "remote" in title.lower(),
        employment_type=_parse_employment(item.get("employment_type")),
        description=description,
        required_skills=_extract_skills_from_description(description),
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        source=JobSource.INDEED,
        source_url=item.get("url") or item.get("link"),
        apply_url=item.get("apply_url"),
        posted_date=posted_date,
    )


def _parse_employment(raw: Any) -> EmploymentType:
    if not raw:
        return EmploymentType.UNKNOWN
    text = str(raw).lower()
    if "full" in text:
        return EmploymentType.FULL_TIME
    if "part" in text:
        return EmploymentType.PART_TIME
    if "contract" in text:
        return EmploymentType.CONTRACT
    if "intern" in text:
        return EmploymentType.INTERNSHIP
    return EmploymentType.UNKNOWN


def _extract_skills_from_description(description: str) -> list[str]:
    """Heuristic skill extraction from job description text."""
    tech_skills = [
        "Python", "Java", "Go", "Rust", "JavaScript", "TypeScript", "C++",
        "Docker", "Kubernetes", "Terraform", "AWS", "Azure", "GCP",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka", "Spark",
        "FastAPI", "Django", "Spring Boot", "React", "Next.js",
        "PyTorch", "TensorFlow", "scikit-learn", "LangChain",
        "CI/CD", "GitHub Actions", "Jenkins", "Prometheus", "Grafana",
        "Linux", "Bash", "SQL", "GraphQL", "REST", "gRPC",
    ]
    found: list[str] = []
    lower_desc = description.lower()
    for skill in tech_skills:
        if skill.lower() in lower_desc and skill not in found:
            found.append(skill)
        if len(found) >= 15:
            break
    return found


def _make_id(title: str, company: str) -> str:
    return hashlib.sha256(f"{title}:{company}".encode()).hexdigest()[:16]


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _country_to_city(country: str) -> str:
    return {
        "CH": "Zurich",
        "DE": "Berlin",
        "FR": "Paris",
        "AT": "Vienna",
        "NL": "Amsterdam",
        "US": "New York",
        "GB": "London",
    }.get(country.upper(), "")
