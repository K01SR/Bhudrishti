import { create } from 'zustand';

export type MapMode = 'SURFACE' | '3D' | 'UNDERGROUND';

export type InspectionState =
  | 'NORMAL'
  | 'BUILDING_SELECTED'
  | '3D_INSPECTION'
  | 'EXPLODED_VIEW'
  | 'FLOOR_SELECTED';

/**
 * Every measured quantity is nullable, and the reason it is missing is carried
 * alongside it.
 *
 * These fields used to be required numbers, which meant any building that
 * arrived without them had to be given values. OpenStreetMap supplies a
 * footprint and often nothing else, so the studio filled in `floors || 4`,
 * `height || floors * 3.5`, `fsi = 2.3`, a `PASS`/`EXCEEDED` verdict derived
 * from that invented FSI, and a base64 string presented as a 3D ULPIN. A null
 * is answerable; a fabricated floor count with a compliance verdict attached is
 * not, and it looked identical to a surveyed one.
 */
export interface SelectedBuilding {
  id: string;
  name: string;
  osmId?: string;
  /** Metres, or null when the source has no height. */
  heightM: number | null;
  /** True when heightM was derived from a floor count rather than measured. */
  heightIsModelled?: boolean;
  /**
   * Storeys, or null when the source has no count. May be derived from heightM
   * at an assumed floor-to-floor; when it is, floorsIsModelled is set and the
   * UI must label it as an assumption. Never a fallback constant.
   */
  floorsCount: number | null;
  /** True when floorsCount was derived from a height rather than counted. */
  floorsIsModelled?: boolean;
  landUse: string | null;
  /**
   * Floor Space Index. Null unless a real source states it. There is no default
   * FSI, and no verdict may be derived without one.
   */
  fsi: number | null;
  /** Only meaningful when fsi is non-null. */
  fsiStatus: 'PASS' | 'EXCEEDED' | null;
  coordinates: number[][][];
  centroid: [number, number]; // [lng, lat]
  tags?: Record<string, any>;
  /**
   * A locally derived handle for this geometry, clearly NOT a government
   * identifier. Prefixed DERIVED-, never 3D-ULPIN, so it cannot be mistaken for
   * a ULPIN or cited as one.
   */
  derivedLocalId: string;
  /**
   * Only ever set from a real cadastral source. There is no fallback: an
   * unverified building has no official ULPIN, and inventing one attaches a
   * fabricated government identifier to real property.
   */
  officialCadastreUlpin?: string;
  dataLineage: 'OPENSTREETMAP' | 'OFFICIAL_CADASTRE' | 'SYNTHETIC_TWIN';
  /** Human-readable statement of what is measured vs derived vs absent. */
  dataNote?: string;
}

export type ColorMode = 'height' | 'landuse' | 'fsi' | 'lineage';

interface OpenStudioState {
  // Navigation & Panels
  leftPanelOpen: boolean;
  rightPanelOpen: boolean;
  bottomBarOpen: boolean;
  activeInspectorTab: 'massing' | 'strata' | 'civic' | 'lineage';

  // Modes & View
  mapMode: MapMode;
  inspectionState: InspectionState;
  colorMode: ColorMode;

  // Layer Toggles
  layers: {
    buildings3D: boolean;
    landParcels: boolean;
    roadNetwork: boolean;
    civicAmenities: boolean;
    localityLabels: boolean;
    subsurfacePipes: boolean;
    officialCadastre: boolean;
    terrainRelief: boolean;
    satelliteImagery: boolean;
  };

  // Selected Structure & Strata
  selectedBuilding: SelectedBuilding | null;
  selectedFloor: number | null;
  isExploded: boolean;

  // Camera & Search
  cameraCenter: [number, number];
  cameraZoom: number;
  cameraPitch: number;
  cameraBearing: number;

  // Actions
  setLeftPanelOpen: (open: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
  setBottomBarOpen: (open: boolean) => void;
  setActiveInspectorTab: (tab: 'massing' | 'strata' | 'civic' | 'lineage') => void;
  setMapMode: (mode: MapMode) => void;
  setColorMode: (mode: ColorMode) => void;
  toggleLayer: (layer: keyof OpenStudioState['layers']) => void;
  selectBuilding: (building: SelectedBuilding | null) => void;
  selectFloor: (floor: number | null) => void;
  toggleExplode: () => void;
  flyToLocation: (center: [number, number], zoom?: number, pitch?: number) => void;
}

export const useOpenStudioStore = create<OpenStudioState>((set) => ({
  leftPanelOpen: true,
  rightPanelOpen: true,
  bottomBarOpen: false,
  activeInspectorTab: 'massing',

  mapMode: '3D',
  inspectionState: 'NORMAL',
  colorMode: 'height',

  layers: {
    buildings3D: true,
    landParcels: true,
    roadNetwork: true,
    civicAmenities: true,
    localityLabels: true,
    subsurfacePipes: true,
    officialCadastre: true,
    // Off by default: relief changes the read of the basemap, so it should be
    // something the operator asks for rather than something they have to
    // switch off.
    terrainRelief: false,
    satelliteImagery: false,
  },

  selectedBuilding: null,
  selectedFloor: null,
  isExploded: false,

  cameraCenter: [72.9984, 19.1557], // Default Airoli Sector 8 Pilot
  cameraZoom: 16.5,
  cameraPitch: 58,
  cameraBearing: -18,

  setLeftPanelOpen: (open) => set({ leftPanelOpen: open }),
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
  setBottomBarOpen: (open) => set({ bottomBarOpen: open }),
  setActiveInspectorTab: (tab) => set({ activeInspectorTab: tab }),

  setMapMode: (mapMode) =>
    set({
      mapMode,
      cameraPitch: mapMode === 'SURFACE' ? 0 : 58,
    }),

  setColorMode: (colorMode) => set({ colorMode }),

  toggleLayer: (layer) =>
    set((state) => ({
      layers: {
        ...state.layers,
        [layer]: !state.layers[layer],
      },
    })),

  selectBuilding: (building) =>
    set({
      selectedBuilding: building,
      selectedFloor: null,
      isExploded: false,
      inspectionState: building ? 'BUILDING_SELECTED' : 'NORMAL',
      rightPanelOpen: building ? true : false,
    }),

  selectFloor: (floor) =>
    set({
      selectedFloor: floor,
      inspectionState: floor !== null ? 'FLOOR_SELECTED' : 'EXPLODED_VIEW',
    }),

  toggleExplode: () =>
    set((state) => ({
      isExploded: !state.isExploded,
      selectedFloor: null,
      inspectionState: !state.isExploded ? 'EXPLODED_VIEW' : '3D_INSPECTION',
    })),

  flyToLocation: (center, zoom = 16.5, pitch = 58) =>
    set({
      cameraCenter: center,
      cameraZoom: zoom,
      cameraPitch: pitch,
    }),
}));
