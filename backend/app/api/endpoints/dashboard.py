"""
FastAPI endpoints for dashboard and analytics.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.document_management import DocumentManagementUtils
from app.db.services import DocumentService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
def get_dashboard_overview(db: Session = Depends(get_db)):
    """Get overall dashboard statistics."""
    sync_status = DocumentManagementUtils.get_sync_status_summary(db=db)
    documents = DocumentManagementUtils.get_all_documents_dashboard(db=db)

    return {
        "sync_status": sync_status,
        "documents": documents,
        "total_documents": len(documents),
    }


@router.get("/document/{doc_id}/stats")
def get_document_stats(doc_id: str, db: Session = Depends(get_db)):
    """Get detailed statistics for a specific document."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    stats = DocumentManagementUtils.get_document_statistics(db=db, doc_id=doc_id)
    return stats


@router.get("/document/{doc_id}/export")
def export_document_json(doc_id: str, db: Session = Depends(get_db)):
    """Export document with all chunks and embeddings as JSON."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    export_data = DocumentManagementUtils.export_document_to_json(db=db, doc_id=doc_id)
    return export_data


@router.post("/document/{doc_id}/duplicate")
def duplicate_document(
    doc_id: str, new_title: Optional[str] = None, db: Session = Depends(get_db)
):
    """Duplicate a document with all its chunks and embeddings."""
    document = DocumentService.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    new_doc = DocumentManagementUtils.duplicate_document_with_chunks(
        db=db, source_doc_id=doc_id, new_title=new_title
    )

    if not new_doc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to duplicate document",
        )

    return {
        "status": "success",
        "original_id": doc_id,
        "duplicate_id": new_doc.id,
        "duplicate_title": new_doc.title,
    }


@router.post("/documents/batch-delete")
def batch_delete_documents(
    doc_ids: List[str], hard_delete: bool = False, db: Session = Depends(get_db)
):
    """Batch delete multiple documents."""
    if not doc_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No document IDs provided"
        )

    result = DocumentManagementUtils.batch_delete_documents(
        db=db, doc_ids=doc_ids, hard_delete=hard_delete
    )

    return result


@router.get("/search")
def search_content(query: str, limit: int = 100, db: Session = Depends(get_db)):
    """Search for content across all documents."""
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Search query required"
        )

    results = DocumentManagementUtils.search_content_across_documents(
        db=db, search_query=query, limit=limit
    )

    return {
        "query": query,
        "result_count": len(results),
        "results": results,
    }


@router.get("/activity")
def get_recent_activity(days: int = 7, limit: int = 100, db: Session = Depends(get_db)):
    """Get recent activity across documents, chunks, and embeddings."""
    activity = DocumentManagementUtils.get_recent_activity(
        db=db, days=days, limit=limit
    )
    return activity


@router.get("/sync-status")
def get_sync_status(db: Session = Depends(get_db)):
    """Get current sync status with ChromaDB."""
    sync_status = DocumentManagementUtils.get_sync_status_summary(db=db)
    return sync_status
