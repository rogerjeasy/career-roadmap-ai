"""Autopilot — pure proposal engine.

``build_proposals`` is a pure function of an ``AutopilotSignals`` snapshot, so it
is trivially testable without Firestore or the session store. Each proposal has
a stable ``signature`` used to dedupe against already-open proposals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# How stale a weekly review can get before we nudge (days).
REVIEW_STALE_DAYS = 10


@dataclass
class AutopilotSignals:
    has_roadmap: bool = False
    days_since_review: int | None = None  # None → never reviewed
    low_habits: list[str] = field(default_factory=list)  # habit names slipping this week
    missing_trending_skills: list[str] = field(default_factory=list)


@dataclass
class ProposalCandidate:
    kind: str
    title: str
    detail: str
    severity: str  # "info" | "warn"
    action_label: str
    action_route: str
    signature: str


def build_proposals(signals: AutopilotSignals) -> list[ProposalCandidate]:
    """Translate signals into a deterministic list of proposals."""
    out: list[ProposalCandidate] = []

    # 1. No roadmap yet — the highest-leverage nudge.
    if not signals.has_roadmap:
        out.append(
            ProposalCandidate(
                kind="kickstart",
                title="Generate your first roadmap",
                detail="You don't have an active roadmap yet. Generating one unlocks "
                "tracking, market matching, and tailored guidance.",
                severity="info",
                action_label="Start onboarding",
                action_route="/onboarding",
                signature="kickstart",
            )
        )
        # Without a roadmap the remaining plan-adjustment nudges don't apply.
        return out

    # 2. Stale (or missing) weekly review.
    if signals.days_since_review is None:
        out.append(
            ProposalCandidate(
                kind="review_stale",
                title="Log your first weekly review",
                detail="A weekly review is the platform's heartbeat — it lets Autopilot "
                "reason about your momentum. You haven't logged one yet.",
                severity="warn",
                action_label="Log a review",
                action_route="/progress/review",
                signature="review_stale",
            )
        )
    elif signals.days_since_review >= REVIEW_STALE_DAYS:
        out.append(
            ProposalCandidate(
                kind="review_stale",
                title="Time for a weekly review",
                detail=f"It's been {signals.days_since_review} days since your last review. "
                "A quick retrospective keeps your plan honest.",
                severity="warn",
                action_label="Log a review",
                action_route="/progress/review",
                signature="review_stale",
            )
        )

    # 3. Slipping habits.
    if signals.low_habits:
        names = ", ".join(signals.low_habits[:3])
        out.append(
            ProposalCandidate(
                kind="habit_drift",
                title="Some habits are slipping",
                detail=f"{names} {'is' if len(signals.low_habits) == 1 else 'are'} barely "
                "logged this week. Consider reducing scope or rescheduling rather than dropping them.",
                severity="warn",
                action_label="Review habits",
                action_route="/schedule/habits",
                signature="habit_drift:" + "|".join(sorted(signals.low_habits[:3])),
            )
        )

    # 4. Market drift — trending skills you don't have yet.
    if signals.missing_trending_skills:
        skills = ", ".join(signals.missing_trending_skills[:3])
        out.append(
            ProposalCandidate(
                kind="market_drift",
                title="New in-demand skills for your field",
                detail=f"{skills} {'is' if len(signals.missing_trending_skills) == 1 else 'are'} "
                "trending for your target role but not yet in your profile. Consider adding "
                "a phase or milestone to pick them up.",
                severity="info",
                action_label="Open your roadmap",
                action_route="/roadmap",
                signature="market_drift:" + "|".join(sorted(signals.missing_trending_skills[:3])),
            )
        )

    return out
