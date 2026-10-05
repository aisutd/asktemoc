import os

import chromadb
from langchain_chroma import Chroma


def _get_embeddings():
    """Use OpenAI embeddings if OPENAI_API_KEY is set, otherwise Ollama."""
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))
    from langchain_community.embeddings import OllamaEmbeddings
    return OllamaEmbeddings(model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"))


class RetrieverService:
    def __init__(self, collection_name="asktemoc_collection"):
        self.client = chromadb.PersistentClient(
            path=os.getenv("CHROMA_PERSIST_DIRECTORY", "./app/chroma_db")
        )
        self.collection_name = collection_name
        self.embeddings = _get_embeddings()

    def get_retriever(self):
        vector_store = Chroma(
            client=self.client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
        )
        return vector_store.as_retriever()

retriever_service = RetrieverService()
