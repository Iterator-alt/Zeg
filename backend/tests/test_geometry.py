"""
Unit tests for geometry calculation logic.

These tests use synthetic geometries with known dimensions to verify
the correctness of area calculations, buffering, and buildable area logic.

All tests use EPSG:6579 (NAD83 Texas Centric Albers Equal Area) for
calculations, which uses meters as the unit. We verify that:
1. Area calculations are accurate
2. Buffer distances in feet are correctly converted to meters
3. Geometry operations (difference, union, intersection) work correctly
4. Manual excludes/restores are properly handled
"""

import pytest
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union
import math

# Add parent to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.geometry import (
    calculate_buildable_area,
    transform_to_projected,
    transform_to_wgs84,
    calculate_area_acres,
    buffer_geometry,
    validate_geometry,
    shapely_to_geojson,
    geojson_to_shapely,
    FEET_TO_METERS,
    SQ_METERS_TO_ACRES,
)


# Test constants
# For test simplicity, we create geometries in projected CRS and transform to WGS84
# Center point in Texas for realistic coordinates
TEST_CENTER_LON = -98.7
TEST_CENTER_LAT = 29.9

# 1 acre = 4046.86 sq meters
ACRE_SQ_METERS = 4046.86

# Tolerance for floating point comparisons (0.1% for area calculations)
AREA_TOLERANCE_PERCENT = 0.1


def create_square_parcel_wgs84(center_lon: float, center_lat: float, acres: float) -> Polygon:
    """
    Create a square parcel in WGS84 with approximately the specified acreage.

    We create it in projected CRS for accurate sizing, then transform to WGS84.
    """
    from pyproj import Transformer

    transformer_to_proj = Transformer.from_crs("EPSG:4326", "EPSG:6579", always_xy=True)
    transformer_to_wgs = Transformer.from_crs("EPSG:6579", "EPSG:4326", always_xy=True)

    # Calculate side length in meters for desired acreage
    area_sq_meters = acres * ACRE_SQ_METERS
    side_length = math.sqrt(area_sq_meters)

    # Transform center to projected CRS
    cx, cy = transformer_to_proj.transform(center_lon, center_lat)

    # Create square in projected CRS
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


def create_offset_square_wgs84(
    center_lon: float, center_lat: float, acres: float, offset_x_meters: float = 0, offset_y_meters: float = 0
) -> Polygon:
    """Create a square with offset from center."""
    from pyproj import Transformer

    transformer_to_proj = Transformer.from_crs("EPSG:4326", "EPSG:6579", always_xy=True)
    transformer_to_wgs = Transformer.from_crs("EPSG:6579", "EPSG:4326", always_xy=True)

    area_sq_meters = acres * ACRE_SQ_METERS
    side_length = math.sqrt(area_sq_meters)

    cx, cy = transformer_to_proj.transform(center_lon, center_lat)
    cx += offset_x_meters
    cy += offset_y_meters

    half_side = side_length / 2
    coords_proj = [
        (cx - half_side, cy - half_side),
        (cx + half_side, cy - half_side),
        (cx + half_side, cy + half_side),
        (cx - half_side, cy + half_side),
        (cx - half_side, cy - half_side),
    ]

    coords_wgs = [transformer_to_wgs.transform(x, y) for x, y in coords_proj]
    return Polygon(coords_wgs)


class TestAreaCalculations:
    """Test area calculation accuracy."""

    def test_10_acre_parcel(self):
        """Test that a 10-acre parcel calculates to 10 acres."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        parcel_proj = transform_to_projected(parcel)
        area_acres = calculate_area_acres(parcel_proj)

        assert abs(area_acres - 10.0) / 10.0 * 100 < AREA_TOLERANCE_PERCENT, \
            f"Expected ~10 acres, got {area_acres}"

    def test_1_acre_parcel(self):
        """Test that a 1-acre parcel calculates to 1 acre."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 1.0)
        parcel_proj = transform_to_projected(parcel)
        area_acres = calculate_area_acres(parcel_proj)

        assert abs(area_acres - 1.0) / 1.0 * 100 < AREA_TOLERANCE_PERCENT, \
            f"Expected ~1 acre, got {area_acres}"

    def test_100_acre_parcel(self):
        """Test that a 100-acre parcel calculates to 100 acres."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 100.0)
        parcel_proj = transform_to_projected(parcel)
        area_acres = calculate_area_acres(parcel_proj)

        assert abs(area_acres - 100.0) / 100.0 * 100 < AREA_TOLERANCE_PERCENT, \
            f"Expected ~100 acres, got {area_acres}"


class TestBufferOperations:
    """Test buffer distance calculations."""

    def test_buffer_50_feet(self):
        """Test that a 50-foot buffer expands geometry correctly."""
        # Create a 1-acre square (~63.6m side)
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 1.0)
        parcel_proj = transform_to_projected(parcel)

        original_area = parcel_proj.area

        # Buffer by 50 feet = 15.24 meters
        buffered = buffer_geometry(parcel_proj, 50.0)
        buffered_area = buffered.area

        # The buffered area should be larger
        assert buffered_area > original_area

        # Calculate expected increase
        # For a square, buffer adds area = 4 * side * buffer_dist + pi * buffer_dist^2
        side = math.sqrt(original_area)
        buffer_dist_m = 50.0 * FEET_TO_METERS
        expected_increase = 4 * side * buffer_dist_m + math.pi * buffer_dist_m ** 2

        actual_increase = buffered_area - original_area

        # Allow 5% tolerance for buffer calculation
        assert abs(actual_increase - expected_increase) / expected_increase * 100 < 5, \
            f"Buffer increase {actual_increase} differs from expected {expected_increase}"

    def test_zero_buffer(self):
        """Test that zero buffer returns same geometry."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 5.0)
        parcel_proj = transform_to_projected(parcel)

        buffered = buffer_geometry(parcel_proj, 0.0)

        assert buffered.equals(parcel_proj), "Zero buffer should return identical geometry"


class TestBuildableAreaCalculation:
    """Test the main buildable area calculation logic."""

    def test_parcel_no_constraints(self):
        """Test parcel with no constraints - buildable should equal parcel."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[],
            floodplain_geoms=[],
            wetland_buffer_ft=50.0,
            floodplain_buffer_ft=25.0,
        )

        assert abs(result.buildable_acres - 10.0) / 10.0 * 100 < AREA_TOLERANCE_PERCENT
        assert abs(result.parcel_acres - 10.0) / 10.0 * 100 < AREA_TOLERANCE_PERCENT
        assert result.constrained_acres < 0.01  # Essentially zero
        assert len(result.breakdown) == 0
        assert len(result.warnings) == 0

    def test_parcel_with_centered_wetland(self):
        """Test 10-acre parcel with 2-acre wetland in center (no buffer)."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        wetland = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 2.0)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,  # No buffer for precise test
            floodplain_buffer_ft=0.0,
        )

        # Buildable should be ~8 acres (10 - 2)
        assert abs(result.buildable_acres - 8.0) / 8.0 * 100 < AREA_TOLERANCE_PERCENT, \
            f"Expected ~8 acres buildable, got {result.buildable_acres}"

        # Parcel should still be 10 acres
        assert abs(result.parcel_acres - 10.0) / 10.0 * 100 < AREA_TOLERANCE_PERCENT

        # Constrained should be ~2 acres
        assert abs(result.constrained_acres - 2.0) / 2.0 * 100 < AREA_TOLERANCE_PERCENT

        # Should have wetland in breakdown
        assert len(result.breakdown) == 1
        assert "Wetland" in result.breakdown[0].reason
        assert result.breakdown[0].constraint_type == "removed"

    def test_parcel_with_wetland_buffer(self):
        """Test that wetland buffer correctly increases constrained area."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        # Small wetland in center
        wetland = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 0.5)

        # Without buffer
        result_no_buffer = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
        )

        # With 50ft buffer
        result_with_buffer = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=50.0,
            floodplain_buffer_ft=0.0,
        )

        # Buffered constraint should be larger
        assert result_with_buffer.constrained_acres > result_no_buffer.constrained_acres, \
            "Buffered wetland should constrain more area"

        # Buildable should be smaller with buffer
        assert result_with_buffer.buildable_acres < result_no_buffer.buildable_acres

    def test_parcel_with_floodplain(self):
        """Test parcel with floodplain constraint."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        # Floodplain covering half the parcel
        floodplain = create_offset_square_wgs84(
            TEST_CENTER_LON, TEST_CENTER_LAT, 5.0, offset_x_meters=50
        )

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[],
            floodplain_geoms=[floodplain],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
        )

        # Should have some floodplain intersection
        assert result.constrained_acres > 0
        assert len(result.breakdown) == 1
        assert "Floodplain" in result.breakdown[0].reason

    def test_overlapping_constraints(self):
        """
        Test parcel with overlapping wetland and floodplain.

        The breakdown should show both constraints, and they may overlap,
        so individual constraint acres may exceed total constrained area.
        """
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        # Both constraints in same location (overlapping)
        wetland = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 2.0)
        floodplain = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 2.0)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[floodplain],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
        )

        # Both constraints should appear in breakdown
        assert len(result.breakdown) == 2

        # Total constrained should be ~2 acres (they overlap completely)
        assert abs(result.constrained_acres - 2.0) / 2.0 * 100 < AREA_TOLERANCE_PERCENT

        # But breakdown sum would be 4 acres (2 + 2) - this is expected overlap behavior
        breakdown_sum = sum(b.acres for b in result.breakdown)
        assert breakdown_sum > result.constrained_acres, \
            "Overlapping constraints should sum to more than actual constrained area"

    def test_wetland_outside_parcel(self):
        """Test that wetland outside parcel doesn't affect buildable area."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        # Wetland far from parcel
        wetland = create_offset_square_wgs84(
            TEST_CENTER_LON, TEST_CENTER_LAT, 2.0, offset_x_meters=1000
        )

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=50.0,
            floodplain_buffer_ft=0.0,
        )

        # Buildable should equal parcel (no intersection)
        assert abs(result.buildable_acres - result.parcel_acres) < 0.01

    def test_manual_exclude(self):
        """Test manual exclusion reduces buildable area."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        exclude = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 1.0)
        exclude_geojson = shapely_to_geojson(exclude)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
            manual_excludes=[exclude_geojson],
        )

        # Buildable should be ~9 acres
        assert abs(result.buildable_acres - 9.0) / 9.0 * 100 < AREA_TOLERANCE_PERCENT

        # Should have exclusion in breakdown
        assert any("exclusion" in b.reason.lower() for b in result.breakdown)

    def test_manual_restore(self):
        """Test manual restoration adds back area."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        wetland = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 3.0)
        # Restore part of the wetland area
        restore = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 1.0)
        restore_geojson = shapely_to_geojson(restore)

        # Without restore
        result_no_restore = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
        )

        # With restore
        result_with_restore = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
            manual_restores=[restore_geojson],
        )

        # Restore should increase buildable area
        assert result_with_restore.buildable_acres > result_no_restore.buildable_acres

        # Should have restoration in breakdown
        assert any("restoration" in b.reason.lower() for b in result_with_restore.breakdown)
        restore_item = next(b for b in result_with_restore.breakdown if "restoration" in b.reason.lower())
        assert restore_item.constraint_type == "added"

    def test_restore_outside_parcel_ignored(self):
        """Test that restore area outside parcel is clipped to parcel boundary."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        wetland = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 2.0)
        # Restore polygon mostly outside parcel
        restore = create_offset_square_wgs84(
            TEST_CENTER_LON, TEST_CENTER_LAT, 5.0, offset_x_meters=500
        )
        restore_geojson = shapely_to_geojson(restore)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
            manual_restores=[restore_geojson],
        )

        # Buildable should not exceed parcel area
        assert result.buildable_acres <= result.parcel_acres + 0.01

    def test_exclude_fully_outside_parcel(self):
        """Test that exclude polygon fully outside parcel doesn't affect buildable."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        # Exclude polygon completely outside parcel
        exclude = create_offset_square_wgs84(
            TEST_CENTER_LON, TEST_CENTER_LAT, 2.0, offset_x_meters=1000
        )
        exclude_geojson = shapely_to_geojson(exclude)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
            manual_excludes=[exclude_geojson],
        )

        # Buildable should equal parcel (no intersection, no effect)
        assert abs(result.buildable_acres - result.parcel_acres) < 0.01
        # No exclusion in breakdown (nothing was actually excluded)
        assert not any("exclusion" in b.reason.lower() for b in result.breakdown)
        # No errors or warnings about the outside polygon
        assert len(result.warnings) == 0

    def test_exclude_partially_outside_parcel(self):
        """Test that exclude polygon partially outside parcel is clipped gracefully."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        # Exclude polygon straddling parcel edge (half inside, half outside)
        # Parcel is ~201m on a side, so offset by ~100m puts it half outside
        exclude = create_offset_square_wgs84(
            TEST_CENTER_LON, TEST_CENTER_LAT, 2.0, offset_x_meters=100
        )
        exclude_geojson = shapely_to_geojson(exclude)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
            manual_excludes=[exclude_geojson],
        )

        # Should have some exclusion but less than the full 2 acres
        exclusion_items = [b for b in result.breakdown if "exclusion" in b.reason.lower()]
        assert len(exclusion_items) == 1
        assert exclusion_items[0].acres < 2.0  # Less than full exclude polygon
        assert exclusion_items[0].acres > 0.5  # But still some overlap
        # Buildable should be less than parcel
        assert result.buildable_acres < result.parcel_acres
        # No errors
        assert len(result.warnings) == 0

    def test_restore_fully_outside_parcel(self):
        """Test that restore polygon fully outside parcel doesn't affect buildable."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        wetland = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 2.0)
        # Restore polygon completely outside parcel
        restore = create_offset_square_wgs84(
            TEST_CENTER_LON, TEST_CENTER_LAT, 3.0, offset_x_meters=1000
        )
        restore_geojson = shapely_to_geojson(restore)

        result = calculate_buildable_area(
            parcel_geom=parcel,
            wetland_geoms=[wetland],
            floodplain_geoms=[],
            wetland_buffer_ft=0.0,
            floodplain_buffer_ft=0.0,
            manual_restores=[restore_geojson],
        )

        # Buildable should be ~8 acres (10 - 2 wetland), restore had no effect
        assert abs(result.buildable_acres - 8.0) / 8.0 * 100 < AREA_TOLERANCE_PERCENT
        # No restoration in breakdown (nothing was actually restored within parcel)
        assert not any("restoration" in b.reason.lower() for b in result.breakdown)
        # No errors
        assert len(result.warnings) == 0


class TestGeometryValidation:
    """Test geometry validation and repair."""

    def test_valid_geometry_unchanged(self):
        """Test that valid geometry is returned unchanged."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)
        validated, warnings = validate_geometry(parcel, "test")

        assert validated is not None
        assert validated.equals(parcel)
        assert len(warnings) == 0

    def test_empty_geometry_returns_none(self):
        """Test that empty geometry returns None with warning."""
        from shapely.geometry import Polygon

        empty = Polygon()
        validated, warnings = validate_geometry(empty, "test")

        assert validated is None
        assert len(warnings) > 0
        assert "empty" in warnings[0].lower()

    def test_none_geometry_returns_none(self):
        """Test that None geometry returns None with warning."""
        validated, warnings = validate_geometry(None, "test")

        assert validated is None
        assert len(warnings) > 0


class TestCoordinateTransforms:
    """Test coordinate transformations."""

    def test_round_trip_transform(self):
        """Test that transform to projected and back preserves geometry."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 10.0)

        # Transform to projected
        projected = transform_to_projected(parcel)

        # Transform back to WGS84
        restored = transform_to_wgs84(projected)

        # Should be very close to original
        assert parcel.equals_exact(restored, tolerance=1e-6), \
            "Round-trip transform should preserve geometry"

    def test_projected_uses_meters(self):
        """Verify that projected CRS uses meters for measurements."""
        # Create a 1-acre square
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 1.0)
        projected = transform_to_projected(parcel)

        # 1 acre = 4046.86 sq meters
        # So area should be close to 4046.86
        assert abs(projected.area - ACRE_SQ_METERS) / ACRE_SQ_METERS * 100 < AREA_TOLERANCE_PERCENT


class TestGeoJSONConversion:
    """Test GeoJSON conversion utilities."""

    def test_polygon_to_geojson(self):
        """Test converting Polygon to GeoJSON."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 1.0)
        geojson = shapely_to_geojson(parcel)

        assert geojson is not None
        assert geojson["type"] == "Polygon"
        assert "coordinates" in geojson

    def test_geojson_to_polygon(self):
        """Test converting GeoJSON to Polygon."""
        geojson = {
            "type": "Polygon",
            "coordinates": [[
                [-98.7, 29.9],
                [-98.6, 29.9],
                [-98.6, 30.0],
                [-98.7, 30.0],
                [-98.7, 29.9],
            ]]
        }
        polygon = geojson_to_shapely(geojson)

        assert polygon is not None
        assert polygon.geom_type == "Polygon"
        assert polygon.is_valid

    def test_round_trip_geojson(self):
        """Test that GeoJSON conversion round-trip preserves geometry."""
        parcel = create_square_parcel_wgs84(TEST_CENTER_LON, TEST_CENTER_LAT, 5.0)

        geojson = shapely_to_geojson(parcel)
        restored = geojson_to_shapely(geojson)

        assert parcel.equals_exact(restored, tolerance=1e-10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
