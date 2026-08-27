"""Parcel model for land parcels."""

from sqlalchemy import Column, Integer, String, Float, Index
from geoalchemy2 import Geometry
from app.models.base import Base


class Parcel(Base):
    """
    Land parcel geometry and metadata.

    Geometry is stored in EPSG:4326 (WGS84) for compatibility with GeoJSON
    and frontend mapping libraries. All area/buffer calculations are performed
    by reprojecting to EPSG:6579 (NAD83 Texas Centric Albers Equal Area).
    """
    __tablename__ = "parcels"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Original parcel identifier from source data
    source_id = Column(String(100), nullable=True, index=True)

    # Parcel metadata
    owner_name = Column(String(255), nullable=True)
    address = Column(String(500), nullable=True)

    # Recorded acreage from source data (may differ from calculated)
    recorded_acres = Column(Float, nullable=True)

    # Calculated acreage from geometry (in projected CRS)
    calculated_acres = Column(Float, nullable=True)

    # County/jurisdiction info
    county = Column(String(100), nullable=True, index=True)

    # Geometry stored in EPSG:4326
    # Using Polygon type; MultiPolygon parcels are unioned or handled separately
    geom = Column(
        Geometry(
            geometry_type="MULTIPOLYGON",
            srid=4326,
            spatial_index=False  # We'll create the index explicitly
        ),
        nullable=False
    )

    # Explicit GIST spatial index for efficient spatial queries
    __table_args__ = (
        Index("idx_parcels_geom", geom, postgresql_using="gist"),
        Index("idx_parcels_county", county),
    )

    def __repr__(self):
        return f"<Parcel(id={self.id}, source_id={self.source_id}, acres={self.recorded_acres})>"
