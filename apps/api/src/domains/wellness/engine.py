"""Wellness & Sustainability Monitor — pure scoring engine.

``assess`` is a pure function of recent check-ins, so the burnout estimate is
deterministic and unit-testable. Each driver contributes a bounded amount to a
0-100 risk score; the breakdown is returned so the UI can show *why* the risk is
what it is rather than presenting an opaque number.

Conventions for the 1-5 self-report scales:
  energy / motivation — higher is better (low values raise risk)
  stress              — higher is worse (high values raise risk)
Plus hours_worked (per week) and sleep_hours (per night).
"""
from __future__ import annotations

from dataclasses import dataclass, field

RECENT_WINDOW = 4  # number of most-recent check-ins the assessment considers


@dataclass
class CheckinSignal:
    energy: int = 3          # 1-5, higher better
    stress: int = 3          # 1-5, higher worse
    motivation: int = 3      # 1-5, higher better
    hours_worked: float = 40.0
    sleep_hours: float = 7.0


@dataclass
class WellnessAssessment:
    risk_score: int             # 0-100
    risk_level: str             # "low" | "moderate" | "high"
    trend: str                  # "improving" | "steady" | "worsening" | "insufficient"
    drivers: list[str] = field(default_factory=list)
    recommendation: str = ""
    recovery_suggested: bool = False
    sample_size: int = 0


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def assess(checkins: list[CheckinSignal]) -> WellnessAssessment:
    """Most-recent check-ins → burnout-risk assessment. Newest first expected."""
    if not checkins:
        return WellnessAssessment(
            risk_score=0,
            risk_level="low",
            trend="insufficient",
            recommendation="Log a wellness check-in to start tracking your pace.",
            sample_size=0,
        )

    recent = checkins[:RECENT_WINDOW]
    energy = _avg([c.energy for c in recent])
    stress = _avg([c.stress for c in recent])
    motivation = _avg([c.motivation for c in recent])
    hours = _avg([c.hours_worked for c in recent])
    sleep = _avg([c.sleep_hours for c in recent])

    score = 0.0
    drivers: list[str] = []

    # Energy: scales 1(=+25) .. 5(=0)
    energy_risk = max(0.0, (3.0 - energy)) / 2.0 * 25.0
    if energy <= 2.5:
        drivers.append("Low energy")
    score += energy_risk

    # Stress: scales 5(=+25) .. 1(=0)
    stress_risk = max(0.0, (stress - 3.0)) / 2.0 * 25.0
    if stress >= 3.5:
        drivers.append("High stress")
    score += stress_risk

    # Motivation
    motivation_risk = max(0.0, (3.0 - motivation)) / 2.0 * 20.0
    if motivation <= 2.5:
        drivers.append("Fading motivation")
    score += motivation_risk

    # Overwork: 40h baseline, 60h+ saturates.
    hours_risk = min(1.0, max(0.0, (hours - 45.0) / 15.0)) * 20.0
    if hours >= 55:
        drivers.append("Sustained long hours")
    score += hours_risk

    # Sleep debt: 7h baseline, 5h saturates.
    sleep_risk = min(1.0, max(0.0, (7.0 - sleep) / 2.0)) * 10.0
    if sleep <= 6:
        drivers.append("Short sleep")
    score += sleep_risk

    risk_score = round(min(100.0, score))
    risk_level = "high" if risk_score >= 60 else "moderate" if risk_score >= 35 else "low"
    trend = _trend(checkins)
    recovery = risk_level == "high" or (risk_level == "moderate" and trend == "worsening")

    return WellnessAssessment(
        risk_score=risk_score,
        risk_level=risk_level,
        trend=trend,
        drivers=drivers,
        recommendation=_recommend(risk_level, trend, drivers),
        recovery_suggested=recovery,
        sample_size=len(recent),
    )


def _trend(checkins: list[CheckinSignal]) -> str:
    if len(checkins) < 2:
        return "insufficient"
    latest = checkins[0]
    prev = checkins[1]
    # A simple wellbeing index: energy + motivation - stress.
    latest_idx = latest.energy + latest.motivation - latest.stress
    prev_idx = prev.energy + prev.motivation - prev.stress
    if latest_idx > prev_idx + 0.5:
        return "improving"
    if latest_idx < prev_idx - 0.5:
        return "worsening"
    return "steady"


def _recommend(risk_level: str, trend: str, drivers: list[str]) -> str:
    if risk_level == "high":
        return (
            "Your burnout risk is high. Schedule a recovery week — pause net-new "
            "goals, protect sleep, and keep only the lightest habits. Sustainable "
            "pace beats a stall."
        )
    if risk_level == "moderate":
        focus = drivers[0].lower() if drivers else "your pace"
        return (
            f"Risk is building, driven mostly by {focus}. Trim one commitment this "
            "week and recheck in a few days before it compounds."
        )
    if trend == "improving":
        return "You're in a sustainable zone and trending up — keep the current rhythm."
    return "Pace looks sustainable. Keep logging so a downturn is caught early."
