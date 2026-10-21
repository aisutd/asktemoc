"""Unit tests for backend/retrieval. Fakes only: no Neon, no OpenAI."""

import json

import pytest

from retrieval import bm25 as bm25_mod
from retrieval import dense
from retrieval.bm25 import BM25Index, bm25_search, get_index, tokenize

RESULT_KEYS = {"chunk_id", "document_id", "doc_title", "chunk_index", "text", "score"}


class FakeCursor:
    def __init__(self, rows, log):
        self.rows, self.log = rows, log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.log.append((query, params))

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, rows):
        self.rows, self.executed, self.closed = rows, [], False

    def cursor(self):
        return FakeCursor(self.rows, self.executed)

    def close(self):
        self.closed = True


def fake_embed(text):
    fake_embed.calls.append(text)
    return [0.5, -0.25, 1.0]


fake_embed.calls = []

DENSE_ROWS = [
    ("c1", "d1", "bachelor_of_science_in_computer_science/requirements", 0, "CS 1337 ...", 0.91),
    ("c2", "d1", "bachelor_of_science_in_computer_science/requirements", 1, "CS 2336 ...", 0.88),
]


# ── dense ────────────────────────────────────────────────────────────────────

def test_retrieve_requires_k():
    with pytest.raises(TypeError):
        dense.retrieve("q", conn=FakeConn([]), embed=fake_embed)


@pytest.mark.parametrize("k", [0, -1, 2.0, True, None])
def test_retrieve_rejects_bad_k(k):
    with pytest.raises(ValueError):
        dense.retrieve("q", k, conn=FakeConn([]), embed=fake_embed)


def test_retrieve_maps_rows_and_passes_parameters():
    conn = FakeConn(DENSE_ROWS)
    hits = dense.retrieve("core CS courses; DROP TABLE x", 2, conn=conn, embed=fake_embed)

    assert [h["chunk_id"] for h in hits] == ["c1", "c2"]
    assert all(set(h) == RESULT_KEYS for h in hits)
    assert hits[0]["doc_title"] == DENSE_ROWS[0][2] and hits[0]["score"] == pytest.approx(0.91)
    assert fake_embed.calls[-1] == "core CS courses; DROP TABLE x"

    (query, params), = conn.executed
    assert params == {"qvec": "[0.5,-0.25,1.0]", "model": "text-embedding-3-small", "k": 2}
    assert "<=>" in query and "LIMIT %(k)s" in query
    assert "DROP" not in query  # the query text never reaches the SQL string
    assert not conn.closed  # a caller-supplied connection is left open


def test_retrieve_opens_and_closes_its_own_connection(monkeypatch):
    conn = FakeConn([])
    monkeypatch.setattr(dense, "connect", lambda: conn)
    assert dense.retrieve("q", 3, embed=fake_embed) == []
    assert conn.closed


# ── BM25 ─────────────────────────────────────────────────────────────────────

CHUNKS = [
    {"chunk_id": "a0", "document_id": "a", "doc_title": "cs/requirements", "chunk_index": 0,
     "text": "Computer Science core: CS 1337 and CS 2336."},
    {"chunk_id": "b0", "document_id": "b", "doc_title": "ee/requirements", "chunk_index": 0,
     "text": "Electrical Engineering math: MATH 2417, MATH 2419."},
    {"chunk_id": "c0", "document_id": "c", "doc_title": "neuro/requirements", "chunk_index": 0,
     "text": "Neuroscience lab courses and biology prerequisites."},
    {"chunk_id": "c1", "document_id": "c", "doc_title": "neuro/requirements", "chunk_index": 1,
     "text": "Advanced neuroscience electives."},
]


def test_tokenize_lowercases_and_splits_on_punctuation():
    assert tokenize("CS-1337, User Experience (UX)!") == ["cs", "1337", "user", "experience", "ux"]
    assert tokenize("  ...  ") == []


def test_bm25_ranks_matching_chunk_first():
    hits = bm25_search("electrical engineering math", 2, index=BM25Index(CHUNKS))
    assert hits[0]["chunk_id"] == "b0"
    assert hits[0]["score"] > hits[1]["score"]
    assert all(set(h) == RESULT_KEYS for h in hits)


def test_bm25_k_caps_results_and_handles_k_above_corpus():
    index = BM25Index(CHUNKS)
    assert len(bm25_search("neuroscience", 1, index=index)) == 1
    assert len(bm25_search("neuroscience", 50, index=index)) == len(CHUNKS)


def test_bm25_ties_keep_corpus_order():
    hits = bm25_search("zzz-not-in-corpus", 4, index=BM25Index(CHUNKS))
    assert [h["chunk_id"] for h in hits] == ["a0", "b0", "c0", "c1"]
    assert all(h["score"] == 0 for h in hits)


def test_bm25_requires_valid_k():
    index = BM25Index(CHUNKS)
    with pytest.raises(TypeError):
        bm25_search("q", index=index)
    with pytest.raises(ValueError):
        bm25_search("q", 0, index=index)


def test_get_index_loads_once_then_uses_cache_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bm25_mod, "_indexes", {})
    cache = tmp_path / "bm25_chunks.json"
    calls = []

    def loader():
        calls.append(1)
        return CHUNKS

    first = get_index(cache_path=cache, loader=loader)
    assert calls == [1] and json.loads(cache.read_text())["chunks"] == CHUNKS
    assert get_index(cache_path=cache, loader=loader) is first  # in-process cache

    monkeypatch.setattr(bm25_mod, "_indexes", {})  # new process: reads the file
    assert get_index(cache_path=cache, loader=loader).chunks == CHUNKS
    assert calls == [1]

    get_index(cache_path=cache, loader=loader, refresh=True)
    assert calls == [1, 1]


def test_get_index_ignores_corrupt_or_old_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(bm25_mod, "_indexes", {})
    cache = tmp_path / "bm25_chunks.json"
    cache.write_text(json.dumps({"version": 0, "chunks": []}))
    assert get_index(cache_path=cache, loader=lambda: CHUNKS).chunks == CHUNKS

    monkeypatch.setattr(bm25_mod, "_indexes", {})
    cache.write_text("{not json")
    assert get_index(cache_path=cache, loader=lambda: CHUNKS).chunks == CHUNKS


def test_load_chunks_maps_rows():
    conn = FakeConn([("a0", "a", "cs/requirements", 0, "text")])
    assert bm25_mod.load_chunks(conn) == [
        {"chunk_id": "a0", "document_id": "a", "doc_title": "cs/requirements",
         "chunk_index": 0, "text": "text"}]
    assert conn.executed[0][1] is None and not conn.closed
