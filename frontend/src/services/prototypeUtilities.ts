import type { Feature, FeatureCollection, LineString } from 'geojson';

/**
 * Prototype subsurface utility network, DERIVED FROM OSM ROAD GEOMETRY.
 *
 * Read this before using anything it returns. There is no utility data in this
 * project. Not a leak detection survey, not a municipal asset register, not a
 * GPR scan. What follows takes the shape of public roads and runs four
 * invented services alongside them so the underground mode has something to
 * draw, and every feature it emits is stamped `authoritative: false`.
 *
 * The reason this is spelled out in the module rather than only in the UI: the
 * previous version of this layer was two hardcoded two-point line segments at
 * literal coordinates, and the layer panel labelled it "Municipal GPR Survey".
 * A GPR survey is measured subsurface data from a real scan, so that label
 * told the user the app had instrument it did not have. The lines are still
 * synthetic -- that much is inherent to deriving from roads -- but now they are
 * synthetic on purpose, traceable to the OSM ways that shaped them, and cannot
 * be mistaken for a survey result. `UtilitiesNotAuthoritative` is the string
 * the UI is expected to show.
 */
export const UtilitiesNotAuthoritative =
  'PROTOTYPE-DERIVED from OpenStreetMap road geometry - not authoritative utility data. No leak-detection, GPR or municipal asset record was consulted.';

export type UtilityCategory = 'water' | 'sewer' | 'electricity' | 'telecom';

export interface PrototypeUtilityProperties {
  category: UtilityCategory;
  /** Metres below the surface. Invented. */
  depthM: number;
  /** Lateral offset from the road centreline, metres. Invented. */
  offsetM: number;
  /** The OSM way id this line was derived from, so the derivation is traceable. */
  derivedFromOsmWay: number;
  /** The road class it was derived from, for context only. */
  roadClass: string | null;
  provenance: 'PROTOTYPE-DERIVED';
  authoritative: false;
}

const CATEGORY_STYLE: Record<
  UtilityCategory,
  { color: [number, number, number]; offsetM: number; minDepth: number; maxDepth: number }
> = {
  water: { color: [56, 189, 248], offsetM: -4.5, minDepth: 1.2, maxDepth: 2.4 },
  sewer: { color: [74, 222, 128], offsetM: 4.5, minDepth: 2.2, maxDepth: 3.8 },
  electricity: { color: [250, 204, 21], offsetM: -2.0, minDepth: 0.6, maxDepth: 1.4 },
  telecom: { color: [192, 132, 252], offsetM: 2.0, minDepth: 1.5, maxDepth: 5.0 },
};

const CATEGORIES = Object.keys(CATEGORY_STYLE) as UtilityCategory[];

/**
 * Deterministic 32-bit hash. Used instead of Math.random on purpose: a random
 * depth would be reassigned on every re-render, so pipes would visibly twitch
 * each time the camera settled or a layer toggled. Hashing the OSM way id gives
 * a stable pseudo-random spread that survives re-renders and is reproducible
 * from the source data.
 */
function hash32(value: number): number {
  let h = value | 0;
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  h = h ^ (h >>> 16);
  return h >>> 0;
}

function unitInterval(seed: number): number {
  return hash32(seed) / 0x100000000;
}

/**
 * Offsets a lon/lat polyline sideways by `offsetM` metres.
 *
 * Offsetting in degrees is wrong by a factor of cos(latitude): at Mumbai's
 * latitude a degree of longitude is ~87% the ground length of a degree of
 * latitude, so a naive degree offset draws visibly lopsided lines away from
 * the road. The longitude delta is therefore divided by cos(lat) to get true
 * metres, then converted back.
 */
function offsetPolyline(
  coords: [number, number][],
  offsetM: number,
): [number, number][] {
  if (coords.length < 2) return coords;

  const out: [number, number][] = [];
  for (let i = 0; i < coords.length; i++) {
    const prev = coords[Math.max(0, i - 1)];
    const next = coords[Math.min(coords.length - 1, i + 1)];

    let dx = next[0] - prev[0];
    let dy = next[1] - prev[1];
    const len = Math.hypot(dx, dy);

    if (len < 1e-9) {
      // Degenerate segment (repeated point): carry the previous offset forward
      // rather than emitting NaN, which would drop the feature in deck.gl.
      out.push(out.length ? [out[out.length - 1][0], out[out.length - 1][1]] : [coords[i][0], coords[i][1]]);
      continue;
    }

    dx /= len;
    dy /= len;

    // Left-hand normal in degrees, corrected for longitude convergence.
    const latRad = (coords[i][1] * Math.PI) / 180;
    const mPerDegLat = 111_320;
    const mPerDegLon = Math.max(1, mPerDegLat * Math.cos(latRad));

    const nx = -dy;
    const ny = dx * (mPerDegLon / mPerDegLat);

    out.push([
      coords[i][0] + (nx * offsetM) / mPerDegLon,
      coords[i][1] + (ny * offsetM) / mPerDegLat,
    ]);
  }
  return out;
}

function osmWayId(feature: Feature<LineString>, index: number): number {
  const raw = feature.id;
  const parsed = typeof raw === 'number' ? raw : Number(String(raw).replace(/^osm-/, ''));
  return Number.isFinite(parsed) ? parsed : index + 1;
}

/**
 * Builds the prototype network from road geometry.
 *
 * Only the longest ways are used. Every road segment in a dense city produces
 * a line, and a few thousand two-point stubs is both unreadable and a deck.gl
 * cost for no visual gain; taking the longest ways per category keeps the
 * arterial-looking routes that read as a network.
 */
export function derivePrototypeUtilities(
  roads: FeatureCollection<LineString>,
  options: { maxFeatures?: number; minPoints?: number } = {},
): FeatureCollection<LineString, PrototypeUtilityProperties> {
  const { maxFeatures = 160, minPoints = 2 } = options;
  const features: Feature<LineString, PrototypeUtilityProperties>[] = [];

  const candidates: {
    coords: [number, number][];
    wayId: number;
    roadClass: string | null;
    length: number;
  }[] = [];

  roads.features.forEach((feature, index) => {
    if (feature.geometry?.type !== 'LineString') return;
    const coords = feature.geometry.coordinates.filter(
      (pt): pt is [number, number] => Array.isArray(pt) && pt.length >= 2,
    );
    if (coords.length < minPoints) return;

    let length = 0;
    for (let i = 1; i < coords.length; i++) {
      length += Math.hypot(coords[i][0] - coords[i - 1][0], coords[i][1] - coords[i - 1][1]);
    }
    if (length <= 0) return;

    candidates.push({
      coords,
      wayId: osmWayId(feature, index),
      roadClass: (feature.properties as any)?.highway ?? null,
      length,
    });
  });

  // Longest first, so the per-category quota is spent on the routes that read
  // as a network rather than on stubs.
  candidates.sort((a, b) => b.length - a.length);

  const perCategory = new Map<UtilityCategory, number>();
  for (const cat of CATEGORIES) perCategory.set(cat, 0);
  const quota = Math.ceil(maxFeatures / CATEGORIES.length);

  for (const candidate of candidates) {
    const seed = candidate.wayId;
    const category = CATEGORIES[hash32(seed) % CATEGORIES.length];
    if ((perCategory.get(category) ?? 0) >= quota) continue;

    const style = CATEGORY_STYLE[category];
    // A small per-way jitter keeps parallel runs of the same category from
    // stacking into one indistinguishable line.
    const jitter = (unitInterval(seed ^ 0x9e3779b9) - 0.5) * 0.8;
    const depthM =
      style.minDepth + unitInterval(seed ^ 0x85ebca6b) * (style.maxDepth - style.minDepth);

    const coords = offsetPolyline(candidate.coords, style.offsetM + jitter);
    if (coords.length < 2) continue;

    features.push({
      type: 'Feature',
      id: `proto-utility-${category}-${candidate.wayId}`,
      geometry: { type: 'LineString', coordinates: coords },
      properties: {
        category,
        depthM: Math.round(depthM * 10) / 10,
        offsetM: Math.round((style.offsetM + jitter) * 10) / 10,
        derivedFromOsmWay: candidate.wayId,
        roadClass: candidate.roadClass,
        provenance: 'PROTOTYPE-DERIVED',
        authoritative: false,
      },
    });

    perCategory.set(category, (perCategory.get(category) ?? 0) + 1);
    if (features.length >= maxFeatures) break;
  }

  return { type: 'FeatureCollection', features };
}

export function utilityColor(category: UtilityCategory): [number, number, number] {
  return CATEGORY_STYLE[category].color;
}
