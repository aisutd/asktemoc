"""
Scheduled re-scrape: fetch the UTD catalog and web pages, detect changed pages by content
hash, and re-embed only those.

    python -m app.services.scrapers.rescrape --dry-run     # fetch + compare, write nothing
    python -m app.services.scrapers.rescrape               # apply changes
    python -m app.services.scrapers.rescrape --status      # last run summary

Run it weekly from a Cloud Run Job (see deploy/deploy_rescrape_job.sh).

Per page: fetch (HTTP status checked) -> validate -> clean (certificate sections) ->
normalized sha256 -> compare with the hash stored on the document. Changed pages are
chunked, embedded and swapped in one transaction together with a scrape_log row, so the
log can never say a page is current while its embeddings failed. A page that is not
HTTP 200 or has no real content is logged as failed and the stored document is kept;
only after FAIL_LIMIT consecutive 404/410 responses is a document soft-deleted.
Two guards stop a run before it writes anything: too many pages changing at once, or
too many failing (a site redesign, a broken selector, or an outage).
"""

import argparse
import asyncio
import hashlib
import logging
import re
import sys
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime
from typing import Callable, Optional, Protocol

import tiktoken
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, Embedding
from . import scrape_log
from .content import (
    clean_markdown,
    needs_section,
    prepare_catalog_text,
    sanitize,
    sections,
    text_hash,
    validate,
    word_count,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://catalog.utdallas.edu/2025/undergraduate/programs"
OVERVIEW_FOLDER = "undergraduate_catalog_overview"
WEB_PAGES = (
    ("utd_home", "https://www.utdallas.edu/"),
    ("utd_academics", "https://www.utdallas.edu/academics/"),
    ("utd_tuition_rates", "https://bursar.utdallas.edu/tuition/tuition-rates/"),
)

FAIL_LIMIT = 3                  # consecutive 404/410 checks before a document is soft-deleted
GONE_STATUSES = (404, 410)
MAX_CHANGED_FRACTION = 0.30     # of existing pages; above this the run aborts without writing
MAX_FAILED_FRACTION = 0.30      # of all pages; above this the run aborts without writing
GUARD_MIN_PAGES = 10            # guards only apply once a run has at least this many pages
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
EMBED_BATCH = 100
EMBED_DIMS = 1536
PRICE_PER_M_TOKENS = 0.02       # USD, text-embedding-3-small

_enc = tiktoken.get_encoding("cl100k_base")


@lru_cache(maxsize=1)
def _embedding_model() -> str:
    from app.core.config import get_settings

    return get_settings().OPENAI_EMBEDDING_MODEL


# --- data ------------------------------------------------------------------

@dataclass
class Page:
    status: Optional[int]
    text: Optional[str]
    example_url: Optional[str] = None
    error: Optional[str] = None


class Fetcher(Protocol):
    async def links(self) -> list[tuple[str, str]]: ...
    async def page(self, url: str) -> Page: ...
    async def markdown(self, url: str) -> Page: ...


@dataclass
class Unit:
    key: str        # e.g. "bachelor_of_science_in_computer_science/requirements.txt"
    title: str      # e.g. "bachelor_of_science_in_computer_science/requirements"
    url: str
    folder: str
    file: str
    kind: str       # catalog | web | derived


@dataclass
class Item:
    unit: Unit
    status: Optional[int] = None
    text: Optional[str] = None      # prepared text to store
    error: Optional[str] = None
    hash: Optional[str] = None
    words: int = 0
    outcome: str = ""               # new | changed | unchanged | failed | duplicate
    detail: str = ""


@dataclass
class RunSummary:
    run_id: str
    dry_run: bool
    counts: Counter = field(default_factory=Counter)
    aborted: bool = False
    reason: str = ""
    new_chunks: int = 0
    merged_chunks: int = 0
    tokens: int = 0
    items: list = field(default_factory=list)

    @property
    def est_cost(self) -> float:
        return self.tokens / 1e6 * PRICE_PER_M_TOKENS


def doc_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def chunk_text(text: str) -> list[str]:
    tokens = _enc.encode(text)
    chunks, start = [], 0
    while start < len(tokens):
        end = min(start + CHUNK_SIZE, len(tokens))
        chunks.append(_enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    from app.core.config import get_settings
    from app.core.retry_helpers import call_openai_embedding_with_retries

    settings = get_settings()
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]

        def _call(batch=batch):
            resp = client.embeddings.create(model=settings.OPENAI_EMBEDDING_MODEL, input=batch)
            return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

        out.extend(call_openai_embedding_with_retries(_call))
    return out


# --- live fetching ---------------------------------------------------------

class LiveFetcher:
    """Playwright for catalog pages, Crawl4AI for the web pages. Use as an async context manager."""

    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = rate_limit
        self._last = 0.0

    async def __aenter__(self):
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        return self

    async def __aexit__(self, *exc):
        await self._browser.close()
        await self._pw.stop()

    async def _throttle(self):
        wait = self.rate_limit - (asyncio.get_event_loop().time() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = asyncio.get_event_loop().time()

    async def links(self) -> list[tuple[str, str]]:
        from .catalog_scraper import UTDCatalogScraper

        scraper = UTDCatalogScraper(rate_limit=self.rate_limit, output_dir=tempfile.mkdtemp())
        page = await self._browser.new_page()
        try:
            return await scraper.find_program_links(page)
        finally:
            await page.close()

    async def page(self, url: str) -> Page:
        from urllib.parse import urljoin
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        context = await self._browser.new_context()
        pg = await context.new_page()
        try:
            await self._throttle()
            resp = await pg.goto(url, wait_until="networkidle", timeout=30000)
            status = resp.status if resp else None
            main = await pg.query_selector("main, .main-content, #content, .content")
            if main:
                text = await main.inner_text()
            else:
                await pg.evaluate(
                    "() => document.querySelectorAll('script, style, nav, header, footer').forEach(el => el.remove())"
                )
                text = await (await pg.query_selector("body")).inner_text()
            example_url = None
            for link in await pg.query_selector_all("a"):
                label = (await link.inner_text() or "").lower()
                href = await link.get_attribute("href")
                if href and "example" in label and "degree requirements" in label:
                    example_url = urljoin(url, href)
                    break
            return Page(status, text, example_url)
        except PlaywrightTimeoutError:
            return Page(None, None, error="timeout")
        except Exception as e:  # network or page errors must not stop the whole run
            return Page(None, None, error=f"{type(e).__name__}: {e}"[:200])
        finally:
            await context.close()

    async def markdown(self, url: str) -> Page:
        from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

        try:
            await self._throttle()
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(
                    url=url,
                    config=CrawlerRunConfig(
                        cache_mode=CacheMode.BYPASS, word_count_threshold=10, remove_overlay_elements=True
                    ),
                )
            # status_code is the first response (a 301 for www.utdallas.edu); the final one is what counts
            status = getattr(result, "redirected_status_code", None) or result.status_code
            return Page(status, str(result.markdown or ""))
        except Exception as e:
            return Page(None, None, error=f"{type(e).__name__}: {e}"[:200])


# --- phase 1: fetch and classify -------------------------------------------

def _catalog_item(unit: Unit, page: Page) -> Item:
    item = Item(unit, status=page.status)
    err = page.error or validate(page.text, page.status)
    if err:
        item.error = err
        return item
    text, err = prepare_catalog_text(unit.folder, page.text)
    if err is None:
        err = validate(text, None)
    if err:
        item.error = err
        return item
    item.text, item.hash, item.words = text, text_hash(text), word_count(text)
    return item


def _web_item(unit: Unit, page: Page) -> Item:
    item = Item(unit, status=page.status)
    err = page.error or validate(page.text, page.status)
    if err:
        item.error = err
        return item
    text = clean_markdown(page.text)
    err = validate(text, None)
    if err:
        item.error = err
        return item
    item.text, item.hash, item.words = text, text_hash(text), word_count(text)
    return item


async def collect(fetcher: Fetcher, *, limit: Optional[int] = None, only: Optional[str] = None) -> list[Item]:
    """Fetch every page and build the documents that would be stored. Writes nothing."""
    items: list[Item] = []
    wanted = lambda key: only is None or only in key  # noqa: E731

    ov_key = f"{OVERVIEW_FOLDER}/requirements.txt"
    if wanted(ov_key):
        unit = Unit(ov_key, f"{OVERVIEW_FOLDER}/requirements", BASE_URL, OVERVIEW_FOLDER, "requirements", "catalog")
        items.append(_catalog_item(unit, await fetcher.page(BASE_URL)))

    seen: set[str] = set()
    derived: dict[str, tuple[str, str]] = {}
    links = await fetcher.links()
    for url, name in links:
        folder = sanitize(name)
        if not folder or re.fullmatch(r"\d+", folder) or url.split("#")[0].rstrip("/") == BASE_URL or folder in seen:
            continue
        if limit is not None and len(seen) >= limit:
            break
        seen.add(folder)
        if not wanted(f"{folder}/"):
            continue
        req_unit = Unit(f"{folder}/requirements.txt", f"{folder}/requirements", url, folder, "requirements", "catalog")
        page = await fetcher.page(url)
        items.append(_catalog_item(req_unit, page))
        if items[-1].error or not page.text:
            continue
        if folder.startswith("certificate_in_") and needs_section(page.text):
            for sec_folder, sec_text in sections(page.text):
                derived.setdefault(sec_folder, (url, sec_text))
            continue  # a certificate has no degree plan of its own
        if page.example_url:
            ex_unit = Unit(f"{folder}/example.txt", f"{folder}/example", page.example_url, folder, "example", "catalog")
            ex_page = await fetcher.page(page.example_url)
            ex_item = _catalog_item(ex_unit, ex_page)
            items.append(ex_item)

    for sec_folder, (url, sec_text) in derived.items():
        if sec_folder in seen or not wanted(f"{sec_folder}/"):
            continue
        unit = Unit(f"{sec_folder}/requirements.txt", f"{sec_folder}/requirements", url, sec_folder, "requirements", "derived")
        item = Item(unit, status=200, text=sec_text, hash=text_hash(sec_text), words=word_count(sec_text))
        err = validate(sec_text, None)
        if err:
            item.error, item.text, item.hash = err, None, None
        items.append(item)

    for name, url in WEB_PAGES:
        key = f"web/{name}.md"
        if wanted(key):
            unit = Unit(key, f"web/{name}", url, "web", name, "web")
            items.append(_web_item(unit, await fetcher.markdown(url)))
    return items


# --- phase 2: compare with what is stored ----------------------------------

@dataclass
class _Doc:
    deleted: bool
    meta: dict
    source: Optional[str]
    title: str


@dataclass
class Context:
    docs: dict
    has_chunks: set
    hash_owner: dict    # content hash -> document id (live documents only)
    chunk_hashes: dict  # normalized chunk hash -> (chunk id, document id, title)


def load_context(db: Session) -> Context:
    docs, hash_owner = {}, {}
    for d in db.query(Document).all():
        meta = dict(d.doc_metadata or {})
        docs[d.id] = _Doc(bool(d.is_deleted), meta, d.source, d.title)
        if not d.is_deleted and meta.get("content_hash"):
            hash_owner.setdefault(meta["content_hash"], d.id)
    has_chunks = {r[0] for r in db.query(Chunk.document_id).filter(Chunk.is_deleted.isnot(True)).distinct()}
    chunk_hashes = {}
    for c in db.query(Chunk).filter(Chunk.is_deleted.isnot(True)).all():
        owner = docs.get(c.document_id)
        if owner and not owner.deleted:
            chunk_hashes.setdefault(text_hash(c.text), (c.id, c.document_id, owner.title))
    return Context(docs, has_chunks, hash_owner, chunk_hashes)


def classify(ctx: Context, item: Item) -> None:
    if item.error:
        item.outcome, item.detail = "failed", item.error
        return
    did = doc_id(item.unit.key)
    doc = ctx.docs.get(did)
    usable = doc is not None and not doc.deleted and did in ctx.has_chunks
    if usable and doc.meta.get("content_hash") == item.hash:
        item.outcome = "unchanged"
        return
    owner = ctx.hash_owner.get(item.hash)
    if owner and owner != did:
        item.outcome, item.detail = "duplicate", f"same content as document {owner}"
        return
    item.outcome = "changed" if doc is not None else "new"
    ctx.hash_owner[item.hash] = did  # so an identical page later in this run is a duplicate


def check_guards(items: list[Item]) -> Optional[str]:
    total = len(items)
    if total < GUARD_MIN_PAGES:
        return None
    failed = sum(1 for i in items if i.outcome == "failed")
    if failed / total > MAX_FAILED_FRACTION:
        return f"{failed}/{total} pages failed to fetch or validate; the site may be down or have changed"
    existing = [i for i in items if i.outcome in ("changed", "unchanged")]
    changed = sum(1 for i in existing if i.outcome == "changed")
    if len(existing) >= GUARD_MIN_PAGES and changed / len(existing) > MAX_CHANGED_FRACTION:
        return f"{changed}/{len(existing)} existing pages changed at once; refusing to re-embed without --force"
    return None


# --- phase 3: apply ---------------------------------------------------------

def _delete_chunks(db: Session, did: str) -> None:
    ids = [r[0] for r in db.query(Chunk.id).filter(Chunk.document_id == did)]
    if ids:
        db.query(Embedding).filter(Embedding.chunk_id.in_(ids)).delete(synchronize_session=False)
        db.query(Chunk).filter(Chunk.document_id == did).delete(synchronize_session=False)


def upsert_document(db: Session, ctx: Context, item: Item, run: RunSummary, embed: Callable) -> None:
    """Chunk, embed, and swap in a document. Embedding happens before any write."""
    unit, did = item.unit, doc_id(item.unit.key)
    existing = ctx.docs.get(did)

    new_chunks, also_in = [], {}
    for idx, text in enumerate(chunk_text(item.text)):
        h = text_hash(text)
        hit = ctx.chunk_hashes.get(h)
        if hit and hit[1] != did:
            run.merged_chunks += 1
            also_in.setdefault(hit[0], set()).add(unit.title)
            continue
        new_chunks.append((hashlib.sha256(f"{did}:{idx}".encode()).hexdigest()[:32], idx, text, h))

    vectors = embed([c[2] for c in new_chunks]) if new_chunks else []
    for v in vectors:
        if len(v) != EMBED_DIMS:
            raise ValueError(f"embedding has {len(v)} dimensions, expected {EMBED_DIMS}")

    model = _embedding_model()

    meta = {"program": unit.folder, "file": unit.file, "content_hash": item.hash, "url": unit.url}
    if unit.kind == "derived":
        meta["derived_from"] = unit.url
    if existing is not None:
        _delete_chunks(db, did)
        doc = db.get(Document, did)
        doc.title, doc.source = unit.title, unit.url
        doc.doc_metadata = {**existing.meta, **meta}
        doc.is_deleted = False
        doc.updated_at = datetime.utcnow()
    else:
        db.add(Document(id=did, title=unit.title, source=unit.url, doc_metadata=meta))
    db.flush()

    for (cid, idx, text, _h), vec in zip(new_chunks, vectors):
        db.add(Chunk(id=cid, document_id=did, chunk_index=idx, text=text, chunk_metadata={"chunk_index": idx}))
        db.add(Embedding(id=hashlib.sha256(f"emb:{cid}".encode()).hexdigest()[:32], chunk_id=cid, vector=vec, model=model))
    for kept_id, titles in also_in.items():
        kept = db.get(Chunk, kept_id)
        m = dict(kept.chunk_metadata or {})
        m["also_in"] = sorted(set(m.get("also_in", [])) | titles)
        kept.chunk_metadata = m

    scrape_log.record(db, run.run_id, unit.key, unit.url, item.outcome, document_id=did,
                      content_hash=item.hash, http_status=item.status, word_count=item.words)
    db.commit()

    run.new_chunks += len(new_chunks)
    run.tokens += sum(len(_enc.encode(c[2])) for c in new_chunks)
    ctx.docs[did] = _Doc(False, meta, unit.url, unit.title)
    ctx.has_chunks.add(did)
    ctx.hash_owner[item.hash] = did
    for _cid, _idx, _text, h in new_chunks:
        ctx.chunk_hashes[h] = (_cid, did, unit.title)


def apply_item(db: Session, ctx: Context, item: Item, run: RunSummary, embed: Callable) -> None:
    unit, did = item.unit, doc_id(item.unit.key)
    log = lambda outcome, detail=None: scrape_log.record(  # noqa: E731
        db, run.run_id, unit.key, unit.url, outcome, document_id=did if did in ctx.docs else None,
        content_hash=item.hash, http_status=item.status, word_count=item.words or None,
        detail=detail if detail is not None else (item.detail or None),
    )

    if item.outcome == "unchanged":
        doc = ctx.docs[did]
        if doc.source != unit.url:  # moves old local-path sources over to the real URL
            row = db.get(Document, did)
            row.source = unit.url
            row.doc_metadata = {**doc.meta, "url": unit.url}
            doc.source = unit.url
        log("unchanged")
        db.commit()
    elif item.outcome == "duplicate":
        log("duplicate")
        db.commit()
    elif item.outcome == "failed":
        doc = ctx.docs.get(did)
        gone = item.status in GONE_STATUSES
        if gone and doc is not None and not doc.deleted and scrape_log.consecutive_failures(db, unit.key) + 1 >= FAIL_LIMIT:
            db.get(Document, did).is_deleted = True
            doc.deleted = True
            item.outcome = "removed"
            log("removed", f"{item.error}; {FAIL_LIMIT} consecutive failures")
        else:
            log("failed")
        db.commit()
    else:
        try:
            upsert_document(db, ctx, item, run, embed)
        except Exception as e:
            db.rollback()
            logger.exception("Embedding/storing %s failed", unit.key)
            item.outcome, item.detail = "failed", f"{type(e).__name__}: {e}"[:200]
            log("failed")
            db.commit()


# --- orchestration ----------------------------------------------------------

async def run(
    db: Session,
    fetcher: Fetcher,
    *,
    embed: Callable = embed_texts,
    dry_run: bool = False,
    force: bool = False,
    limit: Optional[int] = None,
    only: Optional[str] = None,
) -> RunSummary:
    if not dry_run and not scrape_log.table_exists(db):
        raise RuntimeError("scrape_log table is missing; apply migration 003_scrape_log.sql first")
    summary = RunSummary(run_id=str(uuid.uuid4()), dry_run=dry_run)
    items = await collect(fetcher, limit=limit, only=only)
    ctx = load_context(db)
    for item in items:
        classify(ctx, item)
    summary.items = items
    summary.counts = Counter(i.outcome for i in items)

    reason = None if force else check_guards(items)
    if reason:
        summary.aborted, summary.reason = True, reason
        if not dry_run:
            scrape_log.record(db, summary.run_id, scrape_log.RUN_KEY, BASE_URL, "failed", detail=f"aborted: {reason}")
            db.commit()
        return summary
    if dry_run:
        return summary

    for item in items:
        apply_item(db, ctx, item, summary, embed)
    summary.counts = Counter(i.outcome for i in items)
    return summary


def format_summary(s: RunSummary) -> str:
    lines = [f"run {s.run_id}{' (dry run)' if s.dry_run else ''}"]
    for outcome in ("unchanged", "changed", "new", "duplicate", "failed", "removed"):
        if s.counts.get(outcome):
            lines.append(f"  {outcome:<10} {s.counts[outcome]}")
    for i in s.items:
        if i.outcome in ("changed", "new", "failed", "duplicate"):
            lines.append(f"    [{i.outcome}] {i.unit.key}  {i.detail}")
    if s.aborted:
        lines.append(f"ABORTED, nothing written: {s.reason}")
    elif not s.dry_run:
        lines.append(f"  embedded {s.new_chunks} chunks (~{s.tokens:,} tokens, ~${s.est_cost:.4f}); merged {s.merged_chunks} duplicate chunks")
    return "\n".join(lines)


def print_status(db: Session) -> None:
    if not scrape_log.table_exists(db):
        print("scrape_log does not exist yet (migration 003 has not been applied)")
        return
    rid = scrape_log.latest_run_id(db)
    if not rid:
        print("no runs recorded")
        return
    print(f"last run {rid}: {dict(scrape_log.run_counts(db, rid))}")
    for key, url, detail in scrape_log.failing_pages(db, rid):
        print(f"  failed  {key}  {detail}  {url}")


async def _main(args) -> int:
    from app.db.database import SessionLocal, apply_migrations

    if not (args.dry_run or args.status):
        apply_migrations()
    db = SessionLocal()
    try:
        if args.status:
            print_status(db)
            return 0
        async with LiveFetcher() as fetcher:
            summary = await run(db, fetcher, dry_run=args.dry_run, force=args.force, limit=args.limit, only=args.only)
        print(format_summary(summary))
        return 2 if summary.aborted else 0
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true", help="fetch and compare, write nothing")
    ap.add_argument("--force", action="store_true", help="skip the too-many-changes / too-many-failures guards")
    ap.add_argument("--limit", type=int, help="only the first N catalog programs")
    ap.add_argument("--only", help="only pages whose key contains this text")
    ap.add_argument("--status", action="store_true", help="show the last run and exit")
    sys.exit(asyncio.run(_main(ap.parse_args())))


if __name__ == "__main__":
    main()
