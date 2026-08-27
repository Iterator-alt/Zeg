"""
Integration tests for API endpoints.

These tests verify the API endpoints work correctly with the database.
They require a running PostGIS database with test data loaded.
"""

import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoints:
    """Test health and info endpoints."""

    def test_health_check(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data


class TestParcelsEndpoints:
    """Test parcel-related endpoints."""

    def test_list_parcels_requires_bbox(self, client):
        """Test that list parcels requires bbox parameter."""
        response = client.get("/api/parcels")
        assert response.status_code == 400
        assert "bbox" in response.json()["detail"].lower()

    def test_list_parcels_invalid_bbox_format(self, client):
        """Test invalid bbox format returns 400."""
        response = client.get("/api/parcels?bbox=invalid")
        assert response.status_code == 400

    def test_list_parcels_invalid_bbox_values(self, client):
        """Test bbox with min > max returns 400."""
        response = client.get("/api/parcels?bbox=-98.0,30.0,-99.0,29.0")
        assert response.status_code == 400

    def test_list_parcels_valid_bbox(self, client):
        """Test list parcels with valid bbox returns parcels."""
        # Use a bbox that covers our test data area
        response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # If we have test data, verify structure
        if len(data) > 0:
            parcel = data[0]
            assert "id" in parcel
            assert "centroid_lon" in parcel
            assert "centroid_lat" in parcel

    def test_get_parcel_not_found(self, client):
        """Test getting non-existent parcel returns 404."""
        response = client.get("/api/parcels/99999")
        assert response.status_code == 404

    def test_get_parcel_valid(self, client):
        """Test getting existing parcel returns full details."""
        # First get list to find a valid ID
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            response = client.get(f"/api/parcels/{parcel_id}")
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "geometry" in data
            assert data["geometry"]["type"] in ["Polygon", "MultiPolygon"]


class TestConstraintsEndpoints:
    """Test constraint-related endpoints."""

    def test_get_constraints_not_found(self, client):
        """Test getting constraints for non-existent parcel returns 404."""
        response = client.get("/api/parcels/99999/constraints")
        assert response.status_code == 404

    def test_get_constraints_valid(self, client):
        """Test getting constraints for existing parcel."""
        # First get list to find a valid ID
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            response = client.get(f"/api/parcels/{parcel_id}/constraints")
            assert response.status_code == 200
            data = response.json()
            assert "wetlands" in data
            assert "floodplains" in data
            assert isinstance(data["wetlands"], list)
            assert isinstance(data["floodplains"], list)


class TestBuildableEndpoint:
    """Test buildable area calculation endpoint."""

    def test_buildable_not_found(self, client):
        """Test buildable for non-existent parcel returns 404."""
        response = client.post(
            "/api/parcels/99999/buildable",
            json={"wetland_buffer_ft": 50, "floodplain_buffer_ft": 25},
        )
        assert response.status_code == 404

    def test_buildable_default_params(self, client):
        """Test buildable with default parameters."""
        # First get list to find a valid ID
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            response = client.post(
                f"/api/parcels/{parcel_id}/buildable",
                json={},
            )
            assert response.status_code == 200
            data = response.json()
            assert "buildable_acres" in data
            assert "parcel_acres" in data
            assert "breakdown" in data
            assert "warnings" in data

    def test_buildable_custom_buffers(self, client):
        """Test buildable with custom buffer distances."""
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            response = client.post(
                f"/api/parcels/{parcel_id}/buildable",
                json={
                    "wetland_buffer_ft": 100,
                    "floodplain_buffer_ft": 50,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "buildable_acres" in data

    def test_buildable_invalid_buffer(self, client):
        """Test buildable with invalid buffer distance returns 422."""
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            response = client.post(
                f"/api/parcels/{parcel_id}/buildable",
                json={
                    "wetland_buffer_ft": -10,  # Invalid negative
                },
            )
            assert response.status_code == 422

    def test_buildable_with_manual_exclude(self, client):
        """Test buildable with manual exclusion."""
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            # Get parcel geometry to create exclude within it
            parcel_response = client.get(f"/api/parcels/{parcel_id}")
            if parcel_response.status_code == 200:
                parcel_geom = parcel_response.json()["geometry"]

                # Create a small exclude polygon
                exclude_geom = {
                    "type": "Polygon",
                    "coordinates": [[
                        [-98.705, 29.895],
                        [-98.695, 29.895],
                        [-98.695, 29.905],
                        [-98.705, 29.905],
                        [-98.705, 29.895],
                    ]]
                }

                response = client.post(
                    f"/api/parcels/{parcel_id}/buildable",
                    json={
                        "wetland_buffer_ft": 50,
                        "floodplain_buffer_ft": 25,
                        "manual_excludes": [exclude_geom],
                    },
                )
                assert response.status_code == 200

    def test_buildable_invalid_geojson_exclude(self, client):
        """Test buildable with invalid GeoJSON exclude returns 422."""
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            response = client.post(
                f"/api/parcels/{parcel_id}/buildable",
                json={
                    "manual_excludes": [{"invalid": "geometry"}],
                },
            )
            assert response.status_code == 422


class TestResponseFormats:
    """Test response data formats."""

    def test_buildable_response_structure(self, client):
        """Verify buildable response has all required fields."""
        list_response = client.get("/api/parcels?bbox=-99.0,29.0,-98.0,30.5")
        if list_response.status_code == 200 and len(list_response.json()) > 0:
            parcel_id = list_response.json()[0]["id"]

            response = client.post(
                f"/api/parcels/{parcel_id}/buildable",
                json={},
            )
            assert response.status_code == 200
            data = response.json()

            # Required fields
            assert "buildable_acres" in data
            assert "parcel_acres" in data
            assert "constrained_acres" in data
            assert "breakdown" in data
            assert "warnings" in data

            # Types
            assert isinstance(data["buildable_acres"], (int, float))
            assert isinstance(data["parcel_acres"], (int, float))
            assert isinstance(data["breakdown"], list)
            assert isinstance(data["warnings"], list)

            # Breakdown items structure
            for item in data["breakdown"]:
                assert "reason" in item
                assert "acres" in item
                assert "type" in item
                assert item["type"] in ["removed", "added"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
