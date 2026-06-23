"""Regression tests for the Assessments domain."""
import pytest

from src.domains.assessments.schemas import PASS_THRESHOLD, AssessmentOut, level_for_score

pytestmark = pytest.mark.regression


def test_answer_key_is_never_serialised_to_client() -> None:
    # REGRESSION: the stored doc carries an answer_key + per-question correct
    # answers; the client model must expose neither, or quizzes become cheatable.
    doc = {
        "id": "a1", "skill": "SQL", "status": "in_progress",
        "answer_key": {"q1": {"correct": "4", "rubric": "x"}},
        "questions": [{"id": "q1", "kind": "mcq", "prompt": "2+2?", "options": ["3", "4"], "correct": "4"}],
    }
    out = AssessmentOut.from_doc(doc)
    dumped = out.model_dump()
    assert "answer_key" not in dumped
    assert all("correct" not in q and "rubric" not in q for q in dumped["questions"])


def test_pass_threshold_boundary_levels() -> None:
    # REGRESSION: the pass threshold (70) must align with the "advanced" level cut.
    assert level_for_score(PASS_THRESHOLD) == "advanced"
    assert level_for_score(PASS_THRESHOLD - 1) == "intermediate"


def test_from_doc_unknown_level_becomes_none() -> None:
    assert AssessmentOut.from_doc({"id": "a1", "level": "godlike"}).level is None
