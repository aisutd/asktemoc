from collections import Counter

from app.main import app
from app.services.rag_chain_service import get_rag_chain_service
from app.services.retriever_service import get_retriever_service


def test_health_with_trailing_slash(client):
    r = client.get("/api/health/")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_health_without_trailing_slash_does_not_redirect(client):
    r = client.get("/api/health", follow_redirects=False)
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_no_duplicate_method_and_path():
    seen = Counter(
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or ())
    )
    assert [k for k, n in seen.items() if n > 1] == []


def test_import_and_health_do_not_build_rag_services(client):
    client.get("/api/health/")
    assert get_rag_chain_service.cache_info().currsize == 0
    assert get_retriever_service.cache_info().currsize == 0
