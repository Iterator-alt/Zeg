# Technical Writeup: Buildable Land Analysis

## Overview

This document describes the design decisions, trade-offs, and implementation details of the Buildable Land Analysis application.

## Architecture Decisions

### 1. Coordinate Reference System Strategy

**Decision**: Store geometries in EPSG:4326, perform all calculations in EPSG:6579.

**Rationale**:
- EPSG:4326 (WGS 84) is the universal standard for GPS coordinates and web mapping
- EPSG:6579 (NAD83 Texas Centric Albers Equal Area) provides accurate area calculations for Texas
- EPSG:3857 (Web Mercator) was explicitly avoided for calculations due to significant distortion at non-equatorial latitudes

**Implementation**:
- All geometries stored in PostGIS with SRID 4326
- `pyproj.Transformer` used for CRS conversions
- Buffer distances specified in feet, converted to meters before applying in projected CRS

### 2. Geometry Processing Pipeline

The buildable area calculation follows this pipeline:

```
1. Load parcel geometry (EPSG:4326)
2. Transform to EPSG:6579
3. Validate with shapely.make_valid()
4. Load constraints (wetlands, floodplains)
5. Apply buffers to constraints (in meters)
6. Union all constraints
7. Apply manual excludes (clipped to parcel)
8. Subtract constraints from parcel
9. Apply manual restores (clipped to parcel)
10. Transform result back to EPSG:4326
11. Calculate area in projected CRS
```

**Key Decisions**:
- `make_valid()` is called on all geometries before boolean operations to handle self-intersections
- Manual excludes/restores are clipped to the parcel boundary, not rejected if outside
- Empty geometries are handled gracefully throughout the pipeline

### 3. API Design

**Decision**: REST API with a single calculation endpoint that accepts all parameters.

**Rationale**:
- Simpler than separate endpoints for each operation
- Allows frontend to batch parameter changes
- Enables debouncing on the client side

**Endpoint**: `POST /api/parcels/{id}/buildable`

```json
{
  "wetland_buffer_ft": 50,
  "floodplain_buffer_ft": 25,
  "manual_excludes": [{ "type": "Polygon", ... }],
  "manual_restores": [{ "type": "Polygon", ... }]
}
```

### 4. Breakdown Overlap Handling

**Decision**: Report individual constraint areas that may overlap, with explicit documentation.

**Rationale**:
- Calculating non-overlapping areas would require additional complexity
- Users benefit from seeing the impact of each constraint type
- The `breakdown_note` field clearly explains that values may not sum to total

**Example Response**:
```json
{
  "constrained_acres": 5.0,
  "breakdown": [
    { "reason": "Wetlands (with 50.0ft buffer)", "acres": 3.5 },
    { "reason": "Floodplain (with 25.0ft buffer)", "acres": 2.5 }
  ],
  "breakdown_note": "Breakdown entries may overlap..."
}
```

### 5. Frontend State Management

**Decision**: Local React state with custom hooks, no external state library.

**Rationale**:
- Application is relatively simple with clear data flow
- Custom `useBuildableCalculation` hook encapsulates debouncing and API calls
- Easier to understand and maintain

**Hooks**:
- `useDebounce`: Generic debounce utility
- `useBuildableCalculation`: Manages buildable calculation lifecycle

### 6. Map Drawing Tools

**Decision**: Use @mapbox/mapbox-gl-draw with custom tracking for exclude/restore modes.

**Implementation**:
- Single draw instance shared between exclude and restore modes
- Feature IDs tracked in refs to categorize drawn polygons
- Draw mode resets to simple_select after each polygon completion

**Trade-off**: This approach requires manual tracking but allows users to edit previously drawn polygons.

## Performance Considerations

### Database
- GIST spatial indexes on all geometry columns
- Bbox filtering for parcel queries reduces data transfer
- Connection pooling via SQLAlchemy

### Frontend
- 500ms debounce on buffer sliders and draw events
- Loading state prevents UI blocking
- Map sources updated only when data changes

### API
- Single calculation endpoint reduces round trips
- GeoJSON geometries returned directly (no additional processing)

## Error Handling

### Backend
- Invalid geometries handled with `make_valid()`
- Empty results return zero acres with empty geometry
- API errors include detailed messages in response

### Frontend
- API errors displayed in sidebar
- Loading state during calculations
- Warnings from API surfaced visibly

## Testing Strategy

### Unit Tests (25 tests)
- CRS transformation accuracy
- Buffer distance conversion (feet to meters)
- Area calculations in projected CRS
- Geometry boolean operations
- Edge cases (empty, invalid, outside-parcel geometries)

### Integration Tests (17 tests)
- API endpoint responses
- Database queries
- End-to-end calculation flow

## Future Improvements

1. **Real Data**: Replace synthetic test data with actual TNRIS/NWI/FEMA data
2. **Caching**: Add Redis caching for frequently accessed parcels
3. **Batch Operations**: Support calculating multiple parcels at once
4. **Export**: Add GeoJSON/Shapefile export for buildable areas
5. **Authentication**: Add user authentication for saved configurations
6. **Undo/Redo**: Implement undo stack for manual adjustments

## Lessons Learned

1. **CRS Matters**: Using the wrong CRS for calculations can lead to significant errors. Always use an equal-area projection for area calculations.

2. **Geometry Validation**: Real-world GIS data often contains invalid geometries. Always validate before boolean operations.

3. **Debouncing is Essential**: Without debouncing, slider changes would trigger dozens of API calls. 500ms provides good balance between responsiveness and efficiency.

4. **Document Overlap Behavior**: When breakdown values don't sum to total, users will be confused. Explicit documentation prevents misunderstanding.
