"""Floodplain model for FEMA National Flood Hazard Layer data."""

from sqlalchemy import Column, Integer, String, Index
from geoalchemy2 import Geometry
from app.models.base import Base


class Floodplain(Base):
    """
    Floodplain polygons from FEMA National Flood Hazard Layer (NFHL).

    This model stores 100-year (1% annual chance) flood zones:
    - Zone A: No base flood elevations determined
    - Zone AE: Base flood elevations determined
    - Zone AH: Flood depths of 1-3 feet (usually ponding)
    - Zone AO: Flood depths of 1-3 feet (usually sheet flow)

    500-year flood zones (Zone X) are not included by default but could be added.

    Geometry stored in EPSG:4326, reprojected for buffer calculations.
    """
    __tablename__ = "floodplains"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FEMA flood zone designation
    # Primary zones of interest: A, AE, AH, AO, V, VE (coastal)
    fld_zone = Column(String(20), nullable=True, index=True)

    # Zone subtype if applicable
    zone_subty = Column(String(100), nullable=True)

    # Static BFE (Base Flood Elevation) if available
    static_bfe = Column(String(20), nullable=True)

    # Source feature ID (DFIRM_ID or similar)
    source_id = Column(String(100), nullable=True)

    # SFHA (Special Flood Hazard Area) flag
    # True for zones A, AE, AH, AO, V, VE
    sfha_tf = Column(String(5), nullable=True)

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
        Index("idx_floodplains_geom", geom, postgresql_using="gist"),
        Index("idx_floodplains_fld_zone", fld_zone),
    )

    def __repr__(self):
        return f"<Floodplain(id={self.id}, zone={self.fld_zone})>"
