"""Unit tests for the pure autopilot proposal engine."""
from __future__ import annotations

from src.domains.autopilot.engine import (
    REVIEW_STALE_DAYS,
    AutopilotSignals,
    build_proposals,
)


def _kinds(signals: AutopilotSignals) -> list[str]:
    return [p.kind for p in build_proposals(signals)]


def test_no_roadmap_yields_only_kickstart() -> None:
    proposals = build_proposals(AutopilotSignals(has_roadmap=False, days_since_review=None))
    assert [p.kind for p in proposals] == ["kickstart"]
    assert proposals[0].action_route == "/onboarding"


def test_never_reviewed_with_roadmap_nudges_review() -> None:
    kinds = _kinds(AutopilotSignals(has_roadmap=True, days_since_review=None))
    assert "review_stale" in kinds


def test_fresh_review_no_review_nudge() -> None:
    kinds = _kinds(AutopilotSignals(has_roadmap=True, days_since_review=2))
    assert "review_stale" not in kinds


def test_stale_review_triggers_nudge() -> None:
    kinds = _kinds(
        AutopilotSignals(has_roadmap=True, days_since_review=REVIEW_STALE_DAYS + 1)
    )
    assert "review_stale" in kinds


def test_low_habits_and_market_drift() -> None:
    proposals = build_proposals(
        AutopilotSignals(
            has_roadmap=True,
            days_since_review=1,
            low_habits=["Morning study"],
            missing_trending_skills=["RAG", "MLOps"],
        )
    )
    kinds = [p.kind for p in proposals]
    assert "habit_drift" in kinds
    assert "market_drift" in kinds
    # Signatures encode the specifics so they dedupe precisely.
    drift = next(p for p in proposals if p.kind == "market_drift")
    assert "MLOps" in drift.signature and "RAG" in drift.signature


def test_signatures_are_stable_for_same_inputs() -> None:
    s = AutopilotSignals(has_roadmap=True, days_since_review=1, low_habits=["b", "a"])
    sig1 = build_proposals(s)[0].signature
    sig2 = build_proposals(s)[0].signature
    assert sig1 == sig2
