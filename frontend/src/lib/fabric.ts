import * as THREE from 'three';
import { facadeMaterial, roofMaterial, plinthMaterial } from './facade';

/**
 * Believable urban fabrication — typological massing instead of single boxes.
 *
 * Each parcel gets one of four residential / commercial typologies:
 *
 *   slab      — quiet mid-rise slab, parapet edge, rooftop plant + tank
 *   tower     — two-storey podium with a recessed tower above, rooftop HVAC
 *   row       — attached shop/residential frontage, alternating ridge heights
 *   courtyard — U-shaped arms around a paved yard (large blocks only)
 *
 * Every mass shares the same structural language: a plinth base (terrazzo band),
 * facade-specific fenestration (see facade.ts), a parapet rim, and restrained
 * rooftop furniture. Windows never use toy geometry; all articulation comes from
 * material and proportion so the district stays quiet and architectural.
 *
 * Deterministic: consumes a single provided PRNG so two seeds = two cities.
 */

export type FabricTypology = 'slab' | 'tower' | 'row' | 'courtyard';

export interface FabricRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface FabricGlobals {
  /** hard ceiling on any single mass (m). */
  maxHeight: number;
  /** hero block rect — used for header-height grading so B-17 is never walled off. */
  heroBlock?: FabricRect;
  /** clearance buffer already reserved around the hero (m). */
  heroClearance?: number;
  accent?: THREE.Color;
  /** dusk palette — deep indigo plaster that sleeps until the emissive windows wake. */
  dusk?: boolean;
}

const WALL_TONES = ['#e6e3da', '#eceae0', '#e3e0d4', '#e8e5dc', '#dedbd2', '#e5e2d6', '#dfdbc8', '#e9e6dd'];
const DUSK_TONES = ['#242a41', '#262c46', '#21263d', '#2a3050', '#262b46', '#222741', '#282e47', '#232840'];
const KINDS: ('punched' | 'ribbon' | 'curtain' | 'brick' | 'bands')[] = ['punched', 'ribbon', 'brick', 'bands', 'curtain'];

const roofMats = new Map<boolean, THREE.MeshStandardMaterial>();
function roofMat(dusk: boolean): THREE.MeshStandardMaterial {
  let m = roofMats.get(dusk);
  if (!m) {
    m = roofMaterial(dusk);
    roofMats.set(dusk, m);
  }
  return m;
}

/** Height cap graded by proximity to the hero block — near = low, far = full. */
export function heightCapNear(cx: number, cy: number, globals: FabricGlobals): number {
  const h = globals.heroBlock;
  if (!h) return globals.maxHeight;
  const dx = Math.max(0, h.x0 - cx, cx - h.x1);
  const dy = Math.max(0, h.y0 - cy, cy - h.y1);
  const dist = Math.hypot(dx, dy) - (globals.heroClearance ?? 18);
  if (dist < 6) return 9;
  if (dist < 20) return 12;
  if (dist < 38) return 15;
  if (dist < 64) return 18;
  return globals.maxHeight;
}

/** Box in map frame (XY ground, Z up): Box(w,h,d) rotated about X by PI/2.
 *  Materials: [ +X, -X, top, bottom, +Y(→world -Y), -Y(→world +Y) ]. */
function addBox(
  group: THREE.Group,
  w: number,
  h: number,
  d: number,
  mats: THREE.Material[],
  cx: number,
  cy: number,
  cz: number,
  castShadow = true
): THREE.Mesh {
  const geo = new THREE.BoxGeometry(w, h, d);
  const m = new THREE.Mesh(geo, mats);
  m.rotation.x = Math.PI / 2;
  m.position.set(cx, cy, cz);
  m.castShadow = castShadow;
  group.add(m);
  return m;
}

function faceMats(wFace: number, dFace: number, rise: number, rng: () => number, dusk: boolean): THREE.Material[] {
  const k = KINDS[Math.floor(rng() * KINDS.length)];
  const tones = dusk ? DUSK_TONES : WALL_TONES;
  const wall = tones[Math.floor(rng() * tones.length)];
  const txX = facadeMaterial({ run: wFace, rise, kind: k, wall, dusk });
  const txY = facadeMaterial({ run: dFace, rise, kind: k, wall, dusk });
  return [txX, txX, roofMat(dusk), roofMat(dusk), txY, txY];
}

function rooftopPlant(group: THREE.Group, cx: number, cy: number, w: number, d: number, rng: () => number, dusk: boolean): void {
  if (rng() < 0.55) {
    const sz = 1.5 + rng() * 1.8;
    addBox(group, sz, 1.5 + rng() * 1.1, sz, [roofMat(dusk), roofMat(dusk), roofMat(dusk), roofMat(dusk), roofMat(dusk), roofMat(dusk)], cx + (w / 2 - 2.2) * (rng() < 0.5 ? -1 : 1) * 0.7, cy + (d / 2 - 2) * (rng() < 0.5 ? -1 : 1) * 0.6, 0);
  }
  if (rng() < 0.5) {
    const r = 0.7 + rng() * 0.7;
    const tank = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 1.1 + rng() * 0.8, 14), plinthMaterial(dusk ? '#262b44' : '#d8d4c8', dusk));
    tank.position.set(cx + (w / 2 - 2.6) * (rng() < 0.5 ? -1 : 1) * 0.8, cy + (d / 2 - 2.2) * (rng() < 0.5 ? -1 : 1) * 0.7, 0);
    group.add(tank);
  }
}

/** Benchmarks a height in metres and expected floor count for the picker. */
export function pickHeight(rng: () => number, maxFrom: number): number {
  const table: [number, number][] = [
    [9, 0.5], [12, 1], [15, 2], [18, 2.2], [21, 2.2], [24, 1.5], [27, 1], [30, 0.8],
  ];
  const usable = table.filter(([hh]) => hh <= maxFrom);
  const total = usable.reduce((a, [, w]) => a + w, 0);
  let rr = rng() * total;
  for (const [hh, w] of usable) {
    rr -= w;
    if (rr <= 0) return hh;
  }
  return usable[usable.length - 1][0];
}

/** Build one parcel's mass into `group`. Returns nothing; all kept internal. */
export function fabricBuilding(group: THREE.Group, rect: FabricRect, fullH: number, rng: () => number, globals: FabricGlobals): void {
  const w = rect.x1 - rect.x0;
  const d = rect.y1 - rect.y0;
  if (w < 6 || d < 6) return;
  const cx = (rect.x0 + rect.x1) / 2;
  const cy = (rect.y0 + rect.y1) / 2;
  const dusk = globals.dusk ?? false;

  const plinthH = Math.min(3.1, fullH * 0.22);
  const h = fullH;
  const plinthMat = plinthMaterial(dusk ? '#232842' : '#dfd9cc', dusk);
  const plinthArr = [plinthMat, plinthMat, roofMat(dusk), roofMat(dusk), plinthMat, plinthMat];

  // choose typology (rng first, deterministic)
  const typoRand = rng();
  let typo: FabricTypology;
  if (w * d > 3600 && w >= 30 && d >= 30) typo = 'courtyard';
  else if (w >= 26 || d >= 26) typo = typoRand < 0.4 ? 'row' : typoRand < 0.62 ? 'slab' : 'tower';
  else typo = typoRand < 0.42 ? 'slab' : typoRand < 0.74 ? 'tower' : 'row';

  // shared plinth apron
  addBox(group, w + 0.6, plinthH, d + 0.6, plinthArr, cx, cy, plinthH / 2, false);

  const parapet = (bx: number, by: number, bw: number, bd: number, cz: number) =>
    addBox(group, bw + 0.4, 0.5, bd + 0.4, [roofMat(dusk), roofMat(dusk), roofMat(dusk), roofMat(dusk), roofMat(dusk), roofMat(dusk)], bx, by, cz + 0.25, false);

  if (typo === 'slab') {
    const bw = w - 1.2;
    const bd = d - 1.2;
    const bh = h - plinthH;
    const mats = faceMats(bw, bd, bh, rng, dusk);
    addBox(group, bw, bh, bd, mats, cx, cy, plinthH + bh / 2);
    parapet(cx, cy, bw, bd, h);
    rooftopPlant(group, cx, cy, bw, bd, rng, dusk);
    return;
  }

  if (typo === 'tower') {
    const podiumH = Math.min(6.4, h * 0.3);
    const bw = w - 1.2;
    const bd = d - 1.2;
    const matsP = faceMats(bw, bd, podiumH, rng, dusk);
    addBox(group, bw, podiumH, bd, matsP, cx, cy, plinthH + podiumH / 2);
    const set = Math.min(2.4, w * 0.08);
    const tw = bw - set * 2;
    const td = bd - set * 2;
    const th = h - plinthH - podiumH - 0.8;
    if (th > 1) {
      const matsT = faceMats(tw, td, th, rng, dusk);
      const toff = w > d ? (rng() < 0.5 ? -1 : 1) * (bw - tw) / 2 : 0;
      const doff = w <= d ? (rng() < 0.5 ? -1 : 1) * (bd - td) / 2 : 0;
      addBox(group, tw, th, td, matsT, cx + toff, cy + doff, plinthH + podiumH + th / 2);
      parapet(cx + toff, cy + doff, tw, td, plinthH + podiumH + th);
      rooftopPlant(group, cx + toff, cy + doff, tw, td, rng, dusk);
    }
    return;
  }

  if (typo === 'row') {
    const alongW = w >= d;
    const n = 3;
    const unit = (alongW ? w : d) / n;
    const short = alongW ? d : w;
    const heights = [h, Math.min(h + 1.8, globals.maxHeight), h];
    for (let i = 0; i < n; i++) {
      const uh = heights[i];
      const p0 = i * unit;
      const p1 = (i + 1) * unit - (i === n - 1 ? 0 : 0.7);
      const uw = alongW ? p1 - p0 : short - 1.0;
      const ud = alongW ? short - 1.0 : p1 - p0;
      const ucx = alongW ? rect.x0 + (p0 + p1) / 2 : cx;
      const ucy = alongW ? cy : rect.y0 + (p0 + p1) / 2;
      const uhBody = uh - plinthH;
      const mats = faceMats(uw, ud, uhBody, rng, dusk);
      addBox(group, uw, uhBody, ud, mats, ucx, ucy, plinthH + uhBody / 2);
      parapet(ucx, ucy, uw, ud, uh);
    }
    rooftopPlant(group, cx, cy, w * 0.5, d * 0.5, rng, dusk);
    return;
  }

  // courtyard — U-shaped arms around a paved yard
  const arm = Math.min(w, d) * 0.28;
  const armH = h;
  const wall = Math.min(16, (w + d) * 0.32);
  const bwA = arm;
  const bdA = Math.max(6, d - 2 * arm);
  const matsA = faceMats(bwA, bdA, armH, rng, dusk);
  addBox(group, bwA - 0.8, armH, bdA - 0.8, matsA, cx - (w / 2 - arm / 2), cy, plinthH + armH / 2);
  addBox(group, bwA - 0.8, armH, bdA - 0.8, matsA, cx + (w / 2 - arm / 2), cy, plinthH + armH / 2);
  const bwB = Math.max(6, w - 2 * arm);
  const bdB = arm;
  const rearH = h * 0.8;
  const matsB = faceMats(bwB, bdB, rearH, rng, dusk);
  addBox(group, bwB - 0.8, rearH, bdB - 0.8, matsB, cx, cy + (d / 2 - arm / 2), plinthH + rearH / 2);
  void wall;
  rooftopPlant(group, cx, cy, w * 0.4, d * 0.4, rng, dusk);
}