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

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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


async def stream_rag_response(message: str):
    accumulated = ""
    sources_by_idx: dict[int, dict] = {}
    try:
        async for ev in rag_chain_service.astream_rag(message):
            et = ev.get("type")
            if et == "source":
                idx = ev.get("index", 0)
                src = ev.get("source") or "Unknown"
                sources_by_idx[idx] = {"source": src, "title": ev.get("title")}
                line = f"Source {idx}: {src}"
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "source",
                            "message": line,
                            "index": idx,
                            "source": src,
                            "title": ev.get("title"),
                        }
                    )
                    + "\n\n"
                )
            elif et == "text":
                delta = ev.get("delta") or ""
                accumulated += delta
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "text",
                            "delta": delta,
                            "message": accumulated,
                        }
                    )
                    + "\n\n"
                )
            elif et == "done":
                raw_cites = extract_inline_citations(accumulated)
                citations = []
                for c in raw_cites:
                    i = c["source_index"]
                    meta = sources_by_idx.get(i, {})
                    citations.append(
                        {
                            "source_index": i,
                            "quote": c["quote"],
                            "url": meta.get("source"),
                            "title": meta.get("title"),
                        }
                    )
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "done",
                            "message": accumulated,
                            "citations": citations,
                        }
                    )
                    + "\n\n"
                )
            elif et == "error":
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": ev.get("message", "Error")})
                    + "\n\n"
                )
    except Exception as e:
        logger.exception("SSE chat failed: %s", e)
        yield (
            "data: "
            + json.dumps({"type": "error", "message": "Error processing request"})
            + "\n\n"
        )


@router.post(
    "/chat",
    summary="Stream a cited RAG answer over Server-Sent Events",
    response_class=EventStreamResponse,
    response_description="An SSE stream of `source`, `text`, and terminal `done` / `error` events",
    responses=_SSE_RESPONSES,
)
async def chat(request: ChatRequest):
    """
    Answers a question about UTD and streams the response as Server-Sent Events, in FastAPI format.

    Initial start event contains the conversation_id and title.
    ```json
    {
        "type": "start",
        "conversation_id": "0f8c2b53-4cb7-4ee0-baf1-a12a26fbc716",
        "title": "BS in Computer Science"
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
    return EventStreamResponse(
        stream_rag_response(request.message),
        headers=_SSE_HEADERS,
    )
