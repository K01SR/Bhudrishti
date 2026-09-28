import * as THREE from 'three';
import { fabricBuilding, heightCapNear, pickHeight } from './fabric';

/**
 * Procedural, deterministic world fabric for Bhu-Drishti 3D.
 *
 * Builds a believable mid-rise Indian suburb (light, architectural, quiet)
 * around the real survey grid of Airoli Sector 8 — avenue hierarchy, block
 * grain, building massing with a restrained material palette, avenue trees,
 * parks, sidewalks. Grounded in the same XY coordinate space as the cadastral
 * parcels and the hero building so real parcels / footprints sit *inside* it.
 *
 * Everything lives in groups so callers can toggle layers (used by the app
 * map's layer controls).
 */

export interface WorldLayers {
  ground: THREE.Group;
  blocks: THREE.Group; // urban grain plates + building massing
  roads: THREE.Group; // asphalt + markings + sidewalks
  vegetation: THREE.Group; // avenue trees + parks
  terrainMesh: THREE.Mesh; // the actual ground plane (measure targets)
}

export interface WorldOptions {
  /** Overall terrain extents (world XY). */
  domain: { x0: number; y0: number; x1: number; y1: number };
  /** Rect kept clear of fabric (the hero block). Voids remain empty ground. */
  heroBlock?: { x0: number; y0: number; x1: number; y1: number };
  /** Extra buffer (m) cleared around heroBlock so B-17 is never crowded. */
  heroClearance?: number;
  /** Real cadastral parcel rects — building fabric avoids overlapping them. */
  parcelRects?: { x0: number; y0: number; x1: number; y1: number }[];
  /**
   * Fabric density. 'none' = ground + roads only (B-17 close-ups).
   * 'low' = far fabric kept below the hero height. 'standard' = mixed.
   */
  density?: 'none' | 'low' | 'standard';
  /** Hard cap on fabric building height (m). */
  maxHeight?: number;
  seed?: number;
  /** 'day' = light architectural canvas · 'dusk' = night district that sleeps
   *  until the emissive windows light. */
  mood?: 'day' | 'dusk';
}

interface Road {
  dir: 'v' | 'h';
  at: number;
  w: number;
  major: boolean;
}

/** Deterministic PRNG so the district looks identical across reloads. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const DISTRICT_DOMAIN = { x0: 40, y0: 70, x1: 300, y1: 260 };

// Hard grid: two avenues frame the hero corner; the rest is a quiet grid.
const ROADS: Road[] = [
  { dir: 'v', at: 140, w: 14, major: true },
  { dir: 'v', at: 180, w: 9, major: false },
  { dir: 'v', at: 100, w: 9, major: false },
  { dir: 'v', at: 220, w: 9, major: false },
  { dir: 'v', at: 260, w: 9, major: false },
  { dir: 'h', at: 165, w: 16, major: true },
  { dir: 'h', at: 140, w: 9, major: false },
  { dir: 'h', at: 115, w: 9, major: false },
  { dir: 'h', at: 195, w: 9, major: false },
  { dir: 'h', at: 235, w: 9, major: false },
];

const LEAF_TONES = [0x9fb9a8, 0x8fae9b, 0xa9c1ae, 0x96b3a4];
const DUSK_LEAF_TONES = [0x1d3040, 0x1a2c3b, 0x21404a, 0x1e313f];

export function buildWorld(scene: THREE.Scene, opts: WorldOptions): WorldLayers {
  const domain = opts.domain;
  const hero = opts.heroBlock ?? null;
  const parcelRects = opts.parcelRects ?? [];
  const density = opts.density ?? 'standard';
  const maxHeight = opts.maxHeight ?? 33;
  const dusk = opts.mood === 'dusk';
  const rng = mulberry32(opts.seed ?? 72613);

  // Union of rects that building fabric must not enter: real parcels + any
  // hero clearance buffer. B-17's approach must stay open in every scene.
  const protectedZones: { x0: number; y0: number; x1: number; y1: number }[] = [...parcelRects];
  if (hero) {
    const c = opts.heroClearance ?? 18;
    protectedZones.push({ x0: hero.x0 - c, y0: hero.y0 - c, x1: hero.x1 + c, y1: hero.y1 + c });
  }

  const ground = new THREE.Group();
  const roads = new THREE.Group();
  const blocks = new THREE.Group();
  const vegetation = new THREE.Group();

  // ---- 1 · Terrain ---------------------------------------------------------
  const gwide = domain.x1 - domain.x0 + 60;
  const gdeep = domain.y1 - domain.y0 + 60;
  const terrainGeo = new THREE.PlaneGeometry(gwide, gdeep, 56, 40);
  {
    const pos = terrainGeo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      pos.setZ(
        i,
        Math.sin(x * 0.045) * Math.cos(y * 0.05) * 0.38 + Math.sin((x + y) * 0.085) * 0.22 + Math.cos((x - y) * 0.03) * 0.12
      );
    }
    terrainGeo.computeVertexNormals();
  }
  const terrain = new THREE.Mesh(
    terrainGeo,
    new THREE.MeshStandardMaterial({ color: dusk ? 0x0b0d1c : 0xf4f2eb, roughness: 1, metalness: 0 })
  );
  terrain.position.set((domain.x0 + domain.x1) / 2, (domain.y0 + domain.y1) / 2, -0.02);
  terrain.receiveShadow = true;
  ground.add(terrain);

  // ---- 2 · Block bands ------------------------------------------------------
  const vRoads = ROADS.filter((r) => r.dir === 'v').sort((a, b) => a.at - b.at);
  const hRoads = ROADS.filter((r) => r.dir === 'h').sort((a, b) => a.at - b.at);
  const xs = [domain.x0, ...vRoads.map((r) => r.at), domain.x1];
  const ys = [domain.y0, ...hRoads.map((r) => r.at), domain.y1];

  const roadWidthAt = (dir: 'v' | 'h', at: number): number => {
    const m = ROADS.find((r) => r.dir === dir && r.at === at);
    return m ? m.w / 2 : 0;
  };

  interface Block {
    x0: number; y0: number; x1: number; y1: number;
  }
  const blocksOut: Block[] = [];
  for (let bi = 0; bi < xs.length - 1; bi++) {
    for (let bj = 0; bj < ys.length - 1; bj++) {
      const x0 = xs[bi], x1 = xs[bi + 1], y0 = ys[bj], y1 = ys[bj + 1];
      if (hero && x0 >= hero.x0 - 0.001 && x1 <= hero.x1 + 0.001 && y0 >= hero.y0 - 0.001 && y1 <= hero.y1 + 0.001) continue;
      blocksOut.push({ x0, y0, x1, y1 });
    }
  }

  // ---- 3 · Block grain plates + massing --------------------------------------
  const grassMat = new THREE.MeshStandardMaterial({ color: dusk ? 0x101527 : 0xecebe3, roughness: 1, metalness: 0 });
  const pavementMat = new THREE.MeshStandardMaterial({ color: dusk ? 0x141a30 : 0xe7e5dc, roughness: 1, metalness: 0 });

  // shared plate geometry cache (parks, yards and open ground)
  const plateGeoCache = new Map<string, THREE.PlaneGeometry>();

  const parkBlocks: Block[] = [];
  const massing: Block[] = [];

  blocksOut.forEach((b) => {
    // inset from surrounding roads
    const L = roadWidthAt('v', b.x0) || 0;
    const R = roadWidthAt('v', b.x1) || 0;
    const B = roadWidthAt('h', b.y0) || 0;
    const T = roadWidthAt('h', b.y1) || 0;
    const ix0 = b.x0 + L + 4;
    const ix1 = b.x1 - R - 4;
    const iy0 = b.y0 + B + 4;
    const iy1 = b.y1 - T - 4;
    const w = ix1 - ix0;
    const d = iy1 - iy0;
    if (w < 14 || d < 14) {
      // Thin strips between roads are real carriageway / yard space — pave
      // them so raw terrain never reads as an empty slab around the hero.
      if (density !== 'none' && w * d > 120) {
        const key = `pav${w.toFixed(1)}_${d.toFixed(1)}`;
        let plate = plateGeoCache.get(key);
        if (!plate) {
          plate = new THREE.PlaneGeometry(w, d);
          plateGeoCache.set(key, plate);
        }
        const pm = new THREE.Mesh(plate, pavementMat);
        pm.position.set((ix0 + ix1) / 2, (iy0 + iy1) / 2, 0.013);
        blocks.add(pm);
      }
      return;
    }

    // ground grain plate (skip entirely in 'none' density)
    if (density !== 'none') {
      const key = `${w.toFixed(1)}_${d.toFixed(1)}`;
      let plate = plateGeoCache.get(key);
      if (!plate) {
        plate = new THREE.PlaneGeometry(w, d);
        plateGeoCache.set(key, plate);
      }
      const pm = new THREE.Mesh(plate, grassMat);
      pm.position.set((ix0 + ix1) / 2, (iy0 + iy1) / 2, 0.012);
      blocks.add(pm);
    }

    // some blocks are parks / open yards — keep the plate, skip the fabric
    if (rng() < 0.16 && w * d > 500) {
      parkBlocks.push({ x0: ix0, y0: iy0, x1: ix1, y1: iy1 });
      return;
    }
    massing.push({ x0: ix0, y0: iy0, x1: ix1, y1: iy1 });
  });

  const overlapsProtected = (r: { x0: number; y0: number; x1: number; y1: number }): boolean => {
    for (const p of protectedZones) {
      if (r.x1 > p.x0 + 0.4 && r.x0 < p.x1 - 0.4 && r.y1 > p.y0 + 0.4 && r.y0 < p.y1 - 0.4) return true;
    }
    return false;
  };

  const addBuilding = (x0: number, y0: number, x1: number, y1: number) => {
    const w = x1 - x0;
    const d = y1 - y0;
    if (w < 6 || d < 6) return;
    if (overlapsProtected({ x0, y0, x1, y1 })) return;
    const ctx = { maxHeight, heroBlock: hero ?? undefined, heroClearance: opts.heroClearance, dusk };
    const cap = heightCapNear((x0 + x1) / 2, (y0 + y1) / 2, ctx);
    const h = pickHeight(rng, cap);
    fabricBuilding(blocks, { x0, y0, x1, y1 }, h, rng, ctx);
  };

  massing.forEach((blk) => {
    const w = blk.x1 - blk.x0;
    const d = blk.y1 - blk.y0;
    const area = w * d;
    if (area > 1500) {
      // two parcels along the longer axis
      if (w >= d) {
        const mid = (blk.x0 + blk.x1) / 2;
        addBuilding(blk.x0 + 2, blk.y0 + 2, mid - 1.5, blk.y1 - 2);
        addBuilding(mid + 1.5, blk.y0 + 2, blk.x1 - 2, blk.y1 - 2);
      } else {
        const mid = (blk.y0 + blk.y1) / 2;
        addBuilding(blk.x0 + 2, blk.y0 + 2, blk.x1 - 2, mid - 1.5);
        addBuilding(blk.x0 + 2, mid + 1.5, blk.x1 - 2, blk.y1 - 2);
      }
    } else {
      const inset = Math.min(3, w * 0.08, d * 0.08);
      addBuilding(blk.x0 + inset + 2, blk.y0 + inset + 2, blk.x1 - inset - 2, blk.y1 - inset - 2);
    }
  });

  // ---- 4 · Roads -----------------------------------------------------------
  const asphalt = new THREE.MeshStandardMaterial({ color: dusk ? 0x161a2c : 0xccccbf, roughness: 0.96, metalness: 0.02 });
  const curb = new THREE.MeshStandardMaterial({ color: dusk ? 0x232a42 : 0xdedcd2, roughness: 0.85, metalness: 0 });
  const dashMat = new THREE.LineBasicMaterial({ color: dusk ? 0xb9c0f0 : 0xf0eee2, transparent: true, opacity: dusk ? 0.45 : 0.85 });

  ROADS.forEach((r) => {
    const lenV = domain.y1 - domain.y0 + 2;
    const lenH = domain.x1 - domain.x0 + 2;
    const len = r.dir === 'v' ? lenV : lenH;
    const geo = new THREE.PlaneGeometry(r.dir === 'v' ? r.w : len, r.dir === 'v' ? len : r.w);
    const road = new THREE.Mesh(geo, asphalt);
    road.position.set(
      r.dir === 'v' ? r.at : (domain.x0 + domain.x1) / 2,
      r.dir === 'v' ? (domain.y0 + domain.y1) / 2 : r.at,
      0.03
    );
    road.receiveShadow = true;
    roads.add(road);

    if (r.major) {
      const dashLen = len - 8;
      const dm = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(
          r.dir === 'v'
            ? [new THREE.Vector3(r.at, (domain.y0 + domain.y1) / 2 - dashLen / 2, 0.06), new THREE.Vector3(r.at, (domain.y0 + domain.y1) / 2 + dashLen / 2, 0.06)]
            : [new THREE.Vector3((domain.x0 + domain.x1) / 2 - dashLen / 2, r.at, 0.06), new THREE.Vector3((domain.x0 + domain.x1) / 2 + dashLen / 2, r.at, 0.06)]
        ),
        dashMat
      );
      roads.add(dm);
    }

    // curb edge on both sides
    const curbGeo = new THREE.PlaneGeometry(r.dir === 'v' ? 0.7 : len, r.dir === 'v' ? len : 0.7);
    for (const sign of [-1, 1]) {
      const curbMesh = new THREE.Mesh(curbGeo, curb);
      curbMesh.position.set(
        r.dir === 'v' ? r.at + sign * (r.w / 2) : (domain.x0 + domain.x1) / 2,
        r.dir === 'v' ? (domain.y0 + domain.y1) / 2 : r.at + sign * (r.w / 2),
        0.045
      );
      roads.add(curbMesh);
    }

    // sidewalk along the two avenue edges that frame the hero corner
    if (r.dir === 'v' && r.at === 140) {
      const sw = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 26), curb);
      for (const s of [-1, 1]) {
        const m = sw.clone();
        m.position.set(r.at + s * (r.w / 2 + 1.2), 152.5, 0.05);
        roads.add(m);
      }
    }
    if (r.dir === 'h' && r.at === 165) {
      const sw = new THREE.Mesh(new THREE.PlaneGeometry(40, 2.4), curb);
      for (const s of [-1, 1]) {
        const m = sw.clone();
        m.position.set(160, r.at + s * (r.w / 2 + 1.2), 0.05);
        roads.add(m);
      }
    }
  });

  // ---- 5 · Vegetation -----------------------------------------------------
  const trunkGeo = new THREE.CylinderGeometry(0.16, 0.24, 3.2, 5);
  trunkGeo.rotateZ(Math.PI / 2); // align to map frame (x/y ground)
  const canopyGeo = new THREE.IcosahedronGeometry(2.3, 0);

  interface Tree { x: number; y: number; s: number }
  const trees: Tree[] = [];

  if (density !== 'none') {
    const avenue = ROADS.filter((r) => r.major);
  avenue.forEach((r) => {
    if (r.dir === 'v') {
      for (let y = domain.y0 + 4; y <= domain.y1 - 4; y += 9) {
        for (const s of [-1, 1]) {
          trees.push({ x: r.at + s * (r.w / 2 + 3.2), y: y + (rng() - 0.5) * 1.6, s: 0.85 + rng() * 0.4 });
        }
      }
    } else {
      for (let x = domain.x0 + 4; x <= domain.x1 - 4; x += 9) {
        for (const s of [-1, 1]) {
          trees.push({ x: x + (rng() - 0.5) * 1.6, y: r.at + s * (r.w / 2 + 3.2), s: 0.85 + rng() * 0.4 });
        }
      }
    }
  });

  parkBlocks.forEach((p) => {
    const n = 6 + Math.floor(rng() * 8);
    for (let i = 0; i < n; i++) {
      trees.push({ x: p.x0 + 3 + rng() * (p.x1 - p.x0 - 6), y: p.y0 + 3 + rng() * (p.y1 - p.y0 - 6), s: 0.9 + rng() * 0.55 });
    }
  });
  }

  if (trees.length) {
    const trunkMat = new THREE.MeshStandardMaterial({ color: dusk ? 0x221f24 : 0x8a7b63, roughness: 1 });
    const trunks = new THREE.InstancedMesh(trunkGeo, trunkMat, trees.length);
    const canopies = new THREE.InstancedMesh(canopyGeo, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9 }), trees.length);
    const m4 = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const e = new THREE.Euler();
    const s = new THREE.Vector3();
    const leaf = new THREE.Color();
    const grassTone = new THREE.Color(dusk ? 0x16283a : 0x8fae9b);
    const leafTones = dusk ? DUSK_LEAF_TONES : LEAF_TONES;
    trees.forEach((t, i) => {
      e.set(0, rng() * Math.PI, 0);
      q.setFromEuler(e);
      m4.compose(new THREE.Vector3(t.x, t.y, 3.2), q, s.set(1, 1, t.s));
      trunks.setMatrixAt(i, m4);
      m4.compose(new THREE.Vector3(t.x, t.y, 4.7 * t.s), q, s.set(t.s, t.s, t.s));
      canopies.setMatrixAt(i, m4);
      leaf.setHex(leafTones[i % leafTones.length]);
      leaf.lerp(grassTone, (rng() - 0.5) * 0.12);
      canopies.setColorAt(i, leaf);
    });
    trunks.instanceMatrix.needsUpdate = true;
    canopies.instanceMatrix.needsUpdate = true;
    vegetation.add(trunks, canopies);
  }

  scene.add(ground, roads, blocks, vegetation);
  return { ground, roads, blocks, vegetation, terrainMesh: terrain };
}