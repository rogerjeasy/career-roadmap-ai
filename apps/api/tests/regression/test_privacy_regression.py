"""Regression tests for the Privacy domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.privacy.service import PrivacyService, _USER_COLLECTIONS

pytestmark = pytest.mark.regression


def test_shared_multiparty_collections_are_not_user_purgeable() -> None:
    # REGRESSION: purging a user must not delete shared/multi-party data that
    # belongs to others (cohorts, mentor sessions, case studies).
    for shared in ("cohorts", "mentor_sessions", "case_studies"):
        assert shared not in _USER_COLLECTIONS


async def test_export_includes_soft_deleted_docs() -> None:
    # REGRESSION: a data-export (GDPR-style) must include soft-deleted records too,
    # so list_for_user is always called with include_deleted=True.
    seen_flags: list[bool] = []

    class _Repo:
        def __init__(self, db, name):
            pass

        async def list_for_user(self, uid, limit=0, include_deleted=False):
            seen_flags.append(include_deleted)
            return []

    import src.domains.privacy.service as mod
    orig = mod.FirestoreCrudRepository
    mod.FirestoreCrudRepository = _Repo
    try:
        await PrivacyService(MagicMock(), MagicMock()).export("u1")
    finally:
        mod.FirestoreCrudRepository = orig

    assert seen_flags and all(flag is True for flag in seen_flags)
