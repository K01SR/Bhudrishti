import type { FeatureCollection, Feature, Polygon, Point, LineString } from 'geojson';

export interface OSMBuildingProperties {
  _osm_id: number;
  name: string;
  building_type: string;
  height_m: number;
  floors_count: number;
  landuse?: string;
  amenity?: string;
  centroid: [number, number];
  source: 'OpenStreetMap Live';
  levels_derived: boolean;
}

const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://lz4.overpass-api.de/api/interpreter',
];

const cache = new Map<string, FeatureCollection<Polygon, OSMBuildingProperties>>();
// In-flight requests, so two callers asking for the same grid cell at the same
// time share one fetch. Without this the cache is only populated after the
// response lands, so concurrent callers each downloaded the full ~3MB payload
// (EsriSatelliteView and MapLibreCadastreMap both mount and request the same
// cell, which was measured as two identical 3,040KB responses).
const inflight = new Map<string, Promise<FeatureCollection<Polygon, OSMBuildingProperties>>>();

/**
 * Snaps bounding boxes to discrete spatial quad cells (~1.1km x 1.1km)
 * to ensure that small panning gestures hit the cache instantly with 0ms latency.
 */
export function snapBboxToGrid(bboxStr: string | [number, number, number, number], gridSize = 0.01): string {
  let s: number, w: number, n: number, e: number;
  if (Array.isArray(bboxStr)) {
    [s, w, n, e] = bboxStr;
  } else {
    const parts = bboxStr.split(',').map(Number);
    [s, w, n, e] = parts;
  }
  const snappedS = Math.floor(s / gridSize) * gridSize;
  const snappedW = Math.floor(w / gridSize) * gridSize;
  const snappedN = (Math.floor(n / gridSize) + 1) * gridSize;
  const snappedE = (Math.floor(e / gridSize) + 1) * gridSize;
  return `${snappedS.toFixed(3)},${snappedW.toFixed(3)},${snappedN.toFixed(3)},${snappedE.toFixed(3)}`;
}

export async function fetchOSMBuildings(bbox: string | [number, number, number, number]): Promise<FeatureCollection<Polygon, OSMBuildingProperties>> {
  const gridKey = snapBboxToGrid(bbox);
  const cached = cache.get(gridKey);
  if (cached) return cached;
  const pending = inflight.get(gridKey);
  if (pending) return pending;

  const req = loadOSMBuildings(gridKey).finally(() => inflight.delete(gridKey));
  inflight.set(gridKey, req);
  return req;
}

async function loadOSMBuildings(gridKey: string): Promise<FeatureCollection<Polygon, OSMBuildingProperties>> {
  // 1. Fast path: try the backend proxy, which owns the upstream rate limit.
  let proxyUnavailable = false;
  try {
    const proxyRes = await fetch(`/api/v1/osm/live-stream?bbox=${encodeURIComponent(gridKey)}`);
    if (proxyRes.status === 503) {
      // The backend already tried the upstream, hit its rate limit, and has no
      // cached copy. Asking Overpass from the browser here is what produced a
      // 2.4MB download and a 14s wait, so the cell is reported as unavailable
      // instead and the map shows the honest empty state.
      proxyUnavailable = true;
    }
    if (proxyRes.ok) {
      const data = await proxyRes.json();
      if (data?.buildings && data.buildings.length > 0) {
        const features = data.buildings.map((b: any) => ({
          type: 'Feature' as const,
          id: b.id,
          geometry: {
            type: 'Polygon' as const,
            coordinates: b.coordinates,
          },
          properties: {
            _osm_id: b.osm_id,
            name: b.name,
            building_type: b.landuse || 'structure',
            height_m: b.height_m,
            floors_count: b.floors_count,
            landuse: b.landuse,
            centroid: b.centroid,
            source: 'OpenStreetMap Live' as const,
            levels_derived: false,
          },
        }));
        const fc: FeatureCollection<Polygon, OSMBuildingProperties> = { type: 'FeatureCollection', features };
        cache.set(gridKey, fc);
        return fc;
      }
    }
  } catch (err) {
    // Backend proxy unreachable, proceed to client-side Overpass
  }

  if (proxyUnavailable) {
    const empty: FeatureCollection<Polygon, OSMBuildingProperties> = { type: 'FeatureCollection', features: [] };
    cache.set(gridKey, empty);
    return empty;
  }

  // 2. Direct Overpass query for buildings within snapped grid bounds
  const query = `
    [out:json][timeout:15];
    (
      way["building"](${gridKey});
      relation["building"](${gridKey});
    );
    out body geom;
  `;

  let lastError: Error | null = null;
  for (const endpoint of ENDPOINTS) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `data=${encodeURIComponent(query)}`,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} from ${endpoint}`);
      }

      const json = await response.json();
      const fc = parseOSMBuildings(json);
      cache.set(gridKey, fc);
      return fc;
    } catch (err: any) {
      lastError = err;
      // Continue to next endpoint fallback
    }
  }

  console.warn('All Overpass endpoints failed or timed out:', lastError?.message);
  return { type: 'FeatureCollection', features: [] };
}

function parseOSMBuildings(data: any): FeatureCollection<Polygon, OSMBuildingProperties> {
  const features: Feature<Polygon, OSMBuildingProperties>[] = [];

  if (!data?.elements || !Array.isArray(data.elements)) {
    return { type: 'FeatureCollection', features };
  }

  for (const el of data.elements) {
    if (el.type !== 'way' || !el.geometry || el.geometry.length < 3) continue;

    const coords = el.geometry.map((pt: any) => [pt.lon, pt.lat]);
    // Ensure ring is closed
    if (
      coords[0][0] !== coords[coords.length - 1][0] ||
      coords[0][1] !== coords[coords.length - 1][1]
    ) {
      coords.push([...coords[0]]);
    }
    if (coords.length < 4) continue;

    const tags = el.tags || {};
    let floors = parseInt(tags['building:levels'] || tags['levels'] || '0', 10);
    let height = parseFloat(tags['height'] || tags['building:height'] || '0');

    let levelsDerived = false;
    if (floors <= 0 && height > 0) {
      floors = Math.max(1, Math.round(height / 3.5));
      levelsDerived = true;
    } else if (floors > 0 && height <= 0) {
      height = floors * 3.5;
    } else if (floors <= 0 && height <= 0) {
      // Heuristic based on building type
      const bType = tags.building || 'yes';
      if (['apartments', 'commercial', 'office', 'hospital', 'hotel'].includes(bType)) {
        floors = 6;
        height = 21.0;
      } else if (['retail', 'supermarket', 'industrial', 'warehouse', 'school'].includes(bType)) {
        floors = 2;
        height = 7.0;
      } else {
        floors = 3;
        height = 10.5;
      }
      levelsDerived = true;
    }

    // Centroid approximate calculation
    let sumLon = 0;
    let sumLat = 0;
    for (const c of coords) {
      sumLon += c[0];
      sumLat += c[1];
    }
    const centerLon = sumLon / coords.length;
    const centerLat = sumLat / coords.length;

    features.push({
      type: 'Feature',
      id: `osm-${el.id}`,
      geometry: {
        type: 'Polygon',
        coordinates: [coords],
      },
      properties: {
        _osm_id: el.id,
        name: tags.name || tags['name:en'] || tags['addr:housename'] || `OSM Building #${el.id}`,
        building_type: tags.building || 'structure',
        height_m: Math.round(height * 10) / 10,
        floors_count: floors,
        landuse: tags.landuse,
        amenity: tags.amenity,
        centroid: [centerLon, centerLat],
        source: 'OpenStreetMap Live',
        levels_derived: levelsDerived,
      },
    });
  }

  return { type: 'FeatureCollection', features };
}

export interface OSMRoadProperties {
  highway: string | null;
  name: string | null;
  osm_id: number;
  source: 'OpenStreetMap Live';
}

const roadCache = new Map<string, FeatureCollection<LineString, OSMRoadProperties>>();

/**
 * Fetches road centrelines for a bbox.
 *
 * Separate from fetchOSMBuildings on purpose: the building query is tuned for
 * polygons and returns a lot of them, and asking one Overpass call to return
 * every building and every highway way in a dense cell is how you get a 429
 * from a public endpoint. Roads are also only needed by the underground
 * prototype, so they should not be paying for a building fetch's cache slot.
 */
export async function fetchOSMRoads(
  bbox: string | [number, number, number, number],
): Promise<FeatureCollection<LineString, OSMRoadProperties>> {
  const gridKey = snapBboxToGrid(bbox);
  if (roadCache.has(gridKey)) {
    return roadCache.get(gridKey)!;
  }

  const query = `
    [out:json][timeout:15];
    way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)$"](${gridKey});
    out body geom;
  `;

  // Ask the backend first. It is the only Open Data client now, so it holds
  // the shared quota and the 24h cache for this cell; the browser going
  // direct is what previously caused 406s for everyone.
  try {
    const res = await fetch(
      `/api/v1/osm/overpass?bbox=${encodeURIComponent(gridKey)}&layers=roads`,
    );
    if (res.ok) {
      const data = await res.json();
      const fc = parseOSMRoads(data);
      roadCache.set(gridKey, fc);
      return fc;
    }
    if (res.status === 503) {
      const empty: FeatureCollection<LineString, OSMRoadProperties> = { type: 'FeatureCollection', features: [] };
      roadCache.set(gridKey, empty);
      return empty;
    }
  } catch {
    // Backend unreachable; fall through to a direct query.
  }

  let lastError: Error | null = null;
  for (const endpoint of ENDPOINTS) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `data=${encodeURIComponent(query)}`,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} from ${endpoint}`);
      }

      const json = await response.json();
      const fc = parseOSMRoads(json);
      roadCache.set(gridKey, fc);
      return fc;
    } catch (err: any) {
      lastError = err;
      // Continue to next endpoint fallback
    }
  }

  console.warn('All Overpass endpoints failed for roads:', lastError?.message);
  return { type: 'FeatureCollection', features: [] };
}

function parseOSMRoads(data: any): FeatureCollection<LineString, OSMRoadProperties> {
  const features: Feature<LineString, OSMRoadProperties>[] = [];

  if (!data?.elements || !Array.isArray(data.elements)) {
    return { type: 'FeatureCollection', features };
  }

  for (const el of data.elements) {
    if (el.type !== 'way' || !el.geometry || el.geometry.length < 2) continue;

    const coords: [number, number][] = el.geometry.map((pt: any) => [pt.lon, pt.lat]);
    const tags = el.tags || {};

    features.push({
      type: 'Feature',
      id: `osm-way-${el.id}`,
      geometry: { type: 'LineString', coordinates: coords },
      properties: {
        highway: tags.highway || null,
        name: tags.name || tags['name:en'] || null,
        osm_id: el.id,
        source: 'OpenStreetMap Live',
      },
    });
  }

  return { type: 'FeatureCollection', features };
}

function parseLocalityLabels(data: any): FeatureCollection<Point, { name: string; place: string; rank: number }> {
  const features = (data.elements || [])
    .filter((e: any) => e.tags?.name)
    .map((e: any) => {
      const place = e.tags.place || 'locality';
      const rank = ['city'].includes(place) ? 4 : ['town', 'district'].includes(place) ? 3 : ['suburb', 'neighbourhood'].includes(place) ? 2 : 1;
      return {
        type: 'Feature' as const,
        id: `place-${e.id}`,
        geometry: {
          type: 'Point' as const,
          coordinates: [e.lon, e.lat],
        },
        properties: {
          name: e.tags.name,
          place,
          rank,
        },
      };
    });
  return { type: 'FeatureCollection', features };
}

export async function fetchLocalityLabels(bboxStr: string): Promise<FeatureCollection<Point, { name: string; place: string; rank: number }>> {
  const query = `
    [out:json][timeout:10];
    node["place"~"city|town|suburb|neighbourhood|quarter|district|locality"](${bboxStr});
    out body;
  `;

  try {
    const res = await fetch(
      `/api/v1/osm/overpass?bbox=${encodeURIComponent(snapBboxToGrid(bboxStr))}&layers=labels`,
    );
    if (res.ok) {
      const data = await res.json();
      return parseLocalityLabels(data);
    }
    if (res.status === 503) {
      return { type: 'FeatureCollection', features: [] };
    }
  } catch {
    // Backend unreachable; fall through to a direct query.
  }

  for (const endpoint of ENDPOINTS) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `data=${encodeURIComponent(query)}`,
      });
      if (!response.ok) continue;
      const data = await response.json();
      return parseLocalityLabels(data);
    } catch {
      // try next
    }
  }
  return { type: 'FeatureCollection', features: [] };
}

/* ------------------------------------------------------------------ *
 * Civic amenities
 * ------------------------------------------------------------------ */

export interface OSMAmenityProperties {
  name?: string;
  amenity?: string;
  amenity_class?: string;
}

export const AMENITY_GROUPS: Record<string, { label: string; color: [number, number, number] }> = {
  education: { label: 'Schools & colleges', color: [96, 165, 250] },
  healthcare: { label: 'Hospitals & clinics', color: [248, 113, 113] },
  transit: { label: 'Metro, rail & bus', color: [52, 211, 153] },
  worship: { label: 'Places of worship', color: [167, 139, 250] },
  civic: { label: 'Civic offices', color: [251, 191, 36] },
  park: { label: 'Parks & open space', color: [74, 222, 128] },
};

/**
 * Classifies an OSM tag set into one of AMENITY_GROUPS.
 *
 * Only a fixed allowlist of tags is mapped, so a point can never be given a
 * group this app has no colour or label for. Anything unrecognised is dropped
 * by the caller rather than being filed under a catch-all, because a
 * "Civic Amenities" layer that silently includes a dentist is worse than one
 * that admits it covers six categories.
 */
function classifyAmenity(tags: Record<string, string>): { key: string } | null {
  const amenity = tags.amenity;
  const shop = tags.shop;
  const railway = tags.railway;
  const publicTransport = tags.public_transport;
  const leisure = tags.leisure;

  if (amenity === 'school' || amenity === 'college' || amenity === 'university' || amenity === 'kindergarten') {
    return { key: 'education' };
  }
  if (amenity === 'hospital' || amenity === 'clinic' || amenity === 'doctors' || amenity === 'pharmacy') {
    return { key: 'healthcare' };
  }
  if (amenity === 'place_of_worship' || amenity === 'temple' || amenity === 'mosque' || amenity === 'church') {
    return { key: 'worship' };
  }
  if (amenity === 'townhall' || amenity === 'police' || amenity === 'post_office' || amenity === 'courthouse') {
    return { key: 'civic' };
  }
  if (railway === 'station' || railway === 'subway_entrance' || railway === 'platform' || publicTransport === 'station') {
    return { key: 'transit' };
  }
  if (leisure === 'park' || leisure === 'garden' || leisure === 'pitch' || leisure === 'playground') {
    return { key: 'park' };
  }
  if (shop) return null;
  return null;
}

/**
 * Fetches civic amenities in a bbox as point features.
 *
 * A single Overpass call covering every allowlisted category, rather than one
 * call per category: Overpass rate-limits by request, and six sequential calls
 * on every viewport change is what made this view feel slow. Nodes and ways
 * with an area are reduced to their centre so they can share one point layer.
 */
function parseCivicAmenities(data: any): FeatureCollection<Point, OSMAmenityProperties> {
  const features = (data.elements || [])
    .map((e: any) => {
      const tags = e.tags || {};
      const group = classifyAmenity(tags);
      if (!group) return null;
      // `out center` gives ways and relations a `center`; nodes are their
      // own point. An element with neither is dropped rather than placed at
      // [0, 0], which would put a point in the Gulf of Guinea.
      const lon = e.lon ?? e.center?.lon;
      const lat = e.lat ?? e.center?.lat;
      if (typeof lon !== 'number' || typeof lat !== 'number') return null;
      return {
        type: 'Feature' as const,
        id: `amenity-${e.type}-${e.id}`,
        geometry: { type: 'Point' as const, coordinates: [lon, lat] },
        properties: {
          name: tags.name || tags['name:en'] || '',
          amenity: tags.amenity || tags.railway || tags.leisure || tags.public_transport || '',
          amenity_class: group.key,
        },
      };
    })
    .filter(Boolean);
  return { type: 'FeatureCollection', features } as FeatureCollection<Point, OSMAmenityProperties>;
}

export async function fetchCivicAmenities(
  bboxStr: string,
): Promise<FeatureCollection<Point, OSMAmenityProperties>> {
  const query = `
    [out:json][timeout:25];
    (
      nwr["amenity"~"^(school|college|university|kindergarten|hospital|clinic|doctors|pharmacy|place_of_worship|temple|mosque|church|townhall|police|post_office|courthouse)$"](${bboxStr});
      nwr["railway"~"^(station|subway_entrance|platform)$"](${bboxStr});
      nwr["public_transport"="station"](${bboxStr});
      nwr["leisure"~"^(park|garden|pitch|playground)$"](${bboxStr});
    );
    out center tags;
  `;

  // Prefer the backend, which is the single Open Data client and caches this
  // cell for 24h. A direct query here competes with the backend for the same
  // per-host quota and is what made map views intermittently slow.
  try {
    const res = await fetch(
      `/api/v1/osm/overpass?bbox=${encodeURIComponent(snapBboxToGrid(bboxStr))}&layers=amenities`,
    );
    if (res.ok) {
      return parseCivicAmenities(await res.json());
    }
    if (res.status === 503) {
      return { type: 'FeatureCollection', features: [] };
    }
  } catch {
    // Backend unreachable; fall through to a direct query.
  }

  for (const endpoint of ENDPOINTS) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `data=${encodeURIComponent(query)}`,
      });
      if (!response.ok) continue;
      return parseCivicAmenities(await response.json());
    } catch {
      // try the next endpoint
    }
  }
  return { type: 'FeatureCollection', features: [] };
}
