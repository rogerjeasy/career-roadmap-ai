"""Swiss Job Portal client — jobs.ch and jobup.ch.

Switzerland doesn't have a well-known RapidAPI endpoint, so this client
uses structured HTTP requests to the public jobs.ch JSON search API
and jobup.ch (Ringier-owned multilingual Swiss portal).

Both portals expose undocumented but stable JSON endpoints that power
their own web frontends. We use responsible scraping patterns:
  - Reasonable rate limiting (already enforced at the MCP layer)
  - Standard browser headers
  - Respects robots.txt intent (job listing discovery is explicitly allowed)
  - No bypassing of login or paywalls
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any
from urllib.parse import urlencode

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

_JOBS_CH_API = "https://www.jobs.ch/api/v1/public/search/"
_JOBUP_API = "https://www.jobup.ch/api/search/jobs/"

_WORKLOAD_MAP: dict[str, EmploymentType] = {
    "100": EmploymentType.FULL_TIME,
    "80-100": EmploymentType.FULL_TIME,
    "60-80": EmploymentType.PART_TIME,
    "0-50": EmploymentType.PART_TIME,
}


class SwissJobsClient(BaseJobBoardClient):
    """Fetches Swiss job postings from jobs.ch and jobup.ch."""

    source = JobSource.SWISS_JOBS

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)

    def _default_headers(self) -> dict[str, str]:
        return {
            **super()._default_headers(),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.jobs.ch/",
            "Accept-Language": "en-GB,en;q=0.9,de-CH;q=0.8,de;q=0.7",
        }

    async def _search(
        self,
        params: SearchJobsParams,
        *,
        correlation_id: str = "",
    ) -> list[JobPosting]:
        # Fetch from both jobs.ch and jobup.ch concurrently
        import asyncio

        jobs_ch_results, jobup_results = await asyncio.gather(
            self._search_jobs_ch(params),
            self._search_jobup(params),
            return_exceptions=True,
        )

        postings: list[JobPosting] = []
        for result in [jobs_ch_results, jobup_results]:
            if isinstance(result, list):
                postings.extend(result)

        # Deduplicate by (title, company) hash
        seen: set[str] = set()
        unique: list[JobPosting] = []
        for p in postings:
            key = hashlib.md5(f"{p.title.lower()}:{p.company.lower()}".encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                unique.append(p)

        return unique[: params.limit]

    async def _search_jobs_ch(self, params: SearchJobsParams) -> list[JobPosting]:
        query_params: dict[str, Any] = {
            "query": params.role,
            "location": params.location or "Switzerland",
            "language": "en",
            "pageSize": min(params.limit, 20),
            "page": 1,
        }
        if params.remote:
            query_params["home_office"] = "true"

        resp = await self._get(_JOBS_CH_API, params=query_params)
        data = resp.json()

        postings: list[JobPosting] = []
        for item in data.get("documents", []):
            posting = _parse_jobs_ch(item)
            if posting:
                postings.append(posting)
        return postings

    async def _search_jobup(self, params: SearchJobsParams) -> list[JobPosting]:
        query_params: dict[str, Any] = {
            "term": params.role,
            "location": params.location or "Switzerland",
            "publication_date_since_num_days": 14,
            "rows": min(params.limit, 20),
            "start": 0,
        }
        if params.remote:
            query_params["home_office"] = 100

        resp = await self._get(_JOBUP_API, params=query_params)
        data = resp.json()

        postings: list[JobPosting] = []
        for item in data.get("documents", []):
            posting = _parse_jobup(item)
            if posting:
                postings.append(posting)
        return postings

    async def _get_trending_roles(
        self,
        country: str,
        limit: int,
        *,
        correlation_id: str = "",
    ) -> list[TrendingRole]:
        import asyncio

        if country.upper() != "CH":
            return []

        candidate_roles = [
            "Software Engineer", "Data Engineer", "DevOps Engineer",
            "Machine Learning Engineer", "Cloud Architect", "Full Stack Developer",
            "SAP Consultant", "Security Engineer", "IT Project Manager",
            "Data Scientist", "Backend Developer", "Frontend Developer",
        ]

        async def _probe_role(role: str) -> TrendingRole | None:
            try:
                week_resp, month_resp = await asyncio.gather(
                    self._get(_JOBUP_API, params={
                        "term": role,
                        "publication_date_since_num_days": 7,
                        "rows": 20,
                        "start": 0,
                    }),
                    self._get(_JOBUP_API, params={
                        "term": role,
                        "publication_date_since_num_days": 30,
                        "rows": 20,
                        "start": 0,
                    }),
                    return_exceptions=True,
                )
            except Exception:
                return None

            if isinstance(week_resp, Exception) or isinstance(month_resp, Exception):
                return None

            week_data = week_resp.json()
            month_data = month_resp.json()
            week_docs = week_data.get("documents", [])
            month_docs = month_data.get("documents", [])

            week_count = _extract_total(week_data, len(week_docs))
            month_count = _extract_total(month_data, len(month_docs))

            if month_count == 0:
                return None

            monthly_avg = month_count / 4.3
            growth = round((week_count / monthly_avg - 1.0) * 100, 1) if monthly_avg > 0 else 0.0
            growth = max(-100.0, min(500.0, growth))

            skill_freq: dict[str, int] = {}
            for item in week_docs:
                for skill in _extract_skills(str(item.get("description") or "")):
                    skill_freq[skill] = skill_freq.get(skill, 0) + 1
            top_skills = [s for s, _ in sorted(skill_freq.items(), key=lambda x: -x[1])[:5]]

            return TrendingRole(
                title=role,
                posting_count=month_count,
                growth_percent=growth,
                top_skills=top_skills,
                currency="CHF",
                country="CH",
                sources=[JobSource.SWISS_JOBS],
            )

        results: list[TrendingRole] = []
        batch_size = 3
        for i in range(0, len(candidate_roles[:max(limit * 2, 12)]), batch_size):
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

        results.sort(key=lambda r: (-r.posting_count, -(r.growth_percent or 0.0)))
        return results[:limit]


def _parse_jobs_ch(item: dict[str, Any]) -> JobPosting | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None

    job_id = str(item.get("id") or _make_id(title, item.get("company_name", "")))
    company = str(item.get("company_name") or item.get("company") or "Unknown")
    location = str(item.get("location") or item.get("place") or "Switzerland")

    posted_date: date | None = None
    for field in ("publication_date", "published_at", "created_at"):
        if raw := item.get(field):
            try:
                posted_date = date.fromisoformat(str(raw)[:10])
                break
            except (ValueError, TypeError):
                pass

    workload_raw = str(item.get("workload") or "100")
    emp_type = _WORKLOAD_MAP.get(workload_raw, EmploymentType.FULL_TIME)

    is_remote = bool(item.get("home_office")) or "home office" in title.lower()

    salary_min: int | None = None
    salary_max: int | None = None
    if salary := item.get("salary"):
        if isinstance(salary, dict):
            salary_min = _to_int(salary.get("min"))
            salary_max = _to_int(salary.get("max"))

    url = f"https://www.jobs.ch/en/vacancies/{job_id}/" if job_id else None

    return JobPosting(
        id=job_id,
        title=title,
        company=company,
        location=location,
        country="CH",
        remote=is_remote,
        employment_type=emp_type,
        description=str(item.get("description") or "")[:2000],
        required_skills=_extract_skills(str(item.get("description") or "")),
        salary_min=salary_min,
        salary_max=salary_max,
        currency="CHF",
        source=JobSource.SWISS_JOBS,
        source_url=url,
        posted_date=posted_date,
    )


def _parse_jobup(item: dict[str, Any]) -> JobPosting | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None

    job_id = str(item.get("id") or _make_id(title, item.get("company_name", "")))
    company = str(item.get("company_name") or "Unknown")
    location = str(item.get("place") or item.get("location") or "Switzerland")

    posted_date: date | None = None
    if raw := item.get("publication_date"):
        try:
            posted_date = date.fromisoformat(str(raw)[:10])
        except (ValueError, TypeError):
            pass

    workload_percent = _to_int(item.get("home_office") or item.get("workload_percentage"))
    emp_type = (
        EmploymentType.FULL_TIME if (workload_percent or 100) >= 80 else EmploymentType.PART_TIME
    )

    url = f"https://www.jobup.ch/en/jobs/detail/{job_id}/"

    return JobPosting(
        id=f"jobup_{job_id}",
        title=title,
        company=company,
        location=location,
        country="CH",
        remote=bool(item.get("home_office")),
        employment_type=emp_type,
        description=str(item.get("description") or "")[:2000],
        required_skills=_extract_skills(str(item.get("description") or "")),
        currency="CHF",
        source=JobSource.SWISS_JOBS,
        source_url=url,
        posted_date=posted_date,
    )


def _extract_skills(description: str) -> list[str]:
    skills = [
        "Java", "Python", "C#", ".NET", "JavaScript", "TypeScript", "Go", "Kotlin",
        "Docker", "Kubernetes", "Terraform", "AWS", "Azure", "GCP",
        "PostgreSQL", "MySQL", "Oracle", "MongoDB", "Redis", "Kafka",
        "Spring", "Angular", "React", "Vue.js", "Node.js",
        "SAP", "ABAP", "S/4HANA",
        "CI/CD", "Jenkins", "GitHub Actions", "GitLab",
        "Agile", "Scrum", "JIRA", "Confluence",
        "ISO 27001", "GDPR",
        "Linux", "SQL", "REST", "GraphQL", "microservices",
    ]
    found: list[str] = []
    lower = description.lower()
    for skill in skills:
        if skill.lower() in lower:
            found.append(skill)
        if len(found) >= 15:
            break
    return found


def _extract_total(data: dict[str, Any], fallback: int) -> int:
    for key in ("total", "count", "totalCount", "total_count", "numFound"):
        if (v := data.get(key)) is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
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
