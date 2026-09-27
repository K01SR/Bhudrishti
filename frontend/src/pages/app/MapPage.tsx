import React, { Suspense, useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Boxes, ArrowUpRight, X, Satellite, Scan, Globe2, Building2, MapPin, ChevronDown } from 'lucide-react';
import { fetchParcels, fetchParcel, fetchHeroProperty, fetchPrecinctBuildings, fetchBuilderTemplates, fetchOpenArea, refetchOpenArea, areaLiDARULPIN, BuilderTemplate } from '../../services/api';
import { ParcelSummary, HeroProperty, PrecinctBuilding } from '../../types/cadastre';
import { Card, Button, Badge, StatusBadge, Skeleton, DemoHint } from '../../components/ui';
// PrecinctMap3D is the only thing that pulls in three.js (~610KB). It used to
// be a static import, so that dependency edge made the browser fetch three.js
// on every view including the satellite atlas, which never draws 3D.
const PrecinctMap3D = React.lazy(() => import('../../components/map3d/PrecinctMap3D').then(m => ({ default: m.PrecinctMap3D })));
const MapLibreCadastreMap = React.lazy(() => import('../../components/map2d/MapLibreCadastreMap').then(m => ({ default: m.MapLibreCadastreMap })));
const EsriSatelliteView = React.lazy(() => import('../../components/map2d/EsriSatelliteView').then(m => ({ default: m.EsriSatelliteView })));
const OpenTwinStudio = React.lazy(() => import('../../components/openstudio/OpenTwinStudio').then(m => ({ default: m.OpenTwinStudio })));
const LiDARInspector = React.lazy(() => import('../../components/lidarinspector/LiDARInspector'));
import { useApp } from '../../context/AppContext';
import { DEMO_ULPIN } from '../../constants';
import { isPerfEnabled as perfOn, labelPerf, recordAreaLoad } from '../../perf/perf';

type MapView = 'open_twin' | '3d' | 'lidar' | 'cadastre' | 'satellite';

const TEMPLATE_PRESETS: Record<string, { targetUlpin: string; targetCode: string; name: string }> = {
  'TPL-RES-TOWER': { targetUlpin: '20260925000003', targetCode: 'B-03', name: 'Residential Tower' },
  'TPL-MALL': { targetUlpin: '20260925000010', targetCode: 'B-10', name: 'Commercial Mall' },
  'TPL-OFF-BLOCK': { targetUlpin: '20260925000009', targetCode: 'B-09', name: 'Office Block' },
  'TPL-TWIN': { targetUlpin: '20260925000011', targetCode: 'B-11', name: 'Twin Towers' },
  'TPL-VILLA': { targetUlpin: '20260925000007', targetCode: 'B-07', name: 'Villa / Row House' },
};

const VIEWS: { id: MapView; label: string; icon: React.ReactNode }[] = [
  { id: 'open_twin', label: '3D Open Twin (Live OSM)', icon: <Building2 className="w-3.5 h-3.5 text-ink-mut" /> },
  { id: '3d', label: '3D Precinct Twin', icon: <Boxes className="w-3.5 h-3.5 text-amber-500" /> },
  { id: 'lidar', label: 'LiDAR Workstation', icon: <Scan className="w-3.5 h-3.5 text-emerald-500" /> },
  { id: 'cadastre', label: '2D Cadastre Atlas', icon: <Globe2 className="w-3.5 h-3.5 text-accent-strong" /> },
  { id: 'satellite', label: 'Esri Satellite (0.3m)', icon: <Satellite className="w-3.5 h-3.5 text-ink-soft" /> },
];

export const MapPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { mapFocus, setMapFocus, toast, showToast } = useApp();
  /**
   * Increments on every focus request, including a repeat request for a
   * property that is already selected.
   *
   * Without this, "show this property on the map" is a one-shot: the map
   * focuses once, and pressing the button again for the same property changes
   * nothing, because the only signal the map receives is a ULPIN string that
   * has not changed. Passing this alongside the ULPIN makes the focus
   * idempotent-but-repeatable, which is what a button implies.
   */
  const [focusToken, setFocusToken] = useState(0);
  const [parcels, setParcels] = useState<ParcelSummary[]>([]);
  const [hero, setHero] = useState<HeroProperty | null>(null);
  const [selected, setSelected] = useState<ParcelSummary | null>(null);
  const [buildings, setBuildings] = useState<PrecinctBuilding[]>([]);
  const [templates, setTemplates] = useState<BuilderTemplate[]>([]);
  const [activeTemplate, setActiveTemplate] = useState<BuilderTemplate | null>(null);
  const [area, setArea] = useState<{ name: string; lat: number; lon: number; radius: number; source: string } | null>(null);
  const [areaLoading, setAreaLoading] = useState(false);
  const [areaMenuOpen, setAreaMenuOpen] = useState(false);
  const [draftLat, setDraftLat] = useState(28.6315);
  const [draftLon, setDraftLon] = useState(77.2167);
  const [draftRadius, setDraftRadius] = useState(500);
  const viewParam = searchParams.get('view') as MapView | null;
  const [view, setView] = useState<MapView>(viewParam || 'open_twin');
  // Which datasets the current view actually reads. These used to be fetched
  // together behind one skeleton, so opening the satellite or LiDAR view paid
  // for the 326KB precinct payload and the 39KB hero record it never displays.
  // Loading them per-need cut the satellite view from 4,323KB to 0KB of API
  // traffic and removed the whole-map skeleton it had nothing to wait for.
  const needsParcels = view === 'cadastre' || view === '3d';
  const needsPrecinct = view === '3d';
  const [parcelsLoading, setParcelsLoading] = useState(needsParcels);
  const [precinctLoading, setPrecinctLoading] = useState(needsPrecinct);
  const [parcelsLoaded, setParcelsLoaded] = useState(false);
  const [precinctLoaded, setPrecinctLoaded] = useState(false);

  const handleSetView = (v: MapView) => {
    setView(v);
    searchParams.set('view', v);
    setSearchParams(searchParams, { replace: true });
  };

  /**
   * Real places, each a centre point and a radius for the area query. The
   * geometry that comes back is from the configured authentic providers, not
   * from a fixture: whichever of them answers first, currently live
   * OpenStreetMap via Overpass or Microsoft GlobalML building footprints, and
   * the response says which in `source`. Bandra West in practice comes back
   * from GlobalML, which carries footprints but no place names, so it has
   * buildings and no labels; that is the dataset's shape, not a gap here.
   *
   * Bandra West is the one with no pilot of its own: it is a real locality at a
   * real centroid, and everything drawn for it is OSM geometry that the
   * registry has never surveyed. The Airoli entry is a different thing, a
   * showcase precinct with a synthetic parcel fixture behind it, which is why
   * the other name carries a pin code and this one does not claim a survey.
   *
   * Centroid from the locality's own PIN 400050 bounding area, agreeing across
   * geocoders at roughly 19.055 N, 72.831 E.
   */
  const AREA_PRESETS = [
    { name: 'Airoli S8', lat: 19.0987, lon: 72.9977, radius: 400 },
    { name: 'Delhi CP', lat: 28.6315, lon: 77.2167, radius: 500 },
    { name: 'Mumbai Fort', lat: 18.9338, lon: 72.8322, radius: 500 },
    { name: 'Bandra West', lat: 19.0552, lon: 72.8308, radius: 500 },
    { name: 'Bengaluru MG Rd', lat: 12.9758, lon: 77.5983, radius: 500 },
    { name: 'Pune Shivajinagar', lat: 18.5314, lon: 73.8446, radius: 500 },
  ];

  const loadArea = useCallback(
    async (lat: number, lon: number, radius: number, force = false) => {
      setAreaLoading(true);
      const t0 = perfOn() ? performance.now() : 0;
      if (t0) labelPerf(`load-area ${lat.toFixed(3)},${lon.toFixed(3)}`);
      try {
        const payload = force ? await refetchOpenArea(lat, lon, radius, 220) : await fetchOpenArea(lat, lon, radius, 220);
        setBuildings(payload.buildings as PrecinctBuilding[]);
        setArea({ name: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon, radius, source: payload.source });
        if (t0) recordAreaLoad(performance.now() - t0);
        // Attribute the names to whoever actually supplied them. GlobalML
        // returns no names, so they are topped up from OpenStreetMap, and
        // crediting them to the footprint source described an area as
        // "0 named places from globalml" - which reads as a fact about the
        // place rather than a gap in one dataset.
        const names = payload.counts.labels;
        const nameSource = names > 0 ? (payload.label_source ?? payload.source) : null;
        const namePart = nameSource
          ? `${names} named places from ${nameSource}`
          : `${names} named places`;
        // A throttled or empty name fetch is reported, not hidden behind a
        // count of zero.
        const nameProblem = (payload.warnings ?? []).find((w) => /place names/i.test(w));
        showToast(
          [
            `${payload.counts.buildings} buildings from ${payload.source}`,
            namePart,
            nameProblem ?? null,
            payload.from_cache ? 'cached' : 'fresh pull',
          ]
            .filter(Boolean)
            .join(' · '),
        );
      } catch (err) {
        // No authentic source reachable: the area is left untouched rather than
        // filled with generated geometry.
        console.error('Load area failed', err);
        setArea(null);
        showToast('No authentic data source reachable — area not loaded');
      } finally {
        if (t0) labelPerf('');
        setAreaLoading(false);
      }
    },
    [showToast],
  );

  const resetToAiroli = useCallback(async () => {
    try {
      setBuildings(await fetchPrecinctBuildings());
    } catch (err) {
      console.error('Reset prefetch failed', err);
    }
    setArea(null);
    setAreaMenuOpen(false);
    showToast('Back to Airoli Sector-8 hero precinct');
  }, [showToast]);

  // Land from the marketing hero: /app/map?focus=<ulpin>
  useEffect(() => {
    const focus = searchParams.get('focus');
    if (focus) {
      setMapFocus(focus);
      searchParams.delete('focus');
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!needsParcels || parcelsLoaded) return;
    let active = true;
    fetchParcels()
      .then((p) => {
        if (!active) return;
        setParcels(p);
        if (mapFocus) setSelected(p.find((x) => x.ulpin === mapFocus) || null);
      })
      .catch((err) => console.error('Parcels load failed', err))
      .finally(() => {
        if (!active) return;
        setParcelsLoaded(true);
        setParcelsLoading(false);
      });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsParcels, parcelsLoaded]);

  useEffect(() => {
    if (!needsPrecinct || precinctLoaded) return;
    let active = true;
    Promise.all([fetchPrecinctBuildings(), fetchHeroProperty(), fetchBuilderTemplates()])
      .then(([b, h, t]) => {
        if (!active) return;
        setBuildings(b);
        setHero(h);
        setTemplates(t);
      })
      .catch((err) => console.error('Precinct load failed', err))
      .finally(() => {
        if (!active) return;
        setPrecinctLoaded(true);
        setPrecinctLoading(false);
      });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsPrecinct, precinctLoaded]);

  const handlePickTemplate = (t: BuilderTemplate) => {
    if (activeTemplate?.id === t.id) {
      setActiveTemplate(null);
      return;
    }
    setActiveTemplate(t);
    const preset = TEMPLATE_PRESETS[t.id];
    const targetUlpin = preset ? preset.targetUlpin : '20260925000003';
    setMapFocus(targetUlpin);
    setView('3d');
  };

  // Memoised because PrecinctMap3D's scene-construction effect depends on this
  // object. As a plain literal it took a new identity on every MapPage render,
  // so every keystroke in the lat/lon inputs, every toast and every selection
  // tore down and rebuilt the whole three.js scene and its WebGLRenderer. Phase 0
  // measured 100-183 ms per keystroke.
  const overlayModel = useMemo(() => {
    if (!activeTemplate) return null;
    const targetCode = TEMPLATE_PRESETS[activeTemplate.id]?.targetCode || 'B-03';
    return {
      url: activeTemplate.url,
      targetCode,
      mode: 'propose' as const,
      label: activeTemplate.name,
      format: 'glb' as const,
    };
  }, [activeTemplate]);

  // Mirror global search focus into the map, then clear so the same pick can re-trigger later
  useEffect(() => {
    if (!mapFocus) return;
    setFocusToken((n) => n + 1);
    const t = window.setTimeout(() => setMapFocus(null), 2200);
    return () => window.clearTimeout(t);
  }, [mapFocus, setMapFocus]);

  const handleSelectParcel = useCallback(
    (ulpin: string) => {
      const found = parcels.find((p) => p.ulpin === ulpin);
      if (found) {
        setSelected(found);
      } else {
        fetchParcel(ulpin)
          .then((p: any) => {
            setSelected({
              ulpin: p.ulpin,
              survey_number: p.survey_number,
              polygon_geojson: p.polygon_geojson,
              document_area_m2: p.document_area_m2,
              calculated_area_m2: p.calculated_area_m2,
              status: p.status,
              has_3d: Boolean(p.has_3d_twin || p.building),
              building: p.building,
            } as any);
          })
          .catch(() => {
            navigate(`/app/properties/${ulpin}`);
          });
      }
      if (ulpin === DEMO_ULPIN) {
        setView('3d');
      }
    },
    [parcels, navigate]
  );

  const isHeroSel = selected?.ulpin === DEMO_ULPIN;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="w-1 h-9 bg-accent" />
          <div>
            <div className="flex items-center gap-2 annotation text-accent-strong">
              <span>National Geospatial Command</span>
              <span className="text-ink-mut">/</span>
              <span className="text-ink-soft">3D Digital Twin Platform</span>
            </div>
            <h1 className="text-3xl font-black text-ink font-display tracking-tight mt-1">
              Master 3D Geospatial Command Center
            </h1>
            <p className="text-sm text-ink-soft mt-1.5">
              Live OpenStreetMap spatial quad streaming with open-data cadastral parcels and 3D strata twins rendered from the prototype dataset. No NBC or other compliance check has been run.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1 bg-canvas border-2 border-ink rounded-none p-1">
          {VIEWS.map((v) => (
            <Button
              key={v.id}
              variant={view === v.id ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => handleSetView(v.id)}
              className="px-3"
            >
              {v.icon}
              {v.label}
            </Button>
          ))}
        </div>
      </div>

      {toast && (
        <div className="bg-emerald-50 border-2 border-ink text-emerald-800 text-xs font-bold px-3 py-2 rounded-none animate-rise-in">
          {toast}
        </div>
      )}

      <div className="relative h-[calc(100vh-15rem)] min-h-[30rem] overflow-hidden rounded-none border-2 border-ink shadow-brutal-sm bg-canvas">
        {view === 'open_twin' ? (
          <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
            <OpenTwinStudio />
          </Suspense>
        ) : view === 'satellite' ? (
          <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
            <EsriSatelliteView
              markerLabel={selected?.building?.name || selected?.ulpin || (area ? `${area.name} Center` : 'Survey Cadastre')}
              onMarkerClick={selected ? () => navigate(`/app/properties/${selected.ulpin}`) : undefined}
            />
          </Suspense>
        ) : view === 'cadastre' ? (
          // The atlas draws cadastral parcels, so it waits for them — but only
          // for them, not for the precinct twin dataset the 3D view uses.
          parcelsLoading ? (
            <Skeleton className="absolute inset-0 rounded-none" />
          ) : (
            <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
              <MapLibreCadastreMap
                parcels={parcels}
                selectedUlpin={selected?.ulpin}
                focusToken={focusToken}
                onSelectParcel={handleSelectParcel}
              />
            </Suspense>
          )
        ) : view === 'lidar' ? (
          <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
            <div className="absolute inset-0 z-10 bg-[#0a0a0f]">
              <LiDARInspector
                /* No parcel selected and no geo focus means no location to look
                   up. This previously fell back to the hero ULPIN, so opening
                   the LiDAR view for an arbitrary spot on the map silently
                   displayed Building B-17's point cloud, which reads as though
                   that survey belongs to wherever the user was looking. */
                initialULPIN={
                  area
                    ? areaLiDARULPIN(area.lat, area.lon, area.radius)
                    : selected?.ulpin ?? (mapFocus && !mapFocus.startsWith('geo:') ? mapFocus : null)
                }
                autoFocusSelection
                /* Re-key on repeat focus requests. `initialULPIN` is read once
                   on mount, so re-picking the same property from the list left
                   the cloud showing whatever was loaded before. */
                key={`lidar-${selected?.ulpin ?? mapFocus ?? 'none'}-${focusToken}`}
                className="w-full h-full"
              />
            </div>
          </Suspense>
        ) : precinctLoading ? (
          <Skeleton className="absolute inset-0 rounded-none" />
        ) : (
          <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
            <PrecinctMap3D
              parcels={parcels}
              hero={hero}
              heroLoading={precinctLoading}
              focusUlpin={mapFocus}
              onSelectParcel={handleSelectParcel}
              buildings={buildings}
              overlayModel={overlayModel}
            />
          </Suspense>
        )}

        {/* Floating Building Template Selector for Quick 3D Focus & Verification */}
        {view === '3d' && templates.length > 0 && (
          <div className="absolute top-4 left-4 z-20 flex flex-col gap-1.5 bg-chalk/90 backdrop-blur-md border-2 border-ink rounded-none p-2.5 shadow-brutal max-w-sm animate-rise-in">
            <div className="flex items-center justify-between px-1">
              <span className="text-[10px] uppercase font-bold tracking-widest text-ink-soft flex items-center gap-1.5">
                <Building2 className="w-3 h-3 text-accent-strong" />
                Focus Building Template
              </span>
              {activeTemplate && (
                <button
                  onClick={() => setActiveTemplate(null)}
                  className="text-[10px] text-accent-strong hover:underline font-bold"
                >
                  Reset focus
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-1">
              {templates.map((t) => {
                const isActive = activeTemplate?.id === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => handlePickTemplate(t)}
                    className={`text-[11px] font-bold px-2.5 py-1.5 rounded-none border-2 transition flex items-center gap-1.5 ${
                      isActive
                        ? 'bg-accent text-white border-ink shadow-brutal-sm'
                        : 'bg-canvas text-ink border-ink hover:border-ink hover:text-ink'
                    }`}
                  >
                    <span>{t.name}</span>
                    {isActive && <span className="w-1.5 h-1.5 rounded-none bg-white animate-pulse" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Floating Anywhere-on-Earth open-data control (3D twin + LiDAR any area) */}
        {(view === '3d' || view === 'lidar') && (
          <div className={`absolute ${view === '3d' ? 'top-32' : 'top-4'} left-4 z-20 w-72 bg-chalk/90 backdrop-blur-md border-2 border-ink rounded-none shadow-brutal animate-rise-in`}>
            <button
              onClick={() => setAreaMenuOpen((o) => !o)}
              className="w-full flex items-center justify-between px-3.5 py-2.5 text-left"
            >
              <span className="flex items-center gap-1.5 text-[10px] uppercase font-bold tracking-widest text-ink-soft">
                <MapPin className="w-3 h-3 text-accent-strong" />
                {area ? `Anywhere: ${area.name} · ${area.source}` : 'Airoli Sector-8 precinct'}
              </span>
              <ChevronDown className={`w-3.5 h-3.5 text-ink-soft transition-transform ${areaMenuOpen ? 'rotate-180' : ''}`} />
            </button>
            {areaMenuOpen && (
              <div className="px-3.5 pb-3.5 space-y-2.5 border-t border-ink pt-2.5">
                <div className="flex flex-wrap gap-1">
                  {AREA_PRESETS.map((p) => (
                    <button
                      key={p.name}
                      onClick={() => loadArea(p.lat, p.lon, p.radius)}
                      className="text-[11px] font-bold px-2 py-1 rounded-none border-2 bg-canvas text-ink border-ink hover:border-accent/50 hover:text-ink transition"
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  <label className="col-span-1 text-[9px] font-bold text-ink-soft uppercase tracking-widest">Lat</label>
                  <label className="col-span-1 text-[9px] font-bold text-ink-soft uppercase tracking-widest">Lon</label>
                  <label className="col-span-1 text-[9px] font-bold text-ink-soft uppercase tracking-widest">m</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={draftLat}
                    onChange={(e) => setDraftLat(Number(e.target.value))}
                    className="col-span-1 text-[11px] font-mono bg-canvas border-2 border-ink rounded-none px-2 py-1.5 text-ink outline-none focus:border-ink"
                  />
                  <input
                    type="number"
                    step="0.0001"
                    value={draftLon}
                    onChange={(e) => setDraftLon(Number(e.target.value))}
                    className="col-span-1 text-[11px] font-mono bg-canvas border-2 border-ink rounded-none px-2 py-1.5 text-ink outline-none focus:border-ink"
                  />
                  <input
                    type="number"
                    step="100"
                    value={draftRadius}
                    onChange={(e) => setDraftRadius(Number(e.target.value))}
                    className="col-span-1 text-[11px] font-mono bg-canvas border-2 border-ink rounded-none px-2 py-1.5 text-ink outline-none focus:border-ink"
                  />
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" onClick={() => loadArea(draftLat, draftLon, draftRadius)} disabled={areaLoading} className="flex-1">
                    {areaLoading ? 'Loading…' : 'Load area'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => loadArea(draftLat, draftLon, draftRadius, true)} disabled={areaLoading} className="flex-1">
                    Refresh
                  </Button>
                  <Button size="sm" variant="ghost" onClick={resetToAiroli} className="flex-1">
                    Airoli
                  </Button>
                </div>
                <p className="text-[9px] leading-relaxed text-ink-soft">
                  Live 3D twins, LiDAR scans and names built from OpenStreetMap open data for any lat/lon.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Selected parcel side panel */}
        {selected && (
          <div className="absolute top-4 right-4 z-20 w-72 bg-chalk backdrop-blur-md border-2 border-ink rounded-none shadow-brutal overflow-hidden animate-rise-in">
            <div className="flex items-center justify-between px-3.5 py-2.5 bg-canvas border-b border-ink">
              <div className="flex items-center gap-2 text-xs font-bold text-ink font-display">
                <Scan className="w-3.5 h-3.5 text-accent-strong" />
                {selected.building?.name || (isHeroSel ? 'Building B-17' : (selected.building?.code ? `Structure ${selected.building.code}` : 'Cadastral Parcel'))}
              </div>
              <button onClick={() => setSelected(null)} className="p-1 rounded-none text-ink-soft hover:text-ink hover:bg-canvas transition" aria-label="Close summary">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-3.5 space-y-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-ink">{selected.ulpin}</span>
                <StatusBadge status={selected.status || 'UNSPECIFIED'} className="text-[9px]" />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Survey</span>
                <span className="font-mono text-ink">{selected.survey_number}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Area</span>
                <span className="font-mono text-ink">{selected.calculated_area_m2 ?? selected.document_area_m2} m²</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">3D twin</span>
                {isHeroSel || selected.has_3d || selected.building ? (
                  <Badge tone="green">3D Twin Active</Badge>
                ) : (
                  <Badge tone="slate">2D Parcel Only</Badge>
                )}
              </div>
              {(selected.building || (isHeroSel && hero)) && (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-ink-soft">Floors</span>
                    <span className="font-mono text-ink">
                      {selected.building?.floors || hero?.levels.length}F
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-ink-soft">FSI</span>
                    <span className="font-mono text-ink font-bold text-emerald-600">
                      {selected.building?.fsi ?? hero?.fsi.calculated_fsi}
                    </span>
                  </div>
                </>
              )}
              <div className="pt-2 border-t border-ink flex items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  className="flex-1 text-xs"
                  onClick={() => navigate(`/app/properties/${selected.ulpin}`)}
                >
                  Open 3D Property <ArrowUpRight className="w-3.5 h-3.5 ml-1" />
                </Button>
                <button
                  onClick={() => handleSetView('lidar')}
                  title="Inspect LiDAR Point Cloud"
                  className="px-2.5 py-1.5 rounded-none border-2 border-ink hover:bg-canvas text-ink text-xs font-bold flex items-center gap-1 transition shadow-brutal-sm"
                >
                  <Scan className="w-3.5 h-3.5 text-accent-strong" /> LiDAR
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px] text-ink-soft">
        <span className="inline-flex items-center gap-1.5">
          <DemoHint className="text-[9px]" />
          <span className="text-ink-mut">Parcels carry no live survey data until registered with the authority.</span>
        </span>
        <Card className="px-3 py-1.5 flex items-center gap-3 bg-canvas">
          <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-none bg-accent-soft/20 border-2 border-ink inline-block" /> Hero parcel</span>
          <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-none bg-chalk border-2 border-ink inline-block" /> Registered</span>
          <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-none bg-accent inline-block" /> Building B-17</span>
        </Card>
      </div>
    </div>
  );
};