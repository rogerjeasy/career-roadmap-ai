"""levels.fyi salary data client.

Uses levels.fyi's internal CDN endpoint to fetch crowd-sourced compensation
data for tech roles. No official API key is required. Respects rate limits via
caching (TTL 1h at the tool level) and conservative request patterns.

Endpoint (unofficial, used by levels.fyi web app):
  GET https://www.levels.fyi/js/salaryData.json  (bulk dataset, ~5MB)

For targeted queries we use:
  GET https://www.levels.fyi/api/v2/jobs?standardJobTitle=<title>&country=<code>
"""
from __future__ import annotations

import re
from typing import Any

import structlog

from clients.base_client import BaseSalaryClient
from models import ExperienceLevel, GetSalaryRangeParams, SalaryDataPoint, SalarySource

logger = structlog.get_logger(__name__)

_LEVEL_NORM: dict[str, ExperienceLevel] = {
    "entry": ExperienceLevel.ENTRY,
    "junior": ExperienceLevel.ENTRY,
    "mid": ExperienceLevel.MID,
    "senior": ExperienceLevel.SENIOR,
    "staff": ExperienceLevel.LEAD,
    "lead": ExperienceLevel.LEAD,
    "principal": ExperienceLevel.PRINCIPAL,
    "distinguished": ExperienceLevel.PRINCIPAL,
}

_COUNTRY_CODE: dict[str, str] = {
    "CH": "Switzerland",
    "DE": "Germany",
    "GB": "United Kingdom",
    "US": "United States",
    "NL": "Netherlands",
    "FR": "France",
    "SE": "Sweden",
    "AT": "Austria",
}


class LevelsFyiClient(BaseSalaryClient):
    """Fetches crowd-sourced compensation data from levels.fyi."""

    source = SalarySource.LEVELS_FYI

    def __init__(
        self,
        base_url: str = "https://www.levels.fyi",
        *,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._base_url = base_url.rstrip("/")

    def _default_headers(self) -> dict[str, str]:
        return {
            **super()._default_headers(),
            "Referer": "https://www.levels.fyi/",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _fetch(self, params: GetSalaryRangeParams) -> list[SalaryDataPoint]:
        country_name = _COUNTRY_CODE.get(params.country, params.country)
        role_slug = _normalise_role(params.role)

        try:
            resp = await self._get(
                f"{self._base_url}/api/v2/jobs",
                params={
                    "standardJobTitle": role_slug,
                    "country": country_name,
                    "limit": 50,
                },
            )
            data = resp.json()
        except Exception as exc:
            logger.warning("levels_fyi.fetch_failed", error=str(exc))
            return []

        return _parse_levels_fyi(data, params)


def _parse_levels_fyi(
    data: Any,
    params: GetSalaryRangeParams,
) -> list[SalaryDataPoint]:
    points: list[SalaryDataPoint] = []

    rows = data if isinstance(data, list) else data.get("data", [])
    for row in rows:
        if not isinstance(row, dict):
            continue

        base_raw = row.get("basesalary") or row.get("base") or row.get("salary")
        if not base_raw:
            continue

        try:
            base_salary = int(float(str(base_raw).replace(",", "")))
        except (ValueError, TypeError):
            continue

        if base_salary < 20_000 or base_salary > 5_000_000:
            continue

        total_raw = row.get("totalcompensation") or row.get("totalComp") or row.get("total")
        total_comp = None
        if total_raw:
            try:
                total_comp = int(float(str(total_raw).replace(",", "")))
            except (ValueError, TypeError):
                pass

        currency = str(row.get("currency") or params.currency)
        level_raw = str(row.get("level") or row.get("yearsofexperience") or "").lower()
        level = _infer_level(level_raw, params.experience_level)
        location = str(row.get("location") or row.get("cityid") or params.country)
        company = str(row.get("company") or row.get("companyid") or "")

        points.append(
            SalaryDataPoint(
                source=SalarySource.LEVELS_FYI,
                role=str(row.get("title") or params.role),
                location=location,
                country=params.country,
                experience_level=level,
                base_salary=base_salary,
                total_compensation=total_comp,
                currency=currency,
                company=company if company else None,
            )
        )

    return points


def _infer_level(raw: str, default: ExperienceLevel) -> ExperienceLevel:
    for key, level in _LEVEL_NORM.items():
        if key in raw:
            return level
    # Numeric years of experience heuristic
    match = re.search(r"(\d+)", raw)
    if match:
        yoe = int(match.group(1))
        if yoe <= 2:
            return ExperienceLevel.ENTRY
        elif yoe <= 5:
            return ExperienceLevel.MID
        elif yoe <= 10:
            return ExperienceLevel.SENIOR
        else:
            return ExperienceLevel.LEAD
    return default


def _normalise_role(role: str) -> str:
    """Map free-text roles to levels.fyi standard job titles."""
    role_lower = role.lower()
    if "machine learning" in role_lower or "ml engineer" in role_lower:
        return "Machine Learning Engineer"
    if "ai engineer" in role_lower or "artificial intelligence" in role_lower:
        return "Machine Learning Engineer"
    if "data scientist" in role_lower:
        return "Data Scientist"
    if "data engineer" in role_lower:
        return "Data Engineer"
    if "full stack" in role_lower or "fullstack" in role_lower:
        return "Software Engineer"
    if "backend" in role_lower or "back-end" in role_lower:
        return "Software Engineer"
    if "frontend" in role_lower or "front-end" in role_lower:
        return "Software Engineer"
    if "devops" in role_lower or "platform engineer" in role_lower:
        return "DevOps Engineer"
    if "product manager" in role_lower:
        return "Product Manager"
    return role.title()
