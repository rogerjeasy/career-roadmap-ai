"""Regression tests for the Wellness domain."""
import pytest

from src.domains.wellness.schemas import WellnessCheckinOut

pytestmark = pytest.mark.regression


def test_from_doc_coerces_and_defaults_missing_metrics() -> None:
    # REGRESSION: legacy docs may store metrics as strings or omit them; from_doc
    # must coerce to the typed schema with safe defaults rather than raise.
    out = WellnessCheckinOut.from_doc({"id": "w1", "energy": "4", "hours_worked": "55"})
    assert out.energy == 4
    assert out.hours_worked == 55.0
    assert out.stress == 3  # default when missing
    assert out.created_at is None


def test_from_doc_handles_none_metric_values() -> None:
    # REGRESSION: explicit null metric values must fall back to defaults, not crash.
    out = WellnessCheckinOut.from_doc(
        {"id": "w1", "energy": None, "stress": None, "motivation": None}
    )
    assert out.energy == 3
    assert out.stress == 3
    assert out.motivation == 3
