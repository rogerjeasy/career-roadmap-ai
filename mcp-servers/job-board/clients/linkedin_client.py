"""LinkedIn Jobs client via RapidAPI (linkedin-job-search-api).

Uses the ``linkedin-job-search-api`` endpoint on RapidAPI which provides
real-time LinkedIn job listings updated hourly.

Endpoints used:
  GET /active-jb-7d  — jobs posted in the last 7 days (search + trending count)
  GET /active-jb-1h  — jobs posted in the last hour (trending growth signal)

API docs: https://rapidapi.com/mgujjargamingm/api/linkedin-job-search-api
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime
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

_BASE_URL = "https://linkedin-job-search-api.p.rapidapi.com"

_COUNTRY_TO_LOCATION: dict[str, str] = {
    "CH": "Switzerland",
    "DE": "Germany",
    "FR": "France",
    "AT": "Austria",
    "NL": "Netherlands",
    "BE": "Belgium",
    "ES": "Spain",
    "IT": "Italy",
    "PL": "Poland",
    "SE": "Sweden",
    "DK": "Denmark",
    "FI": "Finland",
    "NO": "Norway",
    "US": "United States",
    "CA": "Canada",
    "GB": "United Kingdom",
    "AU": "Australia",
    "SG": "Singapore",
    "IN": "India",
}

_SENIORITY_MAP: dict[str, ExperienceLevel] = {
    "entry level": ExperienceLevel.ENTRY,
    "associate": ExperienceLevel.ENTRY,
    "internship": ExperienceLevel.ENTRY,
    "mid-senior level": ExperienceLevel.MID,
    "mid level": ExperienceLevel.MID,
    "senior": ExperienceLevel.SENIOR,
    "director": ExperienceLevel.LEAD,
    "management": ExperienceLevel.LEAD,
    "executive": ExperienceLevel.EXECUTIVE,
    "c-level": ExperienceLevel.EXECUTIVE,
}

_EMPLOYMENT_MAP: dict[str, EmploymentType] = {
    "full-time": EmploymentType.FULL_TIME,
    "part-time": EmploymentType.PART_TIME,
    "contract": EmploymentType.CONTRACT,
    "internship": EmploymentType.INTERNSHIP,
    "temporary": EmploymentType.CONTRACT,
    "freelance": EmploymentType.FREELANCE,
}

_TRENDING_ROLES = [
    "Software Engineer", "Data Engineer", "Machine Learning Engineer",
    "DevOps Engineer", "Platform Engineer", "AI Engineer",
    "Backend Engineer", "Cloud Architect", "Data Scientist",
    "Security Engineer", "Frontend Engineer", "Site Reliability Engineer",
    "MLOps Engineer", "Product Manager", "Full Stack Developer",
]

_TECH_SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C#", "C++",
    "Docker", "Kubernetes", "Terraform", "AWS", "Azure", "GCP",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka", "Spark",
    "React", "Vue.js", "Angular", "Node.js", "FastAPI", "Django", "Spring",
    "PyTorch", "TensorFlow", "scikit-learn", "MLflow", "Airflow", "dbt",
    "CI/CD", "GitHub Actions", "Jenkins", "Prometheus", "Grafana",
    "SQL", "GraphQL", "REST", "gRPC", "Linux", "LangChain", "LangGraph",
]


class LinkedInClient(BaseJobBoardClient):
    """Fetches LinkedIn job postings via the linkedin-job-search-api on RapidAPI."""

    source = JobSource.LINKEDIN

    def __init__(
        self,
        api_key: str,
        api_host: str = "linkedin-job-search-api.p.rapidapi.com",
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
        location = _COUNTRY_TO_LOCATION.get(params.country.upper(), params.country)
        if params.location:
            location = params.location

        title_filter = f'"{params.role}"'
        location_filter = f'"{location}"'

        query_params: dict[str, Any] = {
            "limit": str(min(params.limit, 100)),
            "offset": "0",
            "title_filter": title_filter,
            "location_filter": location_filter,
            "description_type": "text",
        }

        resp = await self._get(f"https://{self._api_host}/active-jb-7d", params=query_params)
        data = resp.json()
        items = data if isinstance(data, list) else []

        postings: list[JobPosting] = []
        for item in items:
            posting = _parse_linkedin_item(item, params.country)
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
        location = _COUNTRY_TO_LOCATION.get(country.upper(), country)
        candidate_roles = _TRENDING_ROLES[:max(limit * 2, len(_TRENDING_ROLES))]

        async def _probe_role(role: str) -> TrendingRole | None:
            try:
                # 7d gives us the weekly posting count
                resp_7d = await self._get(
                    f"https://{self._api_host}/active-jb-7d",
                    params={
                        "limit": "100",
                        "offset": "0",
                        "title_filter": f'"{role}"',
                        "location_filter": f'"{location}"',
                        "description_type": "text",
                    },
                )
                items_7d = resp_7d.json() if isinstance(resp_7d.json(), list) else []
            except Exception:
                return None

            posting_count = len(items_7d)
            if posting_count == 0:
                return None

            skill_freq: dict[str, int] = {}
            for item in items_7d:
                desc = str(item.get("description_text") or "")
                for skill in _extract_skills(desc):
                    skill_freq[skill] = skill_freq.get(skill, 0) + 1
            top_skills = [s for s, _ in sorted(skill_freq.items(), key=lambda x: -x[1])[:5]]

            return TrendingRole(
                title=role,
                posting_count=posting_count,
                growth_percent=None,
                top_skills=top_skills,
                country=country,
                sources=[JobSource.LINKEDIN],
            )

        results: list[TrendingRole] = []
        batch_size = 3
        for i in range(0, len(candidate_roles), batch_size):
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


def _parse_linkedin_item(item: dict[str, Any], country: str) -> JobPosting | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None

    job_id = str(item.get("id") or _make_id(title, str(item.get("organization") or "")))
    company = str(item.get("organization") or "Unknown")
    url = str(item.get("url") or "")

    # Derive location from structured fields
    locations = item.get("locations_derived") or []
    location = str(locations[0]) if locations else country

    countries = item.get("countries_derived") or []
    inferred_country = _infer_country_code(countries, country)

    posted_date: date | None = None
    if posted_raw := item.get("date_posted"):
        try:
            posted_date = datetime.fromisoformat(str(posted_raw).replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            pass

    seniority_raw = str(item.get("seniority") or "").lower()
    exp_level = _SENIORITY_MAP.get(seniority_raw, ExperienceLevel.UNKNOWN)

    emp_raw = str(item.get("employment_type") or "").lower()
    emp_type = _EMPLOYMENT_MAP.get(emp_raw, EmploymentType.UNKNOWN)

    description = str(item.get("description_text") or "")[:2000]
    skills = _extract_skills(description)

    salary_min: int | None = None
    salary_max: int | None = None
    if sal := item.get("salary_raw"):
        if isinstance(sal, dict):
            salary_min = _to_int(sal.get("min") or sal.get("value"))
            salary_max = _to_int(sal.get("max"))

    return JobPosting(
        id=job_id,
        title=title,
        company=company,
        location=location,
        country=inferred_country,
        remote=bool(item.get("remote_derived", False)),
        employment_type=emp_type,
        experience_level=exp_level,
        description=description,
        required_skills=skills,
        salary_min=salary_min,
        salary_max=salary_max,
        currency="USD",
        source=JobSource.LINKEDIN,
        source_url=url,
        apply_url=item.get("external_apply_url") or url,
        posted_date=posted_date,
    )


def _extract_skills(description: str) -> list[str]:
    found: list[str] = []
    lower = description.lower()
    for skill in _TECH_SKILLS:
        if skill.lower() in lower and skill not in found:
            found.append(skill)
        if len(found) >= 10:
            break
    return found


def _infer_country_code(countries: list[str], fallback: str) -> str:
    name_to_code = {v.lower(): k for k, v in _COUNTRY_TO_LOCATION.items()}
    for name in countries:
        code = name_to_code.get(str(name).lower())
        if code:
            return code
    return fallback


def _make_id(title: str, company: str) -> str:
    return hashlib.sha256(f"{title}:{company}".encode()).hexdigest()[:16]


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
