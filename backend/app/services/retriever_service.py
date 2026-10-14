"""
Retriever backed by pgvector + OpenAI embeddings.
Replaces the previous ChromaDB-based retriever.
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session
from openai import OpenAI

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Chunk, Embedding, Document

logger = logging.getLogger(__name__)


class RetrieverService:
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    def embed_query(self, query: str) -> list[float]:
        response = self.client.embeddings.create(
            input=query,
            model=self.settings.OPENAI_EMBEDDING_MODEL,
        )
        return response.data[0].embedding

    def search(self, query: str, k: int = 5, db: Optional[Session] = None) -> list[dict]:
        """
        Embed query and find top-k most similar chunks via pgvector cosine distance.
        Returns list of dicts with text, source, title, chunk_index, score.
        """
        own_db = db is None
        if own_db:
            db = SessionLocal()

        try:
            query_vector = self.embed_query(query)

            results = (
                db.query(Chunk, Embedding, Document)
                .join(Embedding, Embedding.chunk_id == Chunk.id)
                .join(Document, Document.id == Chunk.document_id)
                .filter(Chunk.is_deleted == False)
                .filter(Document.is_deleted == False)
                .filter(Embedding.vector.isnot(None))
                .order_by(Embedding.vector.cosine_distance(query_vector))
                .limit(k)
                .all()
            )

            return [
                {
                    "text": chunk.text,
                    "source": doc.source,
                    "title": doc.title,
                    "chunk_index": chunk.chunk_index,
                    "score": float(embedding.vector.cosine_distance(query_vector))
                    if hasattr(embedding.vector, "cosine_distance")
                    else None,
                }
                for chunk, embedding, doc in results
            ]
        finally:
            if own_db:
                db.close()

    async def a_search(self, query: str, k: int = 5, db: Optional[Session] = None) -> list[dict]:
        """Async wrapper — OpenAI SDK is sync so we just call sync version."""
        return self.search(query, k=k, db=db)

    # LangChain compatibility — get_retriever() used by rag_chain_service
    def get_retriever(self, k: int = 5):
        from langchain_core.documents import Document as LCDocument
        from langchain_core.retrievers import BaseRetriever
        from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun

        service = self

        class _PgRetriever(BaseRetriever):
            def _get_relevant_documents(
                self, query: str, *, run_manager: CallbackManagerForRetrieverRun
            ) -> list[LCDocument]:
                hits = service.search(query, k=k)
                return [
                    LCDocument(
                        page_content=h["text"],
                        metadata={"source": h["source"], "title": h["title"]},
                    )
                    for h in hits
                ]

        return _PgRetriever()


retriever_service = RetrieverService()
