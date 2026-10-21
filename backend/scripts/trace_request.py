"""
Trace one chat question through the same pieces POST /api/chat uses, printing
each stage: the query embedding, the retrieved chunks with scores, the exact
prompt sent to the LLM, and the raw LLM answer.

Nothing here changes retrieval or generation. The answer comes from the
endpoint's own cached chain (get_rag_chain_service().get_chain(), streamed with
astream like the endpoint), and LangChain callbacks record what passed through
it. Scores come from the same vector store with the retriever's own k, and are
checked against the documents the chain actually retrieved.

    cd backend && python scripts/trace_request.py [--question "..."]
"""

import argparse
import asyncio
import logging
import math
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.callbacks import AsyncCallbackHandler  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.rag_chain_service import get_rag_chain_service  # noqa: E402
from app.services.retriever_service import get_retriever_service  # noqa: E402

DEFAULT_QUESTION = "What are the requirements for the Data Science major?"


class Recorder(AsyncCallbackHandler):
    """Captures what the chain's retriever and LLM saw and produced."""

    def __init__(self):
        self.retrieved = []
        self.prompts = []
        self.llm_output = None

    async def on_retriever_end(self, documents, **kwargs):
        self.retrieved = list(documents)

    async def on_llm_start(self, serialized, prompts, **kwargs):
        self.prompts = list(prompts)

    async def on_llm_end(self, response, **kwargs):
        gen = response.generations[0][0]
        self.llm_output = (gen.text, gen.generation_info or {})


def section(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def norm(v):
    return math.sqrt(sum(x * x for x in v))


async def trace(question: str):
    settings = get_settings()
    retriever_service = get_retriever_service()
    chain = get_rag_chain_service().get_chain()
    retriever = get_rag_chain_service().retriever
    store = retriever.vectorstore
    k = retriever.search_kwargs.get("k", 4)
    collection = retriever_service.client.get_collection(retriever_service.collection_name)
    space = (collection.configuration_json.get("hnsw") or {}).get("space", "l2")

    section("SETUP (what the endpoint's chain is configured with)")
    print(f"question:          {question}")
    print(f"provider:          {settings.llm_provider}")
    print(f"embedding model:   {settings.embedding_model}")
    print(f"chat model:        {settings.openai_model if settings.llm_provider == 'openai' else settings.ollama_model}")
    print(f"retriever:         search_type={retriever.search_type!r}, search_kwargs={retriever.search_kwargs} -> k={k}")
    print(f"collection:        {collection.name!r}, {collection.count()} chunks, distance space={space!r}")

    section("1. QUERY EMBEDDING (embed_query, exactly as the retriever calls it)")
    vector = retriever_service.embeddings.embed_query(question)
    print(f"dimension: {len(vector)}")
    print(f"first 8:   {[round(x, 5) for x in vector[:8]]}")
    print(f"L2 norm:   {norm(vector):.4f}  (1.0 means the vector is unit-normalised)")

    section(f"2. RETRIEVAL (top {k} by {space} distance; lower = closer)")
    scored = store.similarity_search_with_score(question, k=k)
    ids = [d.id for d, _ in scored]
    stored = collection.get(ids=ids, include=["embeddings"])
    doc_norms = {i: norm(e) for i, e in zip(stored["ids"], stored["embeddings"])}
    for rank, (doc, dist) in enumerate(scored, start=1):
        m = doc.metadata
        line = f"[{rank}] distance={dist:.4f}"
        if space == "l2" and abs(norm(vector) - 1) < 1e-3 and abs(doc_norms.get(doc.id, 0) - 1) < 1e-3:
            # Chroma's l2 is squared L2; for unit vectors that equals 2 - 2*cos.
            line += f"  (cosine similarity={1 - dist / 2:.4f})"
        print(line)
        print(f"    source: {m.get('source')}")
        print(f"    title:  {m.get('title')}  |  {m.get('program')} / {m.get('doc_type')} chunk #{m.get('chunk_index')}")
        snippet = doc.page_content[:300].replace("\n", " / ")
        print(textwrap.indent(textwrap.fill(snippet, 74), "    | "))

    recorder = Recorder()
    deltas = []
    async for chunk in chain.astream(question, config={"callbacks": [recorder]}):
        if chunk.get("answer"):
            deltas.append(chunk["answer"])

    same = [d.id for d in recorder.retrieved] == ids
    print(f"\nchain retrieved the same {len(recorder.retrieved)} chunks in the same order: {same}")

    section("3. PROMPT (exact string the chain passed to the LLM)")
    if len(recorder.prompts) != 1:
        print(f"(expected one prompt, got {len(recorder.prompts)})")
    print(recorder.prompts[0] if recorder.prompts else "(no prompt captured)")

    section("4. RAW LLM ANSWER")
    text, info = recorder.llm_output or ("(no output captured)", {})
    print(text)
    print(f"\nstreamed deltas: {len(deltas)}; joined deltas == raw answer: {''.join(deltas) == text}")
    if info:
        keys = ("model", "prompt_eval_count", "eval_count", "total_duration", "load_duration")
        details = {k_: info[k_] for k_ in keys if k_ in info}
        for k_ in ("total_duration", "load_duration"):
            if k_ in details:
                details[k_] = f"{details[k_] / 1e9:.1f}s"
        print(f"generation info: {details}")


def main():
    parser = argparse.ArgumentParser(description="Trace one question through the RAG pipeline.")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(trace(args.question))


if __name__ == "__main__":
    main()
