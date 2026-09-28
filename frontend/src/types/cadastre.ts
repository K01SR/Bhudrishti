export interface PropertyMesh3D {
  vertices: number[];
  indices: number[];
  vertex_count: number;
  triangle_count: number;
}

export interface CadastralUnit {
  unit_number: string;
  proposed_3d_id: string;
  level_code: string;
  unit_type: string;
  min_z: number;
  max_z: number;
  carpet_area_m2: number;
  built_up_area_m2: number;
  volume_m3: number;
  mesh_3d?: PropertyMesh3D;
  center?: [number, number, number];
  rights?: Array<{
    right_type: string;
    party_name: string;
    party_type: string;
    share_pct?: number;
    encumbrance_status?: string;
    financial_institution?: string;
    mortgage_amount_inr?: number;
    easement_purpose?: string;
    color_hex?: string;
  }>;
}

export interface SubsurfaceObject {
  code: string;
  proposed_3d_id: string;
  type_code: string;
  description: string;
  min_z: number;
  max_z: number;
  has_clash: boolean;
  clash_details?: string;
  geometry_3d: {
    type: string;
    start: [number, number, number];
    end: [number, number, number];
    radius?: number;
  };
}

export interface ElevatedObject {
  code: string;
  proposed_3d_id: string;
  type_code: string;
  description: string;
  min_z: number;
  max_z: number;
  has_clash: boolean;
  geometry_3d: any;
}

/**
 * Shape the evidence API actually returns.
 *
 * This was previously typed with fields the API never sends (file_hash,
 * file_name, timestamp, version, status, provenance_kind), so the card rendered
 * eight blank cells and a green "all hashes SHA-256" badge over sources with no
 * hash at all. The three fields carrying the honest caveats below were in the
 * response the whole time and simply unused.
 */
export interface EvidenceStream {
  id: string;
  name: string;
  source_type: string;
  /** False for every stream in the current deployment: no source data exists. */
  available: boolean;
  format?: string;
  crs?: string;
  confidence_tier: string;
  /** Explicit statement of where this did or did not come from. */
  provenance: string;
  /** History of a claim that was previously overstated. */
  provenance_note?: string;
  quality_result?: string;
  /** What would have to arrive for this stream to carry real weight. */
  required_to_activate: string;
}

export interface TopologyIssue {
  rule_id: string;
  rule_name: string;
  severity: string;
  status: string;
  message: string;
  recommended_action?: string;
}

export interface ValidationSummary {
  total_rules: number;
  passed_rules: number;
  failed_rules: number;
  warning_rules: number;
  overall_status: string;
  findings: TopologyIssue[];
}

/**
 * Data-driven 3D scene specification produced by the backend Scene Architect
 * from persisted PostGIS records. The viewer renders EXCLUSIVELY from this
 * payload — no client-side hardcoded coordinates, anchors or clash points.
 */
export interface Scene3D {
  success: boolean;
  meta: {
    property_id: string;
    parent_ulpin: string;
    building_code: string;
    crs: string;
    engine: string;
    generated_at: string;
    center: [number, number];
    ground_z: number;
    roof_z: number;
  };
  parcel: {
    ulpin: string;
    survey_number: string;
    status: string;
    ring: number[][];
    area_m2: number;
    postgis_verified: boolean;
  };
  neighbors: Array<{
    ulpin: string;
    status: string;
    ring: number[][];
    area_m2: number;
  }>;
  structure: {
    building_code: string;
    name: string;
    footprint_ring: number[][];
    design_height_m: number;
    observed_height_m: number | null;
    extraction_source: string | null;
    floors_count: number;
    basements_count: number;
    ground_z: number;
    roof_z: number;
    has_postgis_3d_solid: boolean;
    total_built_up_area_m2: number;
  };
  levels: Array<{
    level_code: string;
    floor_number: number;
    level_type: string;
    min_z: number;
    max_z: number;
    height_m: number;
    solid: boolean;
  }>;
  units: SceneUnit[];
  subsurface_objects: SceneSubsurface[];
  clash: SceneClash;
  elevated_objects: SceneElevated[];
  architecture: SceneArchitecture;
  fsi: {
    plot_area_m2: number;
    total_built_up_area_m2: number;
    calculated_fsi: number;
    allowed_max_fsi: number;
    status: string;
    utilization_pct: number;
    from_pipeline: boolean;
    disclaimer?: string;
    jurisdiction?: string;
  };
  validation: ValidationSummary & { audit_hash?: string };
  provenance: any;
}

export interface SceneUnit {
  source: 'extracted' | 'design';
  unit_number: string;
  proposed_3d_id: string;
  level_code: string;
  unit_type: string;
  min_z: number;
  max_z: number;
  carpet_area_m2: number;
  built_up_area_m2: number;
  volume_m3: number;
  ring: number[][];
  mesh_3d: PropertyMesh3D;
  center: [number, number, number];
  has_postgis_solid?: boolean;
  rights?: CadastralUnit['rights'];
}

export interface SceneSubsurface {
  code: string;
  type_code: string;
  description: string;
  min_z: number;
  max_z: number;
  geometry_3d: {
    type: string;
    start: [number, number, number];
    end: [number, number, number];
    radius?: number;
    width?: number;
    height?: number;
  };
}

export interface SceneClash {
  has_clash: boolean;
  severity: string;
  rule_id: string;
  utility_code: string;
  clash_depth_z: number;
  penetration_length_m: number;
  clash_intersection_coords: number[][];
  message: string;
  recommended_action: string;
}

export interface SceneElevated {
  code: string;
  type_code: string;
  min_z: number;
  max_z: number;
  geometry_3d: any;
}

export interface SceneArchitecture {
  slabs: Array<{
    name: string;
    bounds: [number, number, number, number];
    z: number;
    thickness: number;
    level_code: string;
  }>;
  columns: Array<{
    id: string;
    x: number;
    y: number;
    min_z: number;
    max_z: number;
    size: [number, number];
  }>;
  central_core: { bounds: [number, number, number, number]; min_z: number; max_z: number };
  balconies: Array<{
    level_code: string;
    facade: string;
    z: number;
    railing_height: number;
    bounds: [number, number, number, number];
  }>;
  roof_crown: {
    parapet: { height: number; offset: number };
    lift_machine_room: {
      center: [number, number];
      size: [number, number, number];
      base_z: number;
    };
    solar_pv_array: {
      cols: number;
      rows: number;
      tilt_deg: number;
      base_z: number;
      bounds: [number, number, number, number];
    };
    water_tanks: Array<{
      code: string;
      position: [number, number];
      base_z: number;
      radius: number;
      height: number;
      color: string;
    }>;
  };
  foundation: {
    raft_slab: { bounds: [number, number, number, number]; z: number; thickness: number };
    piles: Array<{ id: string; x: number; y: number; top_z: number; bottom_z: number; radius: number }>;
    retaining_walls: { offset: number };
  };
}

export interface HeroProperty {
  property_id: string;
  parent_ulpin: string;
  /** Null when no registry allocation exists. Not invented from the ULPIN. */
  proposed_3d_id: string | null;
  record_version: string;
  /**
   * The record's own status. Never defaulted to APPROVED: a record with no
   * stated status is UNVERIFIED, and a submission nobody has reviewed must not
   * render as approved.
   */
  status: string;
  /**
   * Where the record sits, and how the position was obtained. A builder-drawn
   * or builder-typed position is asserted, not surveyed, and says so.
   */
  coordinates: {
    centroid_lat: number | null;
    centroid_lon: number | null;
    /** e.g. 'builder-drawn', 'survey', 'not-stated' */
    source: string;
    authoritative: boolean;
    note: string;
  };
  address: {
    line1: string | null;
    locality: string | null;
    village_ward: string | null;
    taluka: string | null;
    district: string | null;
    state: string | null;
    postal_code: string | null;
  };
  precinct: {
    name: string | null;
    state: string | null;
    district: string | null;
    taluka: string | null;
    /** Null rather than built by slicing state/district names. */
    code: string | null;
    /** Null when the record states no centre. */
    center: [number, number] | null;
    max_allowed_fsi: number | null;
  };
  parcel: {
    ulpin: string;
    survey_number: string | null;
    document_area_m2: number | null;
    calculated_area_m2: number | null;
    polygon_geojson: any;
  };
  structure: {
    building_code: string | null;
    name: string | null;
    height_m: number | null;
    floors_count: number | null;
    basements_count: number | null;
    total_built_up_area_m2: number | null;
    calculated_fsi: number | null;
    status: string;
    footprint_geojson: any;
    /** PENDING_REVIEW until a reviewer records a disposition. */
    verification_status: string;
    /** e.g. 'declared_by_submitter' | 'inferred_from_tags' | 'surveyed'. */
    geometry_basis: string | null;
    /** e.g. 'demo-generated' | 'openstreetmap'. */
    provenance: string | null;
    /** True only when a structure is actually marked verified. */
    is_verified: boolean | null;
  };
  /**
   * The live reviewer workflow state behind this structure, when a submission
   * row exists. Null otherwise; never synthesised from the parcel status.
   */
  builder_record: {
    receipt_number: string | null;
    status: string;
    declared_data: any;
    decision: string | null;
    reviewer_name: string | null;
    submitted_by: string | null;
    officer_notes: string | null;
    basis: string | null;
    decision_timestamp: string | null;
  } | null;
  /**
   * Per-floor records, exactly as the source stated them. A level with no name
   * has `name: null`; levels are never synthesised from a floor count, and a
   * named floor is never invented as "Ground Floor" or "Floor 1".
   */
  levels: Array<{
    level_code: string | null;
    floor_number: number | null;
    name: string | null;
    use: string | null;
    min_z: number | null;
    max_z: number | null;
    height_m: number | null;
    level_type: string | null;
    units_count?: number | null;
  }>;
  units: CadastralUnit[];
  subsurface_objects: SubsurfaceObject[];
  elevated_objects: ElevatedObject[];
  evidence_streams: EvidenceStream[];
  /** Null when no validation run is on record. Never derived from status. */
  validation: ValidationSummary | null;
  validation_note?: string;
  fsi: {
    plot_area_m2: number;
    built_up_area_m2: number;
    /** Null unless a permitted-FAR rule is on record for the jurisdiction. */
    calculated_fsi: number | null;
    /** Null unless a permitted-FAR rule is on record for the jurisdiction. */
    max_allowed_fsi: number | null;
    status: string;
  };
  /**
   * Null: this deployment signs nothing. A signature here would need a real key,
   * a real record to sign, and a real authority to attribute it to. A fixed hex
   * string is not a fingerprint and a constant is not a signature.
   */
  cryptographic_proof: {
    fingerprint_sha256: string;
    digital_signature_ed25519: string;
    /**
     * Null. The signature is made by this service with a published key, so no
     * authority signs the record and none can verify it. Kept as an explicit
     * null rather than omitted so a consumer can tell "no signer" from "this
     * endpoint has no opinion".
     */
    signer_authority: string | null;
    verification_status: string;
    public_qr_url: string;
    disclosure: {
      signature_algorithm: string;
      signature_validates: string;
      signature_does_not_validate: string;
      why: string;
      public_key_published: boolean;
      independent_auditor: string | null;
    };
  } | null;
  cryptographic_proof_note?: string;
  /**
   * Null unless two dated observations of the same structure were compared. A
   * delta against a "2026 Baseline" is a finding, and this deployment has no
   * baseline and no second observation.
   */
  epoch2_change: {
    epoch_from: string;
    epoch_to: string;
    delta_height_m: number;
    new_height_m: number;
    delta_floors: number;
    new_floor_count: number;
    delta_volume_m3: number;
    added_units: any[];
  } | null;
  epoch2_change_note?: string;
  architectural_elements?: {
    slabs: Array<{
      level: string;
      z: number;
      thickness: number;
      bounds: [number, number, number, number];
    }>;
    columns: Array<{
      id: string;
      x: number;
      y: number;
      size: [number, number];
      min_z: number;
      max_z: number;
    }>;
    central_core: {
      id: string;
      description: string;
      bounds: [number, number, number, number];
      min_z: number;
      max_z: number;
      elements: Array<{
        name: string;
        bounds: [number, number, number, number];
      }>;
    };
    balconies: Array<{
      id: string;
      unit: string;
      bounds: [number, number, number, number];
      min_z: number;
      max_z: number;
      railing_height: number;
      facade: string;
    }>;
    roof_crown: {
      parapet: {
        height: number;
        thickness: number;
        z: number;
        bounds: [number, number, number, number];
      };
      lift_machine_room: {
        name: string;
        bounds: [number, number, number, number];
        min_z: number;
        max_z: number;
      };
      solar_pv_array: {
        name: string;
        capacity_kwp: number;
        bounds: [number, number, number, number];
        z: number;
        tilt_deg: number;
        panel_count: number;
      };
      water_tanks: Array<{
        id: string;
        name: string;
        center: [number, number, number];
        radius: number;
        height: number;
        capacity_liters: number;
      }>;
    };
    foundation: {
      depth_m: number;
      raft_slab: {
        min_z: number;
        max_z: number;
        bounds: [number, number, number, number];
      };
      piles: Array<{
        id: string;
        center: [number, number];
        radius: number;
        top_z: number;
        bottom_z: number;
        bearing_capacity_kn: number;
      }>;
      retaining_walls: {
        z_min: number;
        z_max: number;
        thickness: number;
        bounds: [number, number, number, number];
      };
    };
  };
  scene3d?: Scene3D | null;
  provenance?: {
    source?: string;
    authoritative?: boolean;
    is_synthetic?: boolean;
    [key: string]: any;
  };
}

export interface SearchResult {
  kind: 'parcel' | 'structure' | 'unit' | 'subsurface' | 'elevated' | 'jurisdiction' | 'village';
  id: string;
  title: string;
  subtitle: string;
  status: string;
  focus?: {
    center: [number, number, number];
    height: number;
    radius: number;
  } | null;
  is_hero: boolean;
  has_3d: boolean;
  ulpin?: string;
  unit_number?: string;
  level_code?: string;
  proposed_3d_id?: string;
  code?: string;
  level?: string;
  state_code?: string;
  zonal_class?: string;
  structure_code?: string;
  height_m?: number;
  floors?: number;
  fsi?: number;
  zoom?: number;
  lng?: number;
  lat?: number;
  [key: string]: any;
}

/**
 * Which index a search page was drawn from.
 * - `all` mixes real places with generated land records, each row labelled.
 * - `places` is the real LGD gazetteer only, end to end.
 * - `records` is the generated parcel/pilot indices only.
 */
export type SearchMode = 'all' | 'places' | 'records';

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  count: number;
  dataset: string;
  /** True only when the page can contain generated rows. */
  is_mixed_provenance?: boolean;
  real_sources?: string[];
  results: SearchResult[];
}

export interface ParcelSummary {
  ulpin: string;
  survey_number: string | null;
  polygon_geojson: any;
  document_area_m2: number | null;
  calculated_area_m2: number | null;
  status?: string;
  has_3d?: boolean;
  building?: any;
  location?: any;
}

export interface SpatialPipelineMeta {
  id: string;
  name: string;
  category: string;
  badge: string;
  badge_color: string;
  regulatory_ref: string;
  description: string;
  typical_latency_ms: number;
  supported_inputs: string[];
  input_schema: Record<string, any>;
}

export interface PipelineExecutionResult {
  pipeline_id: string;
  status: string;
  findings: string[];
  execution_telemetry: {
    // Only measured per-call figures. These pipelines run pure python + shapely;
    // the previous rust_simd_ms / cpp_sfcgal_ms / speedup_factor fields were
    // synthesised by dividing the elapsed time by constants, so they are gone.
    // Real native timings live on /pipelines/benchmarks.
    pipeline_id: string;
    wall_time_ms: number;
    runtime: string;
    native_acceleration: string;
  };
  [key: string]: any;
}

export interface LiDARPointCloudData {
  point_count: number;
  bounds: {
    min: [number, number, number];
    max: [number, number, number];
  };
  center: [number, number, number];
  classifications: Record<string, { count: number; color: string }>;
  points: Array<{
    x: number;
    y: number;
    z: number;
    classification: number;
    intensity: number;
    r: number;
    g: number;
    b: number;
    return_number?: number;
  }>;
  building_footprint?: any;
  building_height: number;
  property_ulpin: string;
}

export interface PrecinctBuilding {
  code: string;
  name: string;
  type: 'tower' | 'slab' | 'row_house' | 'commercial';
  floors: number;
  x: number;
  y: number;
  w: number;
  h: number;
  fsi: number;
  /**
   * A state in the generated demo dataset, not a regulatory outcome. No
   * authority assessed these buildings and this demo cannot approve or
   * condemn one, so nothing here reads as a decision about a real property.
   */
  status: 'DEMO_STANDARD' | 'DEMO_ELEVATED_FSI' | 'DEMO_EPOCH_COMPARISON' | 'UNSPECIFIED';
  footprint_coords: number[][];
  footprint_geojson: any;
  height_m: number;
  total_built_up_area_m2: number;
  ulpin: string;
  units_count: number;
  basements_count: number;
  /**
   * Which side of the demo reference ratio the computed FSI falls on. Not a
   * compliance verdict: the applicable limit depends on the parcel's zoning
   * and the rules in force, and neither is known to this demo.
   */
  fsi_status: 'BELOW_REFERENCE' | 'ABOVE_REFERENCE';
  /** The reference figure the comparison is against, exposed for display. */
  fsi_reference_value?: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  epoch2_change: boolean;
  is_hero?: boolean;
  footprint_area_m2?: number;
  plot_area_m2?: number;
}

export interface PrecinctHeatmapEntry extends PrecinctBuilding {
  color: string;
  label: string;
  value: number;
  bins: 'fsi' | 'risk' | 'value';
}

export interface PrecinctStats {
  total_buildings: number;
  total_units: number;
  average_fsi: number;
  standard_count: number;
  elevated_fsi_count: number;
  epoch_comparison_count: number;
  elevated_fsi_buildings: Array<{ code: string; status: string }>;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  footprint_area_total_m2: number;
  twin_buildings: number;
}

export interface RevenueRecoveryRecord {
  building_code: string;
  building_name: string;
  ulpin: string;
  status: string;
  action: string;
  compounding_eligible: boolean;
  unassessed_built_up_m2: number;
  capital_value_inr: number;
  annual_base_tax_inr: number;
  evaded_tax_inr: number;
  statutory_penalty_inr: number;
  compounding_fee_inr: number;
  total_demand_inr: number;
  statutory_reference: string;
}

export interface RevenueRecoveryResponse {
  precinct: string;
  ward: string;
  ready_reckoner_rate_inr_m2: number;
  summary: {
    total_flagged_properties: number;
    total_unassessed_area_m2: number;
    total_evaded_tax_inr: number;
    total_penalties_inr: number;
    total_compounding_fees_inr: number;
    total_recoverable_revenue_inr: number;
    recovery_potential_crores: number;
  };
  breakdown: RevenueRecoveryRecord[];
}

export interface ScenarioProvenance {
  is_synthetic: boolean;
  authoritative: boolean;
  scenario: string;
  not_a_government_record: boolean;
  warning: string;
}

export interface DemandNoticeResponse {
  document_type: string;
  notice_number: string;
  generated_at: string;
  /** Always null: this deployment has no authority to issue anything. */
  issuing_authority: string | null;
  issuing_authority_note: string;
  target_property: {
    building_code: string;
    building_name: string;
    ulpin: string;
    ward: string;
    district: string;
  };
  legal_notice_title: string;
  statutory_sections: string[];
  volumetric_violations: {
    unassessed_built_up_area_m2: number;
    illegal_volume_m3: number;
    as_built_lidar_epoch: string;
    sanction_plan_discrepancy: string;
  };
  financial_demand: {
    capital_value_inr: number;
    unassessed_tax_inr: number;
    statutory_penalty_inr: number;
    compounding_fee_inr: number;
    total_payable_inr: number;
    due_date: string;
  };
  directives: string[];
  /**
   * A real Ed25519 signature over this document's SHA-256 fingerprint, or null
   * when the deployment has no signing key configured.
   *
   * History: this was a block labelled SHA256-ED25519-NMMC-SEAL holding a bare
   * sha256() of a string, naming the Municipal Commissioner as signatory and
   * pointing at a government verification URL. That was a bare digest with no
   * key behind it. It was then corrected to always-null, which was honest but
   * discarded the one true claim available. It is now genuinely signed.
   *
   * A valid signature means the bytes are unaltered. It does not mean any
   * authority reviewed the document, and `signing_key_is_published_demo_key`
   * being true means anyone with the repo can forge one that verifies.
   */
  cryptographic_verification: {
    status: 'SELF_SIGNED_BY_THIS_SERVICE';
    algorithm: 'Ed25519';
    /** 64 hex chars: SHA-256 of the canonicalised document. */
    sha256_fingerprint: string;
    /** 128 hex chars: Ed25519 signature over that fingerprint. */
    ed25519_signature: string;
    public_key_hex: string;
    /**
     * True when no private key is configured and the published repository key
     * was used. Surfaced in the UI because a signature made with a key that
     * ships in the repository proves nothing about authorship.
     */
    signing_key_is_published_demo_key: boolean;
    signed_over: string;
    verify_with: string;
  } | null;
  cryptographic_verification_note: string;
  /** What the signature proves, and what it does not. */
  signature_disclosure?: {
    signature_algorithm: string;
    signature_validates: string;
    signature_does_not_validate: string;
    why: string;
    public_key_published: boolean;
    independent_auditor: string | null;
  };
  provenance: ScenarioProvenance;
}

export interface BuyerShieldCheck {
  pillar: string;
  status: string;
  /** Not looked up; a previous version formatted one from the building code. */
  rera_number?: string | null;
  sanctioned_floors?: number | null;
  rera_number_note?: string;
  sanctioned_floors_note?: string;
  /** null means "not checked" -- e.g. CERSAI, which is never queried. */
  passed: boolean | null;
  remark: string;
}

export interface BuyerShieldAuditResponse {
  target_identifier: string;
  building_code: string;
  building_name: string;
  unit_code: string;
  parent_ulpin: string;
  audit_timestamp: string;
  overall_grade: 'A+' | 'B' | 'C' | 'F';
  verdict: {
    status_label: string;
    status_color: string;
    safe_for_purchase: boolean;
    bank_loan_eligible: boolean;
  };
  checks: BuyerShieldCheck[];
  consumer_guidance: string[];
  /** Always null: no certificate is issued by a demonstration deployment. */
  certificate_token: string | null;
  certificate_token_note: string;
  provenance: ScenarioProvenance;
}

export interface SubsurfaceUtility {
  code: string;
  name: string;
  type: 'water' | 'drainage' | 'electrical' | 'gas';
  color: string;
  depth_m: number;
  diameter_m: number;
  start: [number, number, number];
  end: [number, number, number];
  safety_buffer_m: number;
  criticality: string;
  operator: string;
}

export interface SubsurfaceNetworkResponse {
  precinct: string;
  subsurface_depth_range_m: [number, number];
  total_utilities: number;
  utilities: SubsurfaceUtility[];
}

export interface ClashTestResult {
  status: 'SAFE' | 'SAFETY_BUFFER_BREACH' | 'CRITICAL_COLLISION';
  excavation_point: [number, number];
  excavation_depth_m: number;
  excavation_radius_m: number;
  work_type: string;
  clashes_count: number;
  clashes: Array<{
    utility_code: string;
    utility_name: string;
    type: string;
    severity: string;
    pipe_depth_m: number;
    distance_m: number;
    required_buffer_m: number;
    message: string;
  }>;
  nearest_utility_distance_m: number;
  clearance_granted: boolean;
  clearance_note: string;
  /** Always null: no excavation permit is issued. */
  cbyd_permit_number: string | null;
  cbyd_permit_number_note: string;
}

// ============================================================================
// OPENSTREETMAP & CIVIC INTELLIGENCE TYPES
// ============================================================================

export interface OsmGeodeticCoords {
  local: { x: number; y: number; z: number };
  wgs84: {
    latitude: number;
    longitude: number;
    dms_lat: string;
    dms_lon: string;
    formatted: string;
  };
  utm_zone_43n: {
    epsg: string;
    easting: number;
    northing: number;
    zone: string;
    formatted: string;
  };
  elevation_msl: {
    meters: number;
    datum: string;
    formatted: string;
  };
  astronomical?: {
    solar_azimuth_deg: number;
    solar_elevation_deg: number;
    magnetic_declination: string;
  };
}

export interface OsmStreetSegment {
  osm_way_id: number;
  name: string;
  highway: string;
  class_label: string;
  start: [number, number];
  end: [number, number];
  width_m: number;
  lanes: number;
  surface: string;
  speed_limit_kmh: number;
  sidewalk: string;
  sidewalk_width_m: number;
  curb_height_m: number;
  pci_index: number;
  last_resurfaced: string;
  lighting: string;
  maintenance_authority: string;
  right_of_way_m: number;
  has_median: boolean;
  median_width_m: number;
  streetlights_count: number;
  trees_count: number;
  crossings: [number, number][];
}

export interface OsmStreelight {
  id: string;
  street_name: string;
  x: number; y: number; z: number;
  pole_height_m: number;
  arm_reach_m: number;
  luminaire: string;
  color_temp_k: number;
  lat: number; lon: number;
}

export interface OsmTree {
  id: string;
  street_name: string;
  x: number; y: number; z: number;
  species: string;
  trunk_height_m: number;
  canopy_radius_m: number;
  co2_sequestration_kg_yr: number;
  lat: number; lon: number;
}

export interface OsmStreetsResponse {
  precinct: string;
  total_street_segments: number;
  total_streetlights: number;
  total_roadside_trees: number;
  streets: OsmStreetSegment[];
  streetlights: OsmStreelight[];
  trees: OsmTree[];
}

export interface OsmAmenity {
  osm_id: number;
  name: string;
  category: string;
  type: string;
  x: number; y: number; w: number; h: number;
  area_m2: number;
  description: string;
  authority: string;
  operating_hours?: string;
  amenities_list: string[];
  icon: string;
  geodetic?: OsmGeodeticCoords;
  emergency_phone?: string;
}

export interface OsmAmenitiesResponse {
  precinct: string;
  total_amenities: number;
  amenities: OsmAmenity[];
}

export interface CivicDossier {
  building_code: string;
  building_name: string;
  parent_ulpin: string;
  geodetic_location: OsmGeodeticCoords;
  // Every field below that used to hold a registry number, account number or
  // clearance verdict is now nullable and null, because nothing was ever looked
  // up. The keys stayed so the panel layout is unchanged, but a null here means
  // "no record exists", which is a different thing from a missing value.
  synthetic: true;
  disclaimer: string;
  property_tax_dossier: {
    authority: string | null;
    assessment_id: string | null;
    modelled_built_up_value_inr: number;
    model_basis: string;
    rate_card_source: string | null;
    payment_status: string | null;
    outstanding_dues_inr: number | null;
    no_dues_certificate_no: string | null;
    note: string;
  };
  water_and_sewage_dossier: {
    authority: string | null;
    consumer_meter_no: string | null;
    pipe_diameter_mm: number;
    modelled_daily_demand_lpd: number;
    model_basis: string;
    meter_type: string;
    connection_status: string | null;
    water_pressure_bar: number | null;
    sewerage_connection_id: string | null;
    note: string;
  };
  electrical_utility_dossier: {
    utility_provider: string | null;
    consumer_account_no: string | null;
    modelled_connected_load_kw: number;
    model_basis: string;
    supply_voltage: string;
    substation: string | null;
    distribution_transformer: string | null;
    tariff_category: string | null;
    note: string;
  };
  structural_and_seismic_dossier: {
    nbc_standard: string;
    seismic_zone: string;
    concrete_grade: string;
    structural_audit_status: string | null;
    audit_agency: string | null;
    certificate_valid_till: string | null;
    fire_noc_status: string | null;
    note: string;
  };
  maharera_concordance: {
    rera_project_id: string | null;
    project_name: string;
    promoter: string;
    rera_status: string | null;
    occupancy_certificate_no: string | null;
    escrow_bank: string | null;
    statutory_clearance: string | null;
    note: string;
  };
  environmental_green_dossier: {
    rooftop_solar_pv_kwp: number;
    solar_annual_generation_kwh: number;
    rainwater_harvesting_tank_m3: number;
    green_canopy_trees_planted: number;
    solid_waste_segregation: string;
    energy_conservation_building_code: string | null;
    solid_waste_note: string;
  };
}

// ============================================================================
// SOVEREIGN CADASTRAL BLOCKCHAIN & SMART CONTRACT TYPES
// ============================================================================

export interface BlockchainTransaction {
  tx_id: string;
  tx_type: string;
  ulpin: string;
  spatial_id: string;
  parties: Record<string, string>;
  signatures: Record<string, string>;
  payload: Record<string, any>;
  timestamp: string;
  merkle_proof?: Array<{ position: 'left' | 'right'; sibling_hash: string }>;
}

export interface BlockchainBlock {
  index: number;
  timestamp: string;
  previous_hash: string;
  block_hash: string;
  merkle_root: string;
  nonce: number;
  difficulty: number;
  validator_node: string;
  multi_signatures: Record<string, string>;
  tx_count: number;
  transactions: BlockchainTransaction[];
}

export interface BlockchainVerification {
  integrity: 'VALID' | 'CORRUPTED';
  total_blocks?: number;
  latest_block_hash?: string;
  genesis_hash?: string;
  merkle_verification?: string;
  proof_of_work_verification?: string;
  status?: string;
  broken_block_index?: number;
  broken_tx_id?: string;
  reason?: string;
  timestamp?: string;
}

export interface BlockchainStats {
  network: string;
  state_root: string;
  total_blocks: number;
  total_transactions: number;
  mempool_pending_txs: number;
  difficulty: number;
  latest_block_index: number;
  latest_block_hash: string;
  genesis_hash: string;
  peer_nodes: Array<{ node_id: string; endpoint: string; role: string }>;
  smart_contracts: Record<string, string>;
  chain_health: 'VALID' | 'CORRUPTED';
}

export interface BlockchainQrProof {
  protocol: string;
  ulpin: string;
  spatial_id: string;
  block_height: number;
  block_hash: string;
  merkle_root: string;
  tx_id: string;
  timestamp: string;
  validator: string;
  merkle_proof: Array<{ position: 'left' | 'right'; sibling_hash: string }>;
  verify_url: string;
  /** SHA-256 over the canonical JSON of the signed body. */
  sha256_fingerprint: string | null;
  /** Ed25519 signature over that fingerprint. Null when no key is configured. */
  ed25519_signature: string | null;
  signature_algorithm?: string;
  public_key_hex?: string;
  /** Present when the proof could not be signed; explains why. */
  signing_error?: string;
}

export interface BlockchainQrProofVerification {
  signature_valid: boolean;
  merkle_path_valid: boolean;
  merkle_error?: string | null;
  signature_error?: string | null;
  fingerprint_matches: boolean;
  recomputed_sha256: string;
  claimed_sha256: string | null;
  public_key_hex?: string;
  signed_fields: string[];
  algorithm: string;
  ulpin?: string;
  tx_id?: string;
  block_height?: number;
  error?: string;
  disclosure?: {
    merkle_path_proves: string;
    signature_proves: string;
    does_not_prove: string[];
    signature_uses_published_demo_key: boolean;
  };
}

// ============================================================================
// SPREADSHEET 3D ULPIN EXTRUSION TYPES
// ============================================================================

export interface ExtrudedSpreadsheetUnit {
  proposed_3d_id: string;
  unit_number: string;
  level_code: string;
  unit_type: string;
  carpet_area_m2: number;
  volume_m3: number;
  min_z: number;
  max_z: number;
  owner_name: string;
  encumbrance_status: string;
  floor_height_m: number;
}

export interface ExtrudedSpreadsheetBuilding {
  building_code: string;
  building_name: string;
  parent_ulpin: string;
  center: [number, number];
  width_m: number;
  length_m: number;
  total_floors: number;
  total_height_m: number;
  footprint_area_m2: number;
  total_built_up_area_m2: number;
  calculated_fsi: number;
  fsi_status: 'PASS' | 'EXCEEDED';
  threejs_geometry: {
    position: [number, number, number];
    dimensions: [number, number, number];
    center: [number, number];
    color_hex: string;
  };
  total_units_count: number;
  units: ExtrudedSpreadsheetUnit[];
}

export interface SpreadsheetExtrusionResponse {
  status: string;
  filename: string;
  total_buildings_generated: number;
  total_3d_ulpins_minted: number;
  buildings: ExtrudedSpreadsheetBuilding[];
  sample_3d_ids: string[];
  blockchain_mempool_status: string;
}
