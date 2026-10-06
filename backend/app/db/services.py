"""
Database service layer for CRUD operations on documents, chunks, and embeddings.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.db.models import Document, Chunk, Embedding
import uuid


class DocumentService:
    """Service for document CRUD operations."""

    @staticmethod
    def create_document(
        db: Session,
        title: str,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> Document:
        """Create a new document."""
        document = Document(
            id=doc_id or str(uuid.uuid4()),
            title=title,
            source=source,
            doc_metadata=metadata or {},
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def get_document(db: Session, doc_id: str) -> Optional[Document]:
        """Retrieve a document by ID."""
        return db.query(Document).filter(
            and_(Document.id == doc_id, Document.is_deleted == False)
        ).first()

    @staticmethod
    def list_documents(
        db: Session, skip: int = 0, limit: int = 100, include_deleted: bool = False
    ) -> List[Document]:
        """List all documents with pagination."""
        query = db.query(Document)
        if not include_deleted:
            query = query.filter(Document.is_deleted == False)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def update_document(
        db: Session,
        doc_id: str,
        title: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Document]:
        """Update a document."""
        document = DocumentService.get_document(db, doc_id)
        if not document:
            return None

        if title is not None:
            document.title = title
        if source is not None:
            document.source = source
        if metadata is not None:
            document.doc_metadata = {**(document.doc_metadata or {}), **metadata}

        document.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def delete_document(db: Session, doc_id: str, hard_delete: bool = False) -> bool:
        """Soft or hard delete a document."""
        document = db.query(Document).filter(Document.id == doc_id).first()
        if not document:
            return False

        if hard_delete:
            # Hard delete document and all related chunks/embeddings
            db.delete(document)
        else:
            # Soft delete
            document.is_deleted = True
            document.updated_at = datetime.utcnow()

        db.commit()
        return True

    @staticmethod
    def search_documents(db: Session, query_str: str) -> List[Document]:
        """Search documents by title or source."""
        return db.query(Document).filter(
            and_(
                Document.is_deleted == False,
                or_(
                    Document.title.ilike(f"%{query_str}%"),
                    Document.source.ilike(f"%{query_str}%"),
                ),
            )
        ).all()


class ChunkService:
    """Service for chunk CRUD operations."""

    @staticmethod
    def create_chunk(
        db: Session,
        document_id: str,
        chunk_index: int,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_id: Optional[str] = None,
    ) -> Chunk:
        """Create a new chunk."""
        chunk = Chunk(
            id=chunk_id or str(uuid.uuid4()),
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            chunk_metadata=metadata or {},
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        return chunk

    @staticmethod
    def get_chunk(db: Session, chunk_id: str) -> Optional[Chunk]:
        """Retrieve a chunk by ID."""
        return db.query(Chunk).filter(
            and_(Chunk.id == chunk_id, Chunk.is_deleted == False)
        ).first()

    @staticmethod
    def list_chunks_by_document(
        db: Session, document_id: str, skip: int = 0, limit: int = 1000
    ) -> List[Chunk]:
        """List all chunks for a document."""
        return (
            db.query(Chunk)
            .filter(
                and_(
                    Chunk.document_id == document_id,
                    Chunk.is_deleted == False,
                )
            )
            .order_by(Chunk.chunk_index)
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update_chunk(
        db: Session,
        chunk_id: str,
        text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Chunk]:
        """Update a chunk."""
        chunk = ChunkService.get_chunk(db, chunk_id)
        if not chunk:
            return None

        if text is not None:
            chunk.text = text
        if metadata is not None:
            chunk.chunk_metadata = {**(chunk.chunk_metadata or {}), **metadata}

        chunk.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(chunk)
        return chunk

    @staticmethod
    def delete_chunk(db: Session, chunk_id: str, hard_delete: bool = False) -> bool:
        """Soft or hard delete a chunk."""
        chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
        if not chunk:
            return False

        if hard_delete:
            db.delete(chunk)
        else:
            chunk.is_deleted = True
            chunk.updated_at = datetime.utcnow()

        db.commit()
        return True

    @staticmethod
    def get_chunks_by_ids(db: Session, chunk_ids: List[str]) -> List[Chunk]:
        """Retrieve multiple chunks by IDs."""
        return (
            db.query(Chunk)
            .filter(
                and_(
                    Chunk.id.in_(chunk_ids),
                    Chunk.is_deleted == False,
                )
            )
            .all()
        )


class EmbeddingService:
    """Service for embedding CRUD operations."""

    @staticmethod
    def create_embedding(
        db: Session,
        chunk_id: str,
        vector: List[float],
        model: str = "text-embedding-ada-002",
        chroma_id: Optional[str] = None,
        embedding_id: Optional[str] = None,
    ) -> Embedding:
        """Create a new embedding."""
        embedding = Embedding(
            id=embedding_id or str(uuid.uuid4()),
            chunk_id=chunk_id,
            vector=vector,
            model=model,
            chroma_id=chroma_id,
            is_synced=False,
        )
        db.add(embedding)
        db.commit()
        db.refresh(embedding)
        return embedding

    @staticmethod
    def get_embedding(db: Session, embedding_id: str) -> Optional[Embedding]:
        """Retrieve an embedding by ID."""
        return db.query(Embedding).filter(Embedding.id == embedding_id).first()

    @staticmethod
    def get_embedding_by_chunk(db: Session, chunk_id: str) -> Optional[Embedding]:
        """Retrieve an embedding by chunk ID."""
        return db.query(Embedding).filter(Embedding.chunk_id == chunk_id).first()

    @staticmethod
    def list_embeddings_by_chunk(db: Session, chunk_id: str) -> List[Embedding]:
        """List all embeddings for a chunk."""
        return db.query(Embedding).filter(Embedding.chunk_id == chunk_id).all()

    @staticmethod
    def list_unsynced_embeddings(db: Session, limit: int = 100) -> List[Embedding]:
        """List embeddings not yet synced to ChromaDB."""
        return (
            db.query(Embedding)
            .filter(Embedding.is_synced == False)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update_embedding(
        db: Session,
        embedding_id: str,
        vector: Optional[List[float]] = None,
        chroma_id: Optional[str] = None,
        is_synced: Optional[bool] = None,
    ) -> Optional[Embedding]:
        """Update an embedding."""
        embedding = EmbeddingService.get_embedding(db, embedding_id)
        if not embedding:
            return None

        if vector is not None:
            embedding.vector = vector
        if chroma_id is not None:
            embedding.chroma_id = chroma_id
        if is_synced is not None:
            embedding.is_synced = is_synced
            if is_synced:
                embedding.last_synced_at = datetime.utcnow()

        embedding.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(embedding)
        return embedding

    @staticmethod
    def delete_embedding(db: Session, embedding_id: str) -> bool:
        """Delete an embedding."""
        embedding = db.query(Embedding).filter(Embedding.id == embedding_id).first()
        if not embedding:
            return False

        db.delete(embedding)
        db.commit()
        return True

    @staticmethod
    def mark_synced(
        db: Session, embedding_id: str, chroma_id: str
    ) -> Optional[Embedding]:
        """Mark an embedding as synced to ChromaDB."""
        embedding = EmbeddingService.get_embedding(db, embedding_id)
        if not embedding:
            return None

        embedding.is_synced = True
        embedding.chroma_id = chroma_id
        embedding.last_synced_at = datetime.utcnow()
        db.commit()
        db.refresh(embedding)
        return embedding

    @staticmethod
    def get_embeddings_by_document(db: Session, document_id: str) -> List[Embedding]:
        """Retrieve all embeddings for a document."""
        return (
            db.query(Embedding)
            .join(Chunk)
            .filter(Chunk.document_id == document_id)
            .all()
        )

    @staticmethod
    def get_embeddings_by_ids(db: Session, embedding_ids: List[str]) -> List[Embedding]:
        """Retrieve multiple embeddings by IDs."""
        return (
            db.query(Embedding)
            .filter(Embedding.id.in_(embedding_ids))
            .all()
        )
