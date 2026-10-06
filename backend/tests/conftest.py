"""
Test setup. Every setting the app reads is pinned here, before the app is
imported, so a developer's backend/.env (API keys, ...) never leaks in. Nothing
in the suite may reach OpenAI, Ollama or the network: the RAG chain is replaced
by a fake and Chroma is never opened.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmp = tempfile.mkdtemp(prefix="asktemoc-tests-")

os.environ.update({
    "ENVIRONMENT": "development",
    "DATABASE_URL": f"sqlite:///{Path(_tmp, 'test.db').as_posix()}",
    "CHROMA_PERSIST_DIRECTORY": str(Path(_tmp, "chroma")),
    "OPENAI_API_KEY": "",
    "OLLAMA_BASE_URL": "http://ollama.invalid:11434",
    "CORS_ORIGINS": "http://localhost:3000",
})

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from app.api.endpoints.rag_endpoint import get_chain  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


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


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
