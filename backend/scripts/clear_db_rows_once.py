#!/usr/bin/env python3
"""
One-time helper: empty all rows in documents / chunks / embeddings without DROPping tables.

Usage (from repo root, with PYTHONPATH and .env as for the app):

  PYTHONPATH=. python scripts/clear_db_rows_once.py --yes

Postgres (Neon): uses TRUNCATE ... CASCADE when possible.
SQLite: DELETE FROM in FK-safe order.
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from app.core.config import get_settings
from app.db.database import engine


def clear_rows() -> None:
    settings = get_settings()
    url = settings.DATABASE_URL.lower()

    with engine.begin() as conn:
        if "postgresql" in url or "postgres" in url:
            # Cascades through chunks/embeddings via FK constraints
            conn.execute(text("TRUNCATE TABLE documents RESTART IDENTITY CASCADE"))
            return
        # SQLite (and generic): delete children first
        conn.execute(text("DELETE FROM embeddings"))
        conn.execute(text("DELETE FROM chunks"))
        conn.execute(text("DELETE FROM documents"))


def main() -> None:
    p = argparse.ArgumentParser(description="Delete all rows from app DB tables (keep schema)")
    p.add_argument(
        "--yes",
        action="store_true",
        help='Required confirmation flag (otherwise the script refuses to run)',
    )
    args = p.parse_args()

    if not args.yes:
        raise SystemExit(
            'Refusing to run without --yes\n'
            "Example: PYTHONPATH=. python scripts/clear_db_rows_once.py --yes"
        )

    clear_rows()
    print("Cleared embeddings, chunks, and documents rows (tables left in place).")


if __name__ == "__main__":
    main()
