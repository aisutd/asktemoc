import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.rag_chain_service import get_rag_chain_service

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


def get_chain():
    """Dependency so tests can swap in a fake chain."""
    return get_rag_chain_service().get_chain()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_rag_response(chain, message: str):
    """
    SSE events, in order:
      {"type": "source", "message": "Source n: <url>", "index", "url", "title"?}  per doc
      {"type": "text", "message": <delta>}  answer chunks, to be appended
      {"type": "done"}
    """
    try:
        sources_sent = False
        answer_chars = 0
        # astream keeps retrieval and generation off the event loop and yields the
        # retrieved context as soon as it is ready, then answer tokens as produced.
        async for chunk in chain.astream(message):
            if "context" in chunk and not sources_sent:
                sources_sent = True
                for i, doc in enumerate(chunk["context"], start=1):
                    url = doc.metadata.get("source", "Unknown")
                    event = {
                        "type": "source",
                        "message": f"Source {i}: {url}",
                        "index": i,
                        "url": url,
                    }
                    if doc.metadata.get("title"):
                        event["title"] = doc.metadata["title"]
                    yield _sse(event)
            delta = chunk.get("answer")
            if delta:
                answer_chars += len(delta)
                yield _sse({"type": "text", "message": delta})
        logger.info("Streamed answer: %d characters", answer_chars)
    except Exception:
        logger.exception("Error in RAG streaming")
        yield _sse({"type": "text", "message": "Error processing request"})
    yield _sse({"type": "done"})


@router.post("/chat")
async def chat(request: ChatRequest, chain=Depends(get_chain)):
    return StreamingResponse(
        stream_rag_response(chain, request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
