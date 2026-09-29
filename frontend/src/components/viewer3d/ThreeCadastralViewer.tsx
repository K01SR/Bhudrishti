import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as THREE from 'three';
import {
  HeroProperty,
  CadastralUnit,
  Scene3D,
  SceneArchitecture,
  SceneUnit,
  SceneSubsurface,
  SceneClash,
  SceneElevated,
} from '../../types/cadastre';
import { accentRGB, outerRing, centroid, ringBounds } from '../../lib/cadastre3d';
import { loadGlb, fitGlbToFootprint, applyTranslucent, applySolid, disposeGlb } from '../../lib/gltf';
import {
  Layers,
  Eye,
  Sun,
  Camera,
  Ruler,
  AlertTriangle,
  Shield,
  Box,
  Building2,
  Palette,
  Sliders,
  Moon,
  Plus,
  Minus,
} from 'lucide-react';

interface Props {
  property: HeroProperty;
  selectedUnit: CadastralUnit | null;
  onSelectUnit: (unit: CadastralUnit | null) => void;
  activeColorMode: string;
  undergroundMode: boolean;
  onToggleUnderground: () => void;
  isEpoch2: boolean;
  highlightedIds?: string[];
  compact?: boolean;
  modelUrl?: string | null;
  modelDisplayMode?: 'strata' | 'architectural' | 'hybrid';
}

/** Fully-normalized, data-driven scene model built from `property.scene3d`
 *  (preferred) with a legacy fallback for older payloads that lack it. */
interface SceneModel {
  scene: Scene3D | null;
  center: { x: number; y: number };
  targetZ: number;
  ground: { cx: number; cy: number; sizeX: number; sizeY: number };
  parcelRing: number[][];
  neighborRings: number[][][];
  footprintRing: number[][];
  floorList: number[];
  levels: Array<{ level_code: string | null; floor_number: number | null; min_z: number; max_z: number }>;
  units: SceneUnit[];
  arch: SceneArchitecture | null;
  subs: SceneSubsurface[];
  clash: SceneClash | null;
  elevated: SceneElevated[];
  engineLabel: string;
}

function floorIndexOf(code: string | undefined): number {
  if (!code) return 0;
  const c = String(code).toUpperCase();
  if (c === 'B1') return -1;
  if (c === 'G') return 0;
  const m = c.match(/L?0?(\d+)/);
  if (m) return parseInt(m[1], 10);
  return 0;
}

function colorHexToNumber(hex: string | undefined): number {
  if (!hex || !hex.startsWith('#')) return 0x3b82f6;
  return parseInt(hex.slice(1), 16);
}

const rightsHex = (fill: number) => `#${fill.toString(16).padStart(6, '0').toUpperCase()}`;

/**
 * The cadastral unit fill palette, in one place.
 *
 * `getUnitColor` paints from these and the colour key renders from the same
 * numbers, so a swatch can never end up describing a colour the scene is not
 * using.
 *
 * Nothing here is authoritative. The first three restate what a unit's rights
 * array in the modelled record claims; the fourth is the absence of any such
 * claim, which is an unknown state and not a clean one. An earlier build left
 * these four fills unlabelled, and an unlabelled green reads as "no problem
 * found" - so the key says so explicitly rather than naming it "clear".
 */
const RIGHTS_FILL = {
  mortgage: 0xef4444,
  easement: 0x8fa8d8,
  parking: 0x5b6472,
  unencumbered: 0x10b981,
} as const;

const RIGHTS_FILL_LEGEND: ReadonlyArray<{
  id: keyof typeof RIGHTS_FILL;
  hex: string;
  label: string;
  note: string;
}> = [
  {
    id: 'mortgage',
    hex: rightsHex(RIGHTS_FILL.mortgage),
    label: 'Mortgage / lien asserted',
    note: 'Modelled encumbrance from the record. Not a registered lien.',
  },
  {
    id: 'easement',
    hex: rightsHex(RIGHTS_FILL.easement),
    label: 'Easement asserted',
    note: 'Modelled right of way / egress. Not a registered easement.',
  },
  {
    id: 'parking',
    hex: rightsHex(RIGHTS_FILL.parking),
    label: 'Parking / common area',
    note: 'Space type taken from the model. States nothing about rights.',
  },
  {
    id: 'unencumbered',
    hex: rightsHex(RIGHTS_FILL.unencumbered),
    label: 'No encumbrance in the record',
    note: 'Unknown, not cleared. An absent modelled entry is not title evidence.',
  },
];

function buildSceneModel(p: HeroProperty): SceneModel {
  const scene = p.scene3d && p.scene3d.success ? p.scene3d : null;
  if (scene) {
    const allRings = [
      scene.parcel.ring,
      ...scene.neighbors.map((n) => n.ring),
      scene.structure.footprint_ring,
    ];
    const allPts = allRings.flat();
    const allXs = allPts.map((p) => p[0]);
    const allYs = allPts.map((p) => p[1]);
    const [minX, maxX, minY, maxY] = [Math.min(...allXs), Math.max(...allXs), Math.min(...allYs), Math.max(...allYs)];
    const [cx, cy] = scene.meta.center;
    const pad = 14;
    return {
      scene,
      center: { x: cx, y: cy },
      targetZ: Math.min(12, Math.max(3, scene.meta.roof_z / 2)),
      ground: {
        cx: (minX + maxX) / 2,
        cy: (minY + maxY) / 2,
        sizeX: Math.max(60, maxX - minX + pad * 2),
        sizeY: Math.max(50, maxY - minY + pad * 2),
      },
      parcelRing: scene.parcel.ring,
      neighborRings: scene.neighbors.map((n) => n.ring),
      footprintRing: scene.structure.footprint_ring,
      floorList: Array.from(new Set(scene.levels.map((lv) => lv.floor_number))).sort((a, b) => a - b),
      levels: scene.levels,
      units: scene.units,
      arch: scene.architecture,
      subs: scene.subsurface_objects,
      clash: scene.clash,
      elevated: scene.elevated_objects,
      engineLabel: scene.meta.engine,
    };
  }

  // ---- Legacy / National Twin fallback (payloads without pre-rendered scene3d) -------------
  const rawRing = outerRing(p.parcel?.polygon_geojson);
  const rawFr = outerRing(p.structure?.footprint_geojson);
  const legacyPts = [rawRing, rawFr].filter((r) => r.length).flat();
  const lXs = legacyPts.map((pt) => pt[0]);
  const lYs = legacyPts.map((pt) => pt[1]);

  const isDegree = legacyPts.length > 0 && Math.abs(lXs[0]) <= 180 && Math.abs(lYs[0]) <= 90;
  let parcelRing: number[][] = [];
  let footprintRing: number[][] = [];
  let cx = 0;
  let cy = 0;

  if (isDegree) {
    const [lon0, lat0] = centroid(legacyPts);
    const cosLat = Math.cos((lat0 * Math.PI) / 180);
    const toMeters = (pt: number[]): [number, number] => [
      (pt[0] - lon0) * 111320 * cosLat,
      (pt[1] - lat0) * 110574,
    ];
    let pMeters = rawRing.map(toMeters);
    let fMeters = rawFr.map(toMeters);

    const pArea = p.parcel?.calculated_area_m2 || p.parcel?.document_area_m2 || 1200;
    const pDim = Math.max(26, Math.min(65, Math.sqrt(pArea)));
    const fDim = Math.max(18, pDim * 0.65);

    if (pMeters.length < 3 || Math.abs(pMeters[0][0]) > 400) {
      pMeters = [
        [-pDim / 2, -pDim / 2],
        [pDim / 2, -pDim / 2],
        [pDim / 2, pDim / 2],
        [-pDim / 2, pDim / 2],
      ];
    }
    if (fMeters.length < 3 || Math.abs(fMeters[0][0]) > 400) {
      fMeters = [
        [-fDim / 2, -fDim / 2],
        [fDim / 2, -fDim / 2],
        [fDim / 2, fDim / 2],
        [-fDim / 2, fDim / 2],
      ];
    }
    parcelRing = pMeters;
    footprintRing = fMeters;
    cx = 0;
    cy = 0;
  } else {
    parcelRing = rawRing.length ? rawRing : [[140, 140], [180, 140], [180, 165], [140, 165]];
    footprintRing = rawFr.length ? rawFr : [[145, 144], [175, 144], [175, 161], [145, 161]];
    const allMeters = [...parcelRing, ...footprintRing];
    const [c0, c1] = centroid(allMeters);
    cx = c0;
    cy = c1;
  }

  const allRingPts = [...parcelRing, ...footprintRing];
  const allXs = allRingPts.map((pt) => pt[0]);
  const allYs = allRingPts.map((pt) => pt[1]);
  const minX = allXs.length ? Math.min(...allXs) : -25;
  const maxX = allXs.length ? Math.max(...allXs) : 25;
  const minY = allYs.length ? Math.min(...allYs) : -25;
  const maxY = allYs.length ? Math.max(...allYs) : 25;
  const pad = 14;
  // Camera framing only. The old expression was
  //   p.structure?.height_m || (levels.length ? last.max_z : 18)
  // so a record with no stated height was framed as if it were 18 m tall.
  // Nothing here creates geometry, so a default only moves the camera; the
  // floors actually drawn below come from stated levels alone.
  const statedTopZ = Math.max(
    ...(p.levels || []).map((l) => l.max_z).filter((z): z is number => typeof z === 'number'),
    0,
  );
  const frameTop = p.structure?.height_m ?? (statedTopZ || 18);
  const targetZ = Math.min(25, Math.max(3, frameTop / 2));

  const arch = p.architectural_elements;
  const units: SceneUnit[] = (p.units || []).map((u) => ({
    source: 'design' as const,
    unit_number: u.unit_number,
    proposed_3d_id: u.proposed_3d_id ?? undefined,
    level_code: u.level_code,
    unit_type: u.unit_type || 'V',
    min_z: u.min_z,
    max_z: u.max_z,
    carpet_area_m2: u.carpet_area_m2,
    built_up_area_m2: u.built_up_area_m2,
    volume_m3: u.volume_m3,
    ring: [],
    mesh_3d: u.mesh_3d || { vertices: [], indices: [], vertex_count: 0, triangle_count: 0 },
    center: u.center || [cx, cy, u.min_z],
    rights: u.rights,
  }));
  let convertedArch: SceneArchitecture | null = null;
  if (arch) {
    convertedArch = {
      slabs: arch.slabs.map((s) => ({ name: `SLAB-${s.level}`, bounds: s.bounds, z: s.z, thickness: s.thickness, level_code: s.level })),
      columns: arch.columns,
      central_core: arch.central_core,
      balconies: arch.balconies.map((bal) => ({
        level_code: bal.id,
        facade: bal.facade,
        z: bal.min_z,
        railing_height: bal.railing_height,
        bounds: bal.bounds,
      })),
      roof_crown: {
        parapet: { height: arch.roof_crown?.parapet?.height ?? 0.9, offset: 0 },
        lift_machine_room: arch.roof_crown?.lift_machine_room
          ? {
              center: [ (arch.roof_crown.lift_machine_room.bounds[0] + arch.roof_crown.lift_machine_room.bounds[2]) / 2,
                        (arch.roof_crown.lift_machine_room.bounds[1] + arch.roof_crown.lift_machine_room.bounds[3]) / 2 ],
              size: [ arch.roof_crown.lift_machine_room.bounds[2] - arch.roof_crown.lift_machine_room.bounds[0],
                      arch.roof_crown.lift_machine_room.bounds[3] - arch.roof_crown.lift_machine_room.bounds[1],
                      (arch.roof_crown.lift_machine_room.max_z || 0) - (arch.roof_crown.lift_machine_room.min_z || 0) ],
              base_z: arch.roof_crown.lift_machine_room.min_z || 0,
            }
          : { center: [cx, cy] as [number, number], size: [8, 4, 2.4] as [number, number, number], base_z: 18 },
        solar_pv_array: arch.roof_crown?.solar_pv_array
          ? { cols: 8, rows: 3, tilt_deg: arch.roof_crown.solar_pv_array.tilt_deg ?? 18,
              base_z: arch.roof_crown.solar_pv_array.z ?? 20, bounds: arch.roof_crown.solar_pv_array.bounds }
          : { cols: 8, rows: 3, tilt_deg: 18, base_z: 20, bounds: [0, 0, 0, 0] },
        water_tanks: (arch.roof_crown?.water_tanks || []).map((t) => ({
          code: t.id, position: [t.center[0], t.center[1]] as [number, number],
          base_z: t.center[2] ?? 0, radius: t.radius, height: t.height, color: t.id === 'OHT-01' ? '#3B82F6' : '#EF4444',
        })),
      },
      foundation: {
        raft_slab: arch.foundation?.raft_slab
          ? { bounds: arch.foundation.raft_slab.bounds, z: arch.foundation.raft_slab.min_z ?? -0.5, thickness: 0.5 }
          : { bounds: [0, 0, 0, 0], z: -0.5, thickness: 0.5 },
        piles: (arch.foundation?.piles || []).map((pl) => ({ id: pl.id, x: pl.center[0], y: pl.center[1], top_z: pl.top_z, bottom_z: pl.bottom_z, radius: pl.radius })),
        retaining_walls: arch.foundation?.retaining_walls ? { offset: arch.foundation.retaining_walls.thickness ?? 0.4 } : { offset: 0.4 },
      },
    };
  }
  const subs: SceneSubsurface[] = (p.subsurface_objects || []).map((s) => ({ ...s }));
  const pipe = subs.find((s) => s.geometry_3d.type === 'PipeLine');
  const clash: SceneClash | null = pipe
    ? {
        has_clash: true,
        severity: 'CRITICAL',
        rule_id: 'R009',
        utility_code: pipe.code,
        clash_depth_z: pipe.min_z,
        penetration_length_m:
          Math.abs(pipe.geometry_3d.end[0] - pipe.geometry_3d.start[0]) +
          Math.abs(pipe.geometry_3d.end[1] - pipe.geometry_3d.start[1]),
        clash_intersection_coords: [
          [pipe.geometry_3d.start[0], pipe.geometry_3d.start[1]],
          [pipe.geometry_3d.end[0], pipe.geometry_3d.end[1]],
        ],
        message: `${pipe.code} penetrates the basement foundation perimeter.`,
        recommended_action: 'Mandatory municipal diversion required before title registration.',
      }
    : null;

  // Was `[0, 1, 2, 3]` when a record stated no floors, which drew a
  // four-storey building out of a parcel that described none. An empty list
  // draws no storeys, which is what the record supports.
  const statedFloors = (p.levels || [])
    .map((lv) => lv.floor_number)
    .filter((n): n is number => typeof n === 'number' && Number.isFinite(n));
  const floorList = Array.from(new Set(statedFloors)).sort((a, b) => a - b);

  return {
    scene,
    center: { x: cx, y: cy },
    targetZ,
    ground: {
      cx: (minX + maxX) / 2,
      cy: (minY + maxY) / 2,
      sizeX: Math.max(50, maxX - minX + pad * 2),
      sizeY: Math.max(50, maxY - minY + pad * 2),
    },
    parcelRing,
    neighborRings: [],
    footprintRing,
    floorList,
    levels: (p.levels || [])
      .filter(
        (lv): lv is typeof lv & { min_z: number; max_z: number } =>
          typeof lv.min_z === 'number' && typeof lv.max_z === 'number',
      )
      .map((lv) => ({ level_code: lv.level_code, floor_number: lv.floor_number, min_z: lv.min_z, max_z: lv.max_z })),
    units,
    arch: convertedArch,
    subs,
    clash,
    elevated: (p.elevated_objects || []) as SceneElevated[],
    engineLabel: isDegree ? 'National 3D Twin Cadastre Engine' : 'legacy-payload',
  };
}

export const ThreeCadastralViewer: React.FC<Props> = ({
  property,
  selectedUnit,
  onSelectUnit,
  activeColorMode,
  undergroundMode,
  onToggleUnderground,
  isEpoch2,
  highlightedIds = [],
  compact = false,
  modelUrl = null,
  modelDisplayMode = 'strata',
}) => {
  const mountRef = useRef<HTMLDivElement>(null);

  const model = useMemo<SceneModel>(() => buildSceneModel(property), [property]);

  const [explodeFactor, setExplodeFactor] = useState<number>(0);
  const [sliceZ] = useState<number>(25);
  const [isSliceActive] = useState<boolean>(false);
  const [sunHour, setSunHour] = useState<number>(14);
  const [viewerStyle, setViewerStyle] = useState<'architectural' | 'cadastral' | 'xray' | 'wireframe'>('architectural');
  const [measureMode, setMeasureMode] = useState<boolean>(false);
  const [, setMeasurePoints] = useState<THREE.Vector3[]>([]);
  const [measureDistance, setMeasureDistance] = useState<number | null>(null);
  const [hoveredUnit, setHoveredUnit] = useState<SceneUnit | null>(null);
  const [cinema, setCinema] = useState<boolean>(false);
  const [epochStrength, setEpochStrength] = useState<number>(isEpoch2 ? 1 : 0);
  const flyAnimRef = useRef<number | null>(null);
  const epochDeltaRef = useRef<THREE.Group | null>(null);
  const epochDashRef = useRef<THREE.Line | null>(null);

  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const dirLightRef = useRef<THREE.DirectionalLight | null>(null);
  const clipPlaneRef = useRef<THREE.Plane | null>(null);
  const meshMapRef = useRef<Map<string, THREE.Mesh>>(new Map());
  const architecturalGroupRef = useRef<THREE.Group | null>(null);
  const explodedGroupsRef = useRef<Map<number, THREE.Group>>(new Map());
  const centerRef = useRef<THREE.Vector3>(new THREE.Vector3(model.center.x, model.center.y, model.targetZ));
  const orbitRef = useRef<THREE.Spherical | null>(null);
  const clashMeshRef = useRef<THREE.Mesh | null>(null);

  centerRef.current = new THREE.Vector3(model.center.x, model.center.y, model.targetZ);
  const centerVec = centerRef.current;
  const accent = useMemo(() => {
    const [ar, ag, ab] = accentRGB();
    return new THREE.Color(ar / 255, ag / 255, ab / 255);
  }, []);

  // Initialize Three.js Scene (fully data-driven)
  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    const scene = new THREE.Scene();
    scene.up.set(0, 0, 1);
    scene.background = new THREE.Color(0xffffff);
    scene.fog = new THREE.FogExp2(0xffffff, 0.0025);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1200);
    camera.up.set(0, 0, 1);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.localClippingEnabled = true;
    rendererRef.current = renderer;

    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
    scene.add(ambientLight);
    const dirLight1 = new THREE.DirectionalLight(0xfff7ed, 1.25);
    dirLight1.castShadow = true;
    dirLight1.shadow.mapSize.width = 2048;
    dirLight1.shadow.mapSize.height = 2048;
    dirLight1.shadow.camera.near = 10;
    dirLight1.shadow.camera.far = 600;
    const g = model.ground;
    dirLight1.shadow.camera.left = -g.sizeX;
    dirLight1.shadow.camera.right = g.sizeX;
    dirLight1.shadow.camera.top = g.sizeY;
    dirLight1.shadow.camera.bottom = -g.sizeY;
    dirLight1.shadow.bias = -0.0005;
    scene.add(dirLight1);
    dirLightRef.current = dirLight1;
    const dirLight2 = new THREE.DirectionalLight(0xdbeafe, 0.35);
    dirLight2.position.set(g.cx + 100, g.cy + 200, 40);
    scene.add(dirLight2);

    // Ground cadastre sized from actual parcel + neighbour bounds
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0xecefeb, roughness: 0.92, metalness: 0.03,
      transparent: true, opacity: undergroundMode ? 0.2 : 0.95,
    });
    const groundMesh = new THREE.Mesh(new THREE.PlaneGeometry(g.sizeX, g.sizeY), groundMat);
    groundMesh.receiveShadow = true;
    groundMesh.position.set(g.cx, g.cy, 0);
    scene.add(groundMesh);

    const gridHelper = new THREE.GridHelper(Math.max(g.sizeX, g.sizeY), 32, 0xc2ccd6, 0xe3e8e4);
    gridHelper.rotation.x = Math.PI / 2;
    gridHelper.position.set(g.cx, g.cy, 0.03);
    scene.add(gridHelper);

    const ringLine = (ring: number[][], z: number, color: number, opacity: number) => {
      if (ring.length < 3) return;
      const pts = ring.map(([x, y]) => new THREE.Vector3(x, y, z));
      pts.push(new THREE.Vector3(ring[0][0], ring[0][1], z));
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity })
      );
      scene.add(line);
    };

    // Parcel boundary (data-driven)
    ringLine(model.parcelRing, 0.08, accent.getHex(), 0.9);
    // Neighbour lot lines (data-driven)
    model.neighborRings.forEach((nr) => ringLine(nr, 0.06, 0x94a3b8, 0.55));

    // Clip plane for section slice
    const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), sliceZ);
    clipPlaneRef.current = clipPlane;

    const archGroup = new THREE.Group();
    scene.add(archGroup);
    architecturalGroupRef.current = archGroup;

    const floorGroups = new Map<number, THREE.Group>();
    const getFloorGroup = (f: number): THREE.Group => {
      let fg = floorGroups.get(f);
      if (!fg) {
        fg = new THREE.Group();
        scene.add(fg);
        floorGroups.set(f, fg);
      }
      return fg;
    };

    model.floorList.forEach((f) => {
      getFloorGroup(f);
    });
    explodedGroupsRef.current = floorGroups;
    // No `?? 5`. With no stated floors there is no top floor to explode or
    // roof, and the building is not drawn at all rather than drawn to an
    // assumed fifth level.
    const topFloor = model.floorList[model.floorList.length - 1];
    const roofGroup = topFloor === undefined ? null : getFloorGroup(topFloor);

    // ---- Data-driven architecture ---------------------------------------
    const arch = model.arch;
    if (arch) {
      // Slabs at each level's derived Z
      arch.slabs.forEach((slab) => {
        const [minX, minY, maxX, maxY] = slab.bounds;
        const w = maxX - minX || 1;
        const d = maxY - minY || 1;
        const slabGeo = new THREE.BoxGeometry(w, d, slab.thickness);
        const slabMat = new THREE.MeshStandardMaterial({
          color: 0xe2e8f0, roughness: 0.7, metalness: 0.15,
          clippingPlanes: isSliceActive ? [clipPlane] : [],
        });
        const slabMesh = new THREE.Mesh(slabGeo, slabMat);
        slabMesh.position.set((minX + maxX) / 2, (minY + maxY) / 2, slab.z - slab.thickness / 2);
        slabMesh.castShadow = true;
        slabMesh.receiveShadow = true;
        const edge = new THREE.LineSegments(
          new THREE.EdgesGeometry(slabGeo),
          new THREE.LineBasicMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.4 })
        );
        slabMesh.add(edge);
        getFloorGroup(floorIndexOf(slab.level_code)).add(slabMesh);
      });

      // Structural columns
      arch.columns.forEach((col) => {
        const colH = col.max_z - col.min_z;
        if (colH <= 0) return;
        const colGeo = new THREE.BoxGeometry(col.size[0], col.size[1], colH);
        const colMat = new THREE.MeshStandardMaterial({
          color: 0xcbd5e1, roughness: 0.6, metalness: 0.2,
          clippingPlanes: isSliceActive ? [clipPlane] : [],
        });
        const colMesh = new THREE.Mesh(colGeo, colMat);
        colMesh.position.set(col.x, col.y, col.min_z + colH / 2);
        colMesh.castShadow = true;
        colMesh.receiveShadow = true;
        archGroup.add(colMesh);
      });

      // Central lift & stair core
      const core = arch.central_core;
      const [cMinX, cMinY, cMaxX, cMaxY] = core.bounds;
      const coreH = core.max_z - core.min_z;
      if (coreH > 0) {
        const coreGeo = new THREE.BoxGeometry(cMaxX - cMinX, cMaxY - cMinY, coreH);
        const coreMat = new THREE.MeshStandardMaterial({
          color: 0x38bdf8, roughness: 0.4, metalness: 0.3, transparent: true,
          opacity: viewerStyle === 'xray' ? 0.35 : 0.75,
          clippingPlanes: isSliceActive ? [clipPlane] : [],
        });
        const coreMesh = new THREE.Mesh(coreGeo, coreMat);
        coreMesh.position.set((cMinX + cMaxX) / 2, (cMinY + cMaxY) / 2, core.min_z + coreH / 2);
        archGroup.add(coreMesh);
      }

      // Balconies with glass balustrades
      arch.balconies.forEach((balc) => {
        const [bMinX, bMinY, bMaxX, bMaxY] = balc.bounds;
        const bw = bMaxX - bMinX;
        const bd = bMaxY - bMinY;
        if (bw <= 0 || bd <= 0) return;
        const balcMesh = new THREE.Mesh(
          new THREE.BoxGeometry(bw, bd, 0.2),
          new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.7 })
        );
        balcMesh.position.set((bMinX + bMaxX) / 2, (bMinY + bMaxY) / 2, balc.z);
        balcMesh.castShadow = true;
        const railMesh = new THREE.Mesh(
          new THREE.BoxGeometry(bw, 0.05, balc.railing_height),
          new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.1, metalness: 0.9, transparent: true, opacity: 0.45 })
        );
        railMesh.position.set(0, balc.facade === 'SOUTH' ? -bd / 2 : bd / 2, balc.railing_height / 2);
        balcMesh.add(railMesh);
        getFloorGroup(floorIndexOf(balc.level_code)).add(balcMesh);
      });

      // Rooftop crown
      if (roofGroup) {
        const rc = arch.roof_crown;
        // Lift machine room (data-driven)
        const lmr = rc.lift_machine_room;
        const lmrW = lmr.size[0];
        const lmrD = lmr.size[1];
        const lmrH = Math.max(lmr.size[2], 0.5);
        const lmrMesh = new THREE.Mesh(
          new THREE.BoxGeometry(lmrW, lmrD, lmrH),
          new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.6 })
        );
        const [lx, ly] = lmr.center;
        lmrMesh.position.set(lx, ly, lmr.base_z + lmrH / 2);
        lmrMesh.castShadow = true;
        roofGroup.add(lmrMesh);

        // Solar PV panels (derived grid count from bounds)
        const pv = rc.solar_pv_array;
        const [pMinX, pMinY, pMaxX, pMaxY] = pv.bounds;
        const cols = pv.cols || 8;
        const rows = pv.rows || 3;
        if (pMaxX > pMinX && pMaxY > pMinY) {
          const cellW = (pMaxX - pMinX) / cols;
          const cellD = (pMaxY - pMinY) / rows;
          for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
              const panel = new THREE.Mesh(
                new THREE.BoxGeometry(cellW * 0.82, cellD * 0.82, 0.06),
                new THREE.MeshStandardMaterial({ color: 0x1e3a8a, roughness: 0.2, metalness: 0.8 })
              );
              panel.position.set(pMinX + cellW * c + cellW / 2, pMinY + cellD * r + cellD / 2, pv.base_z);
              panel.rotation.x = ((pv.tilt_deg || 18) * Math.PI) / 180;
              panel.castShadow = true;
              roofGroup.add(panel);
            }
          }
        }

        // Water tanks
        rc.water_tanks.forEach((tank) => {
          const tankMesh = new THREE.Mesh(
            new THREE.CylinderGeometry(tank.radius, tank.radius, tank.height, 24),
            new THREE.MeshStandardMaterial({ color: colorHexToNumber(tank.color), roughness: 0.3, metalness: 0.6 })
          );
          tankMesh.position.set(tank.position[0], tank.position[1], tank.base_z + tank.height / 2);
          tankMesh.castShadow = true;
          roofGroup.add(tankMesh);
        });
      }

      // Subterranean deep foundation piles (data-driven)
      if (undergroundMode && arch.foundation) {
        arch.foundation.piles.forEach((pile) => {
          const pileH = pile.top_z - pile.bottom_z;
          if (pileH <= 0) return;
          const pileGeo = new THREE.CylinderGeometry(pile.radius, pile.radius, pileH, 16);
          const pileMesh = new THREE.Mesh(pileGeo, new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.8, metalness: 0.2 }));
          pileMesh.position.set(pile.x, pile.y, pile.bottom_z + pileH / 2);
          archGroup.add(pileMesh);
        });
      }
    }

    // ---- Render cadastral units (extracted + design) ---------------------
    meshMapRef.current.clear();
    const getUnitColor = (u: SceneUnit, idx: number): number => {
      if (highlightedIds.includes(u.unit_number) || highlightedIds.includes(u.proposed_3d_id)) {
        return 0xf59e0b;
      }
      if (viewerStyle === 'architectural') {
        if (u.unit_type === 'P') return 0x5b6472;
        const floor = floorIndexOf(u.level_code);
        const step = ((floor % 3) * 0x0a0a0c + idx % 2 * 0x040407) & 0xffffff;
        return 0xd7dfe8 + step;
      }
      if (activeColorMode === 'rights') {
        const rights = u.rights || [];
        const hasMortgage = rights.some((r) => r.right_type === 'MORTGAGE');
        const hasEasement = rights.some((r) => r.right_type === 'EASEMENT');
        if (hasMortgage) return RIGHTS_FILL.mortgage;
        if (hasEasement) return RIGHTS_FILL.easement;
        if (u.unit_type === 'P') return RIGHTS_FILL.parking;
        return RIGHTS_FILL.unencumbered;
      }
      return 0x10b981;
    };

    // ---- Auto-generate concrete floor slabs if architectural elements missing ----
    if (!model.arch && model.levels.length > 0 && model.footprintRing.length >= 3) {
      const xs = model.footprintRing.map(([x]) => x);
      const ys = model.footprintRing.map(([, y]) => y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const w = maxX - minX;
      const d = maxY - minY;
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;

      model.levels.forEach((lv) => {
        const slabGeo = new THREE.BoxGeometry(w + 0.3, d + 0.3, 0.2);
        const slabMat = new THREE.MeshStandardMaterial({
          color: 0xe2e8f0, roughness: 0.7, metalness: 0.15,
          clippingPlanes: isSliceActive ? [clipPlane] : [],
        });
        const slabMesh = new THREE.Mesh(slabGeo, slabMat);
        slabMesh.position.set(cx, cy, lv.min_z);
        slabMesh.castShadow = true;
        slabMesh.receiveShadow = true;
        const edge = new THREE.LineSegments(
          new THREE.EdgesGeometry(slabGeo),
          new THREE.LineBasicMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.4 })
        );
        slabMesh.add(edge);
        getFloorGroup(floorIndexOf(lv.level_code ?? undefined)).add(slabMesh);
      });

      // Rooftop parapet & lift room
      const topLv = model.levels[model.levels.length - 1];
      // A rooftop needs a top level to sit on. With none stated there is no
      // roof to build, so none is placed at an assumed elevation.
      if (topLv) {
        const roofZ = topLv.max_z;
        const lmrGeo = new THREE.BoxGeometry(w * 0.3, d * 0.3, 2.5);
        const lmrMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.6 });
        const lmrMesh = new THREE.Mesh(lmrGeo, lmrMat);
        lmrMesh.position.set(cx, cy, roofZ + 1.25);
        lmrMesh.castShadow = true;
        archGroup.add(lmrMesh);
      }
    }

    model.units.forEach((u, idx) => {
      let geometry: THREE.BufferGeometry;
      const meshData = u.mesh_3d;
      if (meshData && meshData.vertices && meshData.vertices.length > 0) {
        geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(meshData.vertices, 3));
        geometry.setIndex(meshData.indices);
        geometry.computeVertexNormals();
      } else {
        // No mesh_3d for this unit, so there is no known plan shape for it.
        //
        // This used to extrude a solid box and place it in one of four quadrants
        // chosen by `((unit_number - 1) % 4)`. Both halves of that were invented:
        // a unit's plan extent is not derivable from its number, and four
        // units repeating the same four positions is an artefact of the modulo,
        // not of the building. Two units with consecutive numbers landed in
        // different quadrants and two with the same residue landed on top of each
        // other, so the scene showed floor divisions that were never surveyed.
        //
        // What is genuinely known is that a unit exists on this level between
        // min_z and max_z. So that is all that gets drawn: a marker at the
        // building centroid at the stated height, visually distinct from real
        // geometry and flagged in userData. Extent, shape and orientation stay
        // undrawn rather than guessed.
        const fp = model.footprintRing;
        const xs = fp.map(([x]) => x);
        const ys = fp.map(([, y]) => y);
        const minX = xs.length ? Math.min(...xs) : 0;
        const maxX = xs.length ? Math.max(...xs) : 0;
        const minY = ys.length ? Math.min(...ys) : 0;
        const maxY = ys.length ? Math.max(...ys) : 0;
        const zMid = (u.min_z + u.max_z) / 2;
        const cx = (minX + maxX) / 2;
        const cy = (minY + maxY) / 2;
        const bandHeight = Math.max(0.5, u.max_z - u.min_z);

        const markerGeo = new THREE.OctahedronGeometry(Math.max(0.6, bandHeight * 0.22), 0);
        markerGeo.translate(cx, cy, zMid);
        geometry = markerGeo;
      }

      const geometryUnavailable = !(u.mesh_3d && u.mesh_3d.vertices && u.mesh_3d.vertices.length > 0);

      // A placeholder must not borrow the palette that means "measured volume",
      // or it reads as a real flat that happens to be small.
      const baseColor = geometryUnavailable ? '#d97706' : getUnitColor(u, idx);
      const isSelected = selectedUnit?.unit_number === u.unit_number;
      const isSubterranean = u.max_z <= 0;
      let opacityVal = undergroundMode ? (isSubterranean ? 0.96 : 0.16) : 0.92;
      if (viewerStyle === 'xray') opacityVal = 0.28;
      if (modelDisplayMode === 'architectural') opacityVal = 0.08;
      else if (modelDisplayMode === 'hybrid') opacityVal = 0.70;
      // Placeholders stay legible rather than fading with the solid masses.
      if (geometryUnavailable && modelDisplayMode !== 'architectural') opacityVal = 0.95;

      const material = new THREE.MeshStandardMaterial({
        color: isSelected ? accent.getHex() : baseColor,
        roughness: 0.55, metalness: 0.1, transparent: true, opacity: opacityVal,
        clippingPlanes: isSliceActive ? [clipPlane] : [],
        wireframe: viewerStyle === 'wireframe' || modelDisplayMode === 'architectural',
      });

      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData = { unit: u, geometryUnavailable };
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      const edgeGeo = new THREE.EdgesGeometry(geometry, 22);
      const edgeMat = new THREE.LineBasicMaterial({
        color: isSelected ? accent.getHex() : 0x6b7583, transparent: true, opacity: isSelected ? 0.95 : 0.42,
      });
      mesh.add(new THREE.LineSegments(edgeGeo, edgeMat));
      getFloorGroup(floorIndexOf(u.level_code)).add(mesh);
      meshMapRef.current.set(u.unit_number, mesh);
    });

    // ---- Subsurface utilities + data-driven clash marker -----------------
    model.subs.forEach((sub) => {
      const gh = sub.geometry_3d;
      if (gh.type === 'PipeLine' || gh.type === 'TunnelLine') {
        const start = new THREE.Vector3(...gh.start);
        const end = new THREE.Vector3(...gh.end);
        const distance = start.distanceTo(end);
        if (distance < 0.01) return;
        const inClash = model.clash?.utility_code === sub.code;
        const pipeMesh = new THREE.Mesh(
          new THREE.CylinderGeometry(gh.radius || 0.4, gh.radius || 0.4, distance, 16),
          new THREE.MeshStandardMaterial({
            color: inClash ? 0xdc2626 : 0x8b5cf6, roughness: 0.3, metalness: 0.6,
            emissive: inClash ? 0x991b1b : 0x000000, emissiveIntensity: inClash ? 0.7 : 0.0,
          })
        );
        pipeMesh.position.copy(start.clone().add(end).multiplyScalar(0.5));
        pipeMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), end.clone().sub(start).normalize());
        scene.add(pipeMesh);
      }
    });

    // Clash marker — derived from the detector's intersection coordinates
    if (model.clash && model.clash.has_clash && model.clash.clash_intersection_coords.length >= 1) {
      const xs = model.clash.clash_intersection_coords.map((c) => c[0]);
      const ys = model.clash.clash_intersection_coords.map((c) => c[1]);
      const midX = xs.reduce((a, b) => a + b, 0) / xs.length;
      const midY = ys.reduce((a, b) => a + b, 0) / ys.length;
      const pipe = model.subs.find((s) => s.geometry_3d.type === 'PipeLine');
      const clashZ = (pipe?.min_z ?? model.clash.clash_depth_z ?? -3.5) + 0.3;
      const clashSphere = new THREE.Mesh(
        new THREE.SphereGeometry(1.2, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0xef4444, wireframe: true, transparent: true, opacity: 0.85 })
      );
      clashSphere.position.set(midX, midY, clashZ);
      scene.add(clashSphere);
      clashMeshRef.current = clashSphere;
      // Penetration band along the reported intersection segment
      if (model.clash.clash_intersection_coords.length >= 2) {
        const [ax, ay] = model.clash.clash_intersection_coords[0];
        const [bx, by] = model.clash.clash_intersection_coords[1];
        const line = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(ax, ay, clashZ),
            new THREE.Vector3(bx, by, clashZ),
          ]),
          new THREE.LineBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.9 })
        );
        scene.add(line);
      }
    }

    // ---- Elevated objects (skybridge + air column) -----------------------
    model.elevated.forEach((eo) => {
      const ghx = eo.geometry_3d;
      if (ghx.type === 'Skybridge') {
        const start = new THREE.Vector3(...ghx.start);
        const end = new THREE.Vector3(...ghx.end);
        const len = start.distanceTo(end);
        if (len < 0.01) return;
        const w = ghx.width || 3;
        const h = ghx.height || 3.2;
        const bridge = new THREE.Mesh(
          new THREE.BoxGeometry(len, w, h),
          new THREE.MeshStandardMaterial({ color: 0x22d3ee, roughness: 0.2, metalness: 0.4, transparent: true, opacity: 0.55 })
        );
        bridge.position.copy(start.clone().add(end).multiplyScalar(0.5)).setZ(start.z + h / 2);
        bridge.castShadow = true;
        scene.add(bridge);
        // Under-deck handrails derived from endpoints
        const railLenMat = new THREE.LineBasicMaterial({ color: 0x155e75 });
        const railPts = [
          new THREE.Vector3(start.x, start.y - w / 2, start.z),
          new THREE.Vector3(end.x, end.y - w / 2, start.z),
          new THREE.Vector3(end.x, end.y + w / 2, start.z),
          new THREE.Vector3(start.x, start.y + w / 2, start.z),
        ];
        railPts.forEach((_, i) => {
          const ln = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints([railPts[i], railPts[(i + 1) % railPts.length]]),
            railLenMat
          );
          scene.add(ln);
        });
      } else if (ghx.type === 'AirColumn') {
        const ringFoot = (ghx.footprint || []) as number[][];
        if (ringFoot.length >= 3) {
          const shape = new THREE.Shape();
          ringFoot.forEach(([x, y], i) => (i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y)));
          shape.closePath();
          const geo = new THREE.ExtrudeGeometry(shape, {
            depth: Math.max((eo.max_z || 0) - (eo.min_z || 0), 1),
            bevelEnabled: false,
          });
          const airMesh = new THREE.Mesh(
            geo,
            new THREE.MeshStandardMaterial({
              color: accent.getHex(), transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false,
            })
          );
          airMesh.position.set(0, 0, eo.min_z || 0);
          scene.add(airMesh);
        }
      }
    });

    // ---- Epoch-2 LiDAR delta (monitored unauthorized growth) -------------
    if (isEpoch2 && model.footprintRing.length >= 3) {
      const xs = model.footprintRing.map(([x]) => x);
      const ys = model.footprintRing.map(([, y]) => y);
      const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
      const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
      const unitTop = model.units.reduce((m, u) => Math.max(m, u.max_z || 0), 0);
      const metaRoofZ = model.scene?.meta.roof_z ?? 18;
      const buildTop = Math.max(unitTop, metaRoofZ);
      const fullH = property.structure?.height_m || buildTop;
      const deltaH = Math.max(1.5, fullH - buildTop);

      const pg = new THREE.CylinderGeometry(0.08, 0.08, deltaH, 8, 1, true);
      pg.translate(0, deltaH / 2, 0);
      pg.rotateX(Math.PI / 2);
      const deltaGroup = new THREE.Group();
      const growGeo = new THREE.BoxGeometry(maxX - minX, maxY - minY, deltaH);
      growGeo.translate(0, 0, deltaH / 2);
      const growMat = new THREE.MeshStandardMaterial({
        color: 0xef4444,
        transparent: true,
        opacity: 0.32,
        roughness: 0.5,
        metalness: 0.1,
        wireframe: false,
      });
      const growMesh = new THREE.Mesh(growGeo, growMat);
      growMesh.position.set((minX + maxX) / 2, (minY + maxY) / 2, 0);
      deltaGroup.add(growMesh);
      const growEdge = new THREE.LineSegments(
        new THREE.EdgesGeometry(growGeo),
        new THREE.LineBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.9 })
      );
      growMesh.add(growEdge);
      const ghostDashed = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0, 0),
          new THREE.Vector3(0, 0, deltaH),
        ]),
        new THREE.LineDashedMaterial({ color: 0xdc2626, dashSize: 0.5, gapSize: 0.3 })
      );
      ghostDashed.computeLineDistances();
      ghostDashed.position.set((minX + maxX) / 2, (minY + maxY) / 2, buildTop);
      scene.add(ghostDashed);
      epochDashRef.current = ghostDashed;
      deltaGroup.position.x = (minX + maxX) / 2;
      deltaGroup.position.y = (minY + maxY) / 2;
      deltaGroup.position.z = buildTop;
      deltaGroup.scale.z = epochStrength;
      epochDeltaRef.current = deltaGroup;
      scene.add(deltaGroup);
    }

    // ---- Camera framed on the data-driven footprint center ---------------
    const ext = (model.ground.sizeX + model.ground.sizeY) / 2;
    if (!orbitRef.current) {
      const radius = Math.max(28, ext * (compact ? 0.68 : 0.9));
      const camH = Math.min(70, radius * 0.7);
      camera.position.set(centerVec.x + radius, centerVec.y - radius * 0.9, centerVec.z + camH);
      camera.lookAt(centerVec);
      orbitRef.current = new THREE.Spherical().setFromVector3(camera.position.clone().sub(centerVec));
    } else {
      camera.position.copy(centerVec).add(new THREE.Vector3().setFromSpherical(orbitRef.current));
      camera.lookAt(centerVec);
    }

    // ---- Interaction -----------------------------------------------------
    let isMouseDown = false;
    let prevMousePos = { x: 0, y: 0 };
    const spherical = orbitRef.current!;

    const onMouseDown = (e: MouseEvent) => { isMouseDown = true; prevMousePos = { x: e.clientX, y: e.clientY }; };
    const onMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const mouse = new THREE.Vector2(
        ((e.clientX - rect.left) / container.clientWidth) * 2 - 1,
        -((e.clientY - rect.top) / container.clientHeight) * 2 + 1
      );
      const raycaster = new THREE.Raycaster();
      raycaster.setFromCamera(mouse, camera);
      if (isMouseDown) {
        const deltaX = e.clientX - prevMousePos.x;
        const deltaY = e.clientY - prevMousePos.y;
        prevMousePos = { x: e.clientX, y: e.clientY };
        spherical.theta -= deltaX * 0.007;
        spherical.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.05, spherical.phi - deltaY * 0.007));
        camera.position.setFromSpherical(spherical).add(centerVec);
        camera.lookAt(centerVec);
      } else {
        const meshes = Array.from(meshMapRef.current.values());
        const intersects = raycaster.intersectObjects(meshes, false);
        if (intersects.length > 0) {
          const hitUnit = intersects[0].object.userData.unit as SceneUnit;
          setHoveredUnit(hitUnit);
          container.style.cursor = 'pointer';
        } else {
          setHoveredUnit(null);
          container.style.cursor = 'default';
        }
      }
    };
    const onMouseUp = () => { isMouseDown = false; };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      spherical.radius = Math.max(12, Math.min(400, spherical.radius + e.deltaY * 0.08));
      camera.position.setFromSpherical(spherical).add(centerVec);
      camera.lookAt(centerVec);
    };
    const onClick = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const mouse = new THREE.Vector2(
        ((e.clientX - rect.left) / container.clientWidth) * 2 - 1,
        -((e.clientY - rect.top) / container.clientHeight) * 2 + 1
      );
      const raycaster = new THREE.Raycaster();
      raycaster.setFromCamera(mouse, camera);

      if (measureMode) {
        const intersects = raycaster.intersectObjects(scene.children, true);
        if (intersects.length > 0) {
          const pt = intersects[0].point;
          setMeasurePoints((prev) => {
            const next = [...prev, pt];
            if (next.length === 2) setMeasureDistance(roundNum(next[0].distanceTo(next[1]), 2));
            else if (next.length > 2) { setMeasureDistance(null); return [pt]; }
            return next;
          });
        }
        return;
      }
      const meshes = Array.from(meshMapRef.current.values());
      const intersects = raycaster.intersectObjects(meshes, false);
      if (intersects.length > 0) {
        const unit = intersects[0].object.userData.unit as SceneUnit;
        onSelectUnit(selectedUnit?.unit_number === unit.unit_number ? null : (unit as CadastralUnit));
      } else {
        onSelectUnit(null);
      }
    };

    container.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    container.addEventListener('wheel', onWheel, { passive: false });
    container.addEventListener('click', onClick);

    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      if (clashMeshRef.current) {
        const t = Date.now() / 1000;
        const s = 1 + Math.sin(t * 3) * 0.25;
        clashMeshRef.current.scale.setScalar(s);
      }
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!mountRef.current || !cameraRef.current || !rendererRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animId);
      container.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      container.removeEventListener('wheel', onWheel);
      container.removeEventListener('click', onClick);
      window.removeEventListener('resize', handleResize);

      // Release the GPU resources this effect created.
      //
      // This effect rebuilds the precinct mesh, every unit mesh, the measure
      // rail/line geometries and their materials, and its dependency array
      // includes `selectedUnit` and `isSliceActive`. So it re-runs on ordinary
      // interaction -- selecting a unit, toggling a slice -- not just when the
      // property changes. The old cleanup removed listeners and disposed the
      // renderer but never disposed a single BufferGeometry or Material, so
      // each re-run stranded the previous set on the GPU. That is the leak the
      // perf gate caught: `renderer.info.memory.geometries` came back +1 after
      // five area switches back to the starting area.
      //
      // `renderer.dispose()` alone does not release scene-owned resources, and
      // the renderer's own internal caches are gone once it is disposed, so
      // the traverse has to happen first.
      //
      // The BUILDER_PROPOSAL GLB is added to this same scene by a separate
      // effect that owns its own disposal. `Object3D.traverse` cannot prune a
      // subtree by returning early, so ownership is checked by walking parents
      // instead: anything under BUILDER_PROPOSAL is left alone.
      const ownedByBuilderProposal = (o: THREE.Object3D): boolean => {
        let p: THREE.Object3D | null = o;
        while (p) {
          if (p.name === 'BUILDER_PROPOSAL') return true;
          p = p.parent;
        }
        return false;
      };

      const seenMaterials = new Set<THREE.Material>();
      const seenGeometries = new Set<THREE.BufferGeometry>();
      // Collect first, mutate second: detaching during traverse would skip
      // siblings because the tree changes underneath the iteration.
      const owned: THREE.Object3D[] = [];
      scene.traverse((obj) => {
        if (!ownedByBuilderProposal(obj)) owned.push(obj);
      });
      owned.forEach((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.geometry && !seenGeometries.has(mesh.geometry)) {
          seenGeometries.add(mesh.geometry);
          mesh.geometry.dispose();
        }
        const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
        if (!mat) return;
        // Materials are shared across units, so dispose each exactly once.
        (Array.isArray(mat) ? mat : [mat]).forEach((m) => {
          if (seenMaterials.has(m)) return;
          seenMaterials.add(m);
          m.dispose();
        });
      });
      // Detach only what this effect owns. scene.clear() is NOT safe here: it
      // would also remove BUILDER_PROPOSAL, which a different effect owns and
      // will not re-add until modelUrl/model/modelDisplayMode change.
      owned.forEach((obj) => obj.parent?.remove(obj));

      renderer.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [property, model, activeColorMode, undergroundMode, viewerStyle, measureMode, compact, isSliceActive, selectedUnit, accent, isEpoch2]);

  // Builder proposal overlay — a translucent GLB standing on the parcel footprint
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !modelUrl) return;
    let disposed = false;
    const holder = new THREE.Group();
    holder.name = 'BUILDER_PROPOSAL';
    loadGlb(modelUrl)
      .then((g) => {
        if (disposed) return;
        if (modelDisplayMode === 'architectural') {
          applySolid(g);
        } else {
          applyTranslucent(g);
        }
        const ring = model.footprintRing.length >= 3
          ? model.footprintRing
          : outerRing(property.structure?.footprint_geojson || property.parcel?.polygon_geojson);
        if (ring.length >= 3) {
          const c = centroid(ring);
          const bounds = ringBounds(ring);
          fitGlbToFootprint(g, { x: c[0], y: c[1] }, (bounds.maxX - bounds.minX) || 40, (bounds.maxY - bounds.minY) || 40);
        }
        holder.add(g);
        scene.add(holder);
      })
      .catch((err) => console.error('Builder proposal GLB failed to load', err));
    const old = scene.getObjectByName('BUILDER_PROPOSAL');
    if (old && old !== holder) {
      scene.remove(old);
      disposeGlb(old);
    }
    return () => {
      disposed = true;
      if (holder.parent) holder.removeFromParent();
      disposeGlb(holder);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelUrl, model, modelDisplayMode]);

  // Epoch scrub: drive the delta extrusion height (0=survey baseline, 1=Epoch-2 monitored)
  useEffect(() => {
    if (epochDeltaRef.current) epochDeltaRef.current.scale.set(1, 1, epochStrength);
    if (epochDashRef.current) {
      epochDashRef.current.scale.set(1, 1, Math.max(epochStrength, 0.001));
    }
  }, [epochStrength]);

  // Sun lighting (derived from hour, framed on the scene center)
  useEffect(() => {
    if (!dirLightRef.current) return;
    const light = dirLightRef.current;
    const sunAngle = ((sunHour - 6) / 12) * Math.PI;
    const sunDist = 140;
    light.position.set(
      centerVec.x + Math.cos(sunAngle) * sunDist,
      centerVec.y - Math.sin(sunAngle) * sunDist,
      Math.max(10, Math.sin(sunAngle) * 90)
    );
    if (sunHour <= 9 || sunHour >= 16) {
      light.color.setHex(0xfef08a);
      light.intensity = 1.05;
    } else {
      light.color.setHex(0xfff7ed);
      light.intensity = 1.35;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sunHour]);

  // Exploded floor separation
  useEffect(() => {
    if (!explodedGroupsRef.current) return;
    explodedGroupsRef.current.forEach((group, floorIndex) => {
      const offsetZ = floorIndex * explodeFactor * 4.2;
      group.position.set(0, 0, offsetZ);
    });
  }, [explodeFactor]);

  // Cinema inspection mode: dark diagnostic backdrop, focus glow + dim nearby units
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const bg = cinema ? 0x0b0d1c : 0xffffff;
    if (scene.background instanceof THREE.Color) scene.background.setHex(bg);
    if (scene.fog) scene.fog.color.setHex(bg);
    const dl = dirLightRef.current;
    if (dl) dl.intensity = cinema ? 0.45 : (sunHour <= 9 || sunHour >= 16 ? 1.05 : 1.35);
    meshMapRef.current.forEach((mesh) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (mesh.userData.baseOpacity === undefined) mesh.userData.baseOpacity = mat.opacity;
      const sel = selectedUnit?.unit_number === mesh.userData.unit.unit_number;
      const base = mesh.userData.baseOpacity as number;
      mat.emissive.setHex(cinema ? (sel ? accent.getHex() : 0x0c0e24) : 0x000000);
      mat.emissiveIntensity = cinema ? (sel ? 0.6 : 0.12) : 0;
      if (cinema) mat.opacity = sel ? Math.min(1, base * 1.08) : base * 0.45;
      else mat.opacity = base;
      const edges = mesh.children.find((c) => (c as THREE.LineSegments).isLineSegments) as THREE.LineSegments | undefined;
      if (edges) {
        const em = edges.material as THREE.LineBasicMaterial;
        if (edges.userData.baseOpacity === undefined) edges.userData.baseOpacity = em.opacity;
        em.opacity = cinema ? (sel ? 0.95 : (edges.userData.baseOpacity as number) * 0.3) : (sel ? 0.95 : (edges.userData.baseOpacity as number));
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cinema, selectedUnit, sunHour]);

  // 'C' toggles cinema inspection (ignore while typing / with modifiers)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'c' && e.key !== 'C') return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      setCinema((v) => !v);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Fly camera toward the selected unit for focused inspection
  useEffect(() => {
    if (flyAnimRef.current !== null) { cancelAnimationFrame(flyAnimRef.current); flyAnimRef.current = null; }
    if (!selectedUnit) return;
    const mesh = meshMapRef.current.get(selectedUnit.unit_number);
    if (!mesh || !cameraRef.current) return;
    const box = new THREE.Box3().setFromObject(mesh);
    const target = box.getCenter(new THREE.Vector3());
    const cam = cameraRef.current;
    const startPos = cam.position.clone();
    const toUnit = target.clone().sub(centerRef.current);
    const unitDist = Math.max(20, toUnit.length());
    const endPos = target.clone().add(toUnit.normalize().multiplyScalar(unitDist * 0.92));
    const startT = performance.now();
    const dur = 650;
    const tick = (now: number) => {
      const p = Math.min(1, (now - startT) / dur);
      const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      cam.position.lerpVectors(startPos, endPos, e);
      cam.lookAt(target);
      if (p < 1) flyAnimRef.current = requestAnimationFrame(tick);
      else {
        flyAnimRef.current = null;
        orbitRef.current = new THREE.Spherical().setFromVector3(
          cam.position.clone().sub(centerRef.current)
        );
      }
    };
    flyAnimRef.current = requestAnimationFrame(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUnit]);

  const setCameraPreset = (preset: 'isometric' | 'street' | 'blueprint' | 'subsurface' | 'rooftop') => {
    if (!cameraRef.current) return;
    const camera = cameraRef.current;
    const ext = model.ground.sizeX;
    if (preset === 'isometric') {
      camera.position.set(centerVec.x + ext * 0.45, centerVec.y - ext * 0.5, centerVec.z + ext * 0.35);
      camera.lookAt(centerVec);
    } else if (preset === 'street') {
      camera.position.set(centerVec.x, centerVec.y - ext * 0.6, 2.5);
      camera.lookAt(new THREE.Vector3(centerVec.x, centerVec.y, 8));
    } else if (preset === 'blueprint') {
      camera.position.set(centerVec.x, centerVec.y, 95);
      camera.lookAt(new THREE.Vector3(centerVec.x, centerVec.y, 0));
    } else if (preset === 'subsurface') {
      camera.position.set(centerVec.x + ext * 0.28, centerVec.y - ext * 0.28, -12);
      camera.lookAt(new THREE.Vector3(centerVec.x, centerVec.y, -4));
    } else if (preset === 'rooftop') {
      camera.position.set(centerVec.x + ext * 0.2, centerVec.y + ext * 0.2, centerVec.z + ext * 0.25);
      camera.lookAt(new THREE.Vector3(centerVec.x, centerVec.y, model.scene?.meta.roof_z ?? 18));
    }
    orbitRef.current = new THREE.Spherical().setFromVector3(camera.position.clone().sub(centerVec));
  };

  const roundNum = (val: number, decimals: number) => Math.round(val * Math.pow(10, decimals)) / Math.pow(10, decimals);

  const zoomBy = (factor: number) => {
    const cam = cameraRef.current;
    const s = orbitRef.current;
    if (!cam || !s) return;
    s.radius = Math.max(12, Math.min(400, s.radius * factor));
    cam.position.copy(centerVec).add(new THREE.Vector3().setFromSpherical(s));
    cam.lookAt(centerVec);
  };

  const clash = model.clash;
  const sceneMetaCrs = model.scene?.meta.crs || 'EPSG:7755';
  const sceneLabels = !!model.scene;
  const displayedUnit = (selectedUnit || hoveredUnit) as
    | (CadastralUnit & { source?: string })
    | null;

  return (
    <div className="relative w-full h-full bg-canvas select-none overflow-hidden font-sans">
      <div ref={mountRef} className="w-full h-full" />

      {compact && (
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2 pointer-events-none">
          <span className="w-2 h-2 rounded-sm bg-accent" />
          <span className="annotation text-ink-mut">LIVE · {property.structure.name || property.structure.building_code}</span>
        </div>
      )}

      {!compact && (
        <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
          <div className="flex items-center gap-1 bg-white/95 border border-slate-200 p-1 rounded-xl shadow-premium backdrop-blur-md">
            {(
              [
                ['architectural', 'LOD 3 Architecture', <Building2 key="a" className="w-3.5 h-3.5" />],
                ['cadastral', 'Cadastral Rights', <Shield key="c" className="w-3.5 h-3.5" />],
                ['xray', 'X-Ray Ghost', <Eye key="x" className="w-3.5 h-3.5" />],
                ['wireframe', 'CAD Wireframe', <Box key="w" className="w-3.5 h-3.5" />],
              ] as const
            ).map(([key, label, icon]) => (
              <button
                key={key}
                onClick={() => setViewerStyle(key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  viewerStyle === key ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {icon}
                {label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 bg-white/95 border border-slate-200 p-1.5 rounded-xl shadow-subtle backdrop-blur-md text-[11px] font-medium text-slate-600">
            <span className="text-[10px] uppercase font-bold text-slate-600 px-2 flex items-center gap-1">
              <Camera className="w-3 h-3 text-slate-600" /> Presets:
            </span>
            {(
              [
                ['isometric', '3D Isometric'],
                ['street', 'Street View'],
                ['blueprint', 'Top Blueprint'],
                ['subsurface', 'Subsurface'],
                ['rooftop', 'Rooftop & Solar'],
              ] as const
            ).map(([key, label]) => (
              <button key={key} onClick={() => setCameraPreset(key)} className="px-2 py-1 rounded-md hover:bg-slate-100">
                {label}
              </button>
            ))}
          </div>

          {/* Colour key for the cadastral fill.
              Rendered only while the rights colours are the ones actually on
              screen: in architectural style getUnitColor returns LOD greys
              before it ever consults the rights mode, so a rights key shown
              there would be describing a picture the viewer is not drawing. */}
          {activeColorMode === 'rights' && viewerStyle !== 'architectural' && (
            <div className="bg-white/95 border border-slate-200 p-3 rounded-xl shadow-premium backdrop-blur-md text-[11px] w-64">
              <div className="flex items-center justify-between gap-2 font-bold text-slate-800 mb-2">
                <span className="flex items-center gap-1.5">
                  <Palette className="w-3.5 h-3.5 text-emerald-600" />
                  Unit fill key
                </span>
                <span className="font-mono text-[10px] text-amber-800 bg-amber-50 border border-amber-300 px-1.5 py-0.5 rounded">
                  not a title status
                </span>
              </div>
              <ul className="space-y-1.5">
                {RIGHTS_FILL_LEGEND.map((entry) => (
                  <li key={entry.id} className="flex items-start gap-2">
                    <span
                      className="w-3 h-3 rounded-sm shrink-0 mt-0.5 border border-slate-400"
                      style={{ backgroundColor: entry.hex }}
                      aria-hidden="true"
                    />
                    <span className="min-w-0">
                      <span className="block font-semibold text-slate-700">{entry.label}</span>
                      <span className="block text-[10px] leading-snug text-slate-500">{entry.note}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2.5 pt-2 border-t border-slate-100 text-[10px] leading-relaxed text-slate-500">
                Colours classify the modelled record only. None of them shows a registered title, a confirmed
                owner, or any finding by an authority — the rights shown here are modelled, not extracted from a
                land registry.
              </p>
            </div>
          )}
        </div>
      )}

      {!compact && (
        <div className="absolute top-4 right-4 z-10 flex flex-col gap-2 max-w-xs">
          <div className="bg-white/95 border border-slate-200 p-3 rounded-xl shadow-premium backdrop-blur-md text-xs">
            <div className="flex items-center justify-between font-bold text-slate-800 mb-1.5">
              <span className="flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-blue-600" />
                Exploded Floor Separation
              </span>
              <span className="font-mono text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded text-[11px]">
                {(explodeFactor * 100).toFixed(0)}%
              </span>
            </div>
            <input
              type="range" min="0" max="1" step="0.02" value={explodeFactor}
              onChange={(e) => setExplodeFactor(parseFloat(e.target.value))}
              className="w-full accent-blue-600 h-1.5 bg-slate-200 rounded-lg cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-400 mt-1">
              <span>Compact (0m)</span>
              <span>Floated (+21m)</span>
            </div>
          </div>

          <div className="bg-white/95 border border-slate-200 p-3 rounded-xl shadow-premium backdrop-blur-md text-xs">
            <div className="flex items-center justify-between font-bold text-slate-800 mb-1.5">
              <span className="flex items-center gap-1.5">
                <Sun className="w-3.5 h-3.5 text-amber-500" />
                Sun Path Daylight Simulation
              </span>
              <span className="font-mono text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded text-[11px]">
                {Math.floor(sunHour)}:{sunHour % 1 ? '30' : '00'} {sunHour >= 12 ? 'PM' : 'AM'}
              </span>
            </div>
            <input
              type="range" min="8" max="18" step="0.5" value={sunHour}
              onChange={(e) => setSunHour(parseFloat(e.target.value))}
              className="w-full accent-amber-500 h-1.5 bg-slate-200 rounded-lg cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-400 mt-1">
              <span>08:00 Morning</span><span>13:00 Noon</span><span>18:00 Dusk</span>
            </div>
          </div>

          <button
            onClick={() => setCinema((v) => !v)}
            title="Cinema inspection mode — dark backdrop, focus glow, C-key toggle"
            className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold border transition-all w-full ${
              cinema ? 'bg-slate-900 text-white border-slate-700 shadow-md' : 'bg-white/95 text-slate-700 border-slate-200 hover:bg-slate-100'
            }`}
          >
            <Moon className="w-3.5 h-3.5" />
            {cinema ? 'Cinema Inspection · C' : 'Cinema Inspection (C)'}
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { setMeasureMode(!measureMode); setMeasurePoints([]); setMeasureDistance(null); }}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold border transition-all ${
                measureMode ? 'bg-amber-500 text-white border-amber-600 shadow-md' : 'bg-white/95 text-slate-700 border-slate-200 hover:bg-slate-100'
              }`}
            >
              <Ruler className="w-3.5 h-3.5" />
              {measureMode ? 'Measuring... (Click 2 Pts)' : '3D Distance Caliper'}
            </button>
            <button
              onClick={onToggleUnderground}
              className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold border transition-all ${
                undergroundMode ? 'bg-purple-600 text-white border-purple-700 shadow-md' : 'bg-white/95 text-slate-700 border-slate-200 hover:bg-slate-100'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Underground
            </button>
          </div>

          {measureDistance !== null && (
            <div className="bg-amber-50 border border-amber-300 p-2.5 rounded-xl shadow-subtle text-xs font-bold text-amber-900 flex items-center justify-between">
              <span>Measured Distance:</span>
              <span className="font-mono text-amber-700 bg-white px-2 py-0.5 rounded border border-amber-200">
                {measureDistance.toFixed(2)} meters
              </span>
            </div>
          )}
        </div>
      )}

      {/* Epoch-2 scrub — before/after unauthorized-growth comparison */}
      {!compact && isEpoch2 && (
        <div className="absolute bottom-4 left-4 z-10 bg-white/95 border border-red-300 p-3 rounded-xl shadow-premium backdrop-blur-md text-xs w-64">
          <div className="flex items-center justify-between font-bold text-slate-800 mb-1.5">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
              LiDAR Epoch-2 Delta
            </span>
            <span className="font-mono text-red-700 bg-red-50 px-1.5 py-0.5 rounded text-[11px]">
              {epochStrength <= 0 ? 'Baseline' : `+${(3.5 * epochStrength).toFixed(1)} m`}
            </span>
          </div>
          <input
            type="range" min="0" max="1" step="0.01" value={epochStrength}
            onChange={(e) => setEpochStrength(parseFloat(e.target.value))}
            className="w-full accent-red-600 h-1.5 bg-slate-200 rounded-lg cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-slate-400 mt-1">
            <span>Survey 2019</span>
            <span>Monitored 2026</span>
          </div>
          <p className="mt-1.5 text-[10px] text-red-800 leading-relaxed">
            {epochStrength > 0.35
              ? 'Suspected unauthorised vertical growth above sanctioned roof line — flagged for enforcement.'
              : 'Slide to reveal suspected unauthorised growth captured by Epoch-2 LiDAR.'}
          </p>
        </div>
      )}

      {/* Data-derived subsurface clash alert */}
      {undergroundMode && !compact && clash && clash.has_clash && (
        <div className="absolute top-28 left-4 z-10 max-w-sm bg-red-50/95 border border-red-300 p-4 rounded-xl shadow-premium backdrop-blur-md animate-subterranean-pulse">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <div className="text-xs font-bold text-red-900 tracking-wide uppercase">
                Critical Subsurface Clash (Rule {clash.rule_id})
              </div>
              <p className="text-xs text-red-800 mt-1 leading-relaxed">{clash.message}</p>
              <div className="mt-2 text-[11px] text-red-700 font-semibold">{clash.recommended_action}</div>
            </div>
          </div>
        </div>
      )}

      <div className="absolute bottom-4 right-4 z-10 flex flex-col bg-white/95 border border-slate-200 rounded-xl shadow-premium overflow-hidden">
        <button onClick={() => zoomBy(0.82)} className="w-9 h-9 flex items-center justify-center text-slate-600 hover:text-blue-700 hover:bg-slate-100 transition border-b border-slate-200" title="Zoom in" aria-label="Zoom in">
          <Plus className="w-4 h-4" />
        </button>
        <button onClick={() => zoomBy(1.22)} className="w-9 h-9 flex items-center justify-center text-slate-600 hover:text-blue-700 hover:bg-slate-100 transition" title="Zoom out" aria-label="Zoom out">
          <Minus className="w-4 h-4" />
        </button>
      </div>

      {displayedUnit && (
        <div className="absolute bottom-4 left-4 z-10 bg-white/95 border border-slate-200 p-4 rounded-xl shadow-premium backdrop-blur-md max-w-xs text-xs">
          {(() => {
            const u = displayedUnit!;
            return (
              <>
                <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2.5">
                  <span className="font-bold text-slate-900 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-blue-600"></span>
                    {sceneLabels ? `${u.source === 'extracted' ? 'Extracted' : 'Flat / Unit'} ${u.unit_number}` : `Flat / Unit ${u.unit_number} (${u.level_code})`}
                  </span>
                  <span className="font-mono text-[10px] font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                    {u.unit_type === 'P' ? 'Parking Bay' : u.source === 'extracted' ? 'ML Extract' : 'Residential'}
                  </span>
                </div>
                <div className="space-y-1.5 font-mono text-[11px] text-slate-700">
                  {!u.mesh_3d?.vertices?.length ? (
                    // Say it where the numbers would be, so the placeholder
                    // marker in the scene is not read as a measured volume.
                    <div className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1.5 text-amber-900 text-[10px] leading-snug">
                      <span className="font-bold uppercase tracking-wide">Plan geometry unavailable.</span>{' '}
                      Only this unit&rsquo;s existence and height band
                      ({u.level_code}, {u.min_z}&ndash;{u.max_z} m) are recorded. The
                      marker shown in the scene sits at the building centroid and
                      does not represent the unit&rsquo;s size, shape or position.
                    </div>
                  ) : null}
                  <div className="flex justify-between">
                    <span className="text-slate-400 font-sans">Proposed 3D ID:</span>
                    <span className="text-blue-700 font-bold truncate max-w-[170px]" title={u.proposed_3d_id}>{u.proposed_3d_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 font-sans">Vertical Interval:</span>
                    <span className="text-slate-800 font-semibold">[{u.min_z.toFixed(1)}m, {u.max_z.toFixed(1)}m]</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 font-sans">Cadastral Volume:</span>
                    <span className="text-emerald-700 font-bold">{u.volume_m3.toFixed(1)} m³</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 font-sans">Carpet Area:</span>
                    <span className="text-slate-800 font-semibold">{u.carpet_area_m2.toFixed(1)} m²</span>
                  </div>
                </div>
                {u.rights && u.rights.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-slate-100">
                    <span className="text-[10px] font-sans uppercase font-bold text-slate-500 tracking-wider">Active Rights / Encumbrances:</span>
                    <div className="mt-1.5 space-y-1.5">
                      {u.rights.map((r, i) => (
                        <div key={i} className="flex items-center justify-between text-[11px]">
                          <span className="font-bold text-[10px] px-1.5 py-0.5 rounded"
                            style={{ backgroundColor: `${r.color_hex || '#2563eb'}15`, color: r.color_hex || '#2563eb' }}>
                            {r.right_type}
                          </span>
                          <span className="text-slate-700 font-semibold truncate max-w-[130px]" title={r.party_name}>{r.party_name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {/* Data-driven provenance + datum strip */}
      <div className="absolute bottom-4 right-4 z-10 bg-white/90 border border-slate-200 px-3 py-1.5 rounded-lg shadow-subtle font-mono text-[10px] text-slate-600 pointer-events-none flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
        <span>{sceneMetaCrs.split(' / ')[0]}</span>
        <span className="text-slate-500">|</span>
        <span>LOD 3 Solids</span>
        <span className="text-slate-500">|</span>
        <span>Z-Up</span>
        <span className="text-slate-500">|</span>
        {/* The strip used to read "VERIFIED SOURCE" for anything that was not
            flagged synthetic, so a parcel with no provenance at all — which is
            every parcel here — claimed to be verified. The three states below
            are the only ones the data supports, and the middle one reports the
            source's own declaration rather than endorsing it. */}
        <span
          className={
            property.provenance?.is_synthetic
              ? "text-amber-700 font-semibold"
              : property.provenance?.authoritative
                ? "text-blue-700 font-semibold"
                : "text-slate-500 font-semibold"
          }
        >
          {property.provenance?.is_synthetic
            ? "SYNTHETIC MODEL"
            : property.provenance?.authoritative
              ? "SOURCE-DECLARED AUTHORITATIVE"
              : "PROVENANCE UNKNOWN"}
        </span>
        {model.scene && model.scene.provenance?.run_hash && (
          <>
            <span className="text-slate-500">|</span>
            <span className="text-emerald-700" title={model.scene.provenance.run_hash}>
              run {model.scene.provenance.run_hash.slice(0, 12)}
            </span>
          </>
        )}
      </div>
    </div>
  );
};