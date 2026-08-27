"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import get_settings


def get_engine():
    """Create SQLAlchemy engine."""
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session_factory():
    """Create session factory."""
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create global session factory
SessionLocal = get_session_factory()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database sessions.

    Usage:
        @app.get("/")
        def read_root(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
