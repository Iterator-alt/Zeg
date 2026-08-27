"""Wetland model for National Wetlands Inventory data."""

from sqlalchemy import Column, Integer, String, Index
from geoalchemy2 import Geometry
from app.models.base import Base


class Wetland(Base):
    """
    Wetland polygons from USFWS National Wetlands Inventory (NWI).

    NWI data uses the Cowardin classification system. Key wetland types:
    - PEM: Palustrine Emergent (marshes)
    - PFO: Palustrine Forested (swamps)
    - PSS: Palustrine Scrub-Shrub
    - L: Lacustrine (lake-associated)
    - R: Riverine

    Geometry stored in EPSG:4326, reprojected for buffer calculations.
    """
    __tablename__ = "wetlands"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # NWI attribute code (Cowardin classification)
    # e.g., "PFO1A" = Palustrine, Forested, Broad-leaved Deciduous, Temporary Flooded
    attribute = Column(String(50), nullable=True)

    # Simplified wetland type for display
    wetland_type = Column(String(100), nullable=True)

    # Source feature ID
    source_id = Column(String(100), nullable=True)

    # Geometry stored in EPSG:4326
    geom = Column(
        Geometry(
            geometry_type="MULTIPOLYGON",
            srid=4326,
            spatial_index=False
        ),
        nullable=False
    )

    __table_args__ = (
        Index("idx_wetlands_geom", geom, postgresql_using="gist"),
    )

    def __repr__(self):
        return f"<Wetland(id={self.id}, type={self.wetland_type})>"
