"""Regression tests for the Negotiation domain."""
import pytest

from src.domains.negotiation.schemas import OfferAnalysisOut, OfferInput

pytestmark = pytest.mark.regression


def test_from_doc_unknown_competitiveness_falls_back() -> None:
    # REGRESSION: an unexpected competitiveness value from a legacy doc must
    # degrade to "unknown" rather than raise a validation error.
    out = OfferAnalysisOut.from_doc(
        {"id": "o1", "offer": {"role": "PM"}, "competitiveness": "amazing"}
    )
    assert out.competitiveness == "unknown"


def test_from_doc_rebuilds_nested_offer() -> None:
    out = OfferAnalysisOut.from_doc(
        {"id": "o1", "offer": {"role": "PM", "base_salary": 100000, "currency": "EUR"}}
    )
    assert isinstance(out.offer, OfferInput)
    assert out.offer.base_salary == 100000
    assert out.benchmark_currency == "EUR"  # falls back to the offer currency


def test_from_doc_coerces_numbers_and_null_lists() -> None:
    # REGRESSION: legacy docs may store numerics as strings and lists as null;
    # from_doc must coerce to typed floats and empty lists, never raise.
    out = OfferAnalysisOut.from_doc({
        "id": "o1", "offer": {"role": "PM"},
        "benchmark_low": "140000", "counter_base": "160000",
        "talking_points": None, "risks": None, "assumptions": None, "confidence": None,
    })
    assert out.benchmark_low == 140000.0
    assert out.counter_base == 160000.0
    assert out.talking_points == []
    assert out.risks == []
    assert out.confidence == 0.0
