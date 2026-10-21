"""Read-only connection to the Neon corpus database."""

from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def connect():
    """
    Open a connection to NEON_DATABASE_URL from backend/.env (not the app's
    DATABASE_URL). The session is read-only, so Postgres rejects any write.
    """
    import psycopg
    from dotenv import dotenv_values

    url = dotenv_values(ENV_PATH).get("NEON_DATABASE_URL")
    if not url:
        raise RuntimeError(f"NEON_DATABASE_URL is not set in {ENV_PATH}")
    conn = psycopg.connect(url)
    conn.read_only = True
    return conn


def check_k(k):
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError(f"k must be a positive int, got {k!r}")
