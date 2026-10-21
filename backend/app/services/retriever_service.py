"""
Chroma-backed retriever. Built on first use and cached, so importing this module
never touches Chroma, OpenAI or Ollama.

get_embeddings() is shared by the retriever and scripts/seed_catalog.py: vectors
are only comparable when the same provider and model produced them, so switching
between OpenAI and Ollama requires re-seeding.
"""

import logging
from functools import lru_cache

import chromadb
from langchain_chroma import Chroma

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Collection metadata keys written by the seed script.
EMBEDDING_PROVIDER_KEY = "embedding_provider"
EMBEDDING_MODEL_KEY = "embedding_model"


def get_embeddings(settings: Settings | None = None):
    """Use OpenAI embeddings if OPENAI_API_KEY is set, otherwise Ollama."""
    settings = settings or get_settings()
    if settings.llm_provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
    from langchain_ollama import OllamaEmbeddings
    return OllamaEmbeddings(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
    )


def embedding_signature(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    return {
        EMBEDDING_PROVIDER_KEY: settings.llm_provider,
        EMBEDDING_MODEL_KEY: settings.embedding_model,
    }


class RetrieverService:
    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        self.client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        self.collection_name = settings.chroma_collection_name
        self.embeddings = get_embeddings(settings)
        self._warn_on_embedding_mismatch(settings)

    def _warn_on_embedding_mismatch(self, settings: Settings):
        try:
            collection = self.client.get_collection(self.collection_name)
        except Exception:
            logger.warning(
                "Chroma collection %r does not exist yet; run scripts/seed_catalog.py",
                self.collection_name,
            )
            return
        seeded = {k: (collection.metadata or {}).get(k) for k in embedding_signature(settings)}
        if seeded != embedding_signature(settings):
            logger.warning(
                "Collection %r was seeded with %s but the API is configured for %s; "
                "retrieval will be wrong until you re-run scripts/seed_catalog.py",
                self.collection_name, seeded, embedding_signature(settings),
            )

    def get_retriever(self):
        vector_store = Chroma(
            client=self.client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
        )
        return vector_store.as_retriever()


@lru_cache
def get_retriever_service() -> RetrieverService:
    return RetrieverService()
