from langchain_ollama import ChatOllama
import random


class LLMService:
    def __init__(self):
        self.llm = ChatOllama(model="llama3.1:8b", temperature=0.4)

    def call(self):
        # note that this is just a place holder, this class is only for calling the LLM
        countries = ["Indonesia", "Germany", "China", "France", "Japan", "Brazil"]
        content = self.llm.invoke(f"What is the capital of {random.choice(countries)}?").content
        return content

    async def a_call(self):
        # Just know that this is an async call to the LLM hence the 'a_' prefix
        countries = ["Indonesia", "Germany", "China", "France", "Japan", "Brazil"]
        content = await self.llm.ainvoke(f"What is the capital of {random.choice(countries)}?")
        return content.content
