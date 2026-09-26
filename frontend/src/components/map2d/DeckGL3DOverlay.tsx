import React, { useEffect, useRef } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { SolidPolygonLayer } from '@deck.gl/layers';
import { isPerfEnabled as perfOn, setPerf } from '../../perf/perf';

export type DeckGLColorMode = 'height' | 'landuse' | 'fsi' | 'lineage' | 'none';

export interface InspectedStructure {
  id: string;
  name: string;
  buildingType: string;
  floorsCount: number;
  heightM: number;
  coordinates: number[][][]; // Polygon rings [[ [lon, lat], ... ]]
  fsi?: number;
  fsiStatus?: 'PASS' | 'EXCEEDED' | 'UNDER_REVIEW';
  source: 'OFFICIAL_CADASTRE' | 'OPEN_STREET_MAP' | 'SYNTHETIC_TWIN';
  ulpin?: string;
  centroid?: [number, number];
}

interface DeckGL3DOverlayProps {
  map: MapLibreMap | null;
  structures: InspectedStructure[];
  selectedId: string | null;
  isExploded: boolean;
  selectedFloor: number | null;
  colorMode: DeckGLColorMode;
  onSelectStructure: (s: InspectedStructure) => void;
  onSelectFloor: (floor: number) => void;
}

function getStructureColor(
  s: InspectedStructure,
  colorMode: DeckGLColorMode,
  isSelected: boolean
): [number, number, number, number] {
  if (isSelected) {
    return [6, 182, 212, 230]; // Cyan highlight
  }

  switch (colorMode) {
    case 'height': {
      const floors = s.floorsCount || Math.max(1, Math.round(s.heightM / 3.5));
      if (floors >= 10) return [168, 85, 247, 210]; // Purple (High-rise)
      if (floors >= 5) return [245, 158, 11, 210];  // Amber (Mid-rise)
      return [59, 130, 246, 210];                   // Blue (Low-rise)
    }

    case 'landuse': {
      const bType = (s.buildingType || '').toLowerCase();
      if (bType.includes('com') || bType.includes('retail') || bType.includes('off')) {
        return [192, 132, 252, 210]; // Purple (Commercial)
      }
      if (bType.includes('ind') || bType.includes('ware')) {
        return [251, 146, 60, 210];  // Orange (Industrial)
      }
      if (bType.includes('civic') || bType.includes('inst') || bType.includes('hosp') || bType.includes('sch')) {
        return [34, 197, 94, 210];   // Green (Civic/Institutional)
      }
      return [147, 197, 253, 210];   // Light Blue (Residential)
    }

    case 'fsi': {
      if (s.fsiStatus === 'EXCEEDED' || (s.fsi && s.fsi > 2.0)) {
        return [239, 68, 68, 230];   // Red (Exceeded)
      }
      if (s.fsiStatus === 'UNDER_REVIEW') {
        return [245, 158, 11, 210];  // Amber (Under Review)
      }
      return [16, 185, 129, 210];    // Emerald (Compliant)
    }

    case 'lineage': {
      if (s.source === 'OPEN_STREET_MAP') {
        return [14, 165, 233, 210];  // Sky Blue (OSM Live)
      }
      return [139, 92, 246, 210];    // Purple (Procedural Twin)
    }

    default:
      return [71, 85, 105, 190];     // Slate 600
  }
}

export const DeckGL3DOverlay: React.FC<DeckGL3DOverlayProps> = ({
  map,
  structures,
  selectedId,
  isExploded,
  selectedFloor,
  colorMode,
  onSelectStructure,
  onSelectFloor,
}) => {
  const overlayRef = useRef<MapboxOverlay | null>(null);

  // Handlers are held in refs rather than used as effect dependencies. Callers
  // pass inline arrows, so as dependencies they changed identity on every
  // parent render and re-ran the layer effect each time, and a setProps call
  // makes deck.gl re-diff attributes and re-tessellate every polygon on the
  // main thread. Selection state alone should drive that work.
  const selectStructureRef = useRef(onSelectStructure);
  const selectFloorRef = useRef(onSelectFloor);
  useEffect(() => {
    selectStructureRef.current = onSelectStructure;
    selectFloorRef.current = onSelectFloor;
  });

  useEffect(() => {
    if (!map) return;

    const overlay = new MapboxOverlay({
      interleaved: true,
      layers: [],
    });

    map.addControl(overlay as any);
    overlayRef.current = overlay;

    return () => {
      try {
        if (map && overlayRef.current) {
          map.removeControl(overlayRef.current as any);
        }
      } catch {
        // ignore
      }
      overlayRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    if (!overlayRef.current) return;

    // Filter structures: when exploded, hide the solid building that is currently exploding
    const solidStructures = isExploded && selectedId
      ? structures.filter((s) => s.id !== selectedId)
      : structures;

    // Base extruded buildings layer
    const solidBuildingsLayer = new SolidPolygonLayer({
      id: 'deckgl-solid-buildings',
      data: solidStructures,
      getPolygon: (d: any) => d.coordinates[0],
      getElevation: (d: InspectedStructure) => d.heightM || d.floorsCount * 3.5 || 12.0,
      getFillColor: (d: InspectedStructure) => getStructureColor(d, colorMode, d.id === selectedId),
      getLineColor: [255, 255, 255, 70],
      lineWidthMinPixels: 1,
      extruded: true,
      wireframe: true,
      pickable: true,
      autoHighlight: true,
      highlightColor: [6, 182, 212, 120],
      onClick: (info: any) => {
        if (info.object) {
          selectStructureRef.current(info.object);
        }
      },
    });

    // If a building is selected and exploded view is active, generate vertical floor slices
    let explodedFloorsLayer: any = null;
    if (isExploded && selectedId) {
      const target = structures.find((s) => s.id === selectedId);
      if (target) {
        const floorCount = Math.max(1, target.floorsCount || Math.round(target.heightM / 3.5) || 5);
        const floorGapM = 4.5; // Gap between exploded slabs in meters
        const slabHeightM = 3.0; // Thickness of each individual floor slab

        const floorSlabsData = Array.from({ length: floorCount }, (_, f) => {
          const elevation = f * (slabHeightM + floorGapM);
          return {
            floorIndex: f,
            floorLabel: `Floor ${String(f).padStart(2, '0')}`,
            elevation,
            height: slabHeightM,
            polygon: target.coordinates[0],
            isSelected: selectedFloor === f,
          };
        });

        explodedFloorsLayer = new SolidPolygonLayer({
          id: 'deckgl-exploded-floors',
          data: floorSlabsData,
          getPolygon: (d: any) => d.polygon,
          getElevation: (d: any) => d.elevation + d.height,
          // Use base elevation by subtracting height
          // SolidPolygonLayer in deck.gl extrudes from 0 to getElevation, so to float we draw top slab:
          getFillColor: (d: any) => {
            if (d.isSelected) {
              return [250, 204, 21, 240]; // Yellow gold active floor
            }
            return [99, 102, 241, 180]; // Indigo-500 floating slab
          },
          getLineColor: (d: any) => (d.isSelected ? [255, 255, 255, 255] : [199, 210, 254, 140]),
          lineWidthMinPixels: 1.5,
          extruded: true,
          wireframe: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [250, 204, 21, 100],
          onClick: (info: any) => {
            if (info.object) {
              selectFloorRef.current(info.object.floorIndex);
            }
          },
        });
      }
    }

    const layers = [solidBuildingsLayer, ...(explodedFloorsLayer ? [explodedFloorsLayer] : [])];
    // setProps triggers deck.gl's attribute diffing and polygon tessellation on
    // the main thread, so the cost of assembling the list plus handing it over is
    // the number that shows whether a selection is cheap or catastrophic.
    const buildT0 = perfOn() ? performance.now() : 0;
    overlayRef.current.setProps({ layers });
    if (buildT0) {
      setPerf({
        layerBuildMs: performance.now() - buildT0,
        features: structures.length,
        status: `deck.gl ${layers.length} layers / ${structures.length} structures`,
      });
    }
  }, [
    structures,
    selectedId,
    isExploded,
    selectedFloor,
    colorMode,
  ]);

  return null;
};
