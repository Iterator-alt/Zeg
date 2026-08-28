"""
API routes for Buildable Land Analysis.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.geometry import (
    calculate_buildable_area,
    geojson_to_shapely,
    shapely_to_geojson,
    WGS84,
)
from app.api.schemas import (
    ParcelSummary,
    ParcelWithGeometry,
    ParcelDetail,
    ConstraintsResponse,
    WetlandFeature,
    FloodplainFeature,
    BuildableRequest,
    BuildableResponse,
    BreakdownItem,
)

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/parcels", response_model=list[ParcelSummary])
def list_parcels(
    bbox: Optional[str] = Query(
        None,
        description="Bounding box as minx,miny,maxx,maxy in WGS84 coordinates",
        examples=["-98.8,29.8,-98.6,30.0"],
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of parcels to return"),
    db: Session = Depends(get_db),
):
    """
    Get parcels within a bounding box.

    Returns lightweight parcel data (id, centroid, acres) for efficient map loading.
    Always use a bbox filter - never fetches the entire county.
    """
    if bbox is None:
        raise HTTPException(
            status_code=400,
            detail="bbox parameter is required. Format: minx,miny,maxx,maxy",
        )

    # Parse bbox
    try:
        parts = [float(x.strip()) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("Expected 4 values")
        minx, miny, maxx, maxy = parts
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bbox format: {e}. Expected: minx,miny,maxx,maxy",
        )

    # Validate bbox
    if minx >= maxx or miny >= maxy:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: min values must be less than max values",
        )

    # Query parcels intersecting bbox using GIST index
    query = text("""
        SELECT
            id,
            source_id,
            ST_X(ST_Centroid(geom)) as centroid_lon,
            ST_Y(ST_Centroid(geom)) as centroid_lat,
            recorded_acres,
            calculated_acres
        FROM parcels
        WHERE geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
        ORDER BY id
        LIMIT :limit
    """)

    result = db.execute(
        query,
        {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy, "limit": limit},
    )

    parcels = [
        ParcelSummary(
            id=row.id,
            source_id=row.source_id,
            centroid_lon=row.centroid_lon,
            centroid_lat=row.centroid_lat,
            recorded_acres=row.recorded_acres,
            calculated_acres=row.calculated_acres,
        )
        for row in result
    ]

    return parcels


@router.get("/parcels/geojson", response_model=list[ParcelWithGeometry])
def list_parcels_geojson(
    bbox: Optional[str] = Query(
        None,
        description="Bounding box as minx,miny,maxx,maxy in WGS84 coordinates",
        examples=["-98.8,29.8,-98.6,30.0"],
    ),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of parcels to return"),
    db: Session = Depends(get_db),
):
    """
    Get parcels with full geometry for map rendering.

    Returns parcel polygons for displaying actual boundaries on the map.
    Limited to 500 to keep response size manageable.
    """
    if bbox is None:
        raise HTTPException(
            status_code=400,
            detail="bbox parameter is required. Format: minx,miny,maxx,maxy",
        )

    # Parse bbox
    try:
        parts = [float(x.strip()) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("Expected 4 values")
        minx, miny, maxx, maxy = parts
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bbox format: {e}. Expected: minx,miny,maxx,maxy",
        )

    # Validate bbox
    if minx >= maxx or miny >= maxy:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: min values must be less than max values",
        )

    # Query parcels intersecting bbox with geometry
    query = text("""
        SELECT
            id,
            source_id,
            calculated_acres,
            ST_AsGeoJSON(geom)::json as geometry
        FROM parcels
        WHERE geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
        ORDER BY calculated_acres DESC
        LIMIT :limit
    """)

    result = db.execute(
        query,
        {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy, "limit": limit},
    )

    parcels = [
        ParcelWithGeometry(
            id=row.id,
            source_id=row.source_id,
            calculated_acres=row.calculated_acres,
            geometry=row.geometry,
        )
        for row in result
    ]

    return parcels


@router.get("/parcels/{parcel_id}", response_model=ParcelDetail)
def get_parcel(parcel_id: int, db: Session = Depends(get_db)):
    """
    Get full parcel details including geometry.
    """
    query = text("""
        SELECT
            id,
            source_id,
            owner_name,
            address,
            recorded_acres,
            calculated_acres,
            county,
            ST_AsGeoJSON(geom)::json as geometry
        FROM parcels
        WHERE id = :parcel_id
    """)

    result = db.execute(query, {"parcel_id": parcel_id}).fetchone()

    if result is None:
        raise HTTPException(status_code=404, detail=f"Parcel {parcel_id} not found")

    return ParcelDetail(
        id=result.id,
        source_id=result.source_id,
        owner_name=result.owner_name,
        address=result.address,
        recorded_acres=result.recorded_acres,
        calculated_acres=result.calculated_acres,
        county=result.county,
        geometry=result.geometry,
    )


@router.get("/parcels/{parcel_id}/constraints", response_model=ConstraintsResponse)
def get_parcel_constraints(parcel_id: int, db: Session = Depends(get_db)):
    """
    Get wetlands and floodplains that intersect with a parcel.

    Uses bbox-filtered spatial query with GIST index for performance.
    """
    # First verify parcel exists and get its bbox for efficient querying
    parcel_check = text("""
        SELECT
            id,
            ST_XMin(geom) as minx,
            ST_YMin(geom) as miny,
            ST_XMax(geom) as maxx,
            ST_YMax(geom) as maxy
        FROM parcels
        WHERE id = :parcel_id
    """)
    parcel_result = db.execute(parcel_check, {"parcel_id": parcel_id}).fetchone()

    if parcel_result is None:
        raise HTTPException(status_code=404, detail=f"Parcel {parcel_id} not found")

    # Get wetlands intersecting parcel (bbox filter first, then precise intersection)
    wetlands_query = text("""
        SELECT
            w.id,
            w.attribute,
            w.wetland_type,
            ST_AsGeoJSON(w.geom)::json as geometry
        FROM wetlands w
        JOIN parcels p ON p.id = :parcel_id
        WHERE w.geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          AND ST_Intersects(w.geom, p.geom)
    """)

    wetlands_result = db.execute(
        wetlands_query,
        {
            "parcel_id": parcel_id,
            "minx": parcel_result.minx,
            "miny": parcel_result.miny,
            "maxx": parcel_result.maxx,
            "maxy": parcel_result.maxy,
        },
    )

    wetlands = [
        WetlandFeature(
            id=row.id,
            attribute=row.attribute,
            wetland_type=row.wetland_type,
            geometry=row.geometry,
        )
        for row in wetlands_result
    ]

    # Get floodplains intersecting parcel
    floodplains_query = text("""
        SELECT
            f.id,
            f.fld_zone,
            f.zone_subty,
            ST_AsGeoJSON(f.geom)::json as geometry
        FROM floodplains f
        JOIN parcels p ON p.id = :parcel_id
        WHERE f.geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          AND ST_Intersects(f.geom, p.geom)
    """)

    floodplains_result = db.execute(
        floodplains_query,
        {
            "parcel_id": parcel_id,
            "minx": parcel_result.minx,
            "miny": parcel_result.miny,
            "maxx": parcel_result.maxx,
            "maxy": parcel_result.maxy,
        },
    )

    floodplains = [
        FloodplainFeature(
            id=row.id,
            fld_zone=row.fld_zone,
            zone_subty=row.zone_subty,
            geometry=row.geometry,
        )
        for row in floodplains_result
    ]

    return ConstraintsResponse(wetlands=wetlands, floodplains=floodplains)


@router.post("/parcels/{parcel_id}/buildable", response_model=BuildableResponse)
def calculate_buildable(
    parcel_id: int,
    request: BuildableRequest,
    db: Session = Depends(get_db),
):
    """
    Calculate buildable area for a parcel.

    Removes wetlands and floodplains (with configurable buffers) from the parcel,
    applies manual excludes/restores, and returns the buildable area with breakdown.

    NOTE: Breakdown entries can overlap (e.g., wetland buffer overlapping floodplain)
    so they may not sum exactly to total constrained area. This is expected behavior.
    """
    # Get parcel geometry
    parcel_query = text("""
        SELECT
            id,
            ST_AsGeoJSON(geom)::json as geometry,
            ST_XMin(geom) as minx,
            ST_YMin(geom) as miny,
            ST_XMax(geom) as maxx,
            ST_YMax(geom) as maxy
        FROM parcels
        WHERE id = :parcel_id
    """)
    parcel_result = db.execute(parcel_query, {"parcel_id": parcel_id}).fetchone()

    if parcel_result is None:
        raise HTTPException(status_code=404, detail=f"Parcel {parcel_id} not found")

    parcel_geom = geojson_to_shapely(parcel_result.geometry)

    if parcel_geom is None:
        raise HTTPException(
            status_code=400,
            detail="Parcel geometry is invalid",
        )

    # Get intersecting wetlands
    wetlands_query = text("""
        SELECT ST_AsGeoJSON(w.geom)::json as geometry
        FROM wetlands w
        JOIN parcels p ON p.id = :parcel_id
        WHERE w.geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          AND ST_Intersects(w.geom, p.geom)
    """)

    wetlands_result = db.execute(
        wetlands_query,
        {
            "parcel_id": parcel_id,
            "minx": parcel_result.minx,
            "miny": parcel_result.miny,
            "maxx": parcel_result.maxx,
            "maxy": parcel_result.maxy,
        },
    )

    wetland_geoms = [
        geojson_to_shapely(row.geometry)
        for row in wetlands_result
        if row.geometry is not None
    ]

    # Get intersecting floodplains
    floodplains_query = text("""
        SELECT ST_AsGeoJSON(f.geom)::json as geometry
        FROM floodplains f
        JOIN parcels p ON p.id = :parcel_id
        WHERE f.geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          AND ST_Intersects(f.geom, p.geom)
    """)

    floodplains_result = db.execute(
        floodplains_query,
        {
            "parcel_id": parcel_id,
            "minx": parcel_result.minx,
            "miny": parcel_result.miny,
            "maxx": parcel_result.maxx,
            "maxy": parcel_result.maxy,
        },
    )

    floodplain_geoms = [
        geojson_to_shapely(row.geometry)
        for row in floodplains_result
        if row.geometry is not None
    ]

    # Calculate buildable area
    try:
        result = calculate_buildable_area(
            parcel_geom=parcel_geom,
            wetland_geoms=wetland_geoms,
            floodplain_geoms=floodplain_geoms,
            wetland_buffer_ft=request.wetland_buffer_ft,
            floodplain_buffer_ft=request.floodplain_buffer_ft,
            manual_excludes=request.manual_excludes,
            manual_restores=request.manual_restores,
        )
    except Exception as e:
        logger.exception(f"Error calculating buildable area for parcel {parcel_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating buildable area: {str(e)}",
        )

    return BuildableResponse(
        buildable_acres=result.buildable_acres,
        parcel_acres=result.parcel_acres,
        constrained_acres=result.constrained_acres,
        buildable_geom=result.buildable_geom,
        breakdown=[
            BreakdownItem(reason=b.reason, acres=b.acres, type=b.constraint_type)
            for b in result.breakdown
        ],
        warnings=result.warnings,
    )
