import React, { useState } from 'react';
import {
  ScanLine,
  Crosshair,
  FileJson,
  Camera,
  Upload,
  AlertTriangle,
  LogIn,
  Info,
  Plus,
  Trash2,
  Landmark,
} from 'lucide-react';
import {
  POINT_CLOUD_ACCEPT,
  DRONE_IMAGE_ACCEPT,
  ingestPointCloud,
  ingestGnss,
  ingestParcelGeoJson,
  ingestDroneExif,
  type IngestProvenance,
  type PointCloudIngestResponse,
  type GnssIngestResponse,
  type ParcelGeoJsonIngestResponse,
  type DroneExifIngestResponse,
} from '../../services/ingestApi';
import { Card, Badge, Button, EmptyState, DemoHint } from '../../components/ui';
import { cn } from '../../lib/cn';
import { useApp } from '../../context/AppContext';
import { useTranslation } from '../../i18n/LanguageContext';
import type { TranslationDictionary } from '../../i18n/translations';

/** Substitutes {token} placeholders. Missing tokens are left visible rather
 *  than silently dropped, so a template error shows up in the UI. */
const fill = (template: string, vars: Record<string, string | number>): string =>
  template.replace(/\{([a-zA-Z]+)\}/g, (whole, key: string) =>
    key in vars ? String(vars[key]) : whole
  );

/* ------------------------------------------------------------------ */
/* Provenance rendering                                                */
/* ------------------------------------------------------------------ */

type ProvTone = 'blue' | 'green' | 'amber' | 'slate';

/**
 * The standing of a payload, in words, derived from the server's own
 * provenance block rather than from anything the page knows about the file.
 *
 * The ordering matters: `is_derived` is checked first because a real uploaded
 * file can still produce a modelled result, and a derived result is never
 * described as field input no matter how genuine the upload was. The two
 * `source` labels on the parcel route are checked next, since "authoritative"
 * there is an assertion by an authorised role, not something this deployment
 * verified against a registry.
 */
function classifyProvenance(
  p: IngestProvenance,
  t: TranslationDictionary['ingest']
): { label: string; tone: ProvTone; caveat: string } {
  if (p.is_derived) {
    return {
      label: t.toneDerivedLabel,
      tone: 'amber',
      caveat: t.toneDerivedCaveat,
    };
  }
  if (p.source === 'DRONE_IMAGE_EXIF') {
    // The service sets `is_real` / `has_authentic_source` on this route from
    // whether a GPS tag was found in the file, so they are the signal that the
    // image carried a position at all.
    return p.is_real
      ? {
          label: t.toneExifGpsLabel,
          tone: 'blue',
          caveat: t.toneExifGpsCaveat,
        }
      : {
          label: t.toneExifNoGpsLabel,
          tone: 'amber',
          caveat: t.toneExifNoGpsCaveat,
        };
  }
  if (p.source === 'AUTHORITATIVE') {
    return {
      label: t.toneAuthoritativeLabel,
      tone: 'green',
      caveat: t.toneAuthoritativeCaveat,
    };
  }
  if (p.source === 'BUILDER_ASSERTED') {
    return {
      label: t.toneBuilderAssertedLabel,
      tone: 'amber',
      caveat: t.toneBuilderAssertedCaveat,
    };
  }
  if (p.is_real && p.has_authentic_source) {
    return {
      label: t.toneRealInputLabel,
      tone: 'green',
      caveat: t.toneRealInputCaveat,
    };
  }
  return {
    label: t.toneUnknownLabel,
    tone: 'slate',
    caveat: t.toneUnknownCaveat,
  };
}

const MetaCell: React.FC<{ label: string; value: React.ReactNode; className?: string }> = ({
  label,
  value,
  className,
}) => (
  <div className={cn('p-2 rounded-none bg-chalk border-2 border-ink min-w-0', className)}>
    <div className="text-[9px] uppercase font-black tracking-widest text-ink-mut">{label}</div>
    <div className="text-[11px] font-mono font-bold text-ink break-words mt-0.5">{value}</div>
  </div>
);

const YesNo: React.FC<{ value: boolean | null | undefined; falseMeans?: string }> = ({
  value,
  falseMeans,
}) => {
  const { t } = useTranslation();
  const yes = Boolean(value);
  return (
    <span className={yes ? 'text-emerald-700' : 'text-crimson-600'}>
      {yes ? t.ingest.yes : falseMeans || t.ingest.no}
    </span>
  );
};

/**
 * The standing banner rendered above every result.
 *
 * Both the backend's own one-liner and the note are quoted verbatim; the caveat
 * underneath is the reader-facing consequence. Nothing here is inferred from
 * the file name or from a success flag, so a clean upload of a real file cannot
 * read as authoritative survey data.
 */
const ProvenancePanel: React.FC<{ provenance: IngestProvenance }> = ({ provenance: p }) => {
  const { t } = useTranslation();
  const ti = t.ingest;
  const headline = classifyProvenance(p, ti);
  return (
    <div
      className={cn(
        'p-3.5 rounded-none border-2 border-ink space-y-2.5',
        headline.tone === 'amber'
          ? 'bg-amber-50'
          : headline.tone === 'green'
            ? 'bg-emerald-50'
            : headline.tone === 'blue'
              ? 'bg-accent-faint'
              : 'bg-canvas'
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] uppercase font-black tracking-widest text-ink-mut flex items-center gap-1.5">
          <Info className="w-3.5 h-3.5" />
          {ti.provenanceHeading}
        </span>
        <Badge tone={headline.tone}>{headline.label}</Badge>
      </div>

      <p className="text-[11px] font-bold text-ink leading-relaxed font-mono">{p.provenance}</p>
      <p className="text-[10px] text-ink-soft leading-relaxed">{headline.caveat}</p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <MetaCell label={ti.fieldIsReal} value={<YesNo value={p.is_real} />} />
        <MetaCell label={ti.fieldIsDerived} value={<YesNo value={p.is_derived} />} />
        <MetaCell label={ti.fieldAuthenticSource} value={<YesNo value={p.has_authentic_source} />} />
        <MetaCell label={ti.fieldConfidenceTier} value={p.confidence_tier || ti.unspecified} />
        <MetaCell label={ti.fieldSource} value={p.source || ti.unspecified} />
        <MetaCell label={ti.fieldDataType} value={p.data_type || ti.unspecified} />
        <MetaCell
          label={ti.fieldDerivationMethod}
          value={p.derivation_method || ti.notApplicable}
          className="col-span-2"
        />
      </div>

      {p.provenance_note && (
        <p className="text-[10px] text-ink-soft leading-relaxed border-l-2 border-ink/30 pl-2">
          {p.provenance_note}
        </p>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Shared chrome                                                       */
/* ------------------------------------------------------------------ */

const labelClass = 'block text-[10px] font-black uppercase tracking-widest text-ink mb-1.5';
const inputClass =
  'w-full px-3 py-2 text-xs bg-chalk border-2 border-ink rounded-none text-ink placeholder:text-ink-mut outline-none focus:bg-accent-faint';
const fileClass =
  'text-xs text-ink-soft file:mr-3 file:py-1.5 file:px-3 file:rounded-none file:border-0 file:text-xs file:font-bold file:bg-accent file:text-ink hover:file:bg-accent/90 cursor-pointer';

/**
 * Errors are kept next to the form that caused them rather than only in the
 * global toast, because a failed upload with no visible cause looks like a
 * button that does nothing. A 401 additionally offers the sign-in the shell
 * owns, matching the pattern used where the analytics demand notice hits the
 * same wall.
 */
const ErrorNotice: React.FC<{ error: string; status?: number }> = ({ error, status }) => {
  const { t } = useTranslation();
  return (
    <div className="p-3 rounded-none bg-crimson-50 border-2 border-ink text-xs text-crimson-700">
      <p className="font-bold flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-px" />
        <span>{status === 401 ? t.ingest.errorSignInTitle : t.ingest.errorRejectedTitle}</span>
      </p>
      <p className="mt-1 font-mono leading-relaxed break-words">{error}</p>
      {status === 401 && (
        <button
          onClick={() => window.dispatchEvent(new Event('bhudrishti:request-signin'))}
          className="mt-2.5 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-white bg-ink border-2 border-ink hover:bg-accent hover:text-ink transition"
        >
          <LogIn className="w-3.5 h-3.5" /> {t.ingest.signIn}
        </button>
      )}
    </div>
  );
};

const ResultShell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="space-y-3 pt-1 animate-rise-in">
    {children}
  </div>
);

/**
 * One capability per card, with its standing printed on the card itself.
 *
 * The standing is stated *before* anything is uploaded so the reader knows what
 * the section will produce, rather than only learning it from a provenance
 * banner after the fact.
 */
const IngestSection: React.FC<{
  icon: React.ReactNode;
  title: string;
  endpoint: string;
  standing: string;
  standingTone: ProvTone;
  children: React.ReactNode;
}> = ({ icon, title, endpoint, standing, standingTone, children }) => (
  <Card className="p-5 space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3 pb-3 border-b border-ink">
      <div className="flex items-start gap-3 min-w-0">
        <span className="w-10 h-10 rounded-none bg-accent-faint border-2 border-ink flex items-center justify-center shrink-0">
          {icon}
        </span>
        <div className="min-w-0">
          <h2 className="text-sm font-black text-ink">{title}</h2>
          <div className="text-[10px] font-mono text-ink-mut mt-0.5 break-all">POST {endpoint}</div>
        </div>
      </div>
      <Badge tone={standingTone}>{standing}</Badge>
    </div>
    {children}
  </Card>
);

/* ------------------------------------------------------------------ */
/* GNSS point rows                                                     */
/* ------------------------------------------------------------------ */

type GnssRow = { lat: string; lon: string; elev: string; name: string };

const EMPTY_ROW: GnssRow = { lat: '', lon: '', elev: '', name: '' };

/** The service rejects anything outside India; checked here so the point at
 *  fault is named before the round trip instead of in a 422 detail. */
const IN_LAT = [6.0, 37.0];
const IN_LON = [68.0, 97.5];

function parseGnssRows(
  rows: GnssRow[],
  t: TranslationDictionary['ingest']['gnss']
): { points?: Array<{ lat: number; lon: number; elev?: number; name?: string }>; error?: string } {
  const filled = rows.filter((r) => r.lat.trim() !== '' || r.lon.trim() !== '');
  if (filled.length < 3) return { error: t.errorTooFew };

  const points: Array<{ lat: number; lon: number; elev?: number; name?: string }> = [];
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const hasLat = r.lat.trim() !== '';
    const hasLon = r.lon.trim() !== '';
    if (!hasLat && !hasLon) continue;

    const lat = Number(r.lat);
    const lon = Number(r.lon);
    const n = { n: i + 1 };
    if (!hasLat || !hasLon) return { error: fill(t.errorBothCoords, n) };
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return { error: fill(t.errorNotNumbers, n) };
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return { error: fill(t.errorOutOfRange, n) };
    if (lat < IN_LAT[0] || lat > IN_LAT[1] || lon < IN_LON[0] || lon > IN_LON[1])
      return {
        error: fill(t.errorOutsideIndia, {
          ...n,
          lat,
          lon,
          minLat: IN_LAT[0],
          maxLat: IN_LAT[1],
          minLon: IN_LON[0],
          maxLon: IN_LON[1],
        }),
      };

    const point: { lat: number; lon: number; elev?: number; name?: string } = { lat, lon };
    if (r.elev.trim() !== '' && Number.isFinite(Number(r.elev))) point.elev = Number(r.elev);
    if (r.name.trim() !== '') point.name = r.name.trim();
    points.push(point);
  }
  return { points };
}

const SAMPLE_POINTS: GnssRow[] = [
  { lat: '19.070000', lon: '72.870000', elev: '12.5', name: 'NW' },
  { lat: '19.070000', lon: '72.876000', elev: '13.1', name: 'NE' },
  { lat: '19.075000', lon: '72.876000', elev: '11.8', name: 'SE' },
  { lat: '19.075000', lon: '72.870000', elev: '12.2', name: 'SW' },
];

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export const IngestPage: React.FC = () => {
  const { role, permissions, user, showToast } = useApp();
  const { t } = useTranslation();
  const ti = t.ingest;

  /* --- point cloud --- */
  const [pcFile, setPcFile] = useState<File | null>(null);
  const [pcDataset, setPcDataset] = useState('user-upload');
  const [pcSubmission, setPcSubmission] = useState('');
  const [pcGroundZ, setPcGroundZ] = useState('0');
  const [pcBusy, setPcBusy] = useState(false);
  const [pcError, setPcError] = useState<{ text: string; status?: number } | null>(null);
  const [pcResult, setPcResult] = useState<PointCloudIngestResponse | null>(null);

  /* --- gnss --- */
  const [gnssRows, setGnssRows] = useState<GnssRow[]>([{ ...EMPTY_ROW }, { ...EMPTY_ROW }, { ...EMPTY_ROW }]);
  const [gnssDescription, setGnssDescription] = useState('');
  const [gnssSubmission, setGnssSubmission] = useState('');
  const [gnssBusy, setGnssBusy] = useState(false);
  const [gnssError, setGnssError] = useState<{ text: string; status?: number } | null>(null);
  const [gnssResult, setGnssResult] = useState<GnssIngestResponse | null>(null);

  /* --- parcel geojson --- */
  const [geojsonText, setGeojsonText] = useState('');
  const [geojsonFile, setGeojsonFile] = useState<string | null>(null);
  const [geojsonAuthoritative, setGeojsonAuthoritative] = useState(false);
  const [geojsonSource, setGeojsonSource] = useState('');
  const [geojsonSubmission, setGeojsonSubmission] = useState('');
  const [geojsonBusy, setGeojsonBusy] = useState(false);
  const [geojsonError, setGeojsonError] = useState<{ text: string; status?: number } | null>(null);
  const [geojsonResult, setGeojsonResult] = useState<ParcelGeoJsonIngestResponse | null>(null);

  /* --- drone exif --- */
  const [exifFile, setExifFile] = useState<File | null>(null);
  const [exifBusy, setExifBusy] = useState(false);
  const [exifError, setExifError] = useState<{ text: string; status?: number } | null>(null);
  const [exifResult, setExifResult] = useState<DroneExifIngestResponse | null>(null);

  const mayAssertAuthority = permissions.canSetPolicy || permissions.canApprove;

  const handlePointCloud = async () => {
    if (!pcFile) {
      setPcError({ text: ti.pointCloud.errorNoFile });
      return;
    }
    setPcBusy(true);
    setPcError(null);
    setPcResult(null);
    try {
      const res = await ingestPointCloud({
        file: pcFile,
        dataset_name: pcDataset.trim() || 'user-upload',
        submission_id: pcSubmission.trim() || undefined,
        ground_z: Number.isFinite(Number(pcGroundZ)) ? Number(pcGroundZ) : 0,
      });
      setPcResult(res);
      showToast(fill(ti.pointCloud.toast, { file: res.file_name, format: res.format }));
    } catch (e) {
      const err = e as Error & { status?: number };
      setPcError({ text: err.message || ti.pointCloud.errorFailed, status: err.status });
    } finally {
      setPcBusy(false);
    }
  };

  const handleGnss = async () => {
    const parsed = parseGnssRows(gnssRows, ti.gnss);
    if (!parsed.points) {
      setGnssError({ text: parsed.error || ti.gnss.errorGeneric });
      return;
    }
    setGnssBusy(true);
    setGnssError(null);
    setGnssResult(null);
    try {
      const res = await ingestGnss({
        points: parsed.points,
        description: gnssDescription.trim() || undefined,
        submission_id: gnssSubmission.trim() || undefined,
      });
      setGnssResult(res);
      showToast(fill(ti.gnss.toast, { n: res.point_count }));
    } catch (e) {
      const err = e as Error & { status?: number };
      setGnssError({ text: err.message || ti.gnss.errorFailed, status: err.status });
    } finally {
      setGnssBusy(false);
    }
  };

  const handleGeojsonFile = async (file: File | null) => {
    if (!file) return;
    try {
      const text = await file.text();
      setGeojsonText(text);
      setGeojsonFile(file.name);
      setGeojsonError(null);
    } catch {
      setGeojsonError({ text: ti.geojson.errorUnreadable });
    }
  };

  const handleGeojson = async () => {
    if (!geojsonText.trim()) {
      setGeojsonError({ text: ti.geojson.errorNoPayload });
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(geojsonText);
    } catch {
      setGeojsonError({ text: ti.geojson.errorInvalidJson });
      return;
    }
    if (!parsed || typeof parsed !== 'object') {
      setGeojsonError({ text: ti.geojson.errorNotObject });
      return;
    }
    if (geojsonAuthoritative && !geojsonSource.trim()) {
      // The authoritative flag is an assertion about the source, so the source
      // is required alongside it: an authoritative record with no stated origin
      // is exactly the claim this page exists to make impossible to make by
      // accident.
      setGeojsonError({ text: ti.geojson.errorAuthorityNeedsSource });
      return;
    }

    setGeojsonBusy(true);
    setGeojsonError(null);
    setGeojsonResult(null);
    try {
      const res = await ingestParcelGeoJson({
        geojson: parsed as Record<string, any>,
        is_authoritative: geojsonAuthoritative,
        source: geojsonSource.trim() || undefined,
        submission_id: geojsonSubmission.trim() || undefined,
      });
      setGeojsonResult(res);
      // A missing rejection list must never read as "nothing was dropped". The
      // service defaults the field to an empty array, so an absent one means the
      // count is unknown — and that is what the toast says.
      const rejected = Array.isArray(res.rejected_features) ? res.rejected_features : null;
      const counts = { valid: res.valid_count, total: res.feature_count };
      showToast(
        rejected === null
          ? fill(ti.geojson.toastNoList, counts)
          : rejected.length > 0
            ? fill(ti.geojson.toastRejected, { ...counts, rejected: rejected.length })
            : fill(ti.geojson.toastImported, { ...counts, source: res.provenance.source })
      );
    } catch (e) {
      const err = e as Error & { status?: number };
      setGeojsonError({ text: err.message || ti.geojson.errorFailed, status: err.status });
    } finally {
      setGeojsonBusy(false);
    }
  };

  const handleDroneExif = async () => {
    if (!exifFile) {
      setExifError({ text: ti.drone.errorNoFile });
      return;
    }
    setExifBusy(true);
    setExifError(null);
    setExifResult(null);
    try {
      const res = await ingestDroneExif(exifFile);
      setExifResult(res);
      showToast(
        fill(res.has_gps ? ti.drone.toastGps : ti.drone.toastNoGps, { file: res.file_name })
      );
    } catch (e) {
      const err = e as Error & { status?: number };
      setExifError({ text: err.message || ti.drone.errorFailed, status: err.status });
    } finally {
      setExifBusy(false);
    }
  };

  /* --- gate: ingestion is an administrative / reviewer action --- */
  if (!permissions.canIngest) {
    return (
      <div className="flex flex-col gap-5 animate-rise-in">
        <div>
          <div className="flex items-center gap-2 annotation text-accent-strong">
            <span className="text-accent-strong">{role.replace('_', ' ')}</span>
            <span>/</span>
            <span>{ti.breadcrumb}</span>
          </div>
          <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">{ti.title}</h1>
          <p className="text-sm text-ink-soft mt-1">{ti.introRestricted}</p>
        </div>

        <Card className="p-5">
          <EmptyState
            icon={<Landmark className="w-5 h-5" />}
            title={ti.restrictedTitle}
            description={permissions.canSubmit ? ti.restrictedBuilder : ti.restrictedOther}
            action={
              !user ? (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => window.dispatchEvent(new Event('bhudrishti:request-signin'))}
                >
                  <LogIn className="w-3.5 h-3.5" /> {ti.signInReviewer}
                </Button>
              ) : (
                <span className="font-mono text-[10px] text-ink-mut">
                  {ti.signedInAs} {user.full_name} · {permissions.label}
                </span>
              )
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 animate-rise-in">
      {/* ================================================================== */}
      {/* HEADER                                                             */}
      {/* ================================================================== */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 annotation text-accent-strong">
            <span className="text-accent-strong">{role.replace('_', ' ')}</span>
            <span>/</span>
            <span>{ti.breadcrumb}</span>
          </div>
          <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">{ti.title}</h1>
          <p className="text-sm text-ink-soft mt-1">{ti.intro}</p>
        </div>
        <DemoHint />
      </div>

      {/* Standing rules, stated before any upload so no section is read as
          more than it is. */}
      <div className="p-3.5 bg-canvas border-2 border-ink space-y-2">
        <div className="text-[10px] uppercase font-black tracking-widest text-ink-mut">
          {ti.standingHeading}
        </div>
        <ul className="text-[11px] text-ink-soft leading-relaxed space-y-1 list-disc pl-4">
          <li>
            <strong className="text-ink">{ti.standingPointCloudLabel}</strong>
            {ti.standingPointCloudText} <strong className="text-ink">{ti.standingPointCloudModelled}</strong>.{' '}
            {ti.standingPointCloudTail}
          </li>
          <li>
            <strong className="text-ink">{ti.standingGnssLabel}</strong>
            {ti.standingGnssText}
          </li>
          <li>
            <strong className="text-ink">{ti.standingGeojsonLabel}</strong>
            {ti.standingGeojsonText}
          </li>
          <li>
            <strong className="text-ink">{ti.standingDroneLabel}</strong>
            {ti.standingDroneText}
          </li>
        </ul>
      </div>

      {/* ================================================================== */}
      {/* 1. POINT CLOUD                                                     */}
      {/* ================================================================== */}
      <IngestSection
        icon={<ScanLine className="w-5 h-5 text-accent-strong" />}
        title={ti.pointCloud.title}
        endpoint="/api/v1/ingest/point-cloud"
        standing={ti.pointCloud.standing}
        standingTone="amber"
      >
        <div className="p-4 rounded-none bg-canvas border-2 border-ink space-y-3">
          <div>
            <label className={labelClass} htmlFor="pc-file">
              {ti.pointCloud.fileLabel}
            </label>
            <input
              id="pc-file"
              type="file"
              accept={POINT_CLOUD_ACCEPT}
              onChange={(e) => {
                setPcFile(e.target.files?.[0] || null);
                setPcError(null);
              }}
              disabled={pcBusy}
              className={fileClass}
            />
            {pcFile && (
              <div className="mt-1.5 text-[10px] font-mono text-ink-mut">
                {pcFile.name} · {(pcFile.size / 1024).toFixed(1)} KB
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className={labelClass} htmlFor="pc-dataset">
                {ti.pointCloud.datasetLabel}
              </label>
              <input
                id="pc-dataset"
                type="text"
                value={pcDataset}
                onChange={(e) => setPcDataset(e.target.value)}
                placeholder="user-upload"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="pc-submission">
                {ti.pointCloud.submissionLabel}
              </label>
              <input
                id="pc-submission"
                type="text"
                value={pcSubmission}
                onChange={(e) => setPcSubmission(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="pc-ground">
                {ti.pointCloud.groundZLabel}
              </label>
              <input
                id="pc-ground"
                type="number"
                step="0.01"
                value={pcGroundZ}
                onChange={(e) => setPcGroundZ(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <p className="text-[10px] text-ink-soft leading-relaxed max-w-xl">
              {ti.pointCloud.groundZNote}
            </p>
            <Button variant="primary" size="sm" onClick={handlePointCloud} disabled={pcBusy}>
              <Upload className="w-3.5 h-3.5" />
              {pcBusy ? ti.pointCloud.submitBusy : ti.pointCloud.submit}
            </Button>
          </div>
        </div>

        {pcError && <ErrorNotice error={pcError.text} status={pcError.status} />}

        {pcResult && (
          <ResultShell>
            {pcResult.result?.error && (
              <div className="p-3 rounded-none bg-crimson-50 border-2 border-ink text-xs text-crimson-700">
                <p className="font-bold flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  {ti.pointCloud.pipelineFailedTitle}
                </p>
                <p className="mt-1 font-mono break-words">{String(pcResult.result.error)}</p>
                <p className="mt-1 text-[10px] leading-relaxed">
                  {ti.pointCloud.pipelineFailedBody}
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <MetaCell label={ti.pointCloud.fieldAssetId} value={pcResult.asset_id} />
              <MetaCell label={ti.pointCloud.fieldDatasetId} value={pcResult.dataset_id} />
              <MetaCell label={ti.pointCloud.fieldFile} value={pcResult.file_name} />
              <MetaCell label={ti.pointCloud.fieldFormat} value={pcResult.format} />
              <MetaCell label={ti.pointCloud.fieldSize} value={`${(pcResult.size_bytes / 1024).toFixed(1)} KB`} />
              <MetaCell
                label={ti.pointCloud.fieldSha256}
                value={<span title={pcResult.file_sha256}>{pcResult.file_sha256.slice(0, 16)}…</span>}
                className="col-span-2"
              />
              <MetaCell
                label={ti.pointCloud.fieldPipelineOutput}
                value={pcResult.result?.error ? ti.pointCloud.outputNone : ti.pointCloud.outputCompleted}
              />
            </div>

            <ProvenancePanel provenance={pcResult.provenance} />

            {pcResult.result && !pcResult.result.error && (
              <details className="rounded-none border-2 border-ink bg-canvas">
                <summary className="px-3 py-2 text-[10px] font-black uppercase tracking-widest text-ink cursor-pointer">
                  {ti.pointCloud.resultDisclosure}
                </summary>
                <pre className="px-3 pb-3 max-h-48 overflow-auto text-[10px] font-mono text-ink-soft whitespace-pre-wrap break-words">
                  {JSON.stringify(pcResult.result, null, 2)}
                </pre>
              </details>
            )}
          </ResultShell>
        )}
      </IngestSection>

      {/* ================================================================== */}
      {/* 2. GNSS SURVEY POINTS                                              */}
      {/* ================================================================== */}
      <IngestSection
        icon={<Crosshair className="w-5 h-5 text-accent-strong" />}
        title={ti.gnss.title}
        endpoint="/api/v1/ingest/gnss"
        standing={ti.gnss.standing}
        standingTone="green"
      >
        <div className="p-4 rounded-none bg-canvas border-2 border-ink space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[520px]">
              <thead>
                <tr className="text-left text-[9px] uppercase font-black tracking-widest text-ink-mut border-b border-ink">
                  <th className="py-2 pr-2">{ti.gnss.colIndex}</th>
                  <th className="py-2 pr-2">{ti.gnss.colLat}</th>
                  <th className="py-2 pr-2">{ti.gnss.colLon}</th>
                  <th className="py-2 pr-2">{ti.gnss.colElev}</th>
                  <th className="py-2 pr-2">{ti.gnss.colName}</th>
                  <th className="py-2 w-8" />
                </tr>
              </thead>
              <tbody>
                {gnssRows.map((r, i) => (
                  <tr key={i} className="border-b border-ink/10">
                    <td className="py-1.5 pr-2 font-mono text-[10px] text-ink-mut">{i + 1}</td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={r.lat}
                        onChange={(e) =>
                          setGnssRows((prev) => prev.map((row, j) => (j === i ? { ...row, lat: e.target.value } : row)))
                        }
                        placeholder="19.0700"
                        className={inputClass}
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={r.lon}
                        onChange={(e) =>
                          setGnssRows((prev) => prev.map((row, j) => (j === i ? { ...row, lon: e.target.value } : row)))
                        }
                        placeholder="72.8700"
                        className={inputClass}
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={r.elev}
                        onChange={(e) =>
                          setGnssRows((prev) => prev.map((row, j) => (j === i ? { ...row, elev: e.target.value } : row)))
                        }
                        className={inputClass}
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="text"
                        value={r.name}
                        onChange={(e) =>
                          setGnssRows((prev) => prev.map((row, j) => (j === i ? { ...row, name: e.target.value } : row)))
                        }
                        className={inputClass}
                      />
                    </td>
                    <td className="py-1.5">
                      <button
                        onClick={() => setGnssRows((prev) => prev.filter((_, j) => j !== i))}
                        disabled={gnssRows.length <= 1}
                        className="p-1.5 rounded-none border-2 border-ink bg-chalk text-ink-soft hover:bg-crimson-50 hover:text-crimson-600 disabled:opacity-40 transition"
                        aria-label={fill(ti.gnss.removePoint, { n: i + 1 })}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass} htmlFor="gnss-desc">
                {ti.gnss.descriptionLabel}
              </label>
              <input
                id="gnss-desc"
                type="text"
                value={gnssDescription}
                onChange={(e) => setGnssDescription(e.target.value)}
                placeholder={ti.gnss.descriptionPlaceholder}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="gnss-sub">
                {ti.gnss.submissionLabel}
              </label>
              <input
                id="gnss-sub"
                type="text"
                value={gnssSubmission}
                onChange={(e) => setGnssSubmission(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setGnssRows((prev) => [...prev, { ...EMPTY_ROW }])}
                disabled={gnssBusy}
              >
                <Plus className="w-3.5 h-3.5" /> {ti.gnss.addPoint}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setGnssRows(SAMPLE_POINTS.map((r) => ({ ...r })));
                  setGnssError(null);
                }}
                disabled={gnssBusy}
              >
                {ti.gnss.loadSample}
              </Button>
            </div>
            <Button variant="primary" size="sm" onClick={handleGnss} disabled={gnssBusy}>
              <Crosshair className="w-3.5 h-3.5" />
              {gnssBusy ? ti.gnss.submitBusy : ti.gnss.submit}
            </Button>
          </div>
        </div>

        {gnssError && <ErrorNotice error={gnssError.text} status={gnssError.status} />}

        {gnssResult && (
          <ResultShell>
            {gnssResult.warning && (
              <div className="p-3 rounded-none bg-amber-50 border-2 border-ink text-xs text-amber-800">
                <p className="font-bold">{ti.gnss.warningTitle}</p>
                <p className="mt-0.5 font-mono break-words">{gnssResult.warning}</p>
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <MetaCell label={ti.gnss.fieldPoints} value={gnssResult.point_count} />
              <MetaCell label={ti.gnss.fieldGeometry} value={gnssResult.geometry_type} />
              <MetaCell
                label={ti.gnss.fieldArea}
                value={gnssResult.area_m2 === null ? ti.gnss.notComputed : `${gnssResult.area_m2.toFixed(2)} m²`}
              />
              <MetaCell
                label={ti.gnss.fieldPerimeter}
                value={gnssResult.perimeter_m === null ? ti.gnss.notComputed : `${gnssResult.perimeter_m.toFixed(2)} m`}
              />
              <MetaCell
                label={ti.gnss.fieldCentroid}
                value={gnssResult.centroid ? gnssResult.centroid.map((v) => v.toFixed(6)).join(', ') : '—'}
                className="col-span-2"
              />
              <MetaCell label={ti.gnss.fieldCrs} value={gnssResult.crs} className="col-span-2" />
            </div>

            <div className="p-2.5 rounded-none bg-canvas border-2 border-ink">
              <div className="text-[9px] uppercase font-black tracking-widest text-ink-mut">
                {ti.gnss.computationMethod}
              </div>
              <div className="text-[11px] font-mono text-ink mt-0.5">{gnssResult.computation_method}</div>
            </div>

            <ProvenancePanel provenance={gnssResult.provenance} />
          </ResultShell>
        )}
      </IngestSection>

      {/* ================================================================== */}
      {/* 3. PARCEL GEOJSON                                                  */}
      {/* ================================================================== */}
      <IngestSection
        icon={<FileJson className="w-5 h-5 text-accent-strong" />}
        title={ti.geojson.title}
        endpoint="/api/v1/ingest/parcel-geojson"
        standing={geojsonAuthoritative ? ti.geojson.standingAuthoritative : ti.geojson.standingAsserted}
        standingTone={geojsonAuthoritative ? 'green' : 'amber'}
      >
        <div className="p-4 rounded-none bg-canvas border-2 border-ink space-y-3">
          <div>
            <label className={labelClass} htmlFor="gj-file">
              {ti.geojson.fileLabel}
            </label>
            <input
              id="gj-file"
              type="file"
              accept=".geojson,.json,application/geo+json,application/json"
              onChange={(e) => handleGeojsonFile(e.target.files?.[0] || null)}
              disabled={geojsonBusy}
              className={fileClass}
            />
            {geojsonFile && (
              <div className="mt-1.5 text-[10px] font-mono text-ink-mut">{ti.geojson.loadedPrefix} {geojsonFile}</div>
            )}
          </div>

          <div>
            <label className={labelClass} htmlFor="gj-text">
              {ti.geojson.payloadLabel}
            </label>
            <textarea
              id="gj-text"
              value={geojsonText}
              onChange={(e) => setGeojsonText(e.target.value)}
              placeholder={'{\n  "type": "FeatureCollection",\n  "features": []\n}'}
              rows={6}
              disabled={geojsonBusy}
              className="w-full p-3 border-2 border-ink rounded-none text-[11px] font-mono bg-chalk text-ink placeholder:text-ink-mut outline-none focus:bg-accent-faint"
            />
          </div>

          <div className="space-y-2.5">
            {mayAssertAuthority ? (
              <label className="flex items-start gap-2.5 p-2.5 rounded-none bg-canvas border-2 border-ink cursor-pointer">
                <input
                  type="checkbox"
                  checked={geojsonAuthoritative}
                  onChange={(e) => setGeojsonAuthoritative(e.target.checked)}
                  disabled={geojsonBusy}
                  className="mt-0.5 w-4 h-4 accent-black"
                />
                <span className="text-[11px] text-ink leading-relaxed">
                  <strong className="font-black">{ti.geojson.authorityLead}</strong>{' '}
                  {ti.geojson.authorityBody}
                </span>
              </label>
            ) : (
              <div className="p-2.5 rounded-none bg-canvas border-2 border-dashed border-ink text-[11px] text-ink-soft leading-relaxed">
                {ti.geojson.authorityDenied}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelClass} htmlFor="gj-source">
                  {geojsonAuthoritative ? ti.geojson.sourceRequired : ti.geojson.sourceOptional}
                </label>
                <input
                  id="gj-source"
                  type="text"
                  value={geojsonSource}
                  onChange={(e) => setGeojsonSource(e.target.value)}
                  placeholder={geojsonAuthoritative ? 'e.g. State registry extract, ref 12/A/2026' : ti.unspecified}
                  disabled={geojsonBusy}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="gj-sub">
                  {ti.geojson.submissionLabel}
                </label>
                <input
                  id="gj-sub"
                  type="text"
                  value={geojsonSubmission}
                  onChange={(e) => setGeojsonSubmission(e.target.value)}
                  disabled={geojsonBusy}
                  className={inputClass}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <p className="text-[10px] text-ink-soft leading-relaxed max-w-xl">
              {ti.geojson.boundsNote}
            </p>
            <Button variant="primary" size="sm" onClick={handleGeojson} disabled={geojsonBusy}>
              <FileJson className="w-3.5 h-3.5" />
              {geojsonBusy ? ti.geojson.submitBusy : ti.geojson.submit}
            </Button>
          </div>
        </div>

        {geojsonError && <ErrorNotice error={geojsonError.text} status={geojsonError.status} />}

        {geojsonResult && (() => {
          /* An absent list is not an empty one. Treating a missing
             `rejected_features` as "nothing dropped" would be the one thing this
             panel exists to prevent, so the three cases stay distinct. */
          const rejected = Array.isArray(geojsonResult.rejected_features) ? geojsonResult.rejected_features : null;
          return (
          <ResultShell>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <MetaCell label={ti.geojson.fieldFeaturesSent} value={geojsonResult.feature_count} />
              <MetaCell label={ti.geojson.fieldImported} value={geojsonResult.valid_count} />
              <MetaCell
                label={ti.geojson.fieldRejected}
                value={
                  <span className={rejected && rejected.length > 0 ? 'text-crimson-600' : undefined}>
                    {rejected === null ? ti.geojson.unknown : rejected.length}
                  </span>
                }
              />
              <MetaCell
                label={ti.geojson.fieldTotalArea}
                value={geojsonResult.area_m2 === null ? ti.gnss.notComputed : `${geojsonResult.area_m2.toFixed(2)} m²`}
              />
            </div>

            {rejected && rejected.length > 0 ? (
              <div className="p-3 rounded-none bg-crimson-50 border-2 border-ink space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-crimson-700">
                  <AlertTriangle className="w-4 h-4" />
                  {fill(ti.geojson.rejectedBanner, { rejected: rejected.length, total: geojsonResult.feature_count })}
                </div>
                <p className="text-[10px] text-crimson-700 leading-relaxed">
                  {fill(ti.geojson.rejectedBody, { total: geojsonResult.feature_count })}
                </p>
                <ul className="space-y-1">
                  {rejected.map((rj, i) => (
                    <li
                      key={`${rj.index}-${i}`}
                      className="p-2 bg-chalk border-2 border-ink text-[10px] font-mono text-ink flex flex-wrap items-baseline gap-x-2"
                    >
                      <span className="font-black">feature[{rj.index}]</span>
                      <span className="text-crimson-700 break-words">{rj.reason}</span>
                      {rj.vertex && (
                        <span className="text-ink-mut">
                          {fill(ti.geojson.rejectedVertex, { coords: rj.vertex.map((v) => v.toFixed(4)).join(', ') })}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ) : rejected === null ? (
              <div className="p-3 rounded-none bg-amber-50 border-2 border-ink text-[11px] text-amber-800 leading-relaxed">
                {fill(ti.geojson.unknownListBody, { total: geojsonResult.feature_count })}
              </div>
            ) : (
              <div className="p-2.5 rounded-none bg-canvas border-2 border-ink text-[10px] text-ink-soft">
                {fill(ti.geojson.noneRejected, { valid: geojsonResult.valid_count })}
              </div>
            )}

            <ProvenancePanel provenance={geojsonResult.provenance} />
          </ResultShell>
          );
        })()}
      </IngestSection>

      {/* ================================================================== */}
      {/* 4. DRONE IMAGE EXIF                                                */}
      {/* ================================================================== */}
      <IngestSection
        icon={<Camera className="w-5 h-5 text-accent-strong" />}
        title={ti.drone.title}
        endpoint="/api/v1/ingest/drone-exif"
        standing={ti.drone.standing}
        standingTone="blue"
      >
        <div className="p-4 rounded-none bg-canvas border-2 border-ink space-y-3">
          <div>
            <label className={labelClass} htmlFor="exif-file">
              {ti.drone.fileLabel}
            </label>
            <input
              id="exif-file"
              type="file"
              accept={DRONE_IMAGE_ACCEPT}
              onChange={(e) => {
                setExifFile(e.target.files?.[0] || null);
                setExifError(null);
              }}
              disabled={exifBusy}
              className={fileClass}
            />
            {exifFile && (
              <div className="mt-1.5 text-[10px] font-mono text-ink-mut">
                {exifFile.name} · {(exifFile.size / 1024).toFixed(1)} KB
              </div>
            )}
          </div>

          <p className="text-[10px] text-ink-soft leading-relaxed">
            {ti.drone.metadataNote}
          </p>

          <div className="flex justify-end pt-1">
            <Button variant="primary" size="sm" onClick={handleDroneExif} disabled={exifBusy}>
              <Camera className="w-3.5 h-3.5" />
              {exifBusy ? ti.drone.submitBusy : ti.drone.submit}
            </Button>
          </div>
        </div>

        {exifError && <ErrorNotice error={exifError.text} status={exifError.status} />}

        {exifResult && (
          <ResultShell>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={exifResult.has_gps ? 'blue' : 'amber'}>
                {exifResult.has_gps ? ti.drone.badgeGps : ti.drone.badgeNoGps}
              </Badge>
              <span className="text-[11px] text-ink-soft font-mono">{exifResult.file_name}</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <MetaCell
                label={ti.drone.fieldLat}
                value={exifResult.gps?.lat !== undefined ? exifResult.gps.lat : ti.drone.notInFile}
              />
              <MetaCell
                label={ti.drone.fieldLon}
                value={exifResult.gps?.lon !== undefined ? exifResult.gps.lon : ti.drone.notInFile}
              />
              <MetaCell
                label={ti.drone.fieldAltitude}
                value={exifResult.gps?.altitude_m !== undefined ? `${exifResult.gps.altitude_m} m` : ti.drone.notInFile}
              />
              <MetaCell label={ti.drone.fieldCaptureTime} value={exifResult.capture_time || ti.drone.notInFile} />
              <MetaCell
                label={ti.drone.fieldCamera}
                value={
                  exifResult.camera && Object.keys(exifResult.camera).length > 0
                    ? Object.entries(exifResult.camera)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(' · ')
                    : ti.drone.notReported
                }
                className="col-span-2 sm:col-span-2"
              />
              <MetaCell
                label={ti.drone.fieldSensor}
                value={
                  exifResult.sensor && Object.keys(exifResult.sensor).length > 0
                    ? Object.entries(exifResult.sensor)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(' · ')
                    : ti.drone.notReported
                }
                className="col-span-2"
              />
              <MetaCell label={ti.drone.fieldKeysRead} value={exifResult.exif_keys_count} className="col-span-2" />
            </div>

            <ProvenancePanel provenance={exifResult.provenance} />
          </ResultShell>
        )}
      </IngestSection>
    </div>
  );
};

export default IngestPage;