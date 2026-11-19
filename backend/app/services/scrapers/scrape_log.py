"""
Read/write helpers for the scrape_log table (history of every re-scrape page check).
"""

from collections import Counter
from typing import Optional

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.models import ScrapeLog

RUN_KEY = "__run__"
OK_OUTCOMES = ("new", "changed", "unchanged")


def table_exists(db: Session) -> bool:
    return inspect(db.get_bind()).has_table(ScrapeLog.__tablename__)


def record(
    db: Session,
    run_id: str,
    doc_key: str,
    url: str,
    outcome: str,
    *,
    document_id: Optional[str] = None,
    content_hash: Optional[str] = None,
    http_status: Optional[int] = None,
    word_count: Optional[int] = None,
    detail: Optional[str] = None,
) -> ScrapeLog:
    row = ScrapeLog(
        run_id=run_id,
        doc_key=doc_key,
        url=url,
        outcome=outcome,
        document_id=document_id,
        content_hash=content_hash,
        http_status=http_status,
        word_count=word_count,
        detail=detail[:500] if detail else None,
    )
    db.add(row)
    return row


def consecutive_failures(db: Session, doc_key: str, limit: int = 10) -> int:
    """How many of the most recent checks of this page failed in a row."""
    rows = (
        db.query(ScrapeLog.outcome)
        .filter(ScrapeLog.doc_key == doc_key)
        .order_by(ScrapeLog.checked_at.desc(), ScrapeLog.id.desc())
        .limit(limit)
        .all()
    )
    n = 0
    for (outcome,) in rows:
        if outcome != "failed":
            break
        n += 1
    return n


def latest_run_id(db: Session) -> Optional[str]:
    row = db.query(ScrapeLog.run_id).order_by(ScrapeLog.checked_at.desc(), ScrapeLog.id.desc()).first()
    return row[0] if row else None


def run_counts(db: Session, run_id: str) -> Counter:
    rows = db.query(ScrapeLog.outcome).filter(ScrapeLog.run_id == run_id).all()
    return Counter(r[0] for r in rows)


def failing_pages(db: Session, run_id: str) -> list[tuple[str, str, Optional[str]]]:
    rows = (
        db.query(ScrapeLog.doc_key, ScrapeLog.url, ScrapeLog.detail)
        .filter(ScrapeLog.run_id == run_id, ScrapeLog.outcome == "failed")
        .order_by(ScrapeLog.doc_key)
        .all()
    )
    return [(r[0], r[1], r[2]) for r in rows]
