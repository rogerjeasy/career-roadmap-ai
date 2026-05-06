"""Progress & Adaptation domain models — pure data, no I/O, no LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class DriftSeverity(str, Enum):
    ON_TRACK = "on_track"   # drift_score < 0.20
    MINOR = "minor"         # 0.20 <= drift_score < 0.40
    MODERATE = "moderate"   # 0.40 <= drift_score < 0.65
    SEVERE = "severe"       # drift_score >= 0.65


class AdaptationType(str, Enum):
    PACE_ADJUSTMENT = "pace_adjustment"
    MILESTONE_REORDER = "milestone_reorder"
    SCOPE_REDUCTION = "scope_reduction"
    RESOURCE_SWAP = "resource_swap"
    HABIT_RESET = "habit_reset"
    FULL_REGENERATION = "full_regeneration"


@dataclass(frozen=True)
class WeeklyScorecard:
    """User's weekly self-report or auto-collected progress data."""

    week_start_date: date
    milestones_planned: list[str] = field(default_factory=list)
    milestones_completed: list[str] = field(default_factory=list)
    habit_completions: dict[str, bool] = field(default_factory=dict)
    hours_spent: float = 0.0
    planned_hours: float = 0.0
    notes: str = ""
    blockers: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HabitStreak:
    """Streak and completion-rate data for a single habit."""

    habit_name: str
    current_streak_weeks: int
    longest_streak_weeks: int
    completion_rate: float       # 0-1 across all tracked weeks
    total_weeks_tracked: int
    weeks_completed: int


@dataclass(frozen=True)
class DriftAnalysis:
    """Output of the drift detection step."""

    drift_score: float                    # 0-1: 0 = on-track, 1 = fully drifted
    drift_severity: DriftSeverity
    milestone_completion_rate: float      # fraction of planned milestones completed
    hours_variance: float                 # actual_hours - planned_hours (negative = under)
    stalled_milestones: list[str] = field(default_factory=list)
    at_risk_milestones: list[str] = field(default_factory=list)
    weeks_analysed: int = 0
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class AdaptationChange:
    """A single proposed change within an adaptation."""

    change_type: str        # pace | remove | swap | defer | reset
    target: str             # milestone / habit / resource name
    description: str
    rationale: str
    priority: int = 1       # 1 = highest


@dataclass(frozen=True)
class AdaptationProposal:
    """A single plan adaptation proposal."""

    adaptation_type: AdaptationType
    trigger_reason: str
    changes: list[AdaptationChange] = field(default_factory=list)
    confidence: float = 0.0
    requires_regeneration: bool = False
    summary: str = ""


@dataclass(frozen=True)
class ProgressAnalysisResult:
    """Full output of the ProgressAgent pipeline."""

    drift_analysis: DriftAnalysis
    habit_streaks: list[HabitStreak] = field(default_factory=list)
    adaptations: list[AdaptationProposal] = field(default_factory=list)
    requires_regeneration: bool = False
    analysis_summary: str = ""
