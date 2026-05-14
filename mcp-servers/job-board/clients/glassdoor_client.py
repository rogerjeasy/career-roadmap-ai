"""Glassdoor Jobs client via RapidAPI (real-time-glassdoor-data).

Uses the ``real-time-glassdoor-data`` endpoint on RapidAPI which provides
job listings and salary estimation data from Glassdoor.

Endpoints used:
  GET /job-search         — job listings by query + location
  GET /salary-estimation  — salary benchmarks by job title + location

API docs: https://rapidapi.com/Lakzian/api/real-time-glassdoor-data
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import date, timedelta
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

_COUNTRY_TO_LOCATION: dict[str, str] = {
    "CH": "Zurich, Switzerland",
    "DE": "Berlin, Germany",
    "FR": "Paris, France",
    "AT": "Vienna, Austria",
    "NL": "Amsterdam, Netherlands",
    "BE": "Brussels, Belgium",
    "ES": "Madrid, Spain",
    "IT": "Rome, Italy",
    "PL": "Warsaw, Poland",
    "SE": "Stockholm, Sweden",
    "DK": "Copenhagen, Denmark",
    "NO": "Oslo, Norway",
    "US": "New York, NY",
    "CA": "Toronto, Ontario",
    "GB": "London, United Kingdom",
    "AU": "Sydney, Australia",
    "SG": "Singapore",
    "IN": "Bangalore, India",
}

_COUNTRY_TO_DOMAIN: dict[str, str] = {
    "GB": "www.glassdoor.co.uk",
    "DE": "www.glassdoor.de",
    "FR": "www.glassdoor.fr",
    "AU": "www.glassdoor.com.au",
    "SG": "www.glassdoor.sg",
    "IN": "www.glassdoor.co.in",
}
_DEFAULT_DOMAIN = "www.glassdoor.com"

_COUNTRY_CURRENCY: dict[str, str] = {
    "CH": "CHF",
    "DE": "EUR", "FR": "EUR", "AT": "EUR",
    "NL": "EUR", "BE": "EUR", "ES": "EUR",
    "IT": "EUR", "PL": "EUR", "SE": "EUR",
    "DK": "DKK", "NO": "NOK",
    "US": "USD", "CA": "CAD",
    "GB": "GBP", "AU": "AUD",
    "SG": "SGD", "IN": "INR",
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


def _fix_encoding(s: str) -> str:
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


class GlassdoorClient(BaseJobBoardClient):
    """Fetches Glassdoor job postings via real-time-glassdoor-data on RapidAPI."""

    source = JobSource.GLASSDOOR

    def __init__(
        self,
        api_key: str,
        api_host: str = "real-time-glassdoor-data.p.rapidapi.com",
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
        location = params.location or _COUNTRY_TO_LOCATION.get(params.country.upper(), params.country)
        domain = _COUNTRY_TO_DOMAIN.get(params.country.upper(), _DEFAULT_DOMAIN)
        currency = _COUNTRY_CURRENCY.get(params.country.upper(), "USD")

        query = params.role
        if params.remote:
            query = f"{params.role} remote"

        query_params: dict[str, Any] = {
            "query": query,
            "location": location,
            "location_type": "ANY",
            "min_company_rating": "ANY",
            "domain": domain,
        }

        resp = await self._get(f"https://{self._api_host}/job-search", params=query_params)
        data = resp.json()

        jobs_raw: list[dict] = []
        if isinstance(data, dict):
            inner = data.get("data") or {}
            if isinstance(inner, dict):
                jobs_raw = inner.get("jobs") or []
            elif isinstance(inner, list):
                jobs_raw = inner
        elif isinstance(data, list):
            jobs_raw = data

        postings: list[JobPosting] = []
        for item in jobs_raw:
            posting = _parse_glassdoor_item(item, params.country, currency)
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
        domain = _COUNTRY_TO_DOMAIN.get(country.upper(), _DEFAULT_DOMAIN)
        currency = _COUNTRY_CURRENCY.get(country.upper(), "USD")
        candidate_roles = _TRENDING_ROLES[:max(limit * 2, len(_TRENDING_ROLES))]

        async def _probe_role(role: str) -> TrendingRole | None:
            try:
                jobs_resp, salary_resp = await asyncio.gather(
                    self._get(
                        f"https://{self._api_host}/job-search",
                        params={
                            "query": role,
                            "location": location,
                            "location_type": "ANY",
                            "min_company_rating": "ANY",
                            "domain": domain,
                        },
                    ),
                    self._get(
                        f"https://{self._api_host}/salary-estimation",
                        params={
                            "job_title": role,
                            "location": location,
                            "location_type": "ANY",
                            "years_of_experience": "ALL",
                            "domain": domain,
                        },
                    ),
                    return_exceptions=True,
                )
            except Exception:
                return None

            # Parse job listing count
            jobs_raw: list[dict] = []
            if not isinstance(jobs_resp, Exception):
                data = jobs_resp.json()
                if isinstance(data, dict):
                    inner = data.get("data") or {}
                    if isinstance(inner, dict):
                        jobs_raw = inner.get("jobs") or []
                    elif isinstance(inner, list):
                        jobs_raw = inner

            posting_count = len(jobs_raw)
            if posting_count == 0:
                return None

            # Extract skills from job descriptions
            skill_freq: dict[str, int] = {}
            for item in jobs_raw:
                desc = str(item.get("job_description") or item.get("description") or "")
                for skill in _extract_skills(desc):
                    skill_freq[skill] = skill_freq.get(skill, 0) + 1
            top_skills = [s for s, _ in sorted(skill_freq.items(), key=lambda x: -x[1])[:5]]

            # Parse salary data
            median_salary: int | None = None
            sal_currency = currency
            if not isinstance(salary_resp, Exception):
                sal_data = salary_resp.json()
                if isinstance(sal_data, dict):
                    sal_inner = sal_data.get("data") or {}
                    if isinstance(sal_inner, dict):
                        if v := sal_inner.get("median_base_salary"):
                            try:
                                median_salary = int(float(v))
                            except (TypeError, ValueError):
                                pass
                        if c := sal_inner.get("salary_currency"):
                            sal_currency = str(c)

            return TrendingRole(
                title=role,
                posting_count=posting_count,
                growth_percent=None,
                top_skills=top_skills,
                median_salary=median_salary,
                currency=sal_currency,
                country=country,
                sources=[JobSource.GLASSDOOR],
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

    async def _get_detail(
        self,
        job_id: str,
        *,
        country: str = "CH",
        correlation_id: str = "",
    ) -> JobPosting | None:
        return None


def _parse_glassdoor_item(item: dict[str, Any], country: str, currency: str) -> JobPosting | None:
    title = _fix_encoding(str(item.get("job_title") or item.get("title") or "").strip())
    if not title:
        return None

    job_id = str(item.get("job_id") or item.get("id") or _make_id(title, item.get("company_name", "")))
    company = _fix_encoding(str(item.get("company_name") or item.get("company") or "Unknown"))
    location = _fix_encoding(str(item.get("location_name") or item.get("location") or ""))
    url = str(item.get("job_link") or item.get("url") or "")

    posted_date: date | None = None
    if age_days := item.get("age_in_days"):
        try:
            posted_date = date.today() - timedelta(days=int(age_days))
        except (TypeError, ValueError):
            pass
    elif date_str := item.get("date_posted") or item.get("posted_date"):
        try:
            posted_date = date.fromisoformat(str(date_str)[:10])
        except (ValueError, TypeError):
            pass

    salary_min: int | None = None
    salary_max: int | None = None
    sal_currency = currency
    if v := item.get("salary_min") or item.get("pay_period_min"):
        try:
            salary_min = int(float(v))
        except (TypeError, ValueError):
            pass
    if v := item.get("salary_max") or item.get("pay_period_max"):
        try:
            salary_max = int(float(v))
        except (TypeError, ValueError):
            pass
    if v := item.get("salary_median"):
        try:
            median = int(float(v))
            if salary_min is None:
                salary_min = median
            if salary_max is None:
                salary_max = median
        except (TypeError, ValueError):
            pass
    if c := item.get("salary_currency"):
        sal_currency = str(c)

    description = _fix_encoding(str(item.get("job_description") or item.get("description") or ""))[:2000]
    is_remote = (
        bool(item.get("is_remote"))
        or "remote" in title.lower()
        or "remote" in location.lower()
    )

    return JobPosting(
        id=job_id,
        title=title,
        company=company,
        location=location,
        country=country,
        remote=is_remote,
        employment_type=EmploymentType.UNKNOWN,
        experience_level=ExperienceLevel.UNKNOWN,
        description=description,
        required_skills=_extract_skills(description),
        salary_min=salary_min,
        salary_max=salary_max,
        currency=sal_currency,
        source=JobSource.GLASSDOOR,
        source_url=url,
        apply_url=item.get("apply_url") or url,
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


def _make_id(title: str, company: str) -> str:
    return hashlib.sha256(f"{title}:{company}".encode()).hexdigest()[:16]
