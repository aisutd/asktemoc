import json

from app.api.endpoints.rag_endpoint import get_chain
from app.main import app


def _post(client, message="core requirements for BS Computer Science"):
    return client.post("/api/chat", json={"message": message})


def _events(body: str):
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]


def test_chat_streams_well_formed_sse(client, fake_chain):
    r = _post(client)
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


def test_chat_requires_a_message(client, fake_chain):
    assert client.post("/api/chat", json={}).status_code == 422
    assert fake_chain.calls == []


def test_chain_failure_reports_error_then_done(client):
    class Broken:
        async def astream(self, question):
            raise RuntimeError("LLM down")
            yield  # makes this an async generator

    app.dependency_overrides[get_chain] = lambda: Broken()
    try:
        events = _events(_post(client).text)
    finally:
        app.dependency_overrides.pop(get_chain, None)
    assert events == [{"type": "text", "message": "Error processing request"}, {"type": "done"}]
