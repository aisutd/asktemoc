"""
LLM service — OpenAI when LLM_PROVIDER=openai (default) and OPENAI_API_KEY is set; else Ollama unless LLM_PROVIDER=ollama.
"""

from app.core.config import get_settings


class LLMService:
    def __init__(self):
        self.settings = get_settings()
        if self.settings.use_openai:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
            self._model = self.settings.OPENAI_MODEL
        else:
            from langchain_ollama import ChatOllama
            self._ollama = ChatOllama(
                model=self.settings.OLLAMA_MODEL,
                temperature=self.settings.OLLAMA_TEMPERATURE,
            )

    def call(self, query: str) -> str:
        if self.settings.use_openai:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": query}],
            )
            return response.choices[0].message.content
        return self._ollama.invoke(query).content

    async def a_call(self, query: str) -> str:
        if self.settings.use_openai:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.settings.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": query}],
            )
            return response.choices[0].message.content
        return (await self._ollama.ainvoke(query)).content
