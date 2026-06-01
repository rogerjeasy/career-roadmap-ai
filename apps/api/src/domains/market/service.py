"""Market domain — service layer.

Market intelligence is produced by the market-intelligence agent and cached in
the session plan context (``plan_context.snapshot``). This service reads that
snapshot and shapes it for the client — it does not own a Firestore collection.
The same read-from-session approach is used by the opportunity alerts endpoint.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends

from src.core.logging import get_logger
from src.domains.market.schemas import (
    MarketOverviewOut,
    MarketSignalOut,
    SalaryBenchmarkOut,
    TrendingSkillOut,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)


def _sentiment_for(relevance: float) -> str:
    if relevance >= 0.66:
        return "positive"
    if relevance >= 0.33:
        return "neutral"
    return "negative"


def _delta_for(direction: str, signal_count: int) -> int:
    d = (direction or "").lower()
    magnitude = min(signal_count * 3, 60)
    if any(k in d for k in ("ris", "up", "grow", "increas")):
        return magnitude
    if any(k in d for k in ("fall", "declin", "down", "decreas")):
        return -magnitude
    return 0


def _shape_signals(raw: list[dict[str, Any]]) -> list[MarketSignalOut]:
    out: list[MarketSignalOut] = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            continue
        relevance = float(s.get("relevance_score", 0.5) or 0.5)
        out.append(
            MarketSignalOut(
                id=str(s.get("id") or s.get("topic") or f"signal-{i}"),
                title=str(s.get("topic", "")),
                summary=str(s.get("summary", "")),
                source=str(s.get("source", "")),
                sentiment=_sentiment_for(relevance),  # type: ignore[arg-type]
                tag=str(s.get("signal_type", "trend")),
                time_label=str(s.get("freshness_date") or ""),
            )
        )
    return out


def _shape_salary(raw: dict[str, Any] | None) -> SalaryBenchmarkOut | None:
    if not isinstance(raw, dict):
        return None
    median = raw.get("median_annual")
    p25 = raw.get("p25_annual")
    p75 = raw.get("p75_annual")
    if median is None and p25 is None and p75 is None:
        return None
    base = int(median or p25 or p75 or 0)
    return SalaryBenchmarkOut(
        role=str(raw.get("role", "")),
        location=str(raw.get("country", "")),
        currency=str(raw.get("currency", "")),
        p25=int(p25 if p25 is not None else base),
        p50=int(median if median is not None else base),
        p75=int(p75 if p75 is not None else base),
    )


def _shape_skills(raw: list[dict[str, Any]]) -> list[TrendingSkillOut]:
    counts = [int(s.get("signal_count", 0)) for s in raw if isinstance(s, dict)]
    max_count = max(counts, default=1) or 1
    out: list[TrendingSkillOut] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        count = int(s.get("signal_count", 0))
        out.append(
            TrendingSkillOut(
                name=str(s.get("name", "")),
                demand_index=int(min(100, round((count / max_count) * 100))),
                delta_pct=_delta_for(str(s.get("trend_direction", "")), count),
            )
        )
    return out


class MarketService:
    def __init__(self, sessions: SessionManager) -> None:
        self._sessions = sessions

    async def get_overview(self, user_id: str) -> MarketOverviewOut:
        session = await self._sessions.get(user_id)
        snapshot: dict[str, Any] = {}
        if session and session.plan_context:
            snapshot = session.plan_context.snapshot or {}

        agent_outputs = snapshot.get("agent_outputs", {}) if isinstance(snapshot, dict) else {}
        market: dict[str, Any] = (
            snapshot.get("market")
            or snapshot.get("market_intelligence")
            or agent_outputs.get("market")
            or agent_outputs.get("market_intelligence")
            or {}
        )

        signals = _shape_signals(market.get("industry_signals", []))
        salary = _shape_salary(market.get("salary_benchmark"))
        skills = _shape_skills(market.get("trending_skills", []))
        summary = str(market.get("market_summary", ""))

        return MarketOverviewOut(
            summary=summary,
            signals=signals,
            salary_benchmark=salary,
            trending_skills=skills,
            has_data=bool(signals or salary or skills or summary),
        )


async def get_market_service(
    sessions: SessionManager = Depends(get_session_manager),
) -> MarketService:
    return MarketService(sessions)
