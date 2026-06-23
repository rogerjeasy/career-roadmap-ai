"""Regression tests for the Evidence domain."""
from datetime import datetime, timezone

import pytest

from src.domains.evidence.schemas import EvidenceOut, EvidenceUpdate

pytestmark = pytest.mark.regression

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_from_doc_unknown_type_falls_back_to_other() -> None:
    out = EvidenceOut.from_doc({"id": "e1", "type": "blogpost", "created_at": NOW})
    assert out.type == "other"


def test_update_to_patch_omits_unset_fields() -> None:
    # REGRESSION: a partial PATCH must only touch provided fields — None values
    # must never overwrite existing data.
    patch = EvidenceUpdate(title="new").to_patch()
    assert patch == {"title": "new"}
    assert "description" not in patch
    assert "skills" not in patch
