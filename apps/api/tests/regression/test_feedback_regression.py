"""Regression tests for the Feedback domain."""
from datetime import datetime, timezone

import pytest

from src.domains.feedback.schemas import FeedbackOut

pytestmark = pytest.mark.regression

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_from_doc_unknown_category_falls_back_to_other() -> None:
    # REGRESSION: legacy/garbage categories must degrade to "other", never raise.
    out = FeedbackOut.from_doc(
        {"id": "f1", "category": "legacy_value", "subject": "s", "message": "m", "created_at": NOW}
    )
    assert out.category == "other"


def test_from_doc_defaults_missing_fields() -> None:
    out = FeedbackOut.from_doc({"id": "f1", "created_at": NOW})
    assert out.subject == ""
    assert out.message == ""
    assert out.rating is None
    assert out.category == "other"
