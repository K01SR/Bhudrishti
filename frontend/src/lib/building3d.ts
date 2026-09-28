import * as THREE from 'three';
import { HeroProperty } from '../types/cadastre';
import { shapeFromRing, outerRing, ringBounds } from './cadastre3d';

export interface HeroLevelMeta {
  floor: number;
  type: string;
  height: number;
  z: [number, number];
}

export interface BuildingTwin {
  group: THREE.Group;
  floors: Map<number, THREE.Group>; // keyed by sorted index (0 = lowest)
  floorMeshes: THREE.Mesh[]; // solid per-floor volumes (hover target)
  levels: HeroLevelMeta[];
}

export function sortLevels(hero: HeroProperty): HeroLevelMeta[] {
  const levels = Array.isArray(hero.levels) ? hero.levels : [];
  // A level is only drawable if the record states an elevation band for it.
  // Skipping the rest is the point: this used to compute height as
  // `l.max_z - l.min_z`, which on a null min_z or max_z is NaN, and a NaN
  // height silently produced a degenerate box rather than a visible error.
  return levels
    .filter(
      (l): l is typeof l & { min_z: number; max_z: number; level_type: string } =>
        typeof l.min_z === 'number' &&
        typeof l.max_z === 'number' &&
        Number.isFinite(l.min_z) &&
        Number.isFinite(l.max_z)
    )
    .map((l) => ({
      floor: l.floor_number ?? 0,
      type: l.level_type ?? 'UNSPECIFIED',
      height: l.max_z - l.min_z,
      z: [l.min_z, l.max_z] as [number, number],
    }))
    .sort((a, b) => a.z[0] - b.z[0]);
}

/** Derive a floor number from a unit's level_code ('B1' → -1, 'G' → 0, 'L01'/'1' → 1 …). */
export function floorFromLevelCode(code: string | undefined): number {
  if (!code) return 0;
  if (code.toUpperCase() === 'B1') return -1;
  const up = code.toUpperCase();
  if (up === 'G' || up.startsWith('GF')) return 0;
  const numeric = up.replace('L0', '').replace('L', '').replace(/[^0-9-]/g, '');
  const n = parseInt(numeric, 10);
  return Number.isFinite(n) ? n : 0;
}

/** Build an architectural B-17 twin: per-floor prismatic volumes with seams,
 *  hairline edges, rooftop crown and a slightly recessed basement. Deterministic. */
export function buildHeroBuilding(arg: {
  hero: HeroProperty;
  accent: [number, number, number];
  heroCenter: [number, number];
}): BuildingTwin {
  const { hero, accent, heroCenter } = arg;
  const ring = outerRing(hero?.structure?.footprint_geojson);
  const [cx, cy] = heroCenter;
  const group = new THREE.Group();
  const floors = new Map<number, THREE.Group>();
  const floorMeshes: THREE.Mesh[] = [];
  const levels = sortLevels(hero);

  // Tallest footprint extent used for neighbour-scaled crown pieces
  const b = ring.length >= 3 ? ringBounds(ring) : { minX: -15, maxX: 15, minY: -14, maxY: 14 };
  const w = b.maxX - b.minX;
  const d = b.maxY - b.minY;

  // Facade palette: lift slightly warm-white with an almost-imperceptible per-floor ladder
  const edge = new THREE.Color(0x9aa3ad);
  const loadColor = new THREE.Color(edge).lerp(new THREE.Color(0xe9edf1), 0.55);

  const slabDepth = 0.18; // seam between floor plates

  levels.sort((a, b) => a.z[0] - b.z[0]);

  const makeFloor = (lv: HeroLevelMeta, sortedIndex: number) => {
    const fg = new THREE.Group();
    const h = Math.max(0.05, lv.height - (lv.floor > 0 ? slabDepth : 0));
    const isBasement = lv.type === 'BASEMENT';

    const geo = new THREE.ExtrudeGeometry(shapeFromRing(ring), { depth: h, bevelEnabled: false });
    geo.translate(0, 0, lv.z[0]);

    const base = isBasement
      ? new THREE.Color(0x4b5563)
      : new THREE.Color(0xe6ebf0).offsetHSL(0, 0, (sortedIndex % 2) * 0.012);

    const mat = new THREE.MeshStandardMaterial({
      color: base,
      roughness: 0.62,
      metalness: 0.08,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: isBasement ? 0.55 : 0.97,
    });

    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData = { building: true, floor: lv.floor, sortedIndex };
    fg.add(mesh);
    floorMeshes.push(mesh);

    // Hairline plate edges
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: isBasement ? 0x5b6472 : loadColor, transparent: true, opacity: 0.55 })
    );
    edges.userData = { building: true, floor: lv.floor, sortedIndex };
    fg.add(edges);

    // Basement: sitting below grade, slightly sunken — draw a ground-level collar line
    if (isBasement) {
      const collarPts = ring.map(([x, y]) => new THREE.Vector3(x, y, 0.06));
      const collar = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(collarPts),
        new THREE.LineBasicMaterial({ color: 0xb9c0c8, transparent: true, opacity: 0.7 })
      );
      fg.add(collar);
    }

    group.add(fg);
    floors.set(sortedIndex, fg);
    return fg;
  };

  levels.forEach((lv, i) => makeFloor(lv, i));

  // Rooftop crown on the topmost level
  const topZ = levels[levels.length - 1] ? levels[levels.length - 1].z[1] : 0;
  const crown = new THREE.Group();
  crown.position.set(cx, cy, 0);

  const capGeo = new THREE.ExtrudeGeometry(shapeFromRing(ring), { depth: 0.5, bevelEnabled: false });
  capGeo.translate(0, 0, topZ);
  const cap = new THREE.Mesh(capGeo, new THREE.MeshStandardMaterial({ color: 0xdde3e8, roughness: 0.5, metalness: 0.12, side: THREE.DoubleSide }));
  cap.castShadow = true;
  crown.add(cap);

  // Parapet ring
  const parapetPts = ring.map(([x, y]) => new THREE.Vector3(x, y, topZ + 0.55));
  const parapet = new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints(parapetPts),
    new THREE.LineBasicMaterial({ color: 0x8f99a4, transparent: true, opacity: 0.8 })
  );
  crown.add(parapet);

  // Lift machine room
  const mrSize = Math.min(w * 0.32, 6);
  const mr = new THREE.Mesh(
    new THREE.BoxGeometry(mrSize, Math.min(d * 0.34, 5), 2.4),
    new THREE.MeshStandardMaterial({ color: 0xcfd6dc, roughness: 0.55, metalness: 0.1 })
  );
  mr.position.set(-mrSize * 0.2, -Math.min(d * 0.34, 5) / 2, topZ + 0.5 + 1.2);
  mr.castShadow = true;
  crown.add(mr);

  // PV array (single tilted plate, keeping hero minimal)
  const pv = new THREE.Mesh(
    new THREE.BoxGeometry(Math.min(w * 0.4, 12), Math.min(d * 0.5, 8), 0.12),
    new THREE.MeshStandardMaterial({ color: 0x223052, roughness: 0.22, metalness: 0.75 })
  );
  pv.position.set(mrSize * 0.35, Math.min(d * 0.34, 5) / 2 + 0.8, topZ + 0.9);
  pv.rotation.z = 0; // PV sits flat-on-plane; tilt along the long axis
  pv.castShadow = true;
  crown.add(pv);

  group.add(crown);

  // Accent line on the hero parcel + a vertical tracker mark under the building
  const accentLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(cx, cy, 0.08),
      new THREE.Vector3(cx, cy, topZ + 1.0),
    ]),
    new THREE.LineBasicMaterial({ color: new THREE.Color(`rgb(${accent[0]},${accent[1]},${accent[2]})`), transparent: true, opacity: 0.55 })
  );
  group.add(accentLine);

  return { group, floors, floorMeshes, levels };
}