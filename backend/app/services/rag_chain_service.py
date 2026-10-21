from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

from app.core.config import get_settings
from app.services.prompt_service import rag_prompt_template
from app.services.retriever_service import get_retriever_service


def _get_llm():
    """Use OpenAI if OPENAI_API_KEY is set, otherwise Ollama."""
    settings = get_settings()
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.4,
        )
    from langchain_ollama import OllamaLLM
    return OllamaLLM(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
    )


class RagChainService:
    def __init__(self):
        self.retriever = get_retriever_service().get_retriever()
        self.llm = _get_llm()
        self._chain = None

    def get_chain(self):
        if self._chain is not None:
            return self._chain

        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        rag_chain_from_docs = (
            RunnablePassthrough.assign(context=(lambda x: format_docs(x["context"])))
            | rag_prompt_template
            | self.llm
            | StrOutputParser()
        )

        rag_chain_with_source = RunnableParallel(
            {"context": self.retriever, "question": RunnablePassthrough()}
        ).assign(answer=rag_chain_from_docs)

        self._chain = rag_chain_with_source
        return self._chain


@lru_cache
def get_rag_chain_service() -> RagChainService:
    return RagChainService()
