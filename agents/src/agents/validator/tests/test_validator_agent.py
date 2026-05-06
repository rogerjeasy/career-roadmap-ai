"""Tests for Validator / Critic Agent — four-stage validation pipeline.

All LLM calls are mocked. No network required.

Coverage:
  - EvidenceChecker: coverage score computation, fallback on LLM error
  - ClaimAuditor: grounding score, unsupported claim extraction, fallback
  - RealismAssessor: deterministic pre-check, LLM assessment, fallback
  - FixInstructor: instruction generation, fallback, empty-issue short-circuit
  - ValidatorAgent: full pipeline, concurrent stages, pass/fail logic, metrics
"""
from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.validator.claim_auditor import ClaimAuditor
from agents.validator.evidence_checker import EvidenceChecker, _extract_claims
from agents.validator.fix_instructor import FixInstructor, _fallback_instructions
from agents.validator.models import (
    CheckStatus,
    EvidenceCheck,
    FixInstruction,
    FixPriority,
    RealismIssue,
    UnsupportedClaim,
    ValidationResult,
)
from agents.validator.realism_assessor import RealismAssessor, _deterministic_check
from agents.validator.validator_agent import (
    _EVIDENCE_THRESHOLD,
    _GROUNDING_THRESHOLD,
    _OVERALL_THRESHOLD,
    _REALISM_THRESHOLD,
    _score_to_status,
    ValidatorAgent,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


def _r(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _roadmap() -> dict:
    return {
        "summary": "Become an ML Engineer in 12 months.",
        "phases": [
            {
                "title": "Phase 1: Python & ML Fundamentals",
                "duration_weeks": 8,
                "skills_to_acquire": ["PyTorch", "scikit-learn"],
                "milestones": ["Complete fast.ai", "Build first model"],
                "market_relevance": "Python is the dominant language in ML.",
            },
            {
                "title": "Phase 2: Deep Learning",
                "duration_weeks": 12,
                "skills_to_acquire": ["TensorFlow", "MLflow"],
                "milestones": ["Train CNN on CIFAR-10"],
                "market_relevance": "Deep learning demand up 40% YoY.",
            },
        ],
    }


def _agent_outputs() -> dict:
    return {
        "cv_analysis": {"skills": ["Python", "SQL"]},
        "gap_analysis": {"gaps": [{"name": "PyTorch"}, {"name": "MLflow"}]},
        "market_intelligence": {"trending_skills": ["Python", "TensorFlow"]},
    }


def _user_profile_snapshot(**overrides) -> UserProfileSnapshot:
    defaults = dict(
        target_role="ML Engineer",
        current_role="Backend Engineer",
        skills=["Python", "SQL"],
        timeline_months=12,
        weekly_hours_available=15,
    )
    defaults.update(overrides)
    return UserProfileSnapshot(**defaults)


def _context(roadmap: dict | None = None, **profile_overrides) -> AgentContext:
    snapshot: dict = {
        "draft_roadmap": roadmap if roadmap is not None else _roadmap(),
        **_agent_outputs(),
    }
    return AgentContext(
        task_id="task-001",
        session_id="sess-001",
        user_id="user-001",
        correlation_id="corr-001",
        stream_channel="ch-001",
        user_profile=_user_profile_snapshot(**profile_overrides),
        plan_snapshot=snapshot,
    )


# ── ValidationResult ───────────────────────────────────────────────────────────


class TestValidationResult:
    def test_to_dict_is_json_serialisable(self) -> None:
        result = ValidationResult(
            passed=True,
            overall_score=0.85,
            evidence_coverage_score=0.9,
            grounding_score=0.8,
            realism_score=0.85,
        )
        json.dumps(result.to_dict())  # must not raise

    def test_fix_instructions_serialised_as_dicts(self) -> None:
        fix = FixInstruction(
            issue_id="fix_001",
            priority=FixPriority.HIGH,
            category="timeline",
            description="Too fast",
            suggested_action="Slow down",
            roadmap_location="phases[0]",
        )
        result = ValidationResult(
            passed=False,
            overall_score=0.5,
            evidence_coverage_score=0.7,
            grounding_score=0.6,
            realism_score=0.4,
            fix_instructions=[fix],
        )
        d = result.to_dict()
        assert isinstance(d["fix_instructions"][0], dict)
        assert d["fix_instructions"][0]["priority"] == "high"


# ── _score_to_status ───────────────────────────────────────────────────────────


class TestScoreToStatus:
    def test_passed_at_threshold(self) -> None:
        assert _score_to_status(0.70, 0.70) == CheckStatus.PASSED

    def test_degraded_below_threshold(self) -> None:
        assert _score_to_status(0.55, 0.70) == CheckStatus.DEGRADED

    def test_failed_well_below_threshold(self) -> None:
        assert _score_to_status(0.20, 0.70) == CheckStatus.FAILED


# ── _extract_claims ────────────────────────────────────────────────────────────


class TestExtractClaims:
    def test_extracts_skills_and_milestones(self) -> None:
        claims = _extract_claims(_roadmap())
        assert any("PyTorch" in c for c in claims)
        assert any("TensorFlow" in c for c in claims)
        assert any("fast.ai" in c for c in claims)

    def test_extracts_summary(self) -> None:
        claims = _extract_claims(_roadmap())
        assert any("Summary" in c for c in claims)

    def test_caps_at_40_claims(self) -> None:
        large_roadmap = {
            "phases": [
                {"skills_to_acquire": [f"skill_{i}" for i in range(50)]}
            ]
        }
        claims = _extract_claims(large_roadmap)
        assert len(claims) <= 40

    def test_empty_roadmap_returns_empty(self) -> None:
        assert _extract_claims({}) == []


# ── EvidenceChecker ────────────────────────────────────────────────────────────


class TestEvidenceChecker:
    @pytest.fixture
    def checker(self, mock_llm: AsyncMock) -> EvidenceChecker:
        return EvidenceChecker(llm=mock_llm)

    async def test_returns_checks_and_score(
        self, checker: EvidenceChecker, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            json.dumps({
                "coverage_score": 0.8,
                "checks": [
                    {"claim": "Learn: PyTorch", "is_grounded": True,
                     "evidence_ref": "gap_analysis.gaps[0]", "confidence": 0.9},
                    {"claim": "Learn: TensorFlow", "is_grounded": False,
                     "evidence_ref": None, "confidence": 0.4},
                ],
            })
        )
        checks, score = await checker.check(_agent_outputs(), _roadmap())
        assert score == pytest.approx(0.8)
        assert len(checks) == 2
        assert checks[0].is_grounded is True
        assert checks[1].is_grounded is False

    async def test_score_clamped(
        self, checker: EvidenceChecker, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"coverage_score": 1.5, "checks": []}'
        )
        _, score = await checker.check(_agent_outputs(), _roadmap())
        assert score == pytest.approx(1.0)

    async def test_fallback_on_error_marks_all_grounded(
        self, checker: EvidenceChecker, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("LLM error")
        checks, score = await checker.check(_agent_outputs(), _roadmap())
        assert score == pytest.approx(1.0)
        assert all(c.is_grounded for c in checks)
        assert all(c.confidence == pytest.approx(0.5) for c in checks)

    async def test_empty_roadmap_returns_empty(
        self, checker: EvidenceChecker
    ) -> None:
        checks, score = await checker.check({}, {})
        assert checks == []
        assert score == pytest.approx(1.0)
        # No LLM call should have been made
        checker._llm.ainvoke.assert_not_called()  # type: ignore[attr-defined]


# ── ClaimAuditor ───────────────────────────────────────────────────────────────


class TestClaimAuditor:
    @pytest.fixture
    def auditor(self, mock_llm: AsyncMock) -> ClaimAuditor:
        return ClaimAuditor(llm=mock_llm)

    async def test_returns_claims_and_score(
        self, auditor: ClaimAuditor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            json.dumps({
                "grounding_score": 0.75,
                "unsupported_claims": [
                    {"claim": "Salary $200k",
                     "roadmap_location": "summary",
                     "severity": "critical"},
                ],
            })
        )
        claims, score = await auditor.audit(_agent_outputs(), _roadmap())
        assert score == pytest.approx(0.75)
        assert len(claims) == 1
        assert claims[0].severity == FixPriority.CRITICAL
        assert claims[0].roadmap_location == "summary"

    async def test_score_clamped_low(
        self, auditor: ClaimAuditor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"grounding_score": -0.5, "unsupported_claims": []}'
        )
        _, score = await auditor.audit({}, {})
        assert score == pytest.approx(0.0)

    async def test_fallback_on_error_returns_empty(
        self, auditor: ClaimAuditor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("network error")
        claims, score = await auditor.audit({}, _roadmap())
        assert claims == []
        assert score == pytest.approx(1.0)

    async def test_unknown_severity_defaults_to_low(
        self, auditor: ClaimAuditor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            json.dumps({
                "grounding_score": 0.9,
                "unsupported_claims": [
                    {"claim": "x", "roadmap_location": "phases[0]", "severity": "unknown_value"},
                ],
            })
        )
        claims, _ = await auditor.audit({}, _roadmap())
        assert claims[0].severity == FixPriority.LOW


# ── _deterministic_check ───────────────────────────────────────────────────────


class TestDeterministicCheck:
    def test_critical_timeline_overshoot(self) -> None:
        phases = [{"duration_weeks": 26, "skills_to_acquire": []}]  # ~6 months
        issues = _deterministic_check(phases, {"timeline_months": 3, "weekly_hours_available": 10})
        assert any(i.severity == FixPriority.CRITICAL for i in issues)

    def test_high_timeline_overshoot(self) -> None:
        phases = [{"duration_weeks": 14, "skills_to_acquire": []}]  # ~3.2 months
        issues = _deterministic_check(phases, {"timeline_months": 2, "weekly_hours_available": 10})
        assert any(i.severity == FixPriority.HIGH for i in issues)

    def test_no_issue_within_budget(self) -> None:
        phases = [{"duration_weeks": 8, "skills_to_acquire": []}]  # ~1.8 months
        issues = _deterministic_check(phases, {"timeline_months": 3, "weekly_hours_available": 10})
        assert all(i.phase_index is None for i in issues)  # no timeline issue
        # May have no issues at all
        assert len(issues) == 0

    def test_per_phase_overload_flagged(self) -> None:
        # 10 skills, 1 week, 5h/week → 5h available vs 80h needed
        phases = [{"duration_weeks": 1, "skills_to_acquire": [f"s{i}" for i in range(10)]}]
        issues = _deterministic_check(phases, {"timeline_months": None, "weekly_hours_available": 5})
        assert any(i.phase_index == 0 for i in issues)

    def test_no_check_without_weekly_hours(self) -> None:
        phases = [{"duration_weeks": 1, "skills_to_acquire": ["s1", "s2", "s3", "s4"]}]
        issues = _deterministic_check(phases, {"timeline_months": None, "weekly_hours_available": None})
        assert issues == []


# ── RealismAssessor ────────────────────────────────────────────────────────────


class TestRealismAssessor:
    @pytest.fixture
    def assessor(self, mock_llm: AsyncMock) -> RealismAssessor:
        return RealismAssessor(llm=mock_llm)

    async def test_returns_issues_and_score(
        self, assessor: RealismAssessor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            json.dumps({
                "realism_score": 0.7,
                "issues": [
                    {
                        "description": "Phase 2 too fast",
                        "phase_index": 1,
                        "severity": "high",
                        "suggested_adjustment": "Extend by 4 weeks",
                    }
                ],
            })
        )
        issues, score = await assessor.assess(
            _roadmap(), {"timeline_months": 12, "weekly_hours_available": 15}
        )
        assert score == pytest.approx(0.7)
        assert any(i.phase_index == 1 for i in issues)

    async def test_deterministic_critical_caps_llm_score(
        self, assessor: RealismAssessor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"realism_score": 0.9, "issues": []}'
        )
        # 26 weeks (~6 months) vs 3-month timeline → CRITICAL
        bad_roadmap = {"phases": [{"duration_weeks": 26, "skills_to_acquire": []}]}
        _, score = await assessor.assess(
            bad_roadmap, {"timeline_months": 3, "weekly_hours_available": 10}
        )
        assert score <= 0.3

    async def test_fallback_on_llm_error(
        self, assessor: RealismAssessor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("timeout")
        issues, score = await assessor.assess(
            _roadmap(), {"timeline_months": 12, "weekly_hours_available": 15}
        )
        # Fallback should still return a score without raising
        assert 0.0 <= score <= 1.0


# ── FixInstructor ──────────────────────────────────────────────────────────────


class TestFixInstructor:
    @pytest.fixture
    def instructor(self, mock_llm: AsyncMock) -> FixInstructor:
        return FixInstructor(llm=mock_llm)

    async def test_returns_empty_when_no_issues(
        self, instructor: FixInstructor
    ) -> None:
        result = await instructor.generate(
            [EvidenceCheck("c", True, None, 0.9)], [], []
        )
        assert result == []

    async def test_returns_fix_instructions(
        self, instructor: FixInstructor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            json.dumps([
                {
                    "issue_id": "fix_001",
                    "priority": "high",
                    "category": "unsupported_claim",
                    "description": "Salary not grounded",
                    "suggested_action": "Remove salary claim",
                    "roadmap_location": "summary",
                }
            ])
        )
        ungrounded = EvidenceCheck("Salary $200k", False, None, 0.2)
        fixes = await instructor.generate([ungrounded], [], [])
        assert len(fixes) == 1
        assert fixes[0].priority == FixPriority.HIGH
        assert fixes[0].category == "unsupported_claim"

    async def test_fallback_generates_instructions(
        self, instructor: FixInstructor, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("LLM error")
        gap = EvidenceCheck("Fake skill", False, None, 0.1)
        claim = UnsupportedClaim("Invented fact", "summary", FixPriority.CRITICAL)
        fixes = await instructor.generate([gap], [claim], [])
        assert any(f.priority == FixPriority.CRITICAL for f in fixes)
        assert any(f.category == "evidence_gap" for f in fixes)

    def test_fallback_instructions_cover_all_issue_types(self) -> None:
        gaps = [EvidenceCheck("c1", False, None, 0.3)]
        claims = [UnsupportedClaim("c2", "phases[0]", FixPriority.HIGH)]
        realism = [
            RealismIssue("Too fast", 0, FixPriority.HIGH, "Extend by 4 weeks")
        ]
        fixes = _fallback_instructions(gaps, claims, realism)
        categories = {f.category for f in fixes}
        assert "evidence_gap" in categories
        assert "unsupported_claim" in categories
        assert "timeline" in categories


# ── ValidatorAgent — full pipeline ─────────────────────────────────────────────
#
# Integration tests mock the stage methods (.check, .audit, .assess, .generate)
# directly rather than the underlying LLM.  This avoids coupling the tests to
# tenacity retry counts and asyncio.gather ordering of concurrent stages.


def _make_agent(
    *,
    evidence_result: tuple = ([], 0.9),
    audit_result: tuple = ([], 0.9),
    assess_result: tuple = ([], 0.9),
    fix_result: list | None = None,
    event_publisher=None,
) -> ValidatorAgent:
    """Build a ValidatorAgent with all stage methods replaced by AsyncMock."""
    checker = MagicMock(spec=EvidenceChecker)
    checker.check = AsyncMock(return_value=evidence_result)

    auditor = MagicMock(spec=ClaimAuditor)
    auditor.audit = AsyncMock(return_value=audit_result)

    assessor = MagicMock(spec=RealismAssessor)
    assessor.assess = AsyncMock(return_value=assess_result)

    instructor = MagicMock(spec=FixInstructor)
    instructor.generate = AsyncMock(return_value=fix_result or [])

    return ValidatorAgent(
        evidence_checker=checker,
        claim_auditor=auditor,
        realism_assessor=assessor,
        fix_instructor=instructor,
        event_publisher=event_publisher,
    )


class TestValidatorAgentFull:
    async def test_passed_roadmap(self) -> None:
        agent = _make_agent()
        result = await agent.run(_context())
        assert result.status.value == "completed"
        output = result.output
        assert output["passed"] is True
        assert output["overall_score"] > _OVERALL_THRESHOLD

    async def test_fails_on_critical_fix_instruction(self) -> None:
        critical_fix = FixInstruction(
            issue_id="fix_001",
            priority=FixPriority.CRITICAL,
            category="unsupported_claim",
            description="Fabricated salary claim",
            suggested_action="Remove it",
            roadmap_location="summary",
        )
        agent = _make_agent(fix_result=[critical_fix])
        result = await agent.run(_context())
        output = result.output
        assert output["passed"] is False
        assert any(f["priority"] == "critical" for f in output["fix_instructions"])

    async def test_fails_on_low_grounding_score(self) -> None:
        low = _GROUNDING_THRESHOLD - 0.1
        agent = _make_agent(audit_result=([], low))
        result = await agent.run(_context())
        assert result.output["passed"] is False
        assert result.output["grounding_status"] in ("degraded", "failed")

    async def test_fails_on_low_realism_score(self) -> None:
        low = _REALISM_THRESHOLD - 0.1
        agent = _make_agent(assess_result=([], low))
        result = await agent.run(_context())
        assert result.output["passed"] is False

    async def test_fails_on_low_evidence_coverage(self) -> None:
        low = _EVIDENCE_THRESHOLD - 0.1
        agent = _make_agent(evidence_result=([], low))
        result = await agent.run(_context())
        assert result.output["passed"] is False

    async def test_empty_roadmap_returns_failed(self) -> None:
        ctx = _context(roadmap={})
        checker = MagicMock(spec=EvidenceChecker)
        checker.check = AsyncMock(return_value=([], 1.0))
        agent = ValidatorAgent(evidence_checker=checker)
        result = await agent.run(ctx)
        assert result.output["passed"] is False
        assert result.output["overall_score"] == pytest.approx(0.0)
        checker.check.assert_not_called()

    async def test_output_is_json_serialisable(self) -> None:
        evidence = [EvidenceCheck("Learn: PyTorch", True, "gap_analysis.gaps[0]", 0.9)]
        claim = UnsupportedClaim("Made-up fact", "phases[0]", FixPriority.LOW)
        realism = RealismIssue("Minor overload", 0, FixPriority.LOW, "Trim 1 week")
        fix = FixInstruction("f01", FixPriority.LOW, "timeline", "desc", "action", "phases[0]")
        agent = _make_agent(
            evidence_result=(evidence, 0.9),
            audit_result=([claim], 0.85),
            assess_result=([realism], 0.78),
            fix_result=[fix],
        )
        result = await agent.run(_context())
        json.dumps(result.output)  # must not raise

    async def test_agent_type_and_display_name(self) -> None:
        agent = ValidatorAgent()
        assert agent.agent_type == AgentType.VALIDATOR
        assert agent.display_name == "Validator / Critic Agent"

    async def test_progress_events_emitted(self) -> None:
        publisher = MagicMock()
        publisher.emit = MagicMock()
        agent = _make_agent(event_publisher=publisher)
        await agent.run(_context())
        # At minimum: evidence_coverage, claim_audit_and_realism, fix_instructions
        assert publisher.emit.call_count >= 3

    async def test_progress_emit_failure_does_not_crash(self) -> None:
        broken_publisher = MagicMock()
        broken_publisher.emit.side_effect = RuntimeError("Redis unavailable")
        agent = _make_agent(event_publisher=broken_publisher)
        result = await agent.run(_context())
        assert result.output is not None

    async def test_processing_steps_recorded(self) -> None:
        agent = _make_agent()
        result = await agent.run(_context())
        steps = result.output["processing_steps"]
        assert "evidence_coverage" in steps
        assert "claim_audit" in steps
        assert "realism_assess" in steps
        assert "fix_instructions" in steps

    async def test_deterministic_realism_via_stage_output(self) -> None:
        """Deterministic CRITICAL realism issue causes the roadmap to fail."""
        critical_realism = RealismIssue(
            description="26-week roadmap vs 3-month timeline",
            phase_index=None,
            severity=FixPriority.CRITICAL,
            suggested_adjustment="Reduce to 12 weeks",
        )
        # Realism score of 0.3 because LLM was capped by deterministic check
        agent = _make_agent(assess_result=([critical_realism], 0.3))
        bad_roadmap = {
            "phases": [
                {"title": "Phase 1", "duration_weeks": 26, "skills_to_acquire": ["Go"]}
            ]
        }
        ctx = _context(roadmap=bad_roadmap, timeline_months=3, weekly_hours_available=10)
        result = await agent.run(ctx)
        assert result.output["realism_score"] == pytest.approx(0.3)
        assert result.output["passed"] is False

    async def test_stages_2_and_3_both_contribute_to_output(self) -> None:
        unsupported = UnsupportedClaim("Fake claim", "phases[0]", FixPriority.HIGH)
        realism = RealismIssue("Too fast", 0, FixPriority.HIGH, "Extend by 4 weeks")
        agent = _make_agent(
            audit_result=([unsupported], 0.75),
            assess_result=([realism], 0.72),
        )
        result = await agent.run(_context())
        assert len(result.output["unsupported_claims"]) == 1
        assert len(result.output["realism_issues"]) == 1

    async def test_overall_score_weighted_correctly(self) -> None:
        # evidence=0.8 (weight 0.35) + grounding=0.7 (weight 0.40) + realism=0.9 (weight 0.25)
        # = 0.28 + 0.28 + 0.225 = 0.785
        agent = _make_agent(
            evidence_result=([], 0.8),
            audit_result=([], 0.7),
            assess_result=([], 0.9),
        )
        result = await agent.run(_context())
        assert result.output["overall_score"] == pytest.approx(0.785, abs=0.01)
