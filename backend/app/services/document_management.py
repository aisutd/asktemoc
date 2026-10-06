"""
Document management utilities for dashboard and batch operations.
Provides high-level helper functions for common document operations.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Document, Chunk, Embedding
from app.db.services import DocumentService, ChunkService, EmbeddingService


class DocumentManagementUtils:
    """Utility functions for document management and dashboard operations."""

    @staticmethod
    def get_document_statistics(db: Session, doc_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a document."""
        document = DocumentService.get_document(db=db, doc_id=doc_id)
        if not document:
            return {}

        chunks = ChunkService.list_chunks_by_document(db=db, document_id=doc_id, limit=10000)
        embeddings = EmbeddingService.get_embeddings_by_document(db=db, document_id=doc_id)

        synced_embeddings = sum(1 for e in embeddings if e.is_synced)
        unsynced_embeddings = sum(1 for e in embeddings if not e.is_synced)

        total_text_length = sum(len(chunk.text) for chunk in chunks)
        avg_chunk_length = total_text_length / len(chunks) if chunks else 0

        return {
            "document_id": doc_id,
            "title": document.title,
            "source": document.source,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
            "chunk_count": len(chunks),
            "embedding_count": len(embeddings),
            "synced_embeddings": synced_embeddings,
            "unsynced_embeddings": unsynced_embeddings,
            "total_text_length": total_text_length,
            "average_chunk_length": avg_chunk_length,
            "sync_percentage": (synced_embeddings / len(embeddings) * 100) if embeddings else 0,
        }

    @staticmethod
    def get_all_documents_dashboard(db: Session) -> List[Dict[str, Any]]:
        """Get dashboard view of all documents with key statistics."""
        documents = DocumentService.list_documents(db=db, limit=10000)

        dashboard_data = []
        for doc in documents:
            chunks = ChunkService.list_chunks_by_document(db=db, document_id=doc.id, limit=10000)
            embeddings = EmbeddingService.get_embeddings_by_document(db=db, document_id=doc.id)

            synced = sum(1 for e in embeddings if e.is_synced)

            dashboard_data.append({
                "id": doc.id,
                "title": doc.title,
                "source": doc.source,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "chunks": len(chunks),
                "embeddings": len(embeddings),
                "synced": synced,
                "status": "synced" if len(embeddings) > 0 and synced == len(embeddings) else "partial" if synced > 0 else "unsynced",
            })

        return dashboard_data

    @staticmethod
    def batch_delete_documents(
        db: Session, doc_ids: List[str], hard_delete: bool = False
    ) -> Dict[str, Any]:
        """Batch delete multiple documents."""
        success_count = 0
        failed_ids = []

        for doc_id in doc_ids:
            try:
                success = DocumentService.delete_document(
                    db=db, doc_id=doc_id, hard_delete=hard_delete
                )
                if success:
                    success_count += 1
                else:
                    failed_ids.append(doc_id)
            except Exception as e:
                failed_ids.append(doc_id)

        return {
            "deleted_count": success_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids,
            "total": len(doc_ids),
        }

    @staticmethod
    def duplicate_document_with_chunks(
        db: Session, source_doc_id: str, new_title: Optional[str] = None
    ) -> Optional[Document]:
        """Duplicate a document including all its chunks and embeddings."""
        source_doc = DocumentService.get_document(db=db, doc_id=source_doc_id)
        if not source_doc:
            return None

        # Create new document
        new_doc = DocumentService.create_document(
            db=db,
            title=new_title or f"{source_doc.title} (Copy)",
            source=source_doc.source,
            metadata=source_doc.doc_metadata,
        )

        # Copy all chunks
        source_chunks = ChunkService.list_chunks_by_document(
            db=db, document_id=source_doc_id, limit=10000
        )

        for chunk in source_chunks:
            new_chunk = ChunkService.create_chunk(
                db=db,
                document_id=new_doc.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                metadata=chunk.metadata,
            )

            # Copy embeddings
            embeddings = EmbeddingService.list_embeddings_by_chunk(
                db=db, chunk_id=chunk.id
            )
            for embedding in embeddings:
                EmbeddingService.create_embedding(
                    db=db,
                    chunk_id=new_chunk.id,
                    vector=embedding.vector,
                    model=embedding.model,
                )

        return new_doc

    @staticmethod
    def export_document_to_json(db: Session, doc_id: str) -> Dict[str, Any]:
        """Export document with chunks and embeddings to JSON format."""
        document = DocumentService.get_document(db=db, doc_id=doc_id)
        if not document:
            return {}

        chunks = ChunkService.list_chunks_by_document(db=db, document_id=doc_id, limit=10000)

        chunks_data = []
        for chunk in chunks:
            embeddings = EmbeddingService.list_embeddings_by_chunk(db=db, chunk_id=chunk.id)

            chunk_data = {
                "id": chunk.id,
                "index": chunk.chunk_index,
                "text": chunk.text,
                "metadata": chunk.chunk_metadata,
                "embeddings": [
                    {
                        "id": emb.id,
                        "model": emb.model,
                        "chroma_id": emb.chroma_id,
                        "is_synced": emb.is_synced,
                        "vector_length": len(emb.vector) if emb.vector else 0,
                    }
                    for emb in embeddings
                ],
            }
            chunks_data.append(chunk_data)

        return {
            "document": {
                "id": document.id,
                "title": document.title,
                "source": document.source,
                "metadata": document.doc_metadata,
                "created_at": document.created_at.isoformat(),
                "updated_at": document.updated_at.isoformat(),
            },
            "chunks": chunks_data,
            "statistics": DocumentManagementUtils.get_document_statistics(db=db, doc_id=doc_id),
        }

    @staticmethod
    def search_content_across_documents(
        db: Session, search_query: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search for content across all chunks in all documents."""
        results = []

        # Search in chunk text
        chunks = (
            db.query(Chunk)
            .filter(
                Chunk.text.ilike(f"%{search_query}%"),
                Chunk.is_deleted == False,
            )
            .limit(limit)
            .all()
        )

        for chunk in chunks:
            document = DocumentService.get_document(db=db, doc_id=chunk.document_id)
            if document:
                results.append({
                    "type": "chunk",
                    "document_id": document.id,
                    "document_title": document.title,
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "text_preview": chunk.text[:200],  # First 200 chars
                    "full_text": chunk.text,
                })

        # Search in document titles
        documents = DocumentService.search_documents(db=db, query_str=search_query)
        for doc in documents:
            results.append({
                "type": "document",
                "document_id": doc.id,
                "document_title": doc.title,
                "source": doc.source,
            })

        return results

    @staticmethod
    def get_sync_status_summary(db: Session) -> Dict[str, Any]:
        """Get overall sync status of all embeddings to ChromaDB."""
        total_embeddings = db.query(func.count(Embedding.id)).scalar() or 0
        synced_embeddings = (
            db.query(func.count(Embedding.id))
            .filter(Embedding.is_synced == True)
            .scalar()
            or 0
        )
        unsynced_embeddings = total_embeddings - synced_embeddings

        total_documents = (
            db.query(func.count(Document.id))
            .filter(Document.is_deleted == False)
            .scalar()
            or 0
        )
        total_chunks = (
            db.query(func.count(Chunk.id))
            .filter(Chunk.is_deleted == False)
            .scalar()
            or 0
        )

        return {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "total_embeddings": total_embeddings,
            "synced_embeddings": synced_embeddings,
            "unsynced_embeddings": unsynced_embeddings,
            "sync_percentage": (synced_embeddings / total_embeddings * 100) if total_embeddings > 0 else 0,
            "last_updated": datetime.utcnow(),
        }

    @staticmethod
    def get_recent_activity(db: Session, days: int = 7, limit: int = 100) -> Dict[str, List]:
        """Get recent document and chunk activity."""
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        recent_documents = (
            db.query(Document)
            .filter(
                Document.updated_at >= cutoff_date,
                Document.is_deleted == False,
            )
            .order_by(Document.updated_at.desc())
            .limit(limit)
            .all()
        )

        recent_chunks = (
            db.query(Chunk)
            .filter(
                Chunk.updated_at >= cutoff_date,
                Chunk.is_deleted == False,
            )
            .order_by(Chunk.updated_at.desc())
            .limit(limit)
            .all()
        )

        recent_embeddings = (
            db.query(Embedding)
            .filter(Embedding.updated_at >= cutoff_date)
            .order_by(Embedding.updated_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "documents": [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "updated_at": doc.updated_at,
                }
                for doc in recent_documents
            ],
            "chunks": [
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "updated_at": chunk.updated_at,
                }
                for chunk in recent_chunks
            ],
            "embeddings": [
                {
                    "id": emb.id,
                    "chunk_id": emb.chunk_id,
                    "updated_at": emb.updated_at,
                    "is_synced": emb.is_synced,
                }
                for emb in recent_embeddings
            ],
        }
