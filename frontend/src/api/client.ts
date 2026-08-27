/**
 * API client for Buildable Land Analysis backend
 */

import type {
  ParcelSummary,
  ParcelDetail,
  ConstraintsResponse,
  BuildableRequest,
  BuildableResponse,
} from '../types/api';

// VITE_API_URL should be the backend's base URL (e.g., https://backend.railway.app)
// We always append /api to ensure correct routing
const backendUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_BASE = backendUrl.endsWith('/api') ? backendUrl : `${backendUrl.replace(/\/$/, '')}/api`;

class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = '';
    try {
      const errorData = await response.json();
      detail = errorData.detail || '';
    } catch {
      // Ignore JSON parse errors
    }
    throw new ApiError(
      `API error: ${response.status} ${response.statusText}`,
      response.status,
      detail
    );
  }
  return response.json();
}

/**
 * Get parcels within a bounding box
 */
export async function getParcels(
  bbox: [number, number, number, number],
  limit = 100
): Promise<ParcelSummary[]> {
  const [minx, miny, maxx, maxy] = bbox;
  const url = `${API_BASE}/parcels?bbox=${minx},${miny},${maxx},${maxy}&limit=${limit}`;
  const response = await fetch(url);
  return handleResponse<ParcelSummary[]>(response);
}

/**
 * Get full parcel details by ID
 */
export async function getParcel(parcelId: number): Promise<ParcelDetail> {
  const url = `${API_BASE}/parcels/${parcelId}`;
  const response = await fetch(url);
  return handleResponse<ParcelDetail>(response);
}

/**
 * Get constraints (wetlands, floodplains) for a parcel
 */
export async function getParcelConstraints(
  parcelId: number
): Promise<ConstraintsResponse> {
  const url = `${API_BASE}/parcels/${parcelId}/constraints`;
  const response = await fetch(url);
  return handleResponse<ConstraintsResponse>(response);
}

/**
 * Calculate buildable area for a parcel
 */
export async function calculateBuildable(
  parcelId: number,
  request: BuildableRequest
): Promise<BuildableResponse> {
  const url = `${API_BASE}/parcels/${parcelId}/buildable`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  return handleResponse<BuildableResponse>(response);
}

export { ApiError };
