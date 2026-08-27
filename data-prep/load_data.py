#!/usr/bin/env python3
"""
Data Preparation Script for Buildable Land Analysis

This script loads parcel, wetland, and floodplain data into PostGIS.
It is idempotent (safe to re-run) and logs row counts at each step.

Data Sources:
- Parcels: TNRIS (Texas Natural Resources Information System) - Kendall County
- Wetlands: USFWS National Wetlands Inventory (NWI)
- Floodplains: FEMA National Flood Hazard Layer (NFHL) - 100-year flood zones

Usage:
    python load_data.py --data-dir ./raw_data

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (with PostGIS)
                  Default: postgresql://postgres:postgres@localhost:5435/buildable_land

Data Directory Structure Expected:
    raw_data/
        parcels/          - Kendall County parcel shapefile(s)
        wetlands/         - NWI wetland shapefile(s)
        floodplains/      - FEMA NFHL shapefile(s)
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# CRS Configuration
STORAGE_CRS = "EPSG:4326"  # WGS84 for storage
PROJECTED_CRS = "EPSG:6579"  # NAD83 Texas Centric Albers Equal Area (meters)

# County configuration
COUNTY_NAME = "Kendall"
COUNTY_FIPS = "48259"  # Texas (48) + Kendall County (259)

# Conversion: square meters to acres
SQ_METERS_TO_ACRES = 0.000247105


def get_database_url() -> str:
    """Get database URL from environment or use default."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5435/buildable_land",
    )


def ensure_postgis_extension(engine) -> None:
    """Ensure PostGIS extension is enabled."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()
    logger.info("PostGIS extension verified")


def validate_and_fix_geometry(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Validate and fix geometries in a GeoDataFrame.

    Uses shapely's make_valid to repair invalid geometries (self-intersections,
    slivers, etc.) that are common in real-world shapefile data.

    Args:
        gdf: Input GeoDataFrame

    Returns:
        GeoDataFrame with valid geometries
    """
    initial_count = len(gdf)

    # Remove null geometries
    gdf = gdf[~gdf.geometry.isna()].copy()
    after_null_removal = len(gdf)
    if after_null_removal < initial_count:
        logger.warning(
            f"Removed {initial_count - after_null_removal} rows with null geometries"
        )

    # Check for invalid geometries
    invalid_mask = ~gdf.geometry.is_valid
    invalid_count = invalid_mask.sum()

    if invalid_count > 0:
        logger.warning(f"Found {invalid_count} invalid geometries, attempting repair...")

        # Apply make_valid to fix invalid geometries
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].apply(
            make_valid
        )

        # Re-check validity
        still_invalid = (~gdf.geometry.is_valid).sum()
        if still_invalid > 0:
            logger.error(
                f"{still_invalid} geometries could not be repaired, removing them"
            )
            gdf = gdf[gdf.geometry.is_valid].copy()

    # Remove empty geometries
    empty_mask = gdf.geometry.is_empty
    if empty_mask.sum() > 0:
        logger.warning(f"Removing {empty_mask.sum()} empty geometries")
        gdf = gdf[~empty_mask].copy()

    logger.info(f"Geometry validation complete: {len(gdf)} valid features")
    return gdf


def ensure_multipolygon(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Ensure all geometries are MultiPolygons for consistency.

    Args:
        gdf: Input GeoDataFrame

    Returns:
        GeoDataFrame with MultiPolygon geometries
    """

    def to_multipolygon(geom):
        if geom is None:
            return None
        if isinstance(geom, MultiPolygon):
            return geom
        if isinstance(geom, Polygon):
            return MultiPolygon([geom])
        # For GeometryCollections, extract polygons
        if geom.geom_type == "GeometryCollection":
            polygons = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
            if not polygons:
                return None
            all_polys = []
            for p in polygons:
                if isinstance(p, Polygon):
                    all_polys.append(p)
                else:
                    all_polys.extend(p.geoms)
            return MultiPolygon(all_polys) if all_polys else None
        return None

    gdf["geometry"] = gdf["geometry"].apply(to_multipolygon)
    gdf = gdf[~gdf.geometry.isna()].copy()
    return gdf


def calculate_acres(gdf: gpd.GeoDataFrame) -> pd.Series:
    """
    Calculate acreage using the projected CRS.

    Args:
        gdf: GeoDataFrame (will be temporarily reprojected)

    Returns:
        Series of acre values
    """
    # Reproject to Texas Centric Albers for accurate area calculation
    gdf_projected = gdf.to_crs(PROJECTED_CRS)
    # Area in square meters, convert to acres
    return gdf_projected.geometry.area * SQ_METERS_TO_ACRES


def load_parcels(data_dir: Path, engine) -> int:
    """
    Load parcel data into PostGIS.

    Args:
        data_dir: Path to raw data directory
        engine: SQLAlchemy engine

    Returns:
        Number of parcels loaded
    """
    parcel_dir = data_dir / "parcels"

    if not parcel_dir.exists():
        logger.error(f"Parcels directory not found: {parcel_dir}")
        logger.info(
            "Please download Kendall County parcel data from TNRIS and place in parcels/"
        )
        return 0

    # Find shapefile(s)
    shapefiles = list(parcel_dir.glob("*.shp"))
    if not shapefiles:
        logger.error(f"No shapefiles found in {parcel_dir}")
        return 0

    logger.info(f"Found {len(shapefiles)} parcel shapefile(s)")

    all_parcels = []
    for shp in shapefiles:
        logger.info(f"Reading {shp.name}...")
        gdf = gpd.read_file(shp)
        logger.info(f"  Raw row count: {len(gdf)}")
        logger.info(f"  Original CRS: {gdf.crs}")
        all_parcels.append(gdf)

    # Combine if multiple files
    gdf = gpd.GeoDataFrame(pd.concat(all_parcels, ignore_index=True))
    logger.info(f"Combined parcel count: {len(gdf)}")

    # Validate geometries
    gdf = validate_and_fix_geometry(gdf)

    # Ensure MultiPolygon type
    gdf = ensure_multipolygon(gdf)
    logger.info(f"After geometry processing: {len(gdf)} parcels")

    # Reproject to storage CRS
    if gdf.crs is None:
        logger.warning("No CRS defined, assuming EPSG:4326")
        gdf = gdf.set_crs(STORAGE_CRS)
    elif gdf.crs.to_epsg() != 4326:
        logger.info(f"Reprojecting from {gdf.crs} to {STORAGE_CRS}")
        gdf = gdf.to_crs(STORAGE_CRS)

    # Calculate acres in projected CRS
    logger.info("Calculating acreage in projected CRS (EPSG:6579)...")
    gdf["calculated_acres"] = calculate_acres(gdf)

    # Map columns to our schema
    # Column names vary by county/source, so we try common names
    column_mapping = {
        # Common parcel ID fields
        "PROP_ID": "source_id",
        "PARCEL_ID": "source_id",
        "GEO_ID": "source_id",
        "PIN": "source_id",
        "APN": "source_id",
        # Owner fields
        "OWNER": "owner_name",
        "OWNER_NAME": "owner_name",
        "OWN_NAME": "owner_name",
        # Address fields
        "SITUS_ADDR": "address",
        "SITE_ADDR": "address",
        "ADDRESS": "address",
        "PROP_ADDR": "address",
        # Acreage fields (recorded from source)
        "ACRES": "recorded_acres",
        "ACREAGE": "recorded_acres",
        "GIS_ACRES": "recorded_acres",
        "LAND_ACRES": "recorded_acres",
    }

    # Rename columns that exist
    rename_cols = {}
    for src, dst in column_mapping.items():
        # Case-insensitive matching
        for col in gdf.columns:
            if col.upper() == src.upper() and dst not in rename_cols.values():
                rename_cols[col] = dst
                break

    gdf = gdf.rename(columns=rename_cols)
    logger.info(f"Mapped columns: {rename_cols}")

    # Prepare final DataFrame
    final_cols = ["source_id", "owner_name", "address", "recorded_acres", "calculated_acres", "geometry"]
    for col in final_cols:
        if col not in gdf.columns and col != "geometry":
            gdf[col] = None

    gdf["county"] = COUNTY_NAME

    # Select only the columns we need
    gdf_final = gdf[["source_id", "owner_name", "address", "recorded_acres", "calculated_acres", "county", "geometry"]].copy()
    # Rename geometry column to match table schema
    gdf_final = gdf_final.rename_geometry("geom")

    # Clear existing data (idempotent)
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE parcels CASCADE"))
        conn.commit()
    logger.info("Cleared existing parcel data")

    # Load to PostGIS
    logger.info("Loading parcels to PostGIS...")
    gdf_final.to_postgis(
        "parcels",
        engine,
        if_exists="append",
        index=False,
    )

    # Verify count
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM parcels"))
        count = result.scalar()

    logger.info(f"[OK] Loaded {count} parcels to database")
    return count


def load_wetlands(data_dir: Path, engine, county_bounds: Optional[gpd.GeoDataFrame] = None) -> int:
    """
    Load wetland data from NWI into PostGIS.

    Args:
        data_dir: Path to raw data directory
        engine: SQLAlchemy engine
        county_bounds: Optional GeoDataFrame for clipping

    Returns:
        Number of wetlands loaded
    """
    wetland_dir = data_dir / "wetlands"

    if not wetland_dir.exists():
        logger.error(f"Wetlands directory not found: {wetland_dir}")
        logger.info(
            "Please download NWI wetland data for the county from fws.gov/wetlands/data"
        )
        return 0

    shapefiles = list(wetland_dir.glob("*.shp"))
    if not shapefiles:
        logger.error(f"No shapefiles found in {wetland_dir}")
        return 0

    logger.info(f"Found {len(shapefiles)} wetland shapefile(s)")

    all_wetlands = []
    for shp in shapefiles:
        logger.info(f"Reading {shp.name}...")
        gdf = gpd.read_file(shp)
        logger.info(f"  Raw row count: {len(gdf)}")
        all_wetlands.append(gdf)

    gdf = gpd.GeoDataFrame(pd.concat(all_wetlands, ignore_index=True))
    logger.info(f"Combined wetland count: {len(gdf)}")

    # Validate geometries
    gdf = validate_and_fix_geometry(gdf)
    gdf = ensure_multipolygon(gdf)

    # Reproject to storage CRS
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        logger.info(f"Reprojecting from {gdf.crs} to {STORAGE_CRS}")
        gdf = gdf.to_crs(STORAGE_CRS)
    elif gdf.crs is None:
        gdf = gdf.set_crs(STORAGE_CRS)

    # Clip to county bounds if provided
    if county_bounds is not None:
        logger.info("Clipping wetlands to county extent...")
        original_count = len(gdf)
        gdf = gpd.clip(gdf, county_bounds)
        gdf = validate_and_fix_geometry(gdf)
        gdf = ensure_multipolygon(gdf)
        logger.info(f"After clipping: {len(gdf)} wetlands (from {original_count})")

    # Map NWI attribute columns
    # NWI uses "ATTRIBUTE" or "WETLAND_TY" for the Cowardin code
    attribute_col = None
    for col in ["ATTRIBUTE", "WETLAND_TYPE", "WETLAND_TY", "NWI_CODE"]:
        if col in gdf.columns:
            attribute_col = col
            break

    if attribute_col:
        gdf["attribute"] = gdf[attribute_col]
    else:
        gdf["attribute"] = None

    # Create simplified wetland type from Cowardin code
    def parse_wetland_type(attr):
        if attr is None or pd.isna(attr):
            return "Unknown"
        attr = str(attr).upper()
        if attr.startswith("PEM"):
            return "Emergent Wetland"
        elif attr.startswith("PFO"):
            return "Forested Wetland"
        elif attr.startswith("PSS"):
            return "Scrub-Shrub Wetland"
        elif attr.startswith("PUB") or attr.startswith("L"):
            return "Open Water/Lake"
        elif attr.startswith("R"):
            return "Riverine"
        elif attr.startswith("E"):
            return "Estuarine"
        else:
            return "Other Wetland"

    gdf["wetland_type"] = gdf["attribute"].apply(parse_wetland_type)
    gdf["source_id"] = gdf.get("OBJECTID", gdf.index.astype(str))

    # Prepare final DataFrame
    gdf_final = gdf[["attribute", "wetland_type", "source_id", "geometry"]].copy()
    # Rename geometry column to match table schema
    gdf_final = gdf_final.rename_geometry("geom")

    # Clear existing data
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE wetlands"))
        conn.commit()
    logger.info("Cleared existing wetland data")

    # Load to PostGIS
    logger.info("Loading wetlands to PostGIS...")
    gdf_final.to_postgis(
        "wetlands",
        engine,
        if_exists="append",
        index=False,
    )

    # Verify count
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM wetlands"))
        count = result.scalar()

    logger.info(f"[OK] Loaded {count} wetlands to database")
    return count


def load_floodplains(data_dir: Path, engine, county_bounds: Optional[gpd.GeoDataFrame] = None) -> int:
    """
    Load floodplain data from FEMA NFHL into PostGIS.

    Filters for 100-year flood zones (Zone A, AE, AH, AO).

    Args:
        data_dir: Path to raw data directory
        engine: SQLAlchemy engine
        county_bounds: Optional GeoDataFrame for clipping

    Returns:
        Number of floodplain polygons loaded
    """
    flood_dir = data_dir / "floodplains"

    if not flood_dir.exists():
        logger.error(f"Floodplains directory not found: {flood_dir}")
        logger.info("Please download FEMA NFHL data from msc.fema.gov")
        return 0

    shapefiles = list(flood_dir.glob("*.shp"))
    if not shapefiles:
        # NFHL data often comes as geodatabase, check for that
        gdbs = list(flood_dir.glob("*.gdb"))
        if gdbs:
            logger.info(f"Found geodatabase: {gdbs[0]}")
            # Read the flood hazard layer
            try:
                gdf = gpd.read_file(gdbs[0], layer="S_FLD_HAZ_AR")
            except Exception:
                # Try listing layers
                import fiona
                layers = fiona.listlayers(gdbs[0])
                logger.info(f"Available layers: {layers}")
                # Look for flood hazard layer
                flood_layer = next(
                    (l for l in layers if "FLD" in l.upper() or "FLOOD" in l.upper()),
                    None,
                )
                if flood_layer:
                    gdf = gpd.read_file(gdbs[0], layer=flood_layer)
                else:
                    logger.error("Could not find flood hazard layer in geodatabase")
                    return 0
        else:
            logger.error(f"No shapefiles or geodatabases found in {flood_dir}")
            return 0
    else:
        logger.info(f"Found {len(shapefiles)} floodplain shapefile(s)")

        all_floods = []
        for shp in shapefiles:
            logger.info(f"Reading {shp.name}...")
            gdf = gpd.read_file(shp)
            logger.info(f"  Raw row count: {len(gdf)}")
            all_floods.append(gdf)

        gdf = gpd.GeoDataFrame(pd.concat(all_floods, ignore_index=True))

    logger.info(f"Combined floodplain count: {len(gdf)}")

    # Filter for 100-year flood zones (SFHA - Special Flood Hazard Area)
    # Zones: A, AE, AH, AO, AR, A99, V, VE
    zone_col = None
    for col in ["FLD_ZONE", "ZONE_", "FLOOD_ZONE", "SFHA_TF", "ZONE"]:
        if col in gdf.columns:
            zone_col = col
            break

    if zone_col:
        logger.info(f"Using zone column: {zone_col}")
        logger.info(f"Unique zones: {gdf[zone_col].unique()[:20]}")  # First 20

        # Filter for 100-year flood zones
        sfha_zones = ["A", "AE", "AH", "AO", "AR", "A99", "V", "VE"]
        gdf = gdf[gdf[zone_col].isin(sfha_zones)].copy()
        logger.info(f"After filtering for SFHA zones: {len(gdf)} features")
    else:
        # Check for SFHA_TF field (True/False for Special Flood Hazard Area)
        if "SFHA_TF" in gdf.columns:
            gdf = gdf[gdf["SFHA_TF"] == "T"].copy()
            logger.info(f"Filtered by SFHA_TF=T: {len(gdf)} features")

    if len(gdf) == 0:
        logger.warning("No 100-year flood zone features found")
        return 0

    # Validate geometries
    gdf = validate_and_fix_geometry(gdf)
    gdf = ensure_multipolygon(gdf)

    # Reproject to storage CRS
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        logger.info(f"Reprojecting from {gdf.crs} to {STORAGE_CRS}")
        gdf = gdf.to_crs(STORAGE_CRS)
    elif gdf.crs is None:
        gdf = gdf.set_crs(STORAGE_CRS)

    # Clip to county bounds if provided
    if county_bounds is not None:
        logger.info("Clipping floodplains to county extent...")
        original_count = len(gdf)
        gdf = gpd.clip(gdf, county_bounds)
        gdf = validate_and_fix_geometry(gdf)
        gdf = ensure_multipolygon(gdf)
        logger.info(f"After clipping: {len(gdf)} floodplains (from {original_count})")

    # Map columns - handle various column naming conventions
    if zone_col and zone_col in gdf.columns:
        gdf["fld_zone"] = gdf[zone_col]
    elif "fld_zone" not in gdf.columns:
        gdf["fld_zone"] = gdf.get("FLD_ZONE", None)
    # Otherwise fld_zone already exists in the dataframe (test data case)

    if "zone_subty" not in gdf.columns:
        gdf["zone_subty"] = gdf.get("ZONE_SUBTY", None)
    if "static_bfe" not in gdf.columns:
        gdf["static_bfe"] = gdf.get("STATIC_BFE", None)
    if "source_id" not in gdf.columns:
        gdf["source_id"] = gdf.get("DFIRM_ID", gdf.get("OBJECTID", gdf.index.astype(str)))
    if "sfha_tf" not in gdf.columns:
        gdf["sfha_tf"] = gdf.get("SFHA_TF", "T")

    # Prepare final DataFrame
    gdf_final = gdf[
        ["fld_zone", "zone_subty", "static_bfe", "source_id", "sfha_tf", "geometry"]
    ].copy()
    # Rename geometry column to match table schema
    gdf_final = gdf_final.rename_geometry("geom")

    # Clear existing data
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE floodplains"))
        conn.commit()
    logger.info("Cleared existing floodplain data")

    # Load to PostGIS
    logger.info("Loading floodplains to PostGIS...")
    gdf_final.to_postgis(
        "floodplains",
        engine,
        if_exists="append",
        index=False,
    )

    # Verify count
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM floodplains"))
        count = result.scalar()

    logger.info(f"[OK] Loaded {count} floodplains to database")
    return count


def get_county_bounds(engine) -> Optional[gpd.GeoDataFrame]:
    """
    Get county boundary from loaded parcels for clipping other layers.

    Args:
        engine: SQLAlchemy engine

    Returns:
        GeoDataFrame with county boundary polygon, or None
    """
    try:
        query = """
        SELECT ST_Union(geom) as geometry
        FROM parcels
        WHERE county = :county
        """
        gdf = gpd.read_postgis(
            text(query),
            engine,
            geom_col="geometry",
            params={"county": COUNTY_NAME},
        )
        if len(gdf) > 0 and gdf.geometry.iloc[0] is not None:
            # Buffer slightly to ensure we don't miss edge features
            gdf = gdf.to_crs(PROJECTED_CRS)
            gdf["geometry"] = gdf.geometry.buffer(100)  # 100 meter buffer
            gdf = gdf.to_crs(STORAGE_CRS)
            return gdf
    except Exception as e:
        logger.warning(f"Could not get county bounds: {e}")
    return None


def verify_spatial_indexes(engine) -> None:
    """Verify that spatial indexes exist and are being used."""
    with engine.connect() as conn:
        # Check for GIST indexes
        result = conn.execute(
            text(
                """
                SELECT tablename, indexname
                FROM pg_indexes
                WHERE indexdef LIKE '%gist%'
                ORDER BY tablename
                """
            )
        )
        indexes = result.fetchall()
        logger.info("Spatial indexes verified:")
        for table, index in indexes:
            logger.info(f"  {table}: {index}")


def print_summary(engine) -> None:
    """Print summary statistics for loaded data."""
    logger.info("\n" + "=" * 60)
    logger.info("DATA LOADING SUMMARY")
    logger.info("=" * 60)

    with engine.connect() as conn:
        # Parcel stats
        result = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) as count,
                    ROUND(SUM(calculated_acres)::numeric, 2) as total_acres,
                    ROUND(AVG(calculated_acres)::numeric, 2) as avg_acres
                FROM parcels
                """
            )
        )
        row = result.fetchone()
        logger.info(f"\nParcels:")
        logger.info(f"  Count: {row[0]}")
        logger.info(f"  Total acres: {row[1]}")
        logger.info(f"  Average parcel size: {row[2]} acres")

        # Wetland stats
        result = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) as count,
                    COUNT(DISTINCT wetland_type) as types
                FROM wetlands
                """
            )
        )
        row = result.fetchone()
        logger.info(f"\nWetlands:")
        logger.info(f"  Count: {row[0]}")
        logger.info(f"  Wetland types: {row[1]}")

        # Floodplain stats
        result = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) as count,
                    COUNT(DISTINCT fld_zone) as zones
                FROM floodplains
                """
            )
        )
        row = result.fetchone()
        logger.info(f"\nFloodplains:")
        logger.info(f"  Count: {row[0]}")
        logger.info(f"  Flood zones: {row[1]}")

        # Show flood zone breakdown
        result = conn.execute(
            text(
                """
                SELECT fld_zone, COUNT(*)
                FROM floodplains
                GROUP BY fld_zone
                ORDER BY COUNT(*) DESC
                """
            )
        )
        zones = result.fetchall()
        if zones:
            logger.info("  Zone breakdown:")
            for zone, count in zones:
                logger.info(f"    {zone}: {count}")

    logger.info("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Load land analysis data into PostGIS"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("./raw_data"),
        help="Directory containing raw shapefile data",
    )
    parser.add_argument(
        "--skip-parcels",
        action="store_true",
        help="Skip loading parcels (if already loaded)",
    )
    parser.add_argument(
        "--skip-wetlands",
        action="store_true",
        help="Skip loading wetlands",
    )
    parser.add_argument(
        "--skip-floodplains",
        action="store_true",
        help="Skip loading floodplains",
    )

    args = parser.parse_args()

    logger.info(f"Data directory: {args.data_dir.absolute()}")
    logger.info(f"County: {COUNTY_NAME} (FIPS: {COUNTY_FIPS})")
    logger.info(f"Storage CRS: {STORAGE_CRS}")
    logger.info(f"Projected CRS: {PROJECTED_CRS}")

    # Connect to database
    database_url = get_database_url()
    logger.info(f"Connecting to database...")
    engine = create_engine(database_url)

    # Ensure PostGIS is enabled
    ensure_postgis_extension(engine)

    # Load parcels first (needed for county bounds)
    parcel_count = 0
    if not args.skip_parcels:
        parcel_count = load_parcels(args.data_dir, engine)

    # Get county bounds for clipping other layers
    county_bounds = get_county_bounds(engine)
    if county_bounds is not None:
        logger.info("Using parcel extent for clipping constraint layers")
    else:
        logger.warning("No county bounds available, loading full constraint layers")

    # Load wetlands
    wetland_count = 0
    if not args.skip_wetlands:
        wetland_count = load_wetlands(args.data_dir, engine, county_bounds)

    # Load floodplains
    floodplain_count = 0
    if not args.skip_floodplains:
        floodplain_count = load_floodplains(args.data_dir, engine, county_bounds)

    # Verify indexes
    verify_spatial_indexes(engine)

    # Print summary
    print_summary(engine)

    logger.info("\n[OK] Data loading complete!")

    return 0 if (parcel_count > 0 or args.skip_parcels) else 1


if __name__ == "__main__":
    sys.exit(main())
