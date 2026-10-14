"""
/api/ingest — receives scraper payloads, chunks text, embeds via OpenAI,
and stores Documents + Chunks + Embeddings in Postgres (pgvector).

Chunking stance (production RAG for chatbots, 2026):
- Recursive / structure-aware splitting is the usual default (paragraph → line → sentence)
  rather than blindly fixed characters; overlapping windows (~10–20%) preserves boundary context.
- Semantic or hierarchical chunking can win on messy multi-topic docs; parent-document patterns
  (small chunks indexed, larger parent fed to the LLM) are common once you measure retrieval misses.
- For well-scoped artifacts (single degree catalog page), we keep **one logical chunk**: the database
  row stores **full** scraped text (`Degree program:` + body); vectors are computed from only as much
  of that text as the embedding API allows (~8000 tokens from the beginning), so metadata marks
  `embedding_input_truncated` when the stored chunk is longer than the embedded prefix.
"""

import random
import time
import uuid
import logging
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.orm import Session
from openai import OpenAI

from app.db.database import get_db
from app.db.models import Document, Chunk, Embedding
from app.core.config import get_settings
from app.core.retry_helpers import call_openai_embedding_with_retries

logger = logging.getLogger(__name__)
router = APIRouter()

# text-embedding-3-large token limit is 8191 — use ~2000 tokens per chunk
# for good retrieval granularity while preserving meaningful context.
CHUNK_TOKENS = 2000
CHUNK_OVERLAP_TOKENS = 100
TIKTOKEN_MODEL = "text-embedding-3-large"

_EMBED_SAFE_MAX_TOKENS = 8000  # below OpenAI 8192 cap for text-embedding-3-large inputs


# --------------------------------------------------------------------------- #
# Pydantic schema (matches publisher.py build_payload output)
# --------------------------------------------------------------------------- #

class IngestPayload(BaseModel):
    url: str
    page_title: str
    timestamp: Optional[str] = None
    text_content: Optional[str] = None
    html_content: Optional[str] = None
    chunks: Optional[list] = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_utd_catalog_degree_detail_page(url: str) -> bool:
    """
    True for a single-program catalog URL (degree page), not the program listing hub.

    Examples (detail → True):
      .../catalog.utdallas.edu/.../programs/aht/animation-and-games
    Examples (listing hub → False):
      .../undergraduate/programs
    """
    try:
        p = urlparse(url)
        if "catalog.utdallas.edu" not in (p.netloc or "").lower():
            return False
        parts = [x for x in (p.path or "").strip("/").split("/") if x]
        if "programs" not in parts:
            return False
        idx = parts.index("programs")
        # At least school code + degree slug after "programs", e.g. aht/ba-xyz
        return len(parts) >= idx + 3
    except Exception:
        return False


_CATALOG_TRUNCATION_NOTE = (
    "\n\n[Truncated for embedding token limit; see catalog URL for full requirements.]"
)


def _fit_catalog_degree_text_for_embedding(
    page_title: str, body: str, max_tokens: int
) -> tuple[str, bool]:
    """
    One embed string per catalog degree.

    Payload is ``Degree program: {title}\\n\\n`` plus scraped body (requirements plus optional
    example tables — concatenated text from catalog_scraper). We do not embed the title alone.

    When the full ``Degree program …`` string exceeds ``max_tokens``, trims from the end of ``body``
    for the embedding API only; the full canonical string is persisted in ``Chunk.text`` by the
    endpoint, not this return value alone.
    """
    import tiktoken

    enc = tiktoken.encoding_for_model("text-embedding-ada-002")
    prefix = f"Degree program: {page_title.strip()}\n\n"
    body_stripped = (body or "").strip()
    body_ids = enc.encode(body_stripped)

    def pack(body_token_count: int) -> str:
        bod = enc.decode(body_ids[:body_token_count])
        if body_token_count >= len(body_ids):
            return prefix + bod
        return prefix + bod + _CATALOG_TRUNCATION_NOTE

    canon = prefix + body_stripped
    if len(enc.encode(canon)) <= max_tokens:
        return canon, False

    lo, hi_b = 0, len(body_ids)
    best = ""
    ans = -1
    while lo <= hi_b:
        mid = (lo + hi_b) // 2
        cand = pack(mid)
        if len(enc.encode(cand)) <= max_tokens:
            best = cand
            ans = mid
            lo = mid + 1
        else:
            hi_b = mid - 1

    if ans >= 0:
        return best, ans < len(body_ids)

    shortened = prefix
    trimmed = shortened + "" + _CATALOG_TRUNCATION_NOTE
    while len(enc.encode(trimmed)) > max_tokens and len(shortened) > 48:
        shortened = shortened[:-200]
        trimmed = shortened + "" + _CATALOG_TRUNCATION_NOTE
    return trimmed, True


def _catalog_degree_full_text(page_title: str, body: str) -> str:
    """Full display text stored in Chunk.text (never truncated for DB)."""
    return f"Degree program: {page_title.strip()}\n\n{(body or '').strip()}".strip()


def _truncate_text_for_embedding_only(text: str, max_tokens: int) -> tuple[str, bool]:
    """
    Truncate from the end so token count <= max_tokens (prefix preserved).
    Used when Chunk.text stores the full string but the embedding model has a smaller input limit.
    """
    import tiktoken

    enc = tiktoken.encoding_for_model("text-embedding-ada-002")
    t = text or ""
    ids = enc.encode(t)
    if len(ids) <= max_tokens:
        return t, False

    lo, hi = 1, len(ids)
    best = ""
    ans = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = enc.decode(ids[:mid])
        if len(enc.encode(cand)) <= max_tokens:
            best = cand
            ans = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if ans >= 0:
        return best, True
    return enc.decode(ids[:min(len(ids), max_tokens)]), True


def _approx_tokens(text: str) -> int:
    import tiktoken

    enc = tiktoken.encoding_for_model("text-embedding-ada-002")
    return len(enc.encode(text))


def _split_text(text: str) -> list[str]:
    """
    Token-aware recursive splitter using tiktoken.
    Splits on paragraph → sentence → word boundaries before resorting to chars.
    Targets CHUNK_TOKENS tokens per chunk with CHUNK_OVERLAP_TOKENS overlap.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    import tiktoken

    enc = tiktoken.encoding_for_model("text-embedding-ada-002")  # same tokeniser family

    def token_len(t: str) -> int:
        return len(enc.encode(t))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        length_function=token_len,
        separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
    )

    chunks = splitter.split_text(text)
    return [c.strip() for c in chunks if c.strip()]


def _embed_texts(texts: list[str], settings) -> list[list[float]]:
    """Call OpenAI embeddings API and return vectors (retries transient API / network errors)."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def _call():
        response = client.embeddings.create(
            input=texts,
            model=settings.OPENAI_EMBEDDING_MODEL,
        )
        return [item.embedding for item in response.data]

    return call_openai_embedding_with_retries(_call)


def _upsert_document(
    db: Session, url: str, title: str, doc_metadata: Optional[dict] = None
) -> Document:
    """Return existing document for this URL (deleting old chunks) or create new. Caller commits."""
    doc = db.query(Document).filter(Document.source == url, Document.is_deleted == False).first()

    if doc:
        for chunk in db.query(Chunk).filter(Chunk.document_id == doc.id).all():
            db.delete(chunk)
        doc.title = title
        doc.updated_at = datetime.now(timezone.utc)
        if doc_metadata is not None:
            merged = dict(doc.doc_metadata or {})
            merged.update(doc_metadata)
            doc.doc_metadata = merged
        db.flush()
        return doc

    doc = Document(
        id=str(uuid.uuid4()),
        title=title,
        source=url,
        doc_metadata=doc_metadata or {},
    )
    db.add(doc)
    db.flush()
    db.refresh(doc)
    return doc


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #

@router.post("/ingest", status_code=status.HTTP_200_OK)
def ingest(payload: IngestPayload, db: Session = Depends(get_db)):
    """
    Ingest the payload into the database.
    Prefers raw_text, with a fallback to html_content stripped.
    Priority:
    If catalog degree pages: do not split onto chunks.
    If chunks are provided: use them as is.
    If no chunks are provided: chunk using tiktoken.
    Truncate to safe max tokens, then embed.
    Upsert into documents, chunks, and embeddings tables.
    """
    settings = get_settings()

    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # Resolve raw text — prefer text_content, fall back to html_content stripped
    raw_text: Optional[str] = payload.text_content
    if not raw_text and payload.html_content:
        from html.parser import HTMLParser
        class _Strip(HTMLParser):
            def __init__(self):
                super().__init__()
                self._parts: list[str] = []
            def handle_data(self, data):
                if data.strip():
                    self._parts.append(data.strip())
            def text(self):
                return " ".join(self._parts)
        p = _Strip()
        p.feed(payload.html_content)
        raw_text = p.text()

    if not raw_text and not payload.chunks:
        raise HTTPException(status_code=422, detail="No text content or chunks provided")

    catalog_degree_page = _is_utd_catalog_degree_detail_page(payload.url)

    doc_metadata = None
    if catalog_degree_page:
        doc_metadata = {
            "catalog_degree_page": True,
            "degree_title": payload.page_title.strip(),
        }

    # Build (full text for DB, substring for embedding API, embedding_input_truncated)
    chunk_triples: list[tuple[str, str, bool]] = []

    if catalog_degree_page:
        if payload.chunks:
            merged = "\n\n".join(
                str(c).strip() for c in payload.chunks if str(c).strip()
            ).strip()
        else:
            merged = (raw_text or "").strip()

        full_text = _catalog_degree_full_text(payload.page_title, merged)
        embed_text, emb_trunc = _fit_catalog_degree_text_for_embedding(
            payload.page_title, merged, _EMBED_SAFE_MAX_TOKENS
        )
        chunk_triples.append((full_text, embed_text, emb_trunc))
        if emb_trunc:
            logger.info(
                "Catalog degree embedding input trimmed to ~%s tokens (full text stored): %s",
                _approx_tokens(embed_text),
                payload.url,
            )
    elif payload.chunks:
        for c in payload.chunks:
            part = c if isinstance(c, str) else str(c)
            if not str(part).strip():
                continue
            part = str(part).strip()
            et, tr = _truncate_text_for_embedding_only(part, _EMBED_SAFE_MAX_TOKENS)
            chunk_triples.append((part, et, tr))
    else:
        for sp in _split_text(raw_text or ""):
            et, tr = _truncate_text_for_embedding_only(sp, _EMBED_SAFE_MAX_TOKENS)
            chunk_triples.append((sp, et, tr))

    if not chunk_triples:
        raise HTTPException(status_code=422, detail="Text produced zero chunks after splitting")

    if any(t[2] for t in chunk_triples):
        if doc_metadata is None:
            doc_metadata = {}
        doc_metadata["embedding_input_truncated"] = True

    embed_inputs = [t[1] for t in chunk_triples]
    try:
        vectors = _embed_texts(embed_inputs, settings)
    except Exception as e:
        logger.error(f"OpenAI embedding failed for {payload.url}: {e}")
        raise HTTPException(status_code=502, detail=f"Embedding failed: {e}")

    chunk_meta_common = {}
    if catalog_degree_page:
        chunk_meta_common = {
            "catalog_degree_page": True,
            "degree_title": payload.page_title.strip(),
            "embedding_unit": "full_degree_page",
        }

    model_name = settings.OPENAI_EMBEDDING_MODEL

    doc: Optional[Document] = None
    for commit_try in range(12):
        try:
            doc = _upsert_document(
                db, payload.url, payload.page_title, doc_metadata=doc_metadata
            )
            for i, ((stored_text, _embed_in, emb_trunc), vector) in enumerate(
                zip(chunk_triples, vectors)
            ):
                md = dict(chunk_meta_common) if chunk_meta_common else {}
                if emb_trunc:
                    md["embedding_input_truncated"] = True
                chunk = Chunk(
                    id=str(uuid.uuid4()),
                    document_id=doc.id,
                    chunk_index=i,
                    text=stored_text,
                    chunk_metadata=md,
                )
                db.add(chunk)
                db.flush()

                embedding = Embedding(
                    id=str(uuid.uuid4()),
                    chunk_id=chunk.id,
                    vector=vector,
                    model=model_name,
                    is_synced=True,
                )
                db.add(embedding)
            db.commit()
            break
        except IntegrityError as e:
            db.rollback()
            logger.error("Ingest integrity error for %s: %s", payload.url, e)
            raise HTTPException(status_code=409, detail=f"Database conflict: {e}") from e
        except (OperationalError, DBAPIError) as e:
            db.rollback()
            if commit_try >= 11:
                logger.error("Postgres commit failed after retries for %s: %s", payload.url, e)
                raise HTTPException(
                    status_code=503,
                    detail="Database temporarily unavailable; retry later.",
                ) from e
            wait = min(2.0 * (2**commit_try), 120) + random.uniform(0, 0.35)
            logger.warning(
                "Postgres ingest commit retry %s/12 (%s): %s; sleeping %.1fs",
                commit_try + 1,
                e.__class__.__name__,
                str(e)[:200],
                wait,
            )
            time.sleep(wait)

    assert doc is not None

    n = len(chunk_triples)
    embedding_input_truncated = any(t[2] for t in chunk_triples)
    logger.info(
        f"Ingested {n} chunks for {payload.url} (catalog_degree={catalog_degree_page}"
        f", embedding_input_truncated={embedding_input_truncated})"
    )
    return {
        "status": "ok",
        "url": payload.url,
        "chunks_ingested": n,
        "document_id": doc.id,
        "catalog_degree_page": catalog_degree_page,
        "embedding_input_truncated": embedding_input_truncated,
    }
