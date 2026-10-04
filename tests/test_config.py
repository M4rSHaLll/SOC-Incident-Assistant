import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_development_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert "127.0.0.1:55432" in settings.database_url


def test_production_requires_explicit_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must be explicitly set"):
        Settings(_env_file=None, app_env="production")


def test_production_accepts_environment_database_without_llm_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", Settings(_env_file=None).database_url)
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
    assert settings.llm_api_key is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", " "),
        ("llm_base_url", "invalid-url"),
        ("llm_base_url", "ftp://example.com"),
        ("llm_model", " "),
        ("llm_timeout_seconds", 0),
        ("app_env", "staging"),
        ("log_level", "TRACE"),
    ],
)
def test_invalid_configuration(field: str, value: str | int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
