#!/usr/bin/env python3
"""
Data Download Script for Buildable Land Analysis

This script provides instructions and helper functions for downloading
the required geospatial data for Kendall County, Texas.

Data Sources:
1. Parcels: TNRIS Stratmap Parcels
   - URL: https://data.tnris.org/
   - Search for "Kendall County Parcels"

2. Wetlands: USFWS National Wetlands Inventory
   - URL: https://fws.gov/program/national-wetlands-inventory/wetlands-data
   - Download: Texas wetlands, clip to county

3. Floodplains: FEMA National Flood Hazard Layer
   - URL: https://msc.fema.gov/portal/advanceSearch
   - Search by county: Kendall, TX

Note: Due to licensing and data access requirements, this script provides
guidance rather than automated downloads. Some data sources require
registration or acceptance of terms of use.
"""

import os
import sys
import logging
from pathlib import Path
import requests
import zipfile
import io

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_data_directories(base_dir: Path) -> None:
    """Create the expected data directory structure."""
    dirs = ["parcels", "wetlands", "floodplains"]
    for d in dirs:
        dir_path = base_dir / d
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {dir_path}")


def print_download_instructions():
    """Print manual download instructions for each data source."""

    instructions = """
================================================================================
DATA DOWNLOAD INSTRUCTIONS FOR KENDALL COUNTY, TEXAS
================================================================================

Please download the following datasets and place them in the raw_data directory.

1. PARCELS (required)
   ─────────────────────────────────────────────────────────────────────────────
   Source: TNRIS (Texas Natural Resources Information System)
   URL: https://data.tnris.org/

   Steps:
   a) Go to https://data.tnris.org/
   b) Search for "StratMap Parcels" or navigate to Parcels dataset
   c) Filter by County: Kendall
   d) Download the shapefile format
   e) Extract to: raw_data/parcels/

   Expected files:
   - raw_data/parcels/*.shp (and accompanying .dbf, .shx, .prj files)


2. WETLANDS (required)
   ─────────────────────────────────────────────────────────────────────────────
   Source: USFWS National Wetlands Inventory (NWI)
   URL: https://fws.gov/program/national-wetlands-inventory/wetlands-data

   Steps:
   a) Go to https://www.fws.gov/program/national-wetlands-inventory/wetlands-data
   b) Click "Wetlands Data Download" or use the Wetlands Mapper
   c) Navigate to Texas and download the wetlands data
   d) For targeted download, use the Wetlands Mapper:
      - https://fwsprimary.wim.usgs.gov/wetlands/apps/wetlands-mapper/
      - Zoom to Kendall County, TX
      - Use the download tool to select the county area
   e) Extract to: raw_data/wetlands/

   Alternative - Direct HUC download:
   - Kendall County is primarily in HUC8: 12100201 (Upper Guadalupe)
   - Direct link pattern: Search for TX_Wetlands on the FWS download page

   Expected files:
   - raw_data/wetlands/*.shp (and accompanying files)


3. FLOODPLAINS (required)
   ─────────────────────────────────────────────────────────────────────────────
   Source: FEMA National Flood Hazard Layer (NFHL)
   URL: https://msc.fema.gov/portal/advanceSearch

   Steps:
   a) Go to https://msc.fema.gov/portal/advanceSearch
   b) Search Type: "Products by County"
   c) State: Texas
   d) County: Kendall
   e) Product Types: Select "NFHL Data - County"
   f) Download the NFHL data (may be a geodatabase or shapefile)
   g) Extract to: raw_data/floodplains/

   Important: We only need the S_FLD_HAZ_AR layer (Flood Hazard Areas)
   If downloading a geodatabase, the load script will find the correct layer.

   Expected files:
   - raw_data/floodplains/*.shp OR
   - raw_data/floodplains/*.gdb (geodatabase folder)


================================================================================
DIRECTORY STRUCTURE AFTER DOWNLOAD
================================================================================

raw_data/
├── parcels/
│   ├── kendall_parcels.shp
│   ├── kendall_parcels.dbf
│   ├── kendall_parcels.shx
│   └── kendall_parcels.prj
├── wetlands/
│   ├── TX_Wetlands.shp (or similar)
│   ├── TX_Wetlands.dbf
│   ├── TX_Wetlands.shx
│   └── TX_Wetlands.prj
└── floodplains/
    ├── S_FLD_HAZ_AR.shp (or similar)
    └── ... OR ...
    └── NFHL_48259.gdb/

================================================================================
AFTER DOWNLOADING
================================================================================

Run the data loading script:

    cd data-prep
    python load_data.py --data-dir ../raw_data

Or from the project root:

    python data-prep/load_data.py --data-dir raw_data

================================================================================
"""
    print(instructions)


def main():
    """Main entry point."""
    # Create data directory structure
    base_dir = Path("./raw_data")
    create_data_directories(base_dir)

    # Print download instructions
    print_download_instructions()

    # Check what's already present
    logger.info("\nChecking existing data...")

    for subdir in ["parcels", "wetlands", "floodplains"]:
        dir_path = base_dir / subdir
        shapefiles = list(dir_path.glob("*.shp"))
        geodbs = list(dir_path.glob("*.gdb"))

        if shapefiles or geodbs:
            logger.info(f"  ✓ {subdir}/: {len(shapefiles)} shapefiles, {len(geodbs)} geodatabases found")
        else:
            logger.warning(f"  ✗ {subdir}/: No data found - please download")


if __name__ == "__main__":
    main()
