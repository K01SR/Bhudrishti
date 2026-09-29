import React, { useCallback, useEffect, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { fetchVizLayer, NationalVizLayer, VIZ_LEVEL } from '../../services/api';

type VizKind = 'fsi' | 'density' | 'status';

interface NationalVizPanelProps {
  map?: maplibregl.Map | null;
  level?: VIZ_LEVEL;
  jurisdictionCode?: string;
  className?: string;
}

const LAYER_LABELS: Record<VizKind, string> = {
  fsi: 'FSI / NBC Bucket',
  density: 'ULPIN Density',
  status: 'Twin Coverage',
};

const LEVEL_OPTIONS: VIZ_LEVEL[] = ['STATE', 'DISTRICT', 'TALUKA', 'VILLAGE'];

function bucketLegend(kind: VizKind): { label: string; color: string }[] {
  if (kind === 'fsi') {
    return [
      { label: 'NO_TWIN', color: '#e5e7eb' },
      { label: 'UNDER 0.5', color: '#1f7a3d' },
      { label: '0.5–1.0', color: '#7bb661' },
      { label: '1.0–1.5', color: '#e0d33c' },
      { label: '1.5–2.5', color: '#f0a202' },
      { label: '2.5–4.0', color: '#e2593c' },
      { label: 'EXCEEDED', color: '#9d174d' },
    ];
  }
  if (kind === 'density') {
    return [
      { label: '0/km²', color: '#f3f4f6' },
      { label: '1–5', color: '#c4b5fd' },
      { label: '5–25', color: '#8b5cf6' },
      { label: '25–100', color: '#6d28d9' },
      { label: '100+', color: '#581c87' },
    ];
  }
  return [
    { label: 'VERIFIED (>90%)', color: '#16a34a' },
    { label: 'PENDING', color: '#f59e0b' },
    { label: 'CONFLICT', color: '#dc2626' },
    { label: 'NONE', color: '#e5e7eb' },
  ];
}

export const NationalVizPanel: React.FC<NationalVizPanelProps> = ({
  map,
  level = 'STATE',
  jurisdictionCode,
  className = '',
}) => {
  const [kind, setKind] = useState<VizKind>('fsi');
  const [vizLevel, setVizLevel] = useState<VIZ_LEVEL>(level);
  const [featureCount, setFeatureCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const layerId = `national-viz-${kind}-${vizLevel}`;

  const loadLayer = useCallback(async () => {
    if (!map) return;
    setLoading(true);
    setError(null);
    try {
      const data: NationalVizLayer = await fetchVizLayer(kind, vizLevel, jurisdictionCode);
      setFeatureCount(data.features.length);

      if (!map.getSource(layerId)) {
        map.addSource(layerId, { type: 'geojson', data });
      } else {
        (map.getSource(layerId) as maplibregl.GeoJSONSource).setData(data);
      }

      if (!map.getLayer(layerId)) {
        map.addLayer({ id: layerId, type: 'fill', source: layerId, paint: { 'fill-color': ['get', 'fill'], 'fill-opacity': 0.55 } });
        map.addLayer({
          id: `${layerId}-outline`,
          type: 'line',
          source: layerId,
          paint: { 'line-color': '#1e293b', 'line-width': 0.5 },
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load national layer');
    } finally {
      setLoading(false);
    }
  }, [map, kind, vizLevel, jurisdictionCode, layerId]);

  useEffect(() => {
    loadLayer();
    return () => {
      if (map) {
        if (map.getLayer(layerId)) map.removeLayer(layerId);
        if (map.getLayer(`${layerId}-outline`)) map.removeLayer(`${layerId}-outline`);
        if (map.getSource(layerId)) map.removeSource(layerId);
      }
    };
  }, [loadLayer, map, layerId]);

  return (
    <div className={`pointer-events-auto rounded-xl border border-slate-200 bg-white/95 shadow-lg backdrop-blur ${className}`}>
      <div className="border-b border-slate-100 px-3 py-2">
        <div className="text-xs font-semibold text-slate-800">National Thematic Layer</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {(['fsi', 'density', 'status'] as VizKind[]).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                kind === k ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {LAYER_LABELS[k]}
            </button>
          ))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {LEVEL_OPTIONS.map((lv) => (
            <button
              key={lv}
              onClick={() => setVizLevel(lv)}
              className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                vizLevel === lv ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
              }`}
            >
              {lv}
            </button>
          ))}
        </div>
      </div>

      <div className="max-h-52 overflow-y-auto px-3 py-2">
        {loading && <div className="text-[11px] text-slate-500">Loading {featureCount || ''} units…</div>}
        {error && <div className="text-[11px] text-red-600">{error}</div>}
        {!loading && !error && (
          <>
            <div className="mb-1 text-[11px] text-slate-500">
              {featureCount} feature{featureCount === 1 ? '' : 's'} in layer
            </div>
            <div className="space-y-1">
              {bucketLegend(kind).map((b) => (
                <div key={b.label} className="flex items-center gap-1.5 text-[11px] text-slate-700">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-sm border border-slate-300" style={{ background: b.color }} />
                  {b.label}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default NationalVizPanel;