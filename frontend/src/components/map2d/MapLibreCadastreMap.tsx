import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  Filter,
  Boxes,
  Globe2,
  Layers,
  Loader2,
  Palette,
  Download,
  ExternalLink,
} from 'lucide-react';
import { ParcelSummary } from '../../types/cadastre';
import { NationalVizPanel } from './NationalVizPanel';
import { searchProperties, locateLgdVillage, PROPERTY_CARD_PDF_URL, fetchSubgrade, SubgradeResponse } from '../../services/api';
import { useApp } from '../../context/AppContext';
import { DeckGL3DOverlay, InspectedStructure, DeckGLColorMode } from './DeckGL3DOverlay';
import { CadastrePropertyInspector } from './CadastrePropertyInspector';
import { fetchOSMBuildings, fetchLocalityLabels } from '../../services/overpass';
import { DEMO_ULPIN } from '../../constants';
import { MapLoadingBar } from './MapLoadingBar';
import { basemapTileUrl, basemapStyleFor, loadBasemapPref, saveBasemapPref, type BasemapPref } from '../../services/cartoBasemap';
import { BasemapModeToggle } from './BasemapModeToggle';
import { HighlightPointer } from './HighlightPointer';

interface Props {
  parcels?: ParcelSummary[];
  onSelectParcel?: (ulpin: string) => void;
  selectedUlpin?: string;
  /**
   * Monotonic counter, bumped by the parent on every focus request. The camera
   * guard keys on this as well as the ULPIN so a repeat request for the already
   * selected property still flies the camera.
   */
  focusToken?: number;
  hasClash?: boolean;
}

const INDIA_CENTER: [number, number] = [78.9629, 22.5937];
const AIROLI_CENTER: [number, number] = [72.9984, 19.1557];

/* Opening camera. The atlas carries no maxBounds and its basemap is a global
   raster, so the whole world is a legitimate place to start rather than a
   fallback. Biased north of the equator because most of the landmass is there,
   and flat, because a pitched world view hides the far hemisphere behind the
   horizon. India is one click away on the region bar. */
const WORLD_CENTER: [number, number] = [0, 12];
const WORLD_ZOOM = 1.3;

const REGION_PRESETS = [
  { id: 'world', label: 'World', center: WORLD_CENTER, zoom: WORLD_ZOOM, pitch: 0 },
  { id: 'all_india', label: 'All India', center: INDIA_CENTER, zoom: 4.5, pitch: 0 },
  { id: 'maharashtra', label: 'Maharashtra', center: [75.7139, 19.7515] as [number, number], zoom: 6.8, pitch: 35 },
  { id: 'karnataka', label: 'Karnataka', center: [75.7139, 15.3173] as [number, number], zoom: 7.0, pitch: 35 },
  { id: 'gujarat', label: 'Gujarat', center: [71.1924, 22.2587] as [number, number], zoom: 7.0, pitch: 35 },
  { id: 'delhi', label: 'Delhi NCR', center: [77.1025, 28.7041] as [number, number], zoom: 10.5, pitch: 45 },
  { id: 'tamil_nadu', label: 'Tamil Nadu', center: [78.6569, 11.1271] as [number, number], zoom: 7.0, pitch: 35 },
  { id: 'telangana', label: 'Telangana', center: [79.0193, 18.1124] as [number, number], zoom: 7.0, pitch: 35 },
  { id: 'mumbai', label: 'Mumbai Metropole', center: [72.8258, 18.9255] as [number, number], zoom: 15.8, pitch: 58 },
  { id: 'airoli_pilot', label: 'Airoli Sector 8 (Pilot)', center: [72.9984, 19.1557] as [number, number], zoom: 16.5, pitch: 58 },
  // Real locality, real centroid (PIN 400050), no survey behind it: see AREA_PRESETS in MapPage.
  { id: 'bandra_west', label: 'Bandra West', center: [72.8308, 19.0552] as [number, number], zoom: 15.5, pitch: 55 },
];

export const MapLibreCadastreMap: React.FC<Props> = ({
  parcels,
  onSelectParcel,
  selectedUlpin,
  focusToken = 0,
  hasClash = true,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const { mapFocus } = useApp();
  const [mapLoaded, setMapLoaded] = useState(false);
  /**
   * Basemap theme and label state. The atlas was authored against CARTO's
   * `light_all` and its parcel fills and status colours are legible on white,
   * so light is the default here -- the opposite of the 3D studio, which is
   * dark-first. Persisted under its own key so the two views keep separate
   * preferences.
   */
  const [basemapPref, setBasemapPref] = useState<BasemapPref>(() =>
    loadBasemapPref('cadastre', { theme: 'light', labels: true }),
  );
  const [perspective, setPerspective] = useState<'3d' | '2d'>('3d');
  const [activeRegion, setActiveRegion] = useState('world');
  const [showThematicViz, setShowThematicViz] = useState(false);
  const [visibleLayers, setVisibleLayers] = useState({
    states: true,
    districts: true,
    parcels: true,
    twins: true,
  });
  const [inspectedEntity, setInspectedEntity] = useState<any | null>(null);

  // Deck.gl 3D & Exploded View States
  const [deckStructures, setDeckStructures] = useState<InspectedStructure[]>([]);
  const [selectedStructure, setSelectedStructure] = useState<InspectedStructure | null>(null);
  const [isExploded, setIsExploded] = useState(false);
  const [selectedFloor, setSelectedFloor] = useState<number | null>(null);
  const [colorMode, setColorMode] = useState<DeckGLColorMode>('height');
  const [liveOsmEnabled, setLiveOsmEnabled] = useState(false);
  const [osmLoading, setOsmLoading] = useState(false);

  /* Sub-grade. The atlas has no sub-grade geometry of its own - structures
     arrive as footprints, floors and a height - so this is opt-in and loaded
     on demand rather than folded into the default scene. */
  const [undergroundOn, setUndergroundOn] = useState(false);
  const [subgrade, setSubgrade] = useState<SubgradeResponse | null>(null);
  const [subgradeLoading, setSubgradeLoading] = useState(false);
  const [subgradeError, setSubgradeError] = useState<string | null>(null);

  const toggleLayerVisibility = (layerKey: keyof typeof visibleLayers) => {
    setVisibleLayers((prev) => {
      const next = { ...prev, [layerKey]: !prev[layerKey] };
      const map = mapRef.current;
      if (!map) return next;

      if (layerKey === 'states') {
        const val = next.states ? 'visible' : 'none';
        if (map.getLayer('state-line')) map.setLayoutProperty('state-line', 'visibility', val);
        if (map.getLayer('state-fill')) map.setLayoutProperty('state-fill', 'visibility', val);
      } else if (layerKey === 'districts') {
        const val = next.districts ? 'visible' : 'none';
        if (map.getLayer('district-line')) map.setLayoutProperty('district-line', 'visibility', val);
      } else if (layerKey === 'parcels') {
        const val = next.parcels ? 'visible' : 'none';
        if (map.getLayer('parcel-fill')) map.setLayoutProperty('parcel-fill', 'visibility', val);
        if (map.getLayer('parcel-line')) map.setLayoutProperty('parcel-line', 'visibility', val);
      } else if (layerKey === 'twins') {
        const val = next.twins ? 'visible' : 'none';
        if (map.getLayer('twin-extrusion')) map.setLayoutProperty('twin-extrusion', 'visibility', val);
        if (map.getLayer('twin-fill')) map.setLayoutProperty('twin-fill', 'visibility', val);
        if (map.getLayer('twin-line')) map.setLayoutProperty('twin-line', 'visibility', val);
      }
      return next;
    });
  };

  /**
   * Move the camera to whatever parcel is selected.
   *
   * This effect did not exist. `selectedUlpin` was accepted as a prop and used
   * for nothing except the inspector panel, so opening a property from the
   * registry and pressing "show on map" highlighted the right row while leaving
   * the camera wherever it was. At the default Airoli zoom the selected parcel
   * was frequently off-screen or a few pixels across, so the result read as "the
   * map ignored the property".
   *
   * Centroid is computed from the parcel's own polygon ring rather than taken
   * from a separate lat/lon field, because the polygons and the centroid fields
   * do not always agree and a focus that lands beside the parcel is worse than
   * no focus. Rings are treated as geographic (lon, lat) and averaged, with the
   * ring closed by repeating the first point, so that duplicate is not counted
   * twice and biases the mean.
   *
    * `lastFocused` guards against re-flying: the effect also re-runs whenever
    * `parcels` is refetched, and flying the camera on every background refresh
    * would yank the view out from under someone who had panned away.
    *
    * The guard is keyed on the *pair* (ULPIN, focusToken), not the ULPIN alone.
    * Keying on the ULPIN alone made a deliberate second "focus this parcel"
    * request a no-op: the effect re-ran, hit the guard, and never flew. Bumping
    * `focusToken` is how the rest of the app asks for a fresh fly-to, so the
    * guard has to notice that. Background `parcels` refetches keep the same
    * token and therefore still do not move the camera.
    */
  const lastFocused = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedUlpin || !mapLoaded) return;
    const focusKey = `${selectedUlpin}::${focusToken}`;
    if (lastFocused.current === focusKey) return;
    const map = mapRef.current;
    if (!map || !parcels || !parcels.length) return;

    const parcel = parcels.find((p) => p.ulpin === selectedUlpin);
    if (!parcel) return;

    const ring: number[][] | null = Array.isArray(parcel.polygon_geojson?.coordinates?.[0])
      ? parcel.polygon_geojson.coordinates[0]
      : null;
    if (!ring || ring.length < 3) return;

    const closed = ring.length > 1 &&
      ring[0][0] === ring[ring.length - 1][0] &&
      ring[0][1] === ring[ring.length - 1][1];
    const raw = closed ? ring.slice(0, -1) : ring;

    // Drop unusable vertices up front so a single bad pair cannot poison the
    // centroid with NaN/Infinity and leave the camera at an invalid centre.
    const pts = raw
      .map((pt) => [Number(pt?.[0]), Number(pt?.[1])] as [number, number])
      .filter(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat));
    if (!pts.length) return;

    // Area-weighted (shoelace) centroid rather than a plain vertex mean. A
    // mean of the ring's vertices lands outside concave plots — very common for
    // narrow or L-shaped cadastral parcels — which parks the camera in a
    // neighbour's field. Falls back to the vertex mean if the ring is
    // degenerate (collinear or zero area).
    let area2 = 0;
    let cx = 0;
    let cy = 0;
    for (let i = 0; i < pts.length; i += 1) {
      const [x1, y1] = pts[i];
      const [x2, y2] = pts[(i + 1) % pts.length];
      const cross = x1 * y2 - x2 * y1;
      area2 += cross;
      cx += (x1 + x2) * cross;
      cy += (y1 + y2) * cross;
    }
    const center: [number, number] = Math.abs(area2) > 1e-12
      ? [cx / (3 * area2), cy / (3 * area2)]
      : [
        pts.reduce((sum, p) => sum + p[0], 0) / pts.length,
        pts.reduce((sum, p) => sum + p[1], 0) / pts.length,
      ];
    if (!Number.isFinite(center[0]) || !Number.isFinite(center[1])) return;

    // Zoom to the parcel's own extent rather than a fixed level, so a large
    // plot and a small one are both framed. Clamped so a single-point or
    // degenerate ring does not slam the camera to maximum zoom.
    const lons = pts.map((pt) => pt[0]);
    const lats = pts.map((pt) => pt[1]);
    const spanLon = Math.max(...lons) - Math.min(...lons);
    const spanLat = Math.max(...lats) - Math.min(...lats);
    const span = Math.max(spanLon, spanLat);
    const zoom = span > 0
      ? Math.min(19, Math.max(15, Math.log2(360 / Math.max(span * 4, 0.0001))))
      : 17;

    lastFocused.current = focusKey;
    map.flyTo({
      center,
      zoom,
      pitch: perspective === '3d' ? 58 : 0,
      duration: 1400,
      essential: true,
    });
  }, [selectedUlpin, focusToken, mapLoaded, parcels, perspective]);

  const handleFlyToRegion = (region: typeof REGION_PRESETS[0]) => {
    setActiveRegion(region.id);
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({
      center: region.center,
      zoom: region.zoom,
      pitch: perspective === '3d' ? Math.max(region.pitch, 35) : 0,
      duration: 1800,
      essential: true,
    });
  };

  // Convert parcels to Deck.gl 3D InspectedStructures
  useEffect(() => {
    if (!parcels || !parcels.length) return;
    const SCALE = 0.000009;
    const ANCHOR = [160, 152.5];
    const toLngLat = (x: number, y: number): [number, number] => [
      AIROLI_CENTER[0] + (x - ANCHOR[0]) * SCALE,
      AIROLI_CENTER[1] - (y - ANCHOR[1]) * SCALE,
    ];

    const structures: InspectedStructure[] = [];

    for (const p of parcels) {
      const ring = p.polygon_geojson?.coordinates?.[0];
      if (!ring || ring.length < 3) continue;

      const isLocal = Math.abs(ring[0][0]) < 1000 && Math.abs(ring[0][1]) < 1000;
      const coords: number[][] = isLocal
        ? ring.map((pt: number[]) => toLngLat(pt[0], pt[1]))
        : ring.map((pt: number[]) => [pt[0], pt[1]]);
      if (coords.length < 4) continue;

      // Read what the record states, substitute nothing. The old chain gave
      // every parcel 4 floors (6 for one hardcoded ULPIN), a height of
      // floors * 3.5, and an FSI of 1.85, then extruded all of it in 3D and
      // labelled it 'Shree Ganesh CHS (B-17)'.
      const floors = (p as any).floors ?? (p.building?.floors) ?? null;
      const heightM = (p as any).height_m ?? (p.building?.height_m) ?? null;
      const fsi = (p as any).fsi ?? null;

      structures.push({
        id: p.ulpin,
        name: p.survey_number ? `Parcel ${p.survey_number}` : `National Cadastre ${p.ulpin}`,
        buildingType: (p as any).building?.type ?? null,
        floorsCount: floors,
        heightM,
        coordinates: [coords],
        fsi,
        // Null first: `null > 2.0` is false, so an unknown FSI fell through to
        // the 'PASS' branch and every parcel with no FSI was marked compliant.
        fsiStatus: fsi === null ? undefined : fsi > 2.0 ? 'EXCEEDED' : 'PASS',
        source: p.ulpin.length === 14 ? 'OFFICIAL_CADASTRE' : 'SYNTHETIC_TWIN',
        ulpin: p.ulpin,
        centroid: coords[0] as [number, number],
      });
    }

    setDeckStructures((prev) => {
      const existingOsm = prev.filter((s) => s.source === 'OPEN_STREET_MAP');
      return [...structures, ...existingOsm];
    });
  }, [parcels]);

  // Live OpenStreetMap Overpass streaming when enabled
  useEffect(() => {
    if (!mapRef.current || !liveOsmEnabled) return;
    const map = mapRef.current;

    let timeoutId: any = null;
    const handleMove = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(async () => {
        const zoom = map.getZoom();
        if (zoom < 14) return;
        const bounds = map.getBounds();
        const bboxStr = `${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}`;

        setOsmLoading(true);
        try {
          const fc = await fetchOSMBuildings(bboxStr);
          if (fc.features.length > 0) {
            const osmStructures: InspectedStructure[] = fc.features.map((f) => ({
              id: String(f.id),
              name: f.properties.name,
              buildingType: f.properties.building_type,
              floorsCount: f.properties.floors_count,
              heightM: f.properties.height_m,
              coordinates: f.geometry.coordinates as number[][][],
              source: 'OPEN_STREET_MAP' as const,
              ulpin: `OSM-${f.properties._osm_id}`,
              centroid: f.properties.centroid,
            }));

            setDeckStructures((prev) => {
              const seen = new Set(prev.map((s) => s.id));
              const newItems = osmStructures.filter((s) => !seen.has(s.id));
              return [...prev, ...newItems].slice(0, 5000);
            });
          }
        } catch (err) {
          console.warn('Live OSM fetch error:', err);
        } finally {
          setOsmLoading(false);
        }
      }, 1000);
    };

    map.on('moveend', handleMove);
    if (map.isStyleLoaded()) handleMove();

    return () => {
      clearTimeout(timeoutId);
      map.off('moveend', handleMove);
    };
  }, [liveOsmEnabled]);

  // Dynamic Locality Text Labels on MapLibre
  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;

    let timeoutId: any = null;
    const handleLocalityLabels = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(async () => {
        const zoom = map.getZoom();
        if (zoom < 10) return;
        const bounds = map.getBounds();
        const bboxStr = `${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}`;

        try {
          const fc = await fetchLocalityLabels(bboxStr);
          if (!map.isStyleLoaded()) return;

          if (map.getSource('locality-labels-source')) {
            (map.getSource('locality-labels-source') as any).setData(fc);
          } else {
            map.addSource('locality-labels-source', {
              type: 'geojson',
              data: fc as any,
            });

            if (!map.getLayer('locality-labels-text')) {
              map.addLayer({
                id: 'locality-labels-text',
                type: 'symbol',
                source: 'locality-labels-source',
                layout: {
                  'text-field': ['get', 'name'],
                  'text-size': [
                    'interpolate', ['linear'], ['zoom'],
                    10, 11,
                    13, 14,
                    16, 18,
                  ],
                  'text-transform': 'uppercase',
                  'text-letter-spacing': 0.12,
                  'text-anchor': 'center',
                },
                paint: {
                  'text-color': '#f8fafc',
                  'text-halo-color': 'rgba(15, 23, 42, 0.95)',
                  'text-halo-width': 2.5,
                  'text-halo-blur': 1,
                },
              });
            }
          }
        } catch {
          // ignore
        }
      }, 1200);
    };

    map.on('moveend', handleLocalityLabels);
    if (map.isStyleLoaded()) handleLocalityLabels();

    return () => {
      clearTimeout(timeoutId);
      map.off('moveend', handleLocalityLabels);
    };
  }, []);

  const handleSelectStructure = (s: InspectedStructure) => {
    setSelectedStructure(s);
    setIsExploded(false);
    setSelectedFloor(null);
    if (s.ulpin) {
      onSelectParcel?.(s.ulpin);
    }
  };

  const handleToggleExplode = () => {
    const next = !isExploded;
    setIsExploded(next);
    setSelectedFloor(null);
    if (next && mapRef.current && selectedStructure?.centroid) {
      mapRef.current.easeTo({
        center: selectedStructure.centroid,
        pitch: 62,
        bearing: -24,
        zoom: Math.max(mapRef.current.getZoom(), 17.2),
        duration: 1000,
      });
    }
  };

  useEffect(() => {
    if (!mapContainerRef.current) return;

    const protocol = window.location.protocol;
    const host = window.location.host;
    const tileBaseUrl = `${protocol}//${host}/api/v1/tiles/{z}/{x}/{y}.pbf?layers=state,district,taluka,village,parcel,twin`;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          'osm-raster': {
            type: 'raster',
            tiles: [
              // CARTO's basemaps rather than tile.openstreetmap.org. The
              // public OSM tile server is not a general-purpose basemap host:
              // its usage policy reserves it for low-volume use with a
              // identifying User-Agent, which an interactive application is
              // not. CARTO serves the same OpenStreetMap data for this use.
              // Single host: MapLibre does not substitute a {s} subdomain
              // placeholder the way Mapbox GL does.
              // cartoTile appends VITE_CARTO_API_KEY. CARTO raster basemaps
              // now require one and answer keyless requests with a flat grey
              // placeholder at HTTP 200, so without this the cadastral basemap
              // silently draws nothing. The style name comes from the user's
              // light/dark and label choice; the single-host template keeps the
              // `{r}` suffix MapLibre resolves itself.
              ...basemapTileUrl(basemapStyleFor(basemapPref), {
                subdomains: ['a', 'b', 'c'],
                retina: 'maplibre',
              }),
            ],
            tileSize: 256,
            // These tiles are OpenStreetMap data through CARTO, and nothing
            // else. The previous string also credited the Survey of India,
            // which contributed no tile to this basemap.
            attribution: '© OpenStreetMap contributors © CARTO',
          },
          'national-vector-tiles': {
            type: 'vector',
            tiles: [tileBaseUrl],
            minzoom: 0,
            maxzoom: 16,
          },
        },
        layers: [
          {
            id: 'osm-base',
            type: 'raster',
            source: 'osm-raster',
            minzoom: 0,
            maxzoom: 19,
            paint: {
              'raster-saturation': -0.65,
              'raster-contrast': 0.15,
              'raster-brightness-max': 0.7,
            },
          },
          // All-India State boundaries
          {
            id: 'state-fill',
            type: 'fill',
            source: 'national-vector-tiles',
            'source-layer': 'state',
            paint: {
              'fill-color': '#3b82f6',
              'fill-opacity': 0.05,
            },
          },
          {
            id: 'state-line',
            type: 'line',
            source: 'national-vector-tiles',
            'source-layer': 'state',
            paint: {
              'line-color': '#1d4ed8',
              'line-width': ['interpolate', ['linear'], ['zoom'], 4, 1.2, 8, 2.5],
              'line-opacity': 0.85,
            },
          },
          // District Boundaries
          {
            id: 'district-line',
            type: 'line',
            source: 'national-vector-tiles',
            'source-layer': 'district',
            minzoom: 5,
            paint: {
              'line-color': '#475569',
              'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.8, 10, 1.8],
              'line-dasharray': [3, 2],
              'line-opacity': 0.75,
            },
          },
          // Taluka / Tahsil Boundaries
          {
            id: 'taluka-line',
            type: 'line',
            source: 'national-vector-tiles',
            'source-layer': 'taluka',
            minzoom: 8,
            paint: {
              'line-color': '#64748b',
              'line-width': 0.8,
              'line-dasharray': [2, 1],
              'line-opacity': 0.6,
            },
          },
          // Village Boundaries
          {
            id: 'village-line',
            type: 'line',
            source: 'national-vector-tiles',
            'source-layer': 'village',
            minzoom: 11,
            paint: {
              'line-color': '#94a3b8',
              'line-width': 0.6,
              'line-opacity': 0.5,
            },
          },
          // 44,323 National Parcels
          {
            id: 'parcel-fill',
            type: 'fill',
            source: 'national-vector-tiles',
            'source-layer': 'parcel',
            minzoom: 10,
            paint: {
              'fill-color': [
                'case',
                ['==', ['get', 'zonal_class'], 'AGRI'],
                '#10b981',
                ['==', ['get', 'zonal_class'], 'COMMERCIAL'],
                '#f59e0b',
                '#3b82f6',
              ],
              'fill-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.2, 14, 0.45],
            },
          },
          {
            id: 'parcel-line',
            type: 'line',
            source: 'national-vector-tiles',
            'source-layer': 'parcel',
            minzoom: 10,
            paint: {
              'line-color': '#1e293b',
              'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 14, 1.2],
            },
          },
          // 44,323 National 3D Twins (Hardware-Accelerated WebGL Extrusion)
          {
            id: 'twin-extrusion',
            type: 'fill-extrusion',
            source: 'national-vector-tiles',
            'source-layer': 'twin',
            minzoom: 10,
            paint: {
              'fill-extrusion-color': [
                'case',
                ['==', ['get', 'fsi_status'], 'EXCEEDED'],
                '#ef4444',
                ['==', ['get', 'fsi_status'], 'PASS'],
                '#10b981',
                '#06b6d4',
              ],
              'fill-extrusion-height': [
                'coalesce',
                ['get', 'height_m'],
                ['*', ['coalesce', ['get', 'floors'], 3], 3.2],
                12,
              ],
              'fill-extrusion-base': 0,
              'fill-extrusion-opacity': 0.88,
            },
          },
          {
            id: 'twin-line',
            type: 'line',
            source: 'national-vector-tiles',
            'source-layer': 'twin',
            minzoom: 10,
            paint: {
              'line-color': '#0f172a',
              'line-width': 1.6,
            },
          },
        ],
      },
      center: WORLD_CENTER,
      zoom: WORLD_ZOOM,
      pitch: 0,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
    mapRef.current = map;

    map.on('load', () => {
      setMapLoaded(true);

      // Add Airoli Local Fallback Parcels if provided
      if (parcels && parcels.length) {
        const SCALE = 0.000009;
        const ANCHOR = [160, 152.5];
        const toLngLat = (x: number, y: number): [number, number] => [
          AIROLI_CENTER[0] + (x - ANCHOR[0]) * SCALE,
          AIROLI_CENTER[1] - (y - ANCHOR[1]) * SCALE,
        ];

        const localFeatures: GeoJSON.Feature[] = parcels
          .map((p) => {
            const ring = p.polygon_geojson?.coordinates?.[0];
            if (!ring || ring.length < 3) return null;
            const coords = ring.slice(0, -1).map((pt: number[]) => toLngLat(pt[0], pt[1]));
            coords.push(coords[0]);
            return {
              type: 'Feature' as const,
              properties: {
                ulpin: p.ulpin,
                name: p.survey_number || p.ulpin,
                status: p.status,
                has_3d: !!p.building?.has_3d,
                isHero: p.ulpin === DEMO_ULPIN,
                isPilotLocal: true,
              },
              geometry: { type: 'Polygon' as const, coordinates: [coords] },
            };
          })
          .filter(Boolean) as GeoJSON.Feature[];

        map.addSource('airoli-local-parcels', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: localFeatures },
        });

        map.addLayer({
          id: 'airoli-parcels-fill',
          type: 'fill',
          source: 'airoli-local-parcels',
          paint: {
            // Honest per-status colouring. A builder-asserted parcel awaiting
            // survey is amber, a conflicting one red, and a parcel carrying a
            // real persisted structure is teal, so a drawn building is
            // distinguishable from an ingested or empty lot. None of these
            // imply approval.
            'fill-color': [
              'case',
              ['==', ['get', 'isHero'], true], '#2563eb',
              ['==', ['get', 'status'], 'CONFLICT'], '#ef4444',
              ['==', ['get', 'status'], 'PENDING_SURVEY'], '#f59e0b',
              ['==', ['get', 'has_3d'], true], '#0d9488',
              '#6366f1',
            ],
            'fill-opacity': 0.45,
          },
        });
        map.addLayer({
          id: 'airoli-parcels-line',
          type: 'line',
          source: 'airoli-local-parcels',
          paint: {
            'line-color': [
              'case',
              ['==', ['get', 'has_3d'], true], '#0f766e',
              '#1e1b4b',
            ],
            'line-width': 2,
          },
        });

        map.on('click', 'airoli-parcels-fill', (e) => {
          const f = e.features?.[0];
          if (f?.properties?.ulpin) {
            onSelectParcel?.(f.properties.ulpin as string);
            setInspectedEntity({
              type: 'LOCAL_PARCEL',
              ulpin: f.properties.ulpin,
              name: f.properties.name,
              status: f.properties.status,
            });
          }
        });
      }

      // Subsurface Clash Marker at Airoli
      if (hasClash) {
        const el = document.createElement('div');
        el.className = 'w-5 h-5 rounded-full bg-red-600 border-2 border-white shadow-xl cursor-pointer animate-pulse';
        el.title = 'Subsurface clash: NMMC 600mm trunk main';
        new maplibregl.Marker({ element: el }).setLngLat(AIROLI_CENTER).addTo(map);
      }

      // Click Interaction for National Vector Parcels & Twins
      map.on('click', 'parcel-fill', (e) => {
        const f = e.features?.[0];
        if (f?.properties) {
          const p = f.properties;
          setInspectedEntity({
            type: 'NATIONAL_PARCEL',
            ulpin: p.ulpin,
            survey_number: p.survey_number,
            zonal_class: p.zonal_class,
            state_code: p.state_code,
          });
          if (p.ulpin) onSelectParcel?.(p.ulpin as string);
        }
      });

      map.on('click', 'twin-extrusion', (e) => {
        const f = e.features?.[0];
        if (f?.properties) {
          const t = f.properties;
          setInspectedEntity({
            type: 'NATIONAL_TWIN',
            ulpin: t.ulpin,
            structure_code: t.structure_code,
            height_m: t.height_m,
            floors: t.floors,
            fsi: t.fsi,
            fsi_status: t.fsi_status,
          });
          if (t.ulpin) onSelectParcel?.(t.ulpin as string);
        }
      });

      // Click on State or District: zoom into that jurisdiction
      map.on('click', 'state-fill', (e) => {
        const f = e.features?.[0];
        if (f?.properties?.name) {
          map.flyTo({ center: e.lngLat, zoom: 6.8, duration: 1200 });
        }
      });

      // Pointer cursor on interactive layers
      const interactiveLayers = ['state-fill', 'parcel-fill', 'twin-extrusion', 'airoli-parcels-fill'];
      interactiveLayers.forEach((l) => {
        map.on('mouseenter', l, () => {
          map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', l, () => {
          map.getCanvas().style.cursor = '';
        });
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasClash]);

  // Handle mapFocus for smooth camera flight across India
  /* Load sub-grade only when the option is switched on. Doing it eagerly would
     add a request to every atlas load for a layer most sessions never open. */
  useEffect(() => {
    if (!undergroundOn || subgrade) return;
    let cancelled = false;
    setSubgradeLoading(true);
    setSubgradeError(null);
    fetchSubgrade()
      .then((res) => {
        if (!cancelled) setSubgrade(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setSubgradeError(
          err instanceof Error ? err.message : 'Sub-grade record unavailable',
        );
      })
      .finally(() => {
        if (!cancelled) setSubgradeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [undergroundOn, subgrade]);

  /* Draw the sub-grade footprints. They are real lon/lat already - the server
     converts the pilot's local metres with the same transform the OSM
     decorations use - so nothing is placed by arithmetic here. */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !undergroundOn || !subgrade) return;

    const data: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: subgrade.subgrade_units.map((u) => ({
        type: 'Feature',
        properties: {
          unit: u.unit_number,
          use: u.unit_type,
          min_z: u.min_z,
          max_z: u.max_z,
          area: u.carpet_area_m2,
          synthetic: subgrade.provenance.is_synthetic,
        },
        geometry: u.footprint_geojson as unknown as GeoJSON.Geometry,
      })),
    };

    if (map.getSource('subgrade')) {
      (map.getSource('subgrade') as maplibregl.GeoJSONSource).setData(data);
    } else {
      map.addSource('subgrade', { type: 'geojson', data });
      map.addLayer({
        id: 'subgrade-fill',
        type: 'fill',
        source: 'subgrade',
        paint: { 'fill-color': '#00843D', 'fill-opacity': 0.45 },
      });
      map.addLayer({
        id: 'subgrade-line',
        type: 'line',
        source: 'subgrade',
        paint: { 'line-color': '#00843D', 'line-width': 2.5 },
      });
    }
  }, [undergroundOn, subgrade, mapLoaded]);

  /* Switching the option off empties the map rather than leaving a hidden
     layer behind: a layer that is only invisible is still in the scene, and
     the next toggle would have to reason about which of the two it inherited. */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || undergroundOn) return;
    ['subgrade-fill', 'subgrade-line'].forEach((id) => {
      if (map.getLayer(id)) map.removeLayer(id);
    });
    if (map.getSource('subgrade')) {
      map.removeSource('subgrade');
      setSubgrade(null);
    }
  }, [undergroundOn, mapLoaded]);

  /**
   * Swap the basemap tiles in place when the light/dark or label choice
   * changes. Replacing the source's `tiles` array avoids setStyle, which would
   * drop every layer added after load -- the national vector parcels, the
   * Airoli demo geometry, the subgrade fill -- and reset the camera. The
   * previous tiles stay on screen while the new ones load, so there is no
   * flash of empty map.
   */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    saveBasemapPref('cadastre', basemapPref);
    const src = map.getSource('osm-raster') as maplibregl.RasterTileSource | undefined;
    if (!src) return;
    src.setTiles(
      basemapTileUrl(basemapStyleFor(basemapPref), { subdomains: ['a', 'b', 'c'], retina: 'maplibre' }),
    );
  }, [basemapPref, mapLoaded]);

  // Handle mapFocus for smooth camera flight across India
  useEffect(() => {
    if (!mapRef.current || !mapLoaded || !mapFocus) return;
    const map = mapRef.current;
    // 1. Format: geo:lng,lat,zoom:id
    if (mapFocus.startsWith('geo:')) {
      const rest = mapFocus.slice(4);
      const parts = rest.split(':');
      const coords = parts[0].split(',');
      const lng = parseFloat(coords[0]);
      const lat = parseFloat(coords[1]);
      const zoom = coords[2] ? parseFloat(coords[2]) : 15.5;
      const targetId = parts[1] || '';
      if (!isNaN(lng) && !isNaN(lat)) {
        map.flyTo({
          center: [lng, lat],
          zoom,
          pitch: perspective === '3d' ? 58 : 0,
          bearing: perspective === '3d' ? -18 : 0,
          duration: 1500,
        });
        if (targetId) {
          setInspectedEntity({
            type: targetId.startsWith('TWIN-') ? 'NATIONAL_TWIN' : 'NATIONAL_PARCEL',
            ulpin: targetId.replace('TWIN-', ''),
          });
        }
      }
      return;
    }

    // 2. Preset region check
    const preset = REGION_PRESETS.find((r) => r.id === mapFocus.toLowerCase());
    if (preset) {
      handleFlyToRegion(preset);
      return;
    }

    // 3. Real place fallback: LGD villages publish no geometry, so a village
    // focus has to be geocoded before the camera can move. Tried before the
    // generated indices because in `all` mode a generated row would otherwise
    // win the ranking and fly the user to a fabricated boundary.
    const flyToBySearch = async (query: string): Promise<boolean> => {
      try {
        const res = await searchProperties(query);
        const top = res.results?.[0];
        if (!top?.lng || !top?.lat) return false;
        map.flyTo({
          center: [top.lng, top.lat],
          zoom: top.zoom || 15.5,
          pitch: perspective === '3d' ? 58 : 0,
          bearing: perspective === '3d' ? -18 : 0,
          duration: 1500,
        });
        setInspectedEntity({
          type:
            top.kind === 'structure'
              ? 'NATIONAL_TWIN'
              : top.kind === 'jurisdiction'
              ? 'ADMIN_BOUNDARY'
              : 'NATIONAL_PARCEL',
          ulpin: top.ulpin || top.id,
          name: top.title,
          survey_number: (top as any).survey_number,
          height_m: (top as any).height_m,
          floors: (top as any).floors,
          fsi: (top as any).fsi,
          fsi_status: top.status,
          state_code: (top as any).state_code,
        });
        return true;
      } catch {
        // An unresolvable focus is not an error worth surfacing: the map simply
        // stays where it is.
        return false;
      }
    };

    const trimmedFocus = mapFocus.trim();
    if (trimmedFocus.length === 0) return;

    let cancelled = false;
    void (async () => {
      try {
        const res = await searchProperties(trimmedFocus, 'places');
        const village = res.results?.[0];
        if (cancelled || village?.source !== 'lgd') return;
        const located = await locateLgdVillage(village.village_code);
        if (cancelled) return;
        if (located?.found && typeof located.lon === 'number' && typeof located.lat === 'number') {
          map.flyTo({
            center: [located.lon, located.lat],
            zoom: village.zoom || 15,
            pitch: perspective === '3d' ? 58 : 0,
            bearing: perspective === '3d' ? -18 : 0,
            duration: 1500,
          });
          return;
        }
      } catch {
        // Fall through to the generated indices.
      }
      if (!cancelled) await flyToBySearch(mapFocus);
    })();

    return () => {
      cancelled = true;
    };
  }, [mapFocus, mapLoaded, perspective]);

  return (
    <div className="relative w-full h-full bg-slate-900 overflow-hidden rounded-2xl border border-slate-200/80 shadow-line">
      {/* Map Container */}
      <div ref={mapContainerRef} className="w-full h-full" />

      {/* Progress bar at the top, instead of the full-screen overlay that used
          to sit here.

          That overlay was `bg-slate-950/70 backdrop-blur-sm` over the entire
          map, so the thing the user was waiting for was hidden by the wait
          message, and any attempt to look around was blocked. It also only
          covered first load: once the style loaded, later tile and vector
          fetches had no indicator at all, which is when people start panning
          mid-request and cancelling it.

          The bar is non-blocking, covers every fetch rather than just the first,
          and says "please wait, do not pan" once a request has been slow long
          enough that the wait is the thing worth explaining. */}
      <MapLoadingBar
        map={mapLoaded ? mapRef.current : null}
        extraLoading={osmLoading}
        label="Loading cadastral vector tiles (PostGIS MVT)"
      />

      {/* The pulsing dot for whatever Ask-The-Map last highlighted. Gated on
          mapLoaded rather than on the ref, because the ref is set during the
          first effect and nothing re-renders to hand a child the instance. */}
      {mapLoaded && <HighlightPointer map={mapRef.current} pitch={perspective === '3d' ? 58 : 0} />}

      {/* Deck.gl 3D Interleaved Extrusion & Exploded Floor Slicing Overlay */}
      {mapLoaded && mapRef.current && (
        <DeckGL3DOverlay
          map={mapRef.current}
          structures={deckStructures}
          selectedId={selectedStructure?.id || null}
          isExploded={isExploded}
          selectedFloor={selectedFloor}
          colorMode={colorMode}
          onSelectStructure={handleSelectStructure}
          onSelectFloor={(floor) => setSelectedFloor(floor)}
        />
      )}

      {/* Top Header HUD: National Cadastre Indicator & Controls */}
      <div className="absolute top-3 left-3 right-14 flex flex-wrap items-center justify-between gap-2 pointer-events-none z-10">
        <div className="flex items-center gap-2 pointer-events-auto flex-wrap">
          <div className="bg-slate-900/95 text-white border border-slate-700/80 px-3 py-1.5 rounded-xl text-xs font-mono backdrop-blur-md shadow-lg flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-bold tracking-tight">ALL-INDIA 3D CADASTRAL ATLAS</span>
            <span className="text-[10px] text-slate-400 hidden sm:inline">· 15,091 ADMIN BOUNDARIES · 44,323 PARCELS</span>
          </div>

          {/* Perspective View Toggle */}
          <button
            onClick={() => {
              const next = perspective === '3d' ? '2d' : '3d';
              setPerspective(next);
              const map = mapRef.current;
              if (map) {
                map.easeTo({
                  pitch: next === '3d' ? 58 : 0,
                  bearing: next === '3d' ? -18 : 0,
                  duration: 900,
                });
              }
            }}
            className={`px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition flex items-center gap-1.5 border shadow-md ${
              perspective === '3d'
                ? 'bg-emerald-600 text-ink border-emerald-400'
                : 'bg-white/95 text-slate-800 border-slate-200 hover:bg-white'
            }`}
          >
            <Boxes className="w-3.5 h-3.5" />
            <span>{perspective === '3d' ? '3D View (58°)' : '2D Plan'}</span>
          </button>

          {/* Basemap light/dark + place labels. Sits with the other map
              presentation controls and themes itself off the current basemap so
              it stays legible on either ground. */}
          <BasemapModeToggle pref={basemapPref} onChange={setBasemapPref} theme={basemapPref.theme} />

          {/* Thematic 3D Color Mode Dropdown */}
          <div className="bg-slate-900/95 text-white border border-slate-700/80 rounded-xl p-0.5 flex items-center gap-0.5 text-xs font-mono backdrop-blur-md shadow-md">
            <span className="px-2 text-slate-400 flex items-center gap-1 text-[11px]">
              <Palette className="w-3 h-3 text-cyan-400" />
            </span>
            {(['height', 'landuse', 'fsi', 'lineage'] as DeckGLColorMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setColorMode(mode)}
                className={`px-2 py-1 rounded-lg text-[10px] font-bold uppercase transition ${
                  colorMode === mode
                    ? 'bg-cyan-600 text-ink shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                {mode === 'landuse' ? 'Zoning' : mode === 'lineage' ? 'Lineage' : mode}
              </button>
            ))}
          </div>

          {/* Live OpenStreetMap Overpass Streaming Toggle */}
          <button
            onClick={() => setLiveOsmEnabled(!liveOsmEnabled)}
            className={`px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition flex items-center gap-1.5 border shadow-md ${
              liveOsmEnabled
                ? 'bg-sky-600 text-white border-sky-400 ring-2 ring-sky-400/30'
                : 'bg-slate-900/90 text-slate-300 border-slate-700 hover:bg-slate-800'
            }`}
            title="Stream live OSM building footprints dynamically from Overpass API when panning"
          >
            {osmLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-sky-300" />
            ) : (
              <Globe2 className="w-3.5 h-3.5" />
            )}
            <span>Live OSM Stream</span>
            {liveOsmEnabled && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />}
          </button>

          <button
            onClick={() => setShowThematicViz(!showThematicViz)}
            className={`px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition flex items-center gap-1.5 border shadow-md ${
              showThematicViz
                ? 'bg-indigo-600 text-white border-indigo-400'
                : 'bg-white/95 text-slate-800 border-slate-200 hover:bg-white'
            }`}
          >
            <Filter className="w-3.5 h-3.5" />
            <span>Thematic Viz</span>
          </button>
        </div>

        {/* Layer Visibility Toggles */}
        <div className="hidden lg:flex items-center gap-1 bg-slate-900/90 border border-slate-700/80 p-1 rounded-xl text-[11px] font-mono text-white pointer-events-auto backdrop-blur-md shadow-md">
          <button
            onClick={() => toggleLayerVisibility('states')}
            className={`px-2 py-0.5 rounded-lg transition ${
              visibleLayers.states ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            States
          </button>
          <button
            onClick={() => toggleLayerVisibility('districts')}
            className={`px-2 py-0.5 rounded-lg transition ${
              visibleLayers.districts ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            Districts
          </button>
          <button
            onClick={() => toggleLayerVisibility('parcels')}
            className={`px-2 py-0.5 rounded-lg transition ${
              visibleLayers.parcels ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            Parcels (44k)
          </button>
          <button
            onClick={() => toggleLayerVisibility('twins')}
            className={`px-2 py-0.5 rounded-lg transition ${
              visibleLayers.twins ? 'bg-emerald-600 text-ink' : 'text-slate-400 hover:text-white'
            }`}
          >
            3D Twins
          </button>
          {/* Underground is a layer rather than a visibility toggle: it is not
              in the style at all until it is asked for, because the atlas
              carries no sub-grade geometry of its own. */}
          <button
            onClick={() => setUndergroundOn((v) => !v)}
            aria-pressed={undergroundOn}
            data-testid="atlas-underground-toggle"
            className={`px-2 py-0.5 rounded-lg transition flex items-center gap-1 ${
              undergroundOn ? 'bg-emerald-700 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {subgradeLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Layers className="w-3 h-3" />}
            Underground
          </button>
        </div>
      </div>

      {/* Region Preset Quick-Jump Bar (Bottom Center) */}
      <div className="absolute bottom-4 left-4 right-4 flex items-center justify-center pointer-events-none z-10">
        <div className="flex items-center gap-1 overflow-x-auto max-w-[95vw] p-1.5 bg-slate-900/95 border border-slate-700/80 rounded-2xl shadow-2xl backdrop-blur-md pointer-events-auto">
          {REGION_PRESETS.map((r) => (
            <button
              key={r.id}
              onClick={() => handleFlyToRegion(r)}
              className={`px-2.5 py-1 rounded-xl text-xs font-mono whitespace-nowrap transition ${
                activeRegion === r.id
                  ? 'bg-blue-600 text-white font-bold shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Floating Thematic Visualization Panel */}
      {showThematicViz && mapRef.current && (
        <div className="absolute top-14 left-3 z-20 max-w-sm animate-rise-in">
          <NationalVizPanel map={mapRef.current} level="STATE" />
        </div>
      )}

      {/* Sub-grade status. This layer is the one place in the atlas that can
          be empty for a reason, and the reason has to be stated rather than
          left as a blank map: either the parcel has no sub-grade record, or
          what exists is the demonstration pilot's synthetic geometry and is
          not a survey. */}
      {undergroundOn && !subgradeLoading && !subgradeError && subgrade && (
        <div
          data-testid="atlas-underground-status"
          className="absolute top-16 right-4 z-20 bg-slate-900/90 backdrop-blur-md border border-emerald-700/70 rounded-xl p-2.5 shadow-xl max-w-[17rem] text-[11px]"
        >
          <p className="font-mono text-[10px] uppercase tracking-wide text-emerald-400 font-bold">
            Sub-grade
          </p>
          {subgrade.count === 0 ? (
            <p className="text-slate-300 mt-1 leading-snug">
              {subgrade.note || 'No sub-grade record for this parcel.'}
            </p>
          ) : (
            <>
              <p className="text-slate-200 mt-1 leading-snug">
                {subgrade.count} unit{subgrade.count === 1 ? '' : 's'} at or below datum.
              </p>
              <ul className="mt-1 space-y-0.5 text-slate-300 font-mono text-[10px]">
                {subgrade.subgrade_units.map((u) => (
                  <li key={u.unit_number}>
                    {u.unit_number} · {u.unit_type} · {u.min_z}→{u.max_z} m
                  </li>
                ))}
              </ul>
              {subgrade.provenance.is_synthetic && (
                <p className="mt-1.5 text-amber-300/90 leading-snug">
                  Demonstration geometry, not surveyed. Basement counts in this
                  deployment are derived.
                </p>
              )}
            </>
          )}
        </div>
      )}
      {undergroundOn && subgradeError && (
        <div
          data-testid="atlas-underground-status"
          className="absolute top-16 right-4 z-20 bg-slate-900/90 backdrop-blur-md border border-rose-700/70 rounded-xl p-2.5 shadow-xl max-w-[17rem] text-[11px] text-rose-200"
        >
          Sub-grade record unavailable: {subgradeError}
        </div>
      )}

      {/* 2D Cadastral Feature HUD */}
      {inspectedEntity && !selectedStructure && (
        <div className="absolute top-16 left-4 z-20 bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-xl p-3 shadow-xl max-w-xs text-xs animate-rise-in">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-bold">
              {inspectedEntity.type}
            </span>
            <button
              onClick={() => setInspectedEntity(null)}
              className="text-slate-400 hover:text-white text-xs px-1"
              aria-label="Close"
            >
              &times;
            </button>
          </div>
          <div className="font-mono font-bold text-white truncate">{inspectedEntity.ulpin || inspectedEntity.name || 'Selected Feature'}</div>
          {inspectedEntity.survey_number && (
            <div className="text-slate-300 text-[11px] mt-0.5">Survey: {inspectedEntity.survey_number}</div>
          )}
          {inspectedEntity.height_m && (
            <div className="text-slate-300 text-[11px] mt-0.5">
              Height: {inspectedEntity.height_m}m ·{' '}
              {inspectedEntity.floors ?? '--'}{inspectedEntity.floors != null ? 'F' : ''}
              {inspectedEntity.fsi && <span className="ml-1 text-emerald-400 font-mono font-bold">· FSI {inspectedEntity.fsi}</span>}
            </div>
          )}
          {inspectedEntity.ulpin && (
            <div className="flex items-center gap-2 pt-2.5 mt-2 border-t border-slate-700/80">
              <a
                href={PROPERTY_CARD_PDF_URL(inspectedEntity.ulpin)}
                target="_blank"
                rel="noreferrer"
                className="flex-1 py-1.5 px-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-center font-bold text-[10px] transition flex items-center justify-center gap-1 shadow-sm"
              >
                <Download className="w-3 h-3" /> Property Card
              </a>
              <button
                onClick={() => {
                  if (inspectedEntity.ulpin) onSelectParcel?.(inspectedEntity.ulpin);
                }}
                className="py-1.5 px-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg font-bold text-[10px] transition flex items-center gap-1"
              >
                <ExternalLink className="w-3 h-3 text-cyan-400" /> Inspect 3D
              </button>
            </div>
          )}
        </div>
      )}

      {/* 3D Property Inspector & Exploded Floor Slicing Sheet */}
      <CadastrePropertyInspector
        structure={selectedStructure}
        isExploded={isExploded}
        selectedFloor={selectedFloor}
        onToggleExplode={handleToggleExplode}
        onSelectFloor={(floor) => setSelectedFloor(floor)}
        onClose={() => {
          setSelectedStructure(null);
          setIsExploded(false);
          setSelectedFloor(null);
        }}
      />
    </div>
  );
};
export default MapLibreCadastreMap;