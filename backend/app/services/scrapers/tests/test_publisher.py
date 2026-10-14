"""Tests for publisher.py — httpx calls are fully mocked."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scrapers.publisher import (
    build_payload,
    publish_page,
    INGEST_URL,
    _MAX_POST_ATTEMPTS,
)


# ---------------------------------------------------------------------------
# build_payload
# ---------------------------------------------------------------------------

def test_build_payload_raw_content():
    payload = build_payload(
        url="https://example.com/page",
        page_title="My Page",
        text_content="some text",
        html_content="<p>some text</p>",
    )
    assert payload["url"] == "https://example.com/page"
    assert payload["page_title"] == "My Page"
    assert payload["text_content"] == "some text"
    assert payload["html_content"] == "<p>some text</p>"
    assert payload["chunks"] == []
    assert "timestamp" in payload


def test_build_payload_clears_raw_content_when_chunks_provided():
    payload = build_payload(
        url="https://example.com",
        page_title="Title",
        text_content="should be cleared",
        html_content="<p>also cleared</p>",
        chunks=[{"chunk_id": "1", "text": "chunk"}],
    )
    assert payload["text_content"] is None
    assert payload["html_content"] is None
    assert len(payload["chunks"]) == 1


def test_build_payload_timestamp_is_iso_format():
    from datetime import datetime
    payload = build_payload("https://x.com", "X")
    # Should parse without error
    datetime.fromisoformat(payload["timestamp"])


def test_build_payload_empty_chunks_by_default():
    payload = build_payload("https://x.com", "X", text_content="hi")
    assert payload["chunks"] == []


# ---------------------------------------------------------------------------
# publish_page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_page_posts_to_ingest_url():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.scrapers.publisher.httpx.AsyncClient", return_value=mock_client):
        result = await publish_page(
            url="https://example.com",
            page_title="Test Page",
            text_content="Hello",
        )

    assert result is True
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[0][0] == INGEST_URL
    payload = call_kwargs[1]["json"]
    assert payload["url"] == "https://example.com"
    assert payload["page_title"] == "Test Page"
    assert payload["text_content"] == "Hello"


@pytest.mark.asyncio
async def test_publish_page_returns_false_on_http_error():
    mock_response = MagicMock()
    mock_response.status_code = 422
    mock_response.text = "Unprocessable"
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "422", request=MagicMock(), response=mock_response
        )
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.scrapers.publisher.httpx.AsyncClient", return_value=mock_client):
        result = await publish_page("https://example.com", "Title", text_content="hi")

    assert result is False
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_publish_page_returns_false_on_connection_error_after_retries():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(
        side_effect=httpx.RequestError("Connection refused", request=MagicMock())
    )

    with (
        patch("app.services.scrapers.publisher.httpx.AsyncClient", return_value=mock_client),
        patch("app.services.scrapers.publisher.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await publish_page("https://example.com", "Title", text_content="hi")

    assert result is False
    assert mock_client.post.call_count == _MAX_POST_ATTEMPTS
