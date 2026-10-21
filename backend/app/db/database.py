"""
Database session management and initialization.
"""

import logging
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.db.models import Base
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _make_engine():
    settings = get_settings()
    url = settings.DATABASE_URL
    lu = url.lower()
    kw: dict = {
        "echo": settings.DB_ECHO,
    }
    if "sqlite" in lu:
        kw["connect_args"] = {"check_same_thread": False}
    if "postgresql" in lu or "postgres" in lu:
        kw["pool_pre_ping"] = True
        kw["pool_recycle"] = 1800
        # Neon proxies may drop idle connections; recycle + pre-ping reduce surprise disconnects.

    return create_engine(url, **kw)


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip()[:-1].strip()
            if statement:
                statements.append(statement)
            current = []
    if current:
        statement = "\n".join(current).strip().rstrip(";").strip()
        if statement:
            statements.append(statement)
    return statements


def apply_migrations() -> None:
    """
    Apply backend/app/migrations/*.sql once, in filename order.
    Postgres only. Next.js never connects to the database.
    """
    settings = get_settings()
    if "postgresql" not in settings.DATABASE_URL:
        return

    files = sorted(path for path in _MIGRATIONS_DIR.glob("*.sql") if path.is_file())
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename TEXT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        applied = {
            row[0]
            for row in conn.execute(text("SELECT filename FROM schema_migrations"))
        }
        for path in files:
            if path.name in applied:
                continue
            for statement in _sql_statements(path.read_text()):
                conn.execute(text(statement))
            conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:name)"),
                {"name": path.name},
            )
            logger.info("Applied migration %s", path.name)


def init_db():
    """
    Initialize database: enable pgvector extension (Postgres only), apply SQL
    migrations, then create any remaining tables.
    """
    settings = get_settings()
    if "postgresql" in settings.DATABASE_URL:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            conn.commit()
        apply_migrations()

    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")


def drop_db():
    Base.metadata.drop_all(bind=engine)
    print("All database tables dropped.")
