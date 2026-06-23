"""Regression tests for the Portfolio domain."""
from datetime import datetime, timezone

import pytest

from src.domains.portfolio.schemas import PortfolioItemOut, PortfolioItemUpdate

pytestmark = pytest.mark.regression

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_from_doc_unknown_status_falls_back_to_live() -> None:
    out = PortfolioItemOut.from_doc({"id": "p1", "status": "deprecated", "created_at": NOW})
    assert out.status == "live"


def test_update_to_patch_omits_unset_fields() -> None:
    patch = PortfolioItemUpdate(status="archived").to_patch()
    assert patch == {"status": "archived"}
    assert "title" not in patch
