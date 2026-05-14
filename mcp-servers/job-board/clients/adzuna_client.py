"""Adzuna job board client — official aggregated listings API.

Uses the Adzuna public JSON API (https://developer.adzuna.com).
Supports job search and real trend analysis across 20+ countries including
Switzerland, Germany, UK, US, and more.

The ``count`` field in every Adzuna response is the true total number of
matching listings (not a page-size cap), making it ideal for week-over-week
growth computation without synthetic substitutes.
"""
from __future__ import annotations

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

_COUNTRY_TO_ADZUNA: dict[str, str] = {
    "AT": "at", "AU": "au", "BE": "be", "BR": "br",
    "CA": "ca", "CH": "ch", "DE": "de", "ES": "es",
    "FR": "fr", "GB": "gb", "IN": "in", "IT": "it",
    "MX": "mx", "NL": "nl", "NZ": "nz", "PL": "pl",
    "RU": "ru", "SG": "sg", "US": "us", "ZA": "za",
}
_DEFAULT_ADZUNA_COUNTRY = "gb"

_CURRENCY_BY_ADZUNA_CODE: dict[str, str] = {
    "at": "EUR", "au": "AUD", "be": "EUR", "br": "BRL",
    "ca": "CAD", "ch": "CHF", "de": "EUR", "es": "EUR",
    "fr": "EUR", "gb": "GBP", "in": "INR", "it": "EUR",
    "mx": "MXN", "nl": "EUR", "nz": "NZD", "pl": "PLN",
    "ru": "RUB", "sg": "SGD", "us": "USD", "za": "ZAR",
}

_CONTRACT_TIME_MAP: dict[str, EmploymentType] = {
    "full_time": EmploymentType.FULL_TIME,
    "part_time": EmploymentType.PART_TIME,
    "contract": EmploymentType.CONTRACT,
    "permanent": EmploymentType.FULL_TIME,
}

_TRENDING_ROLES = [
    "Software Engineer", "Data Engineer", "Machine Learning Engineer",
    "DevOps Engineer", "Platform Engineer", "AI Engineer",
    "Backend Developer", "Cloud Architect", "Data Scientist",
    "Security Engineer", "Frontend Developer", "Site Reliability Engineer",
    "MLOps Engineer", "Product Manager", "Full Stack Developer",
]

_TECH_SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Kotlin", "Rust",
    "C#", ".NET", "C++", "Ruby", "PHP", "Swift", "Scala",
    "Docker", "Kubernetes", "Terraform", "Ansible", "Helm",
    "AWS", "Azure", "GCP", "Pulumi",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Kafka",
    "React", "Vue.js", "Angular", "Node.js", "FastAPI", "Django", "Spring",
    "PyTorch", "TensorFlow", "scikit-learn", "MLflow", "Airflow", "dbt",
    "Spark", "Flink", "Databricks", "Snowflake",
    "CI/CD", "GitHub Actions", "Jenkins", "GitLab", "ArgoCD",
    "Prometheus", "Grafana", "OpenTelemetry",
    "SQL", "GraphQL", "REST", "gRPC", "Microservices",
    "Agile", "Scrum", "SAP", "Linux", "LangChain", "LangGraph",
]


class AdzunaClient(BaseJobBoardClient):
    """Fetches job postings from the official Adzuna Jobs API."""

    source = JobSource.ADZUNA

    def __init__(
        self,
        app_id: str,
        app_key: str,
        base_url: str = "https://api.adzuna.com/v1/api/jobs",
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._app_id = app_id
        self._app_key = app_key
        self._base_url = base_url.rstrip("/")

    def _country_code(self, country: str) -> str:
        return _COUNTRY_TO_ADZUNA.get(country.upper(), _DEFAULT_ADZUNA_COUNTRY)

    def _auth_params(self) -> dict[str, str]:
        return {"app_id": self._app_id, "app_key": self._app_key}

    async def _search(
        self,
        params: SearchJobsParams,
        *,
        correlation_id: str = "",
    ) -> list[JobPosting]:
        country_code = self._country_code(params.country)

        query_params: dict[str, Any] = {
            **self._auth_params(),
            "what": params.role,
            "results_per_page": min(params.limit, 50),
            "sort_by": "relevance",
        }
        if params.location:
            query_params["where"] = params.location
        if params.remote:
            query_params["what_and"] = "remote"
        if params.salary_min:
            query_params["salary_min"] = params.salary_min
        if params.employment_type == EmploymentType.FULL_TIME:
            query_params["full_time"] = "1"
        elif params.employment_type == EmploymentType.PART_TIME:
            query_params["part_time"] = "1"
        elif params.employment_type == EmploymentType.CONTRACT:
            query_params["contract"] = "1"
        if params.skills:
            query_params["what_and"] = " ".join(params.skills[:3])

        resp = await self._get(f"{self._base_url}/{country_code}/search/1", params=query_params)
        data = resp.json()

        currency = _CURRENCY_BY_ADZUNA_CODE.get(country_code, "USD")
        postings: list[JobPosting] = []
        for item in data.get("results", []):
            posting = _parse_adzuna_item(item, params.country, currency)
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

        country_code = self._country_code(country)
        currency = _CURRENCY_BY_ADZUNA_CODE.get(country_code, "USD")
        # Probe more roles than requested so we can rank and trim
        candidate_roles = _TRENDING_ROLES[:max(limit * 2, 14)]

        async def _probe_role(role: str) -> TrendingRole | None:
            try:
                week_data, month_data = await asyncio.gather(
                    self._fetch_count(role, country_code, max_days_old=7),
                    self._fetch_count(role, country_code, max_days_old=30),
                )
            except Exception:
                return None

            week_count = week_data["count"]
            month_count = month_data["count"]
            if month_count == 0:
                return None

            # week_count / (month_count / 4.3) gives this week vs the monthly average
            monthly_avg = month_count / 4.3
            growth = round((week_count / monthly_avg - 1.0) * 100, 1) if monthly_avg > 0 else 0.0
            growth = max(-100.0, min(500.0, growth))

            # Extract skills from actual postings returned for the week query
            skill_freq: dict[str, int] = {}
            for item in week_data["results"]:
                desc = str(item.get("description") or "")
                for skill in _extract_skills(desc):
                    skill_freq[skill] = skill_freq.get(skill, 0) + 1
            top_skills = [s for s, _ in sorted(skill_freq.items(), key=lambda x: -x[1])[:5]]

            median_salary: int | None = None
            if raw_mean := week_data.get("mean"):
                try:
                    median_salary = int(float(raw_mean))
                except (TypeError, ValueError):
                    pass

            return TrendingRole(
                title=role,
                posting_count=month_count,
                growth_percent=growth,
                top_skills=top_skills,
                median_salary=median_salary,
                currency=currency,
                country=country,
                sources=[JobSource.ADZUNA],
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

        results.sort(key=lambda r: (-r.posting_count, -(r.growth_percent or 0.0)))
        return results[:limit]

    async def _fetch_count(
        self,
        role: str,
        country_code: str,
        max_days_old: int,
    ) -> dict[str, Any]:
        query_params: dict[str, Any] = {
            **self._auth_params(),
            "what": role,
            "results_per_page": 10,
            "max_days_old": max_days_old,
        }
        resp = await self._get(f"{self._base_url}/{country_code}/search/1", params=query_params)
        data = resp.json()
        return {
            "count": int(data.get("count", 0)),
            "results": data.get("results", []),
            "mean": data.get("mean"),
        }


def _fix_encoding(s: str) -> str:
    """Fix double-encoded UTF-8 strings (e.g. ZÃ¼rich → Zürich)."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def _parse_adzuna_item(item: dict[str, Any], country: str, currency: str) -> JobPosting | None:
    title = _fix_encoding(str(item.get("title") or "").strip())
    if not title:
        return None

    company = _fix_encoding(str((item.get("company") or {}).get("display_name") or "Unknown"))
    location = _fix_encoding(str((item.get("location") or {}).get("display_name") or ""))
    job_id = str(item.get("id") or _make_id(title, company))

    posted_date: date | None = None
    if created_raw := item.get("created"):
        try:
            posted_date = datetime.fromisoformat(
                str(created_raw).replace("Z", "+00:00")
            ).date()
        except (ValueError, TypeError):
            pass

    contract_time = str(item.get("contract_time") or "").lower()
    emp_type = _CONTRACT_TIME_MAP.get(contract_time, EmploymentType.UNKNOWN)

    salary_min: int | None = None
    salary_max: int | None = None
    if v := item.get("salary_min"):
        try:
            salary_min = int(float(v))
        except (TypeError, ValueError):
            pass
    if v := item.get("salary_max"):
        try:
            salary_max = int(float(v))
        except (TypeError, ValueError):
            pass

    description = str(item.get("description") or "")[:2000]
    skills = _extract_skills(description)

    return JobPosting(
        id=job_id,
        title=title,
        company=company,
        location=location,
        country=country,
        remote="remote" in title.lower() or "remote" in location.lower(),
        employment_type=emp_type,
        experience_level=ExperienceLevel.UNKNOWN,
        description=description,
        required_skills=skills,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        source=JobSource.ADZUNA,
        source_url=item.get("redirect_url"),
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
