/**
 * Hook for managing buildable area calculations with debouncing
 */

import { useState, useEffect, useRef } from 'react';
import { calculateBuildable } from '../api/client';
import type { BuildableResponse, BuildableRequest } from '../types/api';

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

  // Track request version to handle race conditions
  const requestVersionRef = useRef(0);
  const debounceTimerRef = useRef<number | null>(null);

  // Store latest values in refs to avoid stale closures
  const parcelIdRef = useRef(parcelId);
  const wetlandBufferRef = useRef(wetlandBufferFt);
  const floodplainBufferRef = useRef(floodplainBufferFt);
  const manualExcludesRef = useRef(manualExcludes);
  const manualRestoresRef = useRef(manualRestores);

  // Keep refs updated
  parcelIdRef.current = parcelId;
  wetlandBufferRef.current = wetlandBufferFt;
  floodplainBufferRef.current = floodplainBufferFt;
  manualExcludesRef.current = manualExcludes;
  manualRestoresRef.current = manualRestores;

  const performCalculation = async () => {
    const currentParcelId = parcelIdRef.current;
    if (currentParcelId === null) {
      setResult(null);
      return;
    }

    const currentVersion = ++requestVersionRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const request: BuildableRequest = {
        wetland_buffer_ft: wetlandBufferRef.current,
        floodplain_buffer_ft: floodplainBufferRef.current,
        manual_excludes: manualExcludesRef.current,
        manual_restores: manualRestoresRef.current,
      };

      const response = await calculateBuildable(currentParcelId, request);

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
  };

  // Debounced recalculation when inputs change
  useEffect(() => {
    // Clear any pending debounce
    if (debounceTimerRef.current !== null) {
      clearTimeout(debounceTimerRef.current);
    }

    // Schedule new calculation
    debounceTimerRef.current = window.setTimeout(() => {
      performCalculation();
    }, debounceMs);

    // Cleanup on unmount or before next effect
    return () => {
      if (debounceTimerRef.current !== null) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [
    parcelId,
    wetlandBufferFt,
    floodplainBufferFt,
    JSON.stringify(manualExcludes),
    JSON.stringify(manualRestores),
    debounceMs,
  ]);

  return {
    result,
    isLoading,
    error,
    recalculate: performCalculation,
  };
}
