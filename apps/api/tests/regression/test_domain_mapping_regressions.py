"""Regression tests pinning defensive data-mapping behaviour in domain schemas.

These map legacy / malformed persisted documents onto the current schema. They
exist because real Firestore data predates the current field set, so the
``from_doc`` / ``normalize_status`` mappers must keep coping with old shapes.
"""
import pytest

from src.domains.applications.schemas import ApplicationOut, normalize_status
from src.domains.books.schemas import BookOut

pytestmark = pytest.mark.regression


# ── Applications: legacy status vocabulary ──────────────────────────────────────


@pytest.mark.parametrize(
    ("legacy_status", "expected_status", "expected_outcome"),
    [
        ("accepted", "closed", "accepted"),
        ("rejected", "closed", "rejected"),
        ("withdrawn", "closed", "withdrawn"),
        ("interviewing", "interview", None),
    ],
)
def test_legacy_application_statuses_map_to_canonical(
    legacy_status: str, expected_status: str, expected_outcome: str | None
) -> None:
    assert normalize_status(legacy_status, None) == (expected_status, expected_outcome)


def test_unknown_application_status_falls_back_to_saved() -> None:
    # REGRESSION: a bad/unknown status must never raise — it degrades to "saved".
    assert normalize_status("garbage", None) == ("saved", None)


def test_application_from_doc_handles_legacy_accepted() -> None:
    out = ApplicationOut.from_doc(
        {"id": "a1", "company": "Acme", "role": "PM", "status": "accepted"}
    )
    assert out.status == "closed"
    assert out.outcome == "accepted"


# ── Books: defensive status fallback ────────────────────────────────────────────


def test_book_from_doc_unknown_status_falls_back_to_queued() -> None:
    from datetime import datetime, timezone

    out = BookOut.from_doc(
        {"id": "b1", "title": "T", "status": "in_progress", "created_at": datetime.now(timezone.utc)}
    )
    assert out.status == "queued"  # "in_progress" is not a valid BookStatus


def test_book_from_doc_fills_missing_optional_fields() -> None:
    from datetime import datetime, timezone

    out = BookOut.from_doc({"id": "b1", "title": "T", "created_at": datetime.now(timezone.utc)})
    assert out.author == ""
    assert out.takeaways == []
    assert out.status == "queued"
