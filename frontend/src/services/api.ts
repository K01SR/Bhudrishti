const API_BASE = (import.meta as any).env?.VITE_API_URL || '/api/v1';

const SESSION_KEY = 'bhudrishti.session';

/**
 * Deadline for one API call, covering all of its retry attempts. Generous
 * enough for a cold open-data pull, short enough that a stalled provider
 * surfaces as an error the UI can show instead of an endless spinner.
 */
const REQUEST_TIMEOUT_MS = 60_000;

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

import {
  HeroProperty,
  EvidenceStream,
  ParcelSummary,
  SearchResponse,
  SearchMode,
  LiDARPointCloudData,
  RevenueRecoveryResponse,
  DemandNoticeResponse,
  BuyerShieldAuditResponse,
  SubsurfaceNetworkResponse,
  ClashTestResult,
  OsmStreetsResponse,
  OsmAmenitiesResponse,
  OsmGeodeticCoords,
  CivicDossier,
  BlockchainBlock,
  BlockchainVerification,
  BlockchainStats,
  BlockchainQrProof,
  BlockchainQrProofVerification,
  SpreadsheetExtrusionResponse,
} from '../types/cadastre';

/* HeroPropertyData was a hand-maintained second copy of HeroProperty that had
 * drifted. Two structurally-identical-looking copies of a large type is how a
 * nullable field quietly becomes non-nullable in one of them, so the canonical
 * type in types/cadastre.ts is the only one now. */
export type { HeroProperty };

/**
 * Turn a FastAPI error body into something a person can read.
 *
 * The not-found path answers with a structured explanation rather than a bare
 * string - an `explanation` sentence plus a `not_available` list saying exactly
 * which parts of the record are missing and why, and which endpoint to use
 * instead. `JSON.stringify` on that object threw all of it away and put a
 * minified blob in the error, which is what a user sees on a dead-end URL.
 *
 * So the human-readable fields are preferred, in the order the backend uses to
 * put them in descending order of usefulness, and the object is only stringified
 * as a last resort for shapes nobody anticipated.
 */
function describeDetail(body: unknown): string | null {
  const d = (body as { detail?: unknown })?.detail;
  if (typeof d === 'string') return d;
  if (!d || typeof d !== 'object') return null;

  const o = d as { explanation?: string; error?: string; not_available?: string[] };
  const parts: string[] = [];
  if (o.explanation) parts.push(o.explanation.trim());
  else if (o.error) parts.push(o.error.trim());

  // The list is the most useful thing on the page when someone is chasing a
  // property that does not resolve, so it is worth more than a bare error code.
  if (Array.isArray(o.not_available) && o.not_available.length) {
    parts.push('Not available for this identifier:');
    parts.push(o.not_available.map((x) => `  - ${x}`).join('\n'));
  }

  return parts.length ? parts.join('\n\n') : JSON.stringify(d);
}

export async function get<T>(path: string): Promise<T> {
  const res = await fetchWithRetry(`${API_BASE}${path}`, { method: 'GET', headers: authHeaders() });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = describeDetail(body) || detail;
    } catch { /* keep statusText */ }
    // See the note in post() below: the status rides on the error so callers
    // can branch on 401/403 versus 404 versus 5xx.
    const err = new Error(detail || `Request failed (${res.status})`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

async function fetchWithRetry(url: string, init: RequestInit, attempts = 3): Promise<Response> {
  const backoff = [0, 500, 1500];
  // A cold open-data pull can legitimately take the backend's whole 30s
  // budget, and retrying three times without a deadline stacks that into
  // minutes of un-cancellable waiting on an area the user has already moved
  // on from. One deadline covers all attempts of this call, so the total
  // wait is bounded at REQUEST_TIMEOUT_MS rather than attempts x that.
  const deadline = new AbortController();
  const timer = setTimeout(() => deadline.abort(), REQUEST_TIMEOUT_MS);
  // Honour a caller-supplied signal (e.g. component unmount) as well.
  const signal = init.signal
    ? AbortSignal.any([init.signal, deadline.signal])
    : deadline.signal;
  try {
    for (let i = 0; i < attempts; i += 1) {
      try {
        const res = await fetch(url, { ...init, signal });
        if (res.status < 500 || i === attempts - 1) return res;
      } catch (err) {
        // A caller-initiated cancellation must not be retried.
        if (init.signal?.aborted) throw err;
        if ((err as Error)?.name === 'AbortError') {
          throw new Error(`Request timed out after ${Math.round(REQUEST_TIMEOUT_MS / 1000)}s`);
        }
        if (i === attempts - 1) throw err;
      }
      await new Promise((r) => setTimeout(r, backoff[i] || 500));
    }
  } finally {
    clearTimeout(timer);
  }
  throw new Error(`Request failed after ${attempts} attempts`);
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const headers = { ...authHeaders(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) };
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = describeDetail(b) || detail;
    } catch { /* keep statusText */ }
    // The HTTP status is carried on the error rather than folded into the
    // message. Callers need to tell "you are signed out" (401) apart from "this
    // building code is not in the scenario" (404) and from a server fault (5xx);
    // those three need different responses from the UI, and only the status
    // distinguishes them. A bare Error made that impossible to branch on.
    const err = new Error(detail || `Request failed (${res.status})`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

export async function fetchHeroProperty(): Promise<HeroProperty> {
  return get('/properties/hero');
}

/** One unit at or below datum, as a lon/lat polygon ring. */
export interface SubgradeUnit {
  unit_number: string | null;
  unit_type: string | null;
  min_z: number | null;
  max_z: number | null;
  carpet_area_m2: number | null;
  footprint_geojson: { type: 'Polygon'; coordinates: number[][][] };
}

export interface SubgradeResponse {
  ulpin: string | null;
  datum: { wgs84_lat: number; wgs84_lon: number };
  subgrade_units: SubgradeUnit[];
  count: number;
  /** Carried so callers can label the geometry instead of implying it was surveyed. */
  provenance: { source: string | null; authoritative: boolean; is_synthetic: boolean };
  note: string | null;
}

/**
 * Sub-grade structure for the canonical pilot, in lon/lat.
 *
 * `count: 0` is a normal answer, not an error: a parcel with no sub-grade
 * record has nothing to draw and the caller must not infer a basement from
 * the floors above it.
 */
export async function fetchSubgrade(): Promise<SubgradeResponse> {
  return get<SubgradeResponse>('/properties/hero/subgrade');
}

export async function fetchParcelsGeoJSON() {
  return get('/parcels/geojson');
}

export async function fetchParcels(): Promise<ParcelSummary[]> {
  const data = await get<unknown>('/parcels/');
  return data as ParcelSummary[];
}

export async function fetchParcel(ulpin: string): Promise<ParcelSummary> {
  return get(`/parcels/${encodeURIComponent(ulpin)}`);
}

/**
 * What the server knows about an identifier the UI is holding.
 *
 * `identifier_valid` is a statement about syntax and `exists` about the
 * cadastral store; the server reports them separately on purpose, because a
 * correct check digit says nothing about whether a record was ever ingested.
 * `null` means "not applicable" - a bare parcel ULPIN has no syntax validator.
 */
export interface ResolvedIdentifier {
  identifier: string;
  identifier_valid: boolean | null;
  exists: boolean;
  parent_ulpin: string;
  route: string;
  parsed_components: { building_code: string | null; level_code: string | null; unit_code: string | null } | null;
  parcel: {
    ulpin: string;
    address: string | null;
    locality: string | null;
    status: string;
    data_provenance: string;
    provenance_authoritative: boolean;
    geometry_present: boolean;
  } | null;
  structure: { building_code: string; name: string; structure_type: string } | null;
  level: { level_code: string; floor_number: number; level_type: string } | null;
  unit: { unit_number: string; proposed_3d_id: string; unit_type: string; carpet_area_m2: number } | null;
  unit_exists: boolean | null;
  unresolved: { building_code: string | null; reason: string } | null;
}

/**
 * Resolve a bare parcel ULPIN, a canonical 3D ID (`ULPIN/UB17-L05-501-W`), or
 * a precinct building code to a record and a route.
 *
 * The 3D form is why this exists: its `/` is a path separator, so
 * `/parcels/{ulpin}` cannot address one and answers a bare "Not Found" with no
 * indication of what was wrong. A 404 from this call carries the same structured
 * reason as a parcel lookup, so callers should surface `detail.explanation`
 * rather than inventing a message.
 */
export async function resolveIdentifier(identifier: string): Promise<ResolvedIdentifier> {
  return get(`/ids/resolve?identifier=${encodeURIComponent(identifier)}`);
}

export async function fetchEvidenceStreams(): Promise<EvidenceStream[]> {
  const data = await get<unknown>('/evidence/');
  return data as EvidenceStream[];
}

export async function searchProperties(q: string, mode: SearchMode = 'all'): Promise<SearchResponse> {
  return get(`/search?q=${encodeURIComponent(q)}&mode=${mode}`);
}

export async function locateLgdVillage(villageCode: string): Promise<any> {
  return get(`/locations/lgd/villages/${encodeURIComponent(villageCode)}/locate`);
}

export async function fetchVerificationCases(): Promise<any[]> {
  const data = await get<unknown>('/verification/cases');
  return data as any[];
}

export async function decideVerificationCase(caseId: string, decision: string, notes: string): Promise<any> {
  return post(`/verification/cases/${encodeURIComponent(caseId)}/decide`, { decision, officer_notes: notes });
}

export async function askTheMap(query: string): Promise<any> {
  return post('/queries/ask', { query });
}

export async function processPropertyPipeline(): Promise<any> {
  return post('/submissions/process-property');
}

export async function fetchMetrics(): Promise<any> {
  return get('/metrics/');
}

export async function fetchJurisdictionSummary(): Promise<any> {
  return get('/jurisdictions/state-summary');
}

export async function fetchAuditEvents(): Promise<any[]> {
  const data = await get<unknown>('/audit/events');
  return data as any[];
}

export async function verifyAuditChain(): Promise<any> {
  return get('/audit/verify-chain');
}

export async function decode3DID(idString: string): Promise<any> {
  return get(`/ids/decode?id_string=${encodeURIComponent(idString)}`);
}

export async function generate3DID(payload: {
  parent_ulpin: string;
  type_code: string;
  building_code: string;
  level_code: string;
  unit_code: string;
}): Promise<any> {
  return post('/ids/generate', payload);
}

export async function fetchRulesCatalogue(): Promise<any[]> {
  const data = await get<unknown>('/validation/rules');
  return data as any[];
}

export async function fetchEvidenceStream(streamId: string): Promise<EvidenceStream> {
  return get(`/evidence/${encodeURIComponent(streamId)}`);
}

export async function resetHeroScenario(): Promise<any> {
  return post('/demo/reset');
}

export async function fetchLiDARPointCloud(buildingCode?: string): Promise<LiDARPointCloudData> {
  const q = buildingCode ? `?building_code=${encodeURIComponent(buildingCode)}` : '';
  return get(`/lidar/pointcloud${q}`);
}

export async function fetchLiDARBinary(buildingCode?: string): Promise<ArrayBuffer> {
  const q = buildingCode ? `?building_code=${encodeURIComponent(buildingCode)}` : '';
  const res = await fetch(`${API_BASE}/lidar/pointcloud/binary${q}`);
  if (!res.ok) throw new Error('Failed to fetch LiDAR data');
  return res.arrayBuffer();
}

// ---- Features 1-4: integrity, objections, QR ledger, department workspaces ---- //

export interface IntegrityFactor {
  key: string;
  label: string;
  status: 'PASS' | 'WARN' | 'FAIL' | 'INFO';
  weight: number;
  detail: string;
}

export interface IntegrityReport {
  ulpin: string;
  survey_number: string;
  has_3d_twin: boolean;
  score: number;
  band: 'GREEN' | 'AMBER' | 'RED';
  band_label: string;
  summary: string;
  factors: IntegrityFactor[];
  duplicate_flags: Array<{ key: string; severity: string; message: string }>;
  timeline?: Array<{ date: string; kind: string; title: string; detail: string }>;
  building_economics?: {
    building_code: string;
    floors_above_ground: number;
    basements: number;
    footprint_area_m2: number;
    total_built_up_area_m2: number;
    plot_area_m2: number;
    calculated_fsi: number;
    max_allowed_fsi: number;
    fsi_utilization_pct: number;
    roof_catchment_elevation_m: number;
    baseline_height_m: number;
    detected_delta_height_m: number;
    detected_extra_floors: number;
  };
}

export interface IntegrityOverview {
  total_parcels: number;
  twin_parcels: number;
  bands: { GREEN: number; AMBER: number; RED: number };
  average_score: number;
  parcels: Array<Pick<IntegrityReport, 'ulpin' | 'survey_number' | 'has_3d_twin' | 'score' | 'band' | 'band_label' | 'summary' | 'factors' | 'duplicate_flags'>>;
  critical_flags: Array<{ ulpin: string; severity: string; kind: string; message: string }>;
  duplicate_sweep_summary: any;
}

export interface ObjectionRecord {
  case_number: string;
  ulpin: string;
  category: string;
  description: string;
  contact_email_redacted: string;
  status: 'OPEN' | 'RESOLVED';
  department: string;
  assigned_role: string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  created_at: string;
  resolution?: string | null;
  resolved_at?: string | null;
}

export interface VerificationLedger {
  token: string;
  parcel_ulpin: string;
  record_version: string;
  status: string;
  ledger_status: string;
  total_verifications: number;
  first_verified_at: string;
  last_verified_at: string;
  stamps: Array<{ stamp: string; verified_at: string; channel: string; device: string; result: string }>;
  privacy_notice: string;
}

export async function fetchIntegrityOverview(): Promise<IntegrityOverview> {
  return get('/integrity/overview');
}

export async function fetchIntegrityReport(ulpin: string): Promise<IntegrityReport> {
  return get(`/integrity/properties/${encodeURIComponent(ulpin)}`);
}

export async function fetchIntegrityDuplicates(): Promise<any> {
  return get('/integrity/duplicates');
}

export async function fetchObjections(ulpin?: string, status?: string): Promise<ObjectionRecord[]> {
  const qs = new URLSearchParams();
  if (ulpin) qs.set('ulpin', ulpin);
  if (status) qs.set('status', status);
  const data = await get<unknown>(`/objections/${qs.toString() ? `?${qs.toString()}` : ''}`);
  return data as ObjectionRecord[];
}

export async function fetchObjectionDepartments(): Promise<Array<{ department: string; total: number; open: number; resolved: number; latest: string }>> {
  const data = await get<unknown>('/objections/departments');
  return data as any[];
}

export async function fileObjection(req: {
  ulpin: string;
  category: string;
  description: string;
  contact_email: string;
  priority: string;
}): Promise<ObjectionRecord> {
  return post('/objections/', req);
}

export async function resolveObjection(caseNumber: string, resolution: string, actor: string): Promise<ObjectionRecord> {
  return post(`/objections/${encodeURIComponent(caseNumber)}/resolve`, { resolution, actor });
}

export async function fetchVerificationLedger(token: string): Promise<VerificationLedger> {
  return get(`/qr/ledger/${encodeURIComponent(token)}`);
}

export async function fetchPrecinctBuildings(): Promise<any[]> {
  const data = await get<unknown>('/precinct/buildings');
  return data as any[];
}

export interface OpenAreaPayload {
  region: string;
  area: { lat: number; lon: number; radius_m: number };
  center_local: [number, number];
  source: string;
  fetched_at: string;
  from_cache?: boolean;
  // Set only when the place names came from a different provider than the
  // footprints, which is the common case: GlobalML is the densest footprint
  // source for India and supplies no names at all.
  label_source?: string | null;
  // Why an area is short of something it should have had, e.g. names dropped
  // because Overpass was throttling. The backend refuses to paper over these, so
  // the UI has to be able to pass them on.
  warnings?: string[];
  counts: { buildings: number; labels: number };
  buildings: Array<Record<string, any>>;
  labels: Array<{ name: string; kind: string; x: number; y: number; lat?: number; lon?: number; distance_m?: number }>;
}

export async function fetchOpenArea(
  lat: number,
  lon: number,
  radius = 500,
  maxBuildings = 220,
): Promise<OpenAreaPayload> {
  return get<OpenAreaPayload>(
    `/opendata/area?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius=${radius}&max_buildings=${maxBuildings}`,
  );
}

export async function refetchOpenArea(
  lat: number,
  lon: number,
  radius = 500,
  maxBuildings = 220,
): Promise<OpenAreaPayload> {
  return post<OpenAreaPayload>(
    `/opendata/fetch?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius=${radius}&max_buildings=${maxBuildings}`,
    undefined,
  );
}

export function areaLiDARULPIN(lat: number, lon: number, radius = 500): string {
  return `AREA-${lat}_${lon}_${radius}`;
}

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role_name: string;
  jurisdiction_id: string | null;
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface DemoAccount {
  role: string;
  username: string;
  full_name: string;
  description: string;
  password: string;
}

export async function loginRequest(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username, password });
  const res = await fetchWithRetry(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = describeDetail(b) || detail;
    } catch { /* keep statusText */ }
    throw new Error(detail || `Login failed (${res.status})`);
  }
  return res.json() as Promise<LoginResponse>;
}

export async function fetchDemoAccounts(): Promise<DemoAccount[]> {
  const data = await get<unknown>('/auth/demo-accounts');
  return data as DemoAccount[];
}

export interface LocationNode {
  code: string;
  name: string;
}

export interface ParcelLocation {
  state: string;
  state_code: string;
  district: string;
  district_code: string;
  taluka: string;
  taluka_code: string;
  village_ward: string;
  village_code: string;
  jurisdiction_code: string;
}

export async function fetchStates(): Promise<LocationNode[]> {
  return get('/locations/states');
}

export async function fetchDistricts(state: string): Promise<LocationNode[]> {
  return get(`/locations/states/${encodeURIComponent(state)}/districts`);
}

export async function fetchTalukas(state: string, district: string): Promise<LocationNode[]> {
  return get(`/locations/states/${encodeURIComponent(state)}/districts/${encodeURIComponent(district)}/talukas`);
}

export async function fetchVillages(state: string, district: string, taluka: string): Promise<LocationNode[]> {
  return get(`/locations/states/${encodeURIComponent(state)}/districts/${encodeURIComponent(district)}/talukas/${encodeURIComponent(taluka)}/villages`);
}

export interface ParcelListItem extends ParcelSummary {
  location: ParcelLocation;
  building: {
    code: string;
    name: string;
    floors: number;
    height_m: number;
    fsi: number;
    type: string;
    status: string;
    has_3d: boolean;
  } | null;
}

export async function fetchParcelsByLocation(opts: {
  state?: string;
  district?: string;
  taluka?: string;
  village?: string;
  q?: string;
  limit?: number;
}): Promise<ParcelListItem[]> {
  const params = new URLSearchParams();
  if (opts.state) params.set('state', opts.state);
  if (opts.district) params.set('district', opts.district);
  if (opts.taluka) params.set('taluka', opts.taluka);
  if (opts.village) params.set('village', opts.village);
  if (opts.q) params.set('q', opts.q);
  if (opts.limit) params.set('limit', String(opts.limit));
  return get(`/parcels/?${params.toString()}`);
}

export async function fetchPrecinctHeatmap(mode: string): Promise<any> {
  return get(`/precinct/heatmap/${mode}`);
}

export async function fetchPrecinctStats(): Promise<any> {
  return get('/precinct/stats');
}

export interface BuilderSubmission {
  id: string;
  project_name: string;
  parcel_ulpin: string;
  structure_code: string;
  submission_type: string;
  status: 'APPROVED' | 'UNDER_REVIEW' | 'REJECTED';
  submitted_on: string;
  fsi_proposed: number;
  floors_proposed: number;
  template_id?: string | null;
  asset_id?: string | null;
  remarks: string;
}

export interface BuilderSubmissionSummary {
  total: number;
  by_status: { APPROVED: number; UNDER_REVIEW: number; REJECTED: number };
  approval_rate_pct: number;
  submissions: BuilderSubmission[];
}

export async function fetchBuilderSubmissions(): Promise<BuilderSubmissionSummary> {
  return get('/builder/submissions/');
}

export async function fileBuilderSubmission(req: {
  project_name: string;
  parcel_ulpin: string;
  submission_type: string;
  fsi_proposed: number;
  floors_proposed: number;
  template_id?: string | null;
  asset_id?: string | null;
}): Promise<BuilderSubmission> {
  return post('/builder/submissions/', req);
}

/** A reviewer records a disposition. This is an internal attestation about the
 * working record, not a government certification; the reason is required. */
/**
 * Tamper-evident acceptance proof. `chained: false` means no audit row was
 * written, in which case the hash fields are absent and `reason` explains why.
 */
export interface BuilderAuditProof {
  chained: boolean;
  previous_hash?: string;
  hash?: string;
  event_type?: string;
  timestamp?: string;
  table?: string;
  reason?: string;
  ed25519_signature?: string | null;
  record_fingerprint?: string | null;
  signature_note?: string;
}

export interface BuilderDispositionResponse {
  submission_id: string;
  /** The submission's new status, e.g. `ACCEPTED_FOR_RECORD` or `REJECTED`. */
  record_status: string;
  record_basis: string;
  review?: {
    decision: string;
    verified_by: string;
    verified_at: string;
    reason: string;
    basis?: string;
  };
  review_history?: Array<Record<string, unknown>>;
  /** Result of copying the decision into Postgres. */
  persistence?: {
    persisted: boolean;
    table?: string;
    reason?: string;
    case_number?: string;
    decision_timestamp?: string;
  };
  /**
   * A prototype-computed identifier, or null. This is NOT a registry
   * allocation and confers no title -- see `identifier_authority` and
   * `ulpin_note` before presenting it as an identifier.
   */
  derived_ulpin?: string | null;
  derived_ulpin_status?: 'PROTOTYPE_DERIVED' | 'NOT_DERIVED' | null;
  /** Why derivation succeeded or failed. Always worth showing. */
  derivation_note?: string | null;
  /** e.g. `NOT_A_REGISTRY_ALLOCATION`. */
  identifier_authority?: string | null;
  audit_proof?: BuilderAuditProof | null;
  /** Plain-language caveat on the identifier. Worth rendering verbatim. */
  ulpin_note?: string;
}

export async function decideBuilderSubmission(
  submissionId: string,
  decision: 'ACCEPTED_FOR_RECORD' | 'REJECTED',
  reason: string
): Promise<BuilderDispositionResponse> {
  return post(`/builder/submissions/${encodeURIComponent(submissionId)}/disposition`, {
    decision,
    reason,
  });
}

export interface BuilderTemplate {
  id: string;
  name: string;
  kind: string;
  description: string;
  file_name: string;
  size_bytes: number;
  url: string;
}

export interface BuilderAsset {
  id: string;
  original_name: string;
  name: string;
  format?: string;
  size_bytes: number;
  status: string;
  uploaded_on: string;
  url: string;
}

export async function fetchBuilderTemplates(): Promise<BuilderTemplate[]> {
  return get('/builder/assets/templates');
}

export async function fetchBuilderAssets(): Promise<BuilderAsset[]> {
  return get('/builder/assets/');
}

export async function uploadBuilderAsset(file: File): Promise<BuilderAsset> {
  const body = new FormData();
  body.append('file', file);
  const res = await fetchWithRetry(`${API_BASE}/builder/assets/upload`, { method: 'POST', body });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = describeDetail(b) || detail;
    } catch { /* keep statusText */ }
    throw new Error(detail || `Upload failed (${res.status})`);
  }
  return res.json() as Promise<BuilderAsset>;
}

export interface Precinct3DBuilding {
  code: string;
  name: string;
  type: string;
  floors: number;
  height_m: number;
  parent_ulpin: string;
  building_3d_id?: string;
  status: string;
  units_count: number;
  units: Array<{
    unit_number: string;
    proposed_3d_id: string;
    level_code: string;
    unit_type: string;
    min_z: number;
    max_z: number;
    carpet_area_m2: number;
    built_up_area_m2: number;
  }>;
}

export interface Precinct3DCatalogue {
  specification: string;
  total_buildings: number;
  total_3d_ids: number;
  buildings: Precinct3DBuilding[];
}

export async function fetchPrecinct3DIDs(): Promise<Precinct3DCatalogue> {
  return get('/ids/precinct');
}

export async function fetchBuilding3DIDs(buildingCode: string): Promise<any> {
  return get(`/ids/building/${encodeURIComponent(buildingCode)}`);
}

export async function fetchRevenueRecovery(): Promise<RevenueRecoveryResponse> {
  return get('/precinct/revenue-recovery');
}

export async function generateDemandNotice(buildingCode: string, noticeType?: string): Promise<DemandNoticeResponse> {
  return post('/precinct/generate-demand-notice', {
    building_code: buildingCode,
    notice_type: noticeType || 'SEC_260_DEMOLITION',
  });
}

export async function fetchBuyerShieldVerify(target: string): Promise<BuyerShieldAuditResponse> {
  return get(`/precinct/buyer-shield/verify/${encodeURIComponent(target)}`);
}

export async function fetchSubsurfaceNetwork(): Promise<SubsurfaceNetworkResponse> {
  return get('/precinct/subsurface/network');
}

export async function runSubsurfaceClashTest(params: {
  x: number;
  y: number;
  depth_m: number;
  radius_m: number;
  work_type?: string;
}): Promise<ClashTestResult> {
  return post('/precinct/subsurface/clash-test', params);
}

export interface UnextrudedParcel {
  ulpin: string;
  survey_number: string;
  plot_area_m2: number;
  polygon_geojson: any;
  location: any;
  suggested_building_code: string;
  suggested_building_name: string;
  suggested_typology: string;
  suggested_floors: number;
  permissible_fsi: number;
  has_3d_twin: boolean;
}

export interface UnextrudedParcelsResponse {
  total_unextruded: number;
  parcels: UnextrudedParcel[];
  action: string;
}

export interface ExtrudeAllResponse {
  status: string;
  message: string;
  total_parcels_extruded: number;
  total_3d_ulpins_minted: number;
  buildings: Array<{
    code: string;
    name: string;
    parent_ulpin: string;
    building_3d_id: string;
    type: string;
    floors: number;
    height_m: number;
    units_count: number;
    fsi: number;
    fsi_status: string;
    units_sample: string[];
  }>;
  all_minted_3d_ids: string[];
  specification: string;
}

export async function fetchUnextrudedParcels(): Promise<UnextrudedParcelsResponse> {
  return get('/ids/unextruded-parcels');
}

export async function extrudeAll2DParcels(): Promise<ExtrudeAllResponse> {
  return post('/ids/extrude-all-2d');
}

export async function extrudeSingleParcel(ulpin: string, req?: {
  building_name?: string;
  building_code?: string;
  typology?: string;
  floors?: number;
  units_per_floor?: number;
}): Promise<any> {
  return post(`/ids/extrude-parcel/${encodeURIComponent(ulpin)}`, req);
}

export interface DetailedBuilderFloorLabel {
  level_code: string;
  /** Display name for the level, persisted to the structure's levels. */
  name?: string;
  /** Use, e.g. Commercial/Residential. Persisted to the structure's levels. */
  use?: string;
}

export interface DetailedBuilderSubmissionRequest {
  project_name: string;
  parcel_ulpin: string;
  /** Residential address for the parcel, persisted when a footprint is drawn. */
  address?: string;
  /** Locality, persisted when a footprint is drawn. */
  locality?: string;
  /** Building footprint in local metres [[x, y], ...]. Builder-asserted, not surveyed. */
  footprint_ring?: Array<[number, number]>;
  /** One level per floor. Persisted as real level rows when a footprint is drawn. */
  floor_labels?: DetailedBuilderFloorLabel[];
  /** Quoted by the submitter. Not verified: no registry is reachable from here. */
  builder_rera_id?: string;
  municipal_sanction_no?: string;
  commencement_cert_date?: string;
  building_typology?: string;
  structure_code?: string;
  floors_above_ground?: number;
  basements_count?: number;
  plinth_height_m?: number;
  floor_to_floor_height_m?: number;
  total_height_m?: number;
  fsi_proposed?: number;
  setback_front_m?: number;
  setback_rear_m?: number;
  setback_side_north_m?: number;
  setback_side_south_m?: number;
  subsurface_depth_m?: number;
  sewer_invert_depth_m?: number;
  stormwater_tank_m3?: number;
  rooftop_solar_capacity_kw?: number;
  units?: any[];
}

export interface DetailedBuilderSubmissionResponse {
  submission_id: string;
  /** A submission is never approved at intake. It arrives pending a reviewer. */
  record_status: 'PENDING_REVIEW' | 'ACCEPTED_FOR_RECORD' | 'REJECTED';
  /** What acceptance would mean, carried on every response so it cannot be cropped. */
  record_basis: string;
  declared_by_submitter_not_verified: {
    rera_id: string | null;
    municipal_sanction_no: string | null;
    commencement_cert_date: string | null;
    parent_ulpin: string;
    note: string;
  };
  advisory_threshold_findings: {
    all_thresholds_met: boolean;
    checks: Array<{
      check: string;
      label: string;
      threshold: string;
      provided: string;
      met: boolean;
    }>;
    note: string;
  };
  spatial_massing: {
    total_height_m: number;
    floors_above_ground: number;
    basements_count: number;
    fsi_proposed: number;
  };
  minted_3d_ulpins: {
    total_minted: number;
    identifier_note: string;
    units: Array<{
      unit_number: string;
      level_code: string;
      unit_type: string;
      proposed_3d_id: string;
      /** Null when a footprint was drawn: no area is asserted for a level. */
      carpet_area_m2: number | null;
    }>;
  };
  /** Present only when a footprint was drawn: the geometry was persisted and
   * is labelled builder-asserted, not surveyed. */
  asserted_geometry?: {
    basis: string;
    note: string;
    persistence: {
      persisted: boolean;
      table?: string;
      reason?: string;
    };
    structure_code: string;
    footprint_vertex_count: number;
  };
  remarks: string;
}

export async function fileDetailedBuilderSubmission(
  req: DetailedBuilderSubmissionRequest
): Promise<DetailedBuilderSubmissionResponse> {
  return post('/builder/submissions/detailed', req);
}

// ============================================================================
// OPENSTREETMAP & CIVIC INTELLIGENCE API CLIENT
// ============================================================================

export async function fetchOsmStreets(): Promise<OsmStreetsResponse> {
  return get<OsmStreetsResponse>('/osm/streets');
}

export async function fetchOsmAmenities(): Promise<OsmAmenitiesResponse> {
  return get<OsmAmenitiesResponse>('/osm/amenities');
}

export async function fetchCivicDossier(codeOrUlpin: string): Promise<CivicDossier> {
  return get<CivicDossier>(`/osm/civic-dossier/${encodeURIComponent(codeOrUlpin)}`);
}

export async function convertLocalToGeodetic(x: number, y: number, z: number = 0): Promise<OsmGeodeticCoords> {
  return get<OsmGeodeticCoords>(`/osm/coordinates/convert?x=${x}&y=${y}&z=${z}`);
}

// ============================================================================
// SOVEREIGN CADASTRAL BLOCKCHAIN & SMART CONTRACTS API CLIENT
// ============================================================================

export async function fetchBlockchainBlocks(): Promise<{ network: string; total_blocks: number; blocks: BlockchainBlock[] }> {
  return get('/blockchain/blocks');
}

export async function fetchBlockchainBlock(index: number): Promise<BlockchainBlock> {
  return get(`/blockchain/blocks/${index}`);
}

export async function verifyBlockchain(): Promise<BlockchainVerification> {
  return get('/blockchain/verify');
}

export async function fetchBlockchainStats(): Promise<BlockchainStats> {
  return get('/blockchain/stats');
}

export async function simulateBlockchainTamper(blockIndex: number = 5, field: string = 'consideration_inr', maliciousValue: any = 500000): Promise<any> {
  return post('/blockchain/tamper-simulate', {
    block_index: blockIndex,
    field,
    malicious_value: maliciousValue,
  });
}

export async function selfHealBlockchain(): Promise<any> {
  return post('/blockchain/self-heal', {});
}

export async function fetchBlockchainQrProof(identifier: string): Promise<BlockchainQrProof> {
  return get(`/blockchain/qr-proof/${encodeURIComponent(identifier)}`);
}

/**
 * Checks a scanned proof with the server: Merkle path and Ed25519 signature,
 * reported separately so a valid hash chain with no signature is visible as
 * such rather than collapsing into a single pass/fail.
 */
export async function verifyBlockchainQrProof(proof: BlockchainQrProof): Promise<BlockchainQrProofVerification> {
  return post('/blockchain/qr-proof/verify', proof as unknown as Record<string, unknown>);
}

export async function simulateSmartContract(contractType: string, params: Record<string, any> = {}): Promise<any> {
  return post('/blockchain/smart-contracts/simulate', {
    contract_type: contractType,
    ...params,
  });
}

// ============================================================================
// SPREADSHEET 3D ULPIN EXTRUSION & GOVERNMENT PDF/LATEX EXPORT CLIENT
// ============================================================================

export async function generate3dFromSpreadsheet(file: File): Promise<SpreadsheetExtrusionResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/ids/generate-from-spreadsheet`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to process spreadsheet' }));
    throw new Error(err.detail || 'Spreadsheet processing failed');
  }
  return res.json();
}

export const EXCEL_TEMPLATE_URL = `${API_BASE}/ids/template/excel`;
export const CSV_TEMPLATE_URL = `${API_BASE}/ids/template/csv`;
export const PROPERTY_CARD_PDF_URL = (ulpin: string) => `${API_BASE}/exports/pdf/property-card/${ulpin}`;
export const PROPERTY_CARD_LATEX_URL = (ulpin: string) => `${API_BASE}/exports/latex/property-card/${ulpin}`;

// ============================================================================
// NATIONAL THEMATIC LAYERS (Phase 5) & NATIONAL PARCELS/TWINS
// ============================================================================

export type VIZ_LEVEL = 'STATE' | 'DISTRICT' | 'TALUKA' | 'VILLAGE';

export interface NationalVizLayer {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: any;
    properties: Record<string, any>;
  }>;
}

export async function fetchVizLayer(
  layer: 'fsi' | 'density' | 'status',
  level: VIZ_LEVEL,
  jurisdictionCode?: string,
): Promise<NationalVizLayer> {
  const qs = jurisdictionCode ? `?jurisdiction_code=${encodeURIComponent(jurisdictionCode)}` : '';
  return get(`/viz/${layer}/${level}${qs}`);
}

export async function fetchNationalParcels(boundaryCode: string, limit = 100): Promise<any> {
  const url = `/ids/national-ulpin/parcels?boundary_code=${encodeURIComponent(boundaryCode)}&limit=${limit}&synthesize=true`;
  return get(url);
}

export async function fetchNationalTwin(ulpin: string): Promise<any> {
  return get(`/ids/national-twin/${encodeURIComponent(ulpin)}`);
}

export async function fetchTileMeta(): Promise<any> {
  return get('/tiles/meta');
}

export const MVT_TILE_URL = (z: number, x: number, y: number, layers: string[]) =>
  `${API_BASE}/tiles/${z}/${x}/${y}.pbf?layers=${encodeURIComponent(layers.join(','))}`;
export const CADASTRAL_EXCEL_URL = `${API_BASE}/exports/excel/cadastre`;
export const IFC_EXPORT_URL = (ulpin?: string) => `${API_BASE}/exports/ifc${ulpin ? `?ulpin=${encodeURIComponent(ulpin)}` : ''}`;

export async function fetchCanonicalSchema(): Promise<any> {
  return get('/properties/canonical-schema');
}

export async function fetchRightsColorModes(): Promise<any> {
  return get('/rights/color-modes');
}

export async function fetchEpochChanges(): Promise<any> {
  return get('/changes/compare');
}

export async function mineBlockchainBlock(validator: string = 'demo-local-process'): Promise<any> {
  return post(`/blockchain/blocks/mine?validator=${encodeURIComponent(validator)}`, {});
}

export async function fetchNationalUlpinSpec(): Promise<any> {
  return get('/ids/national-ulpin/spec');
}

export async function deriveNationalUlpin(req: { ring: number[][]; origin_easting?: number; origin_northing?: number; utm_zone?: number }): Promise<any> {
  return post('/ids/national-ulpin/derive', req);
}

export async function verifyNationalUlpin(req: { ring: number[][]; ulpin?: string; origin_easting?: number; origin_northing?: number; utm_zone?: number }): Promise<any> {
  return post('/ids/national-ulpin/verify', req);
}

export async function verifyStoredNationalParcel(ulpin: string): Promise<any> {
  return post(`/ids/national-ulpin/verify-parcel?ulpin=${encodeURIComponent(ulpin)}`, {});
}

export async function extrudeNationalParcelTwin(ulpin: string, customParams?: any): Promise<any> {
  return post(`/ids/national-twin/extrude-parcel/${encodeURIComponent(ulpin)}`, { custom_params: customParams });
}

export async function extrudeNationalBoundaryTwins(boundaryCode: string): Promise<any> {
  return post('/ids/national-twin/extrude-boundary', { boundary_code: boundaryCode });
}

export async function fetchNationalServicesStatus(): Promise<{ loaded: boolean; backend: string; counts: Record<string, number> }> {
  return get('/locations/services/national');
}

export async function fetchDbBoundariesGeojson(level: VIZ_LEVEL): Promise<any> {
  return get(`/locations/db/boundaries/geojson/${level}`);
}

export async function ingestManualFloorplanTrace(req: {
  unit_polygons: number[][][];
  parent_ulpin?: string;
  building_code?: string;
  level_code?: string;
  base_elevation_m?: number;
  floor_height_m?: number;
}): Promise<any> {
  return post('/evidence/floorplan/trace', req);
}

export async function ingestDxfFloorplan(file: File, params?: {
  parent_ulpin?: string;
  building_code?: string;
  level_code?: string;
  base_elevation_m?: number;
  floor_height_m?: number;
}): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  if (params?.parent_ulpin) formData.append('parent_ulpin', params.parent_ulpin);
  if (params?.building_code) formData.append('building_code', params.building_code);
  if (params?.level_code) formData.append('level_code', params.level_code);
  if (params?.base_elevation_m !== undefined) formData.append('base_elevation_m', String(params.base_elevation_m));
  if (params?.floor_height_m !== undefined) formData.append('floor_height_m', String(params.floor_height_m));

  const res = await fetch(`${API_BASE}/evidence/floorplan/dxf`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'DXF floor plan upload failed');
  }
  return res.json();
}


// --- Government source status -------------------------------------------------
//
// Reports what each configured source can answer, so no surface has to infer
// capability from a badge. `authoritative` here means an official publication of
// that specific thing: Bhuvan publishing footprints does not make it
// authoritative for parcel title. Treat a false there as load-bearing.

export interface SourceCapability {
  key: string;
  label: string;
  question: string;
  available: boolean;
  basis: string;
  source_id: string | null;
  authoritative: boolean;
}

export interface SourceDescriptor {
  id: string;
  label: string;
  publisher: string;
  kind: string;
  license: string;
  reference_url: string;
  configured: boolean;
  /** Names of unset variables only. Values are never returned by the API. */
  missing_configuration: string[];
  provides: string[];
  cannot_provide: string[];
  authoritative_for: string[];
  detail: string;
}

export interface SourceStatus {
  sources: SourceDescriptor[];
  capabilities: SourceCapability[];
  summary: {
    configured_sources: string[];
    available_capabilities: string[];
    unavailable_capabilities: string[];
    authoritative_cadastral_source: string | null;
    authoritative_cadastral_note: string;
    generated_data_policy: string;
  };
}

export async function fetchSourceStatus(): Promise<SourceStatus> {
  const data = await get<unknown>('/datasources/status');
  return data as SourceStatus;
}

// --- DILRMP alignment -----------------------------------------------------------
//
// Verified programme facts alongside a self-assessment. `not_held` is all nulls
// on purpose: it is the set of things this system is not, and a consumer
// checking those keys has to see them empty rather than find them absent.

export interface DilrmpAlignmentRow {
  area: string;
  capability: string;
  state: 'implemented' | 'partial' | 'not_implemented' | 'out_of_scope';
  evidence: string;
  limitation: string;
}

export interface DilrmpAlignment {
  programme: {
    programme: string;
    publisher: string;
    source_url: string;
    verified_on: string;
    verification_method: string;
    period: string;
    outlay_inr_crore: number;
    guidelines_launched: string;
  };
  alignment_kind: string;
  disclaimer: string;
  not_held: Record<string, string | null>;
  component_mapping: { verified: boolean; reason: string };
  rows: DilrmpAlignmentRow[];
  summary: { counts: Record<string, number>; total_rows: number; implemented_means: string };
}

export async function fetchDilrmpAlignment(): Promise<DilrmpAlignment> {
  const data = await get<unknown>('/dilrmp/alignment');
  return data as DilrmpAlignment;
}
