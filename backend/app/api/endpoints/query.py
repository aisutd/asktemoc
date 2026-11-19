from fastapi import APIRouter, Depends
from app.services.rag_service import RAGService
from app.models.requests import QueryRequest
from app.models.response import QueryResponse


router = APIRouter()

@router.post("/", response_model=QueryResponse)
async def query(request: QueryRequest):
    rag = RAGService()
    answer = await rag.answer(request.query)
    return QueryResponse(answer=answer)

