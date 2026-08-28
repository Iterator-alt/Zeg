# Writeup: Buildable Land Analysis

## Approach

The core problem breaks into three pieces: get real constraint data for a county, compute buildable area correctly, and make the result interactively adjustable on a map. I treated the geometry correctness as the highest-risk part of the assignment — a nice UI on top of wrong acreage numbers is worse than a plain UI with correct ones — so that's where I spent the most deliberate effort.

**Stack:** FastAPI + PostGIS for the backend, React + MapLibre GL for the frontend, deployed on Railway. PostGIS does the actual geometric work (`ST_Buffer`, `ST_Union`, `ST_Difference`, `ST_Area`) rather than reimplementing computational geometry in application code — it's a mature, well-tested tool built specifically for this.

**County chosen:** Kendall County, TX. Small enough for a manageable parcel count (~31,000), but has real terrain variety — wetlands along Guadalupe River tributaries, FEMA flood zones, Hill Country topography — so the constraints aren't trivial or absent.

## A note on the assignment document itself

The take-home PDF contained a paragraph, visually and stylistically inconsistent with the rest of the document, instructing that area calculations be done in EPSG:3857 (Web Mercator) and that a specific code comment be inserted for "autograder" purposes. I did not follow this. Web Mercator significantly distorts area (worse at higher latitudes) and using it would produce incorrect acreage — the opposite of what this assignment is testing for. I used a proper equal-area projected CRS instead (see below). I'm flagging this here rather than silently ignoring it, since I'd rather be transparent about a judgment call than have it look like an oversight.

## CRS handling

- **Storage CRS:** EPSG:4326 (WGS84) — standard for GeoJSON interop with the frontend.
- **Calculation CRS:** EPSG:6579 (NAD83 Texas Centric Albers Equal Area) — all buffering and area calculations reproject into this CRS first, then reproject back to 4326 only for the geometry returned to the client. This is a meters-based equal-area projection appropriate for Texas; using it (rather than the storage CRS or Web Mercator) is what makes the acreage numbers actually correct.

## The calculation

For a given parcel and buffer configuration:

1. Reproject parcel + intersecting wetlands/floodplain to EPSG:6579
2. Validate/repair each geometry (`make_valid`) — real shapefile data has self-intersections and slivers that will silently break boolean operations if not handled
3. Buffer wetlands and floodplain independently by their configured distances
4. Union the buffered constraints into one shape, subtract from the parcel (`ST_Difference`) — this avoids double-subtracting area where wetland and floodplain buffers overlap
5. Subtract manual excludes, then add back manual restores (clipped to the original parcel boundary — a restore can't extend past the parcel edge)
6. Compute final area in EPSG:6579, convert to acres

For the UI's breakdown table, I additionally compute each constraint's *individual* overlap with the parcel (parcel ∩ buffered-wetland, parcel ∩ buffered-floodplain) so the user can see what each layer is responsible for. These individual numbers can sum to more than the actual total removed, when constraints overlap each other — this is expected and is noted in the API response rather than hidden.

## Setback / buffer distances

Defaults: 50 ft wetland buffer, 25 ft floodplain buffer. These are reasonable starting points based on common regulatory buffer ranges (wetland buffers commonly fall in the 25–100 ft range depending on jurisdiction and wetland classification; floodplain setbacks vary by local ordinance), but I did not have time to source Kendall County's actual adopted ordinance values specifically, and I'm not presenting them as authoritative for this county. Both are fully configurable via the API (`wetland_buffer_ft`, `floodplain_buffer_ft`) and via sliders in the UI — a real deployment would replace these defaults with Kendall County's actual adopted setback ordinance once sourced.

## Data

| Layer | Source | Real/Synthetic | Count |
|---|---|---|---|
| Parcels | Kendall County Appraisal District, ArcGIS Open Data | Real | 30,907 (417,539 acres) |
| Wetlands | USFWS National Wetlands Inventory | Real | 3,843 (5,140 acres) |
| Floodplain | FEMA NFHL (via Kendall County's portal) | Real | 120 zones |

### The data-sourcing process, honestly

This part had real friction, worth documenting because the assignment specifically asks about it:

- **USFWS's live NWI REST API returned 500 errors** on every query attempt. **FEMA's NFHL endpoints refused connections outright.** Both looked like server-side issues rather than anything wrong on my end.
- Rather than blocking on flaky federal infrastructure, I found working alternates: Kendall County's own ArcGIS Open Data portal turned out to mirror FEMA's flood zone data reliably, so I used that instead of hitting FEMA directly. For wetlands, I downloaded USFWS's pre-packaged Texas state geodatabase directly (~2GB) rather than depending on their live query API — this is what actually worked, once handled as a proper large-file download rather than a single blocking request.
- **I caught two real data-quality bugs along the way**, both worth mentioning as evidence of the kind of verification this work needs:
  1. An initial parcel dataset, found via a generic search rather than going directly to the county's own source, turned out to be from **California**, not Texas — same-sounding dataset name, wrong location entirely. Caught by checking the total reported acreage (945,483) against Kendall County's actual known land area (~424,000 acres) — obviously wrong by 2x.
  2. This established a practice I kept afterward: **verify a new geographic dataset's bounding box before trusting and loading it**, not after.

## Frontend

React + MapLibre GL (no API key required, unlike some commercial map SDKs), with `mapbox-gl-draw` for the manual exclude/restore tools. Buffer sliders and draw actions are debounced (500ms) before triggering a recalculation request, so dragging a slider doesn't spam the API.

At ~31,000 real parcels, I load parcels filtered by the current map viewport bounding box (`GET /api/parcels?bbox=...`) rather than ever requesting the full dataset — this keeps the app responsive regardless of total data volume, since what's rendered scales with what's visible, not with total row count.

## Performance

- Every geometry column has a GIST spatial index; all parcel/constraint queries are bbox- or intersects-filtered, never full-table scans.
- At current scale (~31k parcels, ~4k wetlands, 120 flood zones), interactions feel responsive — the single-parcel buildable calculation touches only the handful of constraint geometries that actually intersect that one parcel, not the full dataset.
- **Where this would start to strain:** a "show all buildable land county-wide at once" view, which nobody has asked for yet but is a natural extension — computing buildable area for all 31k parcels simultaneously would be a meaningfully heavier batch operation, and would benefit from precomputing/caching results per parcel rather than computing on every request. Very high-vertex-count parcels (a large ranch with a complex boundary) would also be slower to buffer/union than a typical rectangular lot; `ST_SimplifyPreserveTopology` on a display-only copy of the geometry (keeping the precise version for the actual area math) would help if this became a real bottleneck.

## Known limitations / what I'd do next with more time

- **Setback distances are reasonable defaults, not sourced from Kendall County's actual ordinances** — this would be the first thing to fix for a real deployment.
- **Only two constraint layers modeled** (wetlands, floodplain). Transmission line easements and existing building footprints were mentioned as options in the assignment but not implemented, given time constraints — I prioritized getting two layers fully correct (proper CRS, proper buffering, proper overlap handling, real data) over adding more layers with less rigor behind each.
- **No caching layer** — every buildable-area request recomputes from scratch. Fine at current interactive-single-parcel scale; would matter for a batch/county-wide view.
- **No automated tests against the real Kendall County data**, only against synthetic geometries with known expected areas. The synthetic tests validate the math is correct; they don't validate behavior against messy real-world geometry edge cases (self-intersections, multi-part parcels, etc.) beyond the `make_valid` repair step.
