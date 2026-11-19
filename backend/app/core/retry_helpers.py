"""
Backoff retries for transient OpenAI embedding calls and Postgres (Neon) commits.
"""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def openai_embeddings_retry_predicate(exc: BaseException) -> bool:
    """True for rate limits, timeouts, and 5xx from OpenAI / httpx transport."""
    try:
        from httpx import ConnectError, ReadTimeout, TimeoutException

        if isinstance(exc, (ReadTimeout, ConnectError, TimeoutException)):
            return True
    except ImportError:
        pass
    try:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )

        if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
            return True
        from openai import APIStatusError

        if isinstance(exc, APIStatusError):
            code = getattr(exc, "status_code", None)
            if code is None and getattr(exc, "response", None) is not None:
                code = getattr(exc.response, "status_code", None)
            return code in (408, 429, 502, 503, 504)
    except ImportError:
        pass
    return False


def call_openai_embedding_with_retries(fn: Callable[[], T]) -> T:
    """Run ``fn`` (usually OpenAI embeddings.create) with exponential backoff."""
    r = Retrying(
        retry=retry_if_exception(openai_embeddings_retry_predicate),
        stop=stop_after_attempt(12),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "OpenAI embed retry (%s/%s): %s",
            rs.attempt_number,
            12,
            rs.outcome.exception() if rs.outcome else "?",
        ),
    )
    return r(fn)
