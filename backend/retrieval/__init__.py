"""
Retrieval over the Neon corpus (documents / chunks / embeddings) loaded by
embed_pipeline.py. Used for evaluation; the API's own Chroma retriever is
untouched.

    from retrieval import retrieve, bm25_search

Both return a list of dicts: chunk_id, document_id, doc_title, chunk_index,
text, score (higher = better), best first.
"""

from retrieval.bm25 import bm25_search
from retrieval.dense import retrieve

__all__ = ["retrieve", "bm25_search"]
