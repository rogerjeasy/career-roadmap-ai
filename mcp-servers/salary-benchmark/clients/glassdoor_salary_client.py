"""Glassdoor salary data client via RapidAPI (real-time-glassdoor-data).

Uses the ``real-time-glassdoor-data`` endpoint on RapidAPI to fetch real
salary estimates by job title and location.

Endpoint: GET /salary-estimation
  Params: job_title, location, location_type, years_of_experience, domain
  Response: data.median_base_salary, data.min_base_salary, data.max_base_salary,
            data.salary_currency, data.salary_count

API docs: https://rapidapi.com/Lakzian/api/real-time-glassdoor-data
"""
from __future__ import annotations

from typing import Any

import structlog

from clients.base_client import BaseSalaryClient
from models import ExperienceLevel, GetSalaryRangeParams, SalaryDataPoint, SalarySource

logger = structlog.get_logger(__name__)

_COUNTRY_TO_LOCATION: dict[str, str] = {
    "CH": "Zurich, Switzerland",
    "DE": "Berlin, Germany",
    "AT": "Vienna, Austria",
    "FR": "Paris, France",
    "NL": "Amsterdam, Netherlands",
    "BE": "Brussels, Belgium",
    "ES": "Madrid, Spain",
    "IT": "Rome, Italy",
    "SE": "Stockholm, Sweden",
    "DK": "Copenhagen, Denmark",
    "NO": "Oslo, Norway",
    "PL": "Warsaw, Poland",
    "GB": "London, United Kingdom",
    "US": "New York, NY",
    "CA": "Toronto, Ontario",
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

_LEVEL_TO_YEARS: dict[ExperienceLevel, str] = {
    ExperienceLevel.ENTRY: "1",
    ExperienceLevel.MID: "3",
    ExperienceLevel.SENIOR: "5",
    ExperienceLevel.LEAD: "7",
    ExperienceLevel.PRINCIPAL: "10",
    ExperienceLevel.UNKNOWN: "ALL",
}


class GlassdoorSalaryClient(BaseSalaryClient):
    """Fetches salary estimates from Glassdoor via real-time-glassdoor-data on RapidAPI."""

    source = SalarySource.GLASSDOOR

    def __init__(
        self,
        api_key: str,
        api_host: str = "real-time-glassdoor-data.p.rapidapi.com",
        *,
        timeout_seconds: float = 20.0,
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

    async def _fetch(self, params: GetSalaryRangeParams) -> list[SalaryDataPoint]:
        location = _COUNTRY_TO_LOCATION.get(params.country.upper(), params.country)
        domain = _COUNTRY_TO_DOMAIN.get(params.country.upper(), _DEFAULT_DOMAIN)
        years = _LEVEL_TO_YEARS.get(params.experience_level, "ALL")

        query_params: dict[str, Any] = {
            "job_title": params.role,
            "location": location,
            "location_type": "ANY",
            "years_of_experience": years,
            "domain": domain,
        }

        try:
            resp = await self._get(
                f"https://{self._api_host}/salary-estimation",
                params=query_params,
            )
            data = resp.json()
        except Exception as exc:
            logger.warning("glassdoor_salary.fetch_failed", error=str(exc), role=params.role)
            return []

        return _parse_salary_response(data, params, location)


def _parse_salary_response(
    data: dict[str, Any],
    params: GetSalaryRangeParams,
    location: str,
) -> list[SalaryDataPoint]:
    if not isinstance(data, dict):
        return []

    inner = data.get("data") or {}
    if not isinstance(inner, dict):
        return []

    median_raw = inner.get("median_base_salary")
    min_raw = inner.get("min_base_salary")
    max_raw = inner.get("max_base_salary")
    currency = str(inner.get("salary_currency") or params.currency)

    points: list[SalaryDataPoint] = []

    def _to_int(v: Any) -> int | None:
        if v is None:
            return None
        try:
            val = int(float(str(v)))
            # Sanity check — reject implausible values
            return val if 10_000 < val < 5_000_000 else None
        except (TypeError, ValueError):
            return None

    median = _to_int(median_raw)
    minimum = _to_int(min_raw)
    maximum = _to_int(max_raw)

    # Emit three data points (min, median, max) so the aggregator can compute
    # accurate percentiles from the distribution rather than a single value.
    for salary in (minimum, median, maximum):
        if salary is not None:
            points.append(
                SalaryDataPoint(
                    source=SalarySource.GLASSDOOR,
                    role=params.role,
                    location=location,
                    country=params.country,
                    experience_level=params.experience_level,
                    base_salary=salary,
                    currency=currency,
                )
            )

    return points
