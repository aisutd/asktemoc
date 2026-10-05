"""
Application settings, read from the environment and backend/.env.

Relative filesystem paths (CHROMA_PERSIST_DIRECTORY, a relative SQLite
DATABASE_URL) resolve against the backend/ directory, so the API and the scripts
see the same files whatever directory they are started from.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


def _resolve(path: str) -> str:
    p = Path(path)
    return str(p if p.is_absolute() else (BACKEND_DIR / p).resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors must never echo secrets (API keys, JWT secret) to logs.
        hide_input_in_errors=True,
    )

    environment: str = "development"

    # Database
    database_url: str = "sqlite:///./asktemoc.db"
    db_echo: bool = False

    # Vector store
    chroma_persist_directory: str = "./app/chroma_db"
    chroma_collection_name: str = "asktemoc_collection"
    catalog_data_dir: str = str(REPO_ROOT / "data" / "catalog")

    # LLM / embeddings: OpenAI when OPENAI_API_KEY is set, otherwise Ollama.
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    # Comma-separated in the environment.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Auth: the Next.js server mints short-lived HS256 tokens for the signed-in
    # user; the API verifies them with the shared secret.
    backend_jwt_secret: Optional[str] = None
    jwt_audience: str = "asktemoc-api"
    jwt_issuer: str = "asktemoc-web"
    jwt_leeway_seconds: int = 30
    allowed_email_domain: str = "utdallas.edu"
    # Extra individual addresses, honoured only when ENVIRONMENT=development.
    allowed_emails: Annotated[list[str], NoDecode] = []
    # Development-only escape hatch: every request acts as a fixed dev user.
    auth_disabled: bool = False

    @field_validator("cors_origins", "allowed_emails", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("allowed_emails")
    @classmethod
    def _lower_emails(cls, v: list[str]) -> list[str]:
        return [e.lower() for e in v]

    @field_validator("openai_api_key", "backend_jwt_secret", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return v or None

    @model_validator(mode="after")
    def _check_auth(self):
        if self.auth_disabled and not self.is_development:
            raise ValueError(
                "AUTH_DISABLED=true is only allowed with ENVIRONMENT=development "
                f"(ENVIRONMENT={self.environment!r}); refusing to start"
            )
        if self.backend_jwt_secret is not None and len(self.backend_jwt_secret) < 32:
            raise ValueError("BACKEND_JWT_SECRET must be at least 32 characters")
        if not self.auth_disabled and self.backend_jwt_secret is None and not self.is_development:
            raise ValueError("BACKEND_JWT_SECRET is required outside development")
        return self

    @field_validator("chroma_persist_directory", "catalog_data_dir")
    @classmethod
    def _absolute_dir(cls, v: str) -> str:
        return _resolve(v)

    @field_validator("database_url")
    @classmethod
    def _absolute_sqlite(cls, v: str) -> str:
        prefix = "sqlite:///"
        if v.startswith(prefix) and v != "sqlite:///:memory:":
            return prefix + Path(_resolve(v[len(prefix):])).as_posix()
        return v

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def llm_provider(self) -> Literal["openai", "ollama"]:
        return "openai" if self.openai_api_key else "ollama"

    @property
    def embedding_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_embedding_model
        return self.ollama_embedding_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
