"""
FastAPI endpoints for document management.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.services import DocumentService, ChunkService, EmbeddingService
from app.schemas.db_schemas import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentDetailResponse,
    DocumentSearch,
    ChunkCreate,
    ChunkUpdate,
    ChunkResponse,
    ChunkDetailResponse,
    EmbeddingCreate,
    EmbeddingUpdate,
    EmbeddingResponse,
    BatchChunkCreate,
    SearchResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


# Document Endpoints
@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    doc_data: DocumentCreate, db: Session = Depends(get_db)
):
    """Create a new document."""
    document = DocumentService.create_document(
        db=db,
        title=doc_data.title,
        source=doc_data.source,
        metadata=doc_data.metadata,
    )
    return document


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
):
    """List all documents with pagination."""
    documents = DocumentService.list_documents(
        db=db, skip=skip, limit=limit, include_deleted=include_deleted
    )
    return documents


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
def get_document(doc_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific document with chunk count."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    chunk_count = len(document.chunks)
    return {**document.__dict__, "chunk_count": chunk_count}


@router.put("/{doc_id}", response_model=DocumentResponse)
def update_document(
    doc_id: str, doc_data: DocumentUpdate, db: Session = Depends(get_db)
):
    """Update a document."""
    document = DocumentService.update_document(
        db=db,
        doc_id=doc_id,
        title=doc_data.title,
        source=doc_data.source,
        metadata=doc_data.metadata,
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return document


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: str, hard_delete: bool = False, db: Session = Depends(get_db)
):
    """Delete a document (soft or hard delete)."""
    success = DocumentService.delete_document(db=db, doc_id=doc_id, hard_delete=hard_delete)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return None


@router.post("/search", response_model=SearchResponse)
def search_documents(
    search_data: DocumentSearch, db: Session = Depends(get_db)
):
    """Search documents by title or source."""
    results = DocumentService.search_documents(db=db, query_str=search_data.query)
    return {"count": len(results), "results": [dict(d.__dict__) for d in results]}


# Chunk Endpoints
@router.post("/{doc_id}/chunks", response_model=ChunkResponse, status_code=status.HTTP_201_CREATED)
def create_chunk(
    doc_id: str, chunk_data: ChunkCreate, db: Session = Depends(get_db)
):
    """Create a chunk for a document."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    chunk = ChunkService.create_chunk(
        db=db,
        document_id=doc_id,
        chunk_index=chunk_data.chunk_index,
        text=chunk_data.text,
        metadata=chunk_data.metadata,
    )
    return chunk


@router.post("/{doc_id}/chunks/batch", response_model=List[ChunkResponse], status_code=status.HTTP_201_CREATED)
def batch_create_chunks(
    doc_id: str, batch_data: BatchChunkCreate, db: Session = Depends(get_db)
):
    """Batch create chunks for a document."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    chunks = []
    for chunk_data in batch_data.chunks:
        chunk = ChunkService.create_chunk(
            db=db,
            document_id=doc_id,
            chunk_index=chunk_data.chunk_index,
            text=chunk_data.text,
            metadata=chunk_data.metadata,
        )
        chunks.append(chunk)

    return chunks


@router.get("/{doc_id}/chunks", response_model=List[ChunkResponse])
def list_document_chunks(
    doc_id: str,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db),
):
    """List all chunks for a document."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    chunks = ChunkService.list_chunks_by_document(
        db=db, document_id=doc_id, skip=skip, limit=limit
    )
    return chunks


@router.get("/chunks/{chunk_id}", response_model=ChunkDetailResponse)
def get_chunk(chunk_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific chunk."""
    chunk = ChunkService.get_chunk(db=db, chunk_id=chunk_id)
    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found"
        )

    embedding_count = len(chunk.embeddings)
    has_embedding = embedding_count > 0

    return {**chunk.__dict__, "embedding_count": embedding_count, "has_embedding": has_embedding}


@router.put("/chunks/{chunk_id}", response_model=ChunkResponse)
def update_chunk(
    chunk_id: str, chunk_data: ChunkUpdate, db: Session = Depends(get_db)
):
    """Update a chunk."""
    chunk = ChunkService.update_chunk(
        db=db,
        chunk_id=chunk_id,
        text=chunk_data.text,
        metadata=chunk_data.metadata,
    )
    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found"
        )
    return chunk


@router.delete("/chunks/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chunk(
    chunk_id: str, hard_delete: bool = False, db: Session = Depends(get_db)
):
    """Delete a chunk."""
    success = ChunkService.delete_chunk(db=db, chunk_id=chunk_id, hard_delete=hard_delete)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found"
        )
    return None


# Embedding Endpoints
@router.post("/chunks/{chunk_id}/embeddings", response_model=EmbeddingResponse, status_code=status.HTTP_201_CREATED)
def create_embedding(
    chunk_id: str, embedding_data: EmbeddingCreate, db: Session = Depends(get_db)
):
    """Create an embedding for a chunk."""
    chunk = ChunkService.get_chunk(db=db, chunk_id=chunk_id)
    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found"
        )

    embedding = EmbeddingService.create_embedding(
        db=db,
        chunk_id=chunk_id,
        vector=embedding_data.vector,
        model=embedding_data.model,
    )
    return embedding


@router.get("/embeddings/{embedding_id}", response_model=EmbeddingResponse)
def get_embedding(embedding_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific embedding."""
    embedding = EmbeddingService.get_embedding(db=db, embedding_id=embedding_id)
    if not embedding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Embedding not found"
        )
    return embedding


@router.put("/embeddings/{embedding_id}", response_model=EmbeddingResponse)
def update_embedding(
    embedding_id: str,
    embedding_data: EmbeddingUpdate,
    db: Session = Depends(get_db),
):
    """Update an embedding."""
    embedding = EmbeddingService.update_embedding(
        db=db,
        embedding_id=embedding_id,
        vector=embedding_data.vector,
        chroma_id=embedding_data.chroma_id,
    )
    if not embedding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Embedding not found"
        )
    return embedding


@router.delete("/embeddings/{embedding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_embedding(embedding_id: str, db: Session = Depends(get_db)):
    """Delete an embedding."""
    success = EmbeddingService.delete_embedding(db=db, embedding_id=embedding_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Embedding not found"
        )
    return None
