"""Tests for scraper_state.py — pure logic, no network or disk I/O."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from app.services.scrapers import scraper_state


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------

def test_content_hash_is_deterministic():
    h1 = scraper_state.content_hash("hello world")
    h2 = scraper_state.content_hash("hello world")
    assert h1 == h2


def test_content_hash_differs_for_different_content():
    assert scraper_state.content_hash("foo") != scraper_state.content_hash("bar")


def test_content_hash_is_64_hex_chars():
    h = scraper_state.content_hash("test")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# has_changed
# ---------------------------------------------------------------------------

def test_has_changed_returns_true_for_new_url():
    state = {"pages": {}, "queue": []}
    assert scraper_state.has_changed("https://example.com", "content", state) is True


def test_has_changed_returns_false_when_hash_matches_and_previously_scraped():
    content = "some page content"
    state = {
        "pages": {
            "https://example.com": {
                "hash": scraper_state.content_hash(content),
                "last_scraped": "2026-01-01T00:00:00+00:00",
            },
        },
        "queue": [],
    }
    assert scraper_state.has_changed("https://example.com", content, state) is False


def test_has_changed_true_when_missing_last_scraped_even_if_hash_matches():
    content = "some page content"
    state = {
        "pages": {
            "https://example.com": {
                "hash": scraper_state.content_hash(content),
            },
        },
        "queue": [],
    }
    assert scraper_state.has_changed("https://example.com", content, state) is True


def test_has_changed_returns_true_when_content_differs():
    state = {
        "pages": {
            "https://example.com": {"hash": scraper_state.content_hash("old content")}
        },
        "queue": [],
    }
    assert scraper_state.has_changed("https://example.com", "new content", state) is True


# ---------------------------------------------------------------------------
# record_scraped
# ---------------------------------------------------------------------------

def test_record_scraped_stores_hash_and_timestamps():
    state = {"pages": {}, "queue": []}
    scraper_state.record_scraped("https://example.com", "content", "catalog", state)

    page = state["pages"]["https://example.com"]
    assert page["hash"] == scraper_state.content_hash("content")
    assert page["scraper"] == "catalog"
    assert "last_scraped" in page
    assert "next_scrape" in page


def test_record_scraped_adds_to_queue():
    state = {"pages": {}, "queue": []}
    scraper_state.record_scraped("https://example.com", "content", "catalog", state)

    assert len(state["queue"]) == 1
    entry = state["queue"][0]
    assert entry["url"] == "https://example.com"
    assert entry["scraper"] == "catalog"
    assert "scheduled_for" in entry


def test_record_scraped_replaces_existing_queue_entry():
    state = {"pages": {}, "queue": []}
    scraper_state.record_scraped("https://example.com", "content v1", "catalog", state)
    scraper_state.record_scraped("https://example.com", "content v2", "catalog", state)

    # Should still be exactly one entry for this URL
    entries = [e for e in state["queue"] if e["url"] == "https://example.com"]
    assert len(entries) == 1


def test_record_scraped_first_visit_schedules_next_immediately_not_months_out():
    state = {"pages": {}, "queue": []}
    scraper_state.record_scraped("https://example.com", "content", "catalog", state)
    ns = datetime.fromisoformat(state["pages"]["https://example.com"]["next_scrape"])
    now = datetime.now(timezone.utc)
    assert ns <= now + timedelta(minutes=1), (
        "first successful scrape should queue next scrape immediately (~now)"
    )


def test_record_scraped_follow_up_uses_standard_interval_future():
    state = {"pages": {}, "queue": []}
    scraper_state.record_scraped("https://example.com", "v1", "catalog", state)
    scraper_state.record_scraped("https://example.com", "v2", "catalog", state)
    ns = datetime.fromisoformat(state["pages"]["https://example.com"]["next_scrape"])
    assert ns > datetime.now(timezone.utc)


def test_record_scraped_applies_jitter_after_first_visit():
    """After URL has last_scraped, repeated record_scraped uses jitter on next window."""
    times = set()
    for _ in range(10):
        state = {"pages": {}, "queue": []}
        scraper_state.record_scraped("https://example.com", "a", "catalog", state)
        scraper_state.record_scraped("https://example.com", "b", "catalog", state)
        times.add(state["pages"]["https://example.com"]["next_scrape"])
    assert len(times) > 3


# ---------------------------------------------------------------------------
# get_due_urls
# ---------------------------------------------------------------------------

def test_get_due_urls_returns_past_entries():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    state = {
        "pages": {},
        "queue": [
            {"url": "https://example.com/a", "scraper": "catalog", "scheduled_for": past},
        ],
    }
    due = scraper_state.get_due_urls("catalog", state)
    assert "https://example.com/a" in due


def test_get_due_urls_excludes_future_entries_without_page_row():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    state = {
        "pages": {},
        "queue": [
            {"url": "https://example.com/b", "scraper": "catalog", "scheduled_for": future},
        ],
    }
    due = scraper_state.get_due_urls("catalog", state)
    assert due == []


def test_get_due_urls_includes_future_when_page_missing_last_scraped():
    future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    state = {
        "pages": {
            "https://example.com/b": {"hash": "abc", "scraper": "catalog"},
        },
        "queue": [
            {"url": "https://example.com/b", "scraper": "catalog", "scheduled_for": future},
        ],
    }
    due = scraper_state.get_due_urls("catalog", state)
    assert due == ["https://example.com/b"]


def test_get_due_urls_filters_by_scraper():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    state = {
        "pages": {},
        "queue": [
            {"url": "https://a.com", "scraper": "catalog", "scheduled_for": past},
            {"url": "https://b.com", "scraper": "general", "scheduled_for": past},
        ],
    }
    due = scraper_state.get_due_urls("catalog", state)
    assert "https://a.com" in due
    assert "https://b.com" not in due


# ---------------------------------------------------------------------------
# load / save (using tmp_path fixture to avoid touching real data dir)
# ---------------------------------------------------------------------------

def test_load_returns_empty_state_when_no_file(tmp_path):
    with patch.object(scraper_state, "STATE_FILE", tmp_path / "state.json"):
        state = scraper_state.load()
    assert state == {"pages": {}, "queue": []}


def test_save_and_load_roundtrip(tmp_path):
    state_file = tmp_path / "state.json"
    original = {
        "pages": {"https://example.com": {"hash": "abc123", "scraper": "catalog"}},
        "queue": [{"url": "https://example.com", "scraper": "catalog", "scheduled_for": "2026-01-01T00:00:00+00:00"}],
    }
    with (
        patch.object(scraper_state, "STATE_FILE", state_file),
        patch.object(scraper_state, "DATA_DIR", tmp_path),
    ):
        scraper_state.save(original)
        loaded = scraper_state.load()

    assert loaded == original
