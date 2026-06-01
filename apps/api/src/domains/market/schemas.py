"""Market domain — response schemas for cached market intelligence."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

MarketSentiment = Literal["positive", "neutral", "negative"]


class MarketSignalOut(BaseModel):
    id: str
    title: str
    summary: str
    source: str
    sentiment: MarketSentiment
    tag: str
    time_label: str


class SalaryBenchmarkOut(BaseModel):
    role: str
    location: str
    currency: str
    p25: int
    p50: int
    p75: int


class TrendingSkillOut(BaseModel):
    name: str
    demand_index: int  # 0–100 relative demand
    delta_pct: int


class MarketOverviewOut(BaseModel):
    """Aggregated market intelligence for the user's target role.

    Populated from the most recent market-intelligence agent run cached in the
    session plan context. ``has_data`` is False until a roadmap or market run
    has produced data — clients show an illustrative/empty state in that case.
    """

    summary: str
    signals: list[MarketSignalOut]
    salary_benchmark: SalaryBenchmarkOut | None
    trending_skills: list[TrendingSkillOut]
    has_data: bool
