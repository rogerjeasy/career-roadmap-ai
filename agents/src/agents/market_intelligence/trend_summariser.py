"""TrendSummariser — LLM-based market trend summarisation with structured fallback.

Stateless. Falls back to a deterministic text summary when the LLM fails,
so the pipeline never blocks on this step.
"""
from __future__ import annotations

import json
import time

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import (
    MARKET_SUMMARISE_DURATION,
    MARKET_SUMMARISE_TOTAL,
    get_tracer,
)
from agents.market_intelligence.models import IndustrySignal, SalaryBenchmark, TrendingSkill

logger = get_logger(__name__)
_tracer = get_tracer("agents.market_intelligence.trend_summariser")

_SYSTEM_PROMPT = """\
You are a market intelligence analyst for career planning. Given job market data for a role
in a specific country, produce a concise 2-3 paragraph market intelligence summary.

Cover:
1. Current demand context and salary range
2. Top trending skills and technologies to prioritise
3. Key industry signals and strategic opportunities

Return ONLY valid JSON (no code fences):
{"summary": "<2-3 paragraph market summary>"}

Guidelines:
- Be specific about salaries: include the currency symbol and numbers
- Highlight the top 3-5 trending skills by name
- Mention concrete industry signals (GitHub trends, community discussions)
- End with a freshness note such as "Data reflects market conditions as of today."
- Do not invent facts not present in the input data
"""


class TrendSummariser:
    """Summarises market intelligence data into a human-readable narrative.

    Inject a custom ``llm`` in tests to avoid real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.market_intelligence_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=1024,
            temperature=0.1,
        )

    async def summarise(
        self,
        role: str,
        country: str,
        trending_skills: list[TrendingSkill],
        salary_benchmark: SalaryBenchmark | None,
        industry_signals: list[IndustrySignal],
        job_posting_count: int,
        *,
        correlation_id: str = "",
    ) -> str:
        """Return a market narrative paragraph. Falls back to structured text if LLM fails."""
        with _tracer.start_as_current_span("market.summarise") as span:
            span.set_attribute("role", role)
            span.set_attribute("country", country)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            try:
                summary = await self._summarise_with_llm(
                    role,
                    country,
                    trending_skills,
                    salary_benchmark,
                    industry_signals,
                    job_posting_count,
                    correlation_id,
                )
                MARKET_SUMMARISE_TOTAL.labels(status="llm").inc()
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "market.summarise_llm_failed",
                    error=str(exc),
                    fallback="structured",
                    correlation_id=correlation_id,
                )
                summary = _fallback_summary(
                    role, country, trending_skills, salary_benchmark, job_posting_count
                )
                MARKET_SUMMARISE_TOTAL.labels(status="fallback").inc()

            MARKET_SUMMARISE_DURATION.observe(time.monotonic() - t0)
            logger.info(
                "market.summarised",
                role=role,
                country=country,
                summary_length=len(summary),
                correlation_id=correlation_id,
            )
            return summary

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _summarise_with_llm(
        self,
        role: str,
        country: str,
        trending_skills: list[TrendingSkill],
        salary_benchmark: SalaryBenchmark | None,
        industry_signals: list[IndustrySignal],
        job_posting_count: int,
        correlation_id: str,
    ) -> str:
        user_content = _build_user_prompt(
            role,
            country,
            trending_skills,
            salary_benchmark,
            industry_signals,
            job_posting_count,
        )
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict) or "summary" not in raw:
            raise ValueError("LLM response missing 'summary' key")
        return str(raw["summary"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_user_prompt(
    role: str,
    country: str,
    trending_skills: list[TrendingSkill],
    salary_benchmark: SalaryBenchmark | None,
    industry_signals: list[IndustrySignal],
    job_posting_count: int,
) -> str:
    lines = [
        f"Role: {role}",
        f"Country: {country}",
        f"Active job postings found: {job_posting_count}",
    ]
    if salary_benchmark and salary_benchmark.median_annual:
        lines.append(
            f"Salary benchmark: median {salary_benchmark.median_annual:,} "
            f"{salary_benchmark.currency}/yr "
            f"(p25: {salary_benchmark.p25_annual:,}, "
            f"p75: {salary_benchmark.p75_annual:,})"
        )
    else:
        lines.append("Salary benchmark: not available")

    if trending_skills:
        top = trending_skills[:8]
        skill_list = ", ".join(
            f"{s.name} ({s.signal_count} signals)" for s in top
        )
        lines.append(f"Top trending skills: {skill_list}")
    else:
        lines.append("Top trending skills: none identified")

    if industry_signals:
        top_signals = [s.summary for s in industry_signals[:5]]
        lines.append("Key industry signals:")
        lines.extend(f"  - {sig}" for sig in top_signals)

    return "\n".join(lines)


def _fallback_summary(
    role: str,
    country: str,
    trending_skills: list[TrendingSkill],
    salary_benchmark: SalaryBenchmark | None,
    job_posting_count: int,
) -> str:
    parts: list[str] = [
        f"Market intelligence for {role} in {country}: "
        f"{job_posting_count} active job postings found."
    ]
    if salary_benchmark and salary_benchmark.median_annual:
        parts.append(
            f"Median salary is {salary_benchmark.median_annual:,} "
            f"{salary_benchmark.currency}/yr "
            f"(range: {salary_benchmark.p25_annual:,}–"
            f"{salary_benchmark.p75_annual:,})."
        )
    if trending_skills:
        top = [s.name for s in trending_skills[:5]]
        parts.append(f"Top trending skills: {', '.join(top)}.")
    parts.append("Data freshness: real-time as of retrieval.")
    return " ".join(parts)
