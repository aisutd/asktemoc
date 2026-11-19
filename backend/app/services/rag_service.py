import asyncio
from app.services.llm_service import LLMService
async def generate_answer(query: str) -> str:
    await asyncio.sleep(1) 
    return f"Answer: {query}"

class RAGService:
    def __init__(self):
        pass

    async def answer(self, query: str) -> str:
        llm_service = LLMService()
        # print(f"Test: {llm_service.call()}")
        # answer = await generate_answer(query=query)
        answer = await llm_service.a_call()
        return answer
    
    async def test_llm(self, query: str) -> str:
        llm_service = LLMService()
        answer = await llm_service.a_call()
        return answer

    