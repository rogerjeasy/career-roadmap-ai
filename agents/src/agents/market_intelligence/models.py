"""Market Intelligence domain models — pure data, no I/O, no LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum


class TrendDirection(str, Enum):
    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"


class SignalType(str, Enum):
    JOB_POSTING = "job_posting"
    GITHUB_TREND = "github_trend"
    SOCIAL_SIGNAL = "social_signal"
    SALARY_DATA = "salary_data"
    INDUSTRY_NEWS = "industry_news"


@dataclass(frozen=True)
class JobPosting:
    """A single job posting retrieved from a job board MCP server."""

    title: str
    company: str
    location: str
    required_skills: list[str]
    source: str
    posted_date: date | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str = "USD"
    url: str | None = None


@dataclass(frozen=True)
class SalaryBenchmark:
    """Salary benchmark for a role in a specific country."""

    role: str
    country: str
    median_annual: int | None
    p25_annual: int | None
    p75_annual: int | None
    currency: str
    source: str
    freshness_date: date | None = None


@dataclass(frozen=True)
class TrendingSkill:
    """A skill trending in the market based on aggregated MCP signals."""

    name: str
    category: str  # language | framework | platform | tool | ai_ml | tech | soft
    trend_direction: TrendDirection
    signal_count: int
    sources: list[str]
    evidence: str


@dataclass(frozen=True)
class IndustrySignal:
    """An individual industry signal (GitHub trend, social topic, news item)."""

    topic: str
    signal_type: SignalType
    summary: str
    source: str
    relevance_score: float  # 0-1: how relevant to the target role
    url: str | None = None
    freshness_date: date | None = None


@dataclass(frozen=True)
class MarketIntelligenceResult:
    """Full market intelligence output produced by the pipeline."""

    role: str
    country: str
    job_postings: list[JobPosting] = field(default_factory=list)
    salary_benchmark: SalaryBenchmark | None = None
    trending_skills: list[TrendingSkill] = field(default_factory=list)
    industry_signals: list[IndustrySignal] = field(default_factory=list)
    market_summary: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    data_sources: list[str] = field(default_factory=list)
    processing_steps: list[str] = field(default_factory=list)
