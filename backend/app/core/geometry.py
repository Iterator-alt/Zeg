"""
Core geometry operations for buildable land calculation.

All area and buffer calculations use EPSG:6579 (NAD83 Texas Centric Albers Equal Area)
which is a meters-based equal area projection appropriate for Texas.

NEVER use EPSG:3857 (Web Mercator) for area calculations - it distorts area
significantly, especially at higher latitudes.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from shapely import make_valid
from shapely.geometry import shape, mapping, MultiPolygon, Polygon, GeometryCollection
from shapely.ops import unary_union
import pyproj
from pyproj import Transformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# CRS constants
WGS84 = "EPSG:4326"
TEXAS_ALBERS = "EPSG:6579"  # NAD83 Texas Centric Albers Equal Area (meters)

# Unit conversions
FEET_TO_METERS = 0.3048
SQ_METERS_TO_ACRES = 0.000247105

# Create transformers (thread-safe in pyproj >= 3.0)
transformer_to_projected = Transformer.from_crs(WGS84, TEXAS_ALBERS, always_xy=True)
transformer_to_wgs84 = Transformer.from_crs(TEXAS_ALBERS, WGS84, always_xy=True)


@dataclass
class ConstraintBreakdown:
    """Breakdown of a single constraint's impact on buildable area."""
    reason: str
    acres: float
    constraint_type: str  # "removed" or "added"

    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "acres": round(self.acres, 4),
            "type": self.constraint_type,
        }


@dataclass
class BuildableResult:
    """Result of buildable area calculation."""
    buildable_acres: float
    buildable_geom: dict  # GeoJSON
    breakdown: list[ConstraintBreakdown]
    warnings: list[str]
    parcel_acres: float
    constrained_acres: float

    def to_dict(self) -> dict:
        return {
            "buildable_acres": round(self.buildable_acres, 4),
            "buildable_geom": self.buildable_geom,
            "breakdown": [b.to_dict() for b in self.breakdown],
            "warnings": self.warnings,
            "parcel_acres": round(self.parcel_acres, 4),
            "constrained_acres": round(self.constrained_acres, 4),
        }


def validate_geometry(geom, name: str = "geometry") -> tuple[any, list[str]]:
    """
    Validate and repair a geometry.

    Uses shapely's make_valid to repair invalid geometries (self-intersections,
    slivers, etc.) that are common in real-world shapefile data.

    Args:
        geom: Shapely geometry
        name: Name for logging/warnings

    Returns:
        Tuple of (valid_geometry, list of warnings)
    """
    warnings = []

    if geom is None or geom.is_empty:
        warnings.append(f"{name} is empty or null")
        return None, warnings

    if not geom.is_valid:
        warnings.append(f"{name} was invalid and has been auto-repaired")
        geom = make_valid(geom)

        if geom is None or geom.is_empty:
            warnings.append(f"{name} could not be repaired")
            return None, warnings

    return geom, warnings


def transform_to_projected(geom):
    """
    Transform geometry from WGS84 to Texas Albers projected CRS.

    Args:
        geom: Shapely geometry in EPSG:4326

    Returns:
        Shapely geometry in EPSG:6579
    """
    if geom is None or geom.is_empty:
        return geom
    return transform_geometry(geom, transformer_to_projected)


def transform_to_wgs84(geom):
    """
    Transform geometry from Texas Albers back to WGS84.

    Args:
        geom: Shapely geometry in EPSG:6579

    Returns:
        Shapely geometry in EPSG:4326
    """
    if geom is None or geom.is_empty:
        return geom
    return transform_geometry(geom, transformer_to_wgs84)


def transform_geometry(geom, transformer: Transformer):
    """
    Transform a geometry using a pyproj transformer.

    Handles Polygon, MultiPolygon, and GeometryCollection types.
    """
    if geom is None or geom.is_empty:
        return geom

    if isinstance(geom, Polygon):
        return transform_polygon(geom, transformer)
    elif isinstance(geom, MultiPolygon):
        return MultiPolygon([transform_polygon(p, transformer) for p in geom.geoms])
    elif isinstance(geom, GeometryCollection):
        # Extract only polygon types
        polygons = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
        if not polygons:
            return None
        transformed = []
        for p in polygons:
            if isinstance(p, Polygon):
                transformed.append(transform_polygon(p, transformer))
            else:
                transformed.extend([transform_polygon(poly, transformer) for poly in p.geoms])
        return MultiPolygon(transformed) if transformed else None
    else:
        logger.warning(f"Unsupported geometry type for transformation: {geom.geom_type}")
        return None


def transform_polygon(poly: Polygon, transformer: Transformer) -> Polygon:
    """Transform a single polygon."""
    exterior = [transformer.transform(x, y) for x, y in poly.exterior.coords]
    interiors = [
        [transformer.transform(x, y) for x, y in ring.coords]
        for ring in poly.interiors
    ]
    return Polygon(exterior, interiors)


def buffer_geometry(geom, distance_feet: float):
    """
    Buffer a geometry by a distance in feet.

    The geometry must already be in the projected CRS (EPSG:6579, meters).

    Args:
        geom: Shapely geometry in EPSG:6579
        distance_feet: Buffer distance in feet

    Returns:
        Buffered geometry in EPSG:6579
    """
    if geom is None or geom.is_empty or distance_feet <= 0:
        return geom

    # Convert feet to meters (EPSG:6579 uses meters)
    distance_meters = distance_feet * FEET_TO_METERS

    return geom.buffer(distance_meters)


def calculate_area_acres(geom) -> float:
    """
    Calculate area in acres.

    The geometry must already be in the projected CRS (EPSG:6579, meters).

    Args:
        geom: Shapely geometry in EPSG:6579

    Returns:
        Area in acres
    """
    if geom is None or geom.is_empty:
        return 0.0

    # Area in square meters, convert to acres
    return geom.area * SQ_METERS_TO_ACRES


def ensure_multipolygon(geom) -> Optional[MultiPolygon]:
    """
    Ensure geometry is a MultiPolygon.

    Handles Polygon, MultiPolygon, and GeometryCollection types.
    """
    if geom is None or geom.is_empty:
        return None

    if isinstance(geom, MultiPolygon):
        return geom
    elif isinstance(geom, Polygon):
        return MultiPolygon([geom])
    elif isinstance(geom, GeometryCollection):
        polygons = []
        for g in geom.geoms:
            if isinstance(g, Polygon):
                polygons.append(g)
            elif isinstance(g, MultiPolygon):
                polygons.extend(g.geoms)
        return MultiPolygon(polygons) if polygons else None
    else:
        return None


def geojson_to_shapely(geojson: dict):
    """Convert GeoJSON dict to Shapely geometry."""
    try:
        return shape(geojson)
    except Exception as e:
        logger.error(f"Failed to parse GeoJSON: {e}")
        return None


def shapely_to_geojson(geom) -> Optional[dict]:
    """Convert Shapely geometry to GeoJSON dict."""
    if geom is None or geom.is_empty:
        return None
    try:
        return mapping(geom)
    except Exception as e:
        logger.error(f"Failed to convert to GeoJSON: {e}")
        return None


def calculate_buildable_area(
    parcel_geom,
    wetland_geoms: list,
    floodplain_geoms: list,
    wetland_buffer_ft: float,
    floodplain_buffer_ft: float,
    manual_excludes: list = None,
    manual_restores: list = None,
) -> BuildableResult:
    """
    Calculate buildable area for a parcel after removing constraints.

    Algorithm:
    1. Reproject parcel to projected CRS (EPSG:6579)
    2. Validate all geometries
    3. Buffer each constraint layer independently
    4. Union all buffered constraints into single "constrained" shape
    5. buildable = parcel - constrained
    6. buildable = buildable - union(manual_excludes)
    7. buildable = buildable ∪ (union(manual_restores) ∩ parcel)
    8. Calculate acreage and breakdown

    NOTE: Breakdown entries can overlap (e.g., wetland buffer overlapping floodplain)
    so they may not sum exactly to total constrained area. This is expected behavior
    and is documented in the API response.

    Args:
        parcel_geom: Parcel geometry (WGS84)
        wetland_geoms: List of wetland geometries (WGS84)
        floodplain_geoms: List of floodplain geometries (WGS84)
        wetland_buffer_ft: Buffer distance for wetlands in feet
        floodplain_buffer_ft: Buffer distance for floodplains in feet
        manual_excludes: List of manual exclude geometries (WGS84 GeoJSON dicts)
        manual_restores: List of manual restore geometries (WGS84 GeoJSON dicts)

    Returns:
        BuildableResult with calculated areas and breakdown
    """
    warnings = []
    breakdown = []

    manual_excludes = manual_excludes or []
    manual_restores = manual_restores or []

    # Step 1: Validate and transform parcel to projected CRS
    parcel_geom, parcel_warnings = validate_geometry(parcel_geom, "parcel")
    warnings.extend(parcel_warnings)

    if parcel_geom is None:
        return BuildableResult(
            buildable_acres=0.0,
            buildable_geom=None,
            breakdown=[],
            warnings=["Parcel geometry is invalid or empty"],
            parcel_acres=0.0,
            constrained_acres=0.0,
        )

    parcel_projected = transform_to_projected(parcel_geom)
    parcel_acres = calculate_area_acres(parcel_projected)

    # Step 2: Process wetlands - validate, transform, buffer
    wetland_buffered_geoms = []
    wetland_raw_geoms = []  # For breakdown calculation (unbuffered intersection)

    for i, wg in enumerate(wetland_geoms):
        wg_valid, wg_warnings = validate_geometry(wg, f"wetland_{i}")
        warnings.extend(wg_warnings)

        if wg_valid is not None:
            wg_projected = transform_to_projected(wg_valid)
            wetland_raw_geoms.append(wg_projected)

            if wetland_buffer_ft > 0:
                wg_buffered = buffer_geometry(wg_projected, wetland_buffer_ft)
            else:
                wg_buffered = wg_projected
            wetland_buffered_geoms.append(wg_buffered)

    # Step 3: Process floodplains - validate, transform, buffer
    floodplain_buffered_geoms = []
    floodplain_raw_geoms = []

    for i, fg in enumerate(floodplain_geoms):
        fg_valid, fg_warnings = validate_geometry(fg, f"floodplain_{i}")
        warnings.extend(fg_warnings)

        if fg_valid is not None:
            fg_projected = transform_to_projected(fg_valid)
            floodplain_raw_geoms.append(fg_projected)

            if floodplain_buffer_ft > 0:
                fg_buffered = buffer_geometry(fg_projected, floodplain_buffer_ft)
            else:
                fg_buffered = fg_projected
            floodplain_buffered_geoms.append(fg_buffered)

    # Step 4: Union all buffered constraints
    all_constraints = wetland_buffered_geoms + floodplain_buffered_geoms

    if all_constraints:
        constrained_union = unary_union(all_constraints)
        constrained_union, _ = validate_geometry(constrained_union, "constrained_union")
    else:
        constrained_union = None

    # Step 5: Calculate buildable = parcel - constraints
    if constrained_union is not None and not constrained_union.is_empty:
        # Clip constraints to parcel boundary
        constrained_in_parcel = parcel_projected.intersection(constrained_union)
        constrained_in_parcel, _ = validate_geometry(constrained_in_parcel, "constrained_in_parcel")

        if constrained_in_parcel is not None and not constrained_in_parcel.is_empty:
            buildable = parcel_projected.difference(constrained_in_parcel)
        else:
            buildable = parcel_projected
    else:
        buildable = parcel_projected
        constrained_in_parcel = None

    buildable, _ = validate_geometry(buildable, "buildable")

    # Step 6: Calculate breakdown for each constraint type
    # NOTE: These can overlap, so they may not sum to total constrained

    # Wetland breakdown (with buffer)
    if wetland_buffered_geoms:
        wetland_union = unary_union(wetland_buffered_geoms)
        wetland_in_parcel = parcel_projected.intersection(wetland_union)
        wetland_in_parcel, _ = validate_geometry(wetland_in_parcel, "wetland_intersection")

        if wetland_in_parcel is not None and not wetland_in_parcel.is_empty:
            wetland_acres = calculate_area_acres(wetland_in_parcel)
            buffer_note = f" (with {wetland_buffer_ft}ft buffer)" if wetland_buffer_ft > 0 else ""
            breakdown.append(ConstraintBreakdown(
                reason=f"Wetlands{buffer_note}",
                acres=wetland_acres,
                constraint_type="removed",
            ))

    # Floodplain breakdown (with buffer)
    if floodplain_buffered_geoms:
        floodplain_union = unary_union(floodplain_buffered_geoms)
        floodplain_in_parcel = parcel_projected.intersection(floodplain_union)
        floodplain_in_parcel, _ = validate_geometry(floodplain_in_parcel, "floodplain_intersection")

        if floodplain_in_parcel is not None and not floodplain_in_parcel.is_empty:
            floodplain_acres = calculate_area_acres(floodplain_in_parcel)
            buffer_note = f" (with {floodplain_buffer_ft}ft buffer)" if floodplain_buffer_ft > 0 else ""
            breakdown.append(ConstraintBreakdown(
                reason=f"FEMA Floodplain{buffer_note}",
                acres=floodplain_acres,
                constraint_type="removed",
            ))

    # Step 7: Process manual excludes
    if manual_excludes and buildable is not None:
        exclude_geoms = []
        for i, exc in enumerate(manual_excludes):
            exc_geom = geojson_to_shapely(exc) if isinstance(exc, dict) else exc
            exc_valid, exc_warnings = validate_geometry(exc_geom, f"manual_exclude_{i}")
            warnings.extend(exc_warnings)

            if exc_valid is not None:
                exc_projected = transform_to_projected(exc_valid)
                exclude_geoms.append(exc_projected)

        if exclude_geoms:
            exclude_union = unary_union(exclude_geoms)
            # Only exclude area within parcel
            exclude_in_parcel = parcel_projected.intersection(exclude_union)
            exclude_in_parcel, _ = validate_geometry(exclude_in_parcel, "exclude_intersection")

            if exclude_in_parcel is not None and not exclude_in_parcel.is_empty:
                exclude_acres = calculate_area_acres(exclude_in_parcel)
                buildable = buildable.difference(exclude_in_parcel)
                buildable, _ = validate_geometry(buildable, "buildable_after_exclude")

                breakdown.append(ConstraintBreakdown(
                    reason="Manual exclusion",
                    acres=exclude_acres,
                    constraint_type="removed",
                ))

    # Step 8: Process manual restores
    if manual_restores:
        restore_geoms = []
        for i, rst in enumerate(manual_restores):
            rst_geom = geojson_to_shapely(rst) if isinstance(rst, dict) else rst
            rst_valid, rst_warnings = validate_geometry(rst_geom, f"manual_restore_{i}")
            warnings.extend(rst_warnings)

            if rst_valid is not None:
                rst_projected = transform_to_projected(rst_valid)
                restore_geoms.append(rst_projected)

        if restore_geoms:
            restore_union = unary_union(restore_geoms)
            # Restores can only reclaim area within the original parcel
            restore_in_parcel = parcel_projected.intersection(restore_union)
            restore_in_parcel, _ = validate_geometry(restore_in_parcel, "restore_intersection")

            if restore_in_parcel is not None and not restore_in_parcel.is_empty:
                restore_acres = calculate_area_acres(restore_in_parcel)

                if buildable is not None:
                    buildable = buildable.union(restore_in_parcel)
                else:
                    buildable = restore_in_parcel
                buildable, _ = validate_geometry(buildable, "buildable_after_restore")

                breakdown.append(ConstraintBreakdown(
                    reason="Manual restoration",
                    acres=restore_acres,
                    constraint_type="added",
                ))

    # Step 9: Calculate final results
    if buildable is None or buildable.is_empty:
        buildable_acres = 0.0
        buildable_geojson = None
    else:
        buildable_acres = calculate_area_acres(buildable)
        # Transform back to WGS84 for GeoJSON output
        buildable_wgs84 = transform_to_wgs84(buildable)
        buildable_wgs84 = ensure_multipolygon(buildable_wgs84)
        buildable_geojson = shapely_to_geojson(buildable_wgs84)

    # Calculate total constrained acres
    constrained_acres = parcel_acres - buildable_acres

    return BuildableResult(
        buildable_acres=buildable_acres,
        buildable_geom=buildable_geojson,
        breakdown=breakdown,
        warnings=warnings,
        parcel_acres=parcel_acres,
        constrained_acres=constrained_acres,
    )
