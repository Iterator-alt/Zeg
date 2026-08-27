# Buildable Land Analysis

A full-stack web application for calculating buildable area on land parcels after accounting for regulatory and environmental constraints (wetlands, FEMA floodplain).

## Features

- **Interactive Map**: View parcels on a MapLibre GL JS map with OpenStreetMap tiles
- **Constraint Visualization**: See wetlands (blue) and floodplains (yellow) overlaid on parcels
- **Configurable Buffers**: Adjust buffer distances for wetlands and floodplains (0-200 ft)
- **Buildable Area Calculation**: Real-time computation of buildable area using PostGIS
- **Manual Adjustments**: Draw polygons to manually exclude or restore areas
- **Area Breakdown**: Detailed breakdown of constrained areas by type

## Architecture

```
├── backend/           # FastAPI + PostGIS backend
│   ├── app/
│   │   ├── api/       # API routes and schemas
│   │   ├── core/      # Configuration and geometry calculations
│   │   └── models/    # SQLAlchemy/GeoAlchemy2 models
│   ├── alembic/       # Database migrations
│   └── tests/         # Pytest test suite
├── frontend/          # React + Vite + TypeScript frontend
│   └── src/
│       ├── api/       # API client
│       ├── components/# React components (Map, Sidebar)
│       └── hooks/     # Custom hooks (debounce, calculation)
├── data-prep/         # Data loading scripts
└── docker-compose.yml # PostGIS database
```

## Tech Stack

### Backend
- **Python 3.11+**
- **FastAPI** - Modern async API framework
- **PostGIS** - Spatial database (PostgreSQL + PostGIS)
- **SQLAlchemy + GeoAlchemy2** - ORM with spatial support
- **Shapely** - Geometry operations
- **pyproj** - Coordinate transformations
- **Pydantic v2** - Data validation

### Frontend
- **React 18** - UI framework
- **Vite 5** - Build tool
- **TypeScript** - Type safety
- **MapLibre GL JS** - Interactive maps
- **@mapbox/mapbox-gl-draw** - Drawing tools

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker and Docker Compose

## Setup

### 1. Start the Database

```bash
docker-compose up -d
```

This starts a PostGIS database on port 5435.

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Load test data
cd ../data-prep
python generate_test_data.py
python load_data.py

# Start the API server
cd ../backend
uvicorn app.main:app --reload --port 8000
```

The API will be available at http://localhost:8000

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at http://localhost:5173

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/parcels` | GET | List parcels in bbox |
| `/api/parcels/{id}` | GET | Get parcel details |
| `/api/parcels/{id}/constraints` | GET | Get parcel constraints |
| `/api/parcels/{id}/buildable` | POST | Calculate buildable area |

### Example: Calculate Buildable Area

```bash
curl -X POST "http://localhost:8000/api/parcels/2/buildable" \
  -H "Content-Type: application/json" \
  -d '{
    "wetland_buffer_ft": 50,
    "floodplain_buffer_ft": 25,
    "manual_excludes": [],
    "manual_restores": []
  }'
```

Response:
```json
{
  "buildable_acres": 6.46,
  "parcel_acres": 10.0,
  "constrained_acres": 3.54,
  "buildable_geom": { "type": "MultiPolygon", "coordinates": [...] },
  "breakdown": [
    { "reason": "Wetlands (with 50.0ft buffer)", "acres": 3.54, "type": "removed" }
  ],
  "breakdown_note": "Breakdown entries may overlap...",
  "warnings": []
}
```

## Coordinate Reference Systems

- **Storage**: EPSG:4326 (WGS 84 - GPS coordinates)
- **Calculations**: EPSG:6579 (NAD83 Texas Centric Albers Equal Area)
- **Buffer Input**: Feet (converted to meters internally)

All area and buffer calculations use EPSG:6579 for accurate results in Texas.

## Testing

### Backend Tests

```bash
cd backend
pytest -v
```

The test suite includes 42 tests covering:
- Geometry calculations (25 tests)
- API endpoints (17 tests)

### Test Data

The application includes synthetic test data for Kendall County, TX:
- 5 parcels (2, 10, 10, 15, 20 acres)
- 2 wetland areas
- 3 floodplain zones

## Configuration

### Environment Variables

Create a `.env` file in the backend directory:

```env
DATABASE_URL=postgresql://buildable:buildable@localhost:5435/buildable_land

# Buffer defaults (feet)
DEFAULT_WETLAND_BUFFER_FT=50
DEFAULT_FLOODPLAIN_BUFFER_FT=25

# CRS settings
STORAGE_CRS=4326
PROJECTED_CRS=6579
```

## License

MIT
