import React, { useEffect, useState, useCallback, lazy, Suspense } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import {
  Building2, Sparkles, MapPin,
  ShieldCheck, Box, FileCheck2, Scale, History as HistoryIcon,
  AlertTriangle, Fingerprint, Crosshair, X, Satellite, Globe2,
} from 'lucide-react';
import { fetchHeroProperty, fetchParcel, processPropertyPipeline, fileObjection, fetchBuilderTemplates, fetchBuilderAssets, resolveIdentifier } from '../../services/api';
import type { ResolvedIdentifier } from '../../services/api';
import { HeroProperty, CadastralUnit, ParcelSummary } from '../../types/cadastre';
import { BuilderTemplate, BuilderAsset } from '../../services/api';
import { PropertyHeader } from '../../components/workspace/PropertyHeader';
import { ThreeCadastralViewer } from '../../components/viewer3d/ThreeCadastralViewer';
import LiDARInspector from '../../components/lidarinspector/LiDARInspector';
const MapLibreCadastreMap = lazy(() => import('../../components/map2d/MapLibreCadastreMap').then(m => ({ default: m.MapLibreCadastreMap })));
const EsriSatelliteView = lazy(() => import('../../components/map2d/EsriSatelliteView').then(m => ({ default: m.EsriSatelliteView })));
import { HierarchyTree } from '../../components/workspace/HierarchyTree';
import { EvidencePanel } from '../../components/workspace/EvidencePanel';
import { ValidationPanel } from '../../components/workspace/ValidationPanel';
import { RightsPanel } from '../../components/workspace/RightsPanel';
import { HistoryTimeline } from '../../components/workspace/HistoryTimeline';
import { QRVerificationModal } from '../../components/qr/QRVerificationModal';
import { VerificationQueueModal } from '../../components/verification/VerificationQueueModal';
import { AskTheMapModal } from '../../components/workspace/AskTheMapModal';
import { Card, Badge, ProvenanceTag, StatusBadge, Tabs, ErrorState, Skeleton } from '../../components/ui';
import { useApp } from '../../context/AppContext';
import { BuyerShieldModal } from '../../components/modals/BuyerShieldModal';
import { DemandNoticeModal } from '../../components/modals/DemandNoticeModal';
import { GovernmentDeedPrintModal } from '../../components/modals/GovernmentDeedPrintModal';
import { HERO_ULPIN } from '../../constants';


type TabId = 'overview' | 'twin' | 'evidence' | 'rules' | 'rights' | 'history' | 'map2d';

export const PropertyDetail: React.FC = () => {
  const { ulpin = HERO_ULPIN } = useParams();
  const [searchParams] = useSearchParams();
  const unitParam = searchParams.get('unit');
  // A canonical 3D ID is `ULPIN/UB17-L05-501-W`. Its `/` is a path separator, so
  // it cannot be carried in the route param as-is and `/parcels/{ulpin}` cannot
  // address it. The resolver takes the whole identifier and hands back the
  // parent parcel plus whatever of the unit actually exists.
  const isCompositeId = ulpin.includes('/');
  const [resolution, setResolution] = useState<ResolvedIdentifier | null>(null);
  const [resolutionNote, setResolutionNote] = useState<string | null>(null);
  const { role, highlight, permissions, showToast } = useApp();

  const isHero = ulpin === HERO_ULPIN;
  const [property, setProperty] = useState<HeroProperty | null>(null);
  const [selectedUnit, setSelectedUnit] = useState<CadastralUnit | null>(null);
  const [tab, setTab] = useState<TabId>(isHero ? 'overview' : 'overview');
  const [activeColorMode, setActiveColorMode] = useState('rights');
  const [undergroundMode, setUndergroundMode] = useState(false);
  const [isEpoch2, setIsEpoch2] = useState(false);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  // Bumped by every retry so the loader effect re-runs. Without it, "Try
  // again" only cleared the error string: `loading` was already false and
  // `property` was still null, so the page fell through to `return null` and
  // rendered a blank screen instead of refetching.
  const [reloadToken, setReloadToken] = useState(0);
  const retryLoad = useCallback(() => setReloadToken((n) => n + 1), []);
  const [isProcessing, setIsProcessing] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [lidarOpen, setLidarOpen] = useState(false);
  const [objectionOpen, setObjectionOpen] = useState(false);
  const [buyerShieldOpen, setBuyerShieldOpen] = useState(false);
  const [demandNoticeOpen, setDemandNoticeOpen] = useState(false);
  const [deedPrintOpen, setDeedPrintOpen] = useState(false);
  const [objectionCategory, setObjectionCategory] = useState('Urban Development');
  const [objectionNote, setObjectionNote] = useState('');
  const [objectionSubmitting, setObjectionSubmitting] = useState(false);
  const [objectionError, setObjectionError] = useState<string | null>(null);
  const [modelDisplayMode, setModelDisplayMode] = useState<'strata' | 'architectural' | 'hybrid'>('hybrid');
  const [mapBase, setMapBase] = useState<'cadastre' | 'satellite'>('cadastre');
  const [proposalModel, setProposalModel] = useState<string | null>(null);
  const [proposalTemplates, setProposalTemplates] = useState<BuilderTemplate[]>([]);
  const [proposalAssets, setProposalAssets] = useState<BuilderAsset[]>([]);

  function getMatchingTemplateUrl(bldType?: string, floors?: number, templates: BuilderTemplate[] = []): string | null {
    if (!templates.length) return null;
    const t = (bldType || '').toLowerCase();
    if (t.includes('mall') || t.includes('commercial')) {
      return templates.find((x) => x.id === 'TPL-MALL' || x.id === 'TPL-OFF-BLOCK')?.url || templates[0].url;
    }
    if (t.includes('off') || t.includes('trade')) {
      return templates.find((x) => x.id === 'TPL-OFF-BLOCK')?.url || templates[0].url;
    }
    if (t.includes('villa') || t.includes('row') || (floors !== undefined && floors <= 3)) {
      return templates.find((x) => x.id === 'TPL-VILLA')?.url || templates[0].url;
    }
    if (t.includes('slab') || t.includes('twin')) {
      return templates.find((x) => x.id === 'TPL-TWIN')?.url || templates[0].url;
    }
    return templates.find((x) => x.id === 'TPL-RES-TOWER')?.url || templates[0].url;
  }

  useEffect(() => {
    Promise.all([fetchBuilderTemplates(), fetchBuilderAssets()])
      .then(([t, a]) => {
        setProposalTemplates(t);
        setProposalAssets(a);
        setProposalModel((prev) => prev ?? (t[0]?.url ?? a[0]?.url ?? null));
      })
      .catch((err) => console.error('proposal assets failed to load', err));
  }, []);

  const submitObjection = async () => {
    if (!objectionNote.trim()) {
      setObjectionError('Please describe the discrepancy.');
      return;
    }
    setObjectionError(null);
    setObjectionSubmitting(true);
    try {
      const rec = await fileObjection({
        ulpin: property?.parent_ulpin || ulpin,
        category: objectionCategory,
        description: objectionNote.trim(),
        contact_email: '',
        priority: 'MEDIUM',
      });
      setObjectionOpen(false);
      setObjectionNote('');
      showToast(`Objection filed · Case ${rec.case_number} sent for review`);
    } catch {
      setObjectionError('Could not file the objection. Please try again.');
    } finally {
      setObjectionSubmitting(false);
    }
  };

function synthesizePropertyFromParcel(parcelData: any): HeroProperty {
  const b = parcelData.building || (parcelData.structures && parcelData.structures[0]) || {};
  const rawLevels = (parcelData.levels && parcelData.levels.length ? parcelData.levels : b.levels) || [];
  // Levels come from the record or not at all. This previously fell back to
  // Array.from({length: floors}) and invented 'G', 'L01', 'L02' with
  // 'Ground Floor' and 'Floor 1' as names, and derived min_z/max_z by
  // multiplying an assumed 3.5 m storey height. A builder-submitted parcel
  // reaches this function, so the fabrication would have been attributed to
  // whoever submitted it: a floor list that no surveyor, submitter or registry
  // ever stated, rendered as if it described the building.
  //
  // A level the source did not name is named nothing, not "Ground Floor".
  const levelsData = rawLevels.map((lv: any, idx: number) => ({
    level_code: lv.level_code ?? null,
    floor_number: lv.floor_number ?? null,
    name: lv.name ?? null,
    use: lv.use ?? lv.level_use ?? null,
    min_z: lv.min_z ?? null,
    max_z: lv.max_z ?? null,
    height_m: lv.height_m ?? null,
    level_type: lv.level_type ?? null,
    units_count: lv.units_count ?? null,
    _index: idx,
  }));

  const rawUnits = (parcelData.units && parcelData.units.length ? parcelData.units : b.units) || [];
  // Same rule for units. This previously manufactured four units per level
  // (unit numbers 'G01'..'G04', 68.5 m2 carpet, 84 m2 built-up) and attached an
  // OWNERSHIP right over each one in favour of "Registered Allottee (Flat G01)"
  // at 100% share. That is a fabricated title on a real-shaped record: the
  // name, the area, the share and the existence of the unit were all invented,
  // and a rights panel would have rendered them as registered ownership.
  const enrichedUnits: CadastralUnit[] = rawUnits.map((u: any) => ({
    unit_number: u.unit_number ?? null,
    proposed_3d_id: u.proposed_3d_id ?? null,
    level_code: u.level_code ?? null,
    unit_type: u.unit_type ?? null,
    min_z: u.min_z ?? null,
    max_z: u.max_z ?? null,
    carpet_area_m2: u.carpet_area_m2 ?? null,
    built_up_area_m2: u.built_up_area_m2 ?? null,
    volume_m3: u.volume_m3 ?? null,
    footprint_geojson: u.footprint_geojson ?? null,
    coords: u.coords ?? null,
    mesh_3d: { vertices: [], faces: [] },
    center: [0, 0, 0] as [number, number, number],
    // Rights are a separate record. Absent evidence of a right is the
    // absence of a right, so none is synthesised here.
    rights: u.rights ?? [],
  }));

  const loc = parcelData.location || {};
  const stateName = loc.state || 'Maharashtra';
  const distName = loc.district || 'Thane';
  const talukaName = loc.taluka || distName;
  const villageName = loc.village_ward || talukaName;
  // A permitted-FAR rule is a matter of the jurisdiction's Development Control
  // Regulations, not of the building's use type. The old fallback picked 2.5 for
  // commercial and 2.0 otherwise, i.e. it invented a zoning rule, then used that
  // rule to issue a PASS or EXCEEDED verdict about a real parcel. No rule on
  // record means no verdict.
  const maxAllowedFsi = parcelData.fsi?.max_allowed_fsi ?? b.max_allowed_fsi ?? null;

  // Every one of these previously fell back to a plausible number (1200 m2 plot,
  // 1.85 FSI, built-up area derived from the other two), and the result was
  // displayed as measurement. They are now null unless a source states them.
  const plotArea =
    parcelData.fsi?.plot_area_m2 ?? parcelData.calculated_area_m2 ?? parcelData.document_area_m2 ?? null;
  const rawFsi = parcelData.fsi?.calculated_fsi ?? b.fsi ?? b.calculated_fsi ?? null;
  const fsiVal = rawFsi === null ? null : Number(rawFsi.toFixed(2));
  const builtUp =
    parcelData.fsi?.built_up_area_m2 ??
    b.built_up_area_m2 ??
    b.total_built_up_area_m2 ??
    (plotArea !== null && fsiVal !== null ? Math.round(plotArea * fsiVal) : null);
  const fsiStatus =
    parcelData.fsi?.status ??
    (fsiVal !== null && maxAllowedFsi !== null ? (fsiVal <= maxAllowedFsi ? 'PASS' : 'EXCEEDED') : null);

  return {
    property_id: `${parcelData.ulpin}/${b.code ?? 'no-structure'}`,
    parent_ulpin: parcelData.ulpin,
    // No invented 3D identifier. Previously '<ulpin>/UB01-G-001', which reads
    // like a registry allocation of a ground-floor unit that need not exist.
    proposed_3d_id: b.proposed_3d_id ?? null,
    record_version: 'V1-PRECINCT',
    // Not 'APPROVED'. A record with no stated status is not an approved
    // record, and a builder submission that no reviewer has looked at would
    // have rendered here as APPROVED.
    status: parcelData.status ?? b.status ?? 'UNVERIFIED',
    coordinates: {
      centroid_lat: parcelData.centroid?.lat ?? null,
      centroid_lon: parcelData.centroid?.lon ?? null,
      source: parcelData.geometry_source ?? 'not-stated',
      authoritative: false,
      note: 'Coordinates are the geometry asserted by the record. Not surveyed unless a source says so.',
    },
    address: {
      line1: parcelData.address ?? null,
      locality: parcelData.locality ?? null,
      village_ward: villageName || null,
      taluka: talukaName || null,
      district: distName || null,
      state: stateName || null,
      postal_code: parcelData.postal_code ?? null,
    },
    precinct: {
      name: villageName && distName ? `${villageName}, ${distName}` : null,
      state: stateName || null,
      district: distName || null,
      taluka: talukaName || null,
      // Was built by slicing strings: state.slice(0,2) + district.slice(0,3)
      // produced 'MA-THA' for a jurisdiction code. Nothing assigned that.
      code: loc.jurisdiction_code ?? null,
      center: parcelData.centroid
        ? [parcelData.centroid.lat, parcelData.centroid.lon]
        : null,
      max_allowed_fsi: maxAllowedFsi,
    },
    parcel: {
      ulpin: parcelData.ulpin,
      survey_number: parcelData.survey_number ?? null,
      document_area_m2: plotArea,
      calculated_area_m2: plotArea,
      polygon_geojson: parcelData.polygon_geojson ?? null,
    },
    structure: {
      building_code: b.code ?? b.building_code ?? null,
      name: b.name ?? null,
      // No `b.floors || 4`. A null height is reported as null; the backend
      // already returns null for unknown height and floors, and this was
      // quietly replacing both with invented values.
      height_m: b.height_m ?? null,
      floors_count: b.floors ?? b.floors_count ?? null,
      basements_count: b.basements_count ?? null,
      total_built_up_area_m2: builtUp,
      calculated_fsi: fsiVal,
      status: parcelData.status ?? b.status ?? 'UNVERIFIED',
      footprint_geojson: b.footprint_geojson ?? null,
      // The live workflow status from the submission row when there is one, so
      // a structure a reviewer has already accepted reads ACCEPTED_FOR_RECORD
      // rather than staying the PENDING_REVIEW default forever.
      verification_status:
        parcelData.builder_record?.status ?? parcelData.verification_status ?? 'PENDING_REVIEW',
      // What the geometry is, not what anyone approved. builder-asserted rows
      // are marked as such in the header and map.
      geometry_basis: b.height_basis ?? null,
      provenance: b.provenance ?? null,
      is_verified: b.is_verified ?? null,
    },
    levels: levelsData,
    units: enrichedUnits,
    builder_record: parcelData.builder_record ?? null,
    subsurface_objects: [],
    elevated_objects: [],
    // No evidence streams are declared here. This previously asserted two:
    // a cadastral file and an airborne LiDAR survey, both marked
    // provenance_kind OFFICIAL, one attributed to the Maharashtra Land Records
    // Department, the other to a "Riegl VUX-1LR Sensor" at 32.4 pts/m². Neither
    // file existed under those names (the point cloud in the repo is
    // airoli_s8_hero.las), both sha256 values were typed-in constants, and
    // "Tier A — Authoritative Survey Grade" was the confidence label of an
    // assertion rather than of a measurement. A record that claims official
    // survey provenance it does not have is worse than one that claims none.
    evidence_streams: (parcelData.evidence_streams ?? []).map((e: any) => ({
      stream_id: e.stream_id ?? null,
      source_type: e.source_type ?? null,
      status: e.status ?? 'UNKNOWN',
      file_name: e.file_name ?? null,
      file_hash: e.file_hash ?? null,
      confidence_tier: e.confidence_tier ?? null,
      provenance: e.provenance ?? null,
      provenance_kind: e.provenance_kind ?? 'UNVERIFIED',
    })),
    // No 15-rule PASS. The previous values reported 15 rules run, 15 passed,
    // 0 failed and an empty findings list whenever a structure's status string
    // happened to be APPROVED, which described no validation anyone performed.
    validation: parcelData.validation ?? null,
    validation_note:
      'No validation run is reported for this record. Rule results are produced by a validation run, not by the record status.',
    fsi: {
      plot_area_m2: plotArea,
      built_up_area_m2: builtUp,
      calculated_fsi: fsiVal,
      max_allowed_fsi: maxAllowedFsi,
      status: fsiStatus,
    },
    // Still no proof *on this client-side fallback record*, and the reason has
    // to be stated accurately.
    //
    // This previously read "No signature is produced by this deployment. There
    // is no key, no signing authority, and nothing to verify against." That
    // stopped being true when real Ed25519 signing landed: the deployment now
    // holds a key and signs. The correct statement is narrower -- this record
    // is synthesised in the browser, the signature is computed server-side over
    // the authoritative response, and this object is not that response.
    cryptographic_proof: null,
    cryptographic_proof_note:
      'No signature on this summary, because it is a client-side fallback summary rather than the ' +
      'server response. The deployment does sign: POST /api/v1/precinct/generate-demand-notice returns ' +
      'a real SHA-256 fingerprint and Ed25519 signature, verifiable at POST /api/v1/precinct/verify-signature. ' +
      'That key is held by this deployment, not by any government office.',

    // A change-detection result requires two dated observations of the same
    // structure. The browser has neither, so the previous values here (a 3.5 m
    // delta, +1 floor, against a '2026 Baseline') were a manufactured finding.
    epoch2_change: null,
    epoch2_change_note:
      'Not computed. Change detection needs two dated observations of the same structure from a real source; this deployment has one observation of unknown date.',
    provenance: parcelData.provenance || {
      source: 'Synthesized Cadastral Record',
      authoritative: false,
      is_synthetic: true,
    },
  };
}

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setSelectedUnit(null);
    if (!isHero && isCompositeId) {
      resolveIdentifier(ulpin)
        .then((r) => {
          if (!active) return;
          setResolution(r);
          // A well-formed ID whose structure was never ingested still resolves to
          // its parcel, so the page loads and says what is missing rather than
          // pretending the identifier was wrong.
          if (r.unresolved) {
            setResolutionNote(
              `Unit ${r.unresolved.building_code ?? ulpin} is not part of any ingested structure on parcel ${r.parent_ulpin} (${r.unresolved.reason}). Showing the parcel.`,
            );
          } else if (r.unit_exists === false) {
            setResolutionNote(`Unit ${r.parsed_components?.unit_code ?? ''} is not recorded on this parcel. Showing the parcel.`);
          } else {
            setResolutionNote(null);
          }
        })
        .catch((e) => {
          if (!active) return;
          setResolution(null);
          setResolutionNote(e instanceof Error ? e.message : 'Identifier could not be resolved');
        });
    }
    const lookupUlpIn = isCompositeId ? ulpin.split('/')[0].trim().toUpperCase() : ulpin;
    const job = isHero ? fetchHeroProperty() : fetchParcel(lookupUlpIn);
    job
      .then((d) => {
        if (!active) return;
        if (isHero) {
          setProperty(d as HeroProperty);
          if (unitParam) {
            const u = (d as HeroProperty).units.find((x) => x.unit_number === unitParam);
            if (u) {
              setSelectedUnit(u);
              setTab('twin');
            }
          }
        } else {
          const p = d as any;
          const synth = synthesizePropertyFromParcel(p);
          setProperty(synth);
          const matched = getMatchingTemplateUrl(synth.structure?.name ?? undefined, synth.structure?.floors_count ?? undefined, proposalTemplates);
          if (matched) setProposalModel(matched);
          if (unitParam) {
            const u = synth.units.find((x) => x.unit_number === unitParam);
            if (u) {
              setSelectedUnit(u);
              setTab('twin');
            }
          }
        }
      })
      .catch((e) => active && setError(e instanceof Error ? e.message : 'Failed to load property'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ulpin, isHero, isCompositeId, reloadToken]);

  // Context highlights (from Ask-the-Map) → viewer
  // handled reactively via `highlight?.ids` passed to the viewer below.

  const handleProcess = async () => {
    setIsProcessing(true);
    try {
      await processPropertyPipeline();
      setProperty(await fetchHeroProperty());
    } catch (e) {
      console.error(e);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleExport = (fmt: string) => window.open(`/api/v1/exports/${fmt}`, '_blank');

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-2/5" />
        <Skeleton className="h-4 w-3/5" />
        <Skeleton className="h-72 w-full rounded-none" />
      </div>
    );
  }

  if (error) {
    /*
     * A 404 here is not a failure of this page, it is the absence of a record,
     * and the two deserve very different screens.
     *
     * The endpoint returns 404 both when the identifier has no cadastral record
     * and when the request itself broke, so the branch is split on the status.
     * Previously both landed in the same red ErrorState, which dumped the
     * endpoint's own multi-paragraph explanation -- three bullet lists of things
     * that are not available -- at the user as an error string. The result was a
     * dead end: the tabs never rendered, so the 3D Twin tab could not be opened
     * even for the geometry this identifier does have.
     *
     * A not-ingested record now says so in one sentence, separates what is
     * missing from what is merely unavailable in principle, and points at the
     * area-footprint route, which does resolve published geometry for any place.
     * Nothing is invented to fill the gap: no boundary, no title, no FSI.
     */
    const notInStore = /no dataset ingested|no cadastral record|404/i.test(error);
    if (notInStore) {
      return (
        <div className="space-y-4">
          <div className="annotation text-accent-strong">
            <span className="text-accent-strong">Reviewer (demo)</span>
            <span>/</span>
            <span>Properties</span>
            <span>/</span>
            <span className="font-mono">{ulpin}</span>
          </div>
          <Card>
            <div className="flex flex-col gap-4 p-5">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 shrink-0 bg-amber-400 border-2 border-ink flex items-center justify-center">
                  <MapPin className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-black text-ink">No cadastral record ingested</h3>
                  <p className="text-xs text-ink-soft mt-1.5 leading-relaxed">
                    <span className="font-mono font-bold text-ink">{ulpin}</span> has no record in
                    this deployment&apos;s cadastral store, so there is no parcel boundary, title or
                    compliance finding to show. That is a statement about the data, not an error with
                    the identifier &mdash; nothing here is fabricated to fill the gap.
                  </p>
                </div>
              </div>

              <div className="border-t-2 border-ink pt-3">
                <p className="text-[11px] font-black uppercase tracking-wide text-ink-soft mb-2">
                  What is available for this identifier
                </p>
                <ul className="text-xs text-ink-soft space-y-1.5 list-disc pl-4">
                  <li>
                    Published building footprints for any <em>area</em> &mdash; OpenStreetMap and
                    Microsoft GlobalML, with real ground elevation. Resolved by area, not by parcel
                    identifier, so it works even with no cadastral record.
                  </li>
                  <li>The 3D command center, which draws whatever footprint data the current map
                    view has resolved.</li>
                </ul>
                <p className="text-[11px] font-black uppercase tracking-wide text-ink-soft mt-3 mb-2">
                  What no source provides
                </p>
                <ul className="text-xs text-ink-soft space-y-1.5 list-disc pl-4">
                  <li>Parcel boundary from a land-record source &mdash; no open bulk API exists.</li>
                  <li>Floor ownership &mdash; no public dataset at this granularity.</li>
                  <li>FSI or any compliance verdict &mdash; needs an authoritative permitted-FAR rule
                    and surveyed inputs, and neither is present.</li>
                </ul>
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => navigate('/app/map?view=3d')}
                  className="px-3 py-2 text-xs font-bold bg-ink text-chalk border-2 border-ink shadow-brutal-sm hover:bg-accent transition"
                >
                  Open 3D command center
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/app/map?view=cadastre')}
                  className="px-3 py-2 text-xs font-bold bg-canvas text-ink border-2 border-ink hover:bg-accent transition"
                >
                  Open cadastral map
                </button>
                <button
                  type="button"
                  onClick={retryLoad}
                  className="px-3 py-2 text-xs font-bold text-ink-soft underline hover:text-ink"
                >
                  Try again
                </button>
              </div>
            </div>
          </Card>
        </div>
      );
    }

    return (
      <Card>
        <ErrorState title="Parcel unavailable" message={error} onRetry={retryLoad} />
      </Card>
    );
  }

  // A resolved fetch always sets `property`, so this is a defensive path only.
  // Rendering `null` here produced a silent blank page, which is what a failed
  // retry used to look like; show the skeleton instead so the state is visible.
  if (!property) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-2/5" />
        <Skeleton className="h-4 w-3/5" />
        <Skeleton className="h-72 w-full rounded-none" />
      </div>
    );
  }

  /* ---------------- Full (hero) record ---------------- */
  const tabs: { id: TabId; label: string; icon?: React.ReactNode; count?: number }[] = [
    { id: 'overview', label: 'Overview', icon: <Box className="w-3.5 h-3.5" /> },
    { id: 'twin', label: '3D Twin', icon: <Building2 className="w-3.5 h-3.5" />, count: property.levels.length },
    { id: 'evidence', label: 'Evidence', icon: <FileCheck2 className="w-3.5 h-3.5" />, count: property.evidence_streams.length },
    { id: 'rules', label: 'QA Rules', icon: <Scale className="w-3.5 h-3.5" />, count: property.validation?.total_rules ?? 0 },
    { id: 'rights', label: 'Rights', icon: <ShieldCheck className="w-3.5 h-3.5" /> },
    { id: 'history', label: 'History', icon: <HistoryIcon className="w-3.5 h-3.5" /> },
    { id: 'map2d', label: '2D Map', icon: <MapPin className="w-3.5 h-3.5" /> },
  ];

  return (
    <div className="flex flex-col gap-4 animate-rise-in">
      <div>
        <div className="flex items-center gap-2 annotation text-accent-strong">
          <span className="text-accent-strong">Reviewer (demo)</span><span>/</span><span>Properties</span><span>/</span>
          <span className="font-mono">{property.parent_ulpin}</span>
        </div>
        {/* The requested unit is not in the record. Say so, and say which part of
            the identifier could not be resolved, instead of rendering the parcel
            as though the requested unit were on it. */}
        {resolutionNote && (
          <p
            role="status"
            data-testid="identifier-resolution-note"
            className="mt-1 text-[11px] text-ink-soft border-l-2 border-accent-strong/40 pl-2"
          >
            {resolutionNote}
          </p>
        )}
        {/* When the identifier did resolve all the way to a unit, name the record
            it landed on rather than leaving the visitor to assume. */}
        {resolution?.unit && (
          <p data-testid="identifier-resolution-unit" className="mt-1 text-[11px] text-ink-soft font-mono">
            {resolution.unit.proposed_3d_id} · {resolution.unit.unit_type} · {resolution.unit.carpet_area_m2} m²
            {resolution.structure ? ` · ${resolution.structure.name}` : ''}
          </p>
        )}
      </div>

      <PropertyHeader
        property={property}
        onOpenQR={() => setQrOpen(true)}
        onProcessProperty={handleProcess}
        onExport={handleExport}
        onOpenPrintDeed={() => setDeedPrintOpen(true)}
        isProcessing={isProcessing}
      />

      {/* Honest data-origin strip */}
      <div className="flex flex-wrap items-center gap-2">
        <ProvenanceTag kind="OFFICIAL" />
        <ProvenanceTag kind="AI" />
        <ProvenanceTag kind="DEMO" />
        <span className="text-[11px] text-ink-soft">
          Mixed-source record: layers are ingested from authoritative survey feeds and AI extraction, served from the synthetic pilot.
        </span>
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setAskOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-none text-xs font-bold text-accent-strong bg-accent-faint border-2 border-ink hover:bg-accent-faint transition w-fit"
          >
            <Sparkles className="w-3.5 h-3.5" /> Ask the map
          </button>
          {permissions.canViewLiDAR && (
            <button
              onClick={() => setLidarOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-none text-xs font-bold text-accent-strong bg-accent-faint border-2 border-ink hover:bg-accent-faint hover:border-accent/50 transition w-fit"
            >
              <Crosshair className="w-3.5 h-3.5" /> LiDAR Point Cloud
            </button>
          )}
          {permissions.canApprove && (
            <button
              onClick={() => setVerifyOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-none text-xs font-bold text-emerald-700 bg-emerald-50 border-2 border-ink hover:bg-emerald-100 transition w-fit"
            >
              <ShieldCheck className="w-3.5 h-3.5" /> Verify property
            </button>
          )}
          <button
            onClick={() => setBuyerShieldOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-none text-xs font-bold text-emerald-700 bg-emerald-50 border-2 border-ink hover:bg-emerald-100 transition w-fit shadow-xs"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Buyer Shield
          </button>
          <button
            onClick={() => setDemandNoticeOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-none text-xs font-bold text-rose-700 bg-rose-50 border-2 border-ink hover:bg-rose-100 transition w-fit shadow-xs"
          >
            <FileCheck2 className="w-3.5 h-3.5 text-rose-600" /> Demand Notice
          </button>
        </div>
        <div className="flex items-center gap-2">
          {permissions.canFileObjection && (
            <button
              onClick={() => setObjectionOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-none text-xs font-bold text-green-700 bg-green-50 border-2 border-green-200 hover:bg-green-100 transition w-fit"
            >
              <AlertTriangle className="w-3.5 h-3.5" /> File Objection
            </button>
          )}
          <div className="flex items-center gap-2 text-[11px] text-ink-soft">
            <Badge tone="blue" dot>role · {role.replace('_', ' ').toLowerCase()}</Badge>
            <span className="font-mono text-ink-mut">{property.record_version}</span>
          </div>
        </div>
      </div>

      <Tabs
        tabs={tabs}
        active={tab}
        onChange={(id) => setTab(id as TabId)}
      />

      <div className="pt-1">
        {tab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2 p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-black text-ink">Property snapshot</h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setIsEpoch2((v) => !v)}
                    title="Toggle before/after LiDAR Epoch-2 comparison"
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-none text-[11px] font-bold border-2 transition ${
                      isEpoch2
                        ? 'bg-red-600 text-white border-red-700'
                        : 'bg-canvas text-ink-soft border-ink hover:bg-canvas'
                    }`}
                  >
                    {isEpoch2 ? 'Epoch-2 delta ●' : 'Epoch-2 delta'}
                  </button>
                  <Badge tone="sky">3D twin · full</Badge>
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: 'Plot area', value: `${property.parcel.document_area_m2} m²` },
                  { label: 'Height', value: `${property.structure.height_m} m` },
                  { label: 'Floors', value: `${property.structure.floors_count} + ${property.structure.basements_count} B` },
                  { label: 'Built-up', value: `${property.structure.total_built_up_area_m2} m²` },
                  { label: 'Units', value: String(property.units.length) },
                  {
                    label: 'FSI',
                    value:
                      typeof property.fsi.calculated_fsi === 'number' && typeof property.fsi.max_allowed_fsi === 'number'
                        ? `${property.fsi.calculated_fsi} / ${property.fsi.max_allowed_fsi}`
                        : 'not assessed',
                  },
                ].map((s) => (
                  <div key={s.label} className="bg-canvas border-2 border-ink rounded-none px-3 py-2.5">
                    <div className="text-[10px] uppercase font-bold tracking-widest text-ink-mut">{s.label}</div>
                    <div className="font-mono text-sm font-black text-ink mt-0.5">{s.value}</div>
                  </div>
                ))}
              </div>

              {/* A structure the builder studio actually persisted: show the
                  real address, the submitter's own per-floor names/uses, and
                  the live reviewer status - labelled builder-asserted, not
                  surveyed, and with no invented units. */}
              {property.builder_record && (
                <div className="p-4 bg-canvas border-2 border-ink rounded-none space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ink">Builder-asserted record</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={property.structure.verification_status} />
                      {property.structure.provenance === 'demo-generated' && <Badge tone="amber">not surveyed</Badge>}
                    </div>
                  </div>
                  <p className="text-[10px] text-ink-mut">
                    The footprint, address and per-floor names below were declared by the submitter. No survey
                    authority has confirmed the geometry, and acceptance by a reviewer is an internal record decision,
                    not a government certification. {property.units.length === 0 ? 'No strata units exist on this record - a unit is a subdivision nobody has subdivided.' : ''}
                  </p>
                  {(property.address.line1 || property.address.locality) && (
                    <div className="text-[11px] font-mono text-ink">
                      {[property.address.line1, property.address.locality].filter(Boolean).join(', ')}
                    </div>
                  )}
                  {property.levels.length > 0 && (
                    <div>
                      <span className="block text-[10px] uppercase font-bold tracking-widest text-ink-mut mb-1">Per-floor names &amp; uses</span>
                      <div className="space-y-1">
                        {property.levels.map((lv, i) => (
                          <div key={`${lv.level_code}-${i}`} className="flex items-center gap-2 text-[11px]">
                            <code className="w-8 font-mono font-bold text-accent-strong">{lv.level_code}</code>
                            <span className="text-ink">{lv.name || <span className="text-ink-mut italic">unnamed</span>}</span>
                            <span className="text-ink-mut">· {lv.use || 'use not stated'}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="text-[10px] text-ink-mut font-mono">
                    receipt {property.builder_record.receipt_number}
                    {property.builder_record.decision && ` · ${property.builder_record.decision} by ${property.builder_record.reviewer_name}`}
                    {property.builder_record.basis && ` · basis: ${property.builder_record.basis}`}
                  </div>
                </div>
              )}

              {(property.fsi.calculated_fsi ?? 0) > 0 && (
                <FSIGauge fsi={property.fsi as FsiResult} />
              )}

              <div className="flex flex-wrap items-center justify-between gap-2 px-1 pt-1">
                <div className="flex items-center gap-1 bg-canvas border-2 border-ink rounded-none p-0.5">
                  <button
                    type="button"
                    onClick={() => setModelDisplayMode('strata')}
                    className={`px-2.5 py-1 rounded-none text-[11px] font-bold transition ${modelDisplayMode === 'strata' ? 'bg-accent text-ink shadow-xs' : 'text-ink-soft hover:text-ink'}`}
                  >
                    3D Strata
                  </button>
                  <button
                    type="button"
                    onClick={() => setModelDisplayMode('architectural')}
                    className={`px-2.5 py-1 rounded-none text-[11px] font-bold transition ${modelDisplayMode === 'architectural' ? 'bg-accent text-ink shadow-xs' : 'text-ink-soft hover:text-ink'}`}
                  >
                    3D Model
                  </button>
                  <button
                    type="button"
                    onClick={() => setModelDisplayMode('hybrid')}
                    className={`px-2.5 py-1 rounded-none text-[11px] font-bold transition ${modelDisplayMode === 'hybrid' ? 'bg-accent text-ink shadow-xs' : 'text-ink-soft hover:text-ink'}`}
                  >
                    Hybrid 3D
                  </button>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-ink-soft font-bold">Model:</span>
                  <select
                    aria-label="Proposal model"
                    value={proposalModel || ''}
                    onChange={(e) => {
                      setProposalModel(e.target.value || null);
                      if (modelDisplayMode === 'strata') setModelDisplayMode('hybrid');
                    }}
                    className="bg-canvas border-2 border-ink rounded-none px-2 py-1 text-[11px] font-mono text-ink outline-none focus:border-ink max-w-[10rem]"
                  >
                    {proposalTemplates.map((t) => <option key={t.id} value={t.url}>{t.name}</option>)}
                    {proposalAssets.map((a) => <option key={a.id} value={a.url}>{a.original_name}</option>)}
                  </select>
                </div>
              </div>

              <div className="h-[21rem] rounded-none overflow-hidden border-2 border-ink bg-canvas shadow-brutal-sm relative">
                <ThreeCadastralViewer
                  property={property}
                  selectedUnit={selectedUnit}
                  onSelectUnit={setSelectedUnit}
                  activeColorMode={activeColorMode}
                  undergroundMode={undergroundMode}
                  onToggleUnderground={() => setUndergroundMode(!undergroundMode)}
                  isEpoch2={isEpoch2}
                  highlightedIds={highlight?.ids || []}
                  compact
                  modelUrl={modelDisplayMode !== 'strata' ? proposalModel : null}
                  modelDisplayMode={modelDisplayMode}
                />
              </div>
              <div className="flex items-center justify-between gap-2 px-1 pt-1">
                <p className="text-[11px] text-ink-mut">
                  {property.structure?.name || property.structure?.building_code || 'Cadastral Twin'} · {property.units.length} units · {property.levels.length} levels · drag to orbit
                </p>
                <button
                  onClick={() => setTab('twin')}
                  className="text-xs font-bold text-accent-strong hover:underline flex items-center gap-1"
                >
                  <Building2 className="w-3.5 h-3.5" /> Full 3D Inspector →
                </button>
              </div>
            </Card>

            <div className="space-y-4">
              <Card className="p-4">
                <div className="flex items-center gap-2 text-sm font-bold text-ink font-display mb-3">
                  <Scale className="w-4 h-4 text-emerald-600" /> FSI compliance
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-ink-soft">Calculated FSI</span>
                  <span className="font-mono font-black text-ink">{property.fsi.calculated_fsi}</span>
                </div>
                <div className="flex items-center justify-between text-xs mt-2">
                  <span className="text-ink-soft">Permitted max</span>
                  <span className="font-mono font-black text-ink">{property.fsi.max_allowed_fsi}</span>
                </div>
                <div className="mt-3">
                  <StatusBadge status={property.fsi.status} />
                </div>
              </Card>

              <Card className="p-4">
                <div className="flex items-center gap-2 text-sm font-bold text-ink font-display mb-3">
                  <Fingerprint className="w-4 h-4 text-accent-strong" /> Cryptographic proof
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-ink-soft">Signature</span>
                  <Badge tone="slate">None</Badge>
                </div>
                <div className="mt-2 text-[10px] leading-relaxed bg-canvas border-2 border-ink rounded-none px-2.5 py-2 text-ink-soft font-sans">
                  {property.cryptographic_proof_note ??
                    'This deployment holds no signing key and signs nothing.'}
                </div>
              </Card>

              {property.epoch2_change && (
                <Card className="p-4 border-ink bg-amber-50/40">
                  <div className="flex items-center gap-2 text-sm font-bold text-amber-800 mb-2 font-display">
                    <AlertTriangle className="w-4 h-4" /> Multi-epoch change detected
                  </div>
                  <p className="text-xs text-amber-900/80 leading-relaxed">
                    {property.epoch2_change.delta_height_m > 0 ? '+' : ''}{property.epoch2_change.delta_height_m} m height and {property.epoch2_change.delta_floors} floor{property.epoch2_change.delta_floors !== 1 ? 's' : ''} added since the last surveyed epoch.
                  </p>
                  <button onClick={() => setTab('history')} className="mt-2 text-xs font-bold text-amber-700 hover:underline">
                    Review in time slider →
                  </button>
                </Card>
              )}
            </div>
          </div>
        )}

        {tab === 'twin' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[calc(100vh-22rem)] min-h-[32rem] overflow-hidden">
            <div className="lg:col-span-9 rounded-none overflow-hidden border-2 border-ink shadow-brutal-sm relative bg-canvas">
              <ThreeCadastralViewer
                property={property}
                selectedUnit={selectedUnit}
                onSelectUnit={setSelectedUnit}
                activeColorMode={activeColorMode}
                undergroundMode={undergroundMode}
                onToggleUnderground={() => setUndergroundMode(!undergroundMode)}
                isEpoch2={isEpoch2}
                highlightedIds={highlight?.ids || []}
                modelUrl={modelDisplayMode !== 'strata' ? proposalModel : null}
                modelDisplayMode={modelDisplayMode}
              />
              <div className="absolute top-2.5 right-2.5 flex items-center gap-2 z-10">
                <div className="flex items-center gap-1 bg-white/95 backdrop-blur rounded-none p-0.5 border-2 border-ink shadow-brutal-sm">
                  <button
                    type="button"
                    onClick={() => setModelDisplayMode('strata')}
                    className={`px-2 py-1 rounded-none text-[10px] font-bold transition ${modelDisplayMode === 'strata' ? 'bg-accent text-ink shadow-xs' : 'text-ink-soft hover:text-ink'}`}
                  >
                    Strata
                  </button>
                  <button
                    type="button"
                    onClick={() => setModelDisplayMode('architectural')}
                    className={`px-2 py-1 rounded-none text-[10px] font-bold transition ${modelDisplayMode === 'architectural' ? 'bg-accent text-ink shadow-xs' : 'text-ink-soft hover:text-ink'}`}
                  >
                    3D Model
                  </button>
                  <button
                    type="button"
                    onClick={() => setModelDisplayMode('hybrid')}
                    className={`px-2 py-1 rounded-none text-[10px] font-bold transition ${modelDisplayMode === 'hybrid' ? 'bg-accent text-ink shadow-xs' : 'text-ink-soft hover:text-ink'}`}
                  >
                    Hybrid
                  </button>
                </div>
                <select
                  aria-label="Proposal model"
                  value={proposalModel || ''}
                  onChange={(e) => {
                    setProposalModel(e.target.value || null);
                    if (modelDisplayMode === 'strata') setModelDisplayMode('hybrid');
                  }}
                  className="bg-canvas/95 backdrop-blur border-2 border-ink rounded-none px-1.5 py-1 text-[10px] font-mono text-ink outline-none focus:border-ink max-w-[9.5rem]"
                >
                  {proposalTemplates.map((t) => <option key={t.id} value={t.url}>{t.name}</option>)}
                  {proposalAssets.map((a) => <option key={a.id} value={a.url}>{a.original_name}</option>)}
                </select>
              </div>
            </div>
            <div className="lg:col-span-3 flex flex-col bg-chalk border-2 border-ink rounded-none overflow-hidden">
              <div className="px-3.5 py-2.5 text-xs font-bold text-ink bg-canvas border-b border-ink">Strata tree</div>
              <div className="flex-1 overflow-y-auto">
                <HierarchyTree property={property} selectedUnit={selectedUnit} onSelectUnit={setSelectedUnit} />
              </div>
            </div>
          </div>
        )}

        {tab === 'evidence' && (
          <Card>
            <EvidencePanel evidenceStreams={property.evidence_streams} />
          </Card>
        )}

        {tab === 'rules' && (
          <Card>
            <ValidationPanel validation={property.validation} />
          </Card>
        )}

        {tab === 'rights' && (
          <Card>
            <RightsPanel
              property={property}
              selectedUnit={selectedUnit}
              activeColorMode={activeColorMode}
              onColorModeChange={setActiveColorMode}
            />
          </Card>
        )}

        {tab === 'history' && (
          <Card>
            <HistoryTimeline property={property} isEpoch2={isEpoch2} onToggleEpoch={setIsEpoch2} />
          </Card>
        )}

        {tab === 'map2d' && (
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-ink bg-canvas">
              <span className="text-sm font-bold text-ink">Geographic context</span>
              <div className="flex items-center gap-1 bg-canvas border-2 border-ink rounded-none p-0.5">
                <button
                  type="button"
                  onClick={() => setMapBase('cadastre')}
                  className={`px-2.5 py-1 rounded-none text-[11px] font-bold transition-colors ${mapBase === 'cadastre' ? 'bg-accent text-chalk' : 'text-ink-soft hover:text-ink'}`}
                >
                  <span className="inline-flex items-center gap-1"><Globe2 className="w-3 h-3" /> Cadastre</span>
                </button>
                <button
                  type="button"
                  onClick={() => setMapBase('satellite')}
                  className={`px-2.5 py-1 rounded-none text-[11px] font-bold transition-colors ${mapBase === 'satellite' ? 'bg-accent text-chalk' : 'text-ink-soft hover:text-ink'}`}
                >
                  <span className="inline-flex items-center gap-1"><Satellite className="w-3 h-3" /> Satellite</span>
                </button>
              </div>
            </div>
            <div className="h-[28rem]">
              {mapBase === 'satellite' ? (
                <Suspense fallback={<div className="h-full flex items-center justify-center text-xs text-ink-soft">Loading satellite&hellip;</div>}>
                  <EsriSatelliteView markerLabel={property.parent_ulpin} />
                </Suspense>
              ) : (
                <Suspense fallback={<div className="h-full flex items-center justify-center text-xs text-ink-soft">Loading map&hellip;</div>}>
                  <MapLibreCadastreMap parcels={parcelsWithFallback(null, property)} selectedUlpin={property.parent_ulpin} />
                </Suspense>
              )}
            </div>
          </Card>
        )}
      </div>

      <QRVerificationModal isOpen={qrOpen} onClose={() => setQrOpen(false)} property={property} />
      <VerificationQueueModal isOpen={verifyOpen} onClose={() => setVerifyOpen(false)} onCaseUpdated={() => handleProcess()} />
      <AskTheMapModal isOpen={askOpen} onClose={() => setAskOpen(false)} />

      {/* Citizen objection modal — DPDP-compliant public channel */}
      {objectionOpen && (
        <div className="fixed inset-0 z-[9000] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setObjectionOpen(false)}>
          <div
            className="w-full max-w-md bg-chalk border-2 border-ink rounded-none p-5 shadow-brutal animate-rise-in space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-black text-ink">File an objection</h3>
                <p className="text-[11px] text-ink-soft mt-0.5">Reviewed by the Grievance Cell · {property?.parent_ulpin || HERO_ULPIN}</p>
              </div>
              <X className="w-4 h-4 text-ink-mut hover:text-ink cursor-pointer" onClick={() => setObjectionOpen(false)} />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-ink mb-1.5">Category</label>
              <select
                value={objectionCategory}
                onChange={(e) => setObjectionCategory(e.target.value)}
                className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-bold text-ink outline-none focus:border-ink"
              >
                <option value="Urban Development">Urban Development</option>
                <option value="Survey & Mapping">Survey & Mapping</option>
                <option value="Land Records">Land Records</option>
                <option value="Encroachment">Encroachment</option>
                <option value="Duplicates">Duplicate Record</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-ink mb-1.5">Description</label>
              <textarea
                rows={3}
                value={objectionNote}
                onChange={(e) => setObjectionNote(e.target.value)}
                placeholder="Describe the discrepancy you see in this record..."
                className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs text-ink outline-none focus:border-ink resize-none"
              />
            </div>
            {objectionError && <div className="text-[11px] font-bold text-red-600">{objectionError}</div>}
            <button
              onClick={submitObjection}
              disabled={objectionSubmitting}
              className="w-full py-2.5 rounded-none text-xs font-black text-ink bg-accent hover:bg-accent-strong disabled:opacity-50 transition shadow-brutal-sm"
            >
              {objectionSubmitting ? 'Submitting…' : 'Submit objection'}
            </button>
            <p className="text-[10px] text-ink-mut leading-relaxed">
              Your objection becomes a public case number (OBJ-XXXXX) visible in the audit trail. No contact data is stored beyond an optional email for status updates.
            </p>
          </div>
        </div>
      )}

      {/* LiDAR Inspection Instrument — Full-screen overlay */}
      {lidarOpen && (
        <div className="fixed inset-0 z-[9999] bg-[#05070d] animate-rise-in">
          <LiDARInspector
            initialULPIN={property?.parent_ulpin || HERO_ULPIN}
            autoFocusSelection
            onClose={() => setLidarOpen(false)}
          />
        </div>
      )}

      {/* Buyer Shield Audit Modal */}
      {buyerShieldOpen && (
        <BuyerShieldModal
          initialTarget={selectedUnit?.proposed_3d_id || property?.parent_ulpin || HERO_ULPIN}
          isOpen={buyerShieldOpen}
          onClose={() => setBuyerShieldOpen(false)}
        />
      )}

      {/* Demand Notice Modal */}
      {demandNoticeOpen && (
        <DemandNoticeModal
          buildingCode={property?.structure?.building_code || 'B-17'}
          isOpen={demandNoticeOpen}
          onClose={() => setDemandNoticeOpen(false)}
        />
      )}

      {/* Official Government 3D Deed & Monograph Print Modal */}
      {property && deedPrintOpen && (
        <GovernmentDeedPrintModal
          property={property}
          isOpen={deedPrintOpen}
          onClose={() => setDeedPrintOpen(false)}
        />
      )}
    </div>
  );
};

function parcelsWithFallback(parcel?: ParcelSummary | null, property?: HeroProperty | null): ParcelSummary[] {
  if (parcel) {
    // Was `parcel.ulpin === HERO_ULPIN ? { ...parcel, status: 'APPROVED' }`,
    // so being the demonstration parcel was enough to make a record approved.
    // The parcel now carries whatever status it actually has.
    const hero = parcel.ulpin === HERO_ULPIN ? { ...parcel } : parcel;
    const others = property ? [] : [];
    return [hero, ...others];
  }
  if (property) {
    return [
      {
        ulpin: property.parcel.ulpin,
        survey_number: property.parcel.survey_number,
        polygon_geojson: property.parcel.polygon_geojson,
        document_area_m2: property.parcel.document_area_m2,
        calculated_area_m2: property.parcel.calculated_area_m2,
        // The record's own status. This was a literal 'APPROVED', so a parcel
        // handed to the map claimed approval no matter what the source said.
        status: property.status,
      },
    ];
  }
  return [];
}

type FsiResult = {
  calculated_fsi?: number | null;
  max_allowed_fsi?: number | null;
  status?: string;
  utilization_pct?: number | null;
  inputs_authoritative?: boolean;
  assessable?: boolean;
  disclaimer?: string;
};

function FSIGauge({ fsi }: { fsi: FsiResult }) {
  const calculated = typeof fsi?.calculated_fsi === 'number' ? fsi.calculated_fsi : null;
  const max = typeof fsi?.max_allowed_fsi === 'number' && fsi.max_allowed_fsi > 0 ? fsi.max_allowed_fsi : null;

  // No rule on record, or inputs that are not authoritative: show the measured
  // ratio as descriptive only. A utilisation percentage and an over-permit
  // finding are compliance claims and need a real ceiling plus real inputs.
  if (calculated === null || max === null || fsi?.assessable === false) {
    return (
      <div className="rounded-none border-2 border-ink bg-canvas px-4 py-3">
        <div className="flex items-center justify-between text-[10px] font-mono text-ink-mut mb-1.5">
          <span className="uppercase font-bold tracking-widest flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-none bg-ink-faint" />
            FSI (not assessed)
          </span>
          {calculated !== null && <span className="font-black text-ink">ratio {calculated.toFixed(2)}</span>}
        </div>
        <p className="text-[10px] text-ink-soft">
          {fsi?.disclaimer ??
            'A floor space index verdict needs a permitted-FAR rule from the planning authority and authoritative built-up area. Neither is on record, so no compliance finding is issued.'}
        </p>
      </div>
    );
  }

  const actualPct = (calculated / max) * 100;
  const clampedPct = Math.min(100, Math.max(3, actualPct));
  const over = calculated > max;
  const tone = over ? 'bg-red-500' : actualPct > 90 ? 'bg-amber-500' : 'bg-emerald-500';
  return (
    <div className="rounded-none border-2 border-ink bg-canvas px-4 py-3">
      <div className="flex items-center justify-between text-[10px] font-mono text-ink-mut mb-1.5">
        <span className="uppercase font-bold tracking-widest flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-none ${over ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'}`} />
          FSI Utilisation
        </span>
        <span className="font-black text-ink">
          {Math.round(actualPct)}% of permitted {max.toFixed(1)}
          {over && <span className="ml-1 text-red-600 font-bold">(+{Math.round(actualPct - 100)}% over)</span>}
        </span>
      </div>
      <div className="h-2.5 rounded-none bg-ink/8 overflow-hidden">
        <div className={`h-full rounded-none ${tone} transition-all duration-500`} style={{ width: `${clampedPct}%` }} />
      </div>
      <div className="flex items-center justify-between text-[10px] font-mono text-ink-mut mt-1">
        <span>Measured: <strong className="text-ink font-bold">{calculated.toFixed(2)}</strong></span>
        <span>Sanctioned Ceiling: <strong className="text-ink font-bold">{max.toFixed(1)}</strong></span>
      </div>
      <p className="text-[10px] text-ink-soft mt-1.5">
        {over
          ? `Over-permit: measured ${calculated.toFixed(2)} exceeds the sanctioned ${max.toFixed(1)} FSI ceiling by ${Math.round(actualPct - 100)}% — flagged for compliance audit.`
          : `Measured ${calculated.toFixed(2)} is compliant with the ${max.toFixed(1)} FSI ceiling. ${actualPct > 90 ? 'Close to ceiling — monitor approvals.' : `${Math.round(100 - actualPct)}% headroom available.`}`}
      </p>
    </div>
  );
}
