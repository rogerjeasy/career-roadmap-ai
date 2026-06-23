"""Regression tests for the Interview Prep domain."""
import pytest

from src.domains.interview_prep.schemas import SessionOut

pytestmark = pytest.mark.regression


def test_from_doc_unknown_interview_type_falls_back() -> None:
    out = SessionOut.from_doc({"id": "s1", "interview_type": "panel"})
    assert out.interview_type == "mixed"


def test_from_doc_normalises_transcript_roles() -> None:
    # REGRESSION: any non-"interviewer" role must normalise to "candidate" so the
    # transcript schema never rejects legacy/garbage role values.
    out = SessionOut.from_doc({
        "id": "s1",
        "transcript": [
            {"role": "interviewer", "content": "Q"},
            {"role": "user", "content": "A"},      # legacy → candidate
            {"role": "candidate", "content": "B"},
        ],
    })
    assert [m.role for m in out.transcript] == ["interviewer", "candidate", "candidate"]


def test_from_doc_coerces_overall_score() -> None:
    assert SessionOut.from_doc({"id": "s1", "overall_score": "88"}).overall_score == 88
