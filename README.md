# Buildable Land Analysis

A full-stack application that computes how much of a land parcel is actually buildable after removing regulatory and environmental constraints (wetlands, FEMA floodplains), with an interactive map for reviewing and manually adjusting the result.

**Live demo:** https://zeg-buildable-land.up.railway.app

---

## What this does, in plain terms

A parcel might be 35 acres on paper, but once you subtract wetland buffers, floodplain zones, and any manual adjustments, the real buildable area might be much smaller. This app:

1. Takes a parcel and computes buildable area = parcel − (buffered wetlands ∪ buffered floodplain)
2. Shows the result on an interactive map, color-coded
3. Lets a user draw shapes to manually exclude more land, or restore land back in
4. Recalculates live as buffer distances or manual shapes change

---

## Data used

| Layer | Source | Count | Notes |
|---|---|---|---|
| Parcels | Kendall County Appraisal District (ArcGIS Open Data) | 30,907 | 417,539 total acres — matches the county's real land area (~424,000 acres) within ~2% |
| Wetlands | USFWS National Wetlands Inventory | 3,843 | 5,140 acres |
| Floodplain | FEMA NFHL, via Kendall County's own portal | 120 | 100-year flood zones |

All three are real, publicly available datasets for Kendall County, Texas — not synthetic test data. See `WRITEUP.md` for the sourcing process, including two data-quality issues caught and fixed along the way (wrong-county data, and an acreage sanity check).

---

## Architecture

```
┌──────────────────────┐          ┌───────────────────────┐
│  React + MapLibre GL   │ ◄─────► │  FastAPI + PostGIS      │
│  (frontend)             │  REST   │  (backend)               │
└──────────────────────┘          └───────────────────────┘
```

- **Backend**: Python, FastAPI, PostGIS (via SQLAlchemy + GeoAlchemy2), Alembic migrations
- **Frontend**: React, Vite, TypeScript, MapLibre GL JS, mapbox-gl-draw
- **Database**: PostGIS 3.4, deployed as a Docker service on Railway
- **Deployment**: Railway (backend, frontend, and database as three separate services)

### Why this stack
- **PostGIS** for the actual geometry math (`ST_Buffer`, `ST_Union`, `ST_Difference`) — this is what PostGIS is built for, and it's far more reliable than hand-rolling geometric operations in application code.
- **MapLibre GL** instead of a paid mapping SDK — free, no API key, and performs well at the ~31k parcel scale we're rendering.
- **A projected, equal-area CRS for all measurements** (NAD83 Texas Centric Albers Equal Area, EPSG:6579), not the storage CRS (EPSG:4326/WGS84) and never Web Mercator. This matters: Web Mercator distorts area significantly and would produce wrong acreage numbers. All buffering and area calculations reproject into EPSG:6579 first; only the final GeoJSON sent to the frontend is in EPSG:4326.

---

## Setup — running it yourself

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (for local PostGIS) OR access to a PostGIS-enabled Postgres instance

### 1. Clone and set up the database

```bash
git clone https://github.com/Iterator-alt/Zeg.git
cd Zeg
docker compose up -d
```

This starts a local PostGIS instance. `docker-compose.yml` defines it — check there if you need to change the port or credentials.

**Why Docker for local dev:** PostGIS is a Postgres extension, not something available in default Postgres installs. Docker gives a consistent, disposable environment without installing PostGIS system-wide.

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp ../.env.example .env   # then fill in DATABASE_URL for your local Postgres
alembic upgrade head       # creates the schema
uvicorn app.main:app --reload
```

**What `alembic upgrade head` does:** applies our versioned database migrations — creates the `parcels`, `wetlands`, `floodplains`, and `manual_overrides` tables, each with a GIST spatial index on its geometry column. Without the GIST index, any bbox or intersection query against 30k+ parcels would be a full table scan — slow at this scale, and would only get worse with more data.

Backend runs at `http://localhost:8000`. Interactive API docs at `http://localhost:8000/docs`.

### 3. Load data

```bash
cd data-prep
pip install -r requirements.txt

# For quick local testing with small synthetic data:
python generate_test_data.py
python load_data.py

# For real Kendall County data (large files, not included in this repo):
# See "Real data" section below for sources, then:
python load_data.py --source real
```

### 4. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_URL=http://localhost:8000
npm run dev
```

Frontend runs at `http://localhost:5173`.

---

## Real data — sourcing it yourself

The real Kendall County datasets are too large to include in this repo (the wetlands geodatabase alone is ~2GB before clipping). To reproduce:

1. **Parcels**: Kendall County's ArcGIS Open Data portal — search for the parcels layer, export as GeoJSON.
2. **Wetlands**: USFWS Wetlands Mapper, state-level download for Texas (large file — clip to Kendall County's bounding box after downloading, don't try to load the whole state).
3. **Floodplain**: FEMA NFHL, either directly or via Kendall County's own portal, which also mirrors it.

**A note on data sourcing reliability:** during development, the federal USFWS and FEMA REST APIs were both unreliable — the USFWS endpoint returned 500 errors, and FEMA's connection was reset. The eventual working approach was downloading USFWS's pre-packaged state geodatabase directly rather than depending on the live query API, and using Kendall County's own ArcGIS portal (which mirrors FEMA data) instead of hitting FEMA's servers directly. See `WRITEUP.md` for more on this.

**Always verify a new data source's bounding box before loading it.** We initially loaded a parcel dataset that turned out to be from California, not Texas — caught only because the reported total acreage (945,483) was roughly 2x too large for Kendall County's actual ~424,000 acres. Print and check the bounding box of any new source before trusting it.

---

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/parcels?bbox=minx,miny,maxx,maxy` | GET | Parcels within the given map viewport — never returns the whole table |
| `/api/parcels/{id}` | GET | Full geometry + metadata for one parcel |
| `/api/parcels/{id}/constraints` | GET | Wetlands + floodplain polygons intersecting this parcel |
| `/api/parcels/{id}/buildable` | POST | Computes buildable area given buffer distances + manual exclude/restore shapes |

Full interactive docs at `/docs` once the backend is running.

---

## Testing

```bash
cd backend
pytest
```

39 tests covering: area calculations on known synthetic geometries, buffer operations, buildable-area logic (including overlapping constraints and constraints straddling the parcel boundary), manual exclude/restore geometry handling, coordinate transform round-trips, and API integration tests.

---

## Deployment

Deployed on Railway as three services: PostGIS database, FastAPI backend, React frontend. See `WRITEUP.md` for deployment notes, including a couple of PostGIS-on-Railway-specific gotchas (the default Postgres image doesn't include PostGIS; the data volume mount path needs to be a subdirectory, not the raw mount point).

---

## Known limitations

See `WRITEUP.md` for the full list, including performance behavior at scale and what we'd do differently with more time.
