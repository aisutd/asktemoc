import json

import jwt as pyjwt
import pytest

from app.api.endpoints.rag_endpoint import get_chain
from app.main import app
from tests.conftest import make_token


def _post(client, token=None, message="core requirements for BS Computer Science"):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/chat", json={"message": message}, headers=headers)


def _events(body: str):
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]


def test_missing_token_is_401(client, fake_chain):
    r = _post(client)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert fake_chain.calls == []


def test_non_bearer_scheme_is_401(client, fake_chain):
    r = client.post("/api/chat", json={"message": "x"}, headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


@pytest.mark.parametrize("token", [
    "not-a-jwt",
    make_token(secret="forged-" + "y" * 40),  # signed with the wrong key
    make_token(exp_offset=-600),               # expired beyond the leeway
    make_token(aud="someone-else"),
    make_token(iss="evil-web"),
    make_token(exp=None),
    make_token(sub=None),
], ids=["garbage", "forged", "expired", "wrong-aud", "wrong-iss", "no-exp", "no-sub"])
def test_bad_tokens_are_401(client, fake_chain, token):
    assert _post(client, token).status_code == 401
    assert fake_chain.calls == []


def test_alg_none_is_401(client, fake_chain):
    token = pyjwt.encode(
        {"sub": "x", "email": "a@utdallas.edu", "aud": "asktemoc-api",
         "iss": "asktemoc-web", "iat": 0, "exp": 9999999999},
        None, algorithm="none",
    )
    assert _post(client, token).status_code == 401


def test_recently_expired_token_within_leeway_is_accepted(client, fake_chain):
    assert _post(client, make_token(exp_offset=-5)).status_code == 200


@pytest.mark.parametrize("email", ["someone@gmail.com", "x@utdallas.edu.evil.com", "x@notutdallas.edu"])
def test_wrong_domain_is_403(client, fake_chain, email):
    assert _post(client, make_token(email=email)).status_code == 403
    assert fake_chain.calls == []


def test_missing_email_is_403(client, fake_chain):
    assert _post(client, make_token(email=None)).status_code == 403


def test_domain_check_is_case_insensitive(client, fake_chain):
    assert _post(client, make_token(email="Student@UTDallas.EDU")).status_code == 200


def test_allowed_emails_admitted_in_development(client, fake_chain, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "teammate@gmail.com")
    assert _post(client, make_token(email="Teammate@gmail.com")).status_code == 200


def test_valid_token_streams_well_formed_sse(client, fake_chain):
    r = _post(client, make_token())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _events(r.text)

    assert [e["type"] for e in events] == ["source", "source", "text", "text", "text", "done"]
    assert events[0]["message"] == (
        "Source 1: https://catalog.utdallas.edu/2025/undergraduate/programs/ecs/computer-science"
    )
    assert events[0]["index"] == 1
    assert events[0]["title"] == "Bachelor of Science in Computer Science"
    assert events[1]["message"] == "Source 2: https://example.edu/other"
    assert "title" not in events[1]
    # Deltas, not cumulative prefixes: concatenating them yields the answer once.
    assert "".join(e["message"] for e in events if e["type"] == "text") == "Core courses are CS 1337."
    assert fake_chain.calls == ["core requirements for BS Computer Science"]


def test_chain_failure_reports_error_then_done(client):
    class Broken:
        async def astream(self, question):
            raise RuntimeError("LLM down")
            yield  # makes this an async generator

    app.dependency_overrides[get_chain] = lambda: Broken()
    try:
        events = _events(_post(client, make_token()).text)
    finally:
        app.dependency_overrides.pop(get_chain, None)
    assert events == [{"type": "text", "message": "Error processing request"}, {"type": "done"}]
