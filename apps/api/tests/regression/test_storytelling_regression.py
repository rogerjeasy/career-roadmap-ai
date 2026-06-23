"""Regression tests for the Storytelling domain."""
import pytest

from src.domains.storytelling.schemas import StoryDraftOut

pytestmark = pytest.mark.regression


def test_from_doc_unknown_format_and_tone_fall_back() -> None:
    # REGRESSION: legacy/garbage enum values must degrade, never raise.
    out = StoryDraftOut.from_doc({"id": "d1", "format": "tweet", "tone": "sarcastic"})
    assert out.format == "resume_bullets"
    assert out.tone == "professional"


def test_from_doc_null_lists_become_empty() -> None:
    out = StoryDraftOut.from_doc(
        {"id": "d1", "highlights": None, "tips": None, "evidence_titles": None}
    )
    assert out.highlights == []
    assert out.tips == []
    assert out.evidence_titles == []
