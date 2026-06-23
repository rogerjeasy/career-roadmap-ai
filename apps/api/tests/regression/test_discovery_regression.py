"""Regression tests for the Discovery domain."""
import pytest

from src.domains.discovery.schemas import DiscoveryResult

pytestmark = pytest.mark.regression


def test_has_data_is_true_only_when_paths_exist() -> None:
    # REGRESSION: has_data drives the UI's empty state; it must be derived from
    # the presence of paths, not trusted from the raw doc.
    assert DiscoveryResult.from_doc({"paths": []}).has_data is False
    assert DiscoveryResult.from_doc({"paths": [{"title": "X"}]}).has_data is True


def test_empty_factory_has_no_data() -> None:
    assert DiscoveryResult.empty().has_data is False
    assert DiscoveryResult.empty().paths == []


def test_from_doc_skips_non_dict_paths() -> None:
    out = DiscoveryResult.from_doc({"paths": [{"title": "Good"}, "garbage", 123]})
    assert [p.title for p in out.paths] == ["Good"]
