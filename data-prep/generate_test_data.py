#!/usr/bin/env python3
"""
Generate Synthetic Test Data for Buildable Land Analysis

This script creates synthetic parcel, wetland, and floodplain data for testing
purposes. The geometries are simple and predictable, making it easy to verify
the correctness of area calculations.

All geometries are created in EPSG:4326 (WGS84) with coordinates centered
around Kendall County, Texas (approximately -98.7, 29.9).

Test Parcels:
1. A 10-acre square parcel (known dimensions for validation)
2. A 5-acre rectangular parcel with wetland intersection
3. A 20-acre irregular parcel with floodplain intersection
4. A complex parcel with both wetland and floodplain overlap

Usage:
    python generate_test_data.py --output-dir ./raw_data
"""

import argparse
import logging
import os
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, box
from shapely import make_valid
import pyproj

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Center coordinates for Kendall County, TX
CENTER_LON = -98.7
CENTER_LAT = 29.9

# CRS
WGS84 = "EPSG:4326"
TEXAS_ALBERS = "EPSG:6579"

# Conversion: 1 acre = 4046.86 square meters
ACRE_TO_SQ_METERS = 4046.86


def meters_to_degrees_at_lat(meters: float, latitude: float) -> tuple[float, float]:
    """
    Convert meters to approximate degrees at a given latitude.

    Returns (lon_degrees, lat_degrees) for the given distance in meters.
    """
    # Approximate conversion factors
    # 1 degree latitude ≈ 111,320 meters
    # 1 degree longitude ≈ 111,320 * cos(latitude) meters
    lat_deg = meters / 111320
    lon_deg = meters / (111320 * np.cos(np.radians(latitude)))
    return lon_deg, lat_deg


def create_square_parcel_acres(center_lon: float, center_lat: float, acres: float) -> Polygon:
    """
    Create a square parcel of specified acreage.

    Uses projected CRS for accurate sizing, then converts back to WGS84.
    """
    # Calculate side length in meters
    area_sq_meters = acres * ACRE_TO_SQ_METERS
    side_length = np.sqrt(area_sq_meters)

    # Create square in projected CRS
    transformer_to_proj = pyproj.Transformer.from_crs(WGS84, TEXAS_ALBERS, always_xy=True)
    transformer_to_wgs = pyproj.Transformer.from_crs(TEXAS_ALBERS, WGS84, always_xy=True)

    # Transform center point to projected CRS
    cx, cy = transformer_to_proj.transform(center_lon, center_lat)

    # Create square around center
    half_side = side_length / 2
    coords_proj = [
        (cx - half_side, cy - half_side),
        (cx + half_side, cy - half_side),
        (cx + half_side, cy + half_side),
        (cx - half_side, cy + half_side),
        (cx - half_side, cy - half_side),
    ]

    # Transform back to WGS84
    coords_wgs = [transformer_to_wgs.transform(x, y) for x, y in coords_proj]

    return Polygon(coords_wgs)


def create_rectangle_parcel_acres(
    center_lon: float, center_lat: float, acres: float, aspect_ratio: float = 2.0
) -> Polygon:
    """
    Create a rectangular parcel of specified acreage.
    """
    area_sq_meters = acres * ACRE_TO_SQ_METERS
    # width * height = area, width/height = aspect_ratio
    height = np.sqrt(area_sq_meters / aspect_ratio)
    width = height * aspect_ratio

    transformer_to_proj = pyproj.Transformer.from_crs(WGS84, TEXAS_ALBERS, always_xy=True)
    transformer_to_wgs = pyproj.Transformer.from_crs(TEXAS_ALBERS, WGS84, always_xy=True)

    cx, cy = transformer_to_proj.transform(center_lon, center_lat)

    coords_proj = [
        (cx - width / 2, cy - height / 2),
        (cx + width / 2, cy - height / 2),
        (cx + width / 2, cy + height / 2),
        (cx - width / 2, cy + height / 2),
        (cx - width / 2, cy - height / 2),
    ]

    coords_wgs = [transformer_to_wgs.transform(x, y) for x, y in coords_proj]
    return Polygon(coords_wgs)


def create_wetland_polygon(
    center_lon: float, center_lat: float, acres: float
) -> Polygon:
    """Create a simple wetland polygon."""
    return create_square_parcel_acres(center_lon, center_lat, acres)


def create_floodplain_polygon(
    center_lon: float, center_lat: float, width_meters: float, height_meters: float
) -> Polygon:
    """Create a rectangular floodplain polygon (simulating a river corridor)."""
    transformer_to_proj = pyproj.Transformer.from_crs(WGS84, TEXAS_ALBERS, always_xy=True)
    transformer_to_wgs = pyproj.Transformer.from_crs(TEXAS_ALBERS, WGS84, always_xy=True)

    cx, cy = transformer_to_proj.transform(center_lon, center_lat)

    coords_proj = [
        (cx - width_meters / 2, cy - height_meters / 2),
        (cx + width_meters / 2, cy - height_meters / 2),
        (cx + width_meters / 2, cy + height_meters / 2),
        (cx - width_meters / 2, cy + height_meters / 2),
        (cx - width_meters / 2, cy - height_meters / 2),
    ]

    coords_wgs = [transformer_to_wgs.transform(x, y) for x, y in coords_proj]
    return Polygon(coords_wgs)


def generate_test_parcels() -> gpd.GeoDataFrame:
    """Generate synthetic test parcels."""
    parcels = []

    # Parcel 1: 10-acre square, no constraints (baseline test)
    parcels.append({
        "source_id": "TEST-001",
        "owner_name": "Test Owner A",
        "address": "100 Test Road",
        "recorded_acres": 10.0,
        "county": "Kendall",
        "geometry": MultiPolygon([create_square_parcel_acres(CENTER_LON, CENTER_LAT, 10.0)]),
    })

    # Parcel 2: 10-acre square with 2-acre wetland in center
    # Wetland will be created separately
    parcels.append({
        "source_id": "TEST-002",
        "owner_name": "Test Owner B",
        "address": "200 Test Road",
        "recorded_acres": 10.0,
        "county": "Kendall",
        "geometry": MultiPolygon([create_square_parcel_acres(CENTER_LON + 0.01, CENTER_LAT, 10.0)]),
    })

    # Parcel 3: 20-acre rectangle with floodplain on one end
    parcels.append({
        "source_id": "TEST-003",
        "owner_name": "Test Owner C",
        "address": "300 Test Road",
        "recorded_acres": 20.0,
        "county": "Kendall",
        "geometry": MultiPolygon([create_rectangle_parcel_acres(CENTER_LON + 0.02, CENTER_LAT, 20.0, 2.0)]),
    })

    # Parcel 4: 15-acre square with both wetland and floodplain overlap
    parcels.append({
        "source_id": "TEST-004",
        "owner_name": "Test Owner D",
        "address": "400 Test Road",
        "recorded_acres": 15.0,
        "county": "Kendall",
        "geometry": MultiPolygon([create_square_parcel_acres(CENTER_LON + 0.03, CENTER_LAT, 15.0)]),
    })

    # Parcel 5: Small 2-acre parcel, entirely in floodplain
    parcels.append({
        "source_id": "TEST-005",
        "owner_name": "Test Owner E",
        "address": "500 Test Road",
        "recorded_acres": 2.0,
        "county": "Kendall",
        "geometry": MultiPolygon([create_square_parcel_acres(CENTER_LON + 0.04, CENTER_LAT, 2.0)]),
    })

    gdf = gpd.GeoDataFrame(parcels, crs=WGS84)
    return gdf


def generate_test_wetlands() -> gpd.GeoDataFrame:
    """Generate synthetic test wetlands."""
    wetlands = []

    # Wetland 1: 2-acre wetland centered in Parcel 2
    wetlands.append({
        "attribute": "PFO1A",
        "wetland_type": "Forested Wetland",
        "source_id": "NWI-TEST-001",
        "geometry": MultiPolygon([create_wetland_polygon(CENTER_LON + 0.01, CENTER_LAT, 2.0)]),
    })

    # Wetland 2: 3-acre wetland overlapping Parcel 4
    wetlands.append({
        "attribute": "PEM1C",
        "wetland_type": "Emergent Wetland",
        "source_id": "NWI-TEST-002",
        "geometry": MultiPolygon([create_wetland_polygon(CENTER_LON + 0.03, CENTER_LAT + 0.002, 3.0)]),
    })

    gdf = gpd.GeoDataFrame(wetlands, crs=WGS84)
    return gdf


def generate_test_floodplains() -> gpd.GeoDataFrame:
    """Generate synthetic test floodplains."""
    floodplains = []

    # Floodplain 1: Strip across southern portion of Parcel 3
    # 100m wide, 1000m long
    floodplains.append({
        "fld_zone": "AE",
        "zone_subty": None,
        "static_bfe": "1000",
        "source_id": "FEMA-TEST-001",
        "sfha_tf": "T",
        "geometry": MultiPolygon([create_floodplain_polygon(CENTER_LON + 0.02, CENTER_LAT - 0.001, 1000, 100)]),
    })

    # Floodplain 2: Overlapping Parcel 4 (with wetland)
    floodplains.append({
        "fld_zone": "A",
        "zone_subty": None,
        "static_bfe": None,
        "source_id": "FEMA-TEST-002",
        "sfha_tf": "T",
        "geometry": MultiPolygon([create_floodplain_polygon(CENTER_LON + 0.03, CENTER_LAT - 0.001, 500, 200)]),
    })

    # Floodplain 3: Completely covers Parcel 5
    floodplains.append({
        "fld_zone": "AE",
        "zone_subty": None,
        "static_bfe": "995",
        "source_id": "FEMA-TEST-003",
        "sfha_tf": "T",
        "geometry": MultiPolygon([create_floodplain_polygon(CENTER_LON + 0.04, CENTER_LAT, 500, 500)]),
    })

    gdf = gpd.GeoDataFrame(floodplains, crs=WGS84)
    return gdf


def save_to_shapefile(gdf: gpd.GeoDataFrame, output_dir: Path, name: str) -> None:
    """Save GeoDataFrame to shapefile."""
    output_path = output_dir / f"{name}.shp"
    gdf.to_file(output_path)
    logger.info(f"Saved {len(gdf)} features to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic test data")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./raw_data"),
        help="Output directory for shapefiles",
    )
    args = parser.parse_args()

    # Create directories
    (args.output_dir / "parcels").mkdir(parents=True, exist_ok=True)
    (args.output_dir / "wetlands").mkdir(parents=True, exist_ok=True)
    (args.output_dir / "floodplains").mkdir(parents=True, exist_ok=True)

    # Generate and save parcels
    logger.info("Generating test parcels...")
    parcels_gdf = generate_test_parcels()
    save_to_shapefile(parcels_gdf, args.output_dir / "parcels", "test_parcels")

    # Calculate expected areas for verification
    parcels_proj = parcels_gdf.to_crs(TEXAS_ALBERS)
    for idx, row in parcels_proj.iterrows():
        calc_acres = row.geometry.area / ACRE_TO_SQ_METERS
        logger.info(f"  Parcel {row['source_id']}: {calc_acres:.2f} acres (expected: {row['recorded_acres']})")

    # Generate and save wetlands
    logger.info("Generating test wetlands...")
    wetlands_gdf = generate_test_wetlands()
    save_to_shapefile(wetlands_gdf, args.output_dir / "wetlands", "test_wetlands")

    # Generate and save floodplains
    logger.info("Generating test floodplains...")
    floodplains_gdf = generate_test_floodplains()
    save_to_shapefile(floodplains_gdf, args.output_dir / "floodplains", "test_floodplains")

    logger.info("\n✓ Test data generation complete!")
    logger.info(f"  Parcels: {len(parcels_gdf)}")
    logger.info(f"  Wetlands: {len(wetlands_gdf)}")
    logger.info(f"  Floodplains: {len(floodplains_gdf)}")


if __name__ == "__main__":
    main()
