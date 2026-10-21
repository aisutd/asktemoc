"""Unit tests for backend/retrieval/local_dense.py and the eval script's query cache. Fakes only."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from retrieval import local_dense
from retrieval.local_dense import (
    LocalDenseIndex, embed_chunks, load_index, local_retrieve, missing_chunks, read_vectors,
)

RESULT_KEYS = {"chunk_id", "document_id", "doc_title", "chunk_index", "text", "score"}

CHUNKS = [
    {"chunk_id": f"c{i}", "document_id": f"d{i}", "doc_title": f"doc{i}/requirements",
     "chunk_index": 0, "text": f"text {i}"}
    for i in range(5)
]


def fake_vec(text):
    """Deterministic 4-dim vector per text, never unit length (exercises normalisation)."""
    i = int(text.split()[-1]) if text.split()[-1].isdigit() else 9
    v = np.zeros(4, dtype=np.float32)
    v[i % 4] = 3.0
    v[(i + 1) % 4] = 1.0
    return v


class FakeBatchEmbedder:
    def __init__(self, fail_on_call=None):
        self.calls, self.fail_on_call = [], fail_on_call

    def __call__(self, texts):
        self.calls.append(list(texts))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("simulated API failure")
        return [fake_vec(t) for t in texts]


# ── search ───────────────────────────────────────────────────────────────────

def test_search_ranks_by_cosine_and_ignores_vector_length():
    index = LocalDenseIndex(CHUNKS[:4], [fake_vec(c["text"]) * (i + 1) for i, c in enumerate(CHUNKS[:4])])
    hits = index.search(fake_vec("text 2") * 100, 2)
    assert [h["chunk_id"] for h in hits] == ["c2", "c1"]
    assert hits[0]["score"] == pytest.approx(1.0)
    assert all(set(h) == RESULT_KEYS for h in hits)


def test_search_ties_keep_corpus_order_and_validates_k():
    index = LocalDenseIndex(CHUNKS[:3], [[1, 0], [1, 0], [0, 1]])
    assert [h["chunk_id"] for h in index.search([1, 0], 3)] == ["c0", "c1", "c2"]
    assert len(index.search([1, 0], 50)) == 3
    with pytest.raises(ValueError):
        index.search([1, 0], 0)


def test_index_rejects_mismatched_vectors():
    with pytest.raises(ValueError):
        LocalDenseIndex(CHUNKS[:3], [[1, 0], [0, 1]])


def test_local_retrieve_embeds_query_with_the_index_model(monkeypatch):
    index = LocalDenseIndex(CHUNKS[:4], [fake_vec(c["text"]) for c in CHUNKS[:4]], model="m-large")
    seen = []
    monkeypatch.setattr(local_dense, "openai_embed", lambda text, model: seen.append((text, model)) or fake_vec("text 3"))
    hits = local_retrieve("q", 1, index=index)
    assert seen == [("q", "m-large")] and hits[0]["chunk_id"] == "c3"
    with pytest.raises(TypeError):
        local_retrieve("q", index=index)


# ── cache ────────────────────────────────────────────────────────────────────

def test_embed_chunks_batches_caches_and_skips_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(local_dense, "BATCH_SIZE", 2)
    path = tmp_path / "vecs.npz"
    fake = FakeBatchEmbedder()
    assert embed_chunks(CHUNKS, model="m", path=path, embed_batch=fake) == 5
    assert [len(c) for c in fake.calls] == [2, 2, 1]
    assert len(read_vectors(path)) == 5 and missing_chunks(CHUNKS, path) == []

    assert embed_chunks(CHUNKS, model="m", path=path, embed_batch=fake) == 0  # all cached
    assert len(fake.calls) == 3


def test_embed_chunks_reembeds_changed_text(tmp_path):
    path = tmp_path / "vecs.npz"
    embed_chunks(CHUNKS, model="m", path=path, embed_batch=FakeBatchEmbedder())
    edited = [dict(CHUNKS[0], text="text 7"), *CHUNKS[1:]]
    assert [c["chunk_id"] for c in missing_chunks(edited, path)] == ["c0"]


def test_embed_chunks_keeps_finished_batches_when_a_later_batch_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(local_dense, "BATCH_SIZE", 2)
    path = tmp_path / "vecs.npz"
    with pytest.raises(RuntimeError):
        embed_chunks(CHUNKS, model="m", path=path, embed_batch=FakeBatchEmbedder(fail_on_call=2))
    assert len(read_vectors(path)) == 2  # resume embeds only the remaining 3
    assert len(missing_chunks(CHUNKS, path)) == 3


def test_load_index_aligns_vectors_to_chunk_order(tmp_path):
    path = tmp_path / "vecs.npz"
    embed_chunks(CHUNKS, model="m", path=path, embed_batch=FakeBatchEmbedder())
    index = load_index(list(reversed(CHUNKS)), model="m", path=path)
    assert index.search(fake_vec("text 4"), 1)[0]["chunk_id"] == "c4"
    with pytest.raises(RuntimeError, match="1 of 6"):
        load_index([*CHUNKS, dict(CHUNKS[0], chunk_id="new")], model="m", path=path)


# ── eval script's per-model query cache ──────────────────────────────────────

def _eval_script():
    spec = importlib.util.spec_from_file_location(
        "eval_retrieval", Path(__file__).resolve().parents[1] / "scripts" / "eval_retrieval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_query_cache_is_per_model(tmp_path, monkeypatch):
    ev = _eval_script()
    calls = []
    monkeypatch.setattr(ev, "openai_embed", lambda text, model: calls.append(model) or [1.0, 0.0])
    path = tmp_path / "q.json"

    small = ev.CachedEmbedder("small", path)
    small("q")
    small.save()
    assert ev.CachedEmbedder("small", path)("q") == [1.0, 0.0] and calls == ["small"]

    large = ev.CachedEmbedder("large", path)  # a cache file for another model is not reused
    large("q")
    assert calls == ["small", "large"]
