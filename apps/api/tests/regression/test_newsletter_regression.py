"""Regression tests for the Newsletter domain."""
import pytest

from src.domains.newsletter.schemas import NewsletterDigest, NewsletterPrefsOut

pytestmark = pytest.mark.regression


def test_prefs_unknown_frequency_falls_back_to_weekly() -> None:
    assert NewsletterPrefsOut.from_doc({"frequency": "yearly"}).frequency == "weekly"


def test_digest_has_data_derived_from_content() -> None:
    # REGRESSION: has_data must reflect real content (summary or articles), so the
    # UI's empty state is correct even if a stored doc sets the flag wrong.
    assert NewsletterDigest.from_doc({}).has_data is False
    assert NewsletterDigest.from_doc({"summary": "x"}).has_data is True
    assert NewsletterDigest.from_doc({"articles": [{"title": "a"}]}).has_data is True


def test_digest_skips_non_dict_articles_and_people() -> None:
    out = NewsletterDigest.from_doc({"articles": [{"title": "good"}, "bad"], "people_to_follow": [{"name": "P"}, 1]})
    assert [a.title for a in out.articles] == ["good"]
    assert [p.name for p in out.people_to_follow] == ["P"]
