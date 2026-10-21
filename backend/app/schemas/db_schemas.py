"""
Pydantic schemas for API requests and responses.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# Document Schemas
class DocumentCreate(BaseModel):
    """Schema for creating a document."""
    title: str = Field(..., min_length=1, max_length=255)
    source: Optional[str] = Field(None, max_length=512)
    metadata: Optional[Dict[str, Any]] = None


class DocumentUpdate(BaseModel):
    """Schema for updating a document."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    source: Optional[str] = Field(None, max_length=512)
    metadata: Optional[Dict[str, Any]] = None


class DocumentResponse(BaseModel):
    """Schema for document response."""
    id: str
    title: str
    source: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


class DocumentDetailResponse(DocumentResponse):
    """Detailed document response with chunk count."""
    chunk_count: int = 0


# Chunk Schemas
class ChunkCreate(BaseModel):
    """Schema for creating a chunk."""
    document_id: str
    chunk_index: int = Field(..., ge=0)
    text: str = Field(..., min_length=1)
    metadata: Optional[Dict[str, Any]] = None


class ChunkUpdate(BaseModel):
    """Schema for updating a chunk."""
    text: Optional[str] = Field(None, min_length=1)
    metadata: Optional[Dict[str, Any]] = None


class ChunkResponse(BaseModel):
    """Schema for chunk response."""
    id: str
    document_id: str
    chunk_index: int
    text: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


class ChunkDetailResponse(ChunkResponse):
    """Detailed chunk response with embedding info."""
    embedding_count: int = 0
    has_embedding: bool = False


# Embedding Schemas
class EmbeddingCreate(BaseModel):
    """Schema for creating an embedding."""
    chunk_id: str
    vector: List[float] = Field(..., min_items=1)
    model: Optional[str] = Field("text-embedding-ada-002", max_length=100)


class EmbeddingUpdate(BaseModel):
    """Schema for updating an embedding."""
    vector: Optional[List[float]] = None
    chroma_id: Optional[str] = None


class EmbeddingResponse(BaseModel):
    """Schema for embedding response."""
    id: str
    chunk_id: str
    model: Optional[str]
    chroma_id: Optional[str]
    is_synced: bool
    created_at: datetime
    updated_at: datetime
    last_synced_at: Optional[datetime]

    class Config:
        from_attributes = True


# Batch Operations
class BatchChunkCreate(BaseModel):
    """Schema for batch creating chunks."""
    document_id: str
    chunks: List[ChunkCreate]


class BatchEmbeddingSync(BaseModel):
    """Schema for batch syncing embeddings to ChromaDB."""
    embedding_ids: Optional[List[str]] = None
    document_id: Optional[str] = None
    sync_all_unsynced: bool = False


# ChromaDB Export Responses
class ChromaExportResponse(BaseModel):
    """Response for ChromaDB export operation."""
    status: str
    message: Optional[str] = None
    upserted_count: Optional[int] = None
    updated_db_count: Optional[int] = None
    error: Optional[str] = None


class ChromaIndexStats(BaseModel):
    """ChromaDB index statistics."""
    status: str
    stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# Search and Query
class DocumentSearch(BaseModel):
    """Schema for searching documents."""
    query: str = Field(..., min_length=1)


class SearchResponse(BaseModel):
    """Generic search response."""
    count: int
    results: List[Dict[str, Any]]
