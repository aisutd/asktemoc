import pytest
from pydantic import ValidationError

from app.core.auth import DEV_USER_EMAIL
from app.core.config import BACKEND_DIR, Settings
from app.db.models import User


def _settings(**overrides):
    values = {"backend_jwt_secret": "s" * 40, "environment": "development"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("env", ["production", "staging", "test"])
def test_auth_disabled_refused_outside_development(env):
    with pytest.raises(ValidationError, match="refusing to start"):
        _settings(auth_disabled=True, environment=env)


def test_auth_disabled_allowed_in_development():
    assert _settings(auth_disabled=True).auth_disabled is True


def test_jwt_secret_required_outside_development():
    with pytest.raises(ValidationError, match="BACKEND_JWT_SECRET is required"):
        _settings(environment="production", backend_jwt_secret=None)


def test_short_jwt_secret_rejected():
    with pytest.raises(ValidationError, match="at least 32"):
        _settings(backend_jwt_secret="short")


def test_validation_errors_hide_secret_values():
    with pytest.raises(ValidationError) as exc:
        _settings(auth_disabled=True, environment="production", openai_api_key="sk-secret-value")
    assert "sk-secret-value" not in str(exc.value)


def test_csv_and_path_parsing():
    s = _settings(
        cors_origins="http://a.test, http://b.test",
        allowed_emails="A@x.com,b@y.com",
        database_url="sqlite:///./rel.db",
    )
    assert s.cors_origins == ["http://a.test", "http://b.test"]
    assert s.allowed_emails == ["a@x.com", "b@y.com"]
    assert s.database_url == "sqlite:///" + (BACKEND_DIR / "rel.db").as_posix()


def test_auth_disabled_serves_fixed_dev_user(client, fake_chain, db, monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert [u.email for u in db.query(User).all()] == [DEV_USER_EMAIL]
