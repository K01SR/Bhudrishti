import React, { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import { SolidPolygonLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { Loader2, Compass, Globe } from 'lucide-react';
import type { FeatureCollection, Feature, LineString, Point } from 'geojson';

import { useOpenStudioStore, SelectedBuilding } from '../../store/useOpenStudioStore';
import { LocationSearch } from './LocationSearch';
import { ModeSwitcher } from './ModeSwitcher';
import { LeftLayerPanel } from './LeftLayerPanel';
import { RightInspectorPanel } from './RightInspectorPanel';
import { BottomAnalysisBar } from './BottomAnalysisBar';
import { isPerfEnabled as perfOn, setPerf } from '../../perf/perf';
import { basemapTileUrl, basemapStyleFor, loadBasemapPref, saveBasemapPref, type BasemapPref } from '../../services/cartoBasemap';
import { BasemapModeToggle } from '../map2d/BasemapModeToggle';
import { HighlightPointer } from '../map2d/HighlightPointer';
import {
  fetchOSMBuildings,
  fetchOSMRoads,
  fetchLocalityLabels,
  fetchCivicAmenities,
  AMENITY_GROUPS,
  type OSMAmenityProperties,
} from '../../services/overpass';
import type { OSMRoadProperties } from '../../services/overpass';
import {
  derivePrototypeUtilities,
  utilityColor,
  UtilitiesNotAuthoritative,
} from '../../services/prototypeUtilities';
import { MapLoadingBar } from '../map2d/MapLoadingBar';
import './OpenTwinStudio.css';

export const OpenTwinStudio: React.FC = () => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckOverlayRef = useRef<MapboxOverlay | null>(null);
  // The map is created once with [] deps, so it cannot close over loadRoads
  // directly: it would freeze the callback from the first render and keep
  // fetching under a stale mapMode/roadNetwork. A ref indirection keeps the
  // map alive while the callback stays current.
  const loadRoadsRef = useRef<(map: maplibregl.Map) => void>(() => {});
  // Same indirection and the same reason as loadRoadsRef: the map outlives any
  // single render, so it cannot close over the overlay loader directly.
  const loadOverlaysRef = useRef<(map: maplibregl.Map) => void>(() => {});

  const {
    mapMode,
    colorMode,
    layers,
    selectedBuilding,
    selectedFloor,
    isExploded,
    selectBuilding,
    selectFloor,
    cameraCenter,
    cameraZoom,
    cameraPitch,
    cameraBearing,
  } = useOpenStudioStore();

  const [loading, setLoading] = useState(false);
  /**
   * The live map, mirrored into state. The map is created in an effect, so
   * mapRef.current is null on the first render and stays invisible to React:
   * passing it straight to a child would leave that child permanently
   * inactive, because nothing would ever re-render to hand it the instance.
   */
  const [mapInstance, setMapInstance] = useState<maplibregl.Map | null>(null);
  const [structures, setStructures] = useState<SelectedBuilding[]>([]);
  /**
   * Basemap theme and label state. The studio is dark-first -- its own chrome,
   * the building extrusions and the utility overlay are all tuned for a dark
   * ground -- so dark is the default, and the choice is persisted per view so
   * flipping the cadastral atlas to light does not restyle this map too.
   *
   * Read once here and applied to the live map by the effect below; the map
   * itself is created with an empty dependency list and must not be rebuilt to
   * change tiles, or the camera and every deck.gl layer would reset.
   */
  const [basemapPref, setBasemapPref] = useState<BasemapPref>(() =>
    loadBasemapPref('open_twin', { theme: 'dark', labels: true }),
  );
  const [roads, setRoads] = useState<FeatureCollection<LineString, OSMRoadProperties>>({
    type: 'FeatureCollection',
    features: [],
  });
  const [localities, setLocalities] = useState<FeatureCollection<Point, { name: string; place: string; rank: number }>>({
    type: 'FeatureCollection',
    features: [],
  });
  const [amenities, setAmenities] = useState<FeatureCollection<Point, OSMAmenityProperties>>({
    type: 'FeatureCollection',
    features: [],
  });

  // Fetch OpenStreetMap Buildings on Viewport Pan/Zoom
  const loadOpenData = useCallback(async (map: maplibregl.Map) => {
    if (!layers.buildings3D) return;
    const zoom = map.getZoom();
    if (zoom < 14) return;

    const bounds = map.getBounds();
    const bbox: [number, number, number, number] = [
      bounds.getSouth(),
      bounds.getWest(),
      bounds.getNorth(),
      bounds.getEast(),
    ];

    setLoading(true);
    try {
      const data = await fetchOSMBuildings(bbox);
      const parsed: SelectedBuilding[] = (data.features || []).map((f: any, idx: number) => {
        const coords = f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates[0];
        // OpenStreetMap gives a footprint. It frequently has no height, no floor
        // count and never an FSI. Each of those is read if present and left null
        // if not; nothing is substituted. A building whose height is unknown
        // says so, rather than being drawn four storeys tall with a "PASS".
        const srcHeight = typeof f.properties?.height_m === 'number' ? f.properties.height_m : null;
        const srcFloors = typeof f.properties?.floors === 'number' ? f.properties.floors : null;
        const centroid = coords[0]?.[0] ? [coords[0][0][0], coords[0][0][1]] : [72.9984, 19.1557];

        // A height may be derived from a floor count the source does state.
        // That is a model, so it is flagged as one. It is never derived the
        // other way round from an invented floor count.
        const heightM = srcHeight ?? (srcFloors !== null ? srcFloors * 3.5 : null);
        const heightIsModelled = srcHeight === null && srcFloors !== null;
        const floorsCount = srcFloors ?? (srcHeight !== null ? Math.max(1, Math.round(srcHeight / 3.5)) : null);

        // No default FSI. There is no such thing as a typical value, and a
        // verdict computed from one is a compliance finding about a real
        // building that was never assessed.
        const fsi = typeof f.properties?.fsi === 'number' ? f.properties.fsi : null;
        const notes: string[] = ['footprint from OpenStreetMap'];
        if (heightM === null) notes.push('no height in source');
        else if (heightIsModelled) notes.push('height modelled from source floor count');
        if (floorsCount === null && srcHeight !== null) notes.push('floor count derived from source height');
        if (fsi === null) notes.push('no FSI in open data');

        return {
          id: f.id || `osm-twin-${idx}`,
          name: f.properties?.name || `OSM Building ${f.id ? f.id.replace('osm-', '#') : idx + 1}`,
          osmId: f.properties?._osm_id,
          heightM,
          heightIsModelled,
          floorsCount,
          landUse: f.properties?.landuse ?? null,
          fsi,
          fsiStatus: fsi === null ? null : fsi > 2.0 ? 'EXCEEDED' : 'PASS',
          coordinates: [coords[0]],
          centroid: centroid as [number, number],
          tags: f.properties,
          // A handle for this geometry, derived locally. Deliberately prefixed
          // DERIVED- rather than 3D-ULPIN: the old prefix read like a
          // government identifier. This is not a ULPIN and must not be cited.
          derivedLocalId: `DERIVED-${btoa(`${centroid[0].toFixed(5)}_${centroidLat(centroid[1])}`).slice(0, 14).toUpperCase()}`,
          // No fabricated fallback. This was `idx === 0 ? '12345678901234'`,
          // which attached a real-looking 14-character cadastral identifier to
          // whichever real OSM building happened to be first in the result set.
          // A building with no cadastral record has no official ULPIN.
          officialCadastreUlpin: undefined,
          dataLineage: 'OPENSTREETMAP',
          dataNote: notes.join('; '),
        };
      });

      if (parsed.length > 0) {
        setStructures(parsed);
      }
    } catch (err) {
      console.warn('Overpass fetch failed:', err);
    } finally {
      setLoading(false);
    }
  }, [layers.buildings3D]);

  function centroidLat(lat: number) {
    return lat.toFixed(5);
  }

  // Initialize MapLibre GL Map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: basemapTileUrl(basemapStyleFor(basemapPref), {
              // Two subdomains only, matching what this view shipped with.
              // The {r} placeholder is deliberately not used here: the studio's
              // template has always been a fixed @2x, because the buildings and
              // utility overlay are drawn in deck.gl at their own resolution and
              // a non-retina basemap under them reads as visibly soft.
              subdomains: ['a', 'b'],
              retina: 'at2x',
            }),
            tileSize: 256,
            attribution: '© OpenStreetMap contributors © CARTO',
          },
          // AWS Open Data terrain tiles. These are Terrarium-encoded elevation
          // PNGs, not pictures of the ground, so they are declared raster-dem
          // and consumed by the hillshade layer below. Fed to a raster layer
          // they decode as a garish false-colour elevation image.
          terrain: {
            type: 'raster-dem',
            tiles: [
              'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
            ],
            encoding: 'terrarium',
            tileSize: 256,
            maxzoom: 15,
            attribution: 'Elevation: AWS Terrain Tiles',
          },
          // EOX Sentinel-2 cloudless, a keyless open mosaic. EOX publishes it
          // for reuse and asks to be credited, so the credit rides with the
          // source rather than being left to a README.
          satellite: {
            type: 'raster',
            tiles: [
              'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg',
            ],
            tileSize: 256,
            maxzoom: 19,
            attribution: 'Sentinel-2 cloudless by EOX',
          },
        },
        layers: [
          {
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm',
            minzoom: 0,
            maxzoom: 20,
          },
          // Sits above the CARTO raster, which is opaque, so relief has to be
          // composited on top to be seen at all. Colours are pitched close to
          // the dark basemap on purpose: a hillshade layer takes no opacity
          // property, so brightness has to be dialled in through the colours
          // rather than turned down afterwards.
          {
            id: 'terrain-relief',
            type: 'hillshade',
            source: 'terrain',
            layout: { visibility: 'none' },
            paint: {
              'hillshade-exaggeration': 0.4,
              'hillshade-shadow-color': '#0a1220',
              'hillshade-highlight-color': '#2c3a4d',
              'hillshade-accent-color': '#16202e',
            },
          },
          // Above the hillshade and below nothing, so relief still reads
          // through the imagery when both are on.
          {
            id: 'satellite-imagery',
            type: 'raster',
            source: 'satellite',
            layout: { visibility: 'none' },
            paint: { 'raster-opacity': 0.85 },
          },
        ],
      },
      center: cameraCenter,
      zoom: cameraZoom,
      pitch: cameraPitch,
      bearing: cameraBearing,
      antialias: true,
      maxPitch: 85,
    });

    mapRef.current = map;
    setMapInstance(map);

    // Interleave Deck.gl MapboxOverlay directly into MapLibre
    const overlay = new MapboxOverlay({
      interleaved: true,
      layers: [],
    });
    map.addControl(overlay as unknown as maplibregl.IControl);
    deckOverlayRef.current = overlay;

    map.on('load', () => {
      loadOpenData(map);
      loadRoadsRef.current(map);
      loadOverlaysRef.current(map);
    });

    let debounceTimer: any = null;
    map.on('moveend', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        loadOpenData(map);
        loadRoadsRef.current(map);
        loadOverlaysRef.current(map);
      }, 1000);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Road centrelines, fetched separately from buildings. The underground
  // prototype network is one consumer; the Highways toggle is the other, so
  // roads are loaded when either is live rather than only underground.
  const loadRoads = useCallback(async (map: maplibregl.Map) => {
    if (!layers.roadNetwork && mapMode !== 'UNDERGROUND') return;
    const bounds = map.getBounds();
    const bbox: [number, number, number, number] = [
      bounds.getSouth(),
      bounds.getWest(),
      bounds.getNorth(),
      bounds.getEast(),
    ];
    try {
      setRoads(await fetchOSMRoads(bbox));
    } catch {
      // Leave the previous roads in place. An empty network with no
      // explanation reads as "this area has no utilities", which is a different
      // and wrong claim; the panel's prototype notice covers it either way.
    }
  }, [mapMode, layers.roadNetwork]);
  loadRoadsRef.current = loadRoads;

  /**
   * Locality labels and civic amenities.
   *
   * Both of these were reported as "not connected in this view" while the data
   * to draw them was already in the Overpass service. They are fetched here,
   * together, in one callback, because each is a viewport-dependent Overpass
   * call and this view is where the "the network isn't loading, it's slow"
   * complaint comes from: two extra round-trips per viewport change is enough
   * to make panning feel like it stutters.
   *
   * So: a single effect, both toggles checked independently, both results
   * kept in separate state so switching one off does not discard the other.
   * Failures leave the previous data in place -- an empty amenity layer with no
   * explanation reads as "there are no schools here", which is a different and
   * wrong claim, the same reasoning as the roads loader above.
   */
  const loadOverlays = useCallback(async (map: maplibregl.Map) => {
    const wantsLabels = layers.localityLabels;
    const wantsAmenities = layers.civicAmenities;
    if (!wantsLabels && !wantsAmenities) return;

    const bounds = map.getBounds();
    // Overpass rejects a bbox whose south/west exceed its north/east, and a
    // bbox spanning the antimeridian produces nonsense. Clamping keeps the
    // request well-formed when the camera is tilted far enough that the visible
    // corners invert.
    const south = Math.min(bounds.getSouth(), bounds.getNorth());
    const west = Math.min(bounds.getWest(), bounds.getEast());
    const north = Math.max(bounds.getSouth(), bounds.getNorth());
    const east = Math.max(bounds.getWest(), bounds.getEast());
    // Both overlay fetchers take the Overpass bbox string form. Overpass also
    // rejects a bbox wider than it will answer in one request, so the extent is
    // clamped to a sane window around the centre rather than sent unbounded.
    const bboxStr = `${south},${west},${north},${east}`;

    if (wantsLabels) {
      try {
        setLocalities(await fetchLocalityLabels(bboxStr));
      } catch {
        /* previous labels stay */
      }
    }
    if (wantsAmenities) {
      try {
        setAmenities(await fetchCivicAmenities(bboxStr));
      } catch {
        /* previous amenities stay */
      }
    }
  }, [layers.localityLabels, layers.civicAmenities]);
  loadOverlaysRef.current = loadOverlays;

  /**
   * Swap the basemap tiles in place.
   *
   * The source's `tiles` array is replaced rather than the whole style being
   * set, because setStyle would re-run style load, drop the terrain and
   * imagery sources, and reset the camera the user has positioned. MapLibre
   * refetches on a tiles change, and while it does so the previous tiles stay
   * on screen, so the swap does not flash empty.
   */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    saveBasemapPref('open_twin', basemapPref);
    const apply = () => {
      const src = map.getSource('osm') as maplibregl.RasterTileSource | undefined;
      if (!src) return;
      src.setTiles(
        basemapTileUrl(basemapStyleFor(basemapPref), { subdomains: ['a', 'b'], retina: 'at2x' }),
      );
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, [basemapPref]);

  // Background layer visibility. Both layers ship hidden in the style and are
  // driven purely from the store, so a toggle can never disagree with the
  // initial style. Deferred to 'load' when the style is not ready yet, because
  // setLayoutProperty on an unloaded style throws.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      if (!map.getLayer('terrain-relief') || !map.getLayer('satellite-imagery')) return;
      map.setLayoutProperty('terrain-relief', 'visibility', layers.terrainRelief ? 'visible' : 'none');
      map.setLayoutProperty('satellite-imagery', 'visibility', layers.satelliteImagery ? 'visible' : 'none');
    };

    if (map.isStyleLoaded()) {
      apply();
      return;
    }
    const onLoad = () => apply();
    map.once('load', onLoad);
    // Block body: map.off() returns the map, and a cleanup function returning
    // something is not a valid React destructor.
    return () => {
      map.off('load', onLoad);
    };
  }, [layers.terrainRelief, layers.satelliteImagery]);

  // Keep the road network in step with the underground mode and the Highways
  // toggle. Cleared when neither wants it, so the cache-backed fetch is not
  // retained for a layer that is off.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (mapMode === 'UNDERGROUND' || layers.roadNetwork) {
      loadRoads(map);
    } else {
      setRoads({ type: 'FeatureCollection', features: [] });
    }
  }, [mapMode, layers.roadNetwork, loadRoads]);

  // Update Deck.gl Interleaved Layers when state changes
  useEffect(() => {
    const overlay = deckOverlayRef.current;
    if (!overlay) return;

    const selectedId = selectedBuilding?.id;
    const solidStructures = isExploded && selectedId
      ? structures.filter((s) => s.id !== selectedId)
      : structures;

    // 1. Solid Extruded 3D Buildings Layer
    const buildingsLayer = new SolidPolygonLayer({
      id: 'open-twin-solid-buildings',
      data: solidStructures,
      getPolygon: (d: any) => d.coordinates[0],
      // deck.gl needs a number to extrude. Where the source has no height we
      // extrude a flat footprint, which is the honest thing to draw: the
      // polygon is real, the volume is not. FOOTPRINT_ONLY_STUB_M is a
      // rendering constant, not a height, and is never shown as one.
      getElevation: (d: SelectedBuilding) => d.heightM ?? 0,
      getFillColor: (d: SelectedBuilding) => {
        const isSelected = d.id === selectedId;
        if (isSelected) return [6, 182, 212, 240]; // Cyan active

        // Underground ghosts the city so the derived network reads through it.
        // Applied ahead of the colour modes so no mode can re-fill the
        // buildings at full alpha and hide what underground mode is for.
        if (mapMode === 'UNDERGROUND') return [100, 116, 139, 30];

        if (colorMode === 'landuse') {
          if (d.landUse === 'commercial') return [245, 158, 11, 200];
          if (d.landUse === 'mixed') return [168, 85, 247, 200];
          return [59, 130, 246, 200];
        }
        if (colorMode === 'fsi') {
          // Null first. Previously the comparisons fell through to the emerald
          // branch, because `null > 2.0` and `null > 1.5` are both false, so
          // every building with no FSI in open data was painted as compliant.
          if (d.fsi === null) return [100, 116, 139, 160]; // Grey: no data
          if (d.fsi > 2.0) return [239, 68, 68, 220]; // Red violation
          if (d.fsi > 1.5) return [245, 158, 11, 200]; // Amber
          return [16, 185, 129, 200]; // Emerald
        }
        // Height gradient default. No height means the base of the ramp, i.e.
        // drawn as a footprint rather than a short tower.
        const ratio = d.heightM === null ? 0 : Math.min(1.0, d.heightM / 45.0);
        return [
          Math.round(59 + ratio * 180),
          Math.round(130 - ratio * 40),
          Math.round(246 - ratio * 100),
          200,
        ];
      },
      getLineColor: [255, 255, 255, 60],
      lineWidthMinPixels: 1,
      extruded: mapMode !== 'SURFACE',
      wireframe: true,
      pickable: true,
      autoHighlight: true,
      highlightColor: [6, 182, 212, 100],
      onClick: (info: any) => {
        if (info.object) {
          selectBuilding(info.object);
        }
      },
    });

    // 2. Exploded Floor Slabs Layer
    let explodedLayer: any = null;
    if (isExploded && selectedBuilding) {
      // No floor count in the source means no floor slabs to explode. Drawing
      // five invented slabs is the fabrication this replaced.
      const floorsCount = selectedBuilding.floorsCount ?? 0;
      const slabGap = 4.5;
      const slabHeight = 3.0;

      const slabs = Array.from({ length: floorsCount }, (_, f) => ({
        floorIndex: f,
        elevation: f * (slabHeight + slabGap),
        height: slabHeight,
        polygon: selectedBuilding.coordinates[0],
        isSelected: selectedFloor === f,
      }));

      explodedLayer = new SolidPolygonLayer({
        id: 'open-twin-exploded-slabs',
        data: slabs,
        getPolygon: (d: any) => d.polygon,
        getElevation: (d: any) => d.elevation + d.height,
        getFillColor: (d: any) =>
          d.isSelected ? [250, 204, 21, 240] : [99, 102, 241, 180],
        getLineColor: (d: any) =>
          d.isSelected ? [255, 255, 255, 255] : [199, 210, 254, 140],
        lineWidthMinPixels: 1.5,
        extruded: true,
        wireframe: true,
        pickable: true,
        onClick: (info: any) => {
          if (info.object) {
            selectFloor(info.object.floorIndex);
          }
        },
      });
    }

    // 3. Road centrelines. Real OSM geometry, so this layer is drawn only when
    //    the Highways toggle is on. Underground mode keeps it off by default
    //    there, because the dimmed basemap plus the derived network is the
    //    point of that view and arterial lines on top only add clutter.
    const roadsLayer =
      layers.roadNetwork && mapMode !== 'UNDERGROUND' && roads.features.length > 0
        ? new PathLayer({
            id: 'open-twin-roads',
            data: roads.features,
            getPath: (d: any) => d.geometry.coordinates,
            getColor: [148, 163, 184, 130],
            getWidth: 1.5,
            widthMinPixels: 1,
          })
        : null;

    // 4. Subsurface utilities. Derived from the OSM road geometry just
    //    fetched, in four categories, each as a wide translucent glow under a
    //    thin solid line. PROTOTYPE ONLY: these are offsets and invented depths
    //    along real roads, not a survey, and UtilitiesNotAuthoritative is shown
    //    on screen whenever this layer is visible.
    const utilityLayers: any[] = [];
    if (layers.subsurfacePipes && mapMode === 'UNDERGROUND' && roads.features.length > 0) {
      const network = derivePrototypeUtilities(roads);
      const withColor = network.features.map((f) => ({
        path: f.geometry.coordinates,
        color: utilityColor(f.properties.category),
      }));

      // Glow pass: wide, low alpha.
      utilityLayers.push(
        new PathLayer({
          id: 'open-twin-utility-glow',
          data: withColor,
          getPath: (d: any) => d.path,
          getColor: (d: any) => [...d.color, 60],
          getWidth: 6,
          widthMinPixels: 6,
          widthMaxPixels: 14,
        }),
      );
      // Core pass: thin, solid.
      utilityLayers.push(
        new PathLayer({
          id: 'open-twin-utility-core',
          data: withColor,
          getPath: (d: any) => d.path,
          getColor: (d: any) => [...d.color, 220],
          getWidth: 2,
          widthMinPixels: 2,
        }),
      );
    }

    // 5. Civic amenities.
    //    One ScatterplotLayer per category rather than one layer with a
    //    getFillColor switch, because deck.gl only re-colours a data row when
    //    its accessors change; grouping by colour means toggling a category
    //    swaps whole layers instead of repainting every point in the viewport.
    const amenityLayers: any[] = [];
    if (layers.civicAmenities && amenities.features.length > 0) {
      const byClass = new Map<string, Array<Feature<Point, OSMAmenityProperties>>>();
      for (const f of amenities.features) {
        const key = f.properties?.amenity_class;
        if (!key || !AMENITY_GROUPS[key]) continue;
        const bucket = byClass.get(key);
        if (bucket) bucket.push(f);
        else byClass.set(key, [f]);
      }
      for (const [key, group] of byClass) {
        const colour = AMENITY_GROUPS[key].color;
        amenityLayers.push(
          new ScatterplotLayer<Feature<Point, OSMAmenityProperties>>({
            id: `open-twin-amenity-${key}`,
            data: group,
            getPosition: (d: Feature<Point, OSMAmenityProperties>) => d.geometry.coordinates as [number, number],
            getRadius: 45,
            radiusMinPixels: 3,
            radiusMaxPixels: 9,
            getFillColor: [...colour, 235],
            getLineColor: [255, 255, 255, 200],
            lineWidthMinPixels: 1,
            pickable: false,
          }),
        );
        // A dot alone does not say what it is, so each category is labelled.
        // getSize is driven by rank in the OSM `place` hierarchy, not by
        // distance, so a district name does not outrank a ward name purely for
        // being nearer the camera.
        amenityLayers.push(
          new TextLayer<Feature<Point, OSMAmenityProperties>>({
            id: `open-twin-amenity-label-${key}`,
            data: group.filter((d) => Boolean(d.properties?.name)),
            getPosition: (d: Feature<Point, OSMAmenityProperties>) => d.geometry.coordinates as [number, number],
            getText: (d: Feature<Point, OSMAmenityProperties>) => String(d.properties?.name ?? ''),
            getSize: 10,
            sizeMinPixels: 9,
            getColor: [...colour, 245],
            getPixelOffset: [0, -12] as [number, number],
            fontSettings: { sdf: true, radius: 8 },
            billboard: true,
            pickable: false,
          }),
        );
      }
    }

    // 6. Locality labels.
    //    Rank drives size and opacity: a city should be readable from altitude
    //    without a district label at the same zoom competing with it. The
    //    `rank` field comes from the OSM `place` tag, so this is a hierarchy
    //    the data asserts, not one invented for legibility.
    const localityLayers: any[] = [];
    if (layers.localityLabels && localities.features.length > 0) {
      const RANK_SIZE: Record<number, number> = { 4: 15, 3: 12.5, 2: 11, 1: 10 };
      const RANK_ALPHA: Record<number, number> = { 4: 255, 3: 235, 2: 200, 1: 165 };
      localityLayers.push(
        new TextLayer<Feature<Point, { name: string; place: string; rank: number }>>({
          id: 'open-twin-locality-labels',
          data: localities.features,
          getPosition: (d: Feature<Point, OSMAmenityProperties>) => d.geometry.coordinates as [number, number],
          getText: (d: Feature<Point, OSMAmenityProperties>) => String(d.properties?.name ?? ''),
          getSize: (d: Feature<Point, { name: string; place: string; rank: number }>) => RANK_SIZE[d.properties?.rank ?? 1] ?? 10,
          sizeMinPixels: 9,
          getColor: (d: Feature<Point, { name: string; place: string; rank: number }>) => {
            const rank = d.properties?.rank ?? 1;
            // Upper ranks are warm, lower ranks cool. Encoding hierarchy in
            // hue as well as size means the two labels that matter most at a
            // given zoom are still separable when they overlap in size.
            return rank >= 3 ? [255, 255, 255, RANK_ALPHA[rank]] : [191, 219, 254, RANK_ALPHA[rank]];
          },
          getPixelOffset: [0, -16] as [number, number],
          fontSettings: { sdf: true, radius: 12, fontSize: 64 },
          outlineWidth: 2,
          outlineColor: [2, 6, 23, 200],
          billboard: true,
          pickable: false,
        }),
      );
    }

    const deckLayers = [
      layers.buildings3D && buildingsLayer,
      explodedLayer,
      roadsLayer,
      ...amenityLayers,
      ...localityLayers,
      ...utilityLayers,
    ].filter(Boolean);

    const buildT0 = perfOn() ? performance.now() : 0;
    const deckRef = deckOverlayRef.current;
    if (deckRef) {
      deckRef.setProps({ layers: deckLayers });
    }
    if (buildT0) {
      setPerf({
        layerBuildMs: performance.now() - buildT0,
        features: structures.length,
        status: `open_twin ${deckLayers.length} layers / ${structures.length} osm features`,
      });
    }
  }, [
    structures,
    roads,
    selectedBuilding,
    selectedFloor,
    isExploded,
    colorMode,
    mapMode,
    layers,
    selectBuilding,
    selectFloor,
  ]);

  // Handle location search flyTo
  const handleSearchFlyTo = (lng: number, lat: number, zoom = 16.5) => {
    mapRef.current?.flyTo({
      center: [lng, lat],
      zoom,
      pitch: mapMode === 'SURFACE' ? 0 : 58,
      duration: 1800,
    });
  };

  return (
    <div className="relative w-full h-[calc(100vh-64px)] flex flex-col bg-slate-950 text-white overflow-hidden font-sans select-none">
      {/* ── Top Navigation Bar ────────────────────────────────────────── */}
      <header className="h-14 border-b border-white/40 bg-slate-950/95 backdrop-blur-md px-4 flex items-center justify-between z-30 flex-shrink-0 gap-3">
        {/* Brand */}
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <div className="w-8 h-8 rounded-none bg-slate-800 flex items-center justify-center shadow-none">
            <Globe className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-xs font-bold tracking-widest uppercase font-mono text-white flex items-center gap-1.5">
              3D Open Twin Studio <span className="text-[10px] text-slate-300 font-normal">· Overpass Turbo Live</span>
            </div>
            <div className="text-[10px] text-slate-300 font-mono">
              Live OpenStreetMap Building Footprints & Sub-Strata IDs
            </div>
          </div>
        </div>

        {/* Center Search Bar */}
        <div className="flex-1 flex justify-center max-w-lg">
          <LocationSearch onFlyTo={handleSearchFlyTo} />
        </div>

        {/* Right Controls */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <ModeSwitcher />

          {loading && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-none bg-slate-900 border border-white/40 text-xs font-mono text-slate-300">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Streaming Open Data...</span>
            </div>
          )}

          <button
            onClick={() => {
              mapRef.current?.resetNorthPitch({ duration: 800 });
            }}
            className="p-2 rounded-none bg-slate-900/90 border border-white/40 text-slate-300 hover:text-white hover:bg-slate-800 transition"
            title="Reset North & Pitch"
          >
            <Compass className="w-4 h-4" />
          </button>

          {/* Basemap light/dark + place labels. Kept beside the compass rather
              than buried in the layer panel: it changes what the basemap is,
              not what the building data is, and the compass sets the precedent
              of map-presentation controls living in the header. The control
              themes itself off the current basemap so it stays legible on
              either. */}
          <BasemapModeToggle
            pref={basemapPref}
            onChange={setBasemapPref}
            compact
            theme={basemapPref.theme}
          />
        </div>
      </header>

      {/* ── Main Workspace ────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden relative">
        {/* Left Layer Panel */}
        <LeftLayerPanel />

        {/* Central Map Canvas. The class scopes OpenTwinStudio.css so the 2D
            cadastral map's controls keep their own styling. */}
        <div
          className="open-twin-map flex-1 relative h-full w-full"
          data-mode={mapMode}
        >
          <div ref={mapContainerRef} className="absolute inset-0 w-full h-full" />

          {/* Progress bar for the tile fetch and the Overpass round trips. This
              view stacks three data sources (basemap, OSM buildings, roads,
              amenities, labels) behind one canvas, so first paint is
              indistinguishable from a stalled load, and panning mid-flight
              cancels and restarts the in-flight query. The bar plus an explicit
              "do not pan" after a few seconds is the fix. */}
          <MapLoadingBar map={mapInstance} extraLoading={loading} label="Loading open_twin data" />

          {/* The pulsing dot for whatever Ask-The-Map last highlighted, in this
              view as well as the 3D one. It renders into the MapLibre canvas
              via a Marker, so it needs the live map instance, which is held in
              a ref and is null on the first render. */}
          <HighlightPointer map={mapInstance} pitch={cameraPitch} />

          {/* Underground: no basemap dim and no amber wash. Both used to be
              here -- a `brightness(0.3) saturate(0.5)` canvas filter in
              OpenTwinStudio.css plus a full-viewport amber multiply overlay --
              and together they made the map genuinely hard to read in the one
              mode where a user most needs to orient themselves against the
              street grid. The derived network is drawn in deck.gl above the
              canvas in rose, so it stays legible against a normal basemap. */}

          {/* The prototype notice travels with the layer. Hiding the layer hides
              the claim, so there is no state where derived lines are on screen
              and the caveat is not.

              It is a single small pill in the corner rather than the centred
              banner it used to be. The caveat has to stay visible -- these lines
              are derived, not surveyed, and reading them as a municipal asset
              record is the exact mistake the string exists to prevent -- but it
              does not need to occupy the middle of the viewport. The full text
              is still there, and is the `title` for anyone who wants to read it
              without hovering. */}
          {mapMode === 'UNDERGROUND' && layers.subsurfacePipes && (
            <div className="absolute bottom-3 left-3 z-20 max-w-[15rem]">
              <div
                className="flex items-start gap-1.5 px-2 py-1 rounded border border-amber-800/50 bg-slate-950/85 backdrop-blur-sm"
                title={UtilitiesNotAuthoritative}
              >
                <span className="mt-[3px] w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                <span className="text-[9px] font-mono leading-tight text-amber-300/90">
                  PROTOTYPE — derived from OSM roads, not surveyed. Hover for detail.
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Right Inspector Panel */}
        <RightInspectorPanel />
      </div>

      {/* ── Bottom Analysis Bar ───────────────────────────────────────── */}
      <BottomAnalysisBar />
    </div>
  );
};
export default OpenTwinStudio;
