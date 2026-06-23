"""Unit tests for the camelCase ↔ snake_case helpers (``src.core.case_converter``).

These are the pure functions behind ``CaseConversionMiddleware``. They underpin
the entire frontend↔backend naming contract, so the edge cases (acronyms,
already-correct keys, nested structures) are pinned tightly.
"""
import pytest

from src.core.case_converter import (
    keys_to_camel,
    keys_to_snake,
    to_camel_case,
    to_snake_case,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("camel", "snake"),
    [
        ("displayName", "display_name"),
        ("photoURL", "photo_url"),
        ("idToken", "id_token"),
        ("userID", "user_id"),
        ("already_snake", "already_snake"),
        ("HTTPSConnection", "https_connection"),
        ("simple", "simple"),
        ("aB", "a_b"),
    ],
)
def test_to_snake_case(camel: str, snake: str) -> None:
    assert to_snake_case(camel) == snake


@pytest.mark.parametrize(
    ("snake", "camel"),
    [
        ("display_name", "displayName"),
        ("id_token", "idToken"),
        ("user_id", "userId"),
        ("simple", "simple"),
        ("", ""),
    ],
)
def test_to_camel_case(snake: str, camel: str) -> None:
    assert to_camel_case(snake) == camel


def test_keys_to_snake_recurses_into_nested_dicts_and_lists() -> None:
    payload = {
        "userProfile": {
            "displayName": "Ada",
            "socialLinks": [{"linkType": "github"}, {"linkType": "linkedin"}],
        }
    }
    assert keys_to_snake(payload) == {
        "user_profile": {
            "display_name": "Ada",
            "social_links": [{"link_type": "github"}, {"link_type": "linkedin"}],
        }
    }


def test_keys_to_camel_recurses_into_nested_dicts_and_lists() -> None:
    payload = {
        "user_profile": {
            "display_name": "Ada",
            "social_links": [{"link_type": "github"}],
        }
    }
    assert keys_to_camel(payload) == {
        "userProfile": {
            "displayName": "Ada",
            "socialLinks": [{"linkType": "github"}],
        }
    }


def test_roundtrip_is_stable_for_well_formed_keys() -> None:
    original = {"display_name": "x", "id_token": "y", "nested_obj": {"a_b": 1}}
    assert keys_to_snake(keys_to_camel(original)) == original


def test_non_dict_values_pass_through_untouched() -> None:
    assert keys_to_snake("plain string") == "plain string"
    assert keys_to_snake(42) == 42
    assert keys_to_snake(None) is None
    assert keys_to_camel([1, 2, 3]) == [1, 2, 3]
