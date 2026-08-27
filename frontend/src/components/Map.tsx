/**
 * MapLibre GL map component with parcel display and drawing tools
 */

import { useEffect, useRef, useCallback } from 'react';
import * as maplibregl from 'maplibre-gl';
import MapboxDraw from '@mapbox/mapbox-gl-draw';
import 'maplibre-gl/dist/maplibre-gl.css';
import '@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css';

import { getParcels, getParcel, getParcelConstraints } from '../api/client';
import type {
  ParcelSummary,
  ParcelDetail,
  ConstraintsResponse,
  BuildableResponse,
} from '../types/api';

// Kendall County, TX approximate center (where our test data is)
const DEFAULT_CENTER: [number, number] = [-98.7, 29.9];
const DEFAULT_ZOOM = 14;

// Custom draw styles compatible with MapLibre (using ["literal", [...]] for arrays)
const drawStyles = [
  // Polygon fill - active (being drawn)
  {
    id: 'gl-draw-polygon-fill-active',
    type: 'fill',
    filter: ['all', ['==', '$type', 'Polygon'], ['==', 'active', 'true']],
    paint: {
      'fill-color': '#fbb03b',
      'fill-opacity': 0.2,
    },
  },
  // Polygon fill - inactive
  {
    id: 'gl-draw-polygon-fill-inactive',
    type: 'fill',
    filter: ['all', ['==', '$type', 'Polygon'], ['==', 'active', 'false']],
    paint: {
      'fill-color': '#3bb2d0',
      'fill-opacity': 0.2,
    },
  },
  // Polygon outline - active
  {
    id: 'gl-draw-polygon-stroke-active',
    type: 'line',
    filter: ['all', ['==', '$type', 'Polygon'], ['==', 'active', 'true']],
    paint: {
      'line-color': '#fbb03b',
      'line-width': 2,
    },
  },
  // Polygon outline - inactive
  {
    id: 'gl-draw-polygon-stroke-inactive',
    type: 'line',
    filter: ['all', ['==', '$type', 'Polygon'], ['==', 'active', 'false']],
    paint: {
      'line-color': '#3bb2d0',
      'line-width': 2,
    },
  },
  // Line - active (using literal for dasharray)
  {
    id: 'gl-draw-line-active',
    type: 'line',
    filter: ['all', ['==', '$type', 'LineString'], ['==', 'active', 'true']],
    paint: {
      'line-color': '#fbb03b',
      'line-width': 2,
      'line-dasharray': ['literal', [0.2, 2]],
    },
  },
  // Line - inactive
  {
    id: 'gl-draw-line-inactive',
    type: 'line',
    filter: ['all', ['==', '$type', 'LineString'], ['==', 'active', 'false']],
    paint: {
      'line-color': '#3bb2d0',
      'line-width': 2,
      'line-dasharray': ['literal', [0.2, 2]],
    },
  },
  // Vertex points - active
  {
    id: 'gl-draw-point-active',
    type: 'circle',
    filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'vertex'], ['==', 'active', 'true']],
    paint: {
      'circle-radius': 6,
      'circle-color': '#fbb03b',
    },
  },
  // Vertex points - inactive
  {
    id: 'gl-draw-point-inactive',
    type: 'circle',
    filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'vertex'], ['==', 'active', 'false']],
    paint: {
      'circle-radius': 4,
      'circle-color': '#3bb2d0',
    },
  },
  // Midpoints
  {
    id: 'gl-draw-midpoint',
    type: 'circle',
    filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'midpoint']],
    paint: {
      'circle-radius': 3,
      'circle-color': '#fbb03b',
    },
  },
];

interface MapProps {
  onParcelSelect: (parcel: ParcelDetail | null) => void;
  onConstraintsLoad: (constraints: ConstraintsResponse | null) => void;
  onDrawChange: (excludes: GeoJSON.Geometry[], restores: GeoJSON.Geometry[]) => void;
  buildableResult: BuildableResponse | null;
  drawMode: 'none' | 'exclude' | 'restore';
  setDrawMode: (mode: 'none' | 'exclude' | 'restore') => void;
}

export function Map({
  onParcelSelect,
  onConstraintsLoad,
  onDrawChange,
  buildableResult,
  drawMode,
  setDrawMode,
}: MapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const drawRef = useRef<MapboxDraw | null>(null);
  const excludeIdsRef = useRef<Set<string>>(new Set());
  const restoreIdsRef = useRef<Set<string>>(new Set());

  // Handle draw changes
  const handleDrawChange = useCallback(() => {
    const draw = drawRef.current;
    if (!draw) return;

    const allFeatures = draw.getAll();
    const excludes: GeoJSON.Geometry[] = [];
    const restores: GeoJSON.Geometry[] = [];

    // Track new features based on current mode
    allFeatures.features.forEach((feature) => {
      const id = feature.id as string;

      // If it's a new feature, assign it to current mode
      if (!excludeIdsRef.current.has(id) && !restoreIdsRef.current.has(id)) {
        if (drawMode === 'exclude') {
          excludeIdsRef.current.add(id);
        } else if (drawMode === 'restore') {
          restoreIdsRef.current.add(id);
        }
      }

      // Categorize feature
      if (excludeIdsRef.current.has(id)) {
        excludes.push(feature.geometry as GeoJSON.Geometry);
      } else if (restoreIdsRef.current.has(id)) {
        restores.push(feature.geometry as GeoJSON.Geometry);
      }
    });

    // Clean up deleted features from tracking sets
    const currentIds = new Set(allFeatures.features.map(f => f.id as string));
    excludeIdsRef.current.forEach(id => {
      if (!currentIds.has(id)) excludeIdsRef.current.delete(id);
    });
    restoreIdsRef.current.forEach(id => {
      if (!currentIds.has(id)) restoreIdsRef.current.delete(id);
    });

    onDrawChange(excludes, restores);

    // Reset to simple_select after drawing
    if (drawMode !== 'none') {
      setDrawMode('none');
    }
  }, [drawMode, onDrawChange, setDrawMode]);

  // Initialize map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors',
          },
        },
        layers: [
          {
            id: 'osm',
            type: 'raster',
            source: 'osm',
          },
        ],
      },
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
    });

    // Add navigation controls
    map.addControl(new maplibregl.NavigationControl(), 'top-right');

    // Initialize draw control with MapLibre-compatible styles
    const draw = new MapboxDraw({
      displayControlsDefault: false,
      controls: {
        polygon: true,
        trash: true,
      },
      defaultMode: 'simple_select',
      styles: drawStyles,
    });

    map.addControl(draw as unknown as maplibregl.IControl, 'top-left');
    drawRef.current = draw;

    map.on('load', () => {
      // Add parcel markers source (points for clickable markers)
      map.addSource('parcel-markers', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      // Parcel markers layer
      map.addLayer({
        id: 'parcel-markers',
        type: 'circle',
        source: 'parcel-markers',
        paint: {
          'circle-radius': 8,
          'circle-color': '#3388ff',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 2,
        },
      });

      // Selected parcel source
      map.addSource('selected-parcel', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'selected-parcel-fill',
        type: 'fill',
        source: 'selected-parcel',
        paint: {
          'fill-color': '#007bff',
          'fill-opacity': 0.15,
        },
      });

      map.addLayer({
        id: 'selected-parcel-outline',
        type: 'line',
        source: 'selected-parcel',
        paint: {
          'line-color': '#007bff',
          'line-width': 3,
        },
      });

      // Wetlands layer (blue)
      map.addSource('wetlands', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'wetlands-fill',
        type: 'fill',
        source: 'wetlands',
        paint: {
          'fill-color': '#0066cc',
          'fill-opacity': 0.35,
        },
      });

      map.addLayer({
        id: 'wetlands-outline',
        type: 'line',
        source: 'wetlands',
        paint: {
          'line-color': '#0044aa',
          'line-width': 1.5,
        },
      });

      // Floodplain layer (yellow/orange)
      map.addSource('floodplains', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'floodplains-fill',
        type: 'fill',
        source: 'floodplains',
        paint: {
          'fill-color': '#ffaa00',
          'fill-opacity': 0.35,
        },
      });

      map.addLayer({
        id: 'floodplains-outline',
        type: 'line',
        source: 'floodplains',
        paint: {
          'line-color': '#cc8800',
          'line-width': 1.5,
        },
      });

      // Buildable area layer (green)
      map.addSource('buildable', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'buildable-fill',
        type: 'fill',
        source: 'buildable',
        paint: {
          'fill-color': '#22c55e',
          'fill-opacity': 0.5,
        },
      });

      map.addLayer({
        id: 'buildable-outline',
        type: 'line',
        source: 'buildable',
        paint: {
          'line-color': '#16a34a',
          'line-width': 2,
        },
      });

      // Load initial parcels
      loadParcelsInView(map);
    });

    // Load parcels when map moves
    map.on('moveend', () => {
      loadParcelsInView(map);
    });

    // Handle parcel marker click
    map.on('click', 'parcel-markers', async (e: maplibregl.MapLayerMouseEvent) => {
      if (e.features && e.features.length > 0) {
        const feature = e.features[0];
        const parcelId = feature.properties?.id;
        if (parcelId) {
          await selectParcel(map, parcelId);
        }
      }
    });

    // Change cursor on hover
    map.on('mouseenter', 'parcel-markers', () => {
      map.getCanvas().style.cursor = 'pointer';
    });

    map.on('mouseleave', 'parcel-markers', () => {
      map.getCanvas().style.cursor = '';
    });

    // Handle draw events (mapbox-gl-draw adds custom events)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (map as any).on('draw.create', handleDrawChange);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (map as any).on('draw.delete', handleDrawChange);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (map as any).on('draw.update', handleDrawChange);

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [handleDrawChange]);

  // Update draw mode
  useEffect(() => {
    const draw = drawRef.current;
    if (!draw) return;

    if (drawMode === 'exclude' || drawMode === 'restore') {
      draw.changeMode('draw_polygon');
    } else {
      draw.changeMode('simple_select');
    }
  }, [drawMode]);

  // Update buildable layer when result changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const source = map.getSource('buildable') as maplibregl.GeoJSONSource;
    if (!source) return;

    if (buildableResult?.buildable_geom) {
      source.setData({
        type: 'Feature',
        properties: {},
        geometry: buildableResult.buildable_geom,
      } as GeoJSON.Feature);
    } else {
      source.setData({ type: 'FeatureCollection', features: [] });
    }
  }, [buildableResult]);

  const loadParcelsInView = async (map: maplibregl.Map) => {
    // Guard: ensure map style is loaded before accessing sources
    if (!map.isStyleLoaded()) return;

    const bounds = map.getBounds();
    const bbox: [number, number, number, number] = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
    ];

    try {
      const parcels = await getParcels(bbox, 200);
      updateParcelsLayer(map, parcels);
    } catch (error) {
      console.error('Error loading parcels:', error);
    }
  };

  const updateParcelsLayer = (map: maplibregl.Map, parcels: ParcelSummary[]) => {
    // Guard: ensure map style is loaded before accessing sources
    if (!map.isStyleLoaded()) return;

    const source = map.getSource('parcel-markers') as maplibregl.GeoJSONSource | undefined;
    if (!source) return;

    const features: GeoJSON.Feature[] = parcels.map((p) => ({
      type: 'Feature',
      properties: {
        id: p.id,
        source_id: p.source_id,
        acres: p.calculated_acres || p.recorded_acres,
      },
      geometry: {
        type: 'Point',
        coordinates: [p.centroid_lon, p.centroid_lat],
      },
    }));

    source.setData({
      type: 'FeatureCollection',
      features,
    });
  };

  const selectParcel = async (map: maplibregl.Map, parcelId: number) => {
    // Guard: ensure map style is loaded before accessing sources
    if (!map.isStyleLoaded()) {
      console.warn('Map style not loaded yet, cannot select parcel');
      return;
    }

    try {
      // Get full parcel details
      const parcel = await getParcel(parcelId);
      onParcelSelect(parcel);

      // Update selected parcel layer
      const selectedSource = map.getSource('selected-parcel') as maplibregl.GeoJSONSource | undefined;
      if (selectedSource) {
        selectedSource.setData({
          type: 'Feature',
          properties: { id: parcel.id },
          geometry: parcel.geometry,
        } as GeoJSON.Feature);
      }

      // Get and display constraints
      const constraints = await getParcelConstraints(parcelId);
      onConstraintsLoad(constraints);

      // Update wetlands layer
      const wetlandsSource = map.getSource('wetlands') as maplibregl.GeoJSONSource | undefined;
      if (wetlandsSource) {
        wetlandsSource.setData({
          type: 'FeatureCollection',
          features: constraints.wetlands.map((w) => ({
            type: 'Feature',
            properties: { id: w.id, type: w.wetland_type },
            geometry: w.geometry,
          })),
        } as GeoJSON.FeatureCollection);
      }

      // Update floodplains layer
      const floodplainsSource = map.getSource('floodplains') as maplibregl.GeoJSONSource | undefined;
      if (floodplainsSource) {
        floodplainsSource.setData({
          type: 'FeatureCollection',
          features: constraints.floodplains.map((f) => ({
            type: 'Feature',
            properties: { id: f.id, zone: f.fld_zone },
            geometry: f.geometry,
          })),
        } as GeoJSON.FeatureCollection);
      }

      // Clear draw features and tracking
      const draw = drawRef.current;
      if (draw) {
        draw.deleteAll();
        excludeIdsRef.current.clear();
        restoreIdsRef.current.clear();
        onDrawChange([], []);
      }

      // Fit to parcel bounds
      const bounds = new maplibregl.LngLatBounds();
      const geom = parcel.geometry;
      if (geom.type === 'Polygon') {
        (geom.coordinates[0] as [number, number][]).forEach((coord) => {
          bounds.extend(coord);
        });
      } else if (geom.type === 'MultiPolygon') {
        (geom.coordinates as [number, number][][][]).forEach((poly) => {
          (poly[0] as [number, number][]).forEach((coord) => {
            bounds.extend(coord);
          });
        });
      }
      map.fitBounds(bounds, { padding: 100, maxZoom: 16 });
    } catch (error) {
      console.error('Error selecting parcel:', error);
    }
  };

  return (
    <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
  );
}
