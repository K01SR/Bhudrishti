export const LIDAR_RECORD_STRIDE = 20;

export interface LidarClassMeta {
  code: number;
  name: string;
  label: string;
  color: string;
  count: number;
  present: boolean;
}

export interface LidarLevel {
  level_code: string;
  floor_number: number;
  name?: string;
  level_type?: string;
  min_z: number;
  max_z: number;
}

export interface LidarSurroundingParcel {
  ulpin?: string;
  survey_number?: string;
  building_code?: string;
  building_name?: string;
  proposed_3d_id?: string;
  units?: any[];
  units_count?: number;
  ring: number[][];
  footprint?: number[][];
  height_m?: number;
  floors_count?: number;
  levels?: LidarLevel[];
  type?: string;
  status?: string;
  risk_level?: string;
  fsi?: number;
}

export interface LidarGroundTruth {
  ulpin: string;
  proposed_3d_id?: string;
  parcel_ring: number[][];
  building_code: string;
  building_name: string;
  footprint: number[][];
  height_m: number;
  floors_count: number;
  levels: LidarLevel[];
  units?: any[];
  units_count?: number;
  surrounding_parcels: LidarSurroundingParcel[];
}

export interface LidarScene {
  dataset: {
    id: string;
    name: string;
    source: string;
    demo: boolean;
    demo_note: string;
    license: string;
    crs: { epsg: number; name: string; local_frame_offset_m: number[] };
    format: string;
    point_format: number;
    attributes: string[];
    has_rgb: boolean;
    intensity_range: number[];
    epochs_available: number;
    multi_epoch: boolean;
    multi_epoch_note?: string;
  };
  stats: {
    point_count: number;
    bounds: { min: number[]; max: number[] };
    span_m: number[];
    center: number[];
    density_pts_m2: number;
    classifications: LidarClassMeta[];
  };
  ground_truth: LidarGroundTruth;
}

/** Decoded point cloud: flat arrays, one entry per point. */
export interface DecodedPointCloud {
  positions: Float32Array; // n * 3
  gps: Float32Array; // n
  classification: Uint8Array; // n
  intensity: Uint8Array; // n, 0..255
  returnNumber?: Uint8Array; // n, 1..4 (ASPRS return ordinal within one scan)
  count: number;
}

/**
 * A vertical-change "delta" needs two independent passes over the same scene.
 * `returnNumber` cannot stand in for that: it is the ordinal of a return
 * within a single scan, so `rn === 2` means "second bounce off the same beam",
 * not "seen again in a later epoch". Deriving an epoch delta from it, or from a
 * high intensity value, would invent the finding rather than measure it.
 */
export type EpochDeltaBasis = { kind: 'multi_epoch'; epochOfPoint: Uint8Array } | null;

export type ColorMode =
  | 'monochrome'
  | 'elevation'
  | 'intensity'
  | 'classification'
  | 'gradient'
  | 'rgb'
  | 'epoch2_delta';

export type PointShape = 'splat' | 'disc' | 'voxel';

export type QualityMode = 'low' | 'medium' | 'high' | 'auto';

export type CameraPreset =
  | 'fit'
  | 'building'
  | 'floor'
  | 'top'
  | 'north'
  | 'front'
  | 'side';

export type Tool = 'select' | 'measure' | 'slice' | 'clip';

export interface LidarSelection {
  ulpin: string;
  label: string;
  buildingCode?: string;
  buildingName?: string;
  proposed_3d_id?: string;
  units?: any[];
  units_count?: number;
  parcelRing: number[][];
  footprint: number[][];
  levels: LidarLevel[];
  heightM: number;
}

export const CLASS_COLORS: Record<number, string> = {
  2: '#6b5b4f',
  5: '#4a9d6f',
  6: '#d9a13e',
};

export const CLASS_LABELS: Record<number, string> = {
  2: 'Ground',
  5: 'High Vegetation',
  6: 'Building',
};

export const FAILSAFE_BOUNDS = {
  min: [118.0, 119.49, -3.49],
  max: [199.5, 192.34, 18.06],
};

/** Camera home framing target (local metres, Z-up). */
export function sceneCenterOf(bounds?: LidarScene['stats']['bounds']) {
  const b = bounds ?? { min: FAILSAFE_BOUNDS.min, max: FAILSAFE_BOUNDS.max };
  return [
    (b.min[0] + b.max[0]) / 2,
    (b.min[1] + b.max[1]) / 2,
    (b.min[2] + b.max[2]) / 2,
  ];
}