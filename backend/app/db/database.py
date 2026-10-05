"""
Database session management and initialization.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.models import Base

# Database URL configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./asktemoc.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    Dependency injection for FastAPI to get a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database by creating all tables.
    """
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")


def drop_db():
    """
    Drop all tables (use with caution).
    """
    Base.metadata.drop_all(bind=engine)
    print("All database tables dropped.")
