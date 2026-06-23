"""Regression tests for the Monthly Plan domain."""
from datetime import datetime, timezone

import pytest

from src.domains.monthly_plan.schemas import MonthlyPlanOut

pytestmark = pytest.mark.regression

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_from_doc_unknown_status_falls_back_to_future() -> None:
    out = MonthlyPlanOut.from_doc({"id": "1", "status": "pending", "created_at": NOW})
    assert out.status == "future"


def test_from_doc_rebuilds_weeks_and_skips_non_dicts() -> None:
    # REGRESSION: malformed week entries (non-dict) must be skipped, valid ones rebuilt.
    out = MonthlyPlanOut.from_doc({
        "id": "1", "created_at": NOW,
        "weeks": [{"week": 1, "focus": "Foundations", "goals": ["a"]}, "garbage", {"week": 2}],
    })
    assert [w.week for w in out.weeks] == [1, 2]
    assert out.weeks[0].focus == "Foundations"
