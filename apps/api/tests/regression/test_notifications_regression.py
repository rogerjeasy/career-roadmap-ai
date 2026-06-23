"""Regression tests for the Notifications domain."""
from datetime import datetime, timezone

import pytest

from src.domains.notifications.schemas import NotificationOut

pytestmark = pytest.mark.regression

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_from_doc_unknown_tone_falls_back_to_info() -> None:
    out = NotificationOut.from_doc({"id": "n1", "tone": "danger", "created_at": NOW})
    assert out.tone == "info"


def test_from_doc_missing_read_defaults_false() -> None:
    out = NotificationOut.from_doc({"id": "n1", "created_at": NOW})
    assert out.read is False
    assert out.link is None
