/**
 * API types for Buildable Land Analysis
 */

export interface ParcelSummary {
  id: number;
  source_id: string | null;
  centroid_lon: number;
  centroid_lat: number;
  recorded_acres: number | null;
  calculated_acres: number | null;
}

export interface ParcelWithGeometry {
  id: number;
  source_id: string | null;
  calculated_acres: number | null;
  geometry: GeoJSON.Geometry;
}

export interface ParcelDetail {
  id: number;
  source_id: string | null;
  owner_name: string | null;
  address: string | null;
  recorded_acres: number | null;
  calculated_acres: number | null;
  county: string | null;
  geometry: GeoJSON.Geometry;
}

export interface WetlandFeature {
  id: number;
  attribute: string | null;
  wetland_type: string | null;
  geometry: GeoJSON.Geometry;
}

export interface FloodplainFeature {
  id: number;
  fld_zone: string | null;
  zone_subty: string | null;
  geometry: GeoJSON.Geometry;
}

export interface ConstraintsResponse {
  wetlands: WetlandFeature[];
  floodplains: FloodplainFeature[];
}

export interface BreakdownItem {
  reason: string;
  acres: number;
  type: 'removed' | 'added';
}

export interface BuildableRequest {
  wetland_buffer_ft: number;
  floodplain_buffer_ft: number;
  manual_excludes: GeoJSON.Geometry[];
  manual_restores: GeoJSON.Geometry[];
}

export interface BuildableResponse {
  buildable_acres: number;
  parcel_acres: number;
  constrained_acres: number;
  buildable_geom: GeoJSON.Geometry | null;
  breakdown: BreakdownItem[];
  breakdown_note: string;
  warnings: string[];
}
