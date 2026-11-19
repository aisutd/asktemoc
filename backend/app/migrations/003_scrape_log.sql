-- One row per page check made by the scheduled re-scrape.
-- The latest row with a content_hash for a doc_key is that page's current hash.

CREATE TABLE IF NOT EXISTS scrape_log (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    doc_key TEXT NOT NULL,
    url TEXT NOT NULL,
    document_id TEXT,
    outcome TEXT NOT NULL,
    content_hash TEXT,
    http_status INTEGER,
    word_count INTEGER,
    detail TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_scrape_log_outcome CHECK (
        outcome IN ('new', 'changed', 'unchanged', 'failed', 'duplicate', 'removed')
    )
);

CREATE INDEX IF NOT EXISTS idx_scrape_log_doc_checked
    ON scrape_log (doc_key, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_scrape_log_run
    ON scrape_log (run_id);
