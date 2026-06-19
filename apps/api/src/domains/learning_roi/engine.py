"""Learning ROI Tracker — pure scoring engine.

``score_items`` is a pure function of the logged items plus a signals snapshot,
so the ranking is deterministic and unit-testable without Firestore or the LLM.

The model, in words:
  • relevance — how much an item's skills overlap with what the user's target
    market actually rewards (trending + gap skills). This is the dominant driver.
  • impact   — expected career impact (0-100): relevance, nudged by the item
    type's signalling value (a certification signals more than a blog post).
  • effort   — a normalised blend of money cost and time cost.
  • roi      — impact per unit effort; this is what we rank by.

When no market signals are available yet (no roadmap), relevance falls back to a
neutral prior so the tracker still ranks by effort and type rather than emitting
fabricated alignment.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Signalling weight by item type — certifications/degrees carry external proof,
# so they get a small impact premium over self-directed formats at equal relevance.
_TYPE_SIGNAL: dict[str, float] = {
    "certification": 1.15,
    "degree": 1.15,
    "course": 1.0,
    "bootcamp": 1.05,
    "book": 0.9,
    "article": 0.8,
    "other": 0.85,
}

_NEUTRAL_RELEVANCE = 0.5  # used when no market signals exist yet


@dataclass
class RoiSignals:
    """Real per-user signals the engine ranks against."""

    demand_skills: list[str] = field(default_factory=list)  # trending + gap, lowercased
    target_role: str | None = None


@dataclass
class ScoredItem:
    impact_score: int          # 0-100 expected career impact
    relevance: float           # 0..1 market alignment
    roi_score: int             # 0-100 impact-per-effort, the ranking key
    matched_skills: list[str]  # which of the item's skills the market rewards
    rationale: str


def _effort_index(cost: float, hours: float) -> float:
    """Normalised effort: 1.0 ≈ a cheap, short item; grows with money and time.

    Floored at 0.5 so trivially cheap items don't produce explosive ROI.
    """
    money_units = max(0.0, cost) / 200.0   # every $200 ≈ one unit of effort
    time_units = max(0.0, hours) / 20.0    # every 20h ≈ one unit of effort
    return max(0.5, 1.0 + money_units + time_units)


def score_item(
    *,
    skills: list[str],
    cost: float,
    hours: float,
    item_type: str,
    signals: RoiSignals,
) -> ScoredItem:
    demand = {s.strip().lower() for s in signals.demand_skills if s.strip()}
    item_skills = [s.strip() for s in skills if s.strip()]

    matched: list[str] = []
    if demand and item_skills:
        matched = [s for s in item_skills if s.lower() in demand]
        relevance = len(matched) / len(item_skills)
    elif not demand:
        relevance = _NEUTRAL_RELEVANCE
    else:
        relevance = 0.0  # we know the market but the item declares no skills

    signal = _TYPE_SIGNAL.get(item_type, _TYPE_SIGNAL["other"])
    impact = max(0.0, min(100.0, relevance * 100.0 * signal))

    effort = _effort_index(cost, hours)
    # ROI: impact per unit effort, rescaled so a perfectly-aligned cheap item ≈ 100.
    roi = max(0.0, min(100.0, impact / effort))

    rationale = _build_rationale(
        relevance=relevance,
        matched=matched,
        has_demand=bool(demand),
        cost=cost,
        hours=hours,
        target_role=signals.target_role,
    )

    return ScoredItem(
        impact_score=round(impact),
        relevance=round(relevance, 2),
        roi_score=round(roi),
        matched_skills=matched,
        rationale=rationale,
    )


def _build_rationale(
    *,
    relevance: float,
    matched: list[str],
    has_demand: bool,
    cost: float,
    hours: float,
    target_role: str | None,
) -> str:
    role = f"your move toward {target_role}" if target_role else "your goals"
    if not has_demand:
        return (
            "No market snapshot yet, so this is ranked on effort and format only. "
            "Generate a roadmap to unlock market-aligned impact scoring."
        )
    if matched:
        skills_txt = ", ".join(matched[:4])
        strength = "strongly" if relevance >= 0.6 else "partially"
        effort_note = (
            " It's also a light investment, which lifts its ROI."
            if cost <= 50 and hours <= 10
            else ""
        )
        return (
            f"{skills_txt} {'is' if len(matched) == 1 else 'are'} in demand for {role}, "
            f"so this {strength} aligns with what the market rewards.{effort_note}"
        )
    return (
        f"None of this item's skills currently show up as in-demand for {role}. "
        "Consider whether it's a foundational prerequisite or a lower-priority interest."
    )
