"""Unit tests for application settings (``src.config``).

Focuses on the custom parsing/validation logic rather than every default:
  • the ``cors_origins`` ``before`` validator (comma-separated string → list);
  • SecretStr wrapping of secrets;
  • the lru_cache on ``get_settings``.
"""
import pytest

from src.config import Settings, get_settings

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "redis_url": "redis://localhost:6379/0",
        "celery_broker_url": "redis://localhost:6379/1",
        "celery_result_backend": "redis://localhost:6379/2",
        "anthropic_api_key": "k",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_cors_origins_splits_comma_separated_string() -> None:
    s = _settings(cors_origins="http://a.com, http://b.com ,http://c.com")
    assert s.cors_origins == ["http://a.com", "http://b.com", "http://c.com"]


def test_cors_origins_drops_empty_segments() -> None:
    s = _settings(cors_origins="http://a.com,, ,")
    assert s.cors_origins == ["http://a.com"]


def test_cors_origins_accepts_list_unchanged() -> None:
    s = _settings(cors_origins=["http://a.com"])
    assert s.cors_origins == ["http://a.com"]


def test_cors_origins_has_a_sensible_default() -> None:
    s = _settings()
    assert s.cors_origins == ["http://localhost:3000"]


def test_secrets_are_wrapped_in_secretstr() -> None:
    s = _settings(anthropic_api_key="super-secret")
    # repr must not leak the secret value
    assert "super-secret" not in repr(s.anthropic_api_key)
    assert s.anthropic_api_key.get_secret_value() == "super-secret"


def test_get_settings_is_cached_singleton() -> None:
    assert get_settings() is get_settings()


def test_defaults_apply_when_optional_values_absent() -> None:
    s = _settings()
    assert s.environment == "development"
    assert s.rate_limit_per_minute == 60
    assert s.blob_storage_provider == "local"
    assert s.redis_session_ttl_seconds == 60 * 60 * 24
