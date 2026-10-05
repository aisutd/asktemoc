from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import asyncio

from app.services.rag_chain_service import rag_chain_service

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

async def stream_rag_response(chain, message: str):
    try:
        # Get the RAG result
        result = chain.invoke(message)
        print(f"RAG result obtained: {len(result.get('context', []))} sources, answer length: {len(result.get('answer', ''))}")
        
        # Send sources immediately
        if "context" in result:
            for i, doc in enumerate(result["context"]):
                source_message = f"Source {i+1}: {doc.metadata.get('source', 'Unknown')}"
                print(f"Sending source: {source_message}")
                yield f"data: {json.dumps({'type': 'source', 'message': source_message})}\n\n"
                await asyncio.sleep(0.1)  # Small delay between sources
        
        # Stream the answer character by character for real-time effect
        if "answer" in result:
            answer = result["answer"]
            print(f"Streaming answer: {len(answer)} characters")
            for i in range(len(answer) + 1):
                chunk = answer[:i]
                yield f"data: {json.dumps({'type': 'text', 'message': chunk})}\n\n"
                await asyncio.sleep(0.01)  # Small delay for streaming effect
                
    except Exception as e:
        print(f"Error in streaming: {e}")
        yield f"data: {json.dumps({'type': 'text', 'message': 'Error processing request'})}\n\n"

@router.post("/chat")
async def chat(request: ChatRequest):
    chain = rag_chain_service.get_chain()
    return StreamingResponse(stream_rag_response(chain, request.message), media_type="text/event-stream")
