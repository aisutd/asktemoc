import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_DIR, Settings


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


def test_validation_errors_hide_secret_values():
    # A bad value for a secret field must not be echoed into logs.
    with pytest.raises(ValidationError) as exc:
        _settings(openai_api_key=["sk-secret-value"])
    assert "sk-secret-value" not in str(exc.value)


def test_blank_openai_key_selects_ollama():
    s = _settings(openai_api_key="")
    assert s.openai_api_key is None
    assert s.llm_provider == "ollama"
    assert s.embedding_model == s.ollama_embedding_model


def test_openai_key_selects_openai():
    s = _settings(openai_api_key="sk-test")
    assert s.llm_provider == "openai"
    assert s.embedding_model == s.openai_embedding_model


def test_csv_and_path_parsing():
    s = _settings(
        cors_origins="http://a.test, http://b.test",
        database_url="sqlite:///./rel.db",
    )
    assert s.cors_origins == ["http://a.test", "http://b.test"]
    assert s.database_url == "sqlite:///" + (BACKEND_DIR / "rel.db").as_posix()
