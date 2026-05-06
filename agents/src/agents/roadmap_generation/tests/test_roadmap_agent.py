"""Tests for the Roadmap Generation Agent pipeline.

All tests are isolated: no network calls, no API keys, no Redis.
LLM calls are replaced with MagicMock / AsyncMock.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.contracts.results import AgentResultStatus
from agents.contracts.tasks import UserProfileSnapshot
from agents.core.context import AgentContext, RagChunk
from agents.roadmap_generation.milestone_generator import (
    MilestoneGenerator,
    _build_user_prompt as _milestone_prompt,
    _fallback_milestones,
    _parse_milestone,
)
from agents.roadmap_generation.models import (
    DifficultyLevel,
    Habit,
    Milestone,
    Phase,
    Resource,
    ResourceType,
    RoadmapResult,
    WeeklyTask,
)
from agents.roadmap_generation.phase_generator import (
    PhaseGenerator,
    _build_user_prompt as _phase_prompt,
    _fallback_phases,
    _parse_phase,
    _split_weeks,
)
from agents.roadmap_generation.resource_linker import ResourceLinker, _chunk_to_resource, _dedup_key
from agents.roadmap_generation.roadmap_agent import (
    RoadmapAgent,
    _build_market_grounding,
    _build_summary,
    _serialise_habit,
    _serialise_milestone,
    _serialise_phase,
    _serialise_resource,
    _serialise_weekly_task,
)
from agents.roadmap_generation.weekly_planner import WeeklyPlanner, _plan_phase, _scale_phases


# ── Fixtures and helpers ─────────────────────────────────────────────────────


def _make_phase(
    index: int = 1,
    title: str = "Python Basics",
    duration_weeks: int = 8,
    difficulty: DifficultyLevel = DifficultyLevel.BEGINNER,
    skills: list[str] | None = None,
    gaps: list[str] | None = None,
) -> Phase:
    return Phase(
        index=index,
        title=title,
        description=f"Description for {title}",
        duration_weeks=duration_weeks,
        goals=["Build Python apps", "Write clean code"],
        skills_to_acquire=skills or ["Python", "OOP"],
        gaps_addressed=gaps or ["Python", "Object-Oriented Programming"],
        market_relevance="Python is the #1 trending skill",
        difficulty=difficulty,
    )


def _make_milestone(phase_index: int = 1, week_number: int = 8) -> Milestone:
    return Milestone(
        name="Python Proficiency Checkpoint",
        description="Demonstrate core Python competency",
        phase_index=phase_index,
        week_number=week_number,
        success_criteria=["Build a REST API", "Add unit tests", "Push to GitHub"],
        skills_demonstrated=["Python", "OOP"],
        deliverable="GitHub repository with documented FastAPI project",
    )


def _make_context(
    target_role: str = "Software Engineer",
    timeline_months: int = 6,
    weekly_hours: int = 10,
    plan_snapshot: dict | None = None,
) -> AgentContext:
    profile = UserProfileSnapshot(
        target_role=target_role,
        current_role="Junior Developer",
        skills=["Python", "Git"],
        timeline_months=timeline_months,
        weekly_hours_available=weekly_hours,
        location="Zurich, CH",
    )
    return AgentContext(
        task_id="task-001",
        session_id="session-001",
        user_id="user-001",
        correlation_id="corr-001",
        stream_channel="ch:001",
        user_profile=profile,
        plan_snapshot=plan_snapshot or {
            "gap_analysis": {
                "prioritised_gaps": [
                    {"requirement_name": "FastAPI", "severity": "critical", "is_required": True, "diff_score": 0.9},
                    {"requirement_name": "PostgreSQL", "severity": "high", "is_required": True, "diff_score": 0.7},
                    {"requirement_name": "Docker", "severity": "medium", "is_required": False, "diff_score": 0.5},
                ],
                "dimension_scores": {"tech_skills": 0.6, "soft_skills": 0.2},
                "overall_diff_score": 0.55,
            },
            "market_intelligence": {
                "trending_skills": [
                    {"name": "Python", "signal_count": 12, "trend_direction": "rising"},
                    {"name": "FastAPI", "signal_count": 8, "trend_direction": "rising"},
                ],
                "salary_benchmark": {
                    "median_annual": 120000,
                    "p25_annual": 95000,
                    "p75_annual": 145000,
                    "currency": "CHF",
                },
                "job_postings": [{"title": "Backend Engineer"}] * 5,
                "market_summary": "Strong demand for Python backend engineers in Switzerland.",
                "country": "CH",
            },
        },
    )


def _llm_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.content = content
    return mock


# ── TestSplitWeeks ────────────────────────────────────────────────────────────


class TestSplitWeeks:
    def test_exact_divisible(self) -> None:
        assert _split_weeks(12, 3) == [4, 4, 4]

    def test_remainder_distributed_to_first(self) -> None:
        result = _split_weeks(14, 3)
        assert sum(result) == 14
        assert len(result) == 3

    def test_single_phase(self) -> None:
        assert _split_weeks(8, 1) == [8]

    def test_minimum_one_per_phase(self) -> None:
        result = _split_weeks(2, 3)
        assert all(w >= 1 for w in result)

    def test_zero_handled(self) -> None:
        result = _split_weeks(0, 3)
        assert sum(result) == 3  # min(total, n) = n


# ── TestScalePhases ───────────────────────────────────────────────────────────


class TestScalePhases:
    def test_no_scaling_needed(self) -> None:
        phases = [_make_phase(duration_weeks=8), _make_phase(index=2, duration_weeks=8)]
        result = _scale_phases(phases, 16)
        assert [p.duration_weeks for p in result] == [8, 8]

    def test_scales_up(self) -> None:
        phases = [_make_phase(duration_weeks=4), _make_phase(index=2, duration_weeks=4)]
        result = _scale_phases(phases, 24)
        assert sum(p.duration_weeks for p in result) == 24

    def test_scales_down(self) -> None:
        phases = [_make_phase(duration_weeks=20), _make_phase(index=2, duration_weeks=20)]
        result = _scale_phases(phases, 16)
        assert sum(p.duration_weeks for p in result) == 16

    def test_empty_phases(self) -> None:
        assert _scale_phases([], 24) == []

    def test_preserves_phase_attributes(self) -> None:
        phase = _make_phase(title="Test Phase", duration_weeks=8)
        result = _scale_phases([phase], 12)
        assert result[0].title == "Test Phase"
        assert result[0].duration_weeks == 12

    def test_minimum_one_week_per_phase(self) -> None:
        phases = [_make_phase(duration_weeks=10)] * 5
        result = _scale_phases(phases, 5)
        assert all(p.duration_weeks >= 1 for p in result)


# ── TestPlanPhase ─────────────────────────────────────────────────────────────


class TestPlanPhase:
    def test_correct_number_of_weeks(self) -> None:
        phase = _make_phase(duration_weeks=4)
        tasks = _plan_phase(phase, start_week=1, weekly_hours=10, milestone=None)
        assert len(tasks) == 4

    def test_week_numbers_sequential(self) -> None:
        phase = _make_phase(duration_weeks=4)
        tasks = _plan_phase(phase, start_week=5, weekly_hours=10, milestone=None)
        assert [t.week_number for t in tasks] == [5, 6, 7, 8]

    def test_estimated_hours_matches_input(self) -> None:
        phase = _make_phase(duration_weeks=3)
        tasks = _plan_phase(phase, 1, weekly_hours=15, milestone=None)
        assert all(t.estimated_hours == 15.0 for t in tasks)

    def test_last_week_has_deliverable_when_milestone_set(self) -> None:
        phase = _make_phase(duration_weeks=3)
        milestone = _make_milestone(week_number=3)
        tasks = _plan_phase(phase, 1, 10, milestone)
        assert tasks[-1].deliverable == milestone.deliverable
        assert tasks[0].deliverable is None

    def test_no_deliverable_without_milestone(self) -> None:
        phase = _make_phase(duration_weeks=3)
        tasks = _plan_phase(phase, 1, 10, None)
        assert all(t.deliverable is None for t in tasks)

    def test_skill_rotation(self) -> None:
        phase = _make_phase(skills=["Python", "Docker"], duration_weeks=4)
        tasks = _plan_phase(phase, 1, 10, None)
        focus_areas = [t.focus_area for t in tasks]
        assert "Python" in focus_areas
        assert "Docker" in focus_areas

    def test_single_week_phase(self) -> None:
        phase = _make_phase(duration_weeks=1)
        tasks = _plan_phase(phase, 1, 10, None)
        assert len(tasks) == 1
        assert tasks[0].week_number == 1


# ── TestWeeklyPlanner ─────────────────────────────────────────────────────────


class TestWeeklyPlanner:
    def test_total_weeks_matches_timeline(self) -> None:
        planner = WeeklyPlanner()
        phases = [_make_phase(duration_weeks=12), _make_phase(index=2, duration_weeks=12)]
        milestones = [_make_milestone(1, 12), _make_milestone(2, 24)]
        schedule, _ = planner.plan(phases, milestones, timeline_months=6, weekly_hours=10)
        assert len(schedule) == 24  # 6 months * 4 weeks

    def test_core_habits_always_present(self) -> None:
        planner = WeeklyPlanner()
        _, habits = planner.plan([_make_phase()], [], 3, 10)
        habit_names = [h.name for h in habits]
        assert "Daily coding practice" in habit_names
        assert "Weekly project review" in habit_names

    def test_data_role_adds_kaggle_habit(self) -> None:
        planner = WeeklyPlanner()
        _, habits = planner.plan([_make_phase()], [], 3, 10, target_role="Data Engineer")
        assert any("Kaggle" in h.name for h in habits)

    def test_cloud_role_adds_cloud_habit(self) -> None:
        planner = WeeklyPlanner()
        _, habits = planner.plan([_make_phase()], [], 3, 10, target_role="Cloud Architect")
        assert any("Cloud" in h.name for h in habits)

    def test_unknown_role_only_core_habits(self) -> None:
        planner = WeeklyPlanner()
        _, habits = planner.plan([_make_phase()], [], 3, 10, target_role="Astronaut")
        assert len(habits) == 4  # only core habits

    def test_empty_phases_returns_empty_schedule(self) -> None:
        planner = WeeklyPlanner()
        schedule, _ = planner.plan([], [], 3, 10)
        assert schedule == []


# ── TestFallbackPhases ────────────────────────────────────────────────────────


class TestFallbackPhases:
    def test_always_produces_three_phases(self) -> None:
        phases = _fallback_phases("Python Dev", 6, [])
        assert len(phases) == 3

    def test_phases_sum_to_timeline_weeks(self) -> None:
        phases = _fallback_phases("Backend Dev", 6, [])
        assert sum(p.duration_weeks for p in phases) == 24

    def test_difficulty_progression(self) -> None:
        phases = _fallback_phases("Dev", 6, [])
        difficulties = [p.difficulty for p in phases]
        assert difficulties[0] == DifficultyLevel.BEGINNER
        assert difficulties[1] == DifficultyLevel.INTERMEDIATE
        assert difficulties[2] == DifficultyLevel.ADVANCED

    def test_critical_gaps_in_phase_1(self) -> None:
        gaps = [
            {"requirement_name": "FastAPI", "severity": "critical"},
            {"requirement_name": "PostgreSQL", "severity": "high"},
        ]
        phases = _fallback_phases("Backend Dev", 6, gaps)
        assert "FastAPI" in phases[0].gaps_addressed

    def test_indexes_are_sequential(self) -> None:
        phases = _fallback_phases("Dev", 6, [])
        assert [p.index for p in phases] == [1, 2, 3]

    def test_short_timeline(self) -> None:
        phases = _fallback_phases("Dev", 1, [])
        assert all(p.duration_weeks >= 1 for p in phases)


# ── TestParsePhase ────────────────────────────────────────────────────────────


class TestParsePhase:
    def test_parses_valid_dict(self) -> None:
        raw = {
            "index": 2,
            "title": "Advanced Python",
            "description": "Deep dive",
            "duration_weeks": 6,
            "goals": ["Build async apps"],
            "skills_to_acquire": ["AsyncIO"],
            "gaps_addressed": ["Async Programming"],
            "market_relevance": "Async is trending",
            "difficulty": "intermediate",
        }
        phase = _parse_phase(raw, 2)
        assert phase.index == 2
        assert phase.title == "Advanced Python"
        assert phase.difficulty == DifficultyLevel.INTERMEDIATE

    def test_invalid_difficulty_defaults_to_beginner(self) -> None:
        raw = {"difficulty": "expert", "index": 1, "duration_weeks": 4}
        phase = _parse_phase(raw, 1)
        assert phase.difficulty == DifficultyLevel.BEGINNER

    def test_missing_optional_fields_use_defaults(self) -> None:
        phase = _parse_phase({}, 3)
        assert phase.index == 3
        assert phase.title == "Phase 3"
        assert phase.duration_weeks >= 1
        assert phase.goals == []
        assert phase.skills_to_acquire == []

    def test_duration_weeks_minimum_one(self) -> None:
        phase = _parse_phase({"duration_weeks": 0}, 1)
        assert phase.duration_weeks == 1


# ── TestFallbackMilestones ────────────────────────────────────────────────────


class TestFallbackMilestones:
    def test_one_milestone_per_phase(self) -> None:
        phases = [_make_phase(1, duration_weeks=8), _make_phase(2, duration_weeks=8)]
        milestones = _fallback_milestones(phases)
        assert len(milestones) == 2

    def test_cumulative_week_numbers(self) -> None:
        phases = [_make_phase(1, duration_weeks=6), _make_phase(2, duration_weeks=4)]
        milestones = _fallback_milestones(phases)
        assert milestones[0].week_number == 6
        assert milestones[1].week_number == 10

    def test_phase_index_matches(self) -> None:
        phases = [_make_phase(1, duration_weeks=8), _make_phase(2, duration_weeks=8)]
        milestones = _fallback_milestones(phases)
        assert milestones[0].phase_index == 1
        assert milestones[1].phase_index == 2

    def test_success_criteria_not_empty(self) -> None:
        phases = [_make_phase(1, duration_weeks=4)]
        milestones = _fallback_milestones(phases)
        assert len(milestones[0].success_criteria) >= 3

    def test_deliverable_is_non_empty_string(self) -> None:
        phases = [_make_phase(1, duration_weeks=4)]
        milestones = _fallback_milestones(phases)
        assert milestones[0].deliverable != ""

    def test_empty_phases_returns_empty(self) -> None:
        assert _fallback_milestones([]) == []


# ── TestParseMilestone ────────────────────────────────────────────────────────


class TestParseMilestone:
    def test_parses_valid_dict(self) -> None:
        raw = {
            "name": "Python Checkpoint",
            "description": "Proves Python proficiency",
            "phase_index": 1,
            "week_number": 8,
            "success_criteria": ["Build API", "Write tests"],
            "skills_demonstrated": ["Python"],
            "deliverable": "GitHub repo",
        }
        m = _parse_milestone(raw)
        assert m.name == "Python Checkpoint"
        assert m.phase_index == 1
        assert m.week_number == 8

    def test_missing_fields_use_defaults(self) -> None:
        m = _parse_milestone({})
        assert m.name == "Phase Milestone"
        assert m.success_criteria == []
        assert m.deliverable == "Portfolio project on GitHub"


# ── TestBuildUserPromptPhase ──────────────────────────────────────────────────


class TestBuildUserPromptPhase:
    def test_contains_role_and_timeline(self) -> None:
        prompt = _phase_prompt("Backend Dev", 6, 10, [], [], None, 0)
        assert "Backend Dev" in prompt
        assert "6 months" in prompt
        assert "24" in prompt  # 6 * 4 weeks

    def test_contains_critical_gaps(self) -> None:
        gaps = [
            {"requirement_name": "FastAPI", "severity": "critical", "is_required": True, "diff_score": 0.9},
        ]
        prompt = _phase_prompt("Dev", 6, 10, gaps, [], None, 0)
        assert "FastAPI" in prompt
        assert "critical" in prompt

    def test_contains_trending_skills(self) -> None:
        skills = [{"name": "Python", "signal_count": 10, "trend_direction": "rising"}]
        prompt = _phase_prompt("Dev", 6, 10, [], skills, None, 5)
        assert "Python" in prompt

    def test_contains_salary_when_available(self) -> None:
        bench = {"median_annual": 120000, "currency": "CHF"}
        prompt = _phase_prompt("Dev", 6, 10, [], [], bench, 0)
        assert "120,000" in prompt or "120000" in prompt


# ── TestBuildUserPromptMilestone ──────────────────────────────────────────────


class TestBuildUserPromptMilestone:
    def test_contains_phase_titles(self) -> None:
        phases = [_make_phase(1, "Foundation"), _make_phase(2, "Advanced")]
        prompt = _milestone_prompt(phases, "Software Engineer")
        assert "Foundation" in prompt
        assert "Advanced" in prompt

    def test_contains_cumulative_weeks(self) -> None:
        phases = [_make_phase(duration_weeks=6), _make_phase(index=2, duration_weeks=4)]
        prompt = _milestone_prompt(phases, "Dev")
        assert "week 6" in prompt
        assert "week 10" in prompt


# ── TestResourceLinker ────────────────────────────────────────────────────────


class TestResourceLinker:
    def test_catalog_lookup_python(self) -> None:
        linker = ResourceLinker()
        phase = _make_phase(skills=["Python"])
        resources = linker.link([phase], rag_chunks=[], trending_skills=[])
        titles = [r.title for r in resources]
        assert any("Python" in t for t in titles)

    def test_catalog_lookup_alias(self) -> None:
        linker = ResourceLinker()
        phase = _make_phase(skills=["golang"])
        resources = linker.link([phase], rag_chunks=[], trending_skills=[])
        assert len(resources) > 0

    def test_deduplication(self) -> None:
        linker = ResourceLinker()
        phase1 = _make_phase(1, skills=["Python"])
        phase2 = _make_phase(2, skills=["Python"])
        resources = linker.link([phase1, phase2], rag_chunks=[], trending_skills=[])
        titles = [r.title for r in resources]
        assert len(titles) == len(set(titles))

    def test_rag_chunks_take_priority(self) -> None:
        linker = ResourceLinker()
        chunk = RagChunk(
            chunk_id="c1",
            content="FastAPI Tutorial content",
            source="docs.fastapi",
            relevance_score=0.9,
            metadata={
                "title": "FastAPI Deep Dive",
                "provider": "Custom Docs",
                "resource_type": "tutorial",
                "difficulty": "intermediate",
                "is_free": True,
            },
        )
        phase = _make_phase(skills=["FastAPI"])
        resources = linker.link([phase], rag_chunks=[chunk], trending_skills=[])
        assert any(r.title == "FastAPI Deep Dive" for r in resources)

    def test_max_per_phase_respected(self) -> None:
        linker = ResourceLinker()
        phase = _make_phase(skills=["Python", "Docker", "FastAPI", "PostgreSQL", "Go"])
        resources = linker.link([phase], rag_chunks=[], trending_skills=[], max_per_phase=2)
        assert len(resources) <= 2

    def test_unknown_skill_returns_empty_gracefully(self) -> None:
        linker = ResourceLinker()
        phase = _make_phase(skills=["QuantumFortran"])
        resources = linker.link([phase], rag_chunks=[], trending_skills=[])
        assert isinstance(resources, list)


# ── TestChunkToResource ───────────────────────────────────────────────────────


class TestChunkToResource:
    def test_valid_chunk_converts(self) -> None:
        chunk = RagChunk(
            chunk_id="c1",
            content="Some tutorial content",
            source="example.com",
            relevance_score=0.8,
            metadata={
                "title": "My Tutorial",
                "provider": "Example",
                "resource_type": "course",
                "difficulty": "beginner",
                "url": "https://example.com",
                "is_free": True,
            },
        )
        resource = _chunk_to_resource(chunk, ["Python"])
        assert resource is not None
        assert resource.title == "My Tutorial"
        assert resource.resource_type == ResourceType.COURSE
        assert resource.difficulty == DifficultyLevel.BEGINNER

    def test_missing_title_falls_back_to_content_prefix(self) -> None:
        chunk = RagChunk(
            chunk_id="c2",
            content="A" * 80,
            source="example.com",
            relevance_score=0.5,
            metadata={"provider": "X"},
        )
        resource = _chunk_to_resource(chunk, [])
        assert resource is not None
        assert len(resource.title) <= 60

    def test_no_title_and_no_provider_returns_none(self) -> None:
        chunk = RagChunk(
            chunk_id="c3",
            content="",
            source="",
            relevance_score=0.1,
            metadata={},
        )
        resource = _chunk_to_resource(chunk, [])
        assert resource is None

    def test_invalid_resource_type_defaults_to_tutorial(self) -> None:
        chunk = RagChunk(
            chunk_id="c4",
            content="stuff",
            source="s",
            relevance_score=0.5,
            metadata={"title": "T", "provider": "P", "resource_type": "podcast"},
        )
        r = _chunk_to_resource(chunk, [])
        assert r is not None
        assert r.resource_type == ResourceType.TUTORIAL

    def test_invalid_difficulty_defaults_to_intermediate(self) -> None:
        chunk = RagChunk(
            chunk_id="c5",
            content="stuff",
            source="s",
            relevance_score=0.5,
            metadata={"title": "T", "provider": "P", "difficulty": "expert"},
        )
        r = _chunk_to_resource(chunk, [])
        assert r is not None
        assert r.difficulty == DifficultyLevel.INTERMEDIATE


# ── TestSerialisers ───────────────────────────────────────────────────────────


class TestSerialisers:
    def test_serialise_phase_keys(self) -> None:
        phase = _make_phase()
        d = _serialise_phase(phase)
        for key in ("index", "title", "description", "duration_weeks", "goals",
                    "skills_to_acquire", "gaps_addressed", "market_relevance", "difficulty"):
            assert key in d
        assert d["difficulty"] == "beginner"

    def test_serialise_milestone_keys(self) -> None:
        m = _make_milestone()
        d = _serialise_milestone(m)
        for key in ("name", "description", "phase_index", "week_number",
                    "success_criteria", "skills_demonstrated", "deliverable"):
            assert key in d

    def test_serialise_weekly_task_keys(self) -> None:
        task = WeeklyTask(week_number=1, phase_index=1, focus_area="Python",
                          tasks=["Do X"], estimated_hours=10.0)
        d = _serialise_weekly_task(task)
        for key in ("week_number", "phase_index", "focus_area", "tasks",
                    "estimated_hours", "deliverable"):
            assert key in d

    def test_serialise_habit_keys(self) -> None:
        habit = Habit(name="Daily coding", frequency="daily",
                      duration_minutes=30, rationale="Builds habit")
        d = _serialise_habit(habit)
        for key in ("name", "frequency", "duration_minutes", "rationale", "phase_start"):
            assert key in d

    def test_serialise_resource_keys(self) -> None:
        r = Resource(
            title="Python Tutorial",
            resource_type=ResourceType.TUTORIAL,
            provider="Official",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["python"],
        )
        d = _serialise_resource(r)
        for key in ("title", "resource_type", "provider", "difficulty",
                    "tags", "url", "estimated_hours", "is_free", "description"):
            assert key in d
        assert d["resource_type"] == "tutorial"
        assert d["difficulty"] == "beginner"


# ── TestBuildSummary ──────────────────────────────────────────────────────────


class TestBuildSummary:
    def test_contains_role_and_timeline(self) -> None:
        phases = [_make_phase(1, "Foundation", 8)]
        summary = _build_summary("Python Dev", 6, phases, [], [])
        assert "Python Dev" in summary
        assert "6 months" in summary

    def test_includes_phase_titles(self) -> None:
        phases = [_make_phase(1, "Foundation"), _make_phase(2, "Advanced")]
        summary = _build_summary("Dev", 6, phases, [], [])
        assert "Foundation" in summary
        assert "Advanced" in summary

    def test_includes_trending_skills(self) -> None:
        skills = [{"name": "Python"}, {"name": "FastAPI"}]
        summary = _build_summary("Dev", 6, [_make_phase()], [], skills)
        assert "Python" in summary

    def test_mentions_milestone_count(self) -> None:
        milestones = [_make_milestone(1), _make_milestone(2)]
        summary = _build_summary("Dev", 6, [_make_phase()], milestones, [])
        assert "2" in summary


# ── TestBuildMarketGrounding ──────────────────────────────────────────────────


class TestBuildMarketGrounding:
    def test_all_keys_present(self) -> None:
        market_intel = {
            "market_summary": "Strong demand",
            "job_postings": [{}] * 10,
            "country": "CH",
        }
        salary = {"median_annual": 120000, "currency": "CHF"}
        trending = [{"name": "Python"}, {"name": "FastAPI"}]
        result = _build_market_grounding(market_intel, trending, salary)
        assert result["job_posting_count"] == 10
        assert result["salary_median"] == 120000
        assert result["salary_currency"] == "CHF"
        assert result["country"] == "CH"
        assert "Python" in result["top_trending_skills"]

    def test_no_salary_benchmark(self) -> None:
        result = _build_market_grounding({}, [], None)
        assert result["salary_median"] is None
        assert result["salary_currency"] is None


# ── TestPhaseGeneratorAsync ───────────────────────────────────────────────────


class TestPhaseGeneratorAsync:
    async def test_llm_success_returns_phases(self) -> None:
        llm_payload = json.dumps({
            "phases": [
                {
                    "index": 1,
                    "title": "Python Foundations",
                    "description": "Core Python",
                    "duration_weeks": 8,
                    "goals": ["Build apps"],
                    "skills_to_acquire": ["Python"],
                    "gaps_addressed": ["Python"],
                    "market_relevance": "In demand",
                    "difficulty": "beginner",
                },
                {
                    "index": 2,
                    "title": "Applied Python",
                    "description": "Real projects",
                    "duration_weeks": 8,
                    "goals": ["Deploy APIs"],
                    "skills_to_acquire": ["FastAPI"],
                    "gaps_addressed": ["FastAPI"],
                    "market_relevance": "FastAPI trending",
                    "difficulty": "intermediate",
                },
                {
                    "index": 3,
                    "title": "Cloud & Ops",
                    "description": "Cloud deployment",
                    "duration_weeks": 8,
                    "goals": ["Deploy to cloud"],
                    "skills_to_acquire": ["Docker"],
                    "gaps_addressed": ["Docker"],
                    "market_relevance": "Cloud essential",
                    "difficulty": "advanced",
                },
            ]
        })
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(llm_payload))
        gen = PhaseGenerator(llm=mock_llm)
        phases = await gen.generate("Software Engineer", 6, 10, [], [], None, 5)
        assert len(phases) == 3
        assert phases[0].title == "Python Foundations"
        assert phases[2].difficulty == DifficultyLevel.ADVANCED

    async def test_llm_failure_returns_fallback(self) -> None:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("API error"))
        gen = PhaseGenerator(llm=mock_llm)
        phases = await gen.generate("Backend Dev", 6, 10, [], [], None, 0)
        assert len(phases) == 3  # fallback always produces 3

    async def test_llm_bad_json_falls_back(self) -> None:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response("not json"))
        gen = PhaseGenerator(llm=mock_llm)
        phases = await gen.generate("Dev", 6, 10, [], [], None, 0)
        assert len(phases) == 3

    async def test_llm_missing_phases_key_falls_back(self) -> None:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response('{"result": []}'))
        gen = PhaseGenerator(llm=mock_llm)
        phases = await gen.generate("Dev", 6, 10, [], [], None, 0)
        assert len(phases) == 3


# ── TestMilestoneGeneratorAsync ───────────────────────────────────────────────


class TestMilestoneGeneratorAsync:
    async def test_llm_success_returns_milestones(self) -> None:
        payload = json.dumps({
            "milestones": [
                {
                    "name": "Python Checkpoint",
                    "description": "Core Python done",
                    "phase_index": 1,
                    "week_number": 8,
                    "success_criteria": ["Build API", "Add tests", "Push to GitHub"],
                    "skills_demonstrated": ["Python"],
                    "deliverable": "GitHub repo",
                }
            ]
        })
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(payload))
        gen = MilestoneGenerator(llm=mock_llm)
        phases = [_make_phase(duration_weeks=8)]
        milestones = await gen.generate(phases, "Dev")
        assert len(milestones) == 1
        assert milestones[0].name == "Python Checkpoint"

    async def test_llm_failure_returns_fallback(self) -> None:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("fail"))
        gen = MilestoneGenerator(llm=mock_llm)
        phases = [_make_phase(1, duration_weeks=8), _make_phase(2, duration_weeks=8)]
        milestones = await gen.generate(phases, "Dev")
        assert len(milestones) == 2  # one per phase fallback


# ── TestRoadmapAgent ──────────────────────────────────────────────────────────


class TestRoadmapAgent:
    def _build_agent(
        self,
        phases: list[Phase] | None = None,
        milestones: list[Milestone] | None = None,
        weekly_schedule: list[WeeklyTask] | None = None,
        habits: list[Habit] | None = None,
        resources: list[Resource] | None = None,
    ) -> RoadmapAgent:
        _phases = phases or [_make_phase(duration_weeks=12), _make_phase(2, duration_weeks=12)]
        _milestones = milestones or [_make_milestone(1, 12), _make_milestone(2, 24)]
        _schedule = weekly_schedule or [
            WeeklyTask(week_number=i, phase_index=1, focus_area="Python",
                       tasks=["Do X"], estimated_hours=10.0)
            for i in range(1, 5)
        ]
        _habits = habits or [Habit("Daily coding", "daily", 30, "Builds habit")]
        _resources = resources or [
            Resource("Python Tutorial", ResourceType.TUTORIAL, "Official",
                     DifficultyLevel.BEGINNER, ["python"])
        ]

        mock_pg = MagicMock()
        mock_pg.generate = AsyncMock(return_value=_phases)

        mock_mg = MagicMock()
        mock_mg.generate = AsyncMock(return_value=_milestones)

        mock_wp = MagicMock()
        mock_wp.plan = MagicMock(return_value=(_schedule, _habits))

        mock_rl = MagicMock()
        mock_rl.link = MagicMock(return_value=_resources)

        return RoadmapAgent(
            phase_generator=mock_pg,
            milestone_generator=mock_mg,
            weekly_planner=mock_wp,
            resource_linker=mock_rl,
        )

    async def test_returns_completed_status(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        assert result.status == AgentResultStatus.COMPLETED

    async def test_output_schema_has_all_keys(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        for key in ("roadmap_id", "role", "timeline_months", "generated_at",
                    "phases", "milestones", "weekly_schedule", "habits",
                    "resources", "summary", "market_grounding", "processing_steps"):
            assert key in result.output, f"Missing key: {key}"

    async def test_role_from_user_profile(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context(target_role="Data Engineer"))
        assert result.output["role"] == "Data Engineer"

    async def test_timeline_months_from_user_profile(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context(timeline_months=9))
        assert result.output["timeline_months"] == 9

    async def test_phases_serialised(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        phases = result.output["phases"]
        assert len(phases) == 2
        assert phases[0]["difficulty"] in ("beginner", "intermediate", "advanced")

    async def test_milestones_serialised(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        milestones = result.output["milestones"]
        assert len(milestones) == 2
        assert "success_criteria" in milestones[0]

    async def test_processing_steps_in_order(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        assert result.output["processing_steps"] == [
            "phase_generation",
            "milestone_generation",
            "weekly_planning",
            "resource_linking",
        ]

    async def test_market_grounding_populated(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        mg = result.output["market_grounding"]
        assert "top_trending_skills" in mg
        assert "salary_median" in mg

    async def test_default_role_when_profile_empty(self) -> None:
        agent = self._build_agent()
        profile = UserProfileSnapshot()  # no target_role
        ctx = AgentContext(
            task_id="t", session_id="s", user_id="u",
            correlation_id="c", stream_channel="ch",
            user_profile=profile,
        )
        result = await agent.run(ctx)
        assert result.output["role"] == "Software Engineer"

    async def test_emits_progress_events(self) -> None:
        mock_publisher = MagicMock()
        mock_publisher.emit = MagicMock()
        agent = self._build_agent()
        agent._event_publisher = mock_publisher
        await agent.run(_make_context())
        assert mock_publisher.emit.call_count == 4  # one per step

    async def test_progress_emit_failure_does_not_abort_pipeline(self) -> None:
        mock_publisher = MagicMock()
        mock_publisher.emit = MagicMock(side_effect=RuntimeError("redis down"))
        agent = self._build_agent()
        agent._event_publisher = mock_publisher
        result = await agent.run(_make_context())
        assert result.status == AgentResultStatus.COMPLETED

    async def test_roadmap_id_is_uuid_string(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        import re
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_re.match(result.output["roadmap_id"])

    async def test_generated_at_is_iso_string(self) -> None:
        agent = self._build_agent()
        result = await agent.run(_make_context())
        from datetime import datetime
        # Should parse without error
        datetime.fromisoformat(result.output["generated_at"])

    async def test_phase_generator_called_with_correct_role(self) -> None:
        phases = [_make_phase(duration_weeks=24)]
        milestones = [_make_milestone(1, 24)]

        mock_pg = MagicMock()
        mock_pg.generate = AsyncMock(return_value=phases)
        mock_mg = MagicMock()
        mock_mg.generate = AsyncMock(return_value=milestones)
        mock_wp = MagicMock()
        mock_wp.plan = MagicMock(return_value=([], []))
        mock_rl = MagicMock()
        mock_rl.link = MagicMock(return_value=[])

        agent = RoadmapAgent(
            phase_generator=mock_pg,
            milestone_generator=mock_mg,
            weekly_planner=mock_wp,
            resource_linker=mock_rl,
        )
        await agent.run(_make_context(target_role="Machine Learning Engineer"))
        call_kwargs = mock_pg.generate.call_args
        assert call_kwargs[0][0] == "Machine Learning Engineer"

    async def test_full_stub_pipeline_end_to_end(self) -> None:
        """End-to-end test with real WeeklyPlanner and ResourceLinker (no LLM)."""
        phases = [
            _make_phase(1, "Foundation", 12, DifficultyLevel.BEGINNER, ["Python", "FastAPI"]),
            _make_phase(2, "Applied Dev", 12, DifficultyLevel.INTERMEDIATE, ["Docker", "PostgreSQL"]),
        ]
        milestones = [_make_milestone(1, 12), _make_milestone(2, 24)]

        mock_pg = MagicMock()
        mock_pg.generate = AsyncMock(return_value=phases)
        mock_mg = MagicMock()
        mock_mg.generate = AsyncMock(return_value=milestones)

        agent = RoadmapAgent(
            phase_generator=mock_pg,
            milestone_generator=mock_mg,
            weekly_planner=WeeklyPlanner(),
            resource_linker=ResourceLinker(),
        )
        ctx = _make_context("Backend Engineer", timeline_months=6, weekly_hours=10)
        result = await agent.run(ctx)
        assert result.status == AgentResultStatus.COMPLETED
        assert len(result.output["weekly_schedule"]) == 24
        assert len(result.output["phases"]) == 2
        assert len(result.output["resources"]) > 0
        assert len(result.output["habits"]) >= 4
