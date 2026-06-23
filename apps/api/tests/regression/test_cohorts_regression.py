"""Regression tests for the Cohorts domain."""
import pytest

from src.domains.cohorts.schemas import CohortOut

pytestmark = pytest.mark.regression


def test_is_member_and_is_owner_are_viewer_scoped() -> None:
    # REGRESSION: membership/ownership flags must be computed for the viewer, not
    # leaked globally — a non-member must never see is_member=True.
    doc = {"id": "c1", "created_by": "owner", "member_ids": ["owner", "u1"], "members": []}
    owner_view = CohortOut.from_doc(doc, viewer_id="owner")
    member_view = CohortOut.from_doc(doc, viewer_id="u1")
    outsider_view = CohortOut.from_doc(doc, viewer_id="stranger")
    assert owner_view.is_owner is True and owner_view.is_member is True
    assert member_view.is_owner is False and member_view.is_member is True
    assert outsider_view.is_member is False and outsider_view.is_owner is False


def test_member_count_uses_member_ids() -> None:
    doc = {"id": "c1", "member_ids": ["a", "b", "c"], "members": []}
    assert CohortOut.from_doc(doc).member_count == 3


def test_unknown_status_and_cadence_fall_back() -> None:
    doc = {"id": "c1", "status": "frozen", "cadence": "daily", "member_ids": []}
    out = CohortOut.from_doc(doc)
    assert out.status == "open"
    assert out.cadence == "weekly"
