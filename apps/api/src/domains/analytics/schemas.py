"""Analytics domain — Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ApplicationsFunnel(BaseModel):
    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    active: int = 0
    offers: int = 0
    interview_rate: float = 0.0   # interviewing+/applied+
    offer_rate: float = 0.0       # offers/applied+


class LearningSummary(BaseModel):
    items: int = 0
    total_cost: float = 0.0
    total_hours: float = 0.0
    avg_roi: int = 0


class WellnessSummary(BaseModel):
    checkins: int = 0
    latest_risk: int | None = None
    latest_level: str | None = None


class AssetCounts(BaseModel):
    evidence: int = 0
    portfolio: int = 0
    credentials: int = 0
    story_drafts: int = 0
    oss_bookmarks: int = 0


class MomentumSummary(BaseModel):
    weekly_reviews: int = 0
    days_since_review: int | None = None
    habits_tracked: int = 0
    interview_practices: int = 0


class AnalyticsOverview(BaseModel):
    applications: ApplicationsFunnel
    learning: LearningSummary
    wellness: WellnessSummary
    assets: AssetCounts
    momentum: MomentumSummary
