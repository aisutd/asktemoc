"""
Persistent scraper state: per-URL content hashes and rescrape queue.
Saved to data/scraper_state.json so state survives restarts.
"""

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / "scraper_state.json"

# Default re-scrape interval
DEFAULT_INTERVAL_DAYS = 7
# ± jitter applied to the next scrape time (avoids thundering herd)
JITTER_HOURS = 12


def load() -> dict:
    """Load state from disk. Returns empty state if file does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"pages": {}, "queue": []}


def save(state: dict) -> None:
    """Persist state to disk atomically."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def has_changed(url: str, content: str, state: dict) -> bool:
    """Return True if content differs from the stored hash (or URL is new / never scraped)."""
    stored = state["pages"].get(url, {})
    if not stored.get("last_scraped"):
        return True
    return stored.get("hash") != content_hash(content)


def record_scraped(
    url: str,
    content: str,
    scraper: str,
    state: dict,
    interval_days: int = DEFAULT_INTERVAL_DAYS,
) -> None:
    """
    Update the hash for a URL and schedule its next scrape.

    Mutates *state* in place — caller is responsible for eventually calling save().

    If this URL previously had no *last_scraped* timestamp (never completed a scrape cycle
    in state, or manually cleared), the next queued rescrape runs immediately rather than waiting
    the default interval.
    """
    now = datetime.now(timezone.utc)
    prior = state["pages"].get(url, {})

    jitter = random.uniform(-JITTER_HOURS, JITTER_HOURS)
    if prior.get("last_scraped"):
        next_scrape = now + timedelta(days=interval_days, hours=jitter)
    else:
        # First successful recording (or missing last_scraped) — schedule follow-up scrape ASAP
        next_scrape = now

    state["pages"][url] = {
        "hash": content_hash(content),
        "last_scraped": now.isoformat(),
        "next_scrape": next_scrape.isoformat(),
        "scraper": scraper,
    }

    # Replace any existing queue entry for this URL
    state["queue"] = [e for e in state["queue"] if e["url"] != url]
    state["queue"].append(
        {
            "url": url,
            "scraper": scraper,
            "scheduled_for": next_scrape.isoformat(),
        }
    )


def get_due_urls(scraper: str, state: dict) -> list[str]:
    """
    Return URLs that should be re-scrape for *scraper*.

    Includes queue rows with scheduled_for <= now, plus any page belonging to this
    scraper that has no last_scraped (repair incomplete state).

    Deduped; queue iteration order preserved, then orphaned page entries.
    """
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    urls: list[str] = []

    for entry in state["queue"]:
        if entry["scraper"] != scraper:
            continue
        url = entry["url"]
        if url in seen:
            continue
        pf = datetime.fromisoformat(entry["scheduled_for"])
        pg = state["pages"].get(url) or {}
        in_pages = url in state["pages"]
        missing_last = in_pages and not pg.get("last_scraped")

        if pf <= now or missing_last:
            urls.append(url)
            seen.add(url)

    # Pages never queued but marked for this scraper with missing last_scraped (corrupt slice)
    for url, meta in state["pages"].items():
        if meta.get("scraper") != scraper or url in seen:
            continue
        if not meta.get("last_scraped"):
            urls.append(url)
            seen.add(url)

    return urls
