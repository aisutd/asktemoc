"""
Builds schema-compliant page payloads and sends them to the ingest server.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

INGEST_URL = "http://localhost:8000/api/ingest"

# Transient ingest / infra errors worth backing off instead of dropping the scrape.
_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_MAX_POST_ATTEMPTS = 12


def build_payload(
    url: str,
    page_title: str,
    text_content: Optional[str] = None,
    html_content: Optional[str] = None,
    chunks: Optional[list] = None,
) -> dict:
    """
    Build a schema-compliant page payload.

    Provide either text_content/html_content (raw) or chunks (pre-chunked) — not both.
    """
    return {
        "url": url,
        "page_title": page_title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text_content": text_content if not chunks else None,
        "html_content": html_content if not chunks else None,
        "chunks": chunks or [],
    }


async def publish_page(
    url: str,
    page_title: str,
    text_content: Optional[str] = None,
    html_content: Optional[str] = None,
    chunks: Optional[list] = None,
) -> bool:
    """
    Build and POST a page payload to the ingest server.

    Retries backoff on rate limits, server errors, or connection issues instead of exiting.
    Returns True on success, False after exhausting retries or on non-retryable HTTP errors.
    """
    payload = build_payload(url, page_title, text_content, html_content, chunks)
    timeout = httpx.Timeout(120.0, connect=45.0)
    backoff_s = 2.0

    for attempt in range(_MAX_POST_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(INGEST_URL, json=payload)
                if resp.status_code in _RETRY_STATUS:
                    logger.warning(
                        "Ingest HTTP %s for %s (attempt %s/%s), backing off %.1fs",
                        resp.status_code,
                        url,
                        attempt + 1,
                        _MAX_POST_ATTEMPTS,
                        min(backoff_s, 120.0),
                    )
                    await asyncio.sleep(min(backoff_s + random.uniform(0, 0.5), 120.0))
                    backoff_s = min(backoff_s * 2.0, 128.0)
                    continue
                resp.raise_for_status()
                logger.info(f"Published: {url}")
                return True
        except httpx.HTTPStatusError as e:
            status = getattr(e.response, "status_code", None) or 500
            if status in _RETRY_STATUS and attempt < _MAX_POST_ATTEMPTS - 1:
                logger.warning(
                    "Ingest HTTP error %s for %s (attempt %s/%s), backing off %.1fs — %s",
                    status,
                    url,
                    attempt + 1,
                    _MAX_POST_ATTEMPTS,
                    min(backoff_s, 120.0),
                    e,
                )
                await asyncio.sleep(min(backoff_s + random.uniform(0, 0.5), 120.0))
                backoff_s = min(backoff_s * 2.0, 128.0)
                continue
            logger.error(
                "Server rejected payload for %s: %s %s",
                url,
                status,
                getattr(e.response, "text", "")[:500],
            )
            return False
        except httpx.RequestError as e:
            if attempt < _MAX_POST_ATTEMPTS - 1:
                logger.warning(
                    "Failed to reach ingest for %s (attempt %s/%s): %s; retry in %.1fs",
                    url,
                    attempt + 1,
                    _MAX_POST_ATTEMPTS,
                    e,
                    min(backoff_s, 120.0),
                )
                await asyncio.sleep(min(backoff_s + random.uniform(0, 0.5), 120.0))
                backoff_s = min(backoff_s * 2.0, 128.0)
                continue
            logger.error(f"Failed to reach ingest server for {url}: {e}")
            return False

    logger.error("Exhausted ingest retries for %s", url)
    return False
