import logging
from pathlib import Path
from typing import Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    DB_ECHO: bool = False
    DEBUG: bool = False

    # Chat/completions: "openai" (default), or "ollama" for local Llama/etc.
    LLM_PROVIDER: Literal["openai", "ollama"] = "openai"

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"

    # Ollama (optional fallback)
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_TEMPERATURE: float = 0.4

    # ChromaDB (kept for compatibility)
    CHROMA_PERSIST_DIRECTORY: Path = Path("./app/chroma_db")
    CHROMA_COLLECTION_NAME: str = "asktemoc_collection"

    # Comma-separated browser origins (set your deployed front-end HTTPS URL in Cloud Run).
    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("LLM_PROVIDER", mode="before")
    @classmethod
    def _normalize_llm_provider(cls, v: object) -> str:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "openai"
        s = str(v).strip().lower()
        return s if s in ("openai", "ollama") else "openai"

    @property
    def chroma_persist_path(self) -> Path:
        project_root = Path(__file__).resolve().parent.parent
        return (project_root / self.CHROMA_PERSIST_DIRECTORY).resolve()

    @property
    def cors_origins_list(self) -> list[str]:
        parts = [x.strip() for x in (self.CORS_ORIGINS or "").split(",")]
        return [p for p in parts if p] or ["http://localhost:3000"]

    @property
    def use_openai(self) -> bool:
        """Use OpenAI chat when provider is OpenAI *and* an API key is set; else Ollama."""
        if self.LLM_PROVIDER == "ollama":
            return False
        return bool(self.OPENAI_API_KEY)


def get_settings() -> Settings:
    return Settings()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

logger = logging.getLogger("app")
