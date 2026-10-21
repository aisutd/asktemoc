"""
Database models for documents, chunks, and embeddings.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Document(Base):
    """
    Stores document metadata with optional embedding information.
    """
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)  # UUID or custom ID
    title = Column(String(255), nullable=False, index=True)
    source = Column(String(512), nullable=True)  # URL, file path, etc.
    doc_metadata = Column(JSON, nullable=True)  # Flexible metadata storage
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False, index=True)  # Soft delete
    
    # Relationships
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, title={self.title})>"


class Chunk(Base):
    """
    Stores text chunks extracted from documents.
    """
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, index=True)  # UUID or chunk_id
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)  # Sequence position within document
    text = Column(Text, nullable=False)
    chunk_metadata = Column(JSON, nullable=True)  # Custom metadata for chunk
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False, index=True)  # Soft delete
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    embeddings = relationship("Embedding", back_populates="chunk", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_document_chunk_index", "document_id", "chunk_index"),
    )

    def __repr__(self):
        return f"<Chunk(id={self.id}, document_id={self.document_id}, index={self.chunk_index})>"


class Embedding(Base):
    """
    Stores embedding vectors and related metadata.
    Links chunks to their vector representations.
    """
    __tablename__ = "embeddings"

    id = Column(String, primary_key=True, index=True)  # UUID or chroma_id
    chunk_id = Column(String, ForeignKey("chunks.id"), nullable=False, index=True)
    vector = Column(JSON, nullable=True)  # Store as JSON array for flexibility
    model = Column(String(100), nullable=True)  # Model used (e.g., "text-embedding-ada-002")
    chroma_id = Column(String(255), nullable=True, index=True)  # Reference to ChromaDB ID
    is_synced = Column(Boolean, default=False, index=True)  # Track sync status
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime, nullable=True)

    # Relationships
    chunk = relationship("Chunk", back_populates="embeddings")

    __table_args__ = (
        Index("idx_chroma_id", "chroma_id"),
        Index("idx_is_synced", "is_synced"),
    )

    def __repr__(self):
        return f"<Embedding(id={self.id}, chunk_id={self.chunk_id}, chroma_id={self.chroma_id})>"
