"""Tests for the Progress & Adaptation Agent.

Covers:
  - WeeklyScorecard parsing helpers (_parse_scorecards)
  - DriftDetector: empty input, full completion, partial drift, severe drift,
    hours-only variance, stalled/at-risk classification, _classify_severity
  - HabitStreakAnalyser: empty, single habit, multiple habits, broken streaks,
    _compute_streak edge cases
  - AdaptationProposer: LLM success, LLM failure fallback, _build_proposals,
    _heuristic_proposals coverage for each severity band
  - ProgressAgent: full pipeline, output shape, progress events, BaseAgent.run()
    contract, requires_regeneration flag propagation

All LLM calls are mocked — no network or Anthropic API required.
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.contracts.results import AgentResultStatus
from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.progress.adaptation_proposer import (
    AdaptationProposer,
    _build_proposals,
    _heuristic_proposals,
)
from agents.progress.drift_detector import DriftDetector, _classify_severity
from agents.progress.habit_streak_analyser import HabitStreakAnalyser, _compute_streak
from agents.progress.models import (
    AdaptationChange,
    AdaptationProposal,
    AdaptationType,
    DriftAnalysis,
    DriftSeverity,
    HabitStreak,
    WeeklyScorecard,
)
from agents.progress.progress_agent import (
    ProgressAgent,
    _build_summary,
    _parse_scorecards,
    _serialise_adaptation,
    _serialise_drift,
    _serialise_habit_streak,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def drift_detector() -> DriftDetector:
    return DriftDetector()


@pytest.fixture
def habit_analyser() -> HabitStreakAnalyser:
    return HabitStreakAnalyser()


@pytest.fixture
def adaptation_proposer(mock_llm: AsyncMock) -> AdaptationProposer:
    return AdaptationProposer(llm=mock_llm)


def _w(
    week: str,
    planned: list[str] | None = None,
    completed: list[str] | None = None,
    habits: dict[str, bool] | None = None,
    hours_spent: float = 5.0,
    planned_hours: float = 6.0,
    blockers: list[str] | None = None,
) -> WeeklyScorecard:
    return WeeklyScorecard(
        week_start_date=date.fromisoformat(week),
        milestones_planned=planned or [],
        milestones_completed=completed or [],
        habit_completions=habits or {},
        hours_spent=hours_spent,
        planned_hours=planned_hours,
        blockers=blockers or [],
    )


def _make_context(
    scorecards: list[dict] | None = None,
    planned_milestones: list[str] | None = None,
    target_role: str = "ML Engineer",
    timeline_months: int | None = 12,
    weekly_hours: int | None = 10,
) -> AgentContext:
    profile = UserProfileSnapshot(
        target_role=target_role,
        current_role="Software Engineer",
        skills=["Python", "FastAPI"],
        timeline_months=timeline_months,
        weekly_hours_available=weekly_hours,
    )
    plan: dict = {}
    if scorecards is not None:
        plan["scorecards"] = scorecards
    if planned_milestones is not None:
        plan["planned_milestones"] = planned_milestones
    return AgentContext(
        task_id="task-prog-001",
        session_id="sess-prog-001",
        user_id="user-prog-001",
        correlation_id="corr-prog-001",
        stream_channel="channel-prog-test",
        user_profile=profile,
        plan_snapshot=plan,
    )


def _llm_response(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _sample_drift(
    score: float = 0.3,
    severity: DriftSeverity = DriftSeverity.MINOR,
    stalled: list[str] | None = None,
) -> DriftAnalysis:
    return DriftAnalysis(
        drift_score=score,
        drift_severity=severity,
        milestone_completion_rate=0.5,
        hours_variance=-2.0,
        stalled_milestones=stalled or ["Milestone A"],
        at_risk_milestones=[],
        weeks_analysed=3,
        evidence="Test evidence.",
    )


def _sample_habit_streaks() -> list[HabitStreak]:
    return [
        HabitStreak(
            habit_name="Daily coding",
            current_streak_weeks=3,
            longest_streak_weeks=5,
            completion_rate=0.75,
            total_weeks_tracked=8,
            weeks_completed=6,
        ),
        HabitStreak(
            habit_name="Reading",
            current_streak_weeks=0,
            longest_streak_weeks=2,
            completion_rate=0.25,
            total_weeks_tracked=8,
            weeks_completed=2,
        ),
    ]


# ── _parse_scorecards ─────────────────────────────────────────────────────────


class TestParseScorecards:
    def test_empty_list_returns_empty(self):
        assert _parse_scorecards([]) == []

    def test_non_dict_items_skipped(self):
        result = _parse_scorecards(["not a dict", 42])
        assert result == []

    def test_valid_scorecard_parsed(self):
        raw = [
            {
                "week_start_date": "2026-04-07",
                "milestones_planned": ["M1"],
                "milestones_completed": ["M1"],
                "habit_completions": {"coding": True},
                "hours_spent": 8.0,
                "planned_hours": 10.0,
                "notes": "Good week",
                "blockers": [],
            }
        ]
        result = _parse_scorecards(raw)
        assert len(result) == 1
        sc = result[0]
        assert sc.week_start_date == date(2026, 4, 7)
        assert sc.milestones_completed == ["M1"]
        assert sc.habit_completions == {"coding": True}
        assert sc.hours_spent == 8.0

    def test_invalid_date_string_defaults_to_today(self):
        raw = [{"week_start_date": "not-a-date"}]
        result = _parse_scorecards(raw)
        assert result[0].week_start_date == date.today()

    def test_missing_date_defaults_to_today(self):
        raw = [{}]
        result = _parse_scorecards(raw)
        assert result[0].week_start_date == date.today()

    def test_sorted_by_week_start_date(self):
        raw = [
            {"week_start_date": "2026-04-14"},
            {"week_start_date": "2026-04-07"},
            {"week_start_date": "2026-04-21"},
        ]
        result = _parse_scorecards(raw)
        dates = [sc.week_start_date for sc in result]
        assert dates == sorted(dates)

    def test_habit_completions_values_cast_to_bool(self):
        raw = [{"habit_completions": {"coding": 1, "reading": 0}}]
        result = _parse_scorecards(raw)
        assert result[0].habit_completions["coding"] is True
        assert result[0].habit_completions["reading"] is False


# ── DriftDetector ─────────────────────────────────────────────────────────────


class TestClassifySeverity:
    def test_below_020_is_on_track(self):
        assert _classify_severity(0.0) == DriftSeverity.ON_TRACK
        assert _classify_severity(0.19) == DriftSeverity.ON_TRACK

    def test_020_to_039_is_minor(self):
        assert _classify_severity(0.20) == DriftSeverity.MINOR
        assert _classify_severity(0.39) == DriftSeverity.MINOR

    def test_040_to_064_is_moderate(self):
        assert _classify_severity(0.40) == DriftSeverity.MODERATE
        assert _classify_severity(0.64) == DriftSeverity.MODERATE

    def test_065_and_above_is_severe(self):
        assert _classify_severity(0.65) == DriftSeverity.SEVERE
        assert _classify_severity(1.0) == DriftSeverity.SEVERE


class TestDriftDetector:
    def test_empty_scorecards_returns_on_track(self, drift_detector: DriftDetector):
        result = drift_detector.detect([], ["M1", "M2"])
        assert result.drift_severity == DriftSeverity.ON_TRACK
        assert result.drift_score == 0.0
        assert result.weeks_analysed == 0

    def test_all_milestones_completed_low_drift(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", planned=["M1", "M2"], completed=["M1", "M2"],
                hours_spent=6.0, planned_hours=6.0)
        result = drift_detector.detect([sc], ["M1", "M2"])
        assert result.milestone_completion_rate == 1.0
        assert result.drift_score < 0.20

    def test_no_milestones_completed_high_drift(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", planned=["M1", "M2"], completed=[],
                hours_spent=0.0, planned_hours=10.0)
        result = drift_detector.detect([sc], ["M1", "M2"])
        assert result.drift_score >= 0.40
        assert result.stalled_milestones == ["M1", "M2"]

    def test_stalled_milestones_are_planned_but_not_completed(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", completed=["M1"])
        result = drift_detector.detect([sc], ["M1", "M2", "M3"])
        assert "M2" in result.stalled_milestones
        assert "M3" in result.stalled_milestones
        assert "M1" not in result.stalled_milestones

    def test_at_risk_milestones_from_latest_scorecard(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", planned=["M1", "M2"], completed=[])
        result = drift_detector.detect([sc], [])
        assert "M1" in result.at_risk_milestones
        assert "M2" in result.at_risk_milestones

    def test_hours_underdelivery_increases_drift(self, drift_detector: DriftDetector):
        on_track = _w("2026-04-07", hours_spent=10.0, planned_hours=10.0)
        behind = _w("2026-04-07", hours_spent=2.0, planned_hours=10.0)
        r_on = drift_detector.detect([on_track], [])
        r_behind = drift_detector.detect([behind], [])
        assert r_behind.drift_score > r_on.drift_score

    def test_over_delivery_does_not_increase_drift(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", hours_spent=20.0, planned_hours=10.0)
        result = drift_detector.detect([sc], [])
        assert result.drift_score == 0.0

    def test_hours_variance_correct_sign(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", hours_spent=4.0, planned_hours=10.0)
        result = drift_detector.detect([sc], [])
        assert result.hours_variance == pytest.approx(-6.0)

    def test_drift_score_bounded_zero_to_one(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", completed=[], hours_spent=0.0, planned_hours=100.0)
        result = drift_detector.detect([sc], ["M1", "M2", "M3"])
        assert 0.0 <= result.drift_score <= 1.0

    def test_weeks_analysed_matches_scorecard_count(self, drift_detector: DriftDetector):
        scorecards = [
            _w("2026-04-07"),
            _w("2026-04-14"),
            _w("2026-04-21"),
        ]
        result = drift_detector.detect(scorecards, [])
        assert result.weeks_analysed == 3

    def test_blockers_included_in_evidence(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", blockers=["Sick leave", "Team offsite"])
        result = drift_detector.detect([sc], [])
        assert "Sick leave" in result.evidence

    def test_no_planned_milestones_100pct_completion(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07")
        result = drift_detector.detect([sc], [])
        assert result.milestone_completion_rate == 1.0

    def test_partial_completion_moderate_drift(self, drift_detector: DriftDetector):
        sc = _w("2026-04-07", completed=["M1"], hours_spent=3.0, planned_hours=10.0)
        result = drift_detector.detect([sc], ["M1", "M2", "M3", "M4"])
        assert result.drift_severity in {DriftSeverity.MODERATE, DriftSeverity.SEVERE}


# ── HabitStreakAnalyser ───────────────────────────────────────────────────────


class TestComputeStreak:
    def test_all_completed_full_streak(self):
        result = _compute_streak("coding", [True, True, True, True])
        assert result.current_streak_weeks == 4
        assert result.longest_streak_weeks == 4
        assert result.completion_rate == 1.0

    def test_none_completed_zero_streak(self):
        result = _compute_streak("coding", [False, False, False])
        assert result.current_streak_weeks == 0
        assert result.longest_streak_weeks == 0
        assert result.completion_rate == 0.0

    def test_streak_breaks_resets_current(self):
        result = _compute_streak("coding", [True, True, False, True, True])
        assert result.current_streak_weeks == 2
        assert result.longest_streak_weeks == 2

    def test_single_entry_completed(self):
        result = _compute_streak("coding", [True])
        assert result.current_streak_weeks == 1
        assert result.completion_rate == 1.0

    def test_completion_rate_calculated_correctly(self):
        result = _compute_streak("coding", [True, False, True, False])
        assert result.completion_rate == pytest.approx(0.5, abs=0.01)
        assert result.weeks_completed == 2
        assert result.total_weeks_tracked == 4

    def test_empty_completions(self):
        result = _compute_streak("coding", [])
        assert result.current_streak_weeks == 0
        assert result.completion_rate == 0.0

    def test_longest_streak_spans_middle(self):
        result = _compute_streak("coding", [False, True, True, True, False, True])
        assert result.longest_streak_weeks == 3
        assert result.current_streak_weeks == 1


class TestHabitStreakAnalyser:
    def test_empty_scorecards_returns_empty(self, habit_analyser: HabitStreakAnalyser):
        assert habit_analyser.analyse([]) == []

    def test_single_habit_single_week(self, habit_analyser: HabitStreakAnalyser):
        sc = _w("2026-04-07", habits={"coding": True})
        result = habit_analyser.analyse([sc])
        assert len(result) == 1
        assert result[0].habit_name == "coding"
        assert result[0].current_streak_weeks == 1

    def test_multiple_habits_extracted(self, habit_analyser: HabitStreakAnalyser):
        sc = _w("2026-04-07", habits={"coding": True, "reading": False, "exercise": True})
        result = habit_analyser.analyse([sc])
        names = {h.habit_name for h in result}
        assert names == {"coding", "reading", "exercise"}

    def test_habit_absent_in_week_treated_as_not_completed(
        self, habit_analyser: HabitStreakAnalyser
    ):
        sc1 = _w("2026-04-07", habits={"coding": True})
        sc2 = _w("2026-04-14", habits={})   # "coding" absent this week
        result = habit_analyser.analyse([sc1, sc2])
        coding = next(h for h in result if h.habit_name == "coding")
        assert coding.current_streak_weeks == 0
        assert coding.completion_rate == pytest.approx(0.5, abs=0.01)

    def test_results_sorted_alphabetically(self, habit_analyser: HabitStreakAnalyser):
        sc = _w("2026-04-07", habits={"z_habit": True, "a_habit": False, "m_habit": True})
        result = habit_analyser.analyse([sc])
        names = [h.habit_name for h in result]
        assert names == sorted(names)

    def test_habit_tracked_across_multiple_weeks(self, habit_analyser: HabitStreakAnalyser):
        scorecards = [
            _w("2026-04-07", habits={"coding": True}),
            _w("2026-04-14", habits={"coding": True}),
            _w("2026-04-21", habits={"coding": False}),
            _w("2026-04-28", habits={"coding": True}),
        ]
        result = habit_analyser.analyse(scorecards)
        coding = result[0]
        assert coding.total_weeks_tracked == 4
        assert coding.weeks_completed == 3
        assert coding.completion_rate == pytest.approx(0.75, abs=0.01)
        assert coding.current_streak_weeks == 1
        assert coding.longest_streak_weeks == 2


# ── AdaptationProposer ────────────────────────────────────────────────────────


class TestBuildProposals:
    def test_valid_adaptation_parsed(self):
        raw = {
            "adaptations": [
                {
                    "adaptation_type": "pace_adjustment",
                    "trigger_reason": "User is behind on milestones.",
                    "confidence": 0.8,
                    "requires_regeneration": False,
                    "summary": "Slow down milestone pace.",
                    "changes": [
                        {
                            "change_type": "defer",
                            "target": "ML Course",
                            "description": "Move to next month.",
                            "rationale": "Capacity constraint.",
                            "priority": 1,
                        }
                    ],
                }
            ]
        }
        proposals = _build_proposals(raw)
        assert len(proposals) == 1
        p = proposals[0]
        assert p.adaptation_type == AdaptationType.PACE_ADJUSTMENT
        assert p.confidence == pytest.approx(0.8)
        assert len(p.changes) == 1
        assert p.changes[0].target == "ML Course"

    def test_unknown_adaptation_type_defaults_to_pace_adjustment(self):
        raw = {"adaptations": [{"adaptation_type": "totally_unknown", "trigger_reason": "x"}]}
        proposals = _build_proposals(raw)
        assert proposals[0].adaptation_type == AdaptationType.PACE_ADJUSTMENT

    def test_confidence_clamped_to_unit_interval(self):
        raw = {
            "adaptations": [
                {"adaptation_type": "pace_adjustment", "confidence": 99.0, "trigger_reason": "x"}
            ]
        }
        proposals = _build_proposals(raw)
        assert proposals[0].confidence == 1.0

    def test_change_without_target_skipped(self):
        raw = {
            "adaptations": [
                {
                    "adaptation_type": "pace_adjustment",
                    "trigger_reason": "x",
                    "changes": [{"change_type": "defer"}],   # no target key
                }
            ]
        }
        proposals = _build_proposals(raw)
        assert proposals[0].changes == []

    def test_non_dict_item_skipped(self):
        raw = {"adaptations": ["not a dict", None]}
        proposals = _build_proposals(raw)
        assert proposals == []

    def test_empty_adaptations_list(self):
        assert _build_proposals({"adaptations": []}) == []

    def test_requires_regeneration_defaults_false(self):
        raw = {"adaptations": [{"adaptation_type": "pace_adjustment", "trigger_reason": "x"}]}
        proposals = _build_proposals(raw)
        assert proposals[0].requires_regeneration is False


class TestHeuristicProposals:
    def test_on_track_returns_no_proposals(self):
        drift = _sample_drift(score=0.1, severity=DriftSeverity.ON_TRACK)
        assert _heuristic_proposals(drift, []) == []

    def test_minor_drift_returns_pace_adjustment(self):
        drift = _sample_drift(score=0.25, severity=DriftSeverity.MINOR)
        proposals = _heuristic_proposals(drift, [])
        types = [p.adaptation_type for p in proposals]
        assert AdaptationType.PACE_ADJUSTMENT in types

    def test_broken_habits_trigger_habit_reset(self):
        drift = _sample_drift(score=0.25, severity=DriftSeverity.MINOR)
        broken = HabitStreak(
            habit_name="Exercise",
            current_streak_weeks=0,
            longest_streak_weeks=1,
            completion_rate=0.2,
            total_weeks_tracked=5,
            weeks_completed=1,
        )
        proposals = _heuristic_proposals(drift, [broken])
        types = [p.adaptation_type for p in proposals]
        assert AdaptationType.HABIT_RESET in types

    def test_high_completion_habit_not_reset(self):
        drift = _sample_drift(score=0.25, severity=DriftSeverity.MINOR)
        good = HabitStreak(
            habit_name="Coding",
            current_streak_weeks=4,
            longest_streak_weeks=4,
            completion_rate=0.9,
            total_weeks_tracked=5,
            weeks_completed=4,
        )
        proposals = _heuristic_proposals(drift, [good])
        types = [p.adaptation_type for p in proposals]
        assert AdaptationType.HABIT_RESET not in types

    def test_severe_drift_triggers_full_regeneration(self):
        drift = _sample_drift(score=0.80, severity=DriftSeverity.SEVERE)
        proposals = _heuristic_proposals(drift, [])
        types = [p.adaptation_type for p in proposals]
        assert AdaptationType.FULL_REGENERATION in types

    def test_many_stalled_milestones_triggers_regeneration(self):
        drift = DriftAnalysis(
            drift_score=0.5,
            drift_severity=DriftSeverity.MODERATE,
            milestone_completion_rate=0.2,
            hours_variance=-5.0,
            stalled_milestones=["M1", "M2", "M3", "M4"],  # > 3
            weeks_analysed=4,
        )
        proposals = _heuristic_proposals(drift, [])
        types = [p.adaptation_type for p in proposals]
        assert AdaptationType.FULL_REGENERATION in types

    def test_regeneration_proposal_sets_flag(self):
        drift = _sample_drift(score=0.80, severity=DriftSeverity.SEVERE)
        proposals = _heuristic_proposals(drift, [])
        regen = [p for p in proposals if p.requires_regeneration]
        assert len(regen) >= 1


class TestAdaptationProposerAsync:
    async def test_successful_llm_proposals(
        self, adaptation_proposer: AdaptationProposer, mock_llm: AsyncMock
    ):
        payload = {
            "adaptations": [
                {
                    "adaptation_type": "pace_adjustment",
                    "trigger_reason": "User is behind.",
                    "confidence": 0.75,
                    "requires_regeneration": False,
                    "summary": "Slow down.",
                    "changes": [],
                }
            ]
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        drift = _sample_drift()
        result = await adaptation_proposer.propose(drift, [], {}, "Target: ML Engineer")
        assert len(result) == 1
        assert result[0].adaptation_type == AdaptationType.PACE_ADJUSTMENT

    async def test_llm_failure_returns_heuristic_fallback(
        self, adaptation_proposer: AdaptationProposer, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        drift = _sample_drift(score=0.30, severity=DriftSeverity.MINOR)
        result = await adaptation_proposer.propose(drift, [], {}, "")
        assert isinstance(result, list)

    async def test_invalid_json_returns_heuristic_fallback(
        self, adaptation_proposer: AdaptationProposer, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response("not valid json }{"))
        drift = _sample_drift(score=0.30, severity=DriftSeverity.MINOR)
        result = await adaptation_proposer.propose(drift, [], {}, "")
        assert isinstance(result, list)

    async def test_severe_drift_heuristic_includes_regeneration(
        self, adaptation_proposer: AdaptationProposer, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("down"))
        drift = _sample_drift(score=0.80, severity=DriftSeverity.SEVERE)
        result = await adaptation_proposer.propose(drift, [], {}, "")
        assert any(p.requires_regeneration for p in result)


# ── Serialisers ───────────────────────────────────────────────────────────────


class TestSerialiseDrift:
    def test_all_keys_present(self):
        drift = _sample_drift()
        out = _serialise_drift(drift)
        for key in (
            "drift_score", "drift_severity", "milestone_completion_rate",
            "hours_variance", "stalled_milestones", "at_risk_milestones",
            "weeks_analysed", "evidence",
        ):
            assert key in out

    def test_severity_is_string(self):
        out = _serialise_drift(_sample_drift())
        assert isinstance(out["drift_severity"], str)


class TestSerialiseHabitStreak:
    def test_all_keys_present(self):
        h = _sample_habit_streaks()[0]
        out = _serialise_habit_streak(h)
        for key in (
            "habit_name", "current_streak_weeks", "longest_streak_weeks",
            "completion_rate", "total_weeks_tracked", "weeks_completed",
        ):
            assert key in out


class TestSerialiseAdaptation:
    def test_all_keys_present(self):
        a = AdaptationProposal(
            adaptation_type=AdaptationType.PACE_ADJUSTMENT,
            trigger_reason="Behind on milestones.",
            changes=[
                AdaptationChange(
                    change_type="defer",
                    target="M1",
                    description="Push to next week",
                    rationale="No capacity",
                )
            ],
            confidence=0.7,
            requires_regeneration=False,
            summary="Slow the pace.",
        )
        out = _serialise_adaptation(a)
        for key in (
            "adaptation_type", "trigger_reason", "confidence",
            "requires_regeneration", "summary", "changes",
        ):
            assert key in out
        assert isinstance(out["adaptation_type"], str)
        assert len(out["changes"]) == 1
        change = out["changes"][0]
        for ckey in ("change_type", "target", "description", "rationale", "priority"):
            assert ckey in change


# ── _build_summary ────────────────────────────────────────────────────────────


class TestBuildSummary:
    def test_on_track_no_adaptations(self):
        drift = _sample_drift(score=0.05, severity=DriftSeverity.ON_TRACK)
        drift = DriftAnalysis(
            drift_score=0.05,
            drift_severity=DriftSeverity.ON_TRACK,
            milestone_completion_rate=0.9,
            hours_variance=1.0,
            weeks_analysed=2,
        )
        summary = _build_summary(drift, [], [])
        assert "on_track" in summary
        assert "regeneration" not in summary

    def test_stalled_milestones_mentioned(self):
        drift = DriftAnalysis(
            drift_score=0.5,
            drift_severity=DriftSeverity.MODERATE,
            milestone_completion_rate=0.3,
            hours_variance=-5.0,
            stalled_milestones=["ML Fundamentals", "Portfolio Project"],
            weeks_analysed=4,
        )
        summary = _build_summary(drift, [], [])
        assert "stalled" in summary

    def test_regeneration_mentioned_when_required(self):
        drift = _sample_drift(score=0.8, severity=DriftSeverity.SEVERE)
        adaptation = AdaptationProposal(
            adaptation_type=AdaptationType.FULL_REGENERATION,
            trigger_reason="Severe drift.",
            requires_regeneration=True,
            summary="Regenerate.",
        )
        summary = _build_summary(drift, [], [adaptation])
        assert "regeneration" in summary.lower()

    def test_low_habit_mentioned(self):
        drift = _sample_drift()
        bad_habit = HabitStreak(
            habit_name="Exercise",
            current_streak_weeks=0,
            longest_streak_weeks=1,
            completion_rate=0.2,
            total_weeks_tracked=5,
            weeks_completed=1,
        )
        summary = _build_summary(drift, [bad_habit], [])
        assert "habit" in summary.lower()


# ── ProgressAgent ─────────────────────────────────────────────────────────────


class TestProgressAgent:
    def _make_agent(
        self,
        proposals: list[AdaptationProposal] | None = None,
        emit_events: bool = False,
    ) -> tuple[ProgressAgent, MagicMock, MagicMock, AsyncMock]:
        mock_drift = MagicMock(spec=DriftDetector)
        mock_habit = MagicMock(spec=HabitStreakAnalyser)
        mock_adapt = AsyncMock(spec=AdaptationProposer)
        mock_publisher = MagicMock() if emit_events else None

        mock_drift.detect = MagicMock(return_value=_sample_drift())
        mock_habit.analyse = MagicMock(return_value=_sample_habit_streaks())
        mock_adapt.propose = AsyncMock(return_value=proposals or [])

        agent = ProgressAgent(
            drift_detector=mock_drift,
            habit_streak_analyser=mock_habit,
            adaptation_proposer=mock_adapt,
            event_publisher=mock_publisher,
        )
        return agent, mock_drift, mock_habit, mock_adapt

    def test_agent_type(self):
        agent, *_ = self._make_agent()
        assert agent.agent_type == AgentType.PROGRESS

    def test_display_name(self):
        agent, *_ = self._make_agent()
        assert agent.display_name == "Progress & Adaptation Agent"

    async def test_execute_returns_required_keys(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context(scorecards=[], planned_milestones=[]))
        for key in (
            "drift_analysis", "habit_streaks", "adaptations",
            "requires_regeneration", "analysis_summary", "processing_steps",
        ):
            assert key in result

    async def test_three_processing_steps(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        assert len(result["processing_steps"]) == 3

    async def test_scorecards_parsed_and_passed_to_drift_detector(self):
        agent, mock_drift, *_ = self._make_agent()
        raw_scorecards = [
            {"week_start_date": "2026-04-07", "milestones_completed": ["M1"],
             "hours_spent": 5.0, "planned_hours": 6.0},
        ]
        await agent._execute(_make_context(scorecards=raw_scorecards, planned_milestones=["M1"]))
        call_args = mock_drift.detect.call_args
        scorecards_arg = call_args[0][0]
        assert len(scorecards_arg) == 1
        assert scorecards_arg[0].milestones_completed == ["M1"]

    async def test_planned_milestones_passed_to_drift_detector(self):
        agent, mock_drift, *_ = self._make_agent()
        await agent._execute(
            _make_context(scorecards=[], planned_milestones=["M1", "M2"])
        )
        call_args = mock_drift.detect.call_args
        milestones_arg = call_args[0][1]
        assert milestones_arg == ["M1", "M2"]

    async def test_habit_analyser_receives_scorecards(self):
        agent, _, mock_habit, _ = self._make_agent()
        raw = [{"week_start_date": "2026-04-07", "habit_completions": {"coding": True}}]
        await agent._execute(_make_context(scorecards=raw))
        mock_habit.analyse.assert_called_once()

    async def test_requires_regeneration_false_when_no_proposals(self):
        agent, *_ = self._make_agent(proposals=[])
        result = await agent._execute(_make_context())
        assert result["requires_regeneration"] is False

    async def test_requires_regeneration_true_when_proposal_flagged(self):
        regen_proposal = AdaptationProposal(
            adaptation_type=AdaptationType.FULL_REGENERATION,
            trigger_reason="Severe drift.",
            requires_regeneration=True,
            summary="Regenerate.",
        )
        agent, *_ = self._make_agent(proposals=[regen_proposal])
        result = await agent._execute(_make_context())
        assert result["requires_regeneration"] is True

    async def test_three_progress_events_emitted(self):
        agent, *_ = self._make_agent(emit_events=True)
        publisher = agent._event_publisher
        await agent._execute(_make_context())
        assert publisher.emit.call_count == 3

    async def test_no_events_without_publisher(self):
        agent, *_ = self._make_agent(emit_events=False)
        result = await agent._execute(_make_context())
        assert "drift_analysis" in result

    async def test_adaptation_output_serialised(self):
        proposal = AdaptationProposal(
            adaptation_type=AdaptationType.PACE_ADJUSTMENT,
            trigger_reason="Behind schedule.",
            confidence=0.7,
            requires_regeneration=False,
            summary="Slow down.",
            changes=[
                AdaptationChange(
                    change_type="defer",
                    target="M1",
                    description="Defer M1",
                    rationale="No capacity",
                )
            ],
        )
        agent, *_ = self._make_agent(proposals=[proposal])
        result = await agent._execute(_make_context())
        assert len(result["adaptations"]) == 1
        a = result["adaptations"][0]
        assert a["adaptation_type"] == "pace_adjustment"
        assert len(a["changes"]) == 1

    async def test_full_pipeline_via_base_agent_run(self):
        agent, *_ = self._make_agent()
        result = await agent.run(_make_context())
        assert result.agent_type == AgentType.PROGRESS.value
        assert result.status == AgentResultStatus.COMPLETED
        assert "drift_analysis" in result.output
        assert result.duration_ms >= 0

    async def test_base_agent_run_returns_failed_on_exception(self):
        agent, mock_drift, *_ = self._make_agent()
        mock_drift.detect = MagicMock(side_effect=RuntimeError("Unexpected failure"))
        result = await agent.run(_make_context())
        assert result.status == AgentResultStatus.FAILED
        assert result.error_message is not None

    async def test_empty_scorecards_no_crash(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context(scorecards=[], planned_milestones=[]))
        assert "drift_analysis" in result

    async def test_drift_analysis_structure_in_output(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        da = result["drift_analysis"]
        for key in (
            "drift_score", "drift_severity", "milestone_completion_rate",
            "hours_variance", "stalled_milestones", "weeks_analysed",
        ):
            assert key in da

    async def test_habit_streaks_structure_in_output(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        assert isinstance(result["habit_streaks"], list)
        if result["habit_streaks"]:
            h = result["habit_streaks"][0]
            assert "habit_name" in h
            assert "completion_rate" in h
