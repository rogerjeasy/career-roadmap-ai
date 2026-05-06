"""Tests for OutputValidator — three-stage validation pipeline.

All LLM calls are mocked. No network required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.contracts.results import AgentResult, AgentResultStatus
from agents.orchestrator.output_validator import (
    _GROUNDING_THRESHOLD,
    _failed_report,
    OutputValidator,
    StepConfidence,
    ValidationReport,
    make_output_validator,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def validator(mock_llm: AsyncMock) -> OutputValidator:
    return OutputValidator(llm=mock_llm)


def _r(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _completed(agent_type: str, output: dict) -> AgentResult:
    return AgentResult(
        task_id="t1",
        agent_type=agent_type,
        status=AgentResultStatus.COMPLETED,
        output=output,
    )


def _roadmap() -> dict:
    return {
        "summary": "Backend to ML Engineer in 12 months.",
        "phases": [
            {
                "title": "Phase 1: Python & ML Fundamentals",
                "duration_weeks": 8,
                "milestones": ["Complete fast.ai", "Build first model"],
                "skills_to_gain": ["PyTorch", "scikit-learn"],
            },
            {
                "title": "Phase 2: Deep Learning",
                "duration_weeks": 12,
                "milestones": ["Train CNN", "Kaggle competition"],
                "skills_to_gain": ["TensorFlow", "MLflow"],
            },
        ],
        "weekly_habits": ["Study 10h/week"],
        "next_steps": ["Enrol in fast.ai"],
        "confidence": 0.8,
    }


def _agent_results() -> dict[str, AgentResult]:
    return {
        "cv_analysis": _completed("cv_analysis", {"skills": ["Python", "SQL"]}),
        "gap_analysis": _completed("gap_analysis", {"gaps": ["PyTorch", "MLflow"]}),
    }


# ── ValidationReport.to_dict() ────────────────────────────────────────────────


class TestValidationReport:
    def test_to_dict_is_json_serialisable(self) -> None:
        report = ValidationReport(
            realism_passed=True, coherence_passed=True, stage1_notes=[],
            grounding_score=0.9, unverified_claims=[],
            step_confidences=[StepConfidence(0, "Phase 1", 0.8, "Good")],
            mean_step_confidence=0.8, passed=True, notes=[],
            validation_duration_ms=500,
        )
        json.dumps(report.to_dict())  # must not raise

    def test_step_confidences_serialised_as_dicts(self) -> None:
        sc = StepConfidence(0, "Phase 1", 0.9, "Excellent")
        report = ValidationReport(
            realism_passed=True, coherence_passed=True, stage1_notes=[],
            grounding_score=1.0, unverified_claims=[],
            step_confidences=[sc], mean_step_confidence=0.9,
            passed=True, notes=[], validation_duration_ms=100,
        )
        d = report.to_dict()
        assert isinstance(d["step_confidences"][0], dict)
        assert d["step_confidences"][0]["confidence"] == pytest.approx(0.9)


# ── _failed_report ────────────────────────────────────────────────────────────


class TestFailedReport:
    def test_all_fields_set_correctly(self) -> None:
        import time
        report = _failed_report(["bad timeline"], time.monotonic())
        assert report.passed is False
        assert report.realism_passed is False
        assert report.coherence_passed is False
        assert report.grounding_score == pytest.approx(0.0)
        assert report.step_confidences == []


# ── Stage 1 ───────────────────────────────────────────────────────────────────


class TestStage1:
    async def test_passed_when_llm_confirms(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"realism_passed": true, "coherence_passed": true, "notes": []}'
        )
        r, c, notes = await validator._stage1_realism(_roadmap())
        assert r is True and c is True and notes == []

    async def test_failed_realism(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"realism_passed": false, "coherence_passed": true, '
            '"notes": ["Timeline too short"]}'
        )
        r, c, notes = await validator._stage1_realism(_roadmap())
        assert r is False
        assert "Timeline too short" in notes

    async def test_fallback_permissive_on_error(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("LLM unavailable")
        r, c, notes = await validator._stage1_realism(_roadmap())
        assert r is True and c is True

    async def test_notes_capped_at_3(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"realism_passed": false, "coherence_passed": false, '
            '"notes": ["n1","n2","n3","n4","n5"]}'
        )
        _, _, notes = await validator._stage1_realism(_roadmap())
        assert len(notes) <= 3


# ── Stage 2 ───────────────────────────────────────────────────────────────────


class TestStage2:
    async def test_returns_score_and_claims(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"grounding_score": 0.75, "unverified_claims": ["invented salary"]}'
        )
        score, claims = await validator._stage2_grounding({}, _roadmap())
        assert score == pytest.approx(0.75)
        assert "invented salary" in claims

    async def test_score_clamped_high(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"grounding_score": 2.0, "unverified_claims": []}'
        )
        score, _ = await validator._stage2_grounding({}, _roadmap())
        assert score == pytest.approx(1.0)

    async def test_score_clamped_low(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"grounding_score": -0.5, "unverified_claims": []}'
        )
        score, _ = await validator._stage2_grounding({}, _roadmap())
        assert score == pytest.approx(0.0)

    async def test_fallback_on_error(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("parse error")
        score, claims = await validator._stage2_grounding({}, _roadmap())
        assert score == pytest.approx(1.0) and claims == []


# ── Stage 3 ───────────────────────────────────────────────────────────────────


class TestStage3:
    async def test_returns_per_phase_confidence(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '[{"phase_index": 0, "phase_title": "Phase 1", "confidence": 0.9, "reasoning": "Solid"},'
            ' {"phase_index": 1, "phase_title": "Phase 2", "confidence": 0.7, "reasoning": "OK"}]'
        )
        result = await validator._stage3_step_confidence(_roadmap())
        assert len(result) == 2
        assert isinstance(result[0], StepConfidence)
        assert result[0].confidence == pytest.approx(0.9)

    async def test_empty_when_no_phases(self, validator: OutputValidator) -> None:
        result = await validator._stage3_step_confidence({})
        assert result == []

    async def test_fallback_returns_default_0_5(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("LLM error")
        result = await validator._stage3_step_confidence(_roadmap())
        assert len(result) == 2
        assert all(s.confidence == pytest.approx(0.5) for s in result)

    async def test_confidence_clamped(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '[{"phase_index": 0, "phase_title": "P", "confidence": 99.9, "reasoning": ""}]'
        )
        result = await validator._stage3_step_confidence({"phases": [{"title": "P"}]})
        assert result[0].confidence == pytest.approx(1.0)


# ── Full validate() ───────────────────────────────────────────────────────────


class TestValidate:
    async def test_passed_roadmap(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = [
            _r('{"realism_passed": true, "coherence_passed": true, "notes": []}'),
            _r('{"grounding_score": 0.9, "unverified_claims": []}'),
            _r('[{"phase_index": 0, "phase_title": "P1", "confidence": 0.85, "reasoning": ""},'
               ' {"phase_index": 1, "phase_title": "P2", "confidence": 0.75, "reasoning": ""}]'),
        ]
        report = await validator.validate(
            _agent_results(), _roadmap(), session_id="s1", correlation_id="c1"
        )
        assert report.passed is True
        assert report.grounding_score == pytest.approx(0.9)
        assert len(report.step_confidences) == 2
        assert report.mean_step_confidence == pytest.approx(0.8)

    async def test_early_exit_skips_stages_2_and_3(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _r(
            '{"realism_passed": false, "coherence_passed": false, "notes": ["bad"]}'
        )
        report = await validator.validate(_agent_results(), _roadmap())
        assert report.passed is False
        # Only Stage 1 LLM call should have happened
        assert mock_llm.ainvoke.call_count == 1

    async def test_fails_when_grounding_below_threshold(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        low_score = _GROUNDING_THRESHOLD - 0.1
        mock_llm.ainvoke.side_effect = [
            _r('{"realism_passed": true, "coherence_passed": true, "notes": []}'),
            _r(f'{{"grounding_score": {low_score:.2f}, "unverified_claims": ["made-up claim"]}}'),
            _r('[{"phase_index": 0, "phase_title": "P1", "confidence": 0.8, "reasoning": ""},'
               ' {"phase_index": 1, "phase_title": "P2", "confidence": 0.8, "reasoning": ""}]'),
        ]
        report = await validator.validate(_agent_results(), _roadmap())
        assert report.passed is False
        assert "made-up claim" in report.unverified_claims

    async def test_notes_include_grounding_and_claims_warning(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = [
            _r('{"realism_passed": true, "coherence_passed": true, "notes": []}'),
            _r('{"grounding_score": 0.3, "unverified_claims": ["c1", "c2"]}'),
            _r('[{"phase_index": 0, "phase_title": "P1", "confidence": 0.5, "reasoning": ""},'
               ' {"phase_index": 1, "phase_title": "P2", "confidence": 0.5, "reasoning": ""}]'),
        ]
        report = await validator.validate(_agent_results(), _roadmap())
        combined = " ".join(report.notes).lower()
        assert "threshold" in combined or "grounding" in combined
        assert "unverified" in combined

    async def test_report_serialisable_end_to_end(
        self, validator: OutputValidator, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = [
            _r('{"realism_passed": true, "coherence_passed": true, "notes": []}'),
            _r('{"grounding_score": 0.9, "unverified_claims": []}'),
            _r('[{"phase_index": 0, "phase_title": "P1", "confidence": 0.8, "reasoning": ""},'
               ' {"phase_index": 1, "phase_title": "P2", "confidence": 0.8, "reasoning": ""}]'),
        ]
        report = await validator.validate(_agent_results(), _roadmap())
        json.dumps(report.to_dict())  # must not raise


# ── make_output_validator ─────────────────────────────────────────────────────


class TestFactory:
    def test_returns_validator_instance(self) -> None:
        v = make_output_validator(llm=MagicMock())
        assert isinstance(v, OutputValidator)
