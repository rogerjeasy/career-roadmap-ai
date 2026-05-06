"""Tests for TaskPlanner — DAG construction, phase assignment, retry policies."""
from __future__ import annotations

import pytest

from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.orchestrator.task_planner import (
    TaskPlanner,
    _compute_phases,
    _AGENT_SPECS,
    _DAG_TEMPLATES,
    _DEFAULT_INTENT,
)
from agents.orchestrator.state import TaskNode


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def planner() -> TaskPlanner:
    return TaskPlanner()


@pytest.fixture
def empty_profile() -> UserProfileSnapshot:
    return UserProfileSnapshot()


@pytest.fixture
def full_profile() -> UserProfileSnapshot:
    return UserProfileSnapshot(
        target_role="ML Engineer",
        current_role="Backend Developer",
        skills=["Python"],
        location="Berlin",
        timeline_months=12,
        weekly_hours_available=10,
        salary_goal=120_000,
    )


# ── _compute_phases ───────────────────────────────────────────────────────────


class TestComputePhases:
    def test_no_deps_is_phase_1(self) -> None:
        template = [(AgentType.CV_ANALYSIS, []), (AgentType.MARKET_INTELLIGENCE, [])]
        phases = _compute_phases(template)
        assert phases[AgentType.CV_ANALYSIS] == 1
        assert phases[AgentType.MARKET_INTELLIGENCE] == 1

    def test_dep_on_phase_1_is_phase_2(self) -> None:
        template = [
            (AgentType.CV_ANALYSIS, []),
            (AgentType.GAP_ANALYSIS, [AgentType.CV_ANALYSIS]),
        ]
        phases = _compute_phases(template)
        assert phases[AgentType.GAP_ANALYSIS] == 2

    def test_full_roadmap_template_phases(self) -> None:
        template = _DAG_TEMPLATES["roadmap_generation"]
        phases = _compute_phases(template)
        assert phases[AgentType.CV_ANALYSIS] == 1
        assert phases[AgentType.MARKET_INTELLIGENCE] == 1
        assert phases[AgentType.GAP_ANALYSIS] == 2
        assert phases[AgentType.ROADMAP_GENERATION] == 3
        assert phases[AgentType.LEARNING_RESOURCES] == 4
        assert phases[AgentType.NETWORKING] == 4
        assert phases[AgentType.OPPORTUNITY] == 4


# ── TaskPlanner.build() ───────────────────────────────────────────────────────


class TestTaskPlannerBuild:
    def test_roadmap_generation_returns_all_agents(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-1")
        agent_types = {n["agent_type"] for n in dag}
        assert AgentType.CV_ANALYSIS in agent_types
        assert AgentType.GAP_ANALYSIS in agent_types
        assert AgentType.ROADMAP_GENERATION in agent_types
        assert AgentType.LEARNING_RESOURCES in agent_types

    def test_coach_query_returns_only_coach(
        self, planner: TaskPlanner, empty_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("coach_query", empty_profile, "corr-2")
        assert len(dag) == 1
        assert dag[0]["agent_type"] == AgentType.COACH

    def test_market_query_returns_only_market(
        self, planner: TaskPlanner, empty_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("market_query", empty_profile, "corr-3")
        assert dag[0]["agent_type"] == AgentType.MARKET_INTELLIGENCE

    def test_unknown_intent_falls_back_to_roadmap(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("non_existent_intent", full_profile, "corr-4")
        agent_types = {n["agent_type"] for n in dag}
        assert AgentType.ROADMAP_GENERATION in agent_types

    def test_nodes_have_retry_policy(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-5")
        for node in dag:
            policy = node["retry_policy"]
            assert "max_attempts" in policy
            assert "timeout_seconds" in policy
            assert "backoff_seconds" in policy
            assert policy["max_attempts"] >= 1
            assert policy["timeout_seconds"] > 0

    def test_nodes_have_is_required_flag(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-6")
        for node in dag:
            assert isinstance(node["is_required"], bool)

    def test_nodes_have_phase_number(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-7")
        for node in dag:
            assert isinstance(node["phase"], int)
            assert node["phase"] >= 1

    def test_required_agents_in_roadmap(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-8")
        required = {n["agent_type"] for n in dag if n["is_required"]}
        assert AgentType.CV_ANALYSIS in required
        assert AgentType.GAP_ANALYSIS in required
        assert AgentType.ROADMAP_GENERATION in required

    def test_optional_agents_in_roadmap(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-9")
        optional = {n["agent_type"] for n in dag if not n["is_required"]}
        assert AgentType.MARKET_INTELLIGENCE in optional
        assert AgentType.NETWORKING in optional

    def test_task_ids_are_unique(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-10")
        ids = [n["task_id"] for n in dag]
        assert len(ids) == len(set(ids))

    def test_task_ids_contain_correlation_id(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "my-corr-id")
        for node in dag:
            assert "my-corr-id" in node["task_id"]

    def test_progress_skipped_without_existing_plan(
        self, planner: TaskPlanner
    ) -> None:
        profile = UserProfileSnapshot()
        dag = planner.build("progress_review", profile, "corr-11")
        types = [n["agent_type"] for n in dag]
        assert AgentType.PROGRESS not in types

    def test_progress_included_with_existing_plan(
        self, planner: TaskPlanner
    ) -> None:
        profile = UserProfileSnapshot(additional={"has_existing_plan": True})
        dag = planner.build("progress_review", profile, "corr-12")
        types = [n["agent_type"] for n in dag]
        assert AgentType.PROGRESS in types

    def test_depends_on_uses_task_ids(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("cv_review", full_profile, "corr-13")
        gap = next(n for n in dag if n["agent_type"] == AgentType.GAP_ANALYSIS)
        cv = next(n for n in dag if n["agent_type"] == AgentType.CV_ANALYSIS)
        assert cv["task_id"] in gap["depends_on"]

    def test_phase_order_consistent_with_deps(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-14")
        node_map = {n["task_id"]: n for n in dag}
        for node in dag:
            for dep_id in node["depends_on"]:
                if dep_id in node_map:
                    assert node_map[dep_id]["phase"] < node["phase"]

    def test_roadmap_generation_max_phase_is_4(
        self, planner: TaskPlanner, full_profile: UserProfileSnapshot
    ) -> None:
        dag = planner.build("roadmap_generation", full_profile, "corr-15")
        assert max(n["phase"] for n in dag) == 4


# ── _AGENT_SPECS ──────────────────────────────────────────────────────────────


class TestAgentSpecs:
    def test_all_known_agent_types_have_spec(self) -> None:
        for agent_type in AgentType:
            assert agent_type in _AGENT_SPECS, f"Missing spec for {agent_type}"

    def test_specs_have_required_keys(self) -> None:
        for agent_type, spec in _AGENT_SPECS.items():
            assert "is_required" in spec, agent_type
            assert "retry_policy" in spec, agent_type
            policy = spec["retry_policy"]
            assert "max_attempts" in policy, agent_type
            assert "timeout_seconds" in policy, agent_type
            assert "backoff_seconds" in policy, agent_type

    def test_required_agents_are_boolean(self) -> None:
        for spec in _AGENT_SPECS.values():
            assert isinstance(spec["is_required"], bool)

    def test_max_attempts_at_least_1(self) -> None:
        for spec in _AGENT_SPECS.values():
            assert spec["retry_policy"]["max_attempts"] >= 1

    def test_timeout_positive(self) -> None:
        for spec in _AGENT_SPECS.values():
            assert spec["retry_policy"]["timeout_seconds"] > 0
