"""
Local dense search: chunk vectors from a model that is not stored in Neon
(text-embedding-3-large), kept in a gitignored .npz under backend/.cache/ and
searched with exact cosine similarity in numpy. Neon is not touched; the chunk
texts come from the BM25 chunk cache, which was read from Neon.

    index = load_index(chunks)            # from the cache file
    local_retrieve(query, 5, index=index) # same shape as retrieve()
"""

import hashlib
from pathlib import Path

import numpy as np

from retrieval.db import check_k
from retrieval.dense import openai_embed, openai_embed_batch

LARGE_MODEL = "text-embedding-3-large"
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
BATCH_SIZE = 100


def cache_path(model=LARGE_MODEL):
    return CACHE_DIR / f"chunk_embeddings_{model}.npz"


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_vectors(path):
    """{(chunk_id, text_sha): vector} from a cache file, or {} if there is none."""
    if not path.exists():
        return {}
    with np.load(path) as z:
        return {(cid, sha): vec for cid, sha, vec in zip(z["chunk_ids"], z["text_sha"], z["vectors"])}


def write_vectors(path, model, vectors):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(vectors)
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez(tmp, model=np.array(model), chunk_ids=np.array([k[0] for k in keys]),
             text_sha=np.array([k[1] for k in keys]),
             vectors=np.array([vectors[k] for k in keys], dtype=np.float32))
    tmp.replace(path)


def missing_chunks(chunks, path):
    """Chunks with no cached vector for their current text."""
    have = read_vectors(path)
    return [c for c in chunks if (c["chunk_id"], text_sha(c["text"])) not in have]


def embed_chunks(chunks, *, model=LARGE_MODEL, path=None, embed_batch=None, on_batch=None):
    """
    Embed the chunks that are not cached yet, BATCH_SIZE per call, saving after
    every batch so an interrupted run resumes where it stopped. Returns the
    number of chunks embedded.
    """
    path = path or cache_path(model)
    embed_batch = embed_batch or (lambda texts: openai_embed_batch(texts, model))
    vectors = read_vectors(path)
    todo = missing_chunks(chunks, path)
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        for c, vec in zip(batch, embed_batch([c["text"] for c in batch]), strict=True):
            vectors[c["chunk_id"], text_sha(c["text"])] = np.asarray(vec, dtype=np.float32)
        write_vectors(path, model, vectors)
        if on_batch:
            on_batch(min(i + BATCH_SIZE, len(todo)), len(todo))
    return len(todo)


class LocalDenseIndex:
    """Exact cosine search over unit-normalised chunk vectors."""

    def __init__(self, chunks, vectors, model=LARGE_MODEL):
        m = np.asarray(vectors, dtype=np.float32)
        if len(chunks) == 0 or m.shape[0] != len(chunks):
            raise ValueError(f"{len(chunks)} chunks but {m.shape[0]} vectors")
        self.chunks, self.model = chunks, model
        self.matrix = m / np.linalg.norm(m, axis=1, keepdims=True)

    def search(self, query_vec, k):
        check_k(k)
        q = np.asarray(query_vec, dtype=np.float32)
        scores = self.matrix @ (q / np.linalg.norm(q))
        # Stable sort on -score: ties keep corpus order (title, chunk_index).
        order = np.argsort(-scores, kind="stable")[:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in order]


def load_index(chunks, *, model=LARGE_MODEL, path=None):
    """Index over chunks from the cache file; raises if any chunk is not embedded."""
    path = path or cache_path(model)
    have = read_vectors(path)
    keys = [(c["chunk_id"], text_sha(c["text"])) for c in chunks]
    missing = sum(k not in have for k in keys)
    if missing:
        raise RuntimeError(f"{missing} of {len(chunks)} chunks have no {model} vector in {path}; "
                           "run scripts/embed_chunks_large.py")
    return LocalDenseIndex(chunks, [have[k] for k in keys], model)


def local_retrieve(query, k, *, index, embed=None):
    """
    Top-k chunks for query by cosine similarity against index. The query is
    embedded with the index's model (text-embedding-3-large by default), never
    the small model. Same result shape as retrieve().
    """
    check_k(k)
    embed = embed or (lambda text: openai_embed(text, index.model))
    return index.search(embed(query), k)
