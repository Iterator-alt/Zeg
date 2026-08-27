"""
Buildable Land Analysis API

FastAPI application for calculating buildable area on land parcels
after accounting for regulatory/environmental constraints.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Buildable Land Analysis API")
    logger.info(f"Storage CRS: EPSG:{settings.storage_crs}")
    logger.info(f"Projected CRS: EPSG:{settings.projected_crs}")
    logger.info(f"Default wetland buffer: {settings.default_wetland_buffer_ft} ft")
    logger.info(f"Default floodplain buffer: {settings.default_floodplain_buffer_ft} ft")
    yield
    logger.info("Shutting down Buildable Land Analysis API")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="""
## Buildable Land Analysis API

Calculate buildable area on land parcels after removing regulatory and
environmental constraints (wetlands, FEMA floodplain).

### Key Features:
- View parcels within a map viewport (bbox-filtered)
- Get constraint layers (wetlands, floodplains) for any parcel
- Calculate buildable area with configurable buffer distances
- Support for manual exclude/restore polygons
- Real-time breakdown of constrained areas by type

### Important Notes:
- All area calculations use EPSG:6579 (NAD83 Texas Centric Albers Equal Area)
- Buffer distances are specified in feet
- Breakdown entries may overlap (e.g., wetland overlapping floodplain),
  so individual constraint acres may not sum to total constrained area
""",
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api", tags=["parcels"])


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": settings.api_version}


@app.get("/")
def root():
    """Root endpoint with API info."""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health",
    }
