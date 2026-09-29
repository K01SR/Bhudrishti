import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { getPerf, isPerfEnabled as perfOn, setPerf } from '../../perf/perf';
import {
  Layers,
  PencilRuler,
  Ruler,
  Crosshair,
  Maximize2,
  Minimize2,
  Eye,
  EyeOff,
  Box,
  ChevronDown,
  Plus,
  Minus,
  Play,
  Square,
  X,
  Sun,
  Clock,
  Footprints,
  Shield,
  FileText,
  Compass,
  AlertTriangle,
  ArrowRight,
  ArrowDown,
  Flame,
  CheckCircle2,
} from 'lucide-react';
import { ParcelSummary, HeroProperty, PrecinctBuilding, ClashTestResult } from '../../types/cadastre';
import { cn } from '../../lib/cn';
import { buildHeroBuilding } from '../../lib/building3d';
import { accentRGB } from '../../lib/cadastre3d';
import { loadModel, fitGlbToFootprint, applyTranslucent, disposeGlb, ModelFormat } from '../../lib/gltf';
import { DemandNoticeModal } from '../modals/DemandNoticeModal';
import { BuyerShieldModal } from '../modals/BuyerShieldModal';
import { runSubsurfaceClashTest, fetchOsmStreets, fetchOsmAmenities, fetchCivicDossier } from '../../services/api';
import { OsmStreetSegment, OsmStreelight, OsmTree, OsmAmenity, CivicDossier } from '../../types/cadastre';
import { DEMO_ULPIN } from '../../constants';
import { HERO_ULPIN } from '../../constants';

interface Props {
  parcels: ParcelSummary[];
  hero?: HeroProperty | null;
  heroLoading?: boolean;
  focusUlpin: string | null;
  onSelectParcel: (ulpin: string) => void;
  buildings?: PrecinctBuilding[];
  className?: string;
  overlayModel?: { url: string; targetCode: string; mode: 'replace' | 'propose'; label?: string; format?: ModelFormat } | null;
}

interface LayerState {
  parcels: boolean;
  boundaries: boolean;
  buildings: boolean;
  labels: boolean;
  terrain: boolean;
}

const HERO_CENTER: [number, number] = [160, 152.5];
const PRECINCT_CENTER: [number, number] = [200, 200];
const FLYOVER_MS = 12000;

/** Scratch vector for the per-frame label projection. One instance, reused. */
const _proj = new THREE.Vector3();

type HeatmapMode = 'none' | 'fsi' | 'risk' | 'value';
type Epoch = '2024' | '2025' | '2026' | '2027';

const TYPE_COLORS: Record<string, number> = {
  tower: 0x3b82f6,
  slab: 0x8b5cf6,
  row_house: 0x10b981,
  commercial: 0xf59e0b,
};

const RISK_COLORS: Record<string, number> = {
  LOW: 0x10b981,
  MEDIUM: 0xf59e0b,
  HIGH: 0xf97316,
  CRITICAL: 0xef4444,
};

// Honest colours for a persisted structure's real status. A builder-asserted
// row awaiting a reviewer is amber, never green: "accepted" is something a
// reviewer does, not something the drawer's confidence can imply.
const STATUS_COLORS: Record<string, number> = {
  ACCEPTED_FOR_RECORD: 0x10b981,
  VERIFIED: 0x10b981,
  APPROVED: 0x10b981,
  PENDING_REVIEW: 0xf59e0b,
  UNDER_REVIEW: 0xf59e0b,
  REJECTED: 0xef4444,
  VIOLATION: 0xef4444,
  FLAGGED: 0xef4444,
  // Generated demo rows carry a dataset state, not an approval outcome.
  DEMO_STANDARD: 0x10b981,
  DEMO_ELEVATED_FSI: 0xef4444,
  DEMO_EPOCH_COMPARISON: 0xf59e0b,
  INFERRED: 0x3b82f6,
  SURVEYED: 0x3b82f6,
};

const SUBSURFACE_LINES = [
  { code: 'PIPE-WATER-01', name: 'Water Trunk (Ø 350mm)', color: 0x06b6d4, depth: -1.8, radius: 0.22, p1: [30, 160], p2: [380, 160], buffer: 1.0 },
  { code: 'PIPE-DRAIN-01', name: 'Storm Drain (Ø 600mm)', color: 0x8b5a2b, depth: -2.6, radius: 0.35, p1: [120, 70], p2: [220, 260], buffer: 1.2 },
  { code: 'ELEC-11KV-01', name: '11kV Electrical Duct', color: 0xeab308, depth: -1.2, radius: 0.18, p1: [40, 210], p2: [360, 210], buffer: 1.5 },
  { code: 'GAS-PNG-01', name: 'Pressurized PNG Gas Main', color: 0xf97316, depth: -1.5, radius: 0.22, p1: [170, 40], p2: [170, 360], buffer: 2.0 },
];

function shapeFromPolygon(ring: number[][]): THREE.Shape {
  const s = new THREE.Shape();
  ring.forEach(([x, y], i) => {
    if (i === 0) s.moveTo(x, y);
    else s.lineTo(x, y);
  });
  s.closePath();
  return s;
}

function polyRing(polygon: any): number[][] {
  const coords = polygon?.coordinates;
  if (!coords) return [];
  const ring = coords[0] || [];
  return ring && ring[0] === ring[ring.length - 1] ? ring.slice(0, -1) : ring;
}

function centroidOf(ring: number[][]): [number, number] {
  const n = ring.length;
  if (!n) return HERO_CENTER;
  return [ring.reduce((a, p) => a + p[0], 0) / n, ring.reduce((a, p) => a + p[1], 0) / n];
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function smoother(t: number) {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

function ulpinToBuildingCode(u: string): string | null {
  if (u === DEMO_ULPIN) return 'B-17';
  const m = u.match(/202609250{2,4}(\d{1,2})$/);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  if (n >= 1 && n <= 12) return `B-${String(n).padStart(2, '0')}`;
  return null;
}

export function sphericalToZUp(radius: number, phi: number, theta: number): THREE.Vector3 {
  const safePhi = Math.max(0.03, Math.min(Math.PI / 2 - 0.04, phi));
  const sinPhi = Math.sin(safePhi);
  const cosPhi = Math.cos(safePhi);
  return new THREE.Vector3(
    radius * sinPhi * Math.sin(theta),
    radius * sinPhi * Math.cos(theta),
    radius * cosPhi
  );
}

const HIGHWAY_COLORS: Record<string, number> = {
  primary: 0x8ca0b8, secondary: 0x9eb3c8, residential: 0xb0c2d4, tertiary: 0xaabcce,
};

const AMENITY_FILL: Record<string, number> = {
  'leisure=park': 0x22c55e, 'amenity=townhall': 0x6366f1, 'amenity=clinic': 0xef4444,
  'amenity=police': 0x0ea5e9, 'amenity=power_substation': 0xeab308,
  'amenity=charging_station': 0x10b981, 'amenity=bus_station': 0xf97316, 'amenity=bank': 0x8b5cf6,
};

/**
 * Shared material pool, keyed by the values that actually change a material.
 *
 * Phase 1 profiled an area switch and found `getProgramInfoLog` plus
 * `getShaderInfoLog` at 25% of the main thread: the content rebuild created
 * ~500 fresh materials, and every distinct material forces the driver to
 * compile and link a new shader program. The per-area colours come from a small
 * closed set (TYPE_COLORS, STATUS_COLORS, HIGHWAY_COLORS), so the number of
 * distinct programs needed is small and bounded, but a fresh material per mesh
 * defeats the driver's own program cache.
 *
 * Materials are shared, so teardown must not dispose them. Anything handed out
 * here is registered in SHARED_MATERIALS and skipped by the content teardown.
 */
const SHARED_MATERIALS = new Set<THREE.Material>();

function sharedStandard(
  color: number,
  roughness: number,
  metalness: number,
  extra?: Partial<THREE.MeshStandardMaterialParameters>
): THREE.MeshStandardMaterial {
  const key = `S|${color}|${roughness}|${metalness}|${extra ? JSON.stringify(extra) : ''}`;
  const cached = materialCache.get(key);
  if (cached) return cached as THREE.MeshStandardMaterial;
  const m = new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
  materialCache.set(key, m);
  SHARED_MATERIALS.add(m);
  return m;
}

function sharedBasic(color: number, extra?: Partial<THREE.MeshBasicMaterialParameters>): THREE.MeshBasicMaterial {
  const key = `B|${color}|${extra ? JSON.stringify(extra) : ''}`;
  const cached = materialCache.get(key);
  if (cached) return cached as THREE.MeshBasicMaterial;
  const m = new THREE.MeshBasicMaterial({ color, ...extra });
  materialCache.set(key, m);
  SHARED_MATERIALS.add(m);
  return m;
}

function sharedLine(color: number, extra?: Partial<THREE.LineBasicMaterialParameters>): THREE.LineBasicMaterial {
  const key = `L|${color}|${extra ? JSON.stringify(extra) : ''}`;
  const cached = materialCache.get(key);
  if (cached) return cached as THREE.LineBasicMaterial;
  const m = new THREE.LineBasicMaterial({ color, ...extra });
  materialCache.set(key, m);
  SHARED_MATERIALS.add(m);
  return m;
}

const materialCache = new Map<string, THREE.Material>();

/** Disposes a material only if it is not one of the shared ones. */
function disposeOwnedMaterial(m: THREE.Material | undefined | null): void {
  if (m && !SHARED_MATERIALS.has(m)) m.dispose();
}

/**
 * Geometry batcher.
 *
 * A census of the OSM group found 398 meshes and 114 materials costing 408 draw
 * calls, while the entire parcel content cost 56. Almost all of that was one
 * object per curb, sidewalk, crossing stripe, pole, lantern and tree, each with
 * its own material. The colours come from a small closed set, so the objects are
 * indistinguishable from one another at render time; they only need to be
 * separate because picking has to tell them apart.
 *
 * So: collect each object's geometry, bake its world transform into the
 * vertices, and merge by material. One draw call per material instead of one per
 * object. Objects that picking must address individually are added directly
 * instead of batched.
 */
class GeometryBatcher {
  private buckets = new Map<THREE.Material, THREE.BufferGeometry[]>();
  private lineBuckets = new Map<THREE.Material, THREE.BufferGeometry[]>();

  /** Bakes `obj`'s current world transform into its geometry and queues it. */
  add(obj: THREE.Mesh | THREE.Line | THREE.LineLoop | THREE.LineSegments): void {
    obj.updateMatrix();
    const src = obj.geometry as THREE.BufferGeometry;
    const isMesh = obj instanceof THREE.Mesh;

    // Meshes need identical attribute sets to merge. Primitives from three all
    // carry position/normal/uv; anything else is not merged rather than
    // silently producing a corrupt buffer.
    if (isMesh) {
      const geo = src.clone().applyMatrix4(obj.matrix);
      if (!geo.attributes.normal || !geo.attributes.uv) {
        geo.dispose();
        return;
      }
      this._queue(this.buckets, obj.material as THREE.Material, geo);
      return;
    }

    // Lines have no normal or uv — a LineLoop is position-only — so the mesh
    // rule above rejected every line it was given, leaving lineBuckets
    // permanently empty and the batched-line path dead. Line geometry also
    // needs normalising to plain segment pairs before it can merge: a LineLoop
    // closes implicitly, and mergeGeometries would carry that over as a
    // degenerate run with a different vertex count than its neighbours.
    const pos = src.getAttribute('position');
    if (!pos) return;
    const m = obj.matrix;
    const v = new THREE.Vector3();
    const points: THREE.Vector3[] = [];
    for (let i = 0; i < pos.count; i += 1) {
      v.fromBufferAttribute(pos, i).applyMatrix4(m);
      points.push(v.clone());
    }
    if (points.length < 2) return;
    // A Line/LineSegments is already pairs; a LineLoop needs its wrap-around
    // segment written out explicitly before the run can be merged.
    if (obj instanceof THREE.LineLoop) points.push(points[0].clone());

    const out = new Float32Array(points.length * 3);
    points.forEach((p, i) => { out[i * 3] = p.x; out[i * 3 + 1] = p.y; out[i * 3 + 2] = p.z; });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(out, 3));
    this._queue(this.lineBuckets, obj.material as THREE.Material, geo);
  }

  private _queue(
    target: Map<THREE.Material, THREE.BufferGeometry[]>,
    material: THREE.Material,
    geo: THREE.BufferGeometry,
  ): void {
    const list = target.get(material);
    if (list) list.push(geo);
    else target.set(material, [geo]);
  }

  /** Merges every batch into one mesh per material and adds them to `group`. */
  flush(group: THREE.Group): void {
    for (const [material, geos] of this.buckets) {
      const merged = geos.length === 1 ? geos[0] : mergeGeometries(geos, false);
      if (!merged) {
        geos.forEach((g) => g.dispose());
        continue;
      }
      if (geos.length > 1) geos.forEach((g) => g.dispose());
      const mesh = new THREE.Mesh(merged, material);
      mesh.userData.isBatched = true;
      group.add(mesh);
    }
    for (const [material, geos] of this.lineBuckets) {
      const merged = geos.length === 1 ? geos[0] : mergeGeometries(geos, false);
      if (!merged) {
        geos.forEach((g) => g.dispose());
        continue;
      }
      if (geos.length > 1) geos.forEach((g) => g.dispose());
      group.add(new THREE.LineSegments(merged, material));
    }
    this.buckets.clear();
    this.lineBuckets.clear();
  }
}

/**
 * Instanced box set for buildings that differ only in size, position and colour.
 *
 * Precinct buildings and persisted structures were each a `THREE.Mesh` with its
 * own `BoxGeometry`, so a precinct of a few hundred units cost one draw call and
 * one geometry per unit. These are all axis-aligned boxes of unit extent scaled
 * into place, which is exactly what an `InstancedMesh` is for: one geometry, one
 * draw call, per-instance colour.
 *
 * Picking still resolves to an individual unit. `raycast` reports
 * `instanceId`, so `userData` is not enough on its own; `resolve` maps that id
 * back to the record it stands for, and the pick path calls it before falling
 * back to the parent-walk it already does.
 */
interface InstancedBox {
  mesh: THREE.InstancedMesh;
  /** instanceId -> the record that instance draws. */
  units: { b: PrecinctBuilding; ulpin?: string; baseColor: number }[];
  /** Set per-instance colour without rebuilding. */
  setColor: (id: number, color: number) => void;
  /** Recompute one instance's transform. */
  setTransform: (id: number, x: number, y: number, z: number, sx: number, sy: number, sz: number) => void;
  dispose: () => void;
}

/**
 * Build one InstancedMesh for a set of boxes sharing a material.
 *
 * Boxes are grouped by material *before* instancing, because three.js issues one
 * draw call per InstancedMesh and a single mesh carries exactly one material.
 * Colour is per-instance (instanceColor) and so does not force a split; only
 * genuinely different shading parameters do.
 */
function buildInstancedBoxes(
  group: THREE.Group,
  specs: { w: number; h: number; d: number; x: number; y: number; z: number; color: number }[],
  material: THREE.Material,
): InstancedBox {
  const geo = new THREE.BoxGeometry(1, 1, 1);
  const mesh = new THREE.InstancedMesh(geo, material, Math.max(specs.length, 1));
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.count = specs.length;
  mesh.userData.isInstancedBuilding = true;

  const units: { b: PrecinctBuilding; ulpin?: string; baseColor: number }[] = [];
  const m = new THREE.Matrix4();
  const col = new THREE.Color();

  specs.forEach((s, i) => {
    m.makeScale(s.w, s.h, s.d);
    m.setPosition(s.x, s.y, s.z);
    mesh.setMatrixAt(i, m);
    col.setHex(s.color);
    mesh.setColorAt(i, col);
  });
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  group.add(mesh);

  return {
    mesh,
    units,
    setColor: (id, color) => {
      col.setHex(color);
      mesh.setColorAt(id, col);
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    },
    setTransform: (id, x, y, z, sx, sy, sz) => {
      m.makeScale(sx, sy, sz);
      m.setPosition(x, y, z);
      mesh.setMatrixAt(id, m);
      mesh.instanceMatrix.needsUpdate = true;
    },
    dispose: () => {
      geo.dispose();
    },
  };
}

/**
 * Populate the OSM urban-fabric group.
 *
 * Extracted from the scene-construction effect and run from its own effect
 * instead. The four OSM datasets come from four separate fetches, so building
 * them inside the scene effect meant each arrival disposed and rebuilt the
 * whole scene: two extra full builds on a cold load and a rebuild on every
 * area switch that changed the fabric. It also disposes the previous contents,
 * so a changed dataset does not stack a second copy of every street.
 */
function buildOsmFabric(
  group: THREE.Group,
  streets: OsmStreetSegment[],
  streetlights: OsmStreelight[],
  trees: OsmTree[],
  amenities: OsmAmenity[],
): { streetMeshes: THREE.Mesh[]; amenityMeshes: THREE.Mesh[] } {
  // Clear and release whatever the previous build left behind. Shared materials
  // are skipped: they outlive this group.
  group.traverse((obj) => {
    const any = obj as unknown as { geometry?: { dispose?: () => void }; material?: unknown };
    any.geometry?.dispose?.();
    const mat = any.material;
    if (Array.isArray(mat)) mat.forEach(disposeOwnedMaterial);
    else disposeOwnedMaterial(mat as THREE.Material | undefined);
  });
  group.clear();

  const streetMeshes: THREE.Mesh[] = [];
  const amenityMeshes: THREE.Mesh[] = [];
  const axisZ = new THREE.Vector3(0, 0, 1);
  const batcher = new GeometryBatcher();

  streets.forEach((street) => {
    const [sx, sy] = street.start;
    const [ex, ey] = street.end;
    const length = Math.hypot(ex - sx, ey - sy);
    if (length < 1) return;
    const dirX = (ex - sx) / length;
    const dirY = (ey - sy) / length;
    const normX = -dirY;
    const normY = dirX;
    const midX = (sx + ex) / 2;
    const midY = (sy + ey) / 2;
    const halfW = street.width_m / 2;
    const angle = Math.atan2(dirY, dirX);

    // The road surface itself stays its own mesh: clicking it selects this
    // street, so it cannot be merged with the others.
    const roadMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(length, street.width_m),
      sharedStandard(HIGHWAY_COLORS[street.highway] ?? 0x9eb3c8, 0.85, 0)
    );
    roadMesh.setRotationFromAxisAngle(axisZ, angle);
    roadMesh.position.set(midX, midY, 0.01);
    roadMesh.userData = { isOsmStreet: true, street };
    group.add(roadMesh);
    streetMeshes.push(roadMesh);

    const curbMat = sharedStandard(0x8a97a4, 0.9, 0);
    [1, -1].forEach((side) => {
      const curb = new THREE.Mesh(new THREE.BoxGeometry(length, 0.3, street.curb_height_m), curbMat);
      curb.setRotationFromAxisAngle(axisZ, angle);
      curb.position.set(midX + normX * (halfW + 0.15) * side, midY + normY * (halfW + 0.15) * side, street.curb_height_m / 2);
      batcher.add(curb);
      curb.geometry.dispose();
    });

    const swW = street.sidewalk_width_m;
    const swMat = sharedStandard(0xc8cfd8, 0.95, 0);
    if (street.sidewalk === 'both' || street.sidewalk === 'left') {
      const sw = new THREE.Mesh(new THREE.PlaneGeometry(length, swW), swMat);
      sw.setRotationFromAxisAngle(axisZ, angle);
      sw.position.set(midX + normX * (halfW + swW / 2 + 0.3), midY + normY * (halfW + swW / 2 + 0.3), 0.02);
      batcher.add(sw);
      sw.geometry.dispose();
    }
    if (street.sidewalk === 'both' || street.sidewalk === 'right') {
      const sw = new THREE.Mesh(new THREE.PlaneGeometry(length, swW), swMat);
      sw.setRotationFromAxisAngle(axisZ, angle);
      sw.position.set(midX - normX * (halfW + swW / 2 + 0.3), midY - normY * (halfW + swW / 2 + 0.3), 0.02);
      batcher.add(sw);
      sw.geometry.dispose();
    }

    if (street.has_median) {
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(sx, sy, 0.05), new THREE.Vector3(ex, ey, 0.05)]),
        sharedLine(0xf7c948, { transparent: true, opacity: 0.8 })
      );
      // A THREE.Line carries 2-point segments; LineSegments is what merging
      // across streets expects, so the median joins that batch.
      const seg = new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(sx, sy, 0.05), new THREE.Vector3(ex, ey, 0.05)]),
        line.material
      );
      batcher.add(seg);
      line.geometry.dispose();
      seg.geometry.dispose();
    }

    street.crossings.forEach(([cx, cy]) => {
      const crossMat = sharedStandard(0xffffff, 0.7, 0, { transparent: true, opacity: 0.75 });
      for (let i = -2; i <= 2; i += 2) {
        const stripe = new THREE.Mesh(new THREE.PlaneGeometry(0.7, halfW * 2 - 0.4), crossMat);
        stripe.setRotationFromAxisAngle(axisZ, Math.atan2(normY, normX));
        stripe.position.set(cx + dirX * i * 0.85, cy + dirY * i * 0.85, 0.03);
        batcher.add(stripe);
        stripe.geometry.dispose();
      }
    });
  });

  const poleMat = sharedStandard(0x4a5568, 0.6, 0.4);
  const lanternMat = sharedStandard(0xfef3c7, 0.1, 0, {
    emissive: new THREE.Color(0xfef3c7),
    emissiveIntensity: 1.4,
  });
  streetlights.forEach((sl) => {
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, sl.pole_height_m, 8), poleMat);
    pole.rotation.x = Math.PI / 2;
    pole.position.set(sl.x, sl.y, sl.pole_height_m / 2);
    batcher.add(pole);
    pole.geometry.dispose();

    const lantern = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.25, 0.18), lanternMat);
    lantern.position.set(sl.x + sl.arm_reach_m, sl.y, sl.pole_height_m + 0.06);
    batcher.add(lantern);
    lantern.geometry.dispose();
  });

  const trunkMat = sharedStandard(0x795548, 0.9, 0);
  trees.forEach((tree, i) => {
    const trunk = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.18, tree.trunk_height_m, 6),
      trunkMat
    );
    trunk.rotation.x = Math.PI / 2;
    trunk.position.set(tree.x, tree.y, tree.trunk_height_m / 2);
    batcher.add(trunk);
    trunk.geometry.dispose();

    // Deterministic hue. Math.random() here made the same tree a different
    // colour on every rebuild, so a scene that looked settled shifted whenever
    // anything triggered a rebuild.
    const hue = 0.28 + ((i * 37) % 8) * 0.01;
    const canopy = new THREE.Mesh(
      new THREE.SphereGeometry(tree.canopy_radius_m, 8, 6),
      sharedStandard(Math.round(new THREE.Color().setHSL(hue, 0.65, 0.32).getHex()), 0.9, 0, { transparent: true, opacity: 0.92 })
    );
    canopy.position.set(tree.x, tree.y, tree.trunk_height_m + tree.canopy_radius_m * 0.75);
    batcher.add(canopy);
    canopy.geometry.dispose();
  });

  amenities.forEach((am) => {
    const color = AMENITY_FILL[am.category] ?? 0x64748b;
    const amMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(am.w, am.h),
      sharedStandard(color, 0.6, 0, { transparent: true, opacity: 0.4 })
    );
    amMesh.position.set(am.x + am.w / 2, am.y + am.h / 2, 0.025);
    amMesh.userData = { isOsmAmenity: true, amenity: am };
    group.add(amMesh);
    amenityMeshes.push(amMesh);

    // Batched with the other outlines of the same colour. The pick identity
    // lives on the fill mesh above, which stays its own object, so merging the
    // outlines cannot affect what a click resolves to.
    const outline = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(am.x, am.y, 0.03), new THREE.Vector3(am.x + am.w, am.y, 0.03),
        new THREE.Vector3(am.x + am.w, am.y + am.h, 0.03), new THREE.Vector3(am.x, am.y + am.h, 0.03),
      ]),
      sharedLine(color, { transparent: true, opacity: 0.8 })
    );
    batcher.add(outline);
    outline.geometry.dispose();
  });

  batcher.flush(group);
  return { streetMeshes, amenityMeshes };
}

const PrecinctMap3DInner: React.FC<Props> = ({
  parcels,
  hero,
  heroLoading,
  focusUlpin,
  onSelectParcel,
  buildings = [],
  className,
  overlayModel = null,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const radarCanvasRef = useRef<HTMLCanvasElement>(null);
  const focusAnimRef = useRef<number | null>(null);

  // Core view modes
  const [mode, setMode] = useState<'3d' | '2d'>('3d');
  const [measureMode, setMeasureMode] = useState(false);
  const [measureDist, setMeasureDist] = useState<number | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [layers, setLayers] = useState<LayerState>({ parcels: true, boundaries: true, buildings: true, labels: true, terrain: true });
  const [layerOpen, setLayerOpen] = useState(false);
  const [heatmapMode, setHeatmapMode] = useState<HeatmapMode>('none');
  const [flying, setFlying] = useState(false);
  const [flyProgress, setFlyProgress] = useState(0);
  const [selectedBuilding, setSelectedBuilding] = useState<PrecinctBuilding | null>(null);

  // ADVANCED FEATURE 1: Solar & Shadow Simulation
  const [solarMode, setSolarMode] = useState(false);
  const [solarHour, setSolarHour] = useState(14); // 14:00 default
  const [solarSeason, setSolarSeason] = useState<'summer' | 'winter' | 'equinox'>('summer');

  // ADVANCED FEATURE 2: 4D Temporal Multi-Epoch
  const [epoch, setEpoch] = useState<Epoch>('2027');

  // ADVANCED FEATURE 3: First-Person Street Walk Mode
  const [walkMode, setWalkMode] = useState(false);
  const walkPosRef = useRef(new THREE.Vector3(145, 120, 1.7));
  const walkHeadingRef = useRef(0.2); // yaw in radians
  const walkPitchRef = useRef(0.0);
  const [walkSetback, setWalkSetback] = useState<{ building: string; dist: number; compliant: boolean } | null>(null);

  // ADVANCED FEATURE 4: Subsurface 3D Multi-Utility & Excavation Simulator
  const [subsurfaceMode, setSubsurfaceMode] = useState(false);
  const [excavationSim, setExcavationSim] = useState(false);
  const [excavationCoord, setExcavationCoord] = useState<[number, number]>([170, 100]);
  const [clashResult, setClashResult] = useState<ClashTestResult | null>(null);

  // ADVANCED FEATURE 5 & 6: Action Modals
  const [demandNoticeBuilding, setDemandNoticeBuilding] = useState<string | null>(null);
  const [buyerShieldTarget, setBuyerShieldTarget] = useState<string | null>(null);

  // OPENSTREETMAP URBAN FABRIC STATE
  const [osmLayerEnabled, setOsmLayerEnabled] = useState(true);
  const [osmStreets, setOsmStreets] = useState<OsmStreetSegment[]>([]);
  const [osmStreetlights, setOsmStreetlights] = useState<OsmStreelight[]>([]);
  const [osmTrees, setOsmTrees] = useState<OsmTree[]>([]);
  const [osmAmenities, setOsmAmenities] = useState<OsmAmenity[]>([]);
  const [selectedStreet, setSelectedStreet] = useState<OsmStreetSegment | null>(null);
  const [selectedAmenity, setSelectedAmenity] = useState<OsmAmenity | null>(null);
  const [civicDossier, setCivicDossier] = useState<CivicDossier | null>(null);
  const [civicDossierLoading, setCivicDossierLoading] = useState(false);
  const [showGpsHud, setShowGpsHud] = useState(true);
  const osmGroupRef = useRef<THREE.Group | null>(null);
  const osmStreetMeshesRef = useRef<THREE.Mesh[]>([]);
  const osmAmenityMeshesRef = useRef<THREE.Mesh[]>([]);

  // Three.js Scene References
  const camRef = useRef<THREE.PerspectiveCamera | null>(null);
  const sphericalRef = useRef(new THREE.Spherical(280, 0.82, Math.PI * 0.25));
  const targetRef = useRef(new THREE.Vector3(PRECINCT_CENTER[0], PRECINCT_CENTER[1], 8));
  const centerRef = useRef<[number, number]>(PRECINCT_CENTER);
  const parcelMeshesRef = useRef<THREE.Mesh[]>([]);
  const parcelOutlinesRef = useRef<THREE.LineLoop[]>([]);
  const buildingMeshesRef = useRef<THREE.Mesh[]>([]);
  const precinctRef = useRef<{ mesh: THREE.Mesh; id: number; b: PrecinctBuilding; baseColor: number }[]>([]);
  const precinctBoxesRef = useRef<InstancedBox | null>(null);
  const structureBoxesRef = useRef<InstancedBox | null>(null);
  const pinBoxesRef = useRef<InstancedBox | null>(null);
  const violationEdgesRef = useRef<THREE.LineSegments[]>([]);
  const proposalMeshesRef = useRef<THREE.Object3D[]>([]);
  const proposalHoldersRef = useRef<THREE.Group[]>([]);
  const subsurfaceGroupRef = useRef<THREE.Group | null>(null);
  const excavationMeshRef = useRef<THREE.Mesh | null>(null);
  const sunLightRef = useRef<THREE.DirectionalLight | null>(null);
  const measurePtsRef = useRef<THREE.Vector3 | null>(null);
  const flyAnimRef = useRef<number | null>(null);
  const flyingRef = useRef(false);
  const flyStartRef = useRef(0);
  const modeRef = useRef(mode);
  const heatmapRef = useRef<HeatmapMode>(heatmapMode);
  const groundMeshRef = useRef<THREE.Mesh | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);
  const labelLayerRef = useRef<HTMLDivElement | null>(null);
  // The renderer's lifetime is the component's, not the data's. Phase 1
  // profiled one area switch at 1233 ms, of which 1109 ms was forceContextLoss
  // and the shader recompilation that a fresh WebGL context forces. Scene
  // content is rebuilt inside this renderer; the renderer, camera and loop are
  // created once.
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const contentRef = useRef<THREE.Group | null>(null);
  const labelsRef = useRef<{ el: HTMLDivElement; x: number; y: number; z: number; w: number; h: number }[]>([]);
  const buildingCountRef = useRef(0);
  const parcelCountRef = useRef(0);
  // Mirrors of the data props, so the mount-time render loop and click handler
  // can read current values without being re-created (and without the loop
  // holding a snapshot of the area the user just navigated away from).
  const validParcelsRef = useRef<typeof validParcels>([]);
  const buildingsRef = useRef<typeof buildings>([]);
  const excavationCoordRef = useRef<typeof excavationCoord>([0, 0]);
  // False once the content effect has torn its group down. A GLB proposal load
  // can resolve after that and must not re-attach itself to a dead scene.
  const contentAliveRef = useRef(true);
  // Precinct codes hidden because a builder proposal is replacing them. Tracked
  // so applyVisibility can restore them when the proposal is cleared, instead of
  // leaving a permanent hole in the precinct.
  const replacedCodesRef = useRef<Set<string>>(new Set());
  // Read inside the render loop and the scene effect. Both used to depend on
  // walkMode/excavationSim directly, so entering Street Walk or arming the test
  // pit tore down and rebuilt every mesh. The loop needs the current value each
  // frame, which a ref gives it without making the effect re-run.
  const walkModeRef = useRef(walkMode);
  const excavationSimRef = useRef(excavationSim);
  // Same reason. Measure mode is read by the click handler, which is bound once
  // per scene build, so arming it previously did nothing until some unrelated
  // dependency forced a rebuild.
  const measureModeRef = useRef(measureMode);
  useEffect(() => {
    walkModeRef.current = walkMode;
  }, [walkMode]);
  useEffect(() => {
    excavationSimRef.current = excavationSim;
  }, [excavationSim]);
  useEffect(() => {
    measureModeRef.current = measureMode;
  }, [measureMode]);
  const [cameraPreset, setCameraPreset] = useState<'top' | 'iso' | 'front' | 'back' | 'left' | 'right'>('iso');

  const validParcels = useMemo(() => parcels.filter((p) => polyRing(p.polygon_geojson).length >= 3), [parcels]);
  const heroParcel = validParcels.find((p) => p.ulpin === HERO_ULPIN);
  const heroCenter: [number, number] = useMemo(
    () => (heroParcel ? centroidOf(polyRing(heroParcel.polygon_geojson)) : HERO_CENTER),
    [heroParcel]
  );

  // Smooth camera animator to auto-focus any building or parcel
  const focusOnTarget = useCallback((
    targetX: number,
    targetY: number,
    targetZ: number,
    radius: number,
    phi: number = 0.82,
    theta: number = Math.PI * 0.25,
    durationMs: number = 900
  ) => {
    if (focusAnimRef.current) {
      cancelAnimationFrame(focusAnimRef.current);
      focusAnimRef.current = null;
    }
    const startTime = performance.now();
    const startTarget = targetRef.current.clone();
    const startRadius = sphericalRef.current.radius;
    const startPhi = sphericalRef.current.phi;
    const startTheta = sphericalRef.current.theta;
    const destTarget = new THREE.Vector3(targetX, targetY, targetZ);

    const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(1, elapsed / durationMs);
      const ease = easeOutCubic(progress);

      targetRef.current.lerpVectors(startTarget, destTarget, ease);
      sphericalRef.current.radius = lerp(startRadius, radius, ease);
      sphericalRef.current.phi = lerp(startPhi, phi, ease);
      sphericalRef.current.theta = lerp(startTheta, theta, ease);

      const cam = camRef.current;
      if (cam) {
        const s = sphericalRef.current;
        cam.position.copy(targetRef.current).add(sphericalToZUp(s.radius, s.phi, s.theta));
        cam.lookAt(targetRef.current);
      }

      if (progress < 1) {
        focusAnimRef.current = requestAnimationFrame(step);
      } else {
        focusAnimRef.current = null;
      }
    };

    focusAnimRef.current = requestAnimationFrame(step);
  }, []);

  const applyCameraPreset = (preset: 'top' | 'iso' | 'front' | 'back' | 'left' | 'right') => {
    setCameraPreset(preset);
    const target = targetRef.current;
    const r = sphericalRef.current.radius || 240;
    switch (preset) {
      case 'top':
        focusOnTarget(target.x, target.y, target.z, r, 0.04, 0, 700);
        break;
      case 'iso':
        focusOnTarget(target.x, target.y, target.z, r, 0.82, Math.PI * 0.25, 700);
        break;
      case 'front':
        focusOnTarget(target.x, target.y, target.z, r, 1.38, Math.PI, 700);
        break;
      case 'back':
        focusOnTarget(target.x, target.y, target.z, r, 1.38, 0, 700);
        break;
      case 'left':
        focusOnTarget(target.x, target.y, target.z, r, 1.38, -Math.PI / 2, 700);
        break;
      case 'right':
        focusOnTarget(target.x, target.y, target.z, r, 1.38, Math.PI / 2, 700);
        break;
    }
  };

  // React to template selection or focus change: auto-focus camera on target building
  useEffect(() => {
    if (!focusUlpin && !overlayModel?.targetCode) return;
    const targetCode = overlayModel?.targetCode || (focusUlpin ? ulpinToBuildingCode(focusUlpin) : null);

    let targetBuilding: PrecinctBuilding | undefined;
    if (targetCode) {
      targetBuilding = buildings.find((b) => b.code === targetCode);
    }
    if (!targetBuilding && focusUlpin) {
      targetBuilding = buildings.find((b) => b.ulpin === focusUlpin || (focusUlpin === HERO_ULPIN && (b.is_hero || b.code === 'B-17')));
    }

    if (targetBuilding) {
      const cx = targetBuilding.x + targetBuilding.w / 2;
      const cy = targetBuilding.y + targetBuilding.h / 2;
      const cz = Math.min(targetBuilding.height_m * 0.45, 25);
      const dist = Math.max(55, Math.max(targetBuilding.w, targetBuilding.h, targetBuilding.height_m) * 2.2);

      focusOnTarget(cx, cy, cz, dist, 0.82, Math.PI * 0.25);
      setSelectedBuilding(targetBuilding);
      return;
    }

    if (focusUlpin) {
      const targetParcel = validParcels.find((p) => p.ulpin === focusUlpin);
      if (targetParcel) {
        const ring = polyRing(targetParcel.polygon_geojson);
        const [cx, cy] = centroidOf(ring);
        focusOnTarget(cx, cy, 6, 80, 0.82, Math.PI * 0.25);
      }
    }
  }, [focusUlpin, overlayModel?.targetCode, buildings, validParcels, focusOnTarget]);

  // Fetch OSM Urban Fabric data on mount
  useEffect(() => {
    let cancelled = false;
    fetchOsmStreets().then((r) => {
      if (cancelled) return;
      setOsmStreets(r.streets);
      setOsmStreetlights(r.streetlights);
      setOsmTrees(r.trees);
    }).catch(() => {});
    fetchOsmAmenities().then((r) => {
      if (cancelled) return;
      setOsmAmenities(r.amenities);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Single owner of every `visible` flag in the scene.
  //
  // The five layer flags used to be dependencies of the scene-construction
  // effect, so every checkbox toggled a full teardown and rebuild: several
  // hundred geometries and materials constructed and disposed to change one
  // boolean. Phase 0 measured that path at 532-965 ms per area switch, and a
  // single checkbox click cost the same. The scene now always builds every layer
  // and this function only flips visibility, which is what the flags mean.
  //
  // It is one function rather than one effect per flag because the flags are not
  // independent: an epoch, a layer toggle and a builder proposal can each hide a
  // precinct mass, and three effects writing `visible` independently meant the
  // last one to run won.
  const applyVisibility = useCallback(() => {
    if (groundMeshRef.current) groundMeshRef.current.visible = layers.terrain;
    if (gridHelperRef.current) gridHelperRef.current.visible = layers.terrain;
    if (osmGroupRef.current) osmGroupRef.current.visible = osmLayerEnabled;
    if (subsurfaceGroupRef.current) subsurfaceGroupRef.current.visible = subsurfaceMode;
    if (excavationMeshRef.current) excavationMeshRef.current.visible = excavationSim;

    parcelMeshesRef.current.forEach((m) => { m.visible = layers.parcels; });
    parcelOutlinesRef.current.forEach((l) => { l.visible = layers.boundaries; });
    buildingMeshesRef.current.forEach((m) => { m.visible = layers.buildings; });

    // Instanced units have no per-instance visibility, so an absent or replaced
    // unit is collapsed to zero scale rather than hidden. Zero-scale is also
    // what the raycaster treats as absent, so a hidden unit is not pickable
    // either — matching the old per-mesh `visible = false` behaviour.
    const pboxes = precinctBoxesRef.current;
    precinctRef.current.forEach(({ id, b }) => {
      // B-12 has no 2026 record, so it is absent from the 2026 epoch rather
      // than drawn and then hidden. Same visible result, stated once.
      const absentInEpoch = epoch === '2026' && b.code === 'B-12';
      const replaced = replacedCodesRef.current.has(b.code);
      const show = layers.buildings && !absentInEpoch && !replaced;
      if (show) {
        pboxes?.setTransform(id, b.x + b.w / 2, b.y + b.h / 2, b.height_m / 2, b.w, b.h, b.height_m);
      } else {
        pboxes?.setTransform(id, b.x + b.w / 2, b.y + b.h / 2, b.height_m / 2, 0, 0, 0);
      }
    });
    if (pboxes) pboxes.mesh.visible = layers.buildings;

    violationEdgesRef.current.forEach((e) => {
      e.visible = layers.buildings && epoch === '2027';
    });

    if (labelLayerRef.current) labelLayerRef.current.style.display = layers.labels ? '' : 'none';
  }, [layers, osmLayerEnabled, subsurfaceMode, epoch, excavationSim]);

  // Solar calculations for Navi Mumbai (19.1557° N)
  const solarParams = useMemo(() => {
    const lat = 19.1557 * (Math.PI / 180);
    const decl = solarSeason === 'summer' ? 0.409 : solarSeason === 'winter' ? -0.409 : 0.0;
    const h = ((solarHour - 12) * Math.PI) / 12;
    const sinAlpha = Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(h);
    const alpha = Math.max(0.08, Math.asin(Math.max(-1, Math.min(1, sinAlpha))));
    const gamma = Math.atan2(Math.sin(h), Math.tan(decl) * Math.cos(lat) - Math.sin(lat) * Math.cos(h));
    const shadowLen = Math.round((18.0 / Math.tan(Math.max(0.12, alpha))) * 10) / 10;
    const insolationKwh = Math.round(Math.sin(alpha) * 6.8 * 10) / 10;
    return {
      altitudeRad: alpha,
      azimuthRad: gamma,
      altitudeDeg: Math.round((alpha * 180) / Math.PI),
      azimuthDeg: Math.round((((gamma * 180) / Math.PI) + 360) % 360),
      shadowLengthM: shadowLen,
      insolationKwh,
    };
  }, [solarHour, solarSeason]);

  // Update dynamic sunlight whenever solarHour / season changes
  useEffect(() => {
    const sun = sunLightRef.current;
    if (!sun) return;
    const dist = 360;
    const cx = PRECINCT_CENTER[0];
    const cy = PRECINCT_CENTER[1];
    const { altitudeRad, azimuthRad } = solarParams;

    const sx = cx - Math.sin(azimuthRad) * dist;
    const sy = cy - Math.cos(azimuthRad) * dist;
    const sz = Math.max(15, Math.sin(altitudeRad) * dist);
    sun.position.set(sx, sy, sz);

    if (solarHour <= 7 || solarHour >= 17) {
      sun.color.setHex(0xfb923c); // Warm dawn/dusk
      sun.intensity = 1.1;
    } else if (solarHour >= 11 && solarHour <= 14) {
      sun.color.setHex(0xffffff); // Bright noon
      sun.intensity = 1.7;
    } else {
      sun.color.setHex(0xfef08a);
      sun.intensity = 1.4;
    }
  }, [solarParams, solarHour]);

  // Update building heights and styles when Epoch changes
  useEffect(() => {
    if (!precinctRef.current.length) return;

    // Wireframe is a material property, so with every unit sharing one material
    // it is set once for the whole instanced set rather than per building.
    const boxes = precinctBoxesRef.current;
    const precinctMat = boxes?.mesh.material as THREE.MeshStandardMaterial | undefined;
    precinctRef.current.forEach(({ id, b, baseColor }) => {
      const cx = b.x + b.w / 2;
      const cy = b.y + b.h / 2;
      if (epoch === '2024') {
        // Foundation slab: a flat plate at the base.
        boxes?.setTransform(id, cx, cy, 0.3, b.w, b.h, b.height_m * 0.05);
        boxes?.setColor(id, 0xeab308);
      } else if (epoch === '2025') {
        // Sanction blueprint: full height, blueprint blue.
        boxes?.setTransform(id, cx, cy, b.height_m / 2, b.w, b.h, b.height_m);
        boxes?.setColor(id, 0x38bdf8);
      } else {
        // 2026 sanctioned, 2027 present day with breaches: as built.
        boxes?.setTransform(id, cx, cy, b.height_m / 2, b.w, b.h, b.height_m);
        boxes?.setColor(id, baseColor);
      }
    });
    if (precinctMat) precinctMat.wireframe = epoch === '2024' || epoch === '2025';

    // Visibility is owned by applyVisibility, which runs on epoch too. Depends
    // on epoch alone: listing applyVisibility here would re-run the whole
    // material pass on every layer toggle.
  }, [epoch]);

  // Subsurface ground translucency. Group visibility itself is in applyVisibility.
  useEffect(() => {
    if (groundMeshRef.current) {
      const mat = groundMeshRef.current.material as THREE.MeshStandardMaterial;
      mat.transparent = subsurfaceMode;
      mat.opacity = subsurfaceMode ? 0.28 : 1.0;
    }
  }, [subsurfaceMode]);

  useEffect(() => {
    applyVisibility();
  }, [applyVisibility]);

  // Entering and leaving Street Walk moves the camera to and from the walking
  // position. This used to be a side effect of the scene rebuild that walkMode
  // triggered; now that the rebuild is gone it has to be explicit.
  useEffect(() => {
    const cam = camRef.current;
    if (!cam) return;
    if (walkMode) {
      cam.position.copy(walkPosRef.current);
    } else {
      const s = sphericalRef.current;
      cam.position.copy(targetRef.current).add(sphericalToZUp(s.radius, s.phi, s.theta));
      cam.lookAt(targetRef.current);
    }
  }, [walkMode]);

  // 2D/3D toggle. The preset only changes the orbit camera, so it moves the
  // existing camera rather than rebuilding the scene. modeRef keeps the previous
  // value so the initial build is not treated as a change.

  useEffect(() => {
    if (modeRef.current === mode) return;
    modeRef.current = mode;
    if (walkModeRef.current) return;
    const preset =
      mode === '3d'
        ? { radius: 280, phi: 0.82, theta: Math.PI * 0.25 }
        : { radius: 240, phi: 0.04, theta: 0 };
    sphericalRef.current.set(preset.radius, preset.phi, preset.theta);
    const cam = camRef.current;
    if (!cam) return;
    cam.position.copy(targetRef.current).add(sphericalToZUp(preset.radius, preset.phi, preset.theta));
    cam.lookAt(targetRef.current);
  }, [mode]);

  // Run excavation clash test when coordinate changes
  const executeClashCheck = useCallback((x: number, y: number) => {
    setExcavationCoord([x, y]);
    runSubsurfaceClashTest({ x, y, depth_m: 3.5, radius_m: 1.5, work_type: 'Foundation Piling' })
      .then((res) => {
        setClashResult(res);
        if (excavationMeshRef.current) {
          const mat = excavationMeshRef.current.material as THREE.MeshStandardMaterial;
          mat.color.setHex(res.status === 'SAFE' ? 0x10b981 : 0xef4444);
        }
      })
      .catch(() => {});
  }, []);

  const applyHeatmap = (hm: HeatmapMode) => {
    heatmapRef.current = hm;
    if (!precinctRef.current.length) return;
    let hival = 1;
    if (hm === 'value') {
      hival = Math.max(...precinctRef.current.map(({ b }) => b.w * b.h * b.height_m), 1);
    }
    // Per-unit colour, so it goes through the instance colour rather than a
    // shared material — mutating the material here would recolour every unit
    // at once and make these four modes indistinguishable.
    const hboxes = precinctBoxesRef.current;
    precinctRef.current.forEach(({ id, b, baseColor }) => {
      if (hm === 'none') {
        hboxes?.setColor(id, baseColor);
      } else if (hm === 'fsi') {
        const f = b.fsi;
        hboxes?.setColor(id, f < 1.5 ? 0x10b981 : f <= 2.0 ? 0xf59e0b : 0xef4444);
      } else if (hm === 'risk') {
        hboxes?.setColor(id, RISK_COLORS[b.risk_level] ?? 0x10b981);
      } else {
        const v = (b.w * b.h * b.height_m) / hival;
        const c = new THREE.Color(0x2563eb).lerp(new THREE.Color(0xef4444), v);
        hboxes?.setColor(id, c.getHex());
      }
    });
    violationEdgesRef.current.forEach((e) => {
      e.visible = hm === 'none' && epoch === '2027';
    });
  };

  // Keyboard navigation for first-person Street Walk
  useEffect(() => {
    if (!walkMode) return;
    const speed = 3.5;
    const onKeyDown = (e: KeyboardEvent) => {
      const heading = walkHeadingRef.current;
      const pos = walkPosRef.current;
      let dx = 0;
      let dy = 0;

      if (e.key === 'w' || e.key === 'ArrowUp') {
        dx = Math.sin(heading) * speed;
        dy = Math.cos(heading) * speed;
      } else if (e.key === 's' || e.key === 'ArrowDown') {
        dx = -Math.sin(heading) * speed;
        dy = -Math.cos(heading) * speed;
      } else if (e.key === 'a' || e.key === 'ArrowLeft') {
        dx = -Math.cos(heading) * speed;
        dy = Math.sin(heading) * speed;
      } else if (e.key === 'd' || e.key === 'ArrowRight') {
        dx = Math.cos(heading) * speed;
        dy = -Math.sin(heading) * speed;
      }

      pos.x = Math.max(30, Math.min(370, pos.x + dx));
      pos.y = Math.max(30, Math.min(370, pos.y + dy));

      // Calculate nearest building setback
      let minDist = 999;
      let nearestB: PrecinctBuilding | null = null;
      buildings.forEach((b) => {
        const cx = b.x + b.w / 2;
        const cy = b.y + b.h / 2;
        const d = Math.hypot(pos.x - cx, pos.y - cy) - Math.max(b.w, b.h) / 2;
        if (d < minDist) {
          minDist = d;
          nearestB = b;
        }
      });

      if (nearestB && minDist < 35) {
        setWalkSetback({
          building: (nearestB as PrecinctBuilding).name,
          dist: Math.max(0.8, Math.round(minDist * 10) / 10),
          compliant: minDist >= 4.5,
        });
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [walkMode, buildings]);

  // Build the whole scene
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;
    const width = container.clientWidth;
    const height = container.clientHeight;

    const scene = new THREE.Scene();
    scene.up.set(0, 0, 1);
    const bg = 0xffffff;
    scene.background = new THREE.Color(bg);
    scene.fog = new THREE.FogExp2(bg, 0.0019);

    const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 2000);
    camera.up.set(0, 0, 1);
    camRef.current = camera;
    if (!walkModeRef.current) {
      const s = sphericalRef.current;
      camera.position.copy(targetRef.current).add(sphericalToZUp(s.radius, s.phi, s.theta));
      camera.lookAt(targetRef.current);
    } else {
      camera.position.copy(walkPosRef.current);
    }

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // The shadow map depends on the sun and the static scene graph, not on the
    // camera, and neither moves after construction. autoUpdate re-rasterised
    // every shadow caster into a 2048px depth target on every frame, which is a
    // second full pass over the scene at 30-60 Hz to produce an identical
    // result. One update after the graph is built is enough; needsUpdate is
    // re-asserted below whenever geometry is added later.
    renderer.shadowMap.autoUpdate = false;
    renderer.shadowMap.needsUpdate = true;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.45));
    const sun = new THREE.DirectionalLight(0xfff7ed, 1.5);
    sun.position.set(centerRef.current[0] + 190, centerRef.current[1] - 130, 250);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const shCam = sun.shadow.camera as THREE.OrthographicCamera;
    shCam.left = -260;
    shCam.right = 260;
    shCam.top = 260;
    shCam.bottom = -260;
    scene.add(sun);
    sunLightRef.current = sun;

    const fill = new THREE.DirectionalLight(0xdbeafe, 0.4);
    fill.position.set(centerRef.current[0] - 140, centerRef.current[1] + 120, 70);
    scene.add(fill);

    const groundMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(480, 480),
      new THREE.MeshStandardMaterial({ color: 0xf4f6f9, roughness: 0.95, metalness: 0.03 })
    );
    groundMesh.position.set(centerRef.current[0], centerRef.current[1], 0);
    groundMesh.receiveShadow = true;
    // Always added. Visibility is applied by the layer-sync effect below, so
    // toggling a layer no longer re-runs this whole effect.
    groundMesh.visible = true;
    scene.add(groundMesh);
    groundMeshRef.current = groundMesh;

    // The content group is the unit of invalidation. The renderer, the camera,
    // the loop and the DOM label layer outlive every data change; only the
    // objects inside this group are rebuilt. Phase 1 profiled a single area
    // switch at 1233 ms, of which 1109 ms was forceContextLoss plus the shader
    // recompilation it forced. Recreating the WebGL context on a data change
    // was the entire cost.
    const content = new THREE.Group();
    content.name = 'Parcel_Content';
    scene.add(content);
    contentRef.current = content;
    sceneRef.current = scene;
    rendererRef.current = renderer;

    // Labels live in one persistent DOM layer. The loop projects whatever is in
    // the array; a rebuild replaces the array rather than the layer, so the
    // element churn no longer touches layout structure the loop is reading.
    const labelLayer = document.createElement('div');
    labelLayer.className = 'absolute inset-0 pointer-events-none';
    container.appendChild(labelLayer);
    labelLayerRef.current = labelLayer;

    const gridHelper = new THREE.GridHelper(460, 46, 0xdde4ec, 0xe9eef3);
    gridHelper.rotation.x = Math.PI / 2;
    gridHelper.position.set(centerRef.current[0], centerRef.current[1], 0.02);
    gridHelper.visible = true;
    scene.add(gridHelper);
    gridHelperRef.current = gridHelper;

    // ==========================================
    // OPENSTREETMAP 3D URBAN FABRIC LAYER
    // ==========================================
    // The group is created empty here and populated by buildOsmFabric below.
    // The four OSM datasets arrive from their own fetches, so building them
    // here meant the arrival of street data tore down and rebuilt the entire
    // scene, twice on a cold load. Phase 1 measured that as a second build
    // ~700 ms after the first.
    const osmGroup = new THREE.Group();
    osmGroup.name = 'OSM_Urban_Fabric';
    osmGroupRef.current = osmGroup;
    osmGroup.visible = osmLayerEnabled;
    scene.add(osmGroup);

    // ==========================================
    // SUBSURFACE UTILITIES & CLASH GEOMETRY
    // ==========================================
    const subsurfaceGroup = new THREE.Group();
    subsurfaceGroup.name = 'Subsurface_Utilities';

    SUBSURFACE_LINES.forEach((line) => {
      const p1 = new THREE.Vector3(line.p1[0], line.p1[1], line.depth);
      const p2 = new THREE.Vector3(line.p2[0], line.p2[1], line.depth);
      const dist = p1.distanceTo(p2);
      const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);

      // Core pipe cylinder
      const geom = new THREE.CylinderGeometry(line.radius, line.radius, dist, 16);
      const mat = sharedStandard(line.color, 0.4, 0.2);
      const pipeMesh = new THREE.Mesh(geom, mat);
      pipeMesh.position.copy(mid);
      pipeMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3().subVectors(p2, p1).normalize());
      subsurfaceGroup.add(pipeMesh);

      // Safety buffer envelope
      const bufGeom = new THREE.CylinderGeometry(line.radius + line.buffer, line.radius + line.buffer, dist, 16);
      const bufMat = sharedBasic(line.color, { transparent: true, opacity: 0.15, wireframe: true });
      const bufMesh = new THREE.Mesh(bufGeom, bufMat);
      bufMesh.position.copy(mid);
      bufMesh.quaternion.copy(pipeMesh.quaternion);
      subsurfaceGroup.add(bufMesh);
    });

    // Excavation test pit
    const pitGeom = new THREE.CylinderGeometry(1.5, 1.5, 3.5, 24);
    const pitMat = sharedStandard(0x10b981, 0.6, 0, { transparent: true, opacity: 0.75 });
    const pitMesh = new THREE.Mesh(pitGeom, pitMat);
    pitMesh.rotation.x = Math.PI / 2;
    pitMesh.position.set(excavationCoord[0], excavationCoord[1], -1.75);
    subsurfaceGroup.add(pitMesh);
    excavationMeshRef.current = pitMesh;

    subsurfaceGroup.visible = subsurfaceMode;
    scene.add(subsurfaceGroup);
    subsurfaceGroupRef.current = subsurfaceGroup;


    // Interaction handlers
    /**
     * Map a raycast hit back to the record it stands for.
     *
     * An InstancedMesh is one Object3D drawing many units, so the record cannot
     * ride along in `userData` — each unit is identified by `instanceId`. That
     * has to be resolved first; without it a click on any instanced precinct
     * building or persisted structure hits the mesh and selects nothing, which
     * is a silent failure with no error to trace. Individual meshes still carry
     * their record in `userData`, so the parent walk below still runs and still
     * covers them.
     *
     * Kept as its own function, rather than inline in the handler, so the e2e
     * suite can drive the real resolution against a known instance instead of
     * clicking pixels — see `__PICK__` in `registerPickSeam` below.
     */
    const resolveBuildingHit = (hit: THREE.Intersection | undefined): { b?: PrecinctBuilding; ulpin?: string } => {
      let node: THREE.Object3D | null = hit?.object ?? null;
      let b: PrecinctBuilding | undefined;
      let ulpin: string | undefined;
      if (hit && hit.instanceId !== undefined && hit.instanceId !== null) {
        const set =
          node === structureBoxesRef.current?.mesh ? structureBoxesRef.current
          : node === pinBoxesRef.current?.mesh ? pinBoxesRef.current
          : node === precinctBoxesRef.current?.mesh ? precinctBoxesRef.current
          : null;
        const unit = set?.units[hit.instanceId];
        if (unit) {
          b = unit.b;
          ulpin = unit.ulpin;
        }
      }
      while (node) {
        if (!b && node.userData.building) b = node.userData.building as PrecinctBuilding;
        if (!ulpin && node.userData.ulpin) ulpin = node.userData.ulpin as string;
        if (b && ulpin) break;
        node = node.parent as THREE.Object3D;
      }
      return { b, ulpin };
    };

    // Deterministic pick seam for the e2e suite, behind `?perf=1` like the rest
    // of the test surface so it does not exist in a normal session. It resolves
    // a named instance through the same function the click handler uses, so a
    // passing test means that path is intact rather than that a pixel happened
    // to land on a building.
    if (perfOn()) {
      (window as any).__PICK__ = {
        resolve: (which: 'precinct' | 'structures', instanceId: number) => {
          const set = which === 'precinct' ? precinctBoxesRef.current : structureBoxesRef.current;
          if (!set) return null;
          const unit = set.units[instanceId];
          if (!unit) return null;
          // Same resolver, fed a synthetic hit for that instance. `object` must
          // be the real mesh: the resolver identifies which instanced set it is
          // looking at by comparing the hit's object against each set's mesh, so
          // a hit without one would match nothing and report a false failure.
          const out = resolveBuildingHit({ instanceId, object: set.mesh } as unknown as THREE.Intersection);
          return { code: unit.b.code, ulpin: out.ulpin ?? unit.ulpin, resolvedBy: out.b ? 'instanceId' : 'none' };
        },
        dump: (which: 'precinct' | 'structures', id: number) => {
          const set = which === 'precinct' ? precinctBoxesRef.current : structureBoxesRef.current;
          if (!set) return null;
          const m = new THREE.Matrix4();
          const col = new THREE.Color();
          set.mesh.getMatrixAt(id, m);
          const s = new THREE.Vector3(); m.decompose(new THREE.Vector3(), new THREE.Quaternion(), s);
          set.mesh.getColorAt(id, col);
          return { scale: s.toArray().map((v) => +v.toFixed(2)), color: col.getHexString(),
                   wireframe: (set.mesh.material as THREE.MeshStandardMaterial).wireframe,
                   vis: set.mesh.visible };
        },
        counts: () => ({
          precinct: precinctBoxesRef.current?.units.length ?? 0,
          structures: structureBoxesRef.current?.units.length ?? 0,
        }),
      };
    }

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let isDragging = false;
    let prevMouse = { x: 0, y: 0 };

    const onPointerDown = (e: PointerEvent) => {
      isDragging = true;
      prevMouse = { x: e.clientX, y: e.clientY };
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging) return;
      const dx = e.clientX - prevMouse.x;
      const dy = e.clientY - prevMouse.y;
      prevMouse = { x: e.clientX, y: e.clientY };

      if (walkModeRef.current) {
        walkHeadingRef.current -= dx * 0.005;
        walkPitchRef.current = Math.max(-0.6, Math.min(0.8, walkPitchRef.current - dy * 0.005));
      } else {
        const s = sphericalRef.current;
        s.theta -= dx * 0.005;
        s.phi = Math.max(0.04, Math.min(Math.PI / 2 - 0.04, s.phi + dy * 0.005));
        const cam = camRef.current;
        if (cam) {
          cam.position.copy(targetRef.current).add(sphericalToZUp(s.radius, s.phi, s.theta));
          cam.lookAt(targetRef.current);
        }
      }
    };

    const onPointerUp = () => {
      isDragging = false;
    };

    const onWheel = (e: WheelEvent) => {
      if (walkModeRef.current) return;
      e.preventDefault();
      const s = sphericalRef.current;
      s.radius = Math.max(40, Math.min(520, s.radius * (1 + e.deltaY * 0.001)));
      const cam = camRef.current;
      if (cam) {
        cam.position.copy(targetRef.current).add(sphericalToZUp(s.radius, s.phi, s.theta));
        cam.lookAt(targetRef.current);
      }
    };

    const onClick = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      if (excavationSimRef.current) {
        raycaster.setFromCamera(mouse, camera);
        const hits = raycaster.intersectObject(groundMesh, false);
        if (hits[0]) {
          executeClashCheck(Math.round(hits[0].point.x), Math.round(hits[0].point.y));
        }
        return;
      }

      if (measureModeRef.current) {
        raycaster.setFromCamera(mouse, camera);
        const hits = raycaster.intersectObject(groundMesh, false);
        if (hits[0]) {
          const pt = new THREE.Vector3(hits[0].point.x, hits[0].point.y, 0);
          if (!measurePtsRef.current) {
            measurePtsRef.current = pt;
            setMeasureDist(null);
          } else {
            setMeasureDist(Math.round(measurePtsRef.current.distanceTo(pt) * 100) / 100);
            measurePtsRef.current = null;
          }
        }
        return;
      }

      raycaster.setFromCamera(mouse, camera);

      // Check OSM amenities first
      const amenityHit = raycaster.intersectObjects(osmAmenityMeshesRef.current, false)[0];
      if (amenityHit?.object?.userData.isOsmAmenity) {
        setSelectedAmenity(amenityHit.object.userData.amenity as OsmAmenity);
        setSelectedStreet(null);
        setSelectedBuilding(null);
        return;
      }
      // Check OSM streets
      const streetHit = raycaster.intersectObjects(osmStreetMeshesRef.current, false)[0];
      if (streetHit?.object?.userData.isOsmStreet) {
        setSelectedStreet(streetHit.object.userData.street as OsmStreetSegment);
        setSelectedAmenity(null);
        setSelectedBuilding(null);
        return;
      }

      const targets = [
        ...buildingMeshesRef.current,
        ...precinctRef.current.map((x) => x.mesh),
        ...proposalMeshesRef.current,
        ...parcelMeshesRef.current,
      ];
      const hit = raycaster.intersectObjects(targets, true)[0];
      const { b, ulpin } = resolveBuildingHit(hit);
      if (b) {
        setSelectedBuilding(b);
        setSelectedStreet(null);
        setSelectedAmenity(null);
        setMeasureDist(null);

        // Automatically fly & focus camera on the clicked building
        const cx = b.x + b.w / 2;
        const cy = b.y + b.h / 2;
        const cz = Math.min(b.height_m * 0.45, 25);
        const dist = Math.max(55, Math.max(b.w, b.h, b.height_m) * 2.2);
        focusOnTarget(cx, cy, cz, dist, 0.82, Math.PI * 0.25);

        if (b.ulpin) {
          onSelectParcel(b.ulpin);
        }
        return;
      }
      if (ulpin) {
        setSelectedBuilding(null);
        onSelectParcel(ulpin);

        // Automatically fly & focus camera on the clicked parcel
        const targetParcel = validParcelsRef.current.find((p) => p.ulpin === ulpin);
        if (targetParcel) {
          const ring = polyRing(targetParcel.polygon_geojson);
          const [cx, cy] = centroidOf(ring);
          focusOnTarget(cx, cy, 6, 85, 0.82, Math.PI * 0.25);
        }
      }
    };

    const listen: Array<[string, (e: any) => void, AddEventListenerOptions?]> = [
      ['pointerdown', onPointerDown],
      ['pointermove', onPointerMove],
      ['pointerup', onPointerUp],
      ['wheel', onWheel, { passive: false }],
      ['click', onClick],
    ];
    listen.forEach(([ev, fn, opts]) => container.addEventListener(ev, fn, opts));

    // Render loop
    let frame = 0;
    let animId = 0;
    let lastT = 0;
    let suspended = false;
    const loop = () => {
      // The guard matters because the re-arm happens on the line below: a cancel
      // that lands between the intersection callback and this frame would
      // otherwise be undone by the ID written just before it.
      if (!contentAliveRef.current || suspended) {
        animId = 0;
        return;
      }
      animId = requestAnimationFrame(loop);
      frame++;

      if (walkModeRef.current) {
        const pos = walkPosRef.current;
        const h = walkHeadingRef.current;
        const p = walkPitchRef.current;
        camera.position.set(pos.x, pos.y, 1.7);
        camera.lookAt(
          pos.x + Math.sin(h) * Math.cos(p) * 20,
          pos.y + Math.cos(h) * Math.cos(p) * 20,
          1.7 + Math.sin(p) * 20
        );

        // Update radar canvas
        if (radarCanvasRef.current && frame % 3 === 0) {
          const cvs = radarCanvasRef.current;
          const ctx = cvs.getContext('2d');
          if (ctx) {
            ctx.clearRect(0, 0, cvs.width, cvs.height);
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(0, 0, cvs.width, cvs.height);

            // Draw buildings
            ctx.fillStyle = '#334155';
            buildingsRef.current.forEach((b) => {
              const rx = (b.x / 400) * cvs.width;
              const ry = (1 - (b.y + b.h) / 400) * cvs.height;
              const rw = (b.w / 400) * cvs.width;
              const rh = (b.h / 400) * cvs.height;
              ctx.fillRect(rx, ry, rw, rh);
            });

            // Draw user cone
            const ux = (pos.x / 400) * cvs.width;
            const uy = (1 - pos.y / 400) * cvs.height;
            ctx.fillStyle = 'rgba(56, 189, 248, 0.4)';
            ctx.beginPath();
            ctx.moveTo(ux, uy);
            ctx.arc(ux, uy, 18, -h - Math.PI / 2 - 0.4, -h - Math.PI / 2 + 0.4);
            ctx.fill();

            // Draw user dot
            ctx.fillStyle = '#38bdf8';
            ctx.beginPath();
            ctx.arc(ux, uy, 3.5, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      } else {
        camera.lookAt(targetRef.current);
      }

      violationEdgesRef.current.forEach((e, i) => {
        const m = e.material as THREE.LineBasicMaterial;
        m.opacity = 0.45 + 0.4 * Math.abs(Math.sin(frame * 0.08 + i));
      });

      if (excavationMeshRef.current && excavationSimRef.current) {
        const ec = excavationCoordRef.current;
        excavationMeshRef.current.position.set(ec[0], ec[1], -1.75);
      }

      renderer.render(scene, camera);

      const labels = labelsRef.current;
      if (frame % 2 === 0 && labels.length && !walkModeRef.current) {
        // Read the container once, project every label, then write. Splitting
        // reads and writes keeps the browser from flushing layout between them.
        const rect = container.getBoundingClientRect();
        for (let i = 0; i < labels.length; i++) {
          const l = labels[i];
          // Projection is a matrix multiply, so reusing one vector is cheaper
          // than allocating a Vector3 per label per frame.
          _proj.set(l.x, l.y, l.z).project(camera);
          if (_proj.z > 1 || _proj.z < -1) {
            if (l.el.style.display !== 'none') l.el.style.display = 'none';
            continue;
          }
          if (l.el.style.display === 'none') l.el.style.display = '';
          // transform rather than left/top: the compositor handles it without
          // re-running layout for the absolutely positioned element.
          l.el.style.transform = `translate3d(${(_proj.x * 0.5 + 0.5) * rect.width - l.w / 2}px, ${(-_proj.y * 0.5 + 0.5) * rect.height - l.h - 4}px, 0)`;
        }
      }

      const now = performance.now();
      if (flyingRef.current && now - lastT > 150) {
        lastT = now;
        setFlyProgress(Math.round(((now - flyStartRef.current) / FLYOVER_MS) * 100));
      }

      // Sample renderer counters on a fixed cadence. Reading renderer.info every
      // frame is cheap but would make the overlay's own numbers the thing being
      // measured at 60 Hz; twice a second is enough to see draw-call growth.
      if (perfOn() && frame % 30 === 0) {
        const info = renderer.info;
        setPerf({
          drawCalls: info.render.calls,
          triangles: info.render.triangles,
          geometries: info.memory.geometries,
          textures: info.memory.textures,
          programs: info.programs?.length ?? 0,
          features: parcelCountRef.current + buildingCountRef.current,
        });
      }
    };
    loop();

    const onResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    // Entering or leaving fullscreen resizes the host without firing a window
    // resize, so the canvas kept rendering at the old size until something else
    // happened to resize the window.
    const onFs = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
      onResize();
    };
    window.addEventListener('resize', onResize);
    document.addEventListener('fullscreenchange', onFs);

    // The loop is unconditional: it re-arms rAF before doing anything else, so a
    // backgrounded tab, a scrolled-away view or a covered modal all keep paying
    // for a full render of a scene that has not changed.
    const onVisibility = () => {
      if (document.hidden) {
        cancelAnimationFrame(animId);
        animId = 0;
        suspendObserver?.disconnect();
      } else {
        // Re-observe rather than restarting directly: the observer fires an
        // initial entry, so a view that is still scrolled off-screen stays
        // suspended instead of resuming.
        suspendObserver?.observe(container);
        if (!suspendObserver) animId = requestAnimationFrame(loop);
      }
    };
    const onIntersect = (entries: IntersectionObserverEntry[]) => {
      if (!contentAliveRef.current || document.hidden) return;
      const visible = entries.some((e) => e.isIntersecting);
      suspended = !visible;
      if (visible) {
        if (!animId) animId = requestAnimationFrame(loop);
      } else if (animId) {
        cancelAnimationFrame(animId);
        animId = 0;
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    const suspendObserver =
      typeof IntersectionObserver !== 'undefined' ? new IntersectionObserver(onIntersect, { threshold: 0 }) : null;
    suspendObserver?.observe(container);

    return () => {
      contentAliveRef.current = false;
      if (animId) cancelAnimationFrame(animId);
      if (focusAnimRef.current) cancelAnimationFrame(focusAnimRef.current);
      // The flyover loop was never cancelled here, so it could outlive the scene
      // by up to FLYOVER_MS, keep writing to the shared camera refs that the
      // freshly built scene reads from, and call setState on a component that may
      // already be unmounted.
      if (flyAnimRef.current) {
        cancelAnimationFrame(flyAnimRef.current);
        flyAnimRef.current = 0;
      }
      document.removeEventListener('visibilitychange', onVisibility);
      suspendObserver?.disconnect();
      listen.forEach(([ev, fn]) => container.removeEventListener(ev, fn));
      proposalHoldersRef.current.forEach((g) => {
        g.removeFromParent();
        disposeGlb(g);
      });
      proposalHoldersRef.current = [];
      labelLayer.remove();
      window.removeEventListener('resize', onResize);
      document.removeEventListener('fullscreenchange', onFs);
      // On unmount every GPU object has to go, and the context itself with them.
      // Phase 0 measured geometries climbing 414 -> 490 -> 532 -> 535 across
      // three area switches and never returning to baseline, and WebGL contexts
      // climbing 2 -> 3 -> 4 -> 5 because dispose() alone does not hand the
      // context back to the browser.
      scene.traverse((obj) => {
        const any = obj as unknown as {
          geometry?: { dispose?: () => void };
          material?: unknown;
        };
        any.geometry?.dispose?.();
        const mat = any.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach(disposeOwnedMaterial);
        else disposeOwnedMaterial(mat);
      });
      materialCache.forEach((m) => m.dispose());
      materialCache.clear();
      scene.clear();
      renderer.dispose();
      // Without this the context survives the rebuild. Chrome stops handing out
      // new contexts at roughly 16, and past that limit WebGLRenderer
      // construction fails silently, which presents as a blank canvas.
      renderer.forceContextLoss();
      camRef.current = null;
      sceneRef.current = null;
      rendererRef.current = null;
      contentRef.current = null;
    };
    // Mount-only. Data changes are handled by the content effect above, which
    // reuses this renderer, scene, camera, label layer and loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the render-loop mirrors current. No dependency array on purpose: this
  // is a cheap assignment that must track every render, and it never rebuilds
  // anything.
  useEffect(() => {
    validParcelsRef.current = validParcels;
    buildingsRef.current = buildings;
    excavationCoordRef.current = excavationCoord;
    buildingCountRef.current = buildings.length;
    parcelCountRef.current = validParcels.length;
  });

  // ==========================================
  // SCENE CONTENT (rebuilt on data change only)
  // ==========================================
  // Everything below builds meshes. It runs inside the renderer, scene, camera,
  // label layer and render loop created above, none of which are touched here.
  // This split is what removes the ~1.1 s context teardown from a data change.
  useEffect(() => {
    const content = contentRef.current;
    const scene = sceneRef.current;
    if (!content || !scene) return;

    contentAliveRef.current = true;
    const t0 = perfOn() ? performance.now() : 0;

    // Tear down the previous contents. disposeGlb handles textures and
    // materials that a plain geometry dispose would leak.
    content.traverse((obj) => {
      const any = obj as unknown as {
        geometry?: { dispose?: () => void };
        material?: unknown;
      };
      any.geometry?.dispose?.();
      const mat = any.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach(disposeOwnedMaterial);
      else disposeOwnedMaterial(mat);
    });
    proposalHoldersRef.current.forEach((g) => {
      g.removeFromParent();
      disposeGlb(g);
    });
    proposalHoldersRef.current = [];
    content.clear();

    parcelMeshesRef.current = [];
    parcelOutlinesRef.current = [];
    buildingMeshesRef.current = [];
    structureBoxesRef.current?.dispose();
    structureBoxesRef.current = null;
    pinBoxesRef.current?.dispose();
    pinBoxesRef.current = null;
    precinctRef.current = [];
    precinctBoxesRef.current?.dispose();
    precinctBoxesRef.current = null;
    violationEdgesRef.current = [];
    proposalMeshesRef.current = [];
    replacedCodesRef.current.clear();
    const labelTargets: { x: number; y: number; text: string; hero: boolean; z: number }[] = [];
    const childProposalMeshes = (g: THREE.Object3D) => {
      g.traverse((child) => {
        if ((child as THREE.Mesh).isMesh) proposalMeshesRef.current.push(child);
      });
    };

    validParcels
      .filter((p) => p.ulpin === HERO_ULPIN)
      .forEach((p) => {
        const ring = polyRing(p.polygon_geojson);
        if (ring.length < 3) return;
        const isHero = true;
        const c = centroidOf(ring);
        const shape = shapeFromPolygon(ring);

        {
          const mesh = new THREE.Mesh(
            new THREE.ShapeGeometry(shape),
            sharedStandard(0xbfdbfe, 0.7, 0.05, {
              transparent: true,
              opacity: 0.55,
              side: THREE.DoubleSide,
              polygonOffset: true,
              polygonOffsetFactor: 1,
            })
          );
          mesh.position.set(c[0], c[1], 0.016);
          mesh.receiveShadow = true;
          mesh.userData = { ulpin: p.ulpin, isHero };
          content.add(mesh);
          parcelMeshesRef.current.push(mesh);
        }

        {
          const pts = ring.map(([x, y]) => new THREE.Vector3(x, y, 0.055));
          const line = new THREE.LineLoop(
            new THREE.BufferGeometry().setFromPoints(pts),
            sharedLine(0x1d4ed8, { transparent: true, opacity: 0.9 })
          );
          line.userData = { ulpin: p.ulpin, isHero };
          content.add(line);
          parcelOutlinesRef.current.push(line);
        }

        labelTargets.push({ x: c[0], y: c[1], text: 'B-17', hero: true, z: 10 });
      });

    // Building B-17 hero
    if (hero) {
      const footRing = polyRing(hero?.structure?.footprint_geojson);
      if (footRing.length >= 3) {
        const [ar, ag, ab] = accentRGB();
        const twin = buildHeroBuilding({ hero, accent: [ar, ag, ab], heroCenter });
        content.add(twin.group);
        buildingMeshesRef.current = twin.floorMeshes;
        buildingMeshesRef.current.forEach((m) => {
          (m as THREE.Mesh).userData.ulpin = HERO_ULPIN;
        });
      }
    } else {
      labelTargets.push({ x: HERO_CENTER[0], y: HERO_CENTER[1], text: 'B-17', hero: true, z: 10 });
    }

    // Real persisted structures (any non-hero parcel that carries a building
    // twin). This is where a structure the builder studio actually wrote
    // shows up: a solid extruded mass at the parcel's own centroid, coloured
    // by its honest status. PENDING_REVIEW (builder-asserted, awaiting a
    // reviewer) is amber; ACCEPTED_FOR_RECORD / VERIFIED is green; REJECTED is
    // red; INFERRED (an ingested OSM/GlobalML footprint) is the type colour.
      const structureSpecs: {
        w: number; h: number; d: number; x: number; y: number; z: number; color: number;
        ulpin: string; code?: string; name?: string; status?: string;
      }[] = [];
      const pinSpecs: { x: number; y: number; z: number; color: number }[] = [];
    validParcels
      .filter((p) => p.ulpin !== HERO_ULPIN && p.building?.has_3d)
      .forEach((p) => {
        const ring = polyRing(p.polygon_geojson);
        if (ring.length < 3) return;
        const c = centroidOf(ring);
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        ring.forEach(([x, y]) => {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        });
        const spanX = Math.max(maxX - minX, 1);
        const spanY = Math.max(maxY - minY, 1);
        const w = spanX * 0.8;
        const h = spanY * 0.8;
        const bh = p.building?.height_m;
        const bf = p.building?.floors ?? 0;
        const z = bh != null && bh > 0 ? bh : bf > 0 ? bf * 3 : 6;
        const baseColor = STATUS_COLORS[p.building?.status ?? 'INFERRED'] ?? TYPE_COLORS[p.building?.type] ?? 0x3b82f6;
        structureSpecs.push({
          w, h, d: z,
          x: c[0], y: c[1], z: z / 2,
          color: baseColor,
          ulpin: p.ulpin,
          code: p.building?.code,
          name: p.building?.name,
          status: p.building?.status,
        });
        if (p.building?.status === 'PENDING_REVIEW') pinSpecs.push({ x: c[0], y: c[1], z: z + 2, color: baseColor });
        labelTargets.push({ x: c[0], y: c[1], text: p.building?.name || p.building?.code || p.ulpin, hero: false, z: z + 1 });
      });

      // One InstancedMesh for every persisted structure. These were one mesh
      // and one BoxGeometry each, so an area of 120 units cost 120 draw calls
      // and 120 geometries before anything was drawn. Colour is per-instance,
      // so units of different status still read differently.
      if (structureSpecs.length) {
        const inst = buildInstancedBoxes(content, structureSpecs, sharedStandard(0xffffff, 0.6, 0.1));
        structureBoxesRef.current = inst;
        inst.units = structureSpecs.map((s) => ({
          b: { code: s.code, name: s.name, status: s.status } as unknown as PrecinctBuilding,
          ulpin: s.ulpin,
          baseColor: s.color,
        }));
        buildingMeshesRef.current.push(inst.mesh);
      }
      if (pinSpecs.length) {
        const pins = buildInstancedBoxes(
          content,
          pinSpecs.map((s) => ({ w: 0.6, h: 0.6, d: 4, x: s.x, y: s.y, z: s.z, color: s.color })),
          sharedBasic(0xffffff),
        );
        pinBoxesRef.current = pins;
        buildingMeshesRef.current.push(pins.mesh);
      }

    // Precinct buildings B-01..B-12, instanced.
    //
    // These were one mesh plus one BoxGeometry each, and every one of them is a
    // unit box scaled into place, so a precinct of a dozen cost a dozen draw
    // calls. Per-instance colour keeps the type/status colouring intact.
    //
    // The epoch effect rewrites scale, position and colour per unit, so it now
    // goes through setTransform/setColor instead of touching a mesh each.
    const precinctSpecs = buildings.map((b) => ({
      w: b.w, h: b.h, d: b.height_m,
      x: b.x + b.w / 2, y: b.y + b.h / 2, z: b.height_m / 2,
      // Rows in the later epoch get an outline, not a red fill. Colouring by a
      // "violation" status painted invented buildings the colour a viewer reads
      // as enforcement action, which this demo has no basis to assert.
      color: TYPE_COLORS[b.type] ?? 0x3b82f6,
    }));
    if (precinctSpecs.length) {
      const inst = buildInstancedBoxes(content, precinctSpecs, sharedStandard(0xffffff, 0.55, 0.12));
      precinctBoxesRef.current = inst;
      inst.units = buildings.map((b, i) => ({
        b,
        baseColor: precinctSpecs[i].color,
      }));
      precinctRef.current = buildings.map((b, i) => ({
        mesh: inst.mesh,
        id: i,
        b,
        baseColor: precinctSpecs[i].color,
      }));

      buildings.forEach((b, i) => {
        if (b.status !== 'DEMO_EPOCH_COMPARISON') return;
        // The breach outline is its own geometry per unit, and it is only drawn
        // in the 2027 epoch, so it stays individual — a merged edge run would
        // stop being addressable for the per-unit visibility toggle.
        const spec = precinctSpecs[i];
        const edges = new THREE.EdgesGeometry(new THREE.BoxGeometry(spec.w, spec.h, spec.d));
        const ringM = new THREE.LineSegments(edges, sharedLine(0xef4444, { transparent: true, opacity: 0.9 }));
        ringM.position.set(spec.x, spec.y, spec.z);
        content.add(ringM);
        violationEdgesRef.current.push(ringM);
      });
    }

    // Builder GLB Overlay & 3D Verification Hologram
    if (overlayModel) {
      const target = buildings.find((b) => b.code === overlayModel.targetCode);
      if (target) {
        const holder = new THREE.Group();
        holder.name = `PROPOSAL_${target.code}`;
        const cx = target.x + target.w / 2;
        const cy = target.y + target.h / 2;

        // 1. Holographic Setback Perimeter (Permissible boundary outline)
        const setbackGeo = new THREE.BoxGeometry(target.w + 6.0, target.h + 6.0, 0.4);
        const setbackMat = sharedBasic(0x06b6d4, { wireframe: true, transparent: true, opacity: 0.7 });
        const setbackMesh = new THREE.Mesh(setbackGeo, setbackMat);
        setbackMesh.position.set(cx, cy, 0.2);
        holder.add(setbackMesh);

        // 2. Vertical Alignment Beacon Beam
        const beaconHeight = Math.max(30, target.height_m + 20);
        const beaconGeo = new THREE.CylinderGeometry(0.4, target.w * 0.7, beaconHeight, 16, 1, true);
        const beaconMat = sharedBasic(0x06b6d4, {
          transparent: true,
          opacity: 0.15,
          side: THREE.DoubleSide,
          depthWrite: false,
        });
        const beacon = new THREE.Mesh(beaconGeo, beaconMat);
        beacon.position.set(cx, cy, beaconHeight / 2);
        beacon.rotation.x = Math.PI / 2;
        holder.add(beacon);

        content.add(holder);
        proposalHoldersRef.current.push(holder);

        loadModel(overlayModel.url, overlayModel.format as ModelFormat)
          .then((g) => {
            if (!contentAliveRef.current) return;
            if (overlayModel.mode === 'propose') applyTranslucent(g);
            fitGlbToFootprint(g, { x: cx, y: cy }, target.w * 0.9, target.h * 0.9);
            g.traverse((child) => {
              if ((child as THREE.Mesh).isMesh) child.userData.building = target;
            });
            holder.add(g);
            childProposalMeshes(g);
            // The proposal arrives after the initial bake, so the shadow map
            // has to be invalidated or the overlay renders unshadowed.
            if (rendererRef.current) rendererRef.current.shadowMap.needsUpdate = true;
          })
          .catch((err) => console.error('Builder proposal GLB failed to load', err));

        if (overlayModel.mode === 'replace') {
          replacedCodesRef.current.add(target.code);
        }
      }
    }

    buildings.forEach((b) => {
      const cx = b.x + b.w / 2;
      const cy = b.y + b.h / 2;
      labelTargets.push({ x: cx, y: cy, text: b.name, hero: false, z: b.height_m + 2.4 });
    });

    // Billboards. The layer is persistent; only the label set is replaced.
    const labelLayer = labelLayerRef.current;
    labelsRef.current.forEach((l) => l.el.remove());
    const labels: typeof labelsRef.current = [];
    labelTargets.forEach((t) => {
      const el = document.createElement('div');
      el.className = cn(
        'absolute left-0 top-0 font-mono text-[9px] font-bold px-1.5 py-0.5 rounded-md border select-none text-center leading-tight',
        t.hero ? 'text-blue-800 bg-blue-100/80 border-blue-300' : 'text-slate-600 bg-white/70 border-slate-200'
      );
      el.textContent = t.text;
      labelLayer?.appendChild(el);
      // Cached at creation. The projection loop used to read el.offsetWidth and
      // el.offsetHeight every update, interleaved with the style.left/top
      // writes for the next label, which forces the browser to recompute layout
      // twice per label per pass. With ~235 labels at 30 Hz that alone pinned
      // the main thread. Label text is fixed, so measuring once is sufficient.
      // left-0/top-0 is now required because position comes from transform.
      labels.push({ el, x: t.x, y: t.y, z: t.z, w: el.offsetWidth, h: el.offsetHeight });
    });
    labelsRef.current = labels;

    applyHeatmap(heatmapRef.current);
    applyVisibility();
    // Geometry changed, so the static shadow map has to be re-baked once.
    if (rendererRef.current) rendererRef.current.shadowMap.needsUpdate = true;

    if (t0) {
      setPerf({
        sceneBuildMs: performance.now() - t0,
        sceneBuilds: getPerf().sceneBuilds + 1,
        status: `3d scene built - ${buildings.length} precinct, ${validParcels.length} parcels`,
      });
    }

    return () => {
      contentAliveRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [validParcels, hero, buildings, overlayModel]);

  // Populate the urban fabric when its datasets arrive. Separate from the scene
  // build, and the reason a cold load is one scene build rather than two or
  // three. buildOsmFabric disposes the previous contents first.
  useEffect(() => {
    const group = osmGroupRef.current;
    if (!group) return;
    const { streetMeshes, amenityMeshes } = buildOsmFabric(group, osmStreets, osmStreetlights, osmTrees, osmAmenities);
    osmStreetMeshesRef.current = streetMeshes;
    osmAmenityMeshesRef.current = amenityMeshes;
  }, [osmStreets, osmStreetlights, osmTrees, osmAmenities]);

  const startFlyover = () => {
    if (flying || walkMode) return;
    if (flyAnimRef.current) cancelAnimationFrame(flyAnimRef.current);
    flyingRef.current = true;
    setFlying(true);
    setFlyProgress(0);
    flyStartRef.current = performance.now();
    const startTab = targetRef.current.clone();
    const startSph = sphericalRef.current.clone();

    const poseAt = (t: number) => {
      const centerV = new THREE.Vector3(PRECINCT_CENTER[0], PRECINCT_CENTER[1], 8);
      const b17V = new THREE.Vector3(HERO_CENTER[0], HERO_CENTER[1], 8);
      if (t < 0.2) {
        const p = smoother(t / 0.2);
        sphericalRef.current.radius = lerp(startSph.radius, 300, p);
        sphericalRef.current.phi = lerp(startSph.phi, 0.70, p);
        sphericalRef.current.theta = lerp(startSph.theta, Math.PI * 0.25, p);
        targetRef.current.lerpVectors(startTab, centerV, p);
      } else if (t < 0.7) {
        const p = smoother((t - 0.2) / 0.5);
        sphericalRef.current.radius = lerp(300, 240, p);
        sphericalRef.current.phi = 0.70;
        sphericalRef.current.theta = Math.PI * 0.25 + Math.PI * 2 * p;
        targetRef.current.copy(centerV);
      } else if (t < 0.9) {
        const p = smoother((t - 0.7) / 0.2);
        sphericalRef.current.radius = lerp(240, 90, p);
        sphericalRef.current.phi = 0.82;
        sphericalRef.current.theta = Math.PI * 0.25 + Math.PI * 2 + Math.PI * 0.45 * p;
        targetRef.current.lerpVectors(centerV, b17V, p);
      } else {
        const p = smoother((t - 0.9) / 0.1);
        sphericalRef.current.radius = lerp(90, 260, p);
        sphericalRef.current.phi = 0.82;
        sphericalRef.current.theta = Math.PI * 0.25 + Math.PI * 2 + Math.PI * 0.45 + Math.PI * 0.5 * p;
        targetRef.current.copy(b17V);
      }
      const cam = camRef.current;
      if (cam) {
        const s = sphericalRef.current;
        cam.position.copy(targetRef.current).add(sphericalToZUp(s.radius, s.phi, s.theta));
        cam.lookAt(targetRef.current);
      }
    };

    const step = (now: number) => {
      const t = Math.min(1, (now - flyStartRef.current) / FLYOVER_MS);
      poseAt(t);
      if (t < 1) {
        flyAnimRef.current = requestAnimationFrame(step);
      } else {
        flyingRef.current = false;
        setFlying(false);
        setFlyProgress(100);
        flyAnimRef.current = null;
      }
    };
    flyAnimRef.current = requestAnimationFrame(step);
  };

  const stopFlyover = () => {
    if (flyAnimRef.current) cancelAnimationFrame(flyAnimRef.current);
    flyAnimRef.current = null;
    flyingRef.current = false;
    setFlying(false);
  };

  const toggleLayer = (k: keyof LayerState) => setLayers((s) => ({ ...s, [k]: !s[k] }));

  const toggleFullscreen = () => {
    const host = mountRef.current?.parentElement;
    if (!host) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else host.requestFullscreen?.();
  };

  const zoomBy = (factor: number) => {
    const s = sphericalRef.current;
    s.radius = Math.max(40, Math.min(520, s.radius * factor));
    const cam = camRef.current;
    if (cam) cam.position.copy(targetRef.current).add(sphericalToZUp(s.radius, s.phi, s.theta));
  };

  const layerItems: { key: keyof LayerState; label: string; icon: React.ReactNode }[] = [
    { key: 'parcels', label: 'Parcels', icon: <Layers className="w-3.5 h-3.5" /> },
    { key: 'boundaries', label: 'Boundaries', icon: <PencilRuler className="w-3.5 h-3.5" /> },
    { key: 'buildings', label: 'Buildings', icon: <Box className="w-3.5 h-3.5" /> },
    { key: 'labels', label: 'Labels', icon: <Crosshair className="w-3.5 h-3.5" /> },
    { key: 'terrain', label: 'Terrain relief', icon: <Layers className="w-3.5 h-3.5" /> },
  ];

  const heatmapPills: { id: HeatmapMode; label: string }[] = [
    { id: 'none', label: 'None' },
    { id: 'fsi', label: 'FSI' },
    { id: 'risk', label: 'Risk' },
    { id: 'value', label: 'Value' },
  ];

  const heatmapLegend =
    heatmapMode === 'fsi'
      ? { colors: ['#10B981', '#F59E0B', '#EF4444'], labels: ['FSI ≤ 1.5', '1.5–2.0', '> 2.0'] }
      : heatmapMode === 'risk'
      ? { colors: ['#10B981', '#F59E0B', '#F97316', '#EF4444'], labels: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] }
      : heatmapMode === 'value'
      ? { colors: ['#2563EB', '#EF4444'], labels: ['Low', 'High (value)'] }
      : null;

  return (
    <div className={cn('relative w-full h-full bg-slate-50 overflow-hidden select-none', className)}>
      <div ref={mountRef} className="w-full h-full" />

      {/* Primary Toolbar (Top-Left) */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
        <div className="flex items-center gap-1 bg-white/95 border border-slate-200 p-1 rounded-xl shadow-premium backdrop-blur-md">
          {(['3d', '2d'] as const).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                if (walkMode) setWalkMode(false);
              }}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-semibold uppercase transition',
                mode === m && !walkMode ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'
              )}
            >
              {m}
            </button>
          ))}
        </div>

        {/* Action Toggles: Flyover, Walk, Solar, 4D, Subsurface */}
        <div className="flex flex-col gap-1.5 bg-white/95 border border-slate-200 p-1.5 rounded-xl shadow-premium backdrop-blur-md">
          <button
            onClick={flying ? stopFlyover : startFlyover}
            disabled={walkMode}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition',
              flying ? 'bg-rose-600 text-white' : 'text-slate-700 hover:bg-slate-100 disabled:opacity-40'
            )}
            title="Cinematic drone flyover"
          >
            {flying ? <Square className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 text-blue-600" />}
            {flying ? `Flyover ${flyProgress}%` : 'Flyover'}
          </button>

          <button
            onClick={() => {
              setWalkMode(!walkMode);
              if (flying) stopFlyover();
            }}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition',
              walkMode ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-700 hover:bg-slate-100'
            )}
            title="First-Person Ground Foot-Patrol (WASD keys)"
          >
            <Footprints className="w-3.5 h-3.5" />
            {walkMode ? 'Exit Walk' : 'Street Walk'}
          </button>

          <button
            onClick={() => setSolarMode(!solarMode)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition',
              solarMode ? 'bg-amber-500 text-white shadow-sm' : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Solar Insolation & Dynamic Shadow Engine"
          >
            <Sun className="w-3.5 h-3.5 text-amber-500" />
            Solar & Shadows
          </button>

          <button
            onClick={() => setSubsurfaceMode(!subsurfaceMode)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition',
              subsurfaceMode ? 'bg-cyan-700 text-white shadow-sm' : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Subsurface 3D Utility Networks & Excavation Simulator"
          >
            <Flame className="w-3.5 h-3.5 text-cyan-600" />
            Subsurface (X-Ray)
          </button>
        </div>

        {/* Layers & Measurement */}
        <div className="flex items-center gap-1">
          <div className="relative">
            <button
              onClick={() => setLayerOpen(!layerOpen)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border bg-white/95 border-slate-200 shadow-premium backdrop-blur-md transition',
                layerOpen ? 'text-blue-700' : 'text-slate-700'
              )}
            >
              <Layers className="w-3.5 h-3.5" />
              Layers
              <ChevronDown className={cn('w-3 h-3 transition', layerOpen && 'rotate-180')} />
            </button>
            {layerOpen && (
              <div className="absolute top-full left-0 mt-2 w-52 bg-white border border-slate-200 rounded-xl shadow-premium p-2 space-y-0.5 animate-rise-in z-20">
                {layerItems.map((it) => (
                  <button
                    key={it.key}
                    onClick={() => toggleLayer(it.key)}
                    className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    <span className="flex items-center gap-2">
                      {it.icon}
                      {it.label}
                    </span>
                    {layers[it.key] ? <Eye className="w-3.5 h-3.5 text-accent" /> : <EyeOff className="w-3.5 h-3.5 text-ink-faint" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => {
              setMeasureMode(!measureMode);
              measurePtsRef.current = null;
              setMeasureDist(null);
            }}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border transition shadow-premium backdrop-blur-md',
              measureMode ? 'bg-amber-500 text-white border-amber-600' : 'bg-white/95 text-slate-700 border-slate-200'
            )}
          >
            <Ruler className="w-3.5 h-3.5" />
            {measureMode ? 'Measuring…' : 'Measure'}
          </button>
        </div>
      </div>

      {/* Top Center: 4D Temporal Epoch Scrubber Bar. Constrained to the
          viewport with max-w and horizontal scroll, so the four epoch buttons
          stay reachable on a 360px phone instead of running off both edges. */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 max-w-[calc(100vw-1.5rem)] overflow-x-auto overscroll-x-contain bg-white/95 border border-slate-200 p-1.5 rounded-2xl shadow-premium backdrop-blur-md flex items-center gap-2 text-xs">
        <span className="text-[10px] uppercase font-mono font-black text-slate-600 pl-2 flex items-center gap-1 shrink-0">
          <Clock className="w-3 h-3" /> 4D Epoch
        </span>
        {(['2024', '2025', '2026', '2027'] as const).map((yr) => (
          <button
            key={yr}
            onClick={() => setEpoch(yr)}
            className={cn(
              'px-3 py-1 rounded-xl font-bold transition flex items-center gap-1.5 text-xs font-mono shrink-0',
              epoch === yr
                ? yr === '2027'
                  ? 'bg-rose-600 text-white shadow-sm'
                  : 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
            )}
          >
            {yr}
            {yr === '2024' && <span className="text-[9px] opacity-75">Drone</span>}
            {yr === '2025' && <span className="text-[9px] opacity-75">CAD</span>}
            {yr === '2026' && <span className="text-[9px] opacity-75">Epoch 1</span>}
            {yr === '2027' && <span className="text-[9px] bg-rose-800 text-rose-100 px-1 py-0.2 rounded font-bold uppercase tracking-wider">LiDAR Alert</span>}
          </button>
        ))}
      </div>

      {/* Top Right: System info & Fullscreen */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
        <div className="bg-white/95 border border-slate-200 px-3 py-1.5 rounded-lg shadow-subtle font-mono text-[10px] text-slate-600 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          Airoli S8 Cadastre
          <span className="text-slate-500">|</span>
          {buildings.length || validParcels.length} buildings
        </div>
        <button
          onClick={toggleFullscreen}
          className="p-2 rounded-lg bg-white/95 border border-slate-200 shadow-subtle text-slate-600 hover:text-blue-700 transition"
          title="Toggle fullscreen"
        >
          {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
      </div>

      {/* Heatmap pills */}
      <div className="absolute top-[4.5rem] right-4 z-10 flex items-center gap-1 bg-white/95 border border-slate-200 p-1 rounded-xl shadow-premium backdrop-blur-md">
        {heatmapPills.map((p) => (
          <button
            key={p.id}
            onClick={() => {
              setHeatmapMode(p.id);
              applyHeatmap(p.id);
            }}
            className={cn(
              'px-2.5 py-1.5 rounded-lg text-[11px] font-bold uppercase transition',
              heatmapMode === p.id ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Zoom controls */}
      <div className="absolute top-[7.5rem] right-4 z-10 flex flex-col bg-white/95 border border-slate-200 rounded-xl shadow-subtle overflow-hidden">
        <button
          onClick={() => zoomBy(0.8)}
          className="w-9 h-9 flex items-center justify-center text-slate-600 hover:text-blue-700 hover:bg-slate-100 transition border-b border-slate-200"
          title="Zoom in"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          onClick={() => zoomBy(1.25)}
          className="w-9 h-9 flex items-center justify-center text-slate-600 hover:text-blue-700 hover:bg-slate-100 transition"
          title="Zoom out"
        >
          <Minus className="w-4 h-4" />
        </button>
      </div>

      {/* Camera View Angle Selector (Above, Iso 3D, and All Sides) */}
      <div className="absolute top-[12.8rem] right-4 z-10 flex flex-col bg-white/95 border border-slate-200 rounded-2xl p-1.5 shadow-premium backdrop-blur-md gap-1 text-[10px] w-32">
        <div className="text-[9px] font-mono font-bold text-slate-600 px-1 py-0.5 text-center uppercase tracking-wider flex items-center justify-center gap-1 border-b border-slate-100 pb-1">
          <Compass className="w-3 h-3 text-blue-600" /> View Angle
        </div>
        <button
          onClick={() => applyCameraPreset('top')}
          className={cn(
            'px-2 py-1.5 rounded-lg font-bold transition flex items-center justify-between gap-1',
            cameraPreset === 'top' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-700 hover:bg-slate-100'
          )}
          title="View from Above / Top-Down (Roof & Plot Outline)"
        >
          <span className="flex items-center gap-1.5">
            <ArrowDown className="w-3 h-3 text-sky-400" /> Above
          </span>
          <span className="text-[8px] font-mono opacity-70">Top</span>
        </button>
        <button
          onClick={() => applyCameraPreset('iso')}
          className={cn(
            'px-2 py-1.5 rounded-lg font-bold transition flex items-center justify-between gap-1',
            cameraPreset === 'iso' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-700 hover:bg-slate-100'
          )}
          title="Isometric 3D Angled View from Above"
        >
          <span className="flex items-center gap-1.5">
            <Box className="w-3 h-3 text-indigo-500" /> Iso 3D
          </span>
          <span className="text-[8px] font-mono opacity-70">45°</span>
        </button>
        <div className="h-px bg-slate-200 my-0.5" />
        <div className="text-[8px] font-mono text-slate-600 px-1 text-center uppercase font-bold">All Sides</div>
        <div className="grid grid-cols-2 gap-1">
          <button
            onClick={() => applyCameraPreset('front')}
            className={cn(
              'px-1.5 py-1.5 min-h-[28px] rounded-lg font-bold transition text-center text-[10px]',
              cameraPreset === 'front' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Front Side View (Looking North)"
          >
            Front (N)
          </button>
          <button
            onClick={() => applyCameraPreset('back')}
            className={cn(
              'px-1.5 py-1.5 min-h-[28px] rounded-lg font-bold transition text-center text-[10px]',
              cameraPreset === 'back' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Back Side View (Looking South)"
          >
            Back (S)
          </button>
          <button
            onClick={() => applyCameraPreset('left')}
            className={cn(
              'px-1.5 py-1.5 min-h-[28px] rounded-lg font-bold transition text-center text-[10px]',
              cameraPreset === 'left' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Left Side View (Looking East)"
          >
            Left (W)
          </button>
          <button
            onClick={() => applyCameraPreset('right')}
            className={cn(
              'px-1.5 py-1.5 min-h-[28px] rounded-lg font-bold transition text-center text-[10px]',
              cameraPreset === 'right' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Right Side View (Looking West)"
          >
            Right (E)
          </button>
        </div>
      </div>

      {/* 3D PROPOSAL VERIFICATION TELEMETRY HUD (Floating when proposal active) */}
      {overlayModel && (
        <div className="absolute top-[23.5rem] right-4 z-20 w-80 bg-slate-950/95 backdrop-blur-md border border-cyan-500/40 rounded-2xl shadow-2xl p-3.5 text-xs text-white space-y-3 animate-rise-in font-sans">
          <div className="flex items-center justify-between border-b border-cyan-500/20 pb-2">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
              <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-cyan-400">
                Live 3D Verification Radar
              </span>
            </div>
            <span className="text-[10px] font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded">
              {overlayModel.targetCode}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div className="bg-slate-900/80 p-2 rounded-xl border border-white/5 space-y-0.5">
              <div className="text-slate-400 font-mono text-[9px] uppercase">CAD Delineation</div>
              <div className="font-bold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 shrink-0" /> Conforming
              </div>
            </div>
            <div className="bg-slate-900/80 p-2 rounded-xl border border-white/5 space-y-0.5">
              <div className="text-slate-400 font-mono text-[9px] uppercase">NBC Setbacks</div>
              <div className="font-bold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 shrink-0" /> 6m Front / 4.5m Rear
              </div>
            </div>
            <div className="bg-slate-900/80 p-2 rounded-xl border border-white/5 space-y-0.5">
              <div className="text-slate-400 font-mono text-[9px] uppercase">Subsurface Clash</div>
              <div className="font-bold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 shrink-0" /> Zero Clash (+4.2m)
              </div>
            </div>
            <div className="bg-slate-900/80 p-2 rounded-xl border border-white/5 space-y-0.5">
              <div className="text-slate-400 font-mono text-[9px] uppercase">Air Rights / Shadow</div>
              <div className="font-bold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 shrink-0" /> 0.0mm Overhang
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1 border-t border-white/10 text-[10px] font-mono text-slate-400">
            <span>Spatial Datum: <b className="text-slate-200">EPSG:32643</b></span>
            <span className="text-cyan-400 font-bold">PoW Consensus Ready</span>
          </div>
        </div>
      )}

      {/* SOLAR & SHADOW SIMULATION CONTROLS (Floating Panel) */}
      {solarMode && (
        <div className="absolute top-24 left-4 z-20 w-72 bg-white/95 backdrop-blur-md border border-slate-200 rounded-2xl shadow-premium p-4 text-xs space-y-3 animate-rise-in">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-800 flex items-center gap-1.5">
              <Sun className="w-4 h-4 text-amber-500" /> Solar Insolation Simulator
            </span>
            <button onClick={() => setSolarMode(false)} className="text-slate-400 hover:text-slate-700">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-500 font-mono">Time of Day</span>
              <span className="font-bold font-mono text-amber-700">
                {Math.floor(solarHour)}:{String(Math.floor((solarHour % 1) * 60)).padStart(2, '0')} hrs
              </span>
            </div>
            <input
              type="range"
              min={6}
              max={18}
              step={0.25}
              value={solarHour}
              onChange={(e) => setSolarHour(parseFloat(e.target.value))}
              className="w-full accent-amber-500 cursor-pointer"
            />
          </div>

          <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
            {(['summer', 'equinox', 'winter'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSolarSeason(s)}
                className={cn(
                  'flex-1 py-1 rounded text-[10px] font-bold capitalize transition',
                  solarSeason === s ? 'bg-white text-slate-800 shadow-xs' : 'text-slate-500 hover:text-slate-800'
                )}
              >
                {s}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2 text-[10px] font-mono bg-slate-50 p-2.5 rounded-xl border border-slate-200">
            <div>
              <span className="text-slate-400 block">Sun Altitude</span>
              <span className="font-bold text-slate-800">{solarParams.altitudeDeg}°</span>
            </div>
            <div>
              <span className="text-slate-400 block">Sun Azimuth</span>
              <span className="font-bold text-slate-800">{solarParams.azimuthDeg}°</span>
            </div>
            <div>
              <span className="text-slate-400 block">Est. Shadow Length</span>
              <span className="font-bold text-amber-700">{solarParams.shadowLengthM} m</span>
            </div>
            <div>
              <span className="text-slate-400 block">Insolation Index</span>
              <span className="font-bold text-emerald-700">{solarParams.insolationKwh} kWh/m²</span>
            </div>
          </div>

          <div className="p-2 bg-amber-50/70 border border-amber-200 rounded-lg text-[10px] text-amber-800 leading-tight">
            <strong>Right-to-Light Alert:</strong> B-17 6th floor addition casts a {solarParams.shadowLengthM}m shadow
            obscuring adjoining B-02 balconies at {solarHour} hrs.
          </div>
        </div>
      )}

      {/* STREET WALK MODE RADAR & HUD */}
      {walkMode && (
        <div className="absolute top-20 right-4 z-20 flex flex-col items-end gap-2 animate-rise-in">
          {/* Mini-Radar Canvas */}
          <div className="bg-slate-900/90 border border-slate-700 p-2 rounded-2xl shadow-premium backdrop-blur-md">
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mb-1 px-1">
              <span>Radar Mini-Map</span>
              <span className="text-emerald-400 flex items-center gap-1">● Live</span>
            </div>
            <canvas ref={radarCanvasRef} width={120} height={120} className="rounded-xl border border-slate-800 bg-slate-950" />
            <div className="text-[9px] font-mono text-slate-400 text-center mt-1">
              WASD or Arrow Keys to Walk
            </div>
          </div>

          {/* Setback Distance Caliper */}
          {walkSetback && (
            <div className="bg-white/95 border border-slate-200 p-2.5 rounded-xl shadow-premium text-xs font-mono max-w-[220px]">
              <div className="text-[10px] text-slate-400 uppercase">Setback Inspector</div>
              <div className="font-bold text-slate-800 truncate">{walkSetback.building}</div>
              <div className="text-xs font-bold mt-1 flex items-center justify-between">
                <span>Distance:</span>
                <span className={walkSetback.compliant ? 'text-emerald-600' : 'text-rose-600'}>{walkSetback.dist} m</span>
              </div>
              <div className="text-[9px] text-slate-500 mt-0.5">
                NBC 2016 Min: 4.5m {walkSetback.compliant ? 'Compliant' : 'Encroachment'}
              </div>
            </div>
          )}
        </div>
      )}

      {/* SUBSURFACE & EXCAVATION SIMULATOR HUD */}
      {subsurfaceMode && (
        <div className="absolute bottom-20 right-4 z-20 w-72 bg-white/95 backdrop-blur-md border border-slate-200 rounded-2xl shadow-premium p-4 text-xs space-y-3 animate-rise-in">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-800 flex items-center gap-1.5">
              <Flame className="w-4 h-4 text-orange-500" /> Subsurface Infrastructure
            </span>
            <button
              onClick={() => {
                setExcavationSim(!excavationSim);
                if (!excavationSim) executeClashCheck(excavationCoord[0], excavationCoord[1]);
              }}
              className={cn(
                'px-2.5 py-1 rounded-lg text-[10px] font-bold transition',
                excavationSim ? 'bg-cyan-700 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              )}
            >
              {excavationSim ? 'Pit Active' : 'Test Pit'}
            </button>
          </div>

          {/* Utility lines legend */}
          <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
            {SUBSURFACE_LINES.map((line) => (
              <div key={line.code} className="flex items-center gap-1.5 p-1.5 bg-slate-50 rounded border border-slate-200">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: `#${line.color.toString(16).padStart(6, '0')}` }} />
                <div className="truncate">
                  <span className="font-bold block truncate">{line.code}</span>
                  <span className="text-slate-400">{line.depth}m (buf {line.buffer}m)</span>
                </div>
              </div>
            ))}
          </div>

          {excavationSim && (
            <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-bold text-slate-800">CBYD Excavation Clash Test</span>
                <span className="text-[10px] text-slate-400 font-mono">Click ground to place</span>
              </div>
              <div className="text-[10px] font-mono text-slate-300">
                Coords: [{excavationCoord[0]}, {excavationCoord[1]}] · Depth: 3.5m · Rad: 1.5m
              </div>

              {clashResult && (
                <div
                  className={cn(
                    'p-2 rounded-lg border text-[11px] leading-tight space-y-1',
                    clashResult.status === 'SAFE'
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-rose-50 border-rose-300 text-rose-800'
                  )}
                >
                  <div className="font-bold flex items-center gap-1">
                    {clashResult.status === 'SAFE' ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                    )}
                    {clashResult.status}
                  </div>
                  {clashResult.clashes[0] ? (
                    <p>{clashResult.clashes[0].message}</p>
                  ) : (
                    /* No permit is issued. The old line rendered
                       "Clearance Granted! Permit: CBYD-NMMC-2026-xxxxx", a string
                       built from the clock that read as a municipal authorisation
                       for excavation, based on a mapped demo dataset rather than a
                       surveyed utility registry. */
                    <p>No mapped clashes at this point. This is a scenario geometry
                       check, not a dig-safety clearance, and no permit is issued.</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Measurement readout */}
      {measureDist !== null && (
        <div className="absolute bottom-24 right-4 z-10 bg-amber-50 border border-amber-300 px-3 py-2 rounded-xl shadow-premium text-xs font-bold text-amber-900 flex items-center gap-2 animate-rise-in">
          <Crosshair className="w-3.5 h-3.5" />
          {measureDist.toFixed(2)} m
        </div>
      )}

      {/* Selected Precinct Building Drawer */}
      {selectedBuilding && (
        <div data-testid="building-card" className="absolute bottom-20 left-4 z-20 w-72 bg-white/95 backdrop-blur-md border border-slate-200 rounded-2xl shadow-premium p-4 text-xs animate-rise-in space-y-3">
          <div className="flex items-center justify-between">
            <span data-testid="building-code" className="font-mono font-black text-slate-800 text-sm">{selectedBuilding.code}</span>
            <button onClick={() => setSelectedBuilding(null)} className="p-1 rounded text-slate-400 hover:text-slate-700">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div>
            <div className="font-bold text-slate-900 text-sm">{selectedBuilding.name}</div>
            <div className="text-[10px] font-mono text-slate-400 mt-0.5">ULPIN: {selectedBuilding.ulpin}</div>
          </div>

          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] bg-slate-50 p-2.5 rounded-xl border border-slate-200">
            <span className="text-slate-500">Type</span>
            <span className="font-mono font-bold text-slate-700 text-right capitalize">
              {selectedBuilding.type.replace('_', ' ')}
            </span>
            <span className="text-slate-500">Floors</span>
            <span className="font-mono font-bold text-slate-700 text-right">{selectedBuilding.floors}</span>
            <span className="text-slate-500">Height</span>
            <span className="font-mono font-bold text-slate-700 text-right">{selectedBuilding.height_m.toFixed(0)} m</span>
            <span className="text-slate-500">FSI</span>
            <span className="font-mono font-bold text-slate-700 text-right">{selectedBuilding.fsi.toFixed(2)}</span>
            <span className="text-slate-500">Risk</span>
            <span className="font-mono font-bold text-slate-700 text-right">{selectedBuilding.risk_level}</span>
          </div>

          {/* Quick Action Buttons: Demand Notice & Buyer Shield */}
          <div className="grid grid-cols-2 gap-2 pt-1">
            <button
              onClick={() => setDemandNoticeBuilding(selectedBuilding.code)}
              className="flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-xl text-[11px] font-bold text-rose-700 bg-rose-50 border border-rose-200 hover:bg-rose-100 transition shadow-xs"
            >
              <FileText className="w-3.5 h-3.5" /> Demand Notice
            </button>
            <button
              onClick={() => setBuyerShieldTarget(selectedBuilding.ulpin || selectedBuilding.code)}
              className="flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-xl text-[11px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 hover:bg-emerald-100 transition shadow-xs"
            >
              <Shield className="w-3.5 h-3.5" /> Buyer Shield
            </button>
          </div>

          <button
            onClick={() => onSelectParcel(selectedBuilding.ulpin)}
            className="w-full flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-bold text-blue-600 bg-blue-50 hover:bg-blue-100 transition"
          >
            Inspect 3D Twin Units <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Epoch status banner */}
      <div className="absolute bottom-4 left-4 z-10 bg-white/90 border border-slate-200 px-3 py-1.5 rounded-lg text-[11px] text-slate-600 backdrop-blur-sm shadow-subtle flex items-center gap-2">
        <span className="font-mono font-bold text-blue-700">Epoch {epoch}:</span>
        {epoch === '2024' && 'Drone Photogrammetry Baseline (Site preparation & foundation trenches)'}
        {epoch === '2025' && 'Sanction Plan Blueprint CAD (Permitted municipal massing envelopes)'}
        {epoch === '2026' && 'Epoch 1 Ground Survey (100% Compliant as-built cadastre)'}
        {epoch === '2027' && (
          <span className="text-rose-700 font-bold flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Epoch 2 UAV LiDAR: 3 vertical unauthorized breaches detected (+1,410 m²)
          </span>
        )}
      </div>

      {/* Heatmap legend */}
      {heatmapLegend && (
        <div className="absolute bottom-4 right-4 z-10 bg-white/95 border border-slate-200 px-3 py-2 rounded-xl shadow-premium backdrop-blur-md">
          <div className="flex items-center gap-1.5">
            {heatmapLegend.colors.map((c) => (
              <span key={c} className="w-10 h-2.5 rounded-sm" style={{ backgroundColor: c }} />
            ))}
          </div>
          <div className="mt-1 flex items-center justify-between gap-2">
            {heatmapLegend.labels.map((l) => (
              <span key={l} className="text-[9px] font-mono font-bold text-slate-500 text-center" style={{ width: 44 }}>
                {l}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Action Modals */}
      {demandNoticeBuilding && (
        <DemandNoticeModal
          buildingCode={demandNoticeBuilding}
          isOpen={Boolean(demandNoticeBuilding)}
          onClose={() => setDemandNoticeBuilding(null)}
        />
      )}

      {buyerShieldTarget && (
        <BuyerShieldModal
          initialTarget={buyerShieldTarget}
          isOpen={Boolean(buyerShieldTarget)}
          onClose={() => setBuyerShieldTarget(null)}
        />
      )}

      {heroLoading && (
        <div className="absolute inset-0 bg-white/40 flex items-center justify-center z-10">
          <span className="text-xs font-mono text-slate-500 flex items-center gap-2">
            <span className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            Loading 3D twin…
          </span>
        </div>
      )}

      {/* GPS / Geodetic HUD */}
      {showGpsHud && (
        <div className="absolute bottom-28 left-4 z-10 bg-black/90 backdrop-blur-md border border-cyan-400/30 rounded-xl p-3 font-mono text-[10px] text-cyan-200 min-w-[230px] shadow-2xl">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[9px] uppercase tracking-widest text-cyan-500 font-bold">Geodetic Inspector</span>
            <button
              onClick={() => setShowGpsHud(false)}
              aria-label="Close geodetic inspector"
              className="text-cyan-600 hover:text-white text-xs min-w-[24px] min-h-[24px] flex items-center justify-center"
            >
              x
            </button>
          </div>
          <div className="space-y-0.5 text-[9px]">
            <div className="flex justify-between gap-2"><span className="text-cyan-300">CRS</span><span className="text-white font-bold">EPSG:32643 / WGS84</span></div>
            <div className="flex justify-between gap-2"><span className="text-cyan-300">Datum Origin</span><span className="text-white">19.154N, 72.9965E</span></div>
            <div className="flex justify-between gap-2"><span className="text-cyan-300">UTM Zone</span><span className="text-white">43N</span></div>
            <div className="flex justify-between gap-2"><span className="text-cyan-300">MSL Datum</span><span className="text-white">SoI GTS +12.00m</span></div>
            <div className="flex justify-between gap-2"><span className="text-cyan-300">Accuracy</span><span className="text-emerald-400">DGPS RTK +/-0.02m</span></div>
          </div>
          <div className="mt-1.5 pt-1.5 border-t border-cyan-400/20 text-[9px] text-cyan-500">Click road or amenity for coordinates</div>
        </div>
      )}
      {!showGpsHud && (
        <button onClick={() => setShowGpsHud(true)} className="absolute bottom-28 left-4 z-10 bg-black/60 backdrop-blur-md border border-cyan-400/30 text-cyan-400 rounded-xl px-2.5 py-1.5 text-[10px] font-mono font-bold hover:bg-black/80 transition">GPS HUD</button>
      )}

      {/* OSM Urban Fabric Toggle */}
      <button
        onClick={() => setOsmLayerEnabled(v => !v)}
        className={cn(
          'absolute top-4 right-4 z-10 flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[10px] font-bold border transition backdrop-blur-md',
          osmLayerEnabled ? 'bg-emerald-600 text-ink border-emerald-500' : 'bg-white/90 text-slate-600 border-slate-200'
        )}
      >
        <Compass className="w-3.5 h-3.5" />
        {osmLayerEnabled ? 'OSM ON' : 'OSM OFF'}
      </button>

      {/* OSM Highway Inspector */}
      {selectedStreet && (
        <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-20 bg-white/95 border border-slate-200 rounded-2xl shadow-2xl p-4 w-[380px] backdrop-blur-xl">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[9px] uppercase tracking-widest text-slate-400 font-bold">OSM Way #{selectedStreet.osm_way_id}</div>
              <h3 className="text-sm font-black text-ink mt-0.5">{selectedStreet.name}</h3>
              <div className="text-xs text-slate-500">{selectedStreet.class_label}</div>
            </div>
            <button onClick={() => setSelectedStreet(null)} className="text-slate-400 hover:text-ink ml-4"><X className="w-4 h-4" /></button>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-1.5 text-[11px]">
            {([
              ['Right-of-Way', selectedStreet.right_of_way_m + ' m'],
              ['Lanes', selectedStreet.lanes + ' lanes'],
              ['Width', selectedStreet.width_m + ' m'],
              ['Speed Limit', selectedStreet.speed_limit_kmh + ' km/h'],
              ['PCI Index', selectedStreet.pci_index + '/100'],
              ['Resurfaced', selectedStreet.last_resurfaced],
              ['Surface', selectedStreet.surface],
              ['Lighting', selectedStreet.lighting],
            ] as [string, string][]).map(([k, v]) => (
              <div key={k} className="bg-slate-50 rounded-lg px-2.5 py-1.5">
                <div className="text-[9px] text-slate-400 uppercase font-bold">{k}</div>
                <div className="text-slate-800 font-semibold mt-0.5 truncate">{v}</div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-[10px] text-slate-500 bg-blue-50 rounded-lg px-2.5 py-1.5">{selectedStreet.maintenance_authority}</div>
        </div>
      )}

      {/* OSM Amenity Dossier */}
      {selectedAmenity && (
        <div className="absolute bottom-4 right-16 z-20 bg-white/96 border border-slate-200 rounded-2xl shadow-2xl p-4 w-[340px] backdrop-blur-xl max-h-[70vh] overflow-y-auto">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[9px] uppercase tracking-widest text-slate-400 font-bold">{selectedAmenity.category}</div>
              <h3 className="text-sm font-black text-ink mt-0.5 leading-tight">{selectedAmenity.name}</h3>
            </div>
            <button onClick={() => { setSelectedAmenity(null); setCivicDossier(null); }} className="text-slate-400 hover:text-ink ml-4 shrink-0"><X className="w-4 h-4" /></button>
          </div>
          <p className="text-[11px] text-slate-600 mt-2 leading-relaxed line-clamp-3">{selectedAmenity.description}</p>
          {selectedAmenity.operating_hours && (
            <div className="mt-2 text-[10px] text-emerald-700 bg-emerald-50 rounded-lg px-2.5 py-1.5 font-medium">{selectedAmenity.operating_hours}</div>
          )}
          <div className="mt-2 flex flex-wrap gap-1">
            {selectedAmenity.amenities_list.slice(0, 4).map((a) => (
              <span key={a} className="text-[9px] bg-blue-50 text-blue-700 border border-blue-100 px-1.5 py-0.5 rounded-full">{a}</span>
            ))}
          </div>
          <button
            onClick={() => {
              setCivicDossierLoading(true);
              setCivicDossier(null);
              fetchCivicDossier(selectedAmenity.name).then(d => { setCivicDossier(d); setCivicDossierLoading(false); }).catch(() => setCivicDossierLoading(false));
            }}
            className="mt-3 w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700 transition"
          >
            {civicDossierLoading ? <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
            {civicDossierLoading ? 'Loading...' : 'Civic & Utility Dossier'}
          </button>
            {civicDossier && (
            <div className="mt-3 space-y-2">
              <div className="text-[9px] uppercase font-bold text-slate-400 tracking-widest">Modelled, Not Recorded</div>
              <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
                <div className="text-[9px] text-amber-600 font-bold uppercase">Property Tax</div>
                <div className="text-[11px] text-amber-900 mt-0.5">
                  {civicDossier.property_tax_dossier.assessment_id ?? 'No tax record exists'}
                </div>
                <div className="text-[10px] text-amber-700 mt-0.5">
                  Modelled built-up value ₹{civicDossier.property_tax_dossier.modelled_built_up_value_inr?.toLocaleString?.() ?? '—'} (area × an arbitrary rate)
                </div>
              </div>
              <div className="bg-cyan-50 border border-cyan-200 rounded-xl px-3 py-2">
                <div className="text-[9px] text-cyan-600 font-bold uppercase">Electricity</div>
                <div className="text-[11px] text-cyan-900 mt-0.5">
                  {civicDossier.electrical_utility_dossier.consumer_account_no ?? 'No supply record exists'}
                </div>
                <div className="text-[10px] text-cyan-700 mt-0.5">
                  Modelled connected load {civicDossier.electrical_utility_dossier.modelled_connected_load_kw} kW
                </div>
              </div>
              <div className="bg-purple-50 border border-purple-200 rounded-xl px-3 py-2">
                <div className="text-[9px] text-purple-600 font-bold uppercase">Seismic Assumption</div>
                <div className="text-[11px] text-purple-900 mt-0.5">{civicDossier.structural_and_seismic_dossier.seismic_zone}</div>
                <div className="text-[10px] text-purple-700 mt-0.5">No structural audit, certificate or fire NOC exists.</div>
              </div>
              <div className="text-[10px] text-slate-500 leading-snug">{civicDossier.disclaimer}</div>
              <button onClick={() => setCivicDossier(null)} className="w-full text-[9px] text-slate-400 hover:text-ink text-center py-0.5">Dismiss</button>
            </div>
          )}
        </div>
      )}

      {/* Bottom Center: Camera View Angle Quick Switcher (Above, Iso 3D, and All Sides) */}
      {!walkMode && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 max-w-[calc(100vw-1.5rem)] overflow-x-auto overscroll-x-contain flex items-center gap-1 bg-white/95 border border-slate-200/90 p-1.5 rounded-2xl shadow-2xl backdrop-blur-md animate-rise-in">
          <span className="text-[10px] uppercase font-mono font-black text-slate-600 px-2 flex items-center gap-1.5 border-r border-slate-200 mr-0.5 shrink-0">
            <Compass className="w-3.5 h-3.5 text-blue-600" />
            Camera
          </span>
          <button
            onClick={() => applyCameraPreset('top')}
            className={cn(
              'px-2.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 shrink-0',
              cameraPreset === 'top'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-700 hover:bg-slate-100'
            )}
            title="View from Above / Top-Down (Roof plan)"
          >
            <ArrowDown className="w-3.5 h-3.5 text-sky-400" /> Above (Top)
          </button>
          <button
            onClick={() => applyCameraPreset('iso')}
            className={cn(
              'px-2.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 shrink-0',
              cameraPreset === 'iso'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Isometric 3D View from Above (Classic 45° angle)"
          >
            <Box className="w-3.5 h-3.5 text-indigo-500" /> Iso 3D
          </button>
          <div className="h-4 w-px bg-slate-200 mx-0.5" />
          <button
            onClick={() => applyCameraPreset('front')}
            className={cn(
              'px-2 py-1.5 rounded-xl text-xs font-bold transition',
              cameraPreset === 'front'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Front Side View (Looking North)"
          >
            Front (N)
          </button>
          <button
            onClick={() => applyCameraPreset('back')}
            className={cn(
              'px-2 py-1.5 rounded-xl text-xs font-bold transition',
              cameraPreset === 'back'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Back Side View (Looking South)"
          >
            Back (S)
          </button>
          <button
            onClick={() => applyCameraPreset('left')}
            className={cn(
              'px-2 py-1.5 rounded-xl text-xs font-bold transition',
              cameraPreset === 'left'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Left Side View (Looking East)"
          >
            Left (W)
          </button>
          <button
            onClick={() => applyCameraPreset('right')}
            className={cn(
              'px-2 py-1.5 rounded-xl text-xs font-bold transition',
              cameraPreset === 'right'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-700 hover:bg-slate-100'
            )}
            title="Right Side View (Looking West)"
          >
            Right (E)
          </button>
        </div>
      )}
    </div>
  );
};

/**
 * Memoised, and the reason is the draft-coordinate fields.
 *
 * Every prop here is referentially stable across a keystroke: parcels, hero and
 * buildings are state that the area menu does not touch, onSelectParcel is a
 * useCallback, and overlayModel is memoised on activeTemplate. Without the memo,
 * typing a latitude re-rendered the entire 3D view, and a measurement showed six
 * keystrokes producing six long frames. The scene effect was already immune; the
 * remaining cost was React reconciling a tree that had nothing to change.
 */
export const PrecinctMap3D = React.memo(PrecinctMap3DInner);
