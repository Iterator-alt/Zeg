/**
 * Sidebar component with buffer controls, breakdown display, and drawing tools
 */

import type {
  ParcelDetail,
  ConstraintsResponse,
  BuildableResponse,
} from '../types/api';
import './Sidebar.css';

interface SidebarProps {
  selectedParcel: ParcelDetail | null;
  constraints: ConstraintsResponse | null;
  buildableResult: BuildableResponse | null;
  isLoading: boolean;
  error: string | null;
  wetlandBufferFt: number;
  floodplainBufferFt: number;
  onWetlandBufferChange: (value: number) => void;
  onFloodplainBufferChange: (value: number) => void;
  drawMode: 'none' | 'exclude' | 'restore';
  onDrawModeChange: (mode: 'none' | 'exclude' | 'restore') => void;
  excludeCount: number;
  restoreCount: number;
}

export function Sidebar({
  selectedParcel,
  constraints,
  buildableResult,
  isLoading,
  error,
  wetlandBufferFt,
  floodplainBufferFt,
  onWetlandBufferChange,
  onFloodplainBufferChange,
  drawMode,
  onDrawModeChange,
  excludeCount,
  restoreCount,
}: SidebarProps) {
  return (
    <div className="sidebar">
      <h1 className="sidebar-title">Buildable Land Analysis</h1>

      {/* Parcel Info */}
      <section className="sidebar-section">
        <h2>Selected Parcel</h2>
        {selectedParcel ? (
          <div className="parcel-info">
            <div className="info-row">
              <span className="label">ID:</span>
              <span className="value">{selectedParcel.source_id || selectedParcel.id}</span>
            </div>
            {selectedParcel.address && (
              <div className="info-row">
                <span className="label">Address:</span>
                <span className="value">{selectedParcel.address}</span>
              </div>
            )}
            <div className="info-row">
              <span className="label">Total Acres:</span>
              <span className="value">
                {(selectedParcel.calculated_acres || selectedParcel.recorded_acres || 0).toFixed(2)}
              </span>
            </div>
          </div>
        ) : (
          <p className="placeholder-text">Click a parcel on the map to select it</p>
        )}
      </section>

      {/* Buffer Controls */}
      <section className="sidebar-section">
        <h2>Buffer Distances</h2>
        <div className="buffer-control">
          <label htmlFor="wetland-buffer">
            Wetland Buffer: <strong>{wetlandBufferFt} ft</strong>
          </label>
          <input
            type="range"
            id="wetland-buffer"
            min="0"
            max="200"
            step="5"
            value={wetlandBufferFt}
            onChange={(e) => onWetlandBufferChange(Number(e.target.value))}
            disabled={!selectedParcel}
          />
          <div className="range-labels">
            <span>0 ft</span>
            <span>200 ft</span>
          </div>
        </div>
        <div className="buffer-control">
          <label htmlFor="floodplain-buffer">
            Floodplain Buffer: <strong>{floodplainBufferFt} ft</strong>
          </label>
          <input
            type="range"
            id="floodplain-buffer"
            min="0"
            max="200"
            step="5"
            value={floodplainBufferFt}
            onChange={(e) => onFloodplainBufferChange(Number(e.target.value))}
            disabled={!selectedParcel}
          />
          <div className="range-labels">
            <span>0 ft</span>
            <span>200 ft</span>
          </div>
        </div>
      </section>

      {/* Drawing Tools */}
      <section className="sidebar-section">
        <h2>Manual Adjustments</h2>
        <div className="draw-buttons">
          <button
            className={`draw-btn exclude-btn ${drawMode === 'exclude' ? 'active' : ''}`}
            onClick={() => onDrawModeChange(drawMode === 'exclude' ? 'none' : 'exclude')}
            disabled={!selectedParcel}
          >
            Draw Exclude
          </button>
          <button
            className={`draw-btn restore-btn ${drawMode === 'restore' ? 'active' : ''}`}
            onClick={() => onDrawModeChange(drawMode === 'restore' ? 'none' : 'restore')}
            disabled={!selectedParcel}
          >
            Draw Restore
          </button>
        </div>
        {(excludeCount > 0 || restoreCount > 0) && (
          <div className="draw-summary">
            {excludeCount > 0 && (
              <span className="exclude-count">{excludeCount} exclusion(s)</span>
            )}
            {restoreCount > 0 && (
              <span className="restore-count">{restoreCount} restoration(s)</span>
            )}
          </div>
        )}
        <p className="help-text">
          Use the draw tools to manually exclude or restore areas within the parcel.
        </p>
      </section>

      {/* Results */}
      <section className="sidebar-section results-section">
        <h2>Buildable Area</h2>

        {/* Loading State */}
        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Calculating...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="error-message">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Results */}
        {buildableResult && !isLoading && (
          <>
            <div className="buildable-total">
              <span className="buildable-acres">
                {buildableResult.buildable_acres.toFixed(2)}
              </span>
              <span className="buildable-unit">acres buildable</span>
            </div>

            <div className="buildable-summary">
              <div className="summary-row">
                <span>Total Parcel:</span>
                <span>{buildableResult.parcel_acres.toFixed(2)} ac</span>
              </div>
              <div className="summary-row constrained">
                <span>Constrained:</span>
                <span>-{buildableResult.constrained_acres.toFixed(2)} ac</span>
              </div>
              <div className="summary-row buildable">
                <span>Buildable:</span>
                <span>{buildableResult.buildable_acres.toFixed(2)} ac</span>
              </div>
            </div>

            {/* Breakdown Table */}
            {buildableResult.breakdown.length > 0 && (
              <div className="breakdown-section">
                <h3>Breakdown</h3>
                <table className="breakdown-table">
                  <thead>
                    <tr>
                      <th>Constraint</th>
                      <th>Acres</th>
                    </tr>
                  </thead>
                  <tbody>
                    {buildableResult.breakdown.map((item, idx) => (
                      <tr key={idx} className={item.type === 'removed' ? 'removed' : 'added'}>
                        <td>{item.reason}</td>
                        <td>
                          {item.type === 'removed' ? '-' : '+'}
                          {item.acres.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="breakdown-note">{buildableResult.breakdown_note}</p>
              </div>
            )}

            {/* Warnings */}
            {buildableResult.warnings.length > 0 && (
              <div className="warnings-section">
                <h3>Warnings</h3>
                <ul className="warnings-list">
                  {buildableResult.warnings.map((warning, idx) => (
                    <li key={idx}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        {/* Constraints Summary */}
        {constraints && !buildableResult && !isLoading && (
          <div className="constraints-summary">
            <p>
              <strong>{constraints.wetlands.length}</strong> wetland(s),{' '}
              <strong>{constraints.floodplains.length}</strong> floodplain zone(s) found
            </p>
          </div>
        )}
      </section>

      {/* Legend */}
      <section className="sidebar-section legend-section">
        <h2>Legend</h2>
        <div className="legend-items">
          <div className="legend-item">
            <span className="legend-color" style={{ backgroundColor: '#00ffaa', boxShadow: '0 0 8px #00ffaa' }}></span>
            <span>Selected Parcel</span>
          </div>
          <div className="legend-item">
            <span className="legend-color" style={{ backgroundColor: '#00aaff', boxShadow: '0 0 8px #00aaff' }}></span>
            <span>Wetlands</span>
          </div>
          <div className="legend-item">
            <span className="legend-color" style={{ backgroundColor: '#ffaa00', boxShadow: '0 0 8px #ffaa00' }}></span>
            <span>Floodplain</span>
          </div>
          <div className="legend-item">
            <span className="legend-color" style={{ backgroundColor: '#00ff88', boxShadow: '0 0 8px #00ff88' }}></span>
            <span>Buildable Area</span>
          </div>
        </div>
      </section>
    </div>
  );
}
