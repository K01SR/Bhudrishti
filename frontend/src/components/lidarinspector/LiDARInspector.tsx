import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  MousePointer2,
  Ruler,
  Slice,
  Box,
  Layers,
  Palette,
  Maximize,
  X,
  Focus,
  Building2,
  RotateCcw,
  Trash2,
  Info,
  Check,
  ArrowUpRight,
  Scan,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Copy,
} from 'lucide-react';
import PointCloudEngine, {
  ColorModeOptions,
  EngineStatus,
  InspectInfo,
  LayerVisibility,
  MeasureRead,
} from './pointCloudEngine';
import { fetchLidarScene, fetchLidarPoints } from './lidarApi';
import { DEMO_ULPIN } from '../../constants';
import {
  CLASS_COLORS,
  CLASS_LABELS,
  ColorMode,
  DecodedPointCloud,
  LidarLevel,
  LidarScene,
  LidarSelection,
  PointShape,
  QualityMode,
  Tool,
} from './types';
import './lidarInspector.css';

const QUALITY_STEP: Record<Exclude<QualityMode, 'auto'>, number> = {
  low: 4,
  medium: 2,
  high: 1,
};

const COLOR_MODES: { id: ColorMode; label: string; key: string }[] = [
  { id: 'rgb', label: 'Photoreal RGB', key: '1' },
  { id: 'epoch2_delta', label: 'Vertical Delta', key: '2' },
  { id: 'elevation', label: 'Turbo Elev', key: '3' },
  { id: 'intensity', label: 'Laser Intensity', key: '4' },
  { id: 'classification', label: 'ASPRS Class', key: '5' },
  { id: 'gradient', label: 'Gradient', key: '6' },
  { id: 'monochrome', label: 'Blueprint', key: '7' },
];

function fmt(n: number, d = 1): string {
  if (!isFinite(n)) return '—';
  return n.toFixed(d);
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

interface LiDARInspectorProps {
  initialULPIN?: string | null;
  autoFocusSelection?: boolean;
  onClose?: () => void;
  onNavigateProperty?: (ulpin: string) => void;
  className?: string;
}

export default function LiDARInspector({
  initialULPIN = null,
  autoFocusSelection = true,
  onClose,
  onNavigateProperty,
  className,
}: LiDARInspectorProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const labelLayerRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<PointCloudEngine | null>(null);
  const sceneRef = useRef<LidarScene | null>(null);

  const [runId, setRunId] = useState(0);
  const [loading, setLoading] = useState<0 | 1 | 2>(0); // 0 scene, 1 points, 2 ready
  const [progress, setProgress] = useState<{ loaded: number; total: number; decoded: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scene, setScene] = useState<LidarScene | null>(null);
  const [cloud, setCloud] = useState<DecodedPointCloud | null>(null);

  const [colorMode, setColorMode] = useState<ColorMode>('rgb');
  const [pointSize, setPointSize] = useState(2.4);
  const [glow, setGlow] = useState(0.4);
  const [pointShape, setPointShape] = useState<PointShape>('splat');
  const [edlStrength] = useState(0.75);
  const [quality, setQuality] = useState<QualityMode>('auto');
  const [visibleClasses, setVisibleClasses] = useState<Set<number> | null>(null);
  const [layers, setLayers] = useState<LayerVisibility>({ lidar: true, parcels: true, footprint: true, model: false, grid: false });
  const [modelOpacity, setModelOpacity] = useState(0.5);

  const [selection, setSelection] = useState<LidarSelection | null>(null);
  const [focusParcel, setFocusParcel] = useState(false);
  const [isolateBuilding, setIsolateBuilding] = useState(false);
  const [floorLevel, setFloorLevel] = useState<LidarLevel | null>(null);
  const [sliceBand, setSliceBand] = useState<{ min: number; max: number; mode: 'dim' | 'hide' } | null>(null);
  const [vSliceX, setVSliceX] = useState<number | null>(null);
  const [clipOn, setClipOn] = useState(false);

  const [tool, setTool] = useState<Tool>('select');
  const [drawer, setDrawer] = useState<'property' | 'layers' | 'appearance' | 'slice' | 'measure' | null>(null);
  const [hover, setHover] = useState<InspectInfo | null>(null);
  const [status, setStatus] = useState<EngineStatus>({ fps: 0, rendered: 0, memoryMB: 0 });
  const [measureReads, setMeasureReads] = useState<MeasureRead[]>([]);
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchCategory, setSearchCategory] = useState<'all' | 'towers' | 'commercial' | 'flagged'>('all');
  const searchContainerRef = useRef<HTMLDivElement>(null);

  const allSelectableBuildings = useMemo(() => {
    if (!scene?.ground_truth) return [];
    const gt = scene.ground_truth;
    const heroItem = {
      code: gt.building_code || 'B-17',
      name: gt.building_name || 'Shree Ganesh CHS (Building B-17)',
      ulpin: gt.ulpin,
      type: 'tower',
      floors: gt.floors_count || 5,
      height_m: gt.height_m || 18,
      status: 'APPROVED',
      risk_level: 'LOW',
      isHero: true,
    };
    const surroundingItems = ((gt.surrounding_parcels as any[]) || []).map((p) => ({
      code: p.building_code || p.survey_number || p.ulpin,
      name: p.building_name || `Building ${p.building_code || p.survey_number}`,
      ulpin: p.ulpin || p.survey_number,
      type: p.type || 'tower',
      floors: p.floors_count || 4,
      height_m: p.height_m || 14,
      status: p.status || 'APPROVED',
      risk_level: p.risk_level || 'LOW',
      isHero: false,
    }));
    return [heroItem, ...surroundingItems];
  }, [scene]);

  const filteredBuildings = useMemo(() => {
    let list = allSelectableBuildings;
    if (searchCategory === 'towers') list = list.filter((b) => b.type === 'tower');
    if (searchCategory === 'commercial') list = list.filter((b) => b.type === 'commercial');
    if (searchCategory === 'flagged')
      list = list.filter(
        (b) => b.status === 'DEMO_ELEVATED_FSI' || b.status === 'DEMO_EPOCH_COMPARISON'
      );

    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter(
      (b) =>
        b.code.toLowerCase().includes(q) ||
        b.name.toLowerCase().includes(q) ||
        b.ulpin.toLowerCase().includes(q) ||
        b.type.toLowerCase().includes(q) ||
        b.status.toLowerCase().includes(q)
    );
  }, [allSelectableBuildings, search, searchCategory]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener('pointerdown', handleClickOutside);
    return () => document.removeEventListener('pointerdown', handleClickOutside);
  }, []);

  const classCounts = useMemo(() => {
    if (!scene) return new Map<number, number>();
    return new Map(scene.stats.classifications.map((c) => [c.code, c.count]));
  }, [scene]);

  const zBounds = useMemo(() => {
    const b = scene?.stats.bounds;
    return { min: b ? b.min[2] : -4, max: b ? b.max[2] : 18 };
  }, [scene]);

  const hero = useMemo(() => scene?.ground_truth ?? null, [scene]);

  /* ---------- build a LidarSelection from query (code, ulpin, or name) ---------- */
  const buildSelection = useCallback(
    (query: string): LidarSelection | null => {
      const gt = sceneRef.current?.ground_truth;
      if (!gt) return null;
      const q = query.trim().toUpperCase();
      if (
        q === gt.ulpin.toUpperCase() ||
        q === (gt.building_code || '').toUpperCase() ||
        (gt.building_name && gt.building_name.toUpperCase().includes(q))
      ) {
        return {
          ulpin: gt.ulpin,
          label: gt.building_name || gt.building_code,
          buildingCode: gt.building_code,
          buildingName: gt.building_name,
          // No fabricated 3D ID and no invented unit count. The old fallback
          // pointed every ground truth without a proposed ID at
          // 12345678901234/UB17-G-001-A, a real cadastral parcel, and reported
          // 21 units for any building whose unit list was simply absent.
          proposed_3d_id: gt.proposed_3d_id,
          units: gt.units || [],
          units_count: gt.units_count ?? (gt.units ? gt.units.length : undefined),
          parcelRing: gt.parcel_ring,
          footprint: gt.footprint,
          levels: gt.levels,
          heightM: gt.height_m,
        };
      }
      const p = (gt.surrounding_parcels as any[]).find((s) => {
        const u = (s.ulpin || '').toUpperCase();
        const sn = (s.survey_number || '').toUpperCase();
        const bc = (s.building_code || '').toUpperCase();
        const bn = (s.building_name || '').toUpperCase();
        return u === q || sn === q || bc === q || (q.length >= 3 && bn.includes(q));
      });
      if (p) {
        return {
          ulpin: p.ulpin || p.survey_number || query,
          label: p.building_name || p.survey_number || p.ulpin || query,
          buildingCode: p.building_code || p.survey_number,
          buildingName: p.building_name,
          proposed_3d_id: p.proposed_3d_id,
          units: p.units || [],
          units_count: p.units_count ?? (p.units ? p.units.length : 0),
          parcelRing: p.ring,
          footprint: p.footprint || [],
          levels: p.levels || [],
          heightM: p.height_m || 0,
        };
      }
      return null;
    },
    []
  );

  /* ---------- push UI state into engine ---------- */
  const pushEngineState = useCallback(
    (sel = selection, focus = focusParcel, isolate = isolateBuilding, floor = floorLevel, vsx = vSliceX) => {
      const eng = engineRef.current;
      if (!eng || !cloud) return;
      eng.setColorMode(colorMode);
      eng.setPointSize(pointSize);
      eng.setGlow(glow);
      eng.setVisibleClasses(visibleClasses);
      eng.setPointShape(pointShape);
      eng.setEdlStrength(edlStrength);
      eng.setLayers(layers);
      eng.setModelOpacity(modelOpacity);
      eng.setSliceBand(sliceBand);
      eng.setClipBox(clipOn && sel && sel.parcelRing.length ? boxFromSelection(sel, zBounds) : null);
      eng.setFloorMarks(floor);
      eng.setVerticalGuide(vsx, 1.2);
      const opts: ColorModeOptions = {
        selection: sel,
        focusParcel: focus,
        isolateBuilding: isolate,
        floorLevel: floor,
        vSlice: vsx == null ? null : { x: vsx, width: 1.2 },
      };
      eng.setColorModeOptions(opts);
      eng.setActiveTool(tool === 'measure' ? 'measure' : 'select');
    },
    [cloud, colorMode, pointSize, glow, pointShape, edlStrength, visibleClasses, layers, modelOpacity, sliceBand, clipOn, zBounds, tool]
  );

  /* ---------- load scene + points, create engine ---------- */
  useEffect(() => {
    let cancelled = false;
    const ac = new AbortController();
    setLoading(0);
    setError(null);
    setProgress(null);

    fetchLidarScene()
      .then((scn) => {
        if (cancelled) return;
        sceneRef.current = scn;
        setScene(scn);
        setVisibleClasses(new Set(scn.stats.classifications.filter((c) => c.present).map((c) => c.code)));
        setLoading(1);

        const eng = new PointCloudEngine(
          canvasRef.current!,
          labelLayerRef.current!,
          scn,
          {
            onSelectProperty: (ulpin) => applySelection(buildSelection(ulpin)),
            onInspectPoint: (info) => handleHover(info),
            onStatus: (s) => {
              if (!cancelled) setStatus(s);
            },
            onMeasure: (reads) => {
              if (!cancelled) setMeasureReads(reads);
            },
          }
        );
        engineRef.current = eng;
        syncHeroLabels(scn);

        return fetchLidarPoints({
          query: { step: QUALITY_STEP.high },
          signal: ac.signal,
          onProgress: (loaded, total, decoded) => {
            if (!cancelled) setProgress({ loaded, total, decoded });
          },
        }).then((cl) => {
          if (cancelled) return;
          setCloud(cl);
          eng.loadPointCloud(cl);
          setLoading(2);
          eng.cameraPreset('fit');
          const focusUlpin = initialULPIN || (autoFocusSelection ? scn.ground_truth.ulpin : null);
          pushEngineState(focusUlpin ? buildSelection(focusUlpin) : null, true, false, null, null);
          if (focusUlpin) {
            const sel = buildSelection(focusUlpin);
            if (sel) {
              setSelection(sel);
              setFocusParcel(true);
              if (sel.levels.length) {
                eng.cameraPreset('building');
              }
            }
          }
        });
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || String(e));
      });

    return () => {
      cancelled = true;
      ac.abort();
      const eng = engineRef.current;
      engineRef.current = null;
      if (eng) eng.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  function syncHeroLabels(scn: LidarScene) {
    const gt = scn.ground_truth;
    const cx = (gt.parcel_ring.reduce((s, p) => s + p[0], 0) / gt.parcel_ring.length);
    const cy = (gt.parcel_ring.reduce((s, p) => s + p[1], 0) / gt.parcel_ring.length);
    engineRef.current?.syncPropertyLabels([
      { text: gt.building_name || gt.building_code, pos: [cx, cy, Math.max(gt.height_m + 1.2, 4)] },
      { text: `ULPIN ${gt.ulpin}`, pos: [cx, cy, Math.max(gt.height_m + 3.4, 6)] },
    ]);
  }

  function handleHover(info: InspectInfo | null) {
    setHover((prev) => {
      if (!info) return null;
      const k = `${fmt(info.x, 3)}|${fmt(info.y, 3)}|${fmt(info.z, 3)}|${info.intensity}`;
      if (prev && prev.x === info.x && prev.y === info.y && prev.z === info.z && prev.intensity === info.intensity && k) return prev;
      return info;
    });
  }

  /* ---------- apply a selection (from engine click or ULPIN list) ---------- */
  const applySelection = useCallback(
    (sel: LidarSelection | null) => {
      setSelection(sel);
      setFocusParcel(!!sel);
      setIsolateBuilding(false);
      setFloorLevel(null);
      if (sel) {
        setDrawer('property');
        syncUserLabels(sel);
        pushEngineState(sel, true, false, null, vSliceX);
        engineRef.current?.focusBuilding(sel);
      } else {
        pushEngineState(null, false, false, null, vSliceX);
        engineRef.current?.cameraPreset('fit');
      }
    },
    [pushEngineState, vSliceX]
  );

  const cycleBuilding = useCallback((dir: 1 | -1) => {
    if (!allSelectableBuildings.length) return;
    const currentCode = selection?.buildingCode || selection?.ulpin;
    const idx = allSelectableBuildings.findIndex((b) => b.code === currentCode || b.ulpin === currentCode);
    const nextIdx = (idx + dir + allSelectableBuildings.length) % allSelectableBuildings.length;
    const target = allSelectableBuildings[nextIdx];
    const sel = buildSelection(target.code || target.ulpin);
    if (sel) {
      applySelection(sel);
    }
  }, [allSelectableBuildings, selection, buildSelection, applySelection]);

  function syncUserLabels(sel: LidarSelection) {
    const eng = engineRef.current;
    if (!eng) return;
    const pts = sel.parcelRing;
    if (!pts.length) return;
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    const top = sel.levels.length ? Math.max(sel.heightM + 1.2, 4) : 3;
    eng.syncPropertyLabels([
      { text: sel.label || sel.ulpin, pos: [cx, cy, top] },
      { text: `ULPIN ${sel.ulpin}`, pos: [cx, cy, top + 1.8] },
    ]);
  }

  /* ---------- engine state effects (after ready) ---------- */
  useEffect(() => {
    if (loading === 2 && engineRef.current && cloud) {
      pushEngineState();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, cloud]);

  useEffect(() => {
    if (selection) syncUserLabels(selection);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection]);

  useEffect(() => {
    if (loading === 2) pushEngineState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colorMode, pointSize, glow, visibleClasses, layers, modelOpacity, sliceBand, clipOn, floorLevel, vSliceX, focusParcel, isolateBuilding, selection, tool]);

  /* ---------- quality: auto drives step from camera distance ---------- */
  useEffect(() => {
    const eng = engineRef.current;
    if (!eng || loading !== 2) return;
    if (quality === 'auto') {
      const apply = () => {
        const e = engineRef.current;
        if (!e) return;
        const d = e.getCameraDistance ? e.getCameraDistance() : 90;
        const step = Math.max(1, Math.min(6, Math.round(d / 45)));
        e.setQuality(step);
      };
      apply();
      const id = window.setInterval(apply, 800);
      return () => clearInterval(id);
    }
    eng.setQuality(QUALITY_STEP[quality]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quality, loading]);

  /* ---------- keyboard shortcuts ---------- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
      const eng = engineRef.current;
      const k = e.key.toLowerCase();
      const mode = COLOR_MODES.find((m) => m.key === e.key);
      if (mode) {
        setColorMode(mode.id);
        return;
      }
      switch (k) {
        case 'm':
          setTool('measure');
          setDrawer('measure');
          setActiveToolState('measure');
          break;
        case 's':
          setTool('slice');
          setDrawer('slice');
          break;
        case 'l':
          setDrawer((d) => (d === 'layers' ? null : 'layers'));
          break;
        case 'p':
          setDrawer((d) => (d === 'appearance' ? null : 'appearance'));
          break;
        case 'f':
          eng?.cameraPreset('fit');
          break;
        case 't':
          eng?.cameraPreset('top');
          break;
        case 'e':
          setDrawer((d) => (d === 'slice' ? null : 'slice'));
          break;
        case 'escape':
          setDrawer(null);
          setTool('select');
          setActiveToolState('select');
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setActiveToolState(t: 'select' | 'measure' | 'slice' | 'clip') {
    engineRef.current?.setActiveTool(t === 'measure' ? 'measure' : 'select');
  }

  const selectTool = (t: Tool) => {
    setTool(t);
    if (t === 'measure') {
      setDrawer('measure');
      setActiveToolState('measure');
    } else if (t === 'slice') {
      setDrawer('slice');
      setActiveToolState('select');
    } else if (t === 'clip') {
      setClipOn(true);
      setDrawer('slice');
      setActiveToolState('select');
    } else {
      setDrawer(null);
      setActiveToolState('select');
    }
  };

  const resetAll = useCallback(() => {
    setSelection(null);
    setFocusParcel(false);
    setIsolateBuilding(false);
    setFloorLevel(null);
    setSliceBand(null);
    setVSliceX(null);
    setClipOn(false);
    setDrawer(null);
    setTool('select');
    setActiveToolState('select');
    setColorMode('elevation');
    setPointSize(2.2);
    setGlow(0.35);
    setQuality('auto');
    setLayers({ lidar: true, parcels: true, footprint: true, model: false, grid: false });
    setModelOpacity(0.5);
    setMeasureReads([]);
    if (hero) syncHeroLabels(scene!);
    engineRef.current?.cameraPreset('fit');
  }, [hero, scene]);

  const tryAgain = () => {
    sceneRef.current = null;
    setLoading(0);
    setProgress(null);
    setCloud(null);
    setError(null);
    setRunId((r) => r + 1);
  };

  const navigateProperty = useCallback(
    (ulpin: string) => {
      if (onNavigateProperty) onNavigateProperty(ulpin);
      else window.history.pushState(null, '', `/app/properties/${ulpin}`);
    },
    [onNavigateProperty]
  );

  const stats = scene?.stats;
  const density = stats?.density_pts_m2;

  return (
    <div className={`lidar-insp${className ? ' ' + className : ''}`} role="region" aria-label="LiDAR property inspector">
      <div className="lidar-insp__canvas" ref={canvasRef} />
      <div className="lidar-insp__labels" ref={labelLayerRef} />

      {/* ---------- UI overlay ---------- */}
      <div className="lidar-insp__ui" style={loading === 2 ? undefined : { pointerEvents: 'none' }}>
        {/* top chrome */}
        <div className="li-topbar flex-wrap gap-2">
          <div className="li-brand li-panel">
            <div className="li-brand__mark">BD</div>
            <div>
              <div className="li-brand__name">BHU-DRISHTI</div>
              <div className="li-brand__sub">LIDAR 3D CLOUD</div>
            </div>
            <span className="li-chip">Airoli S8</span>
          </div>

          {/* Building Selector Dropdown & Search */}
          <div className="relative" ref={searchContainerRef} style={{ zIndex: 60 }}>
            <div className="li-search" style={{ minWidth: 280, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Building2 size={15} className="text-[#06b6d4] shrink-0" />
              <input
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setSearchOpen(true);
                }}
                onFocus={() => setSearchOpen(true)}
                placeholder={selection ? `${selection.buildingCode || ''} ${selection.buildingName || selection.label}` : 'Select or search building (13 total)…'}
                aria-label="Search building or area"
                enterKeyHint="search"
                style={{ flex: 1, minWidth: 0, fontWeight: selection ? 600 : 400 }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && search.trim()) {
                    const sel = buildSelection(search.trim());
                    if (sel) {
                      applySelection(sel);
                      setSearch('');
                      setSearchOpen(false);
                    }
                  } else if (e.key === 'Escape') {
                    setSearchOpen(false);
                  }
                }}
              />
              {search ? (
                <button
                  className="li-icon-close"
                  onClick={() => {
                    setSearch('');
                    setSearchOpen(false);
                  }}
                  aria-label="Clear search"
                  style={{ background: 'transparent' }}
                >
                  <X size={13} />
                </button>
              ) : (
                <button
                  className="li-icon-close"
                  onClick={() => setSearchOpen(!searchOpen)}
                  style={{ background: 'transparent' }}
                  aria-label="Toggle buildings dropdown"
                >
                  <ChevronDown size={14} className="text-white/70" />
                </button>
              )}
            </div>

            {/* Area & Building Dropdown Menu */}
            {searchOpen && (
              <div
                className="absolute top-full left-0 mt-2 w-96 max-h-80 overflow-y-auto bg-slate-950/95 border border-white/15 rounded-xl shadow-2xl backdrop-blur-xl p-2 z-50 text-white flex flex-col gap-1.5 animate-rise-in font-mono text-xs"
                style={{ scrollbarWidth: 'thin' }}
              >
                <div className="flex items-center justify-between px-2 pt-1 pb-1.5 border-b border-white/10 text-[10px] text-white/50 uppercase tracking-wider font-bold">
                  <span>Precinct Buildings ({filteredBuildings.length})</span>
                  <div className="flex gap-1">
                    {(['all', 'towers', 'commercial', 'flagged'] as const).map((cat) => (
                      <button
                        key={cat}
                        onClick={() => setSearchCategory(cat)}
                        className={`px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider transition-colors ${
                          searchCategory === cat ? 'bg-[#06b6d4]/20 text-[#06b6d4] font-bold' : 'text-white/40 hover:text-white/80'
                        }`}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex flex-col gap-1 overflow-y-auto max-h-64">
                  {filteredBuildings.map((b) => {
                    const isSelected = selection?.buildingCode === b.code || selection?.ulpin === b.ulpin;
                    const statusColor =
                      b.status === 'DEMO_STANDARD'
                        ? 'text-emerald-400 bg-emerald-950/40 border-emerald-500/30'
                        : b.status === 'DEMO_ELEVATED_FSI'
                        ? 'text-rose-400 bg-rose-950/40 border-rose-500/30'
                        : 'text-amber-400 bg-amber-950/40 border-amber-500/30';

                    return (
                      <button
                        key={b.code}
                        onClick={() => {
                          const sel = buildSelection(b.code);
                          if (sel) {
                            applySelection(sel);
                            setSearch('');
                            setSearchOpen(false);
                          }
                        }}
                        className={`flex items-center justify-between p-2 rounded-lg text-left transition-colors border ${
                          isSelected
                            ? 'bg-[#06b6d4]/15 border-[#06b6d4]/50 text-white shadow-sm'
                            : 'bg-white/5 border-transparent hover:bg-white/10 text-white/80 hover:text-white'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <span
                            className={`w-6 h-6 rounded flex items-center justify-center font-bold text-[10px] shrink-0 ${
                              b.isHero ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40' : 'bg-white/10 text-white/70'
                            }`}
                          >
                            {b.code}
                          </span>
                          <div className="flex flex-col truncate">
                            <span className="font-bold text-xs truncate flex items-center gap-1.5">
                              {b.name}
                              {b.isHero && <span className="text-[9px] px-1 py-0.2 bg-amber-500/20 text-amber-300 rounded font-normal">HERO</span>}
                            </span>
                            <span className="text-[10px] text-white/50">
                              {b.type.toUpperCase()} · {b.floors} Floors · {b.height_m}m
                            </span>
                          </div>
                        </div>

                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border uppercase tracking-wider shrink-0 ${statusColor}`}>
                          {b.status}
                        </span>
                      </button>
                    );
                  })}
                  {filteredBuildings.length === 0 && (
                    <div className="p-4 text-center text-xs text-white/40">
                      No building matching "{search}"
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Quick cycle buttons */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => cycleBuilding(-1)}
              title="Previous Building [key: [ ]"
              className="li-icon-close li-panel"
              style={{ width: 34, height: 34, color: 'rgba(255,255,255,0.7)' }}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              onClick={() => cycleBuilding(1)}
              title="Next Building [key: ] ]"
              className="li-icon-close li-panel"
              style={{ width: 34, height: 34, color: 'rgba(255,255,255,0.7)' }}
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {/* Quick Action Pills: Focus, Isolate, All */}
          <div className="flex items-center gap-1 li-panel px-1.5 py-1" style={{ height: 34 }}>
            <button
              onClick={() => {
                if (selection) {
                  setFocusParcel(true);
                  setIsolateBuilding(false);
                  pushEngineState(selection, true, false, floorLevel, vSliceX);
                  engineRef.current?.focusBuilding(selection);
                }
              }}
              disabled={!selection}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold flex items-center gap-1 transition-colors ${
                focusParcel && !isolateBuilding
                  ? 'bg-[#06b6d4] text-black shadow-sm'
                  : 'text-white/70 hover:text-white hover:bg-white/10'
              } disabled:opacity-30`}
              title="Focus and zoom directly into selected building"
            >
              <Focus size={12} />
              <span>Focus</span>
            </button>

            <button
              onClick={() => {
                if (selection) {
                  const nextIsolate = !isolateBuilding;
                  setIsolateBuilding(nextIsolate);
                  setFocusParcel(true);
                  pushEngineState(selection, true, nextIsolate, floorLevel, vSliceX);
                }
              }}
              disabled={!selection}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold flex items-center gap-1 transition-colors ${
                isolateBuilding
                  ? 'bg-amber-400 text-black shadow-sm font-black'
                  : 'text-white/70 hover:text-white hover:bg-white/10'
              } disabled:opacity-30`}
              title="Isolate only this building's point cloud alone (culls all other points)"
            >
              <Building2 size={12} />
              <span>{isolateBuilding ? 'Isolated' : 'Isolate'}</span>
            </button>

            <button
              onClick={() => {
                setSelection(null);
                setFocusParcel(false);
                setIsolateBuilding(false);
                setFloorLevel(null);
                pushEngineState(null, false, false, null, null);
                engineRef.current?.cameraPreset('fit');
              }}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold flex items-center gap-1 transition-colors ${
                !selection && !isolateBuilding
                  ? 'bg-white/20 text-white'
                  : 'text-white/70 hover:text-white hover:bg-white/10'
              }`}
              title="Show entire precinct point cloud"
            >
              <Maximize size={12} />
              <span>All</span>
            </button>

            <div className="w-[1px] h-3.5 bg-white/15 mx-0.5" />

            {/* Vertical-change (delta) control. Disabled unless the capture really
                holds more than one epoch: a delta needs two dated passes over the
                same scene, and this dataset has a single one. Keeping the button
                live while the delta is unavailable is what let a flat grey wash be
                read as an alert, so it states the reason instead. */}
            <button
              onClick={() => {
                if (!scene?.dataset?.multi_epoch) return;
                const nextMode = colorMode === 'epoch2_delta' ? 'rgb' : 'epoch2_delta';
                setColorMode(nextMode);
              }}
              disabled={!scene?.dataset?.multi_epoch}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold flex items-center gap-1 transition-colors ${
                !scene?.dataset?.multi_epoch
                  ? 'text-white/30 cursor-not-allowed'
                  : colorMode === 'epoch2_delta'
                  ? 'bg-rose-600 text-white shadow-lg animate-pulse'
                  : 'text-white/70 hover:text-white hover:bg-white/10'
              }`}
              title={
                scene?.dataset?.multi_epoch
                  ? 'Highlight points present only in a later survey epoch'
                  : 'No second survey epoch: vertical change cannot be measured from a single pass'
              }
            >
              <span>Epoch-2:</span>
              <span>{scene?.dataset?.multi_epoch ? 'available' : 'unavailable'}</span>
            </button>

            {/* Point Shader Mode Switcher */}
            <button
              onClick={() => {
                const nextShape: PointShape = pointShape === 'splat' ? 'disc' : pointShape === 'disc' ? 'voxel' : 'splat';
                setPointShape(nextShape);
                engineRef.current?.setPointShape(nextShape);
              }}
              className="px-2 py-1 rounded-md text-[11px] font-mono text-[#38bdf8] hover:bg-white/10 flex items-center gap-1 transition-colors"
              title="Toggle Point Shader: 3D Splat (EDL), Clean Disc, or Square Voxel"
            >
              <span>{pointShape === 'splat' ? '3D Splat' : pointShape === 'disc' ? 'Disc' : 'Voxel'}</span>
            </button>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
            <div className="li-property-chip li-panel">
              <span className="li-property-chip__label">Selected</span>
              <span className="li-property-chip__value font-bold text-[#38bdf8]">
                {selection ? (selection.buildingCode ? `${selection.buildingCode} · ${selection.buildingName || selection.label}` : selection.label) : 'Airoli S8 Precinct'}
              </span>
            </div>
            {onClose && (
              <button className="li-icon-close li-panel" onClick={onClose} aria-label="Close inspection" style={{ width: 34, height: 34 }}>
                <X size={16} />
              </button>
            )}
          </div>
        </div>

        {/* Quick Floor Strip (when building with levels is selected) */}
        {selection && selection.levels && selection.levels.length > 0 && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1 li-panel px-3 py-1.5 rounded-full shadow-xl border border-white/15 bg-slate-950/90 backdrop-blur-md animate-rise-in">
            <span className="text-[10px] font-mono font-bold text-white/50 uppercase tracking-wider mr-1">Floor:</span>
            {selection.levels.map((lv) => {
              const isSelected = floorLevel?.level_code === lv.level_code;
              return (
                <button
                  key={lv.level_code}
                  onClick={() => {
                    const next = isSelected ? null : lv;
                    setFloorLevel(next);
                    const band = next ? { min: next.min_z, max: next.max_z, mode: 'dim' as const } : null;
                    setSliceBand(band);
                    pushEngineState(selection, focusParcel, isolateBuilding, next, vSliceX);
                    if (next) engineRef.current?.cameraPreset('floor');
                  }}
                  className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold transition-all ${
                    isSelected
                      ? 'bg-[#06b6d4] text-black shadow-md scale-105'
                      : 'bg-white/10 hover:bg-white/20 text-white/80'
                  }`}
                  title={`${lv.name || lv.level_code} (${fmt(lv.min_z, 1)}m - ${fmt(lv.max_z, 1)}m)`}
                >
                  {lv.level_code}
                </button>
              );
            })}
            {floorLevel && (
              <button
                onClick={() => {
                  setFloorLevel(null);
                  setSliceBand(null);
                  pushEngineState(selection, focusParcel, isolateBuilding, null, vSliceX);
                }}
                className="ml-1 p-1 rounded-full hover:bg-white/20 text-white/60 hover:text-white"
                title="Clear floor slice"
              >
                <X size={11} />
              </button>
            )}
          </div>
        )}

{/* The red "Epoch-2 detected unauthorized 6th floor (+3.5m above sanctioned
            18.0m)" banner used to sit here for B-17/B-03/B-12. Every number in it was
            manufactured: the backend was appending a generated 18.0-21.5 m slab band
            to the uploaded LAS to be detected, the capture is single-pass so no delta
            exists, and the dataset's own ground truth stops at L04 / 18.0 m - there is
            no sanctioned 18.0 m ceiling to exceed and no 6th floor in the file. A
            single-pass cloud cannot establish when anything was built, so change
            detection belongs to a dated multi-epoch survey, not this dataset. */}

        {/* left tool rail */}
        <div className="li-rail li-panel" role="toolbar" aria-label="Inspection tools">
          <IconBtn
            active={tool === 'select'}
            title="Select property"
            kbd="Esc"
            onClick={() => selectTool('select')}
            icon={<MousePointer2 size={17} />}
          />
          <IconBtn active={tool === 'measure'} title="Measure distance / height" kbd="M" onClick={() => selectTool('measure')} icon={<Ruler size={17} />} />
          <IconBtn active={tool === 'slice'} title="Floor / horizontal slice" kbd="S" onClick={() => selectTool('slice')} icon={<Slice size={17} />} />
          <IconBtn active={clipOn} title="Height clip box" kbd="C" onClick={() => selectTool('clip')} icon={<Box size={17} />} />
          <div className="li-rail__sep" />
          <IconBtn active={drawer === 'layers'} title="Layers" kbd="L" onClick={() => setDrawer((d) => (d === 'layers' ? null : 'layers'))} icon={<Layers size={17} />} />
          <IconBtn active={drawer === 'appearance'} title="Appearance" kbd="P" onClick={() => setDrawer((d) => (d === 'appearance' ? null : 'appearance'))} icon={<Palette size={17} />} />
          <div className="li-rail__sep" />
          <IconBtn title="Fit view" kbd="F" onClick={() => engineRef.current?.cameraPreset('fit')} icon={<Maximize size={17} />} />
          <IconBtn title="Top view" kbd="T" onClick={() => engineRef.current?.cameraPreset('top')} icon={<Scan size={17} />} />
          <div className="li-rail__sep" />
          <IconBtn title="Reset instrument" onClick={resetAll} icon={<RotateCcw size={17} />} />
        </div>

        {/* legend */}
        {loading === 2 && <Legend mode={colorMode} classCounts={classCounts} />}

        {/* property drawer */}
        {drawer === 'property' && selection && (
          <div className="li-drawer li-panel" role="dialog" aria-label="Property">
            <PropertyDrawer
              selection={selection}
              focusParcel={focusParcel}
              isolateBuilding={isolateBuilding}
              onToggleFocus={() => setFocusParcel(!focusParcel)}
              onToggleIsolate={() => setIsolateBuilding(!isolateBuilding)}
              onFloor={(lvl) => {
                setFloorLevel(lvl === floorLevel ? null : lvl);
                if (lvl && lvl !== floorLevel) {
                  engineRef.current?.cameraPreset('floor');
                }
              }}
              floorLevel={floorLevel}
              onOpenMap={() => navigateProperty(selection.ulpin)}
            />
          </div>
        )}

        {/* layers drawer */}
        {drawer === 'layers' && (
          <div className="li-drawer li-panel" role="dialog" aria-label="Layers">
            <DrawerHead title="Layers" onClose={() => setDrawer(null)} />
            <div className="li-drawer__body">
              <LayerToggle label="LiDAR points" on={layers.lidar} onChange={() => setLayers((l) => ({ ...l, lidar: !l.lidar }))} hint={stats ? fmt(stats.point_count, 0) + ' pts' : undefined} />
              <LayerToggle label="Parcel boundary" on={layers.parcels} onChange={() => setLayers((l) => ({ ...l, parcels: !l.parcels }))} />
              <LayerToggle label="Building footprint" on={layers.footprint} onChange={() => setLayers((l) => ({ ...l, footprint: !l.footprint }))} />
              <LayerToggle label="Reconstruction model" on={layers.model} onChange={() => setLayers((l) => ({ ...l, model: !l.model }))} />
              <LayerToggle label="Ground grid" on={layers.grid} onChange={() => setLayers((l) => ({ ...l, grid: !l.grid }))} />
              {layers.model && (
                <SliderRow
                  label="Model opacity"
                  min={5}
                  max={100}
                  value={modelOpacity * 100}
                  display={pct(modelOpacity)}
                  onChange={(v) => setModelOpacity(v / 100)}
                />
              )}
            </div>
          </div>
        )}

        {/* appearance drawer */}
        {drawer === 'appearance' && (
          <div className="li-drawer li-panel" role="dialog" aria-label="Appearance">
            <DrawerHead title="Appearance" onClose={() => setDrawer(null)} />
            <div className="li-drawer__body">
              <div className="li-tiny">Color mode</div>
              <div className="li-seg" style={{ flexWrap: 'wrap' }}>
                {COLOR_MODES.map((m) => (
                  <button
                    key={m.id}
                    className={`li-btn ${colorMode === m.id ? 'li-btn--active' : ''}`}
                    style={{ flex: '0 0 31%' }}
                    onClick={() => setColorMode(m.id)}
                    title={`${m.label} (key ${m.key})`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              <div className="li-divider" />
              <SliderRow label="Point size" min={6} max={60} value={pointSize * 10} display={fmt(pointSize, 1)} onChange={(v) => setPointSize(v / 10)} />
              <SliderRow label="Glow" min={0} max={100} value={glow * 100} display={pct(glow)} onChange={(v) => setGlow(v / 100)} />
              <div className="li-tiny">Quality</div>
              <div className="li-seg">
                {(['low', 'medium', 'high', 'auto'] as QualityMode[]).map((q) => (
                  <button
                    key={q}
                    className={`li-btn ${quality === q ? 'li-btn--active' : ''}`}
                    onClick={() => setQuality(q)}
                  >
                    {q === 'auto' ? 'Auto' : q}
                  </button>
                ))}
              </div>
              <div className="li-divider" />
              <div className="li-tiny">Visible classes</div>
              {scene?.stats.classifications.filter((c) => c.present).map((c) => (
                <LayerToggle
                  key={c.code}
                  label={`${CLASS_LABELS[c.code] || c.name} · ${fmt(c.count, 0)}`}
                  on={(visibleClasses ?? new Set()).has(c.code)}
                  onChange={() =>
                    setVisibleClasses((prev) => {
                      const next = new Set(prev ?? scene.stats.classifications.filter((x) => x.present).map((x) => x.code));
                      if (next.has(c.code)) next.delete(c.code);
                      else next.add(c.code);
                      return next;
                    })
                  }
                  swatch={CLASS_COLORS[c.code]}
                />
              ))}
            </div>
          </div>
        )}

        {/* slice drawer */}
        {drawer === 'slice' && (
          <div className="li-drawer li-panel" role="dialog" aria-label="Slice and clip">
            <DrawerHead title="Slice & Clip" onClose={() => setDrawer(null)} />
            <div className="li-drawer__body">
              <div className="li-tiny">Horizontal slice</div>
              <div className="li-seg">
                {(['dim', 'hide'] as const).map((m) => (
                  <button
                    key={m}
                    className={`li-btn ${sliceBand?.mode === m ? 'li-btn--active' : ''}`}
                    onClick={() =>
                      setSliceBand(
                        sliceBand
                          ? { min: sliceBand.min, max: sliceBand.max, mode: m }
                          : { min: zBounds.min, max: zBounds.max, mode: m }
                      )
                    }
                  >
                    {m === 'dim' ? 'Dim' : 'Hide'}
                  </button>
                ))}
                <button
                  className={`li-btn ${!sliceBand ? 'li-btn--active' : ''}`}
                  onClick={() => setSliceBand(null)}
                >
                  Off
                </button>
              </div>
              {sliceBand && (
                <div className="li-slider-row" style={{ gap: 8 }}>
                  <SliderRow
                    label="Lower elevation"
                    min={Math.round(zBounds.min * 10)}
                    max={Math.round(zBounds.max * 10)}
                    value={Math.round(sliceBand.min * 10)}
                    display={`${fmt(sliceBand.min, 1)} m`}
                    onChange={(v) => setSliceBand({ min: v / 10, max: sliceBand.max, mode: sliceBand.mode })}
                  />
                  <SliderRow
                    label="Upper elevation"
                    min={Math.round(zBounds.min * 10)}
                    max={Math.round(zBounds.max * 10)}
                    value={Math.round(sliceBand.max * 10)}
                    display={`${fmt(sliceBand.max, 1)} m`}
                    onChange={(v) => setSliceBand({ min: Math.min(sliceBand.min, v / 10), max: v / 10, mode: sliceBand.mode })}
                  />
                </div>
              )}

              {(selection?.levels.length || 0) > 0 && (
                <>
                  <div className="li-tiny">Floor snap</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selection!.levels.map((lv) => (
                      <button
                        key={lv.level_code}
                        className={`li-btn ${floorLevel?.level_code === lv.level_code ? 'li-btn--active' : ''}`}
                        onClick={() => {
                          const next = floorLevel?.level_code === lv.level_code ? null : lv;
                          setFloorLevel(next);
                          const band = next
                            ? { min: next.min_z, max: next.max_z, mode: 'dim' as const }
                            : sliceBand;
                          setSliceBand(band);
                          engineRef.current?.cameraPreset('floor');
                        }}
                      >
                        {lv.name || lv.level_code}
                      </button>
                    ))}
                    {floorLevel && (
                      <button className="li-btn" onClick={() => { setFloorLevel(null); setSliceBand(sliceBand && sliceBand.mode ? { ...sliceBand, mode: sliceBand.mode } : sliceBand); }}>
                        <X size={12} /> Clear
                      </button>
                    )}
                  </div>
                </>
              )}

              <div className="li-divider" />

              <div className="li-tiny">Vertical slice (E–W guide)</div>
              <SliderRow
                label="Slice X"
                min={118}
                max={200}
                value={vSliceX ?? 140}
                display={vSliceX == null ? 'off' : `${fmt(vSliceX, 1)} m`}
                onChange={(v) => setVSliceX((prev) => (prev == null && v === 140 ? 140 : v))}
              />
              <button className={`li-action ${vSliceX == null ? 'li-action--accent' : ''}`} onClick={() => setVSliceX(null)}>
                <Check size={13} /> {vSliceX == null ? 'Vertical guide off' : 'Turn guide off'}
              </button>

              <div className="li-divider" />

              <div className="li-tiny">Height clip box</div>
              <div className="li-seg" style={{ gap: 6 }}>
                <button className={`li-btn ${clipOn ? 'li-btn--active' : ''}`} onClick={() => setClipOn(true)}>
                  <Box size={12} /> Clip on
                </button>
                <button className="li-btn" onClick={() => { setClipOn(false); }}>
                  Clip off
                </button>
              </div>
              <div className="li-faint" style={{ fontSize: 10, lineHeight: 1.6 }}>
                Hard-clips points outside the selected parcel height slab.
              </div>
            </div>
          </div>
        )}

        {/* measure drawer */}
        {drawer === 'measure' && (
          <div className="li-drawer li-panel" role="dialog" aria-label="Measurements">
            <DrawerHead title="Measure" onClose={() => setDrawer(null)} />
            <div className="li-drawer__body">
              <div className="li-muted" style={{ fontSize: 11, lineHeight: 1.7, display: 'flex', gap: 8 }}>
                <Info size={14} className="li-accent" />
                <span>
                  Click two points on the point cloud to measure distance, or a double-point span with height for floor-to-floor readings.
                </span>
              </div>
              {measureReads.length > 0 && (
                <>
                  <div className="li-tiny">Readings</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {measureReads.map((r, i) => (
                      <div key={i} className="li-row">
                        <span className="li-row__k">R{i + 1}</span>
                        <span className="li-row__v">
                          {fmt(r.distance, 2)} m{i === 0 && tool === 'measure' ? '' : ''}
                          {r.height != null && <span style={{ color: 'var(--lidar-accent)' }}> · Δ {fmt(r.height, 2)} m</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                  <button className="li-action" onClick={() => engineRef.current?.clearMeasurements()}>
                    <Trash2 size={13} /> Clear measurements
                  </button>
                </>
              )}
              <div className="li-divider" />
              <button className="li-action" onClick={() => { setTool('select'); setDrawer(null); setActiveToolState('select'); }}>
                <MousePointer2 size={13} /> Return to select
              </button>
            </div>
          </div>
        )}

        {/* status bar */}
        {loading === 2 && (
          <div className="li-status li-panel">
            <span className="li-status__item">
              <span className="li-status__dot" />
              <b>DEMO LIDAR</b>
            </span>
            <span className="li-status__item">
              Points <b>{fmt(status.rendered, 0)} / {stats ? fmt(stats.point_count, 0) : '—'}</b>
            </span>
            <span className="li-status__item">
              Density <b>{density ? fmt(density, 1) : '—'} pts/m²</b>
            </span>
            <span className="li-status__item">
              {hover ? (
                <>
                  Elev <b>{fmt(hover.z, 2)} m</b> · {CLASS_LABELS[hover.classification] || 'Class ' + hover.classification} · Int {hover.intensity}
                </>
              ) : (
                <>
                  Elev <b>{zBounds.min.toFixed(1)}…{zBounds.max.toFixed(1)} m</b>
                </>
              )}
            </span>
            <span className="li-status__item">
              Mode <b>{COLOR_MODES.find((m) => m.id === colorMode)?.label.toLowerCase()}</b>
            </span>
            {selection && (
              <span className="li-status__item">
                ULPIN <b>{selection.ulpin}</b>
              </span>
            )}
            <span className="li-status__spacer" />
            <span className="li-status__item li-faint">
              {fmt(status.fps, 0)} fps · {scene?.dataset.crs.epsg ? 'EPSG:' + scene.dataset.crs.epsg : ''}
            </span>
          </div>
        )}

        {/* empty hint */}
        {loading === 2 && !selection && (
          <div className="li-hint li-panel">
            <MousePointer2 size={13} className="li-accent" />
            Select a property to begin inspection — click the highlighted parcel
          </div>
        )}
      </div>

      {/* loading overlay */}
      {loading !== 2 && !error && (
        <div className="li-overlay">
          <div className="li-overlay__mark">BD</div>
          <div className="li-overlay__title">LIDAR INSPECTION</div>
          <div className="li-overlay__sub">
            {loading === 0 ? 'Reading dataset header…' : 'Streaming point cloud…'}
          </div>
          {progress && (
            <>
              <div className="li-progress">
                <div className="li-progress__bar" style={{ width: pct(progress.total ? progress.loaded / progress.total : 0) }} />
              </div>
              <div className="li-overlay__sub li-mono">
                {fmt(progress.decoded, 0)} points decoded
              </div>
            </>
          )}
          <div className="li-chip" style={{ marginTop: 8 }}>Demo dataset — Airoli S8, Navi Mumbai</div>
        </div>
      )}

      {/* error overlay */}
      {error && (
        <div className="li-overlay">
          <div className="li-overlay__mark" style={{ background: 'linear-gradient(140deg,#b91c1c,#7f1d1d)' }}>!</div>
          <div className="li-overlay__title li-overlay__error">LIDAR DATA UNAVAILABLE</div>
          <div className="li-overlay__error-detail">{error}</div>
          <button className="li-btn li-btn--active" onClick={tryAgain} style={{ padding: '8px 18px' }}>
            <RotateCcw size={14} /> Retry
          </button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* small building blocks                                                */
/* ------------------------------------------------------------------ */

function IconBtn({ active, title, kbd, onClick, icon }: { active?: boolean; title: string; kbd?: string; onClick: () => void; icon: React.ReactNode }) {
  return (
    <button
      className={`li-icon${active ? ' li-icon--active' : ''}`}
      onClick={onClick}
      title={title}
      aria-label={title}
      aria-pressed={!!active}
      data-tooltip={title}
    >
      {icon}
      {kbd && <span className="li-kbd">{kbd}</span>}
    </button>
  );
}

function DrawerHead({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="li-drawer__head">
      <span className="li-drawer__title">{title}</span>
      <button className="li-icon-close" onClick={onClose} aria-label={`Close ${title}`}>
        <X size={14} />
      </button>
    </div>
  );
}

function LayerToggle({ label, on, onChange, hint, swatch }: { label: string; on: boolean; onChange: () => void; hint?: string; swatch?: string }) {
  return (
    <button
      className="li-action"
      onClick={onChange}
      role="checkbox"
      aria-checked={on}
      style={{ justifyContent: 'space-between' }}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        {swatch && <span className="li-legend__swatch" style={{ background: swatch }} />}
        {label}
      </span>
      <span className="li-status__item">
        {hint && <span className="li-faint">{hint}</span>}
        <span style={{ marginLeft: 8, width: 14, height: 14, borderRadius: 4, border: '1px solid var(--lidar-border-strong)', background: on ? 'var(--lidar-accent)' : 'transparent', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: '#05070d' }}>
          {on && <Check size={10} strokeWidth={3} />}
        </span>
      </span>
    </button>
  );
}

function SliderRow({ label, min, max, value, display, onChange }: { label: string; min: number; max: number; value: number; display: string; onChange: (v: number) => void }) {
  return (
    <div className="li-slider-row">
      <div className="li-slider-row__labels">
        <span>{label}</span>
        <span className="li-accent">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={Math.max(max, min)}
        value={Math.min(max, Math.max(min, value))}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
      />
    </div>
  );
}

function Legend({ mode, classCounts }: { mode: ColorMode; classCounts: Map<number, number> }) {
  switch (mode) {
    case 'elevation':
      return (
        <div className="li-legend li-panel">
          <span className="li-legend__title">Elevation</span>
          <div className="li-legend__bar" style={{ background: 'linear-gradient(90deg,#4a1126,#b2452d,#e8a63b,#e8d84b)' }} />
          <div className="li-legend__ticks">
            <span>low</span>
            <span>high</span>
          </div>
        </div>
      );
    case 'intensity':
      return (
        <div className="li-legend li-panel">
          <span className="li-legend__title">Intensity</span>
          <div className="li-legend__bar" style={{ background: 'linear-gradient(90deg,#05070d,#1c3a5f,#2767b0,#8fd0ff)' }} />
          <div className="li-legend__ticks">
            <span>42</span>
            <span>90</span>
          </div>
        </div>
      );
    case 'classification':
      return (
        <div className="li-legend li-panel">
          <span className="li-legend__title">Classification</span>
          {Object.entries(CLASS_LABELS).map(([code, label]) => (
            <div key={code} className="li-legend__item">
              <span className="li-legend__swatch" style={{ background: CLASS_COLORS[Number(code)] }} />
              <span>{label}</span>
              <span className="li-faint" style={{ marginLeft: 'auto' }}>{classCounts.get(Number(code)) ?? ''}</span>
            </div>
          ))}
        </div>
      );
    case 'gradient':
      return (
        <div className="li-legend li-panel">
          <span className="li-legend__title">Gradient</span>
          <div className="li-legend__bar" style={{ background: 'linear-gradient(90deg,#1d4ed8,#ffffff)' }} />
          <div className="li-legend__ticks">
            <span>min</span>
            <span>max</span>
          </div>
        </div>
      );
    case 'rgb':
      return (
        <div className="li-legend li-panel">
          <span className="li-legend__title">RGB</span>
          <div className="li-muted" style={{ fontSize: 10, lineHeight: 1.6 }}>
            Source has no RGB channel — neutral render shown.
          </div>
        </div>
      );
    default:
      return null;
  }
}

function PropertyDrawer({
  selection,
  focusParcel,
  isolateBuilding,
  floorLevel,
  onToggleFocus,
  onToggleIsolate,
  onFloor,
  onOpenMap,
}: {
  selection: LidarSelection;
  focusParcel: boolean;
  isolateBuilding: boolean;
  floorLevel: LidarLevel | null;
  onToggleFocus: () => void;
  onToggleIsolate: () => void;
  onFloor: (lvl: LidarLevel) => void;
  onOpenMap: () => void;
}) {
  const isHero = selection.buildingCode === 'B-17' || selection.ulpin === DEMO_ULPIN;
  const hasBuilding = isHero || selection.levels.length > 0 || (selection.footprint && selection.footprint.length > 0);
  return (
    <>
      <div className="li-drawer__head" style={{ borderBottom: '1px solid var(--lidar-border)' }}>
        <span className="li-drawer__title">
          {hasBuilding ? <Building2 size={14} /> : <Focus size={14} />} {selection.buildingCode || 'Property'}
        </span>
        {hasBuilding && (
          <span className="li-chip" style={{ fontSize: 9 }}>
            {selection.buildingCode === 'B-17' ? 'Hero Twin' : '3D Cadastre'}
          </span>
        )}
      </div>
      <div className="li-drawer__body">
        <div className="li-row">
          <span className="li-row__k">ULPIN</span>
          <span className="li-row__v li-accent">{selection.ulpin}</span>
        </div>
        {selection.buildingName && (
          <div className="li-row">
            <span className="li-row__k">Property</span>
            <span className="li-row__v">{selection.buildingName}</span>
          </div>
        )}
        {selection.buildingCode && (
          <div className="li-row">
            <span className="li-row__k">Code</span>
            <span className="li-row__v">{selection.buildingCode}</span>
          </div>
        )}
        {hasBuilding ? (
          <>
            <div className="li-row">
              <span className="li-row__k">Floors</span>
              <span className="li-row__v">{selection.levels.length} Floors · Height {fmt(selection.heightM, 1)} m</span>
            </div>
            <div className="li-row">
              <span className="li-row__k">Footprint</span>
              <span className="li-row__v">{selection.footprint.length} vertex pts</span>
            </div>
          </>
        ) : (
          <div className="li-row">
            <span className="li-row__k">LiDAR twin</span>
            <span className="li-row__v li-warn" style={{ color: 'var(--lidar-warn)' }}>Parcel Boundary Only</span>
          </div>
        )}

        {hasBuilding && selection.proposed_3d_id && (
          <div className="li-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
            <span className="li-row__k">Building 3D-ULPIN</span>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: 6 }}>
              <span className="li-row__v li-mono li-accent" style={{ fontSize: 10, wordBreak: 'break-all' }}>{selection.proposed_3d_id}</span>
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(selection.proposed_3d_id!);
                }}
                className="li-chip"
                style={{ cursor: 'pointer', padding: '2px 6px', fontSize: 9, whiteSpace: 'nowrap' }}
                title="Copy Building 3D-ULPIN"
              >
                Copy
              </button>
            </div>
          </div>
        )}

        <div className="li-divider" />

        {hasBuilding && (
          <>
            <div className="li-tiny">Inspection emphasis</div>
            <button className={`li-action ${focusParcel ? 'li-action--accent' : ''}`} onClick={onToggleFocus}>
              <Focus size={13} /> {focusParcel ? 'Focus parcel active' : 'Focus parcel'}
            </button>
            <button className={`li-action ${isolateBuilding ? 'li-action--accent' : ''}`} onClick={onToggleIsolate}>
              <Building2 size={13} /> {isolateBuilding ? 'Building isolated' : 'Isolate building'}
            </button>

            <div className="li-tiny">Floor emphasis</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {selection.levels.map((lv) => (
                <button
                  key={lv.level_code}
                  className={`li-btn ${floorLevel?.level_code === lv.level_code ? 'li-btn--active' : ''}`}
                  onClick={() => onFloor(lv)}
                >
                  {lv.name || lv.level_code}
                </button>
              ))}
            </div>
            {floorLevel && (
              <div className="li-muted li-mono" style={{ fontSize: 10 }}>
                {fmt(floorLevel.min_z, 1)} – {fmt(floorLevel.max_z, 1)} m
              </div>
            )}

            {selection.units && selection.units.length > 0 && (
              <>
                <div className="li-divider" />
                <div className="li-tiny" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>Constituent 3D ULPIN Units</span>
                  <span className="li-chip" style={{ fontSize: 8 }}>{selection.units.length} Units</span>
                </div>
                <div style={{ maxHeight: 150, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, paddingRight: 4 }}>
                  {selection.units.slice(0, 16).map((u: any) => (
                    <div
                      key={u.unit_number || u.proposed_3d_id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '3px 6px',
                        background: 'rgba(255,255,255,0.03)',
                        borderRadius: 4,
                        fontSize: 10,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                        <span className="li-chip" style={{ fontSize: 8, padding: '1px 4px' }}>{u.unit_type || 'U'}</span>
                        <span className="li-row__k" style={{ fontSize: 10, whiteSpace: 'nowrap' }}>{u.unit_number} ({u.level_code})</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className="li-mono li-faint" style={{ fontSize: 9 }}>{u.proposed_3d_id?.split('-')?.slice(1)?.join('-') || u.proposed_3d_id}</span>
                        <button
                          onClick={() => navigator.clipboard?.writeText(u.proposed_3d_id)}
                          style={{ background: 'transparent', border: 'none', color: 'var(--lidar-accent)', cursor: 'pointer', fontSize: 10, display: 'inline-flex', alignItems: 'center' }}
                          title="Copy 3D ULPIN"
                        >
                          <Copy size={11} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {selection.units.length > 16 && (
                    <span className="li-faint" style={{ fontSize: 9, textAlign: 'center', marginTop: 2 }}>
                      +{selection.units.length - 16} more units registered
                    </span>
                  )}
                </div>
              </>
            )}
          </>
        )}

        <button className="li-action li-action--accent" onClick={onOpenMap}>
          <ArrowUpRight size={13} /> Open property record
        </button>
      </div>
    </>
  );
}

function boxFromSelection(sel: LidarSelection, z: { min: number; max: number }): { min: number[]; max: number[] } {
  const ring = sel.parcelRing;
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return {
    min: [Math.min(...xs), Math.min(...ys), sel.levels.length ? sel.levels[0].min_z - 0.2 : z.min],
    max: [Math.max(...xs), Math.max(...ys), sel.levels.length ? sel.levels[sel.levels.length - 1].max_z + 0.2 : z.max],
  };
}