/**
 * Main App component for Buildable Land Analysis
 */

import { useState, useCallback } from 'react';
import { Map } from './components/Map';
import { Sidebar } from './components/Sidebar';
import { useBuildableCalculation } from './hooks/useBuildableCalculation';
import type { ParcelDetail, ConstraintsResponse } from './types/api';
import './App.css';

function App() {
  // Selected parcel state
  const [selectedParcel, setSelectedParcel] = useState<ParcelDetail | null>(null);
  const [constraints, setConstraints] = useState<ConstraintsResponse | null>(null);

  // Buffer distances
  const [wetlandBufferFt, setWetlandBufferFt] = useState(50);
  const [floodplainBufferFt, setFloodplainBufferFt] = useState(25);

  // Manual adjustments
  const [manualExcludes, setManualExcludes] = useState<GeoJSON.Geometry[]>([]);
  const [manualRestores, setManualRestores] = useState<GeoJSON.Geometry[]>([]);

  // Draw mode
  const [drawMode, setDrawMode] = useState<'none' | 'exclude' | 'restore'>('none');

  // Buildable calculation with debouncing
  const { result, isLoading, error } = useBuildableCalculation({
    parcelId: selectedParcel?.id ?? null,
    wetlandBufferFt,
    floodplainBufferFt,
    manualExcludes,
    manualRestores,
    debounceMs: 500,
  });

  // Handle parcel selection
  const handleParcelSelect = useCallback((parcel: ParcelDetail | null) => {
    setSelectedParcel(parcel);
    // Reset manual adjustments when selecting new parcel
    setManualExcludes([]);
    setManualRestores([]);
    setDrawMode('none');
  }, []);

  // Handle constraints load
  const handleConstraintsLoad = useCallback((newConstraints: ConstraintsResponse | null) => {
    setConstraints(newConstraints);
  }, []);

  // Handle draw changes
  const handleDrawChange = useCallback((excludes: GeoJSON.Geometry[], restores: GeoJSON.Geometry[]) => {
    setManualExcludes(excludes);
    setManualRestores(restores);
  }, []);

  return (
    <div className="app">
      <Sidebar
        selectedParcel={selectedParcel}
        constraints={constraints}
        buildableResult={result}
        isLoading={isLoading}
        error={error}
        wetlandBufferFt={wetlandBufferFt}
        floodplainBufferFt={floodplainBufferFt}
        onWetlandBufferChange={setWetlandBufferFt}
        onFloodplainBufferChange={setFloodplainBufferFt}
        drawMode={drawMode}
        onDrawModeChange={setDrawMode}
        excludeCount={manualExcludes.length}
        restoreCount={manualRestores.length}
      />
      <div className="map-container">
        <Map
          onParcelSelect={handleParcelSelect}
          onConstraintsLoad={handleConstraintsLoad}
          onDrawChange={handleDrawChange}
          buildableResult={result}
          drawMode={drawMode}
          setDrawMode={setDrawMode}
        />
      </div>
    </div>
  );
}

export default App;
