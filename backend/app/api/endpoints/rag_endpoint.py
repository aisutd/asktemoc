"""
POST /api/chat — streaming RAG over Neon Postgres (pgvector).

1) Embed query + pgvector retrieval (sync, off thread).
2) Stream LLM tokens via model `.astream()` (true token streaming, not replay).

SSE `data:` lines are JSON.

- **source** (before tokens): numbered rows with catalog **URL**, optional **title**; indices match prompt `Source n`.
- **text**: **delta** (token chunk), **message** (cumulative assistant text including `[n, "verbatim"]` citations).
- **done**: final **message** plus **citations**: parsed citation markers enriched with **url**/ **title**
  per `source_index` (hydrated from streamed **source** events).

Citation protocol is defined on `prompt_service.rag_prompt_template` (marker shape `[n, "EXACT_TEXT"]`).
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func

from app.core.auth import CurrentUser, get_current_user
from app.db.database import SessionLocal
from app.db.models import Conversation, Message, User
from app.services.prompt_service import extract_inline_citations
from app.services.rag_chain_service import rag_chain_service

logger = logging.getLogger(__name__)

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class EventStreamResponse(StreamingResponse):
    """Declares the media type so OpenAPI documents the route as SSE, not JSON."""

    media_type = "text/event-stream"


class ChatRequest(BaseModel):
    """A single user turn to answer against the UTD corpus."""

    message: str = Field(
        ...,
        min_length=1,
        description="Natural-language question. Embedded and used for pgvector retrieval verbatim.",
    )
    conversation_id: uuid.UUID | None = Field(
        default=None,
        description="Existing conversation. Omit to create one for the signed-in user.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"message": "How many credit hours does the BS in Computer Science require?"}
        }
    }


_SSE_EXAMPLE_ANSWER = r"""data: {"type": "source", "message": "Source 1: https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science", "index": 1, "source": "https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science", "title": "BS in Computer Science"}

data: {"type": "source", "message": "Source 2: https://cs.utdallas.edu/undergraduate/", "index": 2, "source": "https://cs.utdallas.edu/undergraduate/", "title": "Undergraduate Programs | Computer Science"}

data: {"type": "text", "delta": "The BS", "message": "The BS"}

data: {"type": "text", "delta": " in Computer Science", "message": "The BS in Computer Science"}

data: {"type": "text", "delta": " requires 124 semester credit hours", "message": "The BS in Computer Science requires 124 semester credit hours"}

data: {"type": "text", "delta": " [1, \"The program requires a minimum of 124 semester credit hours.\"].", "message": "The BS in Computer Science requires 124 semester credit hours [1, \"The program requires a minimum of 124 semester credit hours.\"]."}

data: {"type": "done", "message": "The BS in Computer Science requires 124 semester credit hours [1, \"The program requires a minimum of 124 semester credit hours.\"].", "citations": [{"source_index": 1, "quote": "The program requires a minimum of 124 semester credit hours.", "url": "https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science", "title": "BS in Computer Science"}]}

"""

_SSE_EXAMPLE_NO_SOURCES = r"""data: {"type": "text", "delta": "I don't know", "message": "I don't know"}

data: {"type": "text", "delta": " based on the sources available to me.", "message": "I don't know based on the sources available to me."}

data: {"type": "done", "message": "I don't know based on the sources available to me.", "citations": []}

"""

_SSE_EXAMPLE_ERROR = r"""data: {"type": "source", "message": "Source 1: https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science", "index": 1, "source": "https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science", "title": "BS in Computer Science"}

data: {"type": "error", "message": "Error processing request"}

"""

_SSE_RESPONSES = {
    200: {
        "description": "SSE stream, ending in a done event on success or an error event on failure.",
        "content": {
            "text/event-stream": {
                "schema": {"type": "string", "title": "SSE stream"},
                "examples": {
                    "answer_with_citations": {
                        "summary": "Grounded answer with one citation",
                        "value": _SSE_EXAMPLE_ANSWER,
                    },
                    "no_usable_sources": {
                        "summary": "Retrieval returned nothing usable",
                        "value": _SSE_EXAMPLE_NO_SOURCES,
                    },
                    "error_mid_stream": {
                        "summary": "Failure after sources were sent",
                        "value": _SSE_EXAMPLE_ERROR,
                    },
                },
            }
        },
    }
}


def _title_from_message(message: str) -> str:
    # todo: llm summary
    text = message.strip()
    if len(text) <= 30:
        return text or "New Chat"
    return text[:30] + "..."


def _content(parts: list[dict], citations: list[dict] | None = None) -> dict:
    body: dict = {"parts": parts}
    if citations is not None:
        body["citations"] = citations
    return body


def _source_parts(sources_by_idx: dict[int, dict]) -> list[dict]:
    parts = []
    for idx in sorted(sources_by_idx):
        meta = sources_by_idx[idx]
        url = meta.get("source")
        part = {
            "type": "source",
            "message": f"Source {idx}: {url}",
            "index": idx,
        }
        if url:
            part["url"] = url
        title = meta.get("title")
        if title:
            part["title"] = title
        parts.append(part)
    return parts


def begin_turn(user_id: str, message: str, conversation_id: uuid.UUID | None) -> dict:
    """Insert the user row and a streaming assistant row. Returns ids for the start event."""
    db = SessionLocal()
    try:
        if db.get(User, user_id) is None:
            raise HTTPException(
                status_code=403,
                detail="Sign out and sign in again to register your account.",
            )
        if conversation_id is None:
            conversation = Conversation(user_id=user_id, title=_title_from_message(message))
            db.add(conversation)
            db.flush()
        else:
            conversation = (
                db.query(Conversation)
                .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
                .with_for_update()
                .one_or_none()
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            if not conversation.title:
                conversation.title = _title_from_message(message)
        next_index = (
            db.query(func.max(Message.index))
            .filter(Message.conversation_id == conversation.id)
            .scalar()
            or 0
        )
        user_message = Message(
            conversation_id=conversation.id,
            index=next_index + 1,
            role="user",
            status="complete",
            content=_content([{"type": "text", "message": message}]),
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            index=next_index + 2,
            role="assistant",
            status="streaming",
            content=None,
        )
        db.add_all([user_message, assistant_message])
        db.commit()
        return {
            "conversation_id": str(conversation.id),
            "title": conversation.title,
            "user_message_id": str(user_message.id),
            "assistant_message_id": str(assistant_message.id),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_assistant(
    assistant_message_id: str,
    conversation_id: str,
    status: str,
    content: dict | None,
) -> None:
    """Write the assistant row once, and bump the conversation counters."""
    db = SessionLocal()
    try:
        message = db.get(Message, uuid.UUID(assistant_message_id))
        if message is None or message.status in ("complete", "error"):
            return
        message.status = status
        message.content = content
        conversation = db.get(Conversation, uuid.UUID(conversation_id))
        if conversation is not None:
            conversation.message_count = (conversation.message_count or 0) + 2
            conversation.last_message_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to save assistant message %s", assistant_message_id)
    finally:
        db.close()


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def _citations(accumulated: str, sources_by_idx: dict[int, dict]) -> list[dict]:
    citations = []
    for cite in extract_inline_citations(accumulated):
        meta = sources_by_idx.get(cite["source_index"], {})
        citations.append(
            {
                "source_index": cite["source_index"],
                "quote": cite["quote"],
                "url": meta.get("source"),
                "title": meta.get("title"),
            }
        )
    return citations


def _assistant_content(accumulated: str, sources_by_idx: dict[int, dict], citations: list[dict]) -> dict:
    parts = _source_parts(sources_by_idx)
    if accumulated:
        parts.append({"type": "text", "message": accumulated})
    return _content(parts, citations)


async def stream_rag_response(message: str, started: dict):
    persisted = False

    async def persist(status: str, content: dict | None) -> None:
        nonlocal persisted
        if persisted:
            return
        persisted = True
        await asyncio.to_thread(
            save_assistant,
            started["assistant_message_id"],
            started["conversation_id"],
            status,
            content,
        )

    accumulated = ""
    sources_by_idx: dict[int, dict] = {}
    yield _sse({"type": "start", **started})
    try:
        async for ev in rag_chain_service.astream_rag(message):
            et = ev.get("type")
            if et == "source":
                idx = ev.get("index", 0)
                src = ev.get("source") or "Unknown"
                sources_by_idx[idx] = {"source": src, "title": ev.get("title")}
                line = f"Source {idx}: {src}"
                yield _sse(
                    {
                        "type": "source",
                        "message": line,
                        "index": idx,
                        "source": src,
                        "title": ev.get("title"),
                    }
                )
            elif et == "text":
                delta = ev.get("delta") or ""
                accumulated += delta
                yield _sse({"type": "text", "delta": delta, "message": accumulated})
            elif et == "done":
                citations = _citations(accumulated, sources_by_idx)
                await persist("complete", _assistant_content(accumulated, sources_by_idx, citations))
                yield _sse({"type": "done", "message": accumulated, "citations": citations})
            elif et == "error":
                citations = _citations(accumulated, sources_by_idx)
                await persist("error", _assistant_content(accumulated, sources_by_idx, citations))
                yield _sse({"type": "error", "message": ev.get("message", "Error")})
    except Exception as e:
        logger.exception("SSE chat failed: %s", e)
        await persist("error", _assistant_content(accumulated, sources_by_idx, []))
        yield _sse({"type": "error", "message": "Error processing request"})
    finally:
        if not persisted:
            await persist("error", _assistant_content(accumulated, sources_by_idx, []))


@router.post(
    "/chat",
    summary="Stream a cited RAG answer over Server-Sent Events",
    response_class=EventStreamResponse,
    response_description="An SSE stream of `source`, `text`, and terminal `done` / `error` events",
    responses=_SSE_RESPONSES,
)
async def chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Answers a question about UTD and streams the response as Server-Sent Events, in FastAPI format.

    Initial start event contains the conversation and the two message rows just written.
    ```json
    {
        "type": "start",
        "conversation_id": "0f8c2b53-4cb7-4ee0-baf1-a12a26fbc716",
        "title": "BS in Computer Science",
        "user_message_id": "41d0c2e1-6b0a-4f1e-9c3a-1b2d3e4f5a6b",
        "assistant_message_id": "9ac1e7b2-3c4d-5e6f-7081-92a3b4c5d6e7"
    }
    ```
    First, source events are sent in relevance order, max 5, in this format:
    ```json
    {
        "type": "source",
        "message": "Source 1: https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science",
        "index": 1,
        "source": "https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science",
        "title": "BS in Computer Science"
    }
    ```
    A text event contains delta and the accumulated answer. TODO: only send delta
    ```json
    {
        "type": "text",
        "delta": "The BS in Computer Science requires 124 semester credit hours",
        "message": "The BS in Computer Science requires 124 semester credit hours"
    }
    ```
    Finally, a done event is sent with the final answer and citations.
    ```json
    {
        "type": "done",
        "message": "The BS in Computer Science requires 124 semester credit hours",
        "citations": [
            {
                "source_index": 1,
                "quote": "The program requires a minimum of 124 semester credit hours.",
                "url": "https://catalog.utdallas.edu/2024/undergraduate/programs/ecs/computer-science",
                "title": "BS in Computer Science"
            }
        ]
    }
    ```
    """
    logger.info("chat from %s (%s)", user.email, user.sub)
    started = await asyncio.to_thread(
        begin_turn, user.sub, request.message, request.conversation_id
    )
    return EventStreamResponse(
        stream_rag_response(request.message, started),
        headers=_SSE_HEADERS,
    )
