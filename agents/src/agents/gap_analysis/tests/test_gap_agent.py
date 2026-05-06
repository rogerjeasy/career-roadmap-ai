"""Tests for the Gap Analysis Agent.

Covers:
  - RoleProfiler: successful LLM profile, fallback on failure, _build_role_profile helper
  - SkillGapScorer: LLM scoring, heuristic fallback, _compute_dimension_scores, _severity
  - GapPrioritiser: ranking order, urgency multiplier, empty input
  - GapAgent: full pipeline, progress events, output shape, BaseAgent.run() contract

All LLM calls are mocked — no network or Anthropic API required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.contracts.results import AgentResultStatus
from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.gap_analysis.gap_agent import GapAgent, _compute_overall_diff, _serialise_gap
from agents.gap_analysis.gap_prioritiser import GapPrioritiser, _composite, _urgency_multiplier
from agents.gap_analysis.models import (
    DimensionScores,
    GapDimension,
    GapSeverity,
    RoleProfile,
    RoleRequirement,
    SkillGap,
)
from agents.gap_analysis.role_profiler import RoleProfiler, _build_role_profile, _heuristic_profile
from agents.gap_analysis.skill_gap_scorer import (
    SkillGapScorer,
    _build_gaps,
    _compute_dimension_scores,
    _heuristic_gaps,
    _severity,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def role_profiler(mock_llm: AsyncMock) -> RoleProfiler:
    return RoleProfiler(llm=mock_llm)


@pytest.fixture
def skill_gap_scorer(mock_llm: AsyncMock) -> SkillGapScorer:
    return SkillGapScorer(llm=mock_llm)


@pytest.fixture
def gap_prioritiser() -> GapPrioritiser:
    return GapPrioritiser()


@pytest.fixture
def sample_role_profile() -> RoleProfile:
    return RoleProfile(
        role_title="Senior Backend Engineer",
        requirements=[
            RoleRequirement(
                name="Python",
                dimension=GapDimension.TECH_SKILL,
                is_required=True,
                typical_level="advanced",
            ),
            RoleRequirement(
                name="Kubernetes",
                dimension=GapDimension.TECH_SKILL,
                is_required=True,
                typical_level="intermediate",
            ),
            RoleRequirement(
                name="System Design",
                dimension=GapDimension.TECH_SKILL,
                is_required=True,
            ),
            RoleRequirement(
                name="AWS",
                dimension=GapDimension.TECH_SKILL,
                is_required=False,
                typical_level="intermediate",
            ),
            RoleRequirement(
                name="Leadership",
                dimension=GapDimension.SOFT_SKILL,
                is_required=False,
            ),
            RoleRequirement(
                name="AWS Certified Developer",
                dimension=GapDimension.CERTIFICATION,
                is_required=False,
            ),
        ],
        keywords=["Python", "microservices", "Kubernetes", "REST API"],
        typical_experience_months=60,
    )


@pytest.fixture
def sample_gaps() -> list[SkillGap]:
    return [
        SkillGap(
            requirement_name="Kubernetes",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.CRITICAL,
            is_required=True,
            diff_score=0.9,
            current_level=None,
            required_level="intermediate",
            roi_score=0.85,
            urgency_score=0.90,
            evidence="Not found in candidate skill graph",
        ),
        SkillGap(
            requirement_name="System Design",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.HIGH,
            is_required=True,
            diff_score=0.5,
            current_level="beginner",
            required_level="advanced",
            roi_score=0.75,
            urgency_score=0.70,
            evidence="Candidate has limited system design exposure",
        ),
        SkillGap(
            requirement_name="AWS",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.MEDIUM,
            is_required=False,
            diff_score=0.6,
            current_level=None,
            required_level="intermediate",
            roi_score=0.50,
            urgency_score=0.40,
            evidence="Nice-to-have skill absent",
        ),
        SkillGap(
            requirement_name="AWS Certified Developer",
            dimension=GapDimension.CERTIFICATION,
            severity=GapSeverity.LOW,
            is_required=False,
            diff_score=0.3,
            current_level=None,
            required_level=None,
            roi_score=0.30,
            urgency_score=0.20,
            evidence="Certification not listed",
        ),
    ]


def _llm_response(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _make_context(
    target_role: str = "Senior Backend Engineer",
    skills: list[str] | None = None,
    timeline_months: int | None = None,
    weekly_hours: int | None = None,
    cv_analysis: dict | None = None,
) -> AgentContext:
    profile = UserProfileSnapshot(
        target_role=target_role,
        skills=skills or ["Python", "FastAPI", "Docker"],
        timeline_months=timeline_months,
        weekly_hours_available=weekly_hours,
    )
    plan: dict = {}
    if cv_analysis is not None:
        plan["cv_analysis"] = cv_analysis
    return AgentContext(
        task_id="task-gap-001",
        session_id="sess-gap-001",
        user_id="user-gap-001",
        correlation_id="corr-gap-001",
        stream_channel="channel-gap-test",
        user_profile=profile,
        plan_snapshot=plan,
    )


# ── RoleProfiler ──────────────────────────────────────────────────────────────


class TestBuildRoleProfile:
    def test_full_response_parsed(self):
        raw = {
            "typical_experience_months": 60,
            "requirements": [
                {
                    "name": "Python",
                    "dimension": "tech_skill",
                    "is_required": True,
                    "description": "Backend development",
                    "typical_level": "advanced",
                },
                {
                    "name": "Leadership",
                    "dimension": "soft_skill",
                    "is_required": False,
                    "description": "Team leadership",
                    "typical_level": None,
                },
            ],
            "keywords": ["Python", "microservices"],
        }
        profile = _build_role_profile("Senior Backend Engineer", raw)
        assert profile.role_title == "Senior Backend Engineer"
        assert profile.typical_experience_months == 60
        assert len(profile.requirements) == 2
        assert profile.requirements[0].name == "Python"
        assert profile.requirements[0].dimension == GapDimension.TECH_SKILL
        assert profile.requirements[0].is_required is True
        assert profile.requirements[1].dimension == GapDimension.SOFT_SKILL
        assert profile.keywords == ["Python", "microservices"]

    def test_unknown_dimension_defaults_to_tech_skill(self):
        raw = {
            "requirements": [
                {"name": "SomeThing", "dimension": "unknown_dim", "is_required": True}
            ],
            "keywords": [],
        }
        profile = _build_role_profile("SomeRole", raw)
        assert profile.requirements[0].dimension == GapDimension.TECH_SKILL

    def test_item_without_name_skipped(self):
        raw = {
            "requirements": [{"dimension": "tech_skill", "is_required": True}],
            "keywords": [],
        }
        profile = _build_role_profile("Role", raw)
        assert profile.requirements == []

    def test_experience_months_type_coercion(self):
        raw = {"typical_experience_months": "48", "requirements": [], "keywords": []}
        profile = _build_role_profile("Role", raw)
        assert profile.typical_experience_months == 48

    def test_invalid_experience_months_returns_none(self):
        raw = {"typical_experience_months": "varies", "requirements": [], "keywords": []}
        profile = _build_role_profile("Role", raw)
        assert profile.typical_experience_months is None

    def test_empty_raw_returns_empty_profile(self):
        profile = _build_role_profile("Role", {})
        assert profile.requirements == []
        assert profile.keywords == []
        assert profile.typical_experience_months is None


class TestHeuristicProfile:
    def test_returns_non_empty_profile(self):
        profile = _heuristic_profile("ML Engineer")
        assert profile.role_title == "ML Engineer"
        assert len(profile.requirements) >= 3

    def test_all_requirements_have_name_and_dimension(self):
        profile = _heuristic_profile("Data Engineer")
        for req in profile.requirements:
            assert req.name
            assert isinstance(req.dimension, GapDimension)

    def test_keywords_include_role_title(self):
        profile = _heuristic_profile("DevOps Engineer")
        assert "DevOps Engineer" in profile.keywords


class TestRoleProfilerAsync:
    async def test_successful_llm_profile(
        self, role_profiler: RoleProfiler, mock_llm: AsyncMock
    ):
        payload = {
            "typical_experience_months": 48,
            "requirements": [
                {"name": "Python", "dimension": "tech_skill", "is_required": True,
                 "description": "Backend", "typical_level": "advanced"},
            ],
            "keywords": ["Python", "REST"],
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        result = await role_profiler.profile("Backend Engineer")
        assert result.role_title == "Backend Engineer"
        assert len(result.requirements) == 1
        assert result.typical_experience_months == 48

    async def test_llm_failure_returns_heuristic_fallback(
        self, role_profiler: RoleProfiler, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        result = await role_profiler.profile("ML Engineer")
        assert result.role_title == "ML Engineer"
        assert len(result.requirements) >= 1

    async def test_invalid_json_returns_fallback(
        self, role_profiler: RoleProfiler, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response("not json at all"))
        result = await role_profiler.profile("DevOps Engineer")
        assert isinstance(result, RoleProfile)


# ── SkillGapScorer ────────────────────────────────────────────────────────────


class TestSeverity:
    def test_required_high_diff_is_critical(self):
        assert _severity(0.8, True) == GapSeverity.CRITICAL

    def test_required_medium_diff_is_high(self):
        assert _severity(0.5, True) == GapSeverity.HIGH

    def test_required_low_diff_is_low(self):
        assert _severity(0.1, True) == GapSeverity.LOW

    def test_optional_high_diff_is_medium(self):
        assert _severity(0.6, False) == GapSeverity.MEDIUM

    def test_optional_low_diff_is_low(self):
        assert _severity(0.3, False) == GapSeverity.LOW


class TestBuildGaps:
    def test_gaps_below_threshold_excluded(self, sample_role_profile: RoleProfile):
        raw_gaps = [
            {
                "requirement_name": "Python",
                "dimension": "tech_skill",
                "diff_score": 0.03,
                "roi_score": 0.9,
                "urgency_score": 0.9,
                "evidence": "fully met",
            }
        ]
        gaps = _build_gaps(raw_gaps, sample_role_profile)
        assert gaps == []

    def test_gap_above_threshold_included(self, sample_role_profile: RoleProfile):
        raw_gaps = [
            {
                "requirement_name": "Kubernetes",
                "dimension": "tech_skill",
                "diff_score": 0.9,
                "roi_score": 0.85,
                "urgency_score": 0.90,
                "evidence": "not found",
            }
        ]
        gaps = _build_gaps(raw_gaps, sample_role_profile)
        assert len(gaps) == 1
        assert gaps[0].requirement_name == "Kubernetes"
        assert gaps[0].severity == GapSeverity.CRITICAL

    def test_item_without_name_skipped(self, sample_role_profile: RoleProfile):
        raw_gaps = [{"dimension": "tech_skill", "diff_score": 0.8}]
        assert _build_gaps(raw_gaps, sample_role_profile) == []

    def test_unknown_dimension_defaults_to_tech_skill(self, sample_role_profile: RoleProfile):
        raw_gaps = [
            {
                "requirement_name": "SomeNewThing",
                "dimension": "invalid",
                "diff_score": 0.7,
                "roi_score": 0.5,
                "urgency_score": 0.5,
            }
        ]
        gaps = _build_gaps(raw_gaps, sample_role_profile)
        assert gaps[0].dimension == GapDimension.TECH_SKILL

    def test_scores_clamped_to_unit_interval(self, sample_role_profile: RoleProfile):
        raw_gaps = [
            {
                "requirement_name": "Kubernetes",
                "dimension": "tech_skill",
                "diff_score": 2.5,
                "roi_score": -0.1,
                "urgency_score": 1.5,
            }
        ]
        gaps = _build_gaps(raw_gaps, sample_role_profile)
        assert gaps[0].diff_score == 1.0
        assert gaps[0].roi_score == 0.0
        assert gaps[0].urgency_score == 1.0


class TestHeuristicGaps:
    def test_present_skill_excluded(self, sample_role_profile: RoleProfile):
        candidate_skills = ["Python", "Kubernetes", "System Design", "AWS", "Leadership"]
        gaps = _heuristic_gaps(candidate_skills, sample_role_profile)
        names = [g.requirement_name for g in gaps]
        assert "Python" not in names
        assert "Kubernetes" not in names

    def test_missing_required_gets_full_diff(self, sample_role_profile: RoleProfile):
        gaps = _heuristic_gaps([], sample_role_profile)
        k8s_gaps = [g for g in gaps if g.requirement_name == "Kubernetes"]
        assert k8s_gaps[0].diff_score == 1.0

    def test_missing_optional_gets_lower_diff(self, sample_role_profile: RoleProfile):
        gaps = _heuristic_gaps(["Python", "Kubernetes", "System Design"], sample_role_profile)
        aws_gaps = [g for g in gaps if g.requirement_name == "AWS"]
        assert aws_gaps[0].diff_score == 0.6

    def test_case_insensitive_match(self, sample_role_profile: RoleProfile):
        gaps = _heuristic_gaps(["python", "kubernetes"], sample_role_profile)
        names = [g.requirement_name for g in gaps]
        assert "Python" not in names
        assert "Kubernetes" not in names


class TestComputeDimensionScores:
    def test_no_gaps_all_zeros(self):
        scores = _compute_dimension_scores([])
        assert scores.tech_skills == 0.0
        assert scores.soft_skills == 0.0
        assert scores.certifications == 0.0

    def test_single_required_tech_gap(self):
        gaps = [
            SkillGap(
                requirement_name="Kubernetes",
                dimension=GapDimension.TECH_SKILL,
                severity=GapSeverity.CRITICAL,
                is_required=True,
                diff_score=0.9,
                current_level=None,
                required_level=None,
                roi_score=0.8,
                urgency_score=0.9,
            )
        ]
        scores = _compute_dimension_scores(gaps)
        assert scores.tech_skills > 0.0
        assert scores.soft_skills == 0.0

    def test_required_gaps_weighted_higher_than_optional(self):
        required_gap = SkillGap(
            requirement_name="Python",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.CRITICAL,
            is_required=True,
            diff_score=0.8,
            current_level=None,
            required_level=None,
            roi_score=0.8,
            urgency_score=0.8,
        )
        optional_gap = SkillGap(
            requirement_name="Go",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.MEDIUM,
            is_required=False,
            diff_score=0.8,
            current_level=None,
            required_level=None,
            roi_score=0.4,
            urgency_score=0.4,
        )
        scores_req = _compute_dimension_scores([required_gap])
        scores_opt = _compute_dimension_scores([optional_gap])
        assert scores_req.tech_skills >= scores_opt.tech_skills

    def test_scores_bounded_zero_to_one(self, sample_gaps: list[SkillGap]):
        scores = _compute_dimension_scores(sample_gaps)
        for val in (
            scores.tech_skills,
            scores.soft_skills,
            scores.certifications,
            scores.portfolio,
            scores.keywords,
        ):
            assert 0.0 <= val <= 1.0


class TestSkillGapScorerAsync:
    async def test_successful_llm_scoring(
        self,
        skill_gap_scorer: SkillGapScorer,
        mock_llm: AsyncMock,
        sample_role_profile: RoleProfile,
    ):
        payload = {
            "gaps": [
                {
                    "requirement_name": "Kubernetes",
                    "dimension": "tech_skill",
                    "diff_score": 0.9,
                    "current_level": None,
                    "required_level": "intermediate",
                    "roi_score": 0.85,
                    "urgency_score": 0.90,
                    "evidence": "Not in candidate skills",
                }
            ]
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        gaps, scores = await skill_gap_scorer.score(
            ["Python", "FastAPI"], {}, sample_role_profile
        )
        assert len(gaps) == 1
        assert gaps[0].requirement_name == "Kubernetes"
        assert isinstance(scores, DimensionScores)

    async def test_llm_failure_falls_back_to_heuristic(
        self,
        skill_gap_scorer: SkillGapScorer,
        mock_llm: AsyncMock,
        sample_role_profile: RoleProfile,
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        gaps, scores = await skill_gap_scorer.score(
            ["Python"], {}, sample_role_profile
        )
        assert isinstance(gaps, list)
        assert isinstance(scores, DimensionScores)

    async def test_empty_skills_generates_gaps_for_all_requirements(
        self,
        skill_gap_scorer: SkillGapScorer,
        mock_llm: AsyncMock,
        sample_role_profile: RoleProfile,
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        gaps, _ = await skill_gap_scorer.score([], {}, sample_role_profile)
        assert len(gaps) == len(sample_role_profile.requirements)


# ── GapPrioritiser ────────────────────────────────────────────────────────────


class TestUrgencyMultiplier:
    def test_no_context_returns_one(self):
        assert _urgency_multiplier(None, None) == pytest.approx(1.0)

    def test_tight_timeline_boosts_multiplier(self):
        assert _urgency_multiplier(3, None) > 1.0

    def test_high_hours_boosts_multiplier(self):
        assert _urgency_multiplier(None, 25) > 1.0

    def test_multiplier_capped_at_1_30(self):
        assert _urgency_multiplier(1, 40) <= 1.30


class TestComposite:
    def test_higher_roi_scores_higher(self):
        base = SkillGap(
            requirement_name="A",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.HIGH,
            is_required=True,
            diff_score=0.8,
            current_level=None,
            required_level=None,
            roi_score=0.9,
            urgency_score=0.5,
        )
        low_roi = SkillGap(
            requirement_name="B",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.HIGH,
            is_required=True,
            diff_score=0.8,
            current_level=None,
            required_level=None,
            roi_score=0.2,
            urgency_score=0.5,
        )
        assert _composite(base, 1.0) > _composite(low_roi, 1.0)

    def test_critical_severity_bonus_applied(self):
        critical = SkillGap(
            requirement_name="C",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.CRITICAL,
            is_required=True,
            diff_score=0.9,
            current_level=None,
            required_level=None,
            roi_score=0.5,
            urgency_score=0.5,
        )
        low = SkillGap(
            requirement_name="D",
            dimension=GapDimension.TECH_SKILL,
            severity=GapSeverity.LOW,
            is_required=False,
            diff_score=0.9,
            current_level=None,
            required_level=None,
            roi_score=0.5,
            urgency_score=0.5,
        )
        assert _composite(critical, 1.0) > _composite(low, 1.0)


class TestGapPrioritiser:
    def test_empty_list_returns_empty(self, gap_prioritiser: GapPrioritiser):
        assert gap_prioritiser.prioritise([]) == []

    def test_ranks_assigned_correctly(
        self, gap_prioritiser: GapPrioritiser, sample_gaps: list[SkillGap]
    ):
        ranked = gap_prioritiser.prioritise(sample_gaps)
        assert len(ranked) == len(sample_gaps)
        ranks = [g.priority_rank for g in ranked]
        assert sorted(ranks) == list(range(1, len(ranked) + 1))

    def test_highest_priority_is_rank_one(
        self, gap_prioritiser: GapPrioritiser, sample_gaps: list[SkillGap]
    ):
        ranked = gap_prioritiser.prioritise(sample_gaps)
        assert ranked[0].priority_rank == 1

    def test_critical_required_gap_ranks_first(
        self, gap_prioritiser: GapPrioritiser, sample_gaps: list[SkillGap]
    ):
        ranked = gap_prioritiser.prioritise(sample_gaps)
        assert ranked[0].severity in {GapSeverity.CRITICAL, GapSeverity.HIGH}

    def test_tight_timeline_does_not_change_result_count(
        self, gap_prioritiser: GapPrioritiser, sample_gaps: list[SkillGap]
    ):
        ranked = gap_prioritiser.prioritise(sample_gaps, timeline_months=3, weekly_hours=30)
        assert len(ranked) == len(sample_gaps)

    def test_gaps_are_new_objects_with_rank_set(
        self, gap_prioritiser: GapPrioritiser, sample_gaps: list[SkillGap]
    ):
        ranked = gap_prioritiser.prioritise(sample_gaps)
        for original, ranked_gap in zip(sample_gaps, ranked):
            assert ranked_gap.priority_rank != 0


# ── GapAgent ──────────────────────────────────────────────────────────────────


class TestComputeOverallDiff:
    def test_all_zeros_produce_zero(self):
        dim = DimensionScores(0.0, 0.0, 0.0, 0.0, 0.0)
        assert _compute_overall_diff(dim) == pytest.approx(0.0)

    def test_all_ones_produce_one(self):
        dim = DimensionScores(1.0, 1.0, 1.0, 1.0, 1.0)
        assert _compute_overall_diff(dim) == pytest.approx(1.0, abs=0.001)

    def test_result_bounded_zero_to_one(self):
        dim = DimensionScores(0.5, 0.3, 0.7, 0.2, 0.4)
        result = _compute_overall_diff(dim)
        assert 0.0 <= result <= 1.0


class TestSerialiseGap:
    def test_all_keys_present(self, sample_gaps: list[SkillGap]):
        out = _serialise_gap(sample_gaps[0])
        for key in (
            "requirement_name", "dimension", "severity", "is_required",
            "diff_score", "current_level", "required_level",
            "roi_score", "urgency_score", "priority_rank", "evidence",
        ):
            assert key in out

    def test_enum_values_are_strings(self, sample_gaps: list[SkillGap]):
        out = _serialise_gap(sample_gaps[0])
        assert isinstance(out["dimension"], str)
        assert isinstance(out["severity"], str)


class TestGapAgent:
    def _make_agent(
        self,
        role_profile: RoleProfile | None = None,
        gaps: list[SkillGap] | None = None,
        emit_events: bool = False,
    ) -> tuple[GapAgent, AsyncMock, AsyncMock, GapPrioritiser]:
        mock_role_profiler = AsyncMock(spec=RoleProfiler)
        mock_skill_scorer = AsyncMock(spec=SkillGapScorer)
        mock_prioritiser = MagicMock(spec=GapPrioritiser)
        mock_publisher = MagicMock() if emit_events else None

        _profile = role_profile or RoleProfile(
            role_title="Senior Backend Engineer",
            requirements=[
                RoleRequirement(
                    name="Python",
                    dimension=GapDimension.TECH_SKILL,
                    is_required=True,
                )
            ],
            keywords=["Python"],
            typical_experience_months=60,
        )
        _gaps = gaps or [
            SkillGap(
                requirement_name="Kubernetes",
                dimension=GapDimension.TECH_SKILL,
                severity=GapSeverity.CRITICAL,
                is_required=True,
                diff_score=0.9,
                current_level=None,
                required_level="intermediate",
                roi_score=0.85,
                urgency_score=0.90,
                priority_rank=1,
                evidence="Not found",
            )
        ]
        _dim_scores = DimensionScores(0.6, 0.0, 0.0, 0.0, 0.2)

        mock_role_profiler.profile = AsyncMock(return_value=_profile)
        mock_skill_scorer.score = AsyncMock(return_value=(_gaps, _dim_scores))
        mock_prioritiser.prioritise = MagicMock(return_value=_gaps)

        agent = GapAgent(
            role_profiler=mock_role_profiler,
            skill_gap_scorer=mock_skill_scorer,
            gap_prioritiser=mock_prioritiser,
            event_publisher=mock_publisher,
        )
        return agent, mock_role_profiler, mock_skill_scorer, mock_prioritiser

    def test_agent_type(self):
        agent, *_ = self._make_agent()
        assert agent.agent_type == AgentType.GAP_ANALYSIS

    def test_display_name(self):
        agent, *_ = self._make_agent()
        assert agent.display_name == "Gap Analysis Agent"

    async def test_execute_returns_required_keys(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        for key in (
            "role_profile", "skill_gaps", "dimension_scores",
            "overall_diff_score", "prioritised_gaps", "processing_steps",
        ):
            assert key in result

    async def test_execute_has_three_processing_steps(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        assert len(result["processing_steps"]) == 3

    async def test_target_role_passed_to_role_profiler(self):
        agent, mock_profiler, *_ = self._make_agent()
        await agent._execute(_make_context(target_role="ML Engineer"))
        mock_profiler.profile.assert_called_once()
        assert mock_profiler.profile.call_args[0][0] == "ML Engineer"

    async def test_candidate_skills_from_skill_graph_nodes(self):
        agent, _, mock_scorer, _ = self._make_agent()
        cv_analysis = {
            "skill_graph": {
                "nodes": [
                    {"canonical_name": "Python"},
                    {"canonical_name": "FastAPI"},
                ]
            },
            "parsed_cv": {},
        }
        await agent._execute(_make_context(cv_analysis=cv_analysis))
        call_args = mock_scorer.score.call_args[0]
        assert "Python" in call_args[0]
        assert "FastAPI" in call_args[0]

    async def test_fallback_to_profile_skills_when_no_cv_analysis(self):
        agent, _, mock_scorer, _ = self._make_agent()
        await agent._execute(_make_context(skills=["Go", "Rust"]))
        call_args = mock_scorer.score.call_args[0]
        assert "Go" in call_args[0]

    async def test_overall_diff_score_in_range(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        assert 0.0 <= result["overall_diff_score"] <= 1.0

    async def test_dimension_scores_structure(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        dim = result["dimension_scores"]
        for key in ("tech_skills", "soft_skills", "certifications", "portfolio", "keywords"):
            assert key in dim

    async def test_three_progress_events_emitted(self):
        agent, *_ = self._make_agent(emit_events=True)
        mock_publisher = agent._event_publisher
        await agent._execute(_make_context())
        assert mock_publisher.emit.call_count == 3

    async def test_no_events_without_publisher(self):
        agent, *_ = self._make_agent(emit_events=False)
        result = await agent._execute(_make_context())
        assert "overall_diff_score" in result

    async def test_timeline_passed_to_prioritiser(self):
        agent, _, _, mock_prioritiser = self._make_agent()
        await agent._execute(_make_context(timeline_months=6))
        kwargs = mock_prioritiser.prioritise.call_args[1]
        assert kwargs["timeline_months"] == 6

    async def test_weekly_hours_passed_to_prioritiser(self):
        agent, _, _, mock_prioritiser = self._make_agent()
        await agent._execute(_make_context(weekly_hours=25))
        kwargs = mock_prioritiser.prioritise.call_args[1]
        assert kwargs["weekly_hours"] == 25

    async def test_full_pipeline_via_base_agent_run(self):
        agent, *_ = self._make_agent()
        result = await agent.run(_make_context())
        assert result.agent_type == AgentType.GAP_ANALYSIS.value
        assert result.status == AgentResultStatus.COMPLETED
        assert "overall_diff_score" in result.output
        assert result.duration_ms >= 0
