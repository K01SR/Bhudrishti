import * as THREE from 'three';

/**
 * Procedural facade system — several distinct fenestration languages, painted
 * to canvas and wrapped onto box faces. Different languages collide to make
 * every building in the district distinguishable at a glance.
 *
 *   punched  — Indian residential punched window with reveals/sills/lintels
 *   ribbon   — commercial glass ribbon bands with spandrels + slim mullions
 *   curtain  — dark full-height curtain wall, fine grid
 *   brick    — warm brick row-house wall with small dense punched windows
 *   bands    — plaster mid-rise with a stringcourse band under each floor
 *   utility  — blind wall with sparse vents (plant rooms, stairs, roofs)
 *
 * Deterministic — identical output for identical input.
 */

export type FacadeKind = 'punched' | 'ribbon' | 'curtain' | 'brick' | 'bands' | 'utility';

export interface FacadeSpec {
  /** horizontal run of the face in metres */
  run: number;
  /** face height in metres (may cover several floors) */
  rise: number;
  kind?: FacadeKind;
  /** wall base colour, e.g. '#e6e3da' */
  wall?: string;
  /** stringcourse / band colour for 'bands' & spandrels */
  band?: string;
  /** accent colour (window reveal lining on the podium band only) */
  accent?: THREE.Color;
  /** dusk palette — deep indigo plaster, cool glass read for night scenes. */
  dusk?: boolean;
}

const PX_PER_M = 6;

interface WinOpts {
  wall: string;
  reveal: string;
  glassLo: string;
  glassHi: string;
  sill: string;
  accent?: string | null;
}

function drawWin(c: CanvasRenderingContext2D, x0: number, y0: number, w: number, h: number, o: WinOpts): void {
  c.fillStyle = o.reveal;
  c.fillRect(x0 - 2, y0 - 2, w + 4, h + 4);
  const g = c.createLinearGradient(x0, y0, x0 + w, y0);
  g.addColorStop(0, o.glassHi);
  g.addColorStop(1, o.glassLo);
  c.fillStyle = g;
  c.fillRect(x0, y0, w, h);
  c.fillStyle = o.reveal;
  c.fillRect(x0 + w / 2 - 1.5, y0, 3, h);
  c.fillStyle = o.sill;
  c.fillRect(x0 - 4, y0 + h - 2, w + 8, 3);
  c.fillRect(x0 - 4, y0 - 4, w + 8, 3);
  if (o.accent) {
    c.fillStyle = o.accent;
    c.fillRect(x0 + 1, y0 + 1, 6, h - 2);
  }
}

function drawBands(c: CanvasRenderingContext2D, run: number, rise: number, pxPerCol: number, pxPerRow: number, band: string, _wall: string): void {
  const cols = Math.max(2, Math.floor(run / 6));
  const rows = Math.max(1, Math.floor(rise / 3));
  for (let j = 0; j < rows; j++) {
    const yb = j * 3 * PX_PER_M;
    const bh = Math.max(3, 2 * PX_PER_M * 0.34);
    c.fillStyle = band;
    c.fillRect(0, yb, run * PX_PER_M, bh);
    c.fillStyle = 'rgba(255,255,255,0.06)';
    c.fillRect(0, yb + bh, run * PX_PER_M, 2);
  }
  void cols; void pxPerCol; void pxPerRow;
}

function makeCanvasTexture(canvas: HTMLCanvasElement): THREE.CanvasTexture {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  return tex;
}

/** Shared window-grid math so the emissive map lands on the same apertures
 *  as the base facade texture. */
function punchedGrid(run: number, rise: number, kind: FacadeKind) {
  const cols = Math.max(2, Math.min(14, Math.round(run / 2.6)));
  const rows = Math.max(1, Math.min(6, Math.round(rise / 2.7)));
  const pCols = kind === 'brick' ? Math.min(20, Math.round(cols * 1.5)) : cols;
  const pRows = kind === 'brick' ? Math.min(10, Math.round(rows * 1.4)) : rows;
  return {
    pCols,
    pRows,
    pColW: run / pCols,
    pRowH: rise / pRows,
    winW: (run / pCols) * (kind === 'brick' ? 0.58 : 0.64),
    winH: (rise / pRows) * (kind === 'brick' ? 0.6 : 0.66),
  };
}

/** Deterministic per-cell hash (lit-pattern seeding for the emissive map). */
function hash2(a: number, b: number): number {
  let h = (a * 73856093) ^ (b * 19349663);
  h = Math.imul(h ^ (h >>> 15), 2246822519);
  h ^= h >>> 17;
  return ((h >>> 0) % 1000) / 1000;
}

/** Emissive texture: the same window grid painted onto a black base so the
 *  facade's `emissiveMap` glows lit apertures only. Lit pattern is seeded by
 *  geometry, so it never flickers between reloads or faces. */
export function facadeEmissiveTexture(spec: FacadeSpec): THREE.CanvasTexture {
  const { run, rise } = spec;
  const kind: FacadeKind = spec.kind ?? 'punched';
  const cw = Math.min(1600, Math.max(128, Math.round(run * PX_PER_M)));
  const ch = Math.min(640, Math.max(96, Math.round(rise * PX_PER_M)));
  const canvas = document.createElement('canvas');
  canvas.width = cw;
  canvas.height = ch;
  const c = canvas.getContext('2d');
  if (!c) return makeCanvasTexture(canvas);

  const seedA = Math.floor(run * 3.7) + (kind.charCodeAt(0) << 5);

  if (kind === 'curtain') {
    const gcols = Math.max(3, Math.min(22, Math.round(run / 1.9)));
    const grows = Math.max(2, Math.min(18, Math.round(rise / 1.05)));
    const gw = cw / gcols;
    const gh = ch / grows;
    for (let i = 0; i < gcols; i++) {
      for (let j = 0; j < grows; j++) {
        const r = hash2(seedA + i, j);
        const a = 0.25 + r * 0.7;
        c.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
        c.fillRect(i * gw + gw * 0.06, j * gh + gh * 0.08, gw * 0.88, gh * 0.84);
      }
    }
  } else if (kind === 'ribbon') {
    const rows = Math.max(1, Math.min(6, Math.round(rise / 2.7)));
    const rowH = rise / rows;
    const bandH = Math.min(rowH * 0.62, rowH) * PX_PER_M;
    for (let j = 0; j < rows; j++) {
      const y0 = j * rowH * PX_PER_M;
      const r = hash2(seedA, j);
      const a = 0.2 + r * 0.65;
      c.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
      c.fillRect(0, y0, cw, bandH);
    }
  } else {
    const g = punchedGrid(run, rise, kind);
    const ceilCh = ch - 2;
    for (let i = 0; i < g.pCols; i++) {
      for (let j = 0; j < g.pRows; j++) {
        const wx = (i * g.pColW + (g.pColW - g.winW) / 2) * PX_PER_M;
        const wpx = g.winW * PX_PER_M;
        const hpx = g.winH * PX_PER_M;
        let wy = (j * g.pRowH + (g.pRowH - g.winH) / 2 + g.pRowH * 0.04) * PX_PER_M;
        if (wy + hpx > ceilCh) wy = ceilCh - hpx - 4;
        const r = hash2(seedA + i, j);
        // most residences dimly lit; a hash-weighted minority brighter
        let a = 0.18 + r * 0.5;
        if (r > 0.82) a = 0.7 + r * 0.3;
        c.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
        c.fillRect(wx, wy, wpx, hpx);
      }
    }
  }

  return makeCanvasTexture(canvas);
}

export function facadeTexture(spec: FacadeSpec): THREE.CanvasTexture {
  const { run, rise, dusk } = spec;
  const kind: FacadeKind = spec.kind ?? 'punched';
  const wall = spec.wall ?? (dusk ? '#22263a' : '#e6e3da');
  const band = spec.band ?? (dusk ? '#3a4568' : '#9aa09b');

  const rows = Math.max(1, Math.min(6, Math.round(rise / 2.7)));

  const cw = Math.min(1600, Math.max(128, Math.round(run * PX_PER_M)));
  const ch = Math.min(640, Math.max(96, Math.round(rise * PX_PER_M)));
  const canvas = document.createElement('canvas');
  canvas.width = cw;
  canvas.height = ch;
  const c = canvas.getContext('2d');
  if (!c) return makeCanvasTexture(canvas);

  c.fillStyle = wall;
  c.fillRect(0, 0, cw, ch);

  const rowH = rise / rows;
  const opts: WinOpts = dusk
    ? { wall, reveal: '#191d30', glassLo: '#131f3c', glassHi: '#244a86', sill: '#2c3352', accent: null }
    : { wall, reveal: '#c9cdcc', glassLo: '#9aa6b2', glassHi: '#b7c1cb', sill: '#d6dad6', accent: null };

  if (kind === 'curtain') {
    if (dusk) {
      const gcols = Math.max(3, Math.min(22, Math.round(run / 1.9)));
      const grows = Math.max(2, Math.min(18, Math.round(rise / 1.05)));
      const gw = cw / gcols;
      const gh = ch / grows;
      c.fillStyle = '#0f2033';
      c.fillRect(0, 0, cw, ch);
      for (let i = 0; i < gcols; i++) {
        for (let j = 0; j < grows; j++) {
          const px = i * gw + gw * 0.06;
          const py = j * gh + gh * 0.08;
          c.fillStyle = (i + j) % 2 ? '#152a42' : '#183150';
          c.fillRect(px, py, gw * 0.88, gh * 0.84);
        }
      }
    } else {
      // full-height dark glass grid with ultra-slim mullions
      const gcols = Math.max(3, Math.min(22, Math.round(run / 1.9)));
      const grows = Math.max(2, Math.min(18, Math.round(rise / 1.05)));
      const gw = cw / gcols;
      const gh = ch / grows;
      c.fillStyle = '#7f8c99';
      c.fillRect(0, 0, cw, ch);
      for (let i = 0; i < gcols; i++) {
        for (let j = 0; j < grows; j++) {
          const px = i * gw + gw * 0.06;
          const py = j * gh + gh * 0.08;
          c.fillStyle = (i + j) % 2 ? '#2b3742' : '#2e3b46';
          c.fillRect(px, py, gw * 0.88, gh * 0.84);
        }
      }
    }
  } else if (kind === 'ribbon') {
    // horizontal glass bands (shops/offices): band spans full width each floor
    for (let j = 0; j < rows; j++) {
      const y0 = j * rowH * PX_PER_M;
      const bandH = Math.min(rowH * 0.62, rowH) * PX_PER_M;
      c.fillStyle = dusk ? '#1b3352' : '#a9b4be';
      c.fillRect(0, y0, cw, bandH);
      c.fillStyle = dusk ? 'rgba(150,170,255,0.35)' : 'rgba(255,255,255,0.5)';
      c.fillRect(0, y0, cw, bandH * 0.12);
      c.fillStyle = band;
      c.fillRect(0, y0 + bandH + Math.max(1, PX_PER_M * 0.3), cw, Math.max(2, PX_PER_M * 0.42));
      c.fillStyle = dusk ? '#2a3a5e' : '#8e9aa5';
      const m2 = Math.max(2, Math.floor(run / 3));
      for (let m = 0; m <= m2; m++) {
        c.fillRect(Math.round((m / m2) * cw), y0, Math.max(2, PX_PER_M * 0.22), bandH);
      }
    }
  } else {
    // punched-family: brick variant uses denser, smaller openings & mortar hint
    const g = punchedGrid(run, rise, kind);
    const pCols = g.pCols;
    const pRows = g.pRows;
    const pColW = g.pColW;
    const pRowH = g.pRowH;
    const winW = g.winW;
    const winH = g.winH;

    if (kind === 'brick' && !dusk) {
      // brick texture base (day)
      c.fillStyle = wall;
      c.fillRect(0, 0, cw, ch);
      c.strokeStyle = 'rgba(0,0,0,0.07)';
      c.lineWidth = 1;
      const course = Math.max(5, PX_PER_M * 0.9);
      for (let y = 0; y < ch; y += course) {
        c.beginPath();
        c.moveTo(0, y);
        c.lineTo(cw, y);
        c.stroke();
        c.beginPath();
        for (let x = (y % (course * 2) ? 0 : course); x < cw; x += course * 2) {
          c.moveTo(x, y - course + 1);
          c.lineTo(x, y);
        }
        c.stroke();
      }
      opts.reveal = '#b7a891';
    } else if (kind === 'brick') {
      c.fillStyle = wall;
      c.fillRect(0, 0, cw, ch);
      c.strokeStyle = 'rgba(160,170,255,0.08)';
      c.lineWidth = 1;
      const course = Math.max(5, PX_PER_M * 0.9);
      for (let y = 0; y < ch; y += course) {
        c.beginPath();
        c.moveTo(0, y);
        c.lineTo(cw, y);
        c.stroke();
      }
      opts.reveal = '#5a4c3c';
    }

    for (let i = 0; i < pCols; i++) {
      for (let j = 0; j < pRows; j++) {
        const wx = (i * pColW + (pColW - winW) / 2) * PX_PER_M;
        let wy = (j * pRowH + (pRowH - winH) / 2 + pRowH * 0.04) * PX_PER_M;
        if (wy + winH * PX_PER_M > ch - 2) wy = ch - winH * PX_PER_M - 4;
        drawWin(c, wx, wy, winW * PX_PER_M, winH * PX_PER_M, opts);
      }
    }

    if (kind === 'bands') {
      drawBands(c, run, rise, 0, 0, band, wall);
    }
  }

  if (kind === 'utility') {
    c.fillStyle = wall;
    c.fillRect(0, 0, cw, ch);
    c.fillStyle = dusk ? '#2c3550' : '#aeb4b3';
    for (let i = 0; i < Math.max(2, Math.floor(run / 4)); i++) {
      for (let j = 0; j < Math.max(2, Math.floor(rise / 4)); j++) {
        c.fillRect((i / Math.max(1, Math.floor(run / 4)) * (cw - 40)) + 12, (j / Math.max(1, Math.floor(rise / 4)) * (ch - 40)) + 12, 18, 14);
      }
    }
  }

  // floor slab shadow along the top — the seam between stacked plates
  c.fillStyle = dusk ? 'rgba(10, 12, 24, 0.9)' : 'rgba(196, 200, 196, 0.9)';
  c.fillRect(0, 0, cw, 3);

  return makeCanvasTexture(canvas);
}

/** Roof / slab screed material shared across buildings in one scene. */
export function roofMaterial(dusk = false): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: dusk ? 0x1a1d2b : 0xd5d5cd,
    roughness: 0.95,
    metalness: 0.02,
  });
}

/** Wraps a facade texture into a physical material (rough plaster reads light).
 *  In dusk mode the matching emissive map is wired too, so the same apertures
 *  glow with `emissive` — walls stay dark, windows read lit. */
export function facadeMaterial(spec: FacadeSpec): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({
    map: facadeTexture(spec),
    roughness: spec.dusk ? 0.82 : 0.92,
    metalness: 0.03,
  });
  if (spec.dusk) {
    mat.emissive = new THREE.Color(0x6a77e8);
    mat.emissiveMap = facadeEmissiveTexture(spec);
    mat.emissiveIntensity = 1.15;
  }
  return mat;
}

/** Shared plinth / base plaster (darker, wider footing). */
export function plinthMaterial(wallHex?: string, dusk = false): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: wallHex ?? (dusk ? 0x22263a : 0xc7c4b8),
    roughness: 0.94,
    metalness: 0.03,
  });
}

/** Dark utility glass used for shop-fronts, stair over-runs, curtain pods. */
export function darkGlassMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: 0x34404c, roughness: 0.34, metalness: 0.3 });
}