/**
 * Client for the ingestion desk — `POST /api/v1/ingest/*`.
 *
 * Kept out of `services/api.ts` on purpose. Those four endpoints are the only
 * place in the product where a user can hand the platform a file and get
 * geometry back, so they carry the project's provenance contract with them:
 * every response carries a `provenance` block and the UI is expected to render
 * it rather than summarising the payload as "imported". Keeping the contract,
 * the types and the transport in one file makes that obligation hard to skip.
 *
 * Mirrors the transport conventions of `services/api.ts` (session bearer token,
 * `describeDetail` error extraction, `status` carried on the error) so callers
 * handle a 401 from ingestion the same way they handle a 401 anywhere else.
 */

const API_BASE = (import.meta as any).env?.VITE_API_URL || '/api/v1';

const SESSION_KEY = 'bhudrishti.session';

/**
 * Every ingest route is behind `get_current_user_required`, so an anonymous
 * call answers 401. Reading the token here rather than threading it through the
 * component tree keeps the page's submit handlers to one line, and means a
 * session that expires between renders is still picked up.
 */
function authHeaders(): Record<string, string> {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem(SESSION_KEY) : null;
    if (!raw) return {};
    const { token } = JSON.parse(raw) as { token?: string };
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

/** FastAPI `detail` → a sentence a person can read. */
function describeDetail(body: unknown): string | null {
  const d = (body as { detail?: unknown })?.detail;
  if (typeof d === 'string') return d;
  if (!d || typeof d !== 'object') return null;
  const o = d as { explanation?: string; error?: string; msg?: string; message?: string };
  const text = o.explanation || o.error || o.message || o.msg;
  if (text) return String(text).trim();
  return JSON.stringify(d);
}

async function ingestError(res: Response, fallback: string): Promise<Error> {
  let detail = res.statusText || fallback;
  try {
    detail = describeDetail(await res.json()) || detail;
  } catch {
    /* non-JSON error body — keep the status text */
  }
  // The status rides on the error so the page can tell "signed out" (401) from
  // "your file was rejected" (422) from a server fault (5xx); those three need
  // different responses and only the status separates them.
  const err = new Error(detail || fallback) as Error & { status?: number };
  err.status = res.status;
  return err;
}

/**
 * What the server says about where a payload came from.
 *
 * This is the object the UI must not soften: `is_derived` true means the
 * geometry is a model output however real the uploaded file was, and
 * `provenance_note` is the backend's own caveat, quoted rather than replaced.
 */
export interface IngestProvenance {
  is_real: boolean;
  is_derived: boolean;
  source: string;
  derivation_method: string | null;
  confidence_tier: string;
  provenance_note: string;
  /** One-line summary of the standing, e.g. `DERIVED/MODELLED - ...`. */
  provenance: string;
  data_type: string;
  has_authentic_source: boolean;
}

export interface PointCloudIngestResponse {
  success: boolean;
  asset_id: string;
  dataset_id: string;
  file_name: string;
  file_sha256: string;
  size_bytes: number;
  format: string;
  /**
   * The pipeline's own output, or `{ error, derived, modelled }` when the
   * pipeline raised. The endpoint still answers 200 in that case, so a caller
   * that only checks `success` would present a failed run as a successful
   * ingest — `error` has to be rendered, not ignored.
   */
  result: Record<string, any> | null;
  provenance: IngestProvenance;
}

export interface GnssPointInput {
  lat: number;
  lon: number;
  elev?: number;
  name?: string;
}

export interface GnssIngestResponse {
  success: boolean;
  point_count: number;
  geometry_type: string;
  area_m2: number | null;
  perimeter_m: number | null;
  centroid: number[] | null;
  crs: string;
  provenance: IngestProvenance;
  computation_method: string;
  warning: string | null;
}

export interface RejectedFeature {
  index: number;
  reason: string;
  vertex?: number[];
}

export interface ParcelGeoJsonIngestResponse {
  success: boolean;
  feature_count: number;
  valid_count: number;
  /**
   * Features the validator threw away. Dropping these quietly would turn a
   * partial import into a silent data loss, so they are part of the contract
   * the page has to show.
   */
  rejected_features: RejectedFeature[];
  area_m2: number | null;
  provenance: IngestProvenance;
}

export interface DroneExifIngestResponse {
  success: boolean;
  file_name: string;
  has_gps: boolean;
  gps: { lat?: number; lon?: number; altitude_m?: number } | null;
  capture_time: string | null;
  camera: Record<string, any> | null;
  sensor: Record<string, any> | null;
  exif_keys_count: number;
  provenance: IngestProvenance;
}

/** LAS/LAZ/COPC/CSV/TXT. The server rejects anything else with a 422. */
export const POINT_CLOUD_ACCEPT = '.las,.laz,.copc,.csv,.txt';
/** JPEG/TIFF/PNG. EXIF is read from the file; the pixels are not processed. */
export const DRONE_IMAGE_ACCEPT = '.jpg,.jpeg,.tiff,.tif,.png';

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await ingestError(res, 'Ingest request failed');
  return res.json() as Promise<T>;
}

/**
 * No `Content-Type` here on purpose: the browser has to set it with the
 * multipart boundary, and setting it by hand produces a body the server cannot
 * parse.
 */
async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { ...authHeaders() },
    body: form,
  });
  if (!res.ok) throw await ingestError(res, 'Upload failed');
  return res.json() as Promise<T>;
}

export interface PointCloudIngestRequest {
  file: File;
  dataset_name?: string;
  submission_id?: string;
  ground_z?: number;
}

export async function ingestPointCloud(req: PointCloudIngestRequest): Promise<PointCloudIngestResponse> {
  const form = new FormData();
  form.append('file', req.file);
  if (req.dataset_name) form.append('dataset_name', req.dataset_name);
  if (req.submission_id) form.append('submission_id', req.submission_id);
  if (req.ground_z !== undefined && Number.isFinite(req.ground_z)) {
    form.append('ground_z', String(req.ground_z));
  }
  return postForm<PointCloudIngestResponse>('/ingest/point-cloud', form);
}

export interface GnssIngestRequest {
  points: GnssPointInput[];
  submission_id?: string;
  description?: string;
}

export async function ingestGnss(req: GnssIngestRequest): Promise<GnssIngestResponse> {
  return postJson<GnssIngestResponse>('/ingest/gnss', req);
}

export interface ParcelGeoJsonIngestRequest {
  geojson: Record<string, any>;
  submission_id?: string;
  /**
   * Only an authorised role may set this, and setting it is an assertion about
   * the source's standing, not a fact the server can check. Defaults to false,
   * which is the honest default.
   */
  is_authoritative?: boolean;
  source?: string;
}

export async function ingestParcelGeoJson(
  req: ParcelGeoJsonIngestRequest
): Promise<ParcelGeoJsonIngestResponse> {
  return postJson<ParcelGeoJsonIngestResponse>('/ingest/parcel-geojson', req);
}

export async function ingestDroneExif(file: File): Promise<DroneExifIngestResponse> {
  const form = new FormData();
  form.append('file', file);
  return postForm<DroneExifIngestResponse>('/ingest/drone-exif', form);
}