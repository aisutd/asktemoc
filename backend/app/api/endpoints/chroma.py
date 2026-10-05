"""
FastAPI endpoints for ChromaDB export operations.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.services import EmbeddingService, DocumentService
from app.services.chroma_service import ChromaService
from app.schemas.db_schemas import ChromaExportResponse, ChromaIndexStats

router = APIRouter(prefix="/chroma", tags=["chroma"])


def get_chroma_service():
    """Dependency to get ChromaService."""
    try:
        return ChromaService()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize Chroma service: {str(e)}",
        )


@router.post("/export/document/{doc_id}", response_model=ChromaExportResponse)
def export_document_embeddings(
    doc_id: str,
    db: Session = Depends(get_db),
    chroma_svc: ChromaService = Depends(get_chroma_service),
):
    """Export all embeddings for a specific document to ChromaDB."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    result = chroma_svc.export_document_embeddings(db=db, document_id=doc_id)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error"),
        )

    return ChromaExportResponse(
        status=result.get("status"),
        message=f"Exported {result.get('upserted_count', 0)} embeddings",
        upserted_count=result.get("upserted_count"),
        updated_db_count=result.get("updated_db_count"),
    )


@router.post("/export/unsynced", response_model=ChromaExportResponse)
def export_unsynced_embeddings(
    batch_size: int = 100,
    db: Session = Depends(get_db),
    chroma_svc: ChromaService = Depends(get_chroma_service),
):
    """Export all unsynced embeddings to ChromaDB."""
    result = chroma_svc.export_unsynced_embeddings(db=db, batch_size=batch_size)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error"),
        )

    return ChromaExportResponse(
        status=result.get("status"),
        message=f"Exported {result.get('upserted_count', 0)} embeddings",
        upserted_count=result.get("upserted_count"),
        updated_db_count=result.get("updated_db_count"),
    )


@router.post("/export/batch", response_model=ChromaExportResponse)
def export_batch_embeddings(
    embedding_ids: List[str],
    db: Session = Depends(get_db),
    chroma_svc: ChromaService = Depends(get_chroma_service),
):
    """Export a batch of specific embeddings to ChromaDB."""
    embeddings = EmbeddingService.get_embeddings_by_ids(db=db, embedding_ids=embedding_ids)

    if not embeddings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No embeddings found"
        )

    result = chroma_svc.upsert_vectors(db=db, embeddings=embeddings)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error"),
        )

    return ChromaExportResponse(
        status=result.get("status"),
        message=f"Exported {result.get('upserted_count', 0)} embeddings",
        upserted_count=result.get("upserted_count"),
        updated_db_count=result.get("updated_db_count"),
    )


@router.delete("/vectors", response_model=ChromaExportResponse)
def delete_vectors_from_chroma(
    vector_ids: List[str],
    chroma_svc: ChromaService = Depends(get_chroma_service),
):
    """Delete vectors from ChromaDB."""
    if not vector_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No vector IDs provided"
        )

    result = chroma_svc.delete_from_chroma(vector_ids=vector_ids)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error"),
        )

    return ChromaExportResponse(
        status=result.get("status"),
        message=f"Deleted {result.get('deleted_count', 0)} vectors",
    )


@router.get("/index/stats", response_model=ChromaIndexStats)
def get_index_statistics(
    chroma_svc: ChromaService = Depends(get_chroma_service),
):
    """Get ChromaDB collection statistics."""
    result = chroma_svc.get_collection_stats()

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error"),
        )

    return ChromaIndexStats(
        status=result.get("status"),
        stats=result.get("stats"),
    )


@router.get("/search", response_model=dict)
def search_chroma(
    query_vector: List[float],
    top_k: int = 10,
    db: Session = Depends(get_db),
    chroma_svc: ChromaService = Depends(get_chroma_service),
):
    """Search ChromaDB collection with query vector."""
    if not query_vector:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Query vector required"
        )

    result = chroma_svc.search_chroma(query_vector=query_vector, top_k=top_k)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error"),
        )

    return result
