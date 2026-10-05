"""
Test setup. Every setting the app reads is pinned here, before the app is
imported, so a developer's backend/.env (API keys, AUTH_DISABLED, ...) never
leaks in. Nothing in the suite may reach OpenAI, Ollama or the network: the
RAG chain is replaced by a fake and Chroma is never opened.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmp = tempfile.mkdtemp(prefix="asktemoc-tests-")
TEST_SECRET = "test-secret-" + "x" * 40

os.environ.update({
    "ENVIRONMENT": "development",
    "DATABASE_URL": f"sqlite:///{Path(_tmp, 'test.db').as_posix()}",
    "CHROMA_PERSIST_DIRECTORY": str(Path(_tmp, "chroma")),
    "OPENAI_API_KEY": "",
    "OLLAMA_BASE_URL": "http://ollama.invalid:11434",
    "BACKEND_JWT_SECRET": TEST_SECRET,
    "ALLOWED_EMAIL_DOMAIN": "utdallas.edu",
    "ALLOWED_EMAILS": "",
    "AUTH_DISABLED": "false",
    "CORS_ORIGINS": "http://localhost:3000",
})

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from app.api.endpoints.rag_endpoint import get_chain  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import User  # noqa: E402
from app.main import app  # noqa: E402

init_db()


class FakeChain:
    """Mimics the RAG chain's astream output: context first, then answer deltas."""

    def __init__(self, deltas=("Core ", "courses ", "are CS 1337.")):
        self.deltas = deltas
        self.calls = []

    async def astream(self, question):
        self.calls.append(question)
        yield {"question": question}
        yield {"context": [
            Document(page_content="...", metadata={
                "source": "https://catalog.utdallas.edu/2025/undergraduate/programs/ecs/computer-science",
                "title": "Bachelor of Science in Computer Science",
            }),
            Document(page_content="...", metadata={"source": "https://example.edu/other"}),
        ]}
        for d in self.deltas:
            yield {"answer": d}


def make_token(
    email="student@utdallas.edu",
    sub="microsoft-entra-id:abc",
    name="Test Student",
    secret=TEST_SECRET,
    exp_offset=300,
    **overrides,
):
    now = int(time.time())
    claims = {
        "sub": sub, "email": email, "name": name,
        "aud": "asktemoc-api", "iss": "asktemoc-web",
        "iat": now, "exp": now + exp_offset,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def fake_chain():
    chain = FakeChain()
    app.dependency_overrides[get_chain] = lambda: chain
    yield chain
    app.dependency_overrides.pop(get_chain, None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Fresh users table and settings cache per test."""
    with SessionLocal() as s:
        s.query(User).delete()
        s.commit()
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
