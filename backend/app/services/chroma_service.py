"""
Chroma export pipeline for syncing embeddings and metadata.
"""

import os
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import Embedding, Chunk, Document
from app.db.services import EmbeddingService

try:
    import chromadb
    from chromadb.api.models.Collection import Collection
except ImportError:
    chromadb = None
    Collection = None


class ChromaService:
    """Service for exporting embeddings and metadata to ChromaDB."""

    def __init__(self):
        """Initialize ChromaDB client."""
        self.persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY", "./app/chroma_db")
        self.collection_name = os.getenv("CHROMA_COLLECTION_NAME", "asktemoc_collection")
        self.client = None
        self.collection = None

        if chromadb is None:
            raise ImportError("chromadb package not installed")

        self._initialize_client()

    def _initialize_client(self):
        """Initialize ChromaDB client and collection."""
        # Create persist directory if it doesn't exist
        os.makedirs(self.persist_directory, exist_ok=True)

        # Initialize persistent client
        self.client = chromadb.PersistentClient(path=self.persist_directory)

        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
        except Exception:
            # Collection doesn't exist, create it
            self.collection = self.client.create_collection(name=self.collection_name)
            print(f"Created ChromaDB collection: {self.collection_name}")

    def prepare_vectors_for_upsert(
        self, db: Session, embeddings: List[Embedding]
    ) -> Dict[str, Any]:
        """
        Prepare vectors and metadata for Chroma upsert.

        Returns dict with 'ids', 'embeddings', 'metadatas', 'documents'.
        """
        ids = []
        vectors = []
        metadatas = []
        documents = []

        for embedding in embeddings:
            chunk = db.query(Chunk).filter(Chunk.id == embedding.chunk_id).first()
            if not chunk:
                continue

            document = db.query(Document).filter(
                Document.id == chunk.document_id
            ).first()
            if not document:
                continue

            # Prepare metadata
            metadata = {
                "embedding_id": embedding.id,
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_title": document.title,
                "document_source": document.source or "",
                "chunk_index": chunk.chunk_index,
                "created_at": chunk.created_at.isoformat() if chunk.created_at else "",
            }

            # Add custom metadata from chunk
            if chunk.chunk_metadata:
                metadata.update(chunk.chunk_metadata)

            # Add custom metadata from document
            if document.doc_metadata:
                metadata.update(document.doc_metadata)

            # Use embedding ID as vector ID (or chroma_id if already set)
            vector_id = embedding.chroma_id or embedding.id

            ids.append(vector_id)
            vectors.append(embedding.vector)
            metadatas.append(metadata)
            documents.append(chunk.text)

        return {
            "ids": ids,
            "embeddings": vectors,
            "metadatas": metadatas,
            "documents": documents,
        }

    def upsert_vectors(self, db: Session, embeddings: List[Embedding]) -> Dict[str, Any]:
        """
        Upsert embeddings and metadata to ChromaDB.

        Returns a dictionary with upsert results and statistics.
        """
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")

        data = self.prepare_vectors_for_upsert(db, embeddings)

        if not data["ids"]:
            return {"status": "no_vectors", "count": 0}

        try:
            # Upsert vectors to ChromaDB
            # Chroma's add method will overwrite if IDs already exist
            self.collection.add(
                ids=data["ids"],
                embeddings=data["embeddings"],
                metadatas=data["metadatas"],
                documents=data["documents"],
            )

            # Update sync status in database
            updated_ids = []
            for vector_id in data["ids"]:
                # Find embedding by ID or chroma_id
                embedding = db.query(Embedding).filter(
                    (Embedding.id == vector_id) | (Embedding.chroma_id == vector_id)
                ).first()
                if embedding:
                    EmbeddingService.mark_synced(db, embedding.id, vector_id)
                    updated_ids.append(embedding.id)

            return {
                "status": "success",
                "upserted_count": len(data["ids"]),
                "updated_db_count": len(updated_ids),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "attempted_count": len(data["ids"]),
            }

    def export_document_embeddings(
        self, db: Session, document_id: str
    ) -> Dict[str, Any]:
        """Export all embeddings for a specific document to ChromaDB."""
        embeddings = EmbeddingService.get_embeddings_by_document(db, document_id)
        unsynced = [e for e in embeddings if not e.is_synced]

        if not unsynced:
            return {
                "status": "no_new_embeddings",
                "total_embeddings": len(embeddings),
                "synced_embeddings": len([e for e in embeddings if e.is_synced]),
            }

        return self.upsert_vectors(db, unsynced)

    def export_unsynced_embeddings(
        self, db: Session, batch_size: int = 100
    ) -> Dict[str, Any]:
        """Export all unsynced embeddings to ChromaDB."""
        unsynced = EmbeddingService.list_unsynced_embeddings(db, limit=batch_size)

        if not unsynced:
            return {
                "status": "no_embeddings",
                "count": 0,
            }

        return self.upsert_vectors(db, unsynced)

    def delete_from_chroma(
        self, vector_ids: List[str]
    ) -> Dict[str, Any]:
        """Delete vectors from ChromaDB by ID."""
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")

        try:
            self.collection.delete(ids=vector_ids)
            return {
                "status": "success",
                "deleted_count": len(vector_ids),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "attempted_count": len(vector_ids),
            }

    def search_chroma(
        self,
        query_vector: List[float],
        top_k: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Search ChromaDB collection."""
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")

        try:
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=where,
            )

            # Format results to be similar to Pinecone's format
            matches = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i, vec_id in enumerate(results['ids'][0]):
                    match = {
                        "id": vec_id,
                        "score": results['distances'][0][i] if 'distances' in results else None,
                        "metadata": results['metadatas'][0][i] if 'metadatas' in results else {},
                        "document": results['documents'][0][i] if 'documents' in results else "",
                    }
                    matches.append(match)

            return {
                "status": "success",
                "matches": matches,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the ChromaDB collection."""
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")

        try:
            count = self.collection.count()
            return {
                "status": "success",
                "stats": {
                    "count": count,
                    "name": self.collection_name,
                    "persist_directory": self.persist_directory,
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
