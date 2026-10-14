"""
RAG chain: OpenAI or Ollama chat models + retrieval from Neon Postgres via pgvector.

Chunk embeddings are read from the `embeddings` table (vectors written by `/api/ingest` scrape pipeline).
Uses chat models (`ChatOpenAI`, `ChatOllama`) so `.astream()` yields real tokens.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

from app.services.prompt_service import (
    format_numbered_retrieval_context,
    rag_prompt_template,
)
from app.services.retriever_service import retriever_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_llm():
    """Chat models only so retrieval + prompt can stream with `.astream()`."""
    settings = get_settings()
    if settings.use_openai:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0.15,
            top_p=0.9,
            api_key=settings.OPENAI_API_KEY,
        )
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL.rstrip("/"),
        temperature=0.15,
        top_p=0.9,
    )


class RagChainService:
    """Builds a LangChain RAG graph that retrieves from Postgres/pgvector, not Chroma."""

    def __init__(self):
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = _get_llm()
        return self._llm

    def get_chain(self, k: int = 5):
        """
        Fresh retriever each call so it always uses current `DATABASE_URL` (e.g. Neon) data.
        """
        retriever = retriever_service.get_retriever(k=k)

        def format_docs(docs):
            tuples = [
                (d.page_content, (d.metadata or {}).get("source"), (d.metadata or {}).get("title"))
                for d in docs
            ]
            return format_numbered_retrieval_context(tuples)

        rag_chain_from_docs = (
            RunnablePassthrough.assign(context=(lambda x: format_docs(x["context"])))
            | rag_prompt_template
            | self.llm
            | StrOutputParser()
        )

        return RunnableParallel(
            {"context": retriever, "question": RunnablePassthrough()}
        ).assign(answer=rag_chain_from_docs)

    @staticmethod
    def _normalize_chunk_text(chunk) -> str:
        """Normalize AIMessageChunk / chat model stream pieces to concatenatable text."""
        c = getattr(chunk, "content", None)
        if c is None:
            return ""
        if isinstance(c, str):
            return c
        # Multimodal: list of dicts like {"type": "text", "text": "..."}
        parts: list[str] = []
        if not isinstance(c, list):
            return ""
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)

    async def astream_rag(
        self, message: str, k: int = 5
    ) -> AsyncIterator[dict]:
        """
        Retrieve from pgvector first, then stream LLM tokens (true model streaming).

        Yields dict events:
          {"type": "source", "index": int, "source": str, "title": str|null}
          {"type": "text", "delta": str}
          {"type": "done"}
          {"type": "error", "message": str}  — terminal
        """
        try:
            hits = await asyncio.to_thread(retriever_service.search, message, k)
            for i, h in enumerate(hits):
                yield {
                    "type": "source",
                    "index": i + 1,
                    "source": h.get("source") or "Unknown",
                    "title": h.get("title"),
                }

            tuples = [(h["text"] or "", h.get("source"), h.get("title")) for h in hits]
            ctx = format_numbered_retrieval_context(tuples)
            prompt_body = rag_prompt_template.format(context=ctx, question=message)

            messages = [HumanMessage(content=prompt_body)]
            async for chunk in self.llm.astream(messages):
                delta = self._normalize_chunk_text(chunk)
                if delta:
                    yield {"type": "text", "delta": delta}
            yield {"type": "done"}
        except Exception as e:
            logger.exception("astream_rag failed: %s", e)
            yield {"type": "error", "message": str(e)}


rag_chain_service = RagChainService()
