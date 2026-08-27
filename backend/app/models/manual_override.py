"""Manual override model for user-drawn exclude/restore polygons."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Index
from geoalchemy2 import Geometry
from app.models.base import Base


class ManualOverride(Base):
    """
    User-drawn polygons to manually exclude or restore buildable area.

    - 'exclude': User-drawn polygon that removes area from buildable calculation
    - 'restore': User-drawn polygon that adds back area that was removed by
                 constraints (can only restore area within the original parcel)

    Overrides are associated with a session_id to allow multiple users/sessions
    to work independently without affecting each other's calculations.
    """
    __tablename__ = "manual_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Link to the parcel this override applies to
    parcel_id = Column(
        Integer,
        ForeignKey("parcels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Session identifier - allows tracking overrides per user session
    # Could be a UUID, user ID, or other identifier
    session_id = Column(String(100), nullable=False, index=True)

    # Override type: 'exclude' or 'restore'
    kind = Column(String(10), nullable=False)

    # Optional label/description from user
    label = Column(String(255), nullable=True)

    # When the override was created
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Geometry stored in EPSG:4326
    # User-drawn polygons may be simple polygons
    geom = Column(
        Geometry(
            geometry_type="POLYGON",
            srid=4326,
            spatial_index=False
        ),
        nullable=False
    )

    __table_args__ = (
        Index("idx_manual_overrides_geom", geom, postgresql_using="gist"),
        Index("idx_manual_overrides_parcel_session", parcel_id, session_id),
    )

    def __repr__(self):
        return f"<ManualOverride(id={self.id}, parcel_id={self.parcel_id}, kind={self.kind})>"
