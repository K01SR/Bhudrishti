import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Satellite, Layers, ZoomIn, ZoomOut, Compass, Building2 } from 'lucide-react';
import { fetchOSMBuildings } from '../../services/overpass';
import { MapLoadingBar } from './MapLoadingBar';

const BASE: [number, number] = [72.9984, 19.1557];
const ANCHOR: [number, number] = [160, 152.5];
const SCALE = 0.000009;

function toLngLat(x: number, y: number): [number, number] {
  return [BASE[0] + (x - ANCHOR[0]) * SCALE, BASE[1] - (y - ANCHOR[1]) * SCALE];
}

interface Props {
  center?: [number, number];
  zoom?: number;
  markerLabel?: string;
  onMarkerClick?: () => void;
  className?: string;
}

/**
 * Satellite View powered by Esri World Imagery (0.3m/pixel)
 * with cadastral parcel boundaries and building footprint overlays.
 * Public tile endpoint, no API key and no billing account required.
 */
export const EsriSatelliteView: React.FC<Props> = ({
  center = BASE,
  zoom = 16.5,
  markerLabel = 'B-17 · Shree Ganesh CHS',
  onMarkerClick,
  className = '',
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapInstance, setMapInstance] = useState<maplibregl.Map | null>(null);
  const [, setMapLoaded] = useState(false);
  const [showCadastre, setShowCadastre] = useState(true);
  const [showBuildings, setShowBuildings] = useState(true);
  // Mirrors `showBuildings` for the layer-init effect, whose dependency list
  // must stay `[center]`: adding the toggle state to it would tear down the
  // listeners and refetch the city on every visibility flip.
  const showBuildingsRef = useRef(showBuildings);
  showBuildingsRef.current = showBuildings;
  const [buildingCount, setBuildingCount] = useState(0);
  // Overpass round trip is not a MapLibre source, so the map reports itself idle
  // while the footprint query is still open. Tracked here so the loading bar can
  // cover it; without this the bar flashed idle and disappeared during the only
  // slow part of the view.
  const [osmLoading, setOsmLoading] = useState(false);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          'esri-satellite': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            maxzoom: 19,
            attribution: '© Esri, Maxar, Earthstar Geographics | Bhu-Drishti 3D',
          },
        },
        layers: [
          {
            id: 'satellite-tiles',
            type: 'raster',
            source: 'esri-satellite',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: center,
      zoom: zoom,
      pitch: 35,
      bearing: -15,
    });

    mapRef.current = map;
    setMapInstance(map);

    map.on('load', () => {
      setMapLoaded(true);

      // Hero parcel polygon coordinates (CTS-100 / Building B-17 plot)
      const heroRingRaw = [
        [140, 140],
        [180, 140],
        [180, 165],
        [140, 165],
        [140, 140],
      ];
      const heroCoords = heroRingRaw.map(([x, y]) => toLngLat(x, y));

      // Building B-17 footprint
      const b17FootprintRaw = [
        [145, 144],
        [175, 144],
        [175, 161],
        [145, 161],
        [145, 144],
      ];
      const b17Coords = b17FootprintRaw.map(([x, y]) => toLngLat(x, y));

      // Surrounding pilot parcels
      const p1Raw = [[90, 130], [135, 130], [135, 175], [90, 175], [90, 130]];
      const p2Raw = [[185, 130], [230, 130], [230, 175], [185, 175], [185, 130]];
      const p3Raw = [[140, 170], [180, 170], [180, 210], [140, 210], [140, 170]];

      const features: GeoJSON.Feature[] = [
        {
          type: 'Feature',
          properties: { id: 'hero-parcel', name: 'Parcel CTS-100 (B-17)', isHero: true },
          geometry: { type: 'Polygon', coordinates: [heroCoords] },
        },
        {
          type: 'Feature',
          properties: { id: 'b17-footprint', name: 'Building B-17 Footprint', isBuilding: true },
          geometry: { type: 'Polygon', coordinates: [b17Coords] },
        },
        {
          type: 'Feature',
          properties: { id: 'parcel-1', name: 'Adjacent Parcel West' },
          geometry: { type: 'Polygon', coordinates: [p1Raw.map(([x, y]) => toLngLat(x, y))] },
        },
        {
          type: 'Feature',
          properties: { id: 'parcel-2', name: 'Adjacent Parcel East' },
          geometry: { type: 'Polygon', coordinates: [p2Raw.map(([x, y]) => toLngLat(x, y))] },
        },
        {
          type: 'Feature',
          properties: { id: 'parcel-3', name: 'Adjacent Parcel North' },
          geometry: { type: 'Polygon', coordinates: [p3Raw.map(([x, y]) => toLngLat(x, y))] },
        },
      ];

      map.addSource('cadastre-satellite-overlay', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features },
      });

      // Parcel fill
      map.addLayer({
        id: 'parcel-satellite-fill',
        type: 'fill',
        source: 'cadastre-satellite-overlay',
        paint: {
          'fill-color': [
            'case',
            ['==', ['get', 'isBuilding'], true],
            '#f59e0b',
            ['==', ['get', 'isHero'], true],
            '#0284c7',
            '#38bdf8',
          ],
          'fill-opacity': [
            'case',
            ['==', ['get', 'isBuilding'], true],
            0.45,
            ['==', ['get', 'isHero'], true],
            0.3,
            0.15,
          ],
        },
      });

      // Parcel outline
      map.addLayer({
        id: 'parcel-satellite-line',
        type: 'line',
        source: 'cadastre-satellite-overlay',
        paint: {
          'line-color': [
            'case',
            ['==', ['get', 'isBuilding'], true],
            '#fbbf24',
            ['==', ['get', 'isHero'], true],
            '#38bdf8',
            '#94a3b8',
          ],
          'line-width': ['case', ['==', ['get', 'isBuilding'], true], 2.5, 2],
          'line-opacity': 0.9,
        },
      });

      // Add a customized glowing pin marker at the target location
      const el = document.createElement('div');
      el.className = 'group cursor-pointer';
      el.innerHTML = `
        <div class="relative flex items-center justify-center">
          <div class="absolute -inset-2 bg-sky-500/30 rounded-full animate-ping pointer-events-none"></div>
          <div class="relative flex items-center gap-1.5 bg-slate-900/90 text-sky-400 border border-sky-400/40 px-2.5 py-1 rounded-full shadow-xl backdrop-blur-md text-[11px] font-mono font-bold tracking-tight hover:scale-105 transition-transform">
            <span class="w-2 h-2 rounded-full bg-sky-400 shadow-[0_0_8px_#38bdf8]"></span>
            <span>${markerLabel}</span>
          </div>
        </div>
      `;
      el.addEventListener('click', () => {
        if (onMarkerClick) onMarkerClick();
      });

      new maplibregl.Marker({ element: el })
        .setLngLat(center)
        .addTo(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      setMapInstance(null);
    };
  }, [center[0], center[1], zoom, markerLabel, onMarkerClick]);

  /**
   * 3D-extruded building footprints from OpenStreetMap.
   *
   * This view previously drew five hardcoded polygons, so it was the only map in
   * the app with no city around the parcel: pitched to 35 degrees over imagery
   * and nothing else. It now fetches real OSM footprints for the visible bbox
   * and extrudes them, which is what makes the pitch readable.
   *
   * The height rule is the same honesty constraint used elsewhere in this app:
   * OSM footprints routinely have no `height` and no building levels, and
   * substituting a default would draw every low-rise shed as a tower. So the
   * source value is used when present, and a footprint with neither height nor
   * levels is extruded a single storey -- a real, visibly-flat block that reads
   * as "height unknown" rather than a fabricated number. `height_source` carries
   * which rule applied, so a click can say so.
   *
   * Fetched on `idle` after a pause rather than on every `moveend`: a viewport
   * change during an in-flight query restarts it, which is the lag this view is
   * meant to remove.
   */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    // Register the layer up front, with an empty collection.
    //
    // Adding the source and layer only after a successful fetch meant that when
    // Overpass was unreachable the "3D" button still rendered, but toggled a
    // layer that did not exist: the control silently did nothing, and the
    // empty city looked like a feature of the data rather than a failed fetch.
    // Registering first means the toggle always has something to act on, and
    // "0" on the button means an honest empty result.
    const register = () => {
    if (!map.getLayer('osm-3d-extrusion')) {
      map.addSource('osm-3d-buildings', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] } as GeoJSON.FeatureCollection,
      });
      map.addLayer({
        id: 'osm-3d-extrusion',
        type: 'fill-extrusion',
        source: 'osm-3d-buildings',
        minzoom: 14,
        paint: {
          // A pale, slightly transparent shell. Over imagery this has to stay
          // light: a dark extrusion over a dark orthophoto disappears, and a
          // saturated one hides the imagery it is meant to sit over. Contrast
          // against the roofs comes from the edge, not the fill.
          'fill-extrusion-color': [
            'case',
            ['==', ['get', 'height_source'], 'unknown_default_flat'],
            '#94a3b8',
            '#e2e8f0',
          ],
          'fill-extrusion-height': ['get', 'height'],
          'fill-extrusion-base': 0,
          'fill-extrusion-opacity': 0.55,
        },
      });
      // The outline is what makes the massing legible at this opacity; the fill
      // alone reads as haze.
      map.addLayer({
        id: 'osm-3d-outline',
        type: 'line',
        source: 'osm-3d-buildings',
        minzoom: 14,
        paint: {
          'line-color': '#f8fafc',
          'line-width': 0.6,
          'line-opacity': 0.7,
        },
      });
      const vis = showBuildingsRef.current ? 'visible' : 'none';
      map.setLayoutProperty('osm-3d-extrusion', 'visibility', vis);
      map.setLayoutProperty('osm-3d-outline', 'visibility', vis);
    }
    };

    // `mapRef.current` is assigned synchronously by the init effect, so at this
    // point the map object exists but its style has not finished loading.
    // `addSource` before that throws "Style is not done loading", which is what
    // blanked the whole view. Defer registration to the style's load event, and
    // register immediately only if the style is somehow already ready.
    if (map.isStyleLoaded()) register();
    else map.on('load', register);

    const load = async () => {
      if (cancelled) return;
      // Below z14 an Overpass footprint query over a wide bbox returns far more
      // geometry than the GPU wants for no visible gain.
      if (map.getZoom() < 14) return;
      const b = map.getBounds();
      const bbox = `${b.getSouth()},${b.getWest()},${b.getNorth()},${b.getEast()}`;
      setOsmLoading(true);
      try {
        const fc = await fetchOSMBuildings(bbox);
        if (cancelled) return;
        const features = fc.features.map((f) => {
          const h = typeof f.properties.height_m === 'number' ? f.properties.height_m : null;
          const levels = typeof f.properties.floors_count === 'number' ? f.properties.floors_count : null;
          const height = h ?? (levels !== null ? levels * 3.2 : 4.5);
          return {
            type: 'Feature' as const,
            id: String(f.id),
            geometry: f.geometry,
            properties: {
              id: String(f.id),
              name: f.properties.name || 'OSM building',
              height,
              height_source: h !== null ? 'osm_height' : levels !== null ? 'osm_levels_x3.2' : 'unknown_default_flat',
            },
          };
        });
        if (cancelled) return;
        const src = map.getSource('osm-3d-buildings') as maplibregl.GeoJSONSource | undefined;
        src?.setData({ type: 'FeatureCollection', features } as GeoJSON.FeatureCollection);
        setBuildingCount(features.length);
      } catch {
        // Overpass unreachable. The cadastral overlay and the imagery are
        // unaffected, so this fails quietly rather than blanking the view.
        setBuildingCount(0);
      } finally {
        // In `finally` so the bar clears on success, on failure, and on the
        // cancelled early-returns above. Skipped after teardown so the state
        // update cannot land on an unmounted view.
        if (!cancelled) setOsmLoading(false);
      }
    };

    const onIdle = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(load, 600);
    };
    map.on('idle', onIdle);
    onIdle();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off('idle', onIdle);
      map.off('load', register);
    };
  }, [center[0], center[1]]);

  const toggleBuildingsLayer = () => {
    if (!mapRef.current) return;
    const next = !showBuildings;
    setShowBuildings(next);
    const visibility = next ? 'visible' : 'none';
    ['osm-3d-extrusion', 'osm-3d-outline'].forEach((id) => {
      if (mapRef.current?.getLayer(id)) {
        mapRef.current.setLayoutProperty(id, 'visibility', visibility);
      }
    });
  };

  const toggleCadastreLayer = () => {
    if (!mapRef.current) return;
    const next = !showCadastre;
    setShowCadastre(next);
    const visibility = next ? 'visible' : 'none';
    if (mapRef.current.getLayer('parcel-satellite-fill')) {
      mapRef.current.setLayoutProperty('parcel-satellite-fill', 'visibility', visibility);
    }
    if (mapRef.current.getLayer('parcel-satellite-line')) {
      mapRef.current.setLayoutProperty('parcel-satellite-line', 'visibility', visibility);
    }
  };

  const handleZoom = (delta: number) => {
    if (!mapRef.current) return;
    mapRef.current.zoomTo(mapRef.current.getZoom() + delta, { duration: 400 });
  };

  const handleResetOrientation = () => {
    if (!mapRef.current) return;
    mapRef.current.easeTo({ pitch: 35, bearing: -15, duration: 600 });
  };

  return (
    <div className={`relative h-full w-full overflow-hidden rounded-xl border border-ink/10 bg-slate-950 ${className}`}>
      <div ref={mapContainerRef} className="h-full w-full" data-testid="satellite-map" />

      {/* Non-blocking top bar, for the imagery and the OSM footprint fetch. */}
      <MapLoadingBar
        map={mapInstance}
        extraLoading={osmLoading}
        label="Loading satellite imagery and 3D footprints"
      />

      {/* Top Left Badge */}
      <div className="absolute top-3 left-3 pointer-events-none flex flex-col gap-1 z-10">
        <div className="flex items-center gap-2 bg-slate-900/90 border border-slate-700/60 px-3 py-1.5 rounded-lg text-[11px] font-mono text-slate-200 backdrop-blur-md shadow-lg">
          <Satellite className="w-3.5 h-3.5 text-sky-400 animate-pulse" />
          <span className="font-bold">Esri World Imagery (0.3m/px)</span>
          <span className="text-slate-100 text-[10px]">· Satellite Orthophoto</span>
        </div>
        <div className="bg-black/85 px-2 py-0.5 rounded text-[10px] font-mono text-slate-100 backdrop-blur-sm self-start">
          {center[1].toFixed(4)}°N, {center[0].toFixed(4)}°E · WGS84
        </div>
      </div>

      {/* Top Right Controls */}
      <div className="absolute top-3 right-3 flex flex-col gap-1.5 z-10">
        <button
          onClick={toggleCadastreLayer}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono border backdrop-blur-md shadow-lg transition-colors ${
            showCadastre
              ? 'bg-sky-950/80 border-sky-500/50 text-sky-300'
              : 'bg-slate-900/80 border-slate-700 text-slate-400 hover:text-white'
          }`}
          title="Toggle Cadastral Boundaries"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Cadastre</span>
        </button>

        <button
          onClick={toggleBuildingsLayer}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono border backdrop-blur-md shadow-lg transition-colors ${
            showBuildings
              ? 'bg-slate-950/80 border-slate-400/50 text-slate-200'
              : 'bg-slate-900/80 border-slate-700 text-slate-400 hover:text-white'
          }`}
          title="Toggle 3D extruded OSM building footprints"
        >
          <Building2 className="w-3.5 h-3.5" />
          <span>3D</span>
          {/* slate-500 on the translucent slate-900 pill sat at 2.55:1 and the
              count was effectively invisible. */}
          {buildingCount > 0 && <span className="text-slate-200">{buildingCount}</span>}
        </button>

        <div className="flex flex-col bg-slate-900/80 border border-slate-700/60 rounded-lg overflow-hidden backdrop-blur-md shadow-lg">
          <button
            onClick={() => handleZoom(1)}
            className="p-2 text-slate-300 hover:text-white hover:bg-slate-800/80 transition-colors border-b border-slate-700/40"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleZoom(-1)}
            className="p-2 text-slate-300 hover:text-white hover:bg-slate-800/80 transition-colors border-b border-slate-700/40"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            onClick={handleResetOrientation}
            className="p-2 text-slate-300 hover:text-white hover:bg-slate-800/80 transition-colors"
            title="Reset Orientation"
          >
            <Compass className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Bottom info banner */}
      <div className="absolute bottom-2 left-3 pointer-events-none z-10 text-[10px] font-mono text-slate-100 bg-black/85 px-2 py-0.5 rounded backdrop-blur-sm">
        Cadastral Survey Overlay · EPSG:32643 / WGS84
      </div>
    </div>
  );
};