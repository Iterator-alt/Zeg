"""
Application configuration with environment variable support.
Default buffer distances are configurable and overridable via API params.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5435/buildable_land"

    # CRS Configuration
    # Storage CRS - all geometries stored in WGS84
    storage_crs: int = 4326
    # Projected CRS for area/buffer calculations
    # NAD83 Texas Centric Albers Equal Area - appropriate for all of Texas
    # Units: meters
    projected_crs: int = 6579
    # Conversion factor: feet to meters (for buffer distances input in feet)
    feet_to_meters: float = 0.3048

    # Default Buffer Distances (in feet)
    # These are configurable defaults, overridable via API parameters

    # Wetland buffer default: 50 feet
    # TODO: Source needed - this is a placeholder value. Actual setback requirements
    # vary by jurisdiction and wetland type. Check local ordinances for the specific
    # county being analyzed. Common values range from 25-100 feet.
    default_wetland_buffer_ft: float = 50.0

    # Floodplain buffer default: 25 feet
    # TODO: Source needed - this is a placeholder value. FEMA does not mandate a
    # specific setback from flood zone boundaries; this is typically set by local
    # floodplain management ordinances. Check county/city regulations.
    default_floodplain_buffer_ft: float = 25.0

    # Buffer distance limits (for validation)
    min_buffer_ft: float = 0.0
    max_buffer_ft: float = 500.0

    # API Settings
    api_title: str = "Buildable Land Analysis API"
    api_version: str = "1.0.0"

    # Data Prep Settings
    # Selected county for analysis
    county_name: str = "Kendall"
    county_fips: str = "48259"  # Texas (48) + Kendall County (259)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
