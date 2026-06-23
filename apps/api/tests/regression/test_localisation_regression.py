"""Regression tests for the Localisation domain."""
import pytest

from src.domains.localisation.schemas import LocalisationReport, report_slug

pytestmark = pytest.mark.regression


def test_report_slug_collapses_punctuation_and_caps_length() -> None:
    # REGRESSION: the slug is a Firestore doc id; it must be lowercased, have
    # punctuation collapsed to single hyphens, and be length-bounded.
    slug = report_slug("  United States!! ", "Senior  Product/Manager ")
    assert slug == "united-states-senior-product-manager"
    assert len(report_slug("x" * 300, "y" * 300)) <= 200


def test_from_doc_only_keeps_known_fields() -> None:
    # REGRESSION: legacy docs may carry extra keys; from_doc must filter to known
    # model fields rather than error on unexpected ones.
    out = LocalisationReport.from_doc({
        "id": "germany-pm", "country": "Germany", "role": "PM",
        "summary": "ok", "legacy_field": "ignore-me", "confidence": 0.7,
    })
    assert out.country == "Germany"
    assert out.confidence == 0.7


def test_report_always_carries_confidence_and_assumptions_fields() -> None:
    # REGRESSION (responsible-AI): every report must expose confidence + assumptions.
    out = LocalisationReport(country="Germany", role="PM")
    assert hasattr(out, "confidence")
    assert isinstance(out.assumptions, list)
