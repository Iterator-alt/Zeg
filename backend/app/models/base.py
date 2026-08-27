"""Base model configuration for SQLAlchemy with GeoAlchemy2."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass
