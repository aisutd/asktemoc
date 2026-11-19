"""Tests for rescrape.py — in-memory SQLite, fake fetcher, fake embedder. No network."""

import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Chunk, Document, Embedding, ScrapeLog
from app.services.scrapers import rescrape, scrape_log
from app.services.scrapers.rescrape import BASE_URL, Page, doc_id, save_raw

CHROME = (
    "UT Dallas 2025 Undergraduate Catalog\nDownload page as a PDF, opens a new tab\n"
    "Download page as a DOCX (MS Word) file\nOpen page in a printable window, opens a new tab\nCompare Versions\n"
)


def body(tag: str, n: int = 45) -> str:
    return f"{tag} " + " ".join(f"{tag}{i}" for i in range(n))


class FakeFetcher:
    def __init__(self, programs=None, pages=None, web=None):
        self.programs = programs or []
        self.pages = pages or {}
        self.web = web or {}

    async def links(self):
        return self.programs

    async def page(self, url):
        return self.pages.get(url, Page(404, "The page you are looking for does not exist."))

    async def markdown(self, url):
        return self.web.get(url, Page(404, None))


class FakeEmbed:
    def __init__(self):
        self.calls = 0
        self.texts = 0

    def __call__(self, texts):
        self.calls += 1
        self.texts += len(texts)
        return [[0.1] * 1536 for _ in texts]


def failing_embed(texts):
    raise RuntimeError("OpenAI is down")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        engine, tables=[Document.__table__, Chunk.__table__, Embedding.__table__, ScrapeLog.__table__]
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def program(name, text, status=200, example_url=None):
    url = f"https://catalog.test/{name.lower().replace(' ', '-')}"
    return (url, name), {url: Page(status, text, example_url)}


def fetcher_for(*specs):
    links, pages = [], {}
    for link, page in specs:
        links.append(link)
        pages.update(page)
    return FakeFetcher(programs=links, pages=pages)


def run(db, fetcher, **kw):
    kw.setdefault("embed", FakeEmbed())
    kw.setdefault("only", "_in_")  # program pages only; skips the overview and web pages
    return asyncio.run(rescrape.run(db, fetcher, **kw))


def outcomes(db, run_id):
    return {r.doc_key: r.outcome for r in db.query(ScrapeLog).filter(ScrapeLog.run_id == run_id)}


def test_first_run_inserts_documents_and_logs_them(db):
    f = fetcher_for(program("Bachelor of Science in Alpha", body("alpha")))
    embed = FakeEmbed()
    s = run(db, f, embed=embed)
    key = "bachelor_of_science_in_alpha/requirements.txt"
    assert s.counts["new"] == 1
    doc = db.get(Document, doc_id(key))
    assert doc.source == "https://catalog.test/bachelor-of-science-in-alpha"
    assert doc.doc_metadata["content_hash"]
    assert db.query(Chunk).filter(Chunk.document_id == doc.id).count() >= 1
    assert db.query(Embedding).count() == db.query(Chunk).count()
    assert outcomes(db, s.run_id)[key] == "new"


def test_unchanged_page_is_not_re_embedded(db):
    f = fetcher_for(program("Bachelor of Science in Alpha", body("alpha")))
    run(db, f)
    embed = FakeEmbed()
    s = run(db, f, embed=embed)
    assert s.counts["unchanged"] == 1 and embed.calls == 0
    assert outcomes(db, s.run_id)["bachelor_of_science_in_alpha/requirements.txt"] == "unchanged"


def test_updated_stamp_alone_does_not_count_as_a_change(db):
    name = "Bachelor of Science in Alpha"
    run(db, fetcher_for(program(name, body("alpha") + "\nUpdated: 2025-08-04 08:26:12 v12.aaaaaa")))
    embed = FakeEmbed()
    s = run(db, fetcher_for(program(name, body("alpha") + "\nUpdated: 2026-02-01 10:00:00 v13.bbbbbb")), embed=embed)
    assert s.counts["unchanged"] == 1 and embed.calls == 0


def test_changed_page_replaces_chunks_and_hash(db):
    name = "Bachelor of Science in Alpha"
    run(db, fetcher_for(program(name, body("alpha"))))
    key = "bachelor_of_science_in_alpha/requirements.txt"
    old_hash = db.get(Document, doc_id(key)).doc_metadata["content_hash"]
    s = run(db, fetcher_for(program(name, body("alphanew"))))
    assert s.counts["changed"] == 1
    doc = db.get(Document, doc_id(key))
    assert doc.doc_metadata["content_hash"] != old_hash
    texts = [c.text for c in db.query(Chunk).filter(Chunk.document_id == doc.id)]
    assert all("alphanew" in t for t in texts)
    assert db.query(Embedding).count() == db.query(Chunk).count()


def test_404_keeps_the_document_and_is_logged_as_failed(db):
    name = "Bachelor of Science in Alpha"
    key = "bachelor_of_science_in_alpha/requirements.txt"
    run(db, fetcher_for(program(name, body("alpha"))))
    s = run(db, fetcher_for(program(name, "Not found", status=404)))
    assert s.counts["failed"] == 1
    assert db.get(Document, doc_id(key)).is_deleted is False
    assert db.query(Chunk).filter(Chunk.document_id == doc_id(key)).count() >= 1
    row = db.query(ScrapeLog).filter(ScrapeLog.run_id == s.run_id).one()
    assert row.http_status == 404 and row.detail == "HTTP 404"


def test_three_consecutive_404s_soft_delete_the_document(db):
    name = "Bachelor of Science in Alpha"
    key = "bachelor_of_science_in_alpha/requirements.txt"
    run(db, fetcher_for(program(name, body("alpha"))))
    gone = fetcher_for(program(name, "Not found", status=404))
    run(db, gone)
    run(db, gone)
    assert db.get(Document, doc_id(key)).is_deleted is False
    s = run(db, gone)
    assert s.counts["removed"] == 1
    assert db.get(Document, doc_id(key)).is_deleted is True


def test_server_errors_never_delete_a_document(db):
    name = "Bachelor of Science in Alpha"
    key = "bachelor_of_science_in_alpha/requirements.txt"
    run(db, fetcher_for(program(name, body("alpha"))))
    broken = fetcher_for(program(name, "Server error", status=500))
    for _ in range(5):
        run(db, broken)
    assert db.get(Document, doc_id(key)).is_deleted is False


def test_footer_only_page_is_rejected(db):
    f = fetcher_for(program("Bachelor of Arts in Education", "The University of Texas at Dallas, 800 W Campbell Rd | Privacy Policy"))
    s = run(db, f)
    assert s.counts["failed"] == 1
    assert db.query(Document).count() == 0


def test_page_that_comes_back_after_removal_is_revived(db):
    name = "Bachelor of Science in Alpha"
    key = "bachelor_of_science_in_alpha/requirements.txt"
    run(db, fetcher_for(program(name, body("alpha"))))
    gone = fetcher_for(program(name, "Not found", status=404))
    for _ in range(3):
        run(db, gone)
    s = run(db, fetcher_for(program(name, body("alpha"))))
    assert s.counts["changed"] == 1
    assert db.get(Document, doc_id(key)).is_deleted is False


def test_identical_page_under_another_name_is_a_duplicate(db):
    text = body("shared")
    f = fetcher_for(program("Bachelor of Science in Alpha", text), program("Bachelor of Science in Beta", text))
    s = run(db, f)
    assert s.counts["new"] == 1 and s.counts["duplicate"] == 1
    assert db.query(Document).count() == 1


def test_combined_certificate_page_gives_each_certificate_its_own_section(db):
    page = (
        CHROME + "Example School\nCertificates\nCertificate in Alpha Studies\nCertificate in Beta Studies\n\n\n"
        "Certificate in Alpha Studies\n\n6 semester credit hours\n\n" + body("alphaonly") + "\n\n"
        "Certificate in Beta Studies\n\n9 semester credit hours\n\n" + body("betaonly") + "\n"
    )
    f = fetcher_for(
        program("Certificate in Alpha Studies", page, example_url="https://catalog.test/example"),
        program("Certificate in Beta Studies", page),
    )
    f.pages["https://catalog.test/example"] = Page(200, body("example"))
    s = run(db, f)
    alpha = " ".join(c.text for c in db.query(Chunk).filter(Chunk.document_id == doc_id("certificate_in_alpha_studies/requirements.txt")))
    beta = " ".join(c.text for c in db.query(Chunk).filter(Chunk.document_id == doc_id("certificate_in_beta_studies/requirements.txt")))
    assert "alphaonly" in alpha and "betaonly" not in alpha
    assert "betaonly" in beta and "alphaonly" not in beta
    assert db.get(Document, doc_id("certificate_in_alpha_studies/example.txt")) is None
    assert s.counts["new"] == 2


def test_certificate_without_its_own_link_is_created_from_the_combined_page(db):
    page = (
        CHROME + "Example School\nCertificates\nCertificate in Alpha Studies\nCertificate in Beta Studies\n\n\n"
        "Certificate in Alpha Studies\n\n6 semester credit hours\n\n" + body("alphaonly") + "\n\n"
        "Certificate in Beta Studies\n\n9 semester credit hours\n\n" + body("betaonly") + "\n"
    )
    s = run(db, fetcher_for(program("Certificate in Alpha Studies", page)))
    assert db.get(Document, doc_id("certificate_in_beta_studies/requirements.txt")) is not None
    assert s.counts["new"] == 2


def test_guard_aborts_when_too_many_existing_pages_change(db):
    specs = lambda tag: [program(f"Bachelor of Science in Prog{i}", body(f"{tag}{i}")) for i in range(12)]
    run(db, fetcher_for(*specs("v1")))
    before = db.query(Chunk).count()
    embed = FakeEmbed()
    s = run(db, fetcher_for(*specs("v2")), embed=embed)
    assert s.aborted and "changed at once" in s.reason
    assert embed.calls == 0 and db.query(Chunk).count() == before
    last = db.query(ScrapeLog).filter(ScrapeLog.run_id == s.run_id).one()
    assert last.doc_key == "__run__" and last.outcome == "failed"
    forced = run(db, fetcher_for(*specs("v2")), force=True)
    assert not forced.aborted and forced.counts["changed"] == 12


def test_guard_aborts_when_too_many_pages_fail(db):
    specs = [program(f"Bachelor of Science in Prog{i}", "gone", status=404) for i in range(12)]
    s = run(db, fetcher_for(*specs))
    assert s.aborted and "failed" in s.reason


def test_embedding_failure_keeps_the_old_document(db):
    name = "Bachelor of Science in Alpha"
    key = "bachelor_of_science_in_alpha/requirements.txt"
    run(db, fetcher_for(program(name, body("alpha"))))
    old = [c.text for c in db.query(Chunk).filter(Chunk.document_id == doc_id(key))]
    s = run(db, fetcher_for(program(name, body("alphanew"))), embed=failing_embed)
    assert s.counts["failed"] == 1
    assert [c.text for c in db.query(Chunk).filter(Chunk.document_id == doc_id(key))] == old
    assert db.query(Embedding).count() == len(old)


def test_dry_run_writes_nothing(db):
    s = run(db, fetcher_for(program("Bachelor of Science in Alpha", body("alpha"))), dry_run=True)
    assert s.counts["new"] == 1
    assert db.query(Document).count() == 0 and db.query(ScrapeLog).count() == 0


def test_old_local_path_source_is_moved_to_the_real_url(db):
    name = "Bachelor of Science in Alpha"
    f = fetcher_for(program(name, body("alpha")))
    run(db, f)
    doc = db.get(Document, doc_id("bachelor_of_science_in_alpha/requirements.txt"))
    doc.source = "test_output/bachelor_of_science_in_alpha/requirements.txt"
    db.commit()
    run(db, f)
    db.refresh(doc)
    assert doc.source == "https://catalog.test/bachelor-of-science-in-alpha"


def test_web_page_is_cleaned_before_hashing(db):
    md = "[Skip](https://x/#main)\n  * [Nav](https://x/nav/)\n# Tuition Rates\n" + body("tuition") + "\n[Privacy Policy](https://x/p/)\n"
    f = FakeFetcher(web={"https://www.utdallas.edu/": Page(200, md)})
    s = run(db, f, only="web/utd_home")
    assert s.counts["new"] == 1
    text = " ".join(c.text for c in db.query(Chunk))
    assert "tuition" in text and "Nav" not in text and "Privacy" not in text


def test_real_run_without_the_log_table_is_refused(db):
    ScrapeLog.__table__.drop(db.get_bind())
    with pytest.raises(RuntimeError, match="scrape_log"):
        run(db, FakeFetcher())


def _flaky_record(monkeypatch, fail_times=1):
    real = scrape_log.record
    state = {"left": fail_times}

    def record(*a, **kw):
        if state["left"] > 0:
            state["left"] -= 1
            raise OperationalError("INSERT", {}, Exception("SSL SYSCALL error"))
        return real(*a, **kw)

    monkeypatch.setattr(scrape_log, "record", record)
    monkeypatch.setattr(rescrape, "DB_RETRY_BACKOFF", 0)


def test_dropped_connection_is_retried_and_the_page_still_lands(db, monkeypatch):
    f = fetcher_for(program("Bachelor of Science in Alpha", body("alpha")))
    _flaky_record(monkeypatch)
    s = run(db, f)
    assert s.counts["new"] == 1
    assert db.get(Document, doc_id("bachelor_of_science_in_alpha/requirements.txt")) is not None
    assert db.query(Embedding).count() == db.query(Chunk).count() >= 1
    assert db.query(ScrapeLog).count() == 1


def test_source_fix_is_not_lost_when_the_first_attempt_fails(db, monkeypatch):
    name = "Bachelor of Science in Alpha"
    f = fetcher_for(program(name, body("alpha")))
    run(db, f)
    doc = db.get(Document, doc_id("bachelor_of_science_in_alpha/requirements.txt"))
    doc.source = "test_output/old/path.txt"
    db.commit()
    _flaky_record(monkeypatch)
    run(db, f)
    db.refresh(doc)
    assert doc.source == "https://catalog.test/bachelor-of-science-in-alpha"


def test_run_gives_up_after_repeated_database_errors(db, monkeypatch):
    f = fetcher_for(program("Bachelor of Science in Alpha", body("alpha")))
    _flaky_record(monkeypatch, fail_times=99)
    with pytest.raises(OperationalError):
        run(db, f)


def _alpha(text, example=None):
    f = fetcher_for(program("Bachelor of Science in Alpha", text, example_url="https://catalog.test/ex" if example else None))
    if example:
        f.pages["https://catalog.test/ex"] = Page(200, example)
    return f


def test_save_raw_writes_pages_in_the_corpus_layout(db, tmp_path):
    page, example = body("alpha"), body("example")
    s = run(db, _alpha(page, example))
    assert save_raw(s.items, tmp_path, None) == 2
    assert (tmp_path / "bachelor_of_science_in_alpha" / "requirements.txt").read_text(encoding="utf-8") == page
    assert (tmp_path / "bachelor_of_science_in_alpha" / "example.txt").read_text(encoding="utf-8") == example
    s2 = run(db, _alpha(page, example))
    assert save_raw(s2.items, tmp_path, None) == 0  # same content, nothing rewritten


def test_save_raw_rewrites_a_changed_page(db, tmp_path):
    run_a = run(db, _alpha(body("alpha")))
    save_raw(run_a.items, tmp_path, None)
    run_b = run(db, _alpha(body("alphanew")))
    assert save_raw(run_b.items, tmp_path, None) == 1
    assert "alphanew" in (tmp_path / "bachelor_of_science_in_alpha" / "requirements.txt").read_text(encoding="utf-8")


def test_save_raw_skips_failed_pages_and_changes_after_a_dry_run(db, tmp_path):
    run(db, fetcher_for(program("Bachelor of Science in Alpha", body("alpha")), program("Bachelor of Science in Beta", body("beta"))))
    dry = run(
        db,
        fetcher_for(
            program("Bachelor of Science in Alpha", body("alpha")),           # unchanged
            program("Bachelor of Science in Beta", body("betanew")),          # changed, not stored yet
            program("Bachelor of Science in Gamma", "Not found", status=404),  # failed
        ),
        dry_run=True,
    )
    assert save_raw(dry.items, tmp_path, None, dry_run=True) == 1
    assert (tmp_path / "bachelor_of_science_in_alpha" / "requirements.txt").exists()
    assert not (tmp_path / "bachelor_of_science_in_beta").exists()
    assert not (tmp_path / "bachelor_of_science_in_gamma").exists()


def test_save_raw_puts_the_overview_in_folder_1_and_web_pages_in_the_web_dir(db, tmp_path):
    md = "# Tuition Rates\n" + body("tuition")
    f = FakeFetcher(
        pages={BASE_URL: Page(200, body("overview"))},
        web={"https://www.utdallas.edu/": Page(200, md)},
    )
    s = run(db, f, only=None)
    assert save_raw(s.items, tmp_path / "data", tmp_path / "web") == 2
    assert (tmp_path / "data" / "1" / "requirements.txt").read_text(encoding="utf-8") == body("overview")
    assert (tmp_path / "web" / "utd_home.md").read_text(encoding="utf-8") == md
    assert not (tmp_path / "data" / "undergraduate_catalog_overview").exists()


def test_run_aborts_when_the_catalog_returns_nothing(db):
    f = FakeFetcher(pages={BASE_URL: Page(403, "Forbidden")})
    s = run(db, f, only=None)
    assert s.aborted and "no catalog program pages" in s.reason and "HTTP 403" in s.reason
    last = db.query(ScrapeLog).filter(ScrapeLog.run_id == s.run_id).one()
    assert last.doc_key == "__run__"
    assert not run(db, f, only=None, force=True).aborted


def test_a_filtered_run_is_not_treated_as_a_missing_catalog(db):
    s = run(db, FakeFetcher(), only="utd_home")
    assert not s.aborted


def test_save_raw_leaves_a_web_file_alone_when_only_the_navigation_changed(db, tmp_path):
    page = "# Tuition Rates\n" + body("tuition")
    f = FakeFetcher(web={"https://www.utdallas.edu/": Page(200, "  * [Students](https://x/s)\n" + page)})
    s = run(db, f, only="web/utd_home")
    assert save_raw(s.items, None, tmp_path) == 1
    f2 = FakeFetcher(web={"https://www.utdallas.edu/": Page(200, "  * [Faculty](https://x/f)\n" + page)})
    s2 = run(db, f2, only="web/utd_home")
    assert s2.counts["unchanged"] == 1
    assert save_raw(s2.items, None, tmp_path) == 0
