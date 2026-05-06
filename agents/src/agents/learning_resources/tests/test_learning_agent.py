"""Tests for the Learning Resources Agent.

Covers:
  - ResourceMatcher: relevance scoring, bundle creation, empty input
  - ResourceRanker: weighted scoring, cost/level/quality scoring, top resources
  - ResourceEmbedder: phase assignment, hours estimation, empty phase skipping
  - CourseFetcher: concurrent fetching, per-gap failure tolerance, level inference
  - LearningAgent: full pipeline, progress events, output shape, BaseAgent.run() contract

All MCP calls are stubbed — no network or external services required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.contracts.results import AgentResultStatus
from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.learning_resources.course_fetcher import CourseFetcher, _infer_search_level
from agents.learning_resources.learning_agent import (
    LearningAgent,
    _collect_data_sources,
    _resolve_gaps,
    _serialise_bundle,
    _serialise_resource,
)
from agents.learning_resources.mcp_client import StubMCPClient
from agents.learning_resources.models import (
    LearningResource,
    ResourceFormat,
    ResourceLevel,
    SkillResourceBundle,
)
from agents.learning_resources.resource_embedder import (
    ResourceEmbedder,
    _assign_phase,
    _estimate_hours,
)
from agents.learning_resources.resource_matcher import (
    ResourceMatcher,
    _compute_relevance,
    _tokenise,
)
from agents.learning_resources.resource_ranker import (
    ResourceRanker,
    _cost_value_score,
    _level_fit_score,
    _score_resource,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_profile() -> UserProfileSnapshot:
    return UserProfileSnapshot(
        target_role="ML Engineer",
        current_role="Backend Engineer",
        skills=["Python", "SQL"],
        timeline_months=12,
        weekly_hours_available=10,
    )


@pytest.fixture
def sample_context(sample_profile: UserProfileSnapshot) -> AgentContext:
    return AgentContext(
        task_id="task-lr-001",
        session_id="sess-001",
        user_id="user-001",
        correlation_id="corr-001",
        stream_channel="channel-001",
        user_profile=sample_profile,
        plan_snapshot={
            "gap_analysis": {
                "prioritised_gaps": [
                    {
                        "requirement_name": "Python",
                        "dimension": "tech_skill",
                        "severity": "high",
                        "priority_rank": 1,
                        "current_level": "beginner",
                        "required_level": "advanced",
                        "is_required": True,
                        "diff_score": 0.6,
                    },
                    {
                        "requirement_name": "Machine Learning",
                        "dimension": "tech_skill",
                        "severity": "critical",
                        "priority_rank": 2,
                        "current_level": None,
                        "required_level": "intermediate",
                        "is_required": True,
                        "diff_score": 0.9,
                    },
                    {
                        "requirement_name": "Docker",
                        "dimension": "tech_skill",
                        "severity": "medium",
                        "priority_rank": 5,
                        "current_level": "beginner",
                        "required_level": "intermediate",
                        "is_required": False,
                        "diff_score": 0.4,
                    },
                ]
            }
        },
    )


@pytest.fixture
def sample_resource() -> LearningResource:
    return LearningResource(
        resource_id="py-001",
        title="Python for Everybody",
        provider="Coursera",
        skill_tags=["python", "programming"],
        level=ResourceLevel.BEGINNER,
        format=ResourceFormat.COURSE,
        duration_hours=35.0,
        cost_usd=0.0,
        quality_score=0.92,
        relevance_score=0.75,
        overall_score=0.0,
        is_free=True,
    )


@pytest.fixture
def sample_resource_paid() -> LearningResource:
    return LearningResource(
        resource_id="py-002",
        title="Complete Python Bootcamp",
        provider="Udemy",
        skill_tags=["python", "oop", "data structures"],
        level=ResourceLevel.BEGINNER,
        format=ResourceFormat.COURSE,
        duration_hours=22.0,
        cost_usd=19.99,
        quality_score=0.89,
        relevance_score=0.65,
        overall_score=0.0,
        is_free=False,
    )


@pytest.fixture
def sample_bundle(sample_resource: LearningResource, sample_resource_paid: LearningResource) -> SkillResourceBundle:
    return SkillResourceBundle(
        skill_gap="Python",
        gap_severity="high",
        gap_priority_rank=1,
        resources=[sample_resource, sample_resource_paid],
    )


# ── ResourceMatcher tests ─────────────────────────────────────────────────────


class TestTokenise:
    def test_splits_on_spaces(self):
        assert "machine" in _tokenise("machine learning")
        assert "learning" in _tokenise("machine learning")

    def test_splits_on_hyphens(self):
        tokens = _tokenise("deep-learning")
        assert "deep" in tokens
        assert "learning" in tokens

    def test_filters_single_chars(self):
        tokens = _tokenise("a b c python")
        assert "a" not in tokens
        assert "python" in tokens

    def test_normalises_case(self):
        tokens = _tokenise("PyTorch")
        assert "pytorch" in tokens


class TestComputeRelevance:
    def test_exact_match(self):
        score = _compute_relevance(frozenset({"python"}), ["python"])
        assert score == 1.0

    def test_partial_match(self):
        score = _compute_relevance(frozenset({"python", "machine"}), ["python", "data"])
        assert 0.0 < score < 1.0

    def test_no_overlap(self):
        score = _compute_relevance(frozenset({"python"}), ["kubernetes"])
        assert score == 0.0

    def test_empty_gap_keywords_returns_neutral(self):
        score = _compute_relevance(frozenset(), ["python"])
        assert score == 0.5

    def test_empty_tags_returns_neutral(self):
        score = _compute_relevance(frozenset({"python"}), [])
        assert score == 0.5


class TestResourceMatcher:
    def test_creates_bundle_per_gap(self, sample_context: AgentContext):
        matcher = ResourceMatcher()
        gaps = sample_context.plan_snapshot["gap_analysis"]["prioritised_gaps"]
        raw = {
            "Python": [
                {
                    "id": "py-001", "title": "Python for Everybody",
                    "provider": "Coursera", "skill_tags": ["python", "programming"],
                    "level": "beginner", "format": "course", "duration_hours": 35.0,
                    "cost_usd": 0.0, "quality_score": 0.92,
                }
            ],
            "Machine Learning": [],
            "Docker": [],
        }
        bundles = matcher.match(gaps, raw)
        assert len(bundles) == 3
        # Sorted by priority_rank
        assert bundles[0].skill_gap == "Python"
        assert bundles[1].skill_gap == "Machine Learning"
        assert bundles[2].skill_gap == "Docker"

    def test_empty_courses_produces_empty_bundle(self, sample_context: AgentContext):
        matcher = ResourceMatcher()
        gaps = sample_context.plan_snapshot["gap_analysis"]["prioritised_gaps"][:1]
        bundles = matcher.match(gaps, {"Python": []})
        assert bundles[0].resources == []

    def test_respects_top_k(self):
        matcher = ResourceMatcher(top_k=1)
        gaps = [{"requirement_name": "Python", "severity": "high", "priority_rank": 1}]
        raw_courses = [
            {"id": f"py-{i}", "title": f"Course {i}", "provider": "X",
             "skill_tags": ["python"], "level": "intermediate", "format": "course",
             "duration_hours": 10.0, "cost_usd": 0.0, "quality_score": 0.8}
            for i in range(5)
        ]
        bundles = matcher.match(gaps, {"Python": raw_courses})
        assert len(bundles[0].resources) == 1

    def test_sets_overall_score_to_zero(self, sample_resource: LearningResource):
        matcher = ResourceMatcher()
        gaps = [{"requirement_name": "Python", "severity": "high", "priority_rank": 1}]
        raw = [{"id": "py-001", "title": "P4E", "provider": "Coursera",
                "skill_tags": ["python"], "level": "beginner", "format": "course",
                "duration_hours": 35.0, "cost_usd": 0.0, "quality_score": 0.92}]
        bundles = matcher.match(gaps, {"Python": raw})
        assert bundles[0].resources[0].overall_score == 0.0


# ── ResourceRanker tests ──────────────────────────────────────────────────────


class TestCostValueScore:
    def test_free_is_one(self):
        assert _cost_value_score(0.0) == 1.0

    def test_cheap_is_high(self):
        assert _cost_value_score(15.0) == 0.85

    def test_mid_range(self):
        assert _cost_value_score(35.0) == 0.70

    def test_expensive(self):
        assert _cost_value_score(200.0) == 0.40


class TestLevelFitScore:
    def test_critical_beginner_is_high(self):
        assert _level_fit_score(ResourceLevel.BEGINNER, "critical") == 0.95

    def test_high_intermediate_is_perfect(self):
        assert _level_fit_score(ResourceLevel.INTERMEDIATE, "high") == 1.00

    def test_medium_advanced_is_perfect(self):
        assert _level_fit_score(ResourceLevel.ADVANCED, "medium") == 1.00

    def test_unknown_severity_returns_fallback(self):
        assert _level_fit_score(ResourceLevel.INTERMEDIATE, "unknown") == 0.70


class TestResourceRanker:
    def test_score_increases_overall(self, sample_resource: LearningResource):
        scored = _score_resource(sample_resource, "high")
        assert scored.overall_score > 0.0
        assert 0.0 <= scored.overall_score <= 1.0

    def test_free_resource_scores_higher(
        self, sample_resource: LearningResource, sample_resource_paid: LearningResource
    ):
        scored_free = _score_resource(sample_resource, "high")
        scored_paid = _score_resource(sample_resource_paid, "high")
        # Free resource: same quality/level, so cost difference should push it higher
        assert scored_free.overall_score > scored_paid.overall_score

    def test_rank_sorts_resources(self, sample_bundle: SkillResourceBundle):
        ranker = ResourceRanker()
        bundles, top = ranker.rank([sample_bundle])
        resources = bundles[0].resources
        assert len(resources) == 2
        assert resources[0].overall_score >= resources[1].overall_score

    def test_top_resources_are_deduplicated(self, sample_resource: LearningResource):
        bundle1 = SkillResourceBundle(
            skill_gap="Python", gap_severity="high", gap_priority_rank=1,
            resources=[sample_resource],
        )
        bundle2 = SkillResourceBundle(
            skill_gap="ML", gap_severity="critical", gap_priority_rank=2,
            resources=[sample_resource],  # same resource in two gaps
        )
        ranker = ResourceRanker()
        _, top = ranker.rank([bundle1, bundle2])
        ids = [r.resource_id for r in top]
        assert ids.count(sample_resource.resource_id) == 1

    def test_respects_top_global(self, sample_resource: LearningResource):
        bundles = [
            SkillResourceBundle(
                skill_gap=f"skill-{i}", gap_severity="high", gap_priority_rank=i + 1,
                resources=[
                    LearningResource(
                        resource_id=f"r-{i}-{j}", title=f"Course {i}{j}", provider="X",
                        skill_tags=["python"], level=ResourceLevel.INTERMEDIATE,
                        format=ResourceFormat.COURSE, duration_hours=10.0,
                        cost_usd=0.0, quality_score=0.8, relevance_score=0.7,
                        overall_score=0.0, is_free=True,
                    )
                    for j in range(3)
                ],
            )
            for i in range(10)
        ]
        ranker = ResourceRanker(top_global=5)
        _, top = ranker.rank(bundles)
        assert len(top) == 5


# ── ResourceEmbedder tests ────────────────────────────────────────────────────


class TestAssignPhase:
    def test_critical_always_phase_1(self):
        assert _assign_phase(10, "critical") == 1

    def test_priority_1_is_phase_1(self):
        assert _assign_phase(1, "high") == 1

    def test_priority_3_is_phase_1(self):
        assert _assign_phase(3, "high") == 1

    def test_priority_4_high_is_phase_2(self):
        assert _assign_phase(4, "high") == 2

    def test_priority_8_medium_is_phase_3(self):
        assert _assign_phase(8, "medium") == 3


class TestEstimateHours:
    def test_sums_known_durations(self):
        resources = [
            LearningResource(
                resource_id="r1", title="R1", provider="X", skill_tags=[], level=ResourceLevel.BEGINNER,
                format=ResourceFormat.COURSE, duration_hours=10.0, cost_usd=0.0,
                quality_score=0.8, relevance_score=0.7, overall_score=0.0, is_free=True,
            ),
            LearningResource(
                resource_id="r2", title="R2", provider="X", skill_tags=[], level=ResourceLevel.INTERMEDIATE,
                format=ResourceFormat.COURSE, duration_hours=20.0, cost_usd=0.0,
                quality_score=0.8, relevance_score=0.7, overall_score=0.0, is_free=True,
            ),
        ]
        assert _estimate_hours(resources) == 30.0

    def test_uses_fallback_for_missing_duration(self):
        resource = LearningResource(
            resource_id="r1", title="R1", provider="X", skill_tags=[], level=ResourceLevel.BEGINNER,
            format=ResourceFormat.COURSE, duration_hours=None, cost_usd=0.0,
            quality_score=0.8, relevance_score=0.7, overall_score=0.0, is_free=True,
        )
        assert _estimate_hours([resource]) == 20.0


class TestResourceEmbedder:
    def _make_bundle(self, skill: str, severity: str, rank: int, n_resources: int = 2) -> SkillResourceBundle:
        resources = [
            LearningResource(
                resource_id=f"{skill}-{j}", title=f"{skill} course {j}", provider="X",
                skill_tags=[skill.lower()], level=ResourceLevel.INTERMEDIATE,
                format=ResourceFormat.COURSE, duration_hours=10.0, cost_usd=0.0,
                quality_score=0.8, relevance_score=0.8, overall_score=0.75, is_free=True,
            )
            for j in range(n_resources)
        ]
        return SkillResourceBundle(
            skill_gap=skill, gap_severity=severity, gap_priority_rank=rank, resources=resources
        )

    def test_produces_up_to_3_phases(self):
        bundles = [
            self._make_bundle("Python", "critical", 1),
            self._make_bundle("Docker", "high", 4),
            self._make_bundle("SQL", "low", 10),
        ]
        embedder = ResourceEmbedder()
        embeddings = embedder.embed(bundles)
        assert 1 <= len(embeddings) <= 3

    def test_skips_empty_phases(self):
        bundles = [self._make_bundle("Python", "critical", 1)]
        embedder = ResourceEmbedder()
        embeddings = embedder.embed(bundles)
        # Only phase 1 should be present
        assert len(embeddings) == 1
        assert embeddings[0].phase_number == 1

    def test_phase_contains_correct_gaps(self):
        bundles = [
            self._make_bundle("Python", "critical", 1),
            self._make_bundle("ML", "critical", 2),
        ]
        embedder = ResourceEmbedder()
        embeddings = embedder.embed(bundles)
        assert "Python" in embeddings[0].skill_gaps
        assert "ML" in embeddings[0].skill_gaps

    def test_respects_resources_per_phase(self):
        bundles = [self._make_bundle("Python", "high", 1, n_resources=10)]
        embedder = ResourceEmbedder(resources_per_phase=3)
        embeddings = embedder.embed(bundles)
        assert len(embeddings[0].resources) <= 3

    def test_deduplicates_resources_within_phase(self):
        shared_resource = LearningResource(
            resource_id="shared-001", title="Shared Course", provider="X",
            skill_tags=["python"], level=ResourceLevel.INTERMEDIATE, format=ResourceFormat.COURSE,
            duration_hours=10.0, cost_usd=0.0, quality_score=0.9, relevance_score=0.9,
            overall_score=0.85, is_free=True,
        )
        bundles = [
            SkillResourceBundle("Python", "critical", 1, [shared_resource]),
            SkillResourceBundle("ML", "critical", 2, [shared_resource]),
        ]
        embedder = ResourceEmbedder()
        embeddings = embedder.embed(bundles)
        ids = [r.resource_id for r in embeddings[0].resources]
        assert ids.count("shared-001") == 1


# ── CourseFetcher tests ───────────────────────────────────────────────────────


class TestInferSearchLevel:
    def test_expert_current_returns_advanced(self):
        assert _infer_search_level({"current_level": "expert", "severity": "low"}) == "advanced"

    def test_beginner_current_returns_intermediate(self):
        assert _infer_search_level({"current_level": "beginner", "severity": "high"}) == "intermediate"

    def test_no_level_critical_returns_beginner(self):
        assert _infer_search_level({"current_level": None, "severity": "critical"}) == "beginner"

    def test_no_level_high_returns_intermediate(self):
        assert _infer_search_level({"current_level": None, "severity": "high"}) == "intermediate"

    def test_intermediate_low_returns_advanced(self):
        assert _infer_search_level({"current_level": "intermediate", "severity": "low"}) == "advanced"


class TestCourseFetcher:
    @pytest.mark.asyncio
    async def test_returns_courses_per_gap(self):
        fetcher = CourseFetcher(StubMCPClient())
        gaps = [
            {"requirement_name": "Python", "dimension": "tech_skill", "severity": "high",
             "current_level": None, "priority_rank": 1},
        ]
        result = await fetcher.fetch(gaps, correlation_id="test")
        assert "Python" in result
        assert len(result["Python"]) > 0

    @pytest.mark.asyncio
    async def test_non_tech_gaps_get_empty_list(self):
        fetcher = CourseFetcher(StubMCPClient())
        gaps = [
            {"requirement_name": "Leadership", "dimension": "soft_skill", "severity": "medium",
             "current_level": None, "priority_rank": 1},
        ]
        result = await fetcher.fetch(gaps, correlation_id="test")
        # soft_skill not in _SKILL_DIMENSIONS, so no MCP call → empty list
        assert result["Leadership"] == []

    @pytest.mark.asyncio
    async def test_tolerates_partial_failures(self):
        """A failing MCP call for one skill should not abort the others."""
        failing_client = MagicMock()
        call_count = 0

        async def flaky_call(server_id, tool, params, *, correlation_id=""):
            nonlocal call_count
            call_count += 1
            if params.get("skill") == "Python":
                raise RuntimeError("MCP timeout")
            return {"courses": [{"id": "k8s-001", "title": "K8s Intro",
                                  "provider": "KodeKloud", "skill_tags": ["kubernetes"],
                                  "level": "beginner", "format": "course",
                                  "duration_hours": 6.0, "cost_usd": 0.0, "quality_score": 0.9}]}

        failing_client.call = flaky_call
        fetcher = CourseFetcher(failing_client)
        gaps = [
            {"requirement_name": "Python", "dimension": "tech_skill", "severity": "high",
             "current_level": None, "priority_rank": 1},
            {"requirement_name": "Kubernetes", "dimension": "tech_skill", "severity": "high",
             "current_level": None, "priority_rank": 2},
        ]
        result = await fetcher.fetch(gaps, correlation_id="test")
        # Python failed → empty, Kubernetes succeeded
        assert result["Python"] == []
        assert len(result["Kubernetes"]) == 1


# ── LearningAgent full-pipeline tests ────────────────────────────────────────


class TestLearningAgentRun:
    @pytest.mark.asyncio
    async def test_successful_run_returns_completed(self, sample_context: AgentContext):
        agent = LearningAgent(mcp_client=StubMCPClient())
        result = await agent.run(sample_context)
        assert result.status == AgentResultStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_output_has_required_keys(self, sample_context: AgentContext):
        agent = LearningAgent(mcp_client=StubMCPClient())
        result = await agent.run(sample_context)
        output = result.output
        assert output is not None
        assert "target_role" in output
        assert "skill_recommendations" in output
        assert "top_resources" in output
        assert "roadmap_embeddings" in output
        assert "total_resources_found" in output
        assert "total_learning_hours" in output
        assert "processing_steps" in output
        assert "fetched_at" in output
        assert "data_sources" in output

    @pytest.mark.asyncio
    async def test_processing_steps_are_all_present(self, sample_context: AgentContext):
        agent = LearningAgent(mcp_client=StubMCPClient())
        result = await agent.run(sample_context)
        steps = result.output["processing_steps"]
        assert "course_fetching" in steps
        assert "resource_matching" in steps
        assert "resource_ranking" in steps
        assert "resource_embedding" in steps

    @pytest.mark.asyncio
    async def test_agent_type_is_learning_resources(self):
        agent = LearningAgent(mcp_client=StubMCPClient())
        assert agent.agent_type == AgentType.LEARNING_RESOURCES

    @pytest.mark.asyncio
    async def test_emits_progress_events(self, sample_context: AgentContext):
        publisher = MagicMock()
        publisher.emit = MagicMock()
        agent = LearningAgent(mcp_client=StubMCPClient(), event_publisher=publisher)
        await agent.run(sample_context)
        assert publisher.emit.call_count >= 4  # one per pipeline step

    @pytest.mark.asyncio
    async def test_progress_event_emit_failure_does_not_raise(self, sample_context: AgentContext):
        publisher = MagicMock()
        publisher.emit = MagicMock(side_effect=RuntimeError("Redis down"))
        agent = LearningAgent(mcp_client=StubMCPClient(), event_publisher=publisher)
        result = await agent.run(sample_context)
        assert result.status == AgentResultStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_max_gaps_respected(self, sample_context: AgentContext):
        agent = LearningAgent(mcp_client=StubMCPClient(), max_gaps=1)
        result = await agent.run(sample_context)
        recs = result.output["skill_recommendations"]
        assert len(recs) <= 1

    @pytest.mark.asyncio
    async def test_fallback_to_profile_skills_when_no_gap_analysis(self):
        profile = UserProfileSnapshot(
            target_role="Data Scientist",
            skills=["Python", "SQL"],
        )
        ctx = AgentContext(
            task_id="task-002", session_id="sess-002", user_id="user-002",
            correlation_id="corr-002", stream_channel="ch-002",
            user_profile=profile,
            plan_snapshot={},  # no gap_analysis
        )
        agent = LearningAgent(mcp_client=StubMCPClient())
        result = await agent.run(ctx)
        assert result.status == AgentResultStatus.COMPLETED
        assert len(result.output["skill_recommendations"]) >= 1

    @pytest.mark.asyncio
    async def test_resource_scores_are_in_valid_range(self, sample_context: AgentContext):
        agent = LearningAgent(mcp_client=StubMCPClient())
        result = await agent.run(sample_context)
        for resource_dict in result.output["top_resources"]:
            assert 0.0 <= resource_dict["overall_score"] <= 1.0
            assert 0.0 <= resource_dict["quality_score"] <= 1.0
            assert 0.0 <= resource_dict["relevance_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_roadmap_embeddings_have_phase_titles(self, sample_context: AgentContext):
        agent = LearningAgent(mcp_client=StubMCPClient())
        result = await agent.run(sample_context)
        for embedding in result.output["roadmap_embeddings"]:
            assert embedding["phase_title"] != ""
            assert embedding["phase_number"] in (1, 2, 3)
            assert isinstance(embedding["estimated_hours"], float)

    @pytest.mark.asyncio
    async def test_mcp_failure_still_produces_output(self):
        """If MCP entirely fails, pipeline continues with empty resource lists."""
        always_fail = MagicMock()
        always_fail.call = AsyncMock(side_effect=RuntimeError("MCP unavailable"))
        agent = LearningAgent(mcp_client=always_fail)
        profile = UserProfileSnapshot(target_role="Engineer", skills=["Python"])
        ctx = AgentContext(
            task_id="task-003", session_id="sess-003", user_id="user-003",
            correlation_id="corr-003", stream_channel="ch-003",
            user_profile=profile,
            plan_snapshot={
                "gap_analysis": {
                    "prioritised_gaps": [
                        {"requirement_name": "Python", "dimension": "tech_skill",
                         "severity": "high", "priority_rank": 1, "current_level": None,
                         "required_level": "intermediate", "is_required": True, "diff_score": 0.5},
                    ]
                }
            },
        )
        result = await agent.run(ctx)
        assert result.status == AgentResultStatus.COMPLETED
        assert result.output["total_resources_found"] == 0


# ── Serialiser tests ──────────────────────────────────────────────────────────


class TestSerialisers:
    def test_serialise_resource_has_all_fields(self, sample_resource: LearningResource):
        d = _serialise_resource(sample_resource)
        expected_keys = {
            "resource_id", "title", "provider", "skill_tags", "level", "format",
            "duration_hours", "cost_usd", "is_free", "quality_score",
            "relevance_score", "overall_score", "url", "description",
            "freshness_year", "source",
        }
        assert expected_keys == set(d.keys())

    def test_serialise_resource_level_is_string(self, sample_resource: LearningResource):
        d = _serialise_resource(sample_resource)
        assert isinstance(d["level"], str)
        assert d["level"] == "beginner"

    def test_serialise_bundle_has_top_resource(self, sample_bundle: SkillResourceBundle):
        d = _serialise_bundle(sample_bundle)
        assert "top_resource" in d
        assert d["top_resource"] is not None

    def test_serialise_bundle_empty_resources_gives_null_top(self):
        bundle = SkillResourceBundle("skill", "medium", 5, [])
        d = _serialise_bundle(bundle)
        assert d["top_resource"] is None


# ── Helpers tests ─────────────────────────────────────────────────────────────


class TestHelpers:
    def test_resolve_gaps_returns_gap_analysis_when_present(self, sample_context: AgentContext):
        gaps = _resolve_gaps(
            sample_context.plan_snapshot["gap_analysis"], sample_context
        )
        assert len(gaps) == 3
        assert gaps[0]["requirement_name"] == "Python"

    def test_resolve_gaps_fallback_uses_profile_skills(self):
        profile = UserProfileSnapshot(target_role="Engineer", skills=["Python", "Docker"])
        ctx = AgentContext(
            task_id="t", session_id="s", user_id="u", correlation_id="c",
            stream_channel="ch", user_profile=profile, plan_snapshot={},
        )
        gaps = _resolve_gaps({}, ctx)
        assert len(gaps) == 2
        assert gaps[0]["requirement_name"] == "Python"
        assert gaps[0]["severity"] == "medium"

    def test_collect_data_sources_deduplicates(self, sample_bundle: SkillResourceBundle):
        sources = _collect_data_sources([sample_bundle, sample_bundle])
        assert sources.count("Coursera") <= 1
