import * as THREE from 'three';

/** Outer ring of a GeoJSON polygon as [x,y][] pairs. */
export function outerRing(polygon: any): number[][] {
  const coords = polygon?.coordinates;
  if (!coords) return [];
  const ring = coords[0] || [];
  if (!Array.isArray(ring) || ring.length < 3) return [];
  return ring[0] === ring[ring.length - 1] ? ring.slice(0, -1) : ring;
}

/** Build a THREE.Shape from an [x,y][] ring (XY plane; Z is up downstream). */
export function shapeFromRing(ring: number[][]): THREE.Shape {
  const s = new THREE.Shape();
  ring.forEach(([x, y], i) => (i === 0 ? s.moveTo(x, y) : s.lineTo(x, y)));
  s.closePath();
  return s;
}

/** Centroid of a ring. */
export function centroid(ring: number[][]): [number, number] {
  const n = ring.length;
  if (!n) return [0, 0];
  return [ring.reduce((a, p) => a + p[0], 0) / n, ring.reduce((a, p) => a + p[1], 0) / n];
}

/** Bounds of a ring. */
export function ringBounds(ring: number[][]): { minX: number; maxX: number; minY: number; maxY: number } {
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

/** Read the current accent RGB from the CSS variable (space-separated r g b). */
export function accentRGB(): [number, number, number] {
  if (typeof document === 'undefined') return [20, 53, 195];
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '20 53 195';
  const parts = raw.split(/\s+/).map(Number);
  return [parts[0] || 20, parts[1] || 53, parts[2] || 195];
}

/** Split a THREE.Color into 0..255 components. */
export function colorTo255(c: THREE.Color): [number, number, number] {
  return [Math.round(c.r * 255), Math.round(c.g * 255), Math.round(c.b * 255)];
}