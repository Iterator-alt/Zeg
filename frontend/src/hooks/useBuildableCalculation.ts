/**
 * Hook for managing buildable area calculations with debouncing
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { calculateBuildable } from '../api/client';
import type { BuildableResponse, BuildableRequest } from '../types/api';
import { useDebounce } from './useDebounce';

interface UseBuildableCalculationProps {
  parcelId: number | null;
  wetlandBufferFt: number;
  floodplainBufferFt: number;
  manualExcludes: GeoJSON.Geometry[];
  manualRestores: GeoJSON.Geometry[];
  debounceMs?: number;
}

interface UseBuildableCalculationResult {
  result: BuildableResponse | null;
  isLoading: boolean;
  error: string | null;
  recalculate: () => void;
}

export function useBuildableCalculation({
  parcelId,
  wetlandBufferFt,
  floodplainBufferFt,
  manualExcludes,
  manualRestores,
  debounceMs = 500,
}: UseBuildableCalculationProps): UseBuildableCalculationResult {
  const [result, setResult] = useState<BuildableResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounce buffer values to prevent API spam during slider dragging
  const debouncedWetlandBuffer = useDebounce(wetlandBufferFt, debounceMs);
  const debouncedFloodplainBuffer = useDebounce(floodplainBufferFt, debounceMs);

  // Track request version to handle race conditions
  const requestVersionRef = useRef(0);

  // Create a stable serialization of manual geometries for dependency tracking
  // Also debounce these to prevent rapid API calls during drawing
  const manualExcludesJson = JSON.stringify(manualExcludes);
  const manualRestoresJson = JSON.stringify(manualRestores);
  const debouncedExcludesJson = useDebounce(manualExcludesJson, debounceMs);
  const debouncedRestoresJson = useDebounce(manualRestoresJson, debounceMs);

  const performCalculation = useCallback(async () => {
    if (parcelId === null) {
      setResult(null);
      return;
    }

    const currentVersion = ++requestVersionRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const request: BuildableRequest = {
        wetland_buffer_ft: debouncedWetlandBuffer,
        floodplain_buffer_ft: debouncedFloodplainBuffer,
        manual_excludes: JSON.parse(debouncedExcludesJson),
        manual_restores: JSON.parse(debouncedRestoresJson),
      };

      const response = await calculateBuildable(parcelId, request);

      // Only update if this is still the latest request
      if (currentVersion === requestVersionRef.current) {
        setResult(response);
        setError(null);
      }
    } catch (err) {
      // Only update if this is still the latest request
      if (currentVersion === requestVersionRef.current) {
        setError(err instanceof Error ? err.message : 'Calculation failed');
        setResult(null);
      }
    } finally {
      // Only clear loading if this is still the latest request
      if (currentVersion === requestVersionRef.current) {
        setIsLoading(false);
      }
    }
  }, [
    parcelId,
    debouncedWetlandBuffer,
    debouncedFloodplainBuffer,
    debouncedExcludesJson,
    debouncedRestoresJson,
  ]);

  // Recalculate when dependencies change
  useEffect(() => {
    performCalculation();
  }, [performCalculation]);

  return {
    result,
    isLoading,
    error,
    recalculate: performCalculation,
  };
}
