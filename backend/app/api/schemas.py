"""
Pydantic schemas for API request/response validation.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator


class ParcelSummary(BaseModel):
    """Lightweight parcel data for map loading."""
    id: int
    source_id: Optional[str] = None
    centroid_lon: float
    centroid_lat: float
    recorded_acres: Optional[float] = None
    calculated_acres: Optional[float] = None

    class Config:
        from_attributes = True


class ParcelDetail(BaseModel):
    """Full parcel data with geometry."""
    id: int
    source_id: Optional[str] = None
    owner_name: Optional[str] = None
    address: Optional[str] = None
    recorded_acres: Optional[float] = None
    calculated_acres: Optional[float] = None
    county: Optional[str] = None
    geometry: dict  # GeoJSON

    class Config:
        from_attributes = True


class WetlandFeature(BaseModel):
    """Wetland feature for constraint display."""
    id: int
    attribute: Optional[str] = None
    wetland_type: Optional[str] = None
    geometry: dict  # GeoJSON

    class Config:
        from_attributes = True


class FloodplainFeature(BaseModel):
    """Floodplain feature for constraint display."""
    id: int
    fld_zone: Optional[str] = None
    zone_subty: Optional[str] = None
    geometry: dict  # GeoJSON

    class Config:
        from_attributes = True


class ConstraintsResponse(BaseModel):
    """Response containing wetlands and floodplains for a parcel."""
    wetlands: list[WetlandFeature]
    floodplains: list[FloodplainFeature]


class BreakdownItem(BaseModel):
    """Individual breakdown item showing constraint impact."""
    reason: str
    acres: float
    type: str = Field(..., description="'removed' or 'added'")


class BuildableRequest(BaseModel):
    """Request body for buildable area calculation."""
    wetland_buffer_ft: float = Field(
        default=50.0,
        ge=0.0,
        le=500.0,
        description="Buffer distance for wetlands in feet"
    )
    floodplain_buffer_ft: float = Field(
        default=25.0,
        ge=0.0,
        le=500.0,
        description="Buffer distance for floodplains in feet"
    )
    manual_excludes: list[dict] = Field(
        default=[],
        description="List of GeoJSON Polygon geometries to exclude from buildable area"
    )
    manual_restores: list[dict] = Field(
        default=[],
        description="List of GeoJSON Polygon geometries to restore to buildable area"
    )

    @field_validator("manual_excludes", "manual_restores")
    @classmethod
    def validate_geojson_list(cls, v):
        """Validate that each item is a valid GeoJSON geometry."""
        if not v:
            return v

        for i, geom in enumerate(v):
            if not isinstance(geom, dict):
                raise ValueError(f"Item {i} must be a GeoJSON geometry dict")
            if "type" not in geom:
                raise ValueError(f"Item {i} missing 'type' field")
            if "coordinates" not in geom:
                raise ValueError(f"Item {i} missing 'coordinates' field")
            if geom["type"] not in ["Polygon", "MultiPolygon"]:
                raise ValueError(f"Item {i} must be Polygon or MultiPolygon, got {geom['type']}")
        return v


class BuildableResponse(BaseModel):
    """Response containing buildable area calculation results."""
    buildable_acres: float = Field(..., description="Total buildable area in acres")
    parcel_acres: float = Field(..., description="Total parcel area in acres")
    constrained_acres: float = Field(..., description="Total constrained area in acres")
    buildable_geom: Optional[dict] = Field(None, description="GeoJSON of buildable area")
    breakdown: list[BreakdownItem] = Field(
        ...,
        description="Breakdown by constraint type"
    )
    breakdown_note: str = Field(
        default=(
            "Breakdown entries may overlap (e.g., wetland buffer overlapping floodplain), "
            "so individual constraint acres may not sum exactly to total constrained area."
        ),
        description="Explanation of breakdown overlap behavior"
    )
    warnings: list[str] = Field(
        default=[],
        description="Warnings about geometry repairs or other issues"
    )


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    code: Optional[str] = None


class BboxParams(BaseModel):
    """Bounding box parameters for spatial queries."""
    minx: float
    miny: float
    maxx: float
    maxy: float

    @field_validator("maxx")
    @classmethod
    def maxx_gt_minx(cls, v, info):
        if "minx" in info.data and v <= info.data["minx"]:
            raise ValueError("maxx must be greater than minx")
        return v

    @field_validator("maxy")
    @classmethod
    def maxy_gt_miny(cls, v, info):
        if "miny" in info.data and v <= info.data["miny"]:
            raise ValueError("maxy must be greater than miny")
        return v
