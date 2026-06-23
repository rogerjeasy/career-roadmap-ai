"""Regression tests for the OSS domain."""
import pytest

from src.domains.oss.schemas import OssBookmarkOut
from src.domains.oss.service import OssService

pytestmark = pytest.mark.regression


def test_search_endpoint_never_returns_pull_requests() -> None:
    # REGRESSION: GitHub's issue-search mixes PRs into results; they must always
    # be filtered out so users only see contributable issues.
    assert OssService._to_issue({"id": 1, "pull_request": {}, "title": "PR"}, [], []) is None


def test_match_score_stays_within_bounds() -> None:
    # REGRESSION: even with many skill matches, the score must stay <= 100
    # (base 50 + skill bonus capped at 40 + 5 for language = 95 max).
    issue = OssService._to_issue(
        {"id": 1, "title": "a b c d e f", "labels": [{"name": "a b c d e f"}]},
        skills=["a", "b", "c", "d", "e", "f"], languages=["python"],
    )
    assert issue is not None
    assert issue.match_score <= 100
    assert issue.match_score == 95


def test_from_doc_defaults() -> None:
    out = OssBookmarkOut.from_doc({"id": "b1"})
    assert out.issue_id == 0
    assert out.status == "saved"
    assert out.labels == []
