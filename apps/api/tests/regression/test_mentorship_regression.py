"""Regression tests for the Mentorship domain."""
import pytest

from src.domains.mentorship.schemas import CaseStudyOut, MentorSessionOut

pytestmark = pytest.mark.regression


def test_session_role_is_relative_to_viewer() -> None:
    # REGRESSION: the same session doc must render role="mentor" to the mentor and
    # role="mentee" to the mentee — the viewer perspective must not leak/flip.
    doc = {"id": "s1", "mentor_id": "m1", "mentee_id": "u1", "status": "accepted"}
    assert MentorSessionOut.from_doc(doc, viewer_id="m1").role == "mentor"
    assert MentorSessionOut.from_doc(doc, viewer_id="u1").role == "mentee"


def test_anonymous_case_study_hides_author_name() -> None:
    # REGRESSION: an anonymous contribution must never expose the author's name.
    out = CaseStudyOut.from_doc(
        {"id": "c1", "author_name": "Ada Lovelace", "is_anonymous": True, "from_role": "a", "to_role": "b"},
        viewer_id="someone",
    )
    assert out.author_name == "Anonymous"


def test_is_mine_only_true_for_author() -> None:
    doc = {"id": "c1", "author_id": "u1", "author_name": "Ada", "from_role": "a", "to_role": "b"}
    assert CaseStudyOut.from_doc(doc, viewer_id="u1").is_mine is True
    assert CaseStudyOut.from_doc(doc, viewer_id="other").is_mine is False


def test_session_unknown_status_falls_back_to_requested() -> None:
    out = MentorSessionOut.from_doc({"id": "s1", "status": "ghosted"}, viewer_id="u1")
    assert out.status == "requested"
