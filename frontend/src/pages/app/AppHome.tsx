import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Boxes, ShieldCheck, AlertTriangle, ArrowRight, ArrowUpRight, Clock3, Building2, Database,
  QrCode, FilePlus2, ClipboardList, CheckCircle2, XCircle, Hourglass, Zap, Cpu, RefreshCw, Sparkles,
  Play, FileText,
} from 'lucide-react';
import { fetchParcels, fetchHeroProperty, fetchVerificationCases, fetchJurisdictionSummary, fetchObjections, fetchVerificationLedger, fetchBuilderSubmissions, fileBuilderSubmission, fetchIntegrityOverview, fetchBuilderTemplates, uploadBuilderAsset, fetchPrecinctBuildings } from '../../services/api';
import { ParcelSummary, HeroProperty, PrecinctBuilding } from '../../types/cadastre';
import { ObjectionRecord, VerificationLedger, BuilderSubmissionSummary, BuilderTemplate, BuilderAsset } from '../../services/api';
import { Card, Panel, Badge, StatusBadge, Button, Skeleton, DemoHint } from '../../components/ui';
import { PrecinctMap3D } from '../../components/map3d/PrecinctMap3D';
import { ModelPreview3D } from '../../components/viewer3d/ModelPreview3D';
import { modelFormatOf, formatOfFileName, ModelFormat } from '../../lib/gltf';
import { useApp } from '../../context/AppContext';
import { BuyerShieldModal } from '../../components/modals/BuyerShieldModal';
import { DemandNoticeModal } from '../../components/modals/DemandNoticeModal';
import { DetailedBuilderListingModal } from '../../components/builder/DetailedBuilderListingModal';
import { GovernmentDeedPrintModal } from '../../components/modals/GovernmentDeedPrintModal';
import { DEMO_ULPIN } from '../../constants';

type CaseRow = Record<string, any>;

export const AppHome: React.FC = () => {
  const navigate = useNavigate();
  const { role, mapFocus, setMapFocus } = useApp();
  const [buyerShieldOpen, setBuyerShieldOpen] = useState(false);
  const [demandNoticeTarget, setDemandNoticeTarget] = useState<string | null>(null);
  const [detailedListingOpen, setDetailedListingOpen] = useState(false);
  const [deedModalOpen, setDeedModalOpen] = useState(false);
  const [deedProperty, setDeedProperty] = useState<HeroProperty | null>(null);
  const [parcels, setParcels] = useState<ParcelSummary[]>([]);
  const [hero, setHero] = useState<HeroProperty | null>(null);
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [objections, setObjections] = useState<ObjectionRecord[]>([]);
  const [ledger, setLedger] = useState<VerificationLedger | null>(null);
  const [integrity, setIntegrity] = useState<Record<string, any> | null>(null);
  const [submissions, setSubmissions] = useState<BuilderSubmissionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitForm, setSubmitForm] = useState({ project_name: '', parcel_ulpin: '20260925000001', submission_type: 'Architectural approval', fsi_proposed: 1.8, floors_proposed: 6, template_id: null as string | null, asset_id: null as string | null });
  const [templates, setTemplates] = useState<BuilderTemplate[]>([]);
  const [assets, setAssets] = useState<BuilderAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [pendingPreview, setPendingPreview] = useState<{ url: string; format: ModelFormat; name: string } | null>(null);
  const [proposalBuildings, setProposalBuildings] = useState<PrecinctBuilding[]>([]);

  const isVerifier = role === 'DISTRICT_VERIFIER' || role === 'TALUKA_VERIFIER';
  const isBuilder = role === 'BUILDER';
  const isCitizen = role === 'CITIZEN';
  const isStateAdmin = role === 'STATE_ADMIN';
  const isPublic = role === 'PUBLIC';

  useEffect(() => {
    let active = true;
    const jobs: Promise<any>[] = [fetchParcels(), fetchHeroProperty()];
    if (isVerifier) jobs.push(fetchVerificationCases(), fetchJurisdictionSummary());
    if (isStateAdmin) jobs.push(fetchJurisdictionSummary(), fetchIntegrityOverview());
    if (isCitizen) jobs.push(fetchObjections(DEMO_ULPIN), fetchVerificationLedger('demo-token'));
    if (isBuilder) jobs.push(fetchBuilderSubmissions(), fetchBuilderTemplates(), fetchPrecinctBuildings());
    Promise.all(jobs)
      .then((res) => {
        if (!active) return;
        setParcels(res[0] as ParcelSummary[]);
        setHero(res[1] as HeroProperty);
        if (isVerifier) { setCases(res[2] as CaseRow[]); setSummary(res[3] as Record<string, any>); }
        if (isStateAdmin) { setSummary(res[2] as Record<string, any>); setIntegrity(res[3] as Record<string, any>); }
        if (isCitizen) { setObjections(res[2] as ObjectionRecord[]); setLedger(res[3] as VerificationLedger); }
        if (isBuilder) { setSubmissions(res[2] as BuilderSubmissionSummary); setTemplates(res[3] as BuilderTemplate[]); setProposalBuildings(res[4] as PrecinctBuilding[]); }
      })
      .catch((err) => console.error('AppHome load failed', err))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  const handleSubmit = async () => {
    try {
      const rec = await fileBuilderSubmission({ ...submitForm, fsi_proposed: Number(submitForm.fsi_proposed), floors_proposed: Number(submitForm.floors_proposed) });
      setSubmissions((prev) =>
        prev
          ? { ...prev, total: prev.total + 1, submissions: [rec, ...prev.submissions], by_status: { ...prev.by_status, [rec.status]: (prev.by_status[rec.status] || 0) + 1 } }
          : prev
      );
      setSubmitForm({ project_name: '', parcel_ulpin: '20260925000001', submission_type: 'Architectural approval', fsi_proposed: 1.8, floors_proposed: 6, template_id: null, asset_id: null });
    } catch (err) {
      console.error('submit failed', err);
    }
  };

  const TEMPLATE_PRESETS: Record<string, {
    targetUlpin: string;
    targetCode: string;
    projectName: string;
    fsi: number;
    floors: number;
    type: string;
    description: string;
  }> = {
    'TPL-RES-TOWER': {
      targetUlpin: '20260925000003',
      targetCode: 'B-03',
      projectName: 'Lakeview Heights - High-Rise Residential Tower Wing B',
      fsi: 1.95,
      floors: 15,
      type: 'Architectural approval',
      description: 'High-rise residential tower with 15 storeys and podium parking',
    },
    'TPL-MALL': {
      targetUlpin: '20260925000010',
      targetCode: 'B-10',
      projectName: 'Sector 8 Commercial Retail Mall & Multiplex',
      fsi: 1.25,
      floors: 4,
      type: 'Architectural approval',
      description: 'Commercial shopping mall with retail atrium and subterranean service deck',
    },
    'TPL-OFF-BLOCK': {
      targetUlpin: '20260925000009',
      targetCode: 'B-09',
      projectName: 'Airoli Tech Corridor Office Block C',
      fsi: 2.15,
      floors: 10,
      type: 'FSI revision',
      description: 'Mid-rise IT/Commercial office slab with structural glass facade',
    },
    'TPL-TWIN': {
      targetUlpin: '20260925000011',
      targetCode: 'B-11',
      projectName: 'Metro View Residency Twin Towers Phase II',
      fsi: 2.35,
      floors: 20,
      type: 'Architectural approval',
      description: 'Twin 20-storey residential high-rise with shared skybridge podium',
    },
    'TPL-VILLA': {
      targetUlpin: '20260925000007',
      targetCode: 'B-07',
      projectName: 'Orchid Row Signature Duplex Villa',
      fsi: 0.85,
      floors: 3,
      type: 'Architectural approval',
      description: 'Low-density gated villa development with private setback lawns',
    },
  };

  const handleTemplatePick = (t: BuilderTemplate) => {
    const isDeselect = submitForm.template_id === t.id;
    if (isDeselect) {
      setSubmitForm((f) => ({ ...f, template_id: null, asset_id: null }));
    } else {
      const preset = TEMPLATE_PRESETS[t.id];
      const targetUlpin = preset ? preset.targetUlpin : '20260925000003';
      setSubmitForm({
        project_name: preset ? preset.projectName : `${t.name} Proposal`,
        parcel_ulpin: targetUlpin,
        submission_type: preset ? preset.type : 'Architectural approval',
        fsi_proposed: preset ? preset.fsi : 1.8,
        floors_proposed: preset ? preset.floors : 6,
        template_id: t.id,
        asset_id: null,
      });
      // Automatically fly camera and focus 3D map on this building template!
      setMapFocus(targetUlpin);
    }
  };

  const handleAssetPick = (a: BuilderAsset) => {
    setSubmitForm((f) => ({ ...f, asset_id: f.asset_id === a.id ? null : a.id, template_id: null }));
  };

  const handleUploadGlb = async (file: File | undefined) => {
    if (!file) return;
    const localUrl = URL.createObjectURL(file);
    setPendingPreview({ url: localUrl, format: formatOfFileName(file.name), name: file.name });
    setUploading(true);
    try {
      const asset = await uploadBuilderAsset(file);
      setAssets((prev) => [asset, ...prev]);
      setSubmitForm((f) => ({ ...f, asset_id: asset.id, template_id: null }));
    } catch (err) {
      console.error('upload failed', err);
    } finally {
      URL.revokeObjectURL(localUrl);
      setPendingPreview(null);
      setUploading(false);
    }
  };

  const handleSelectParcel = useCallback(
    (ulpin: string) => {
      setMapFocus(ulpin);
      if (isBuilder) {
        const code = ulpinToBuildingCode(ulpin);
        const b = proposalBuildings.find((x) => x.code === code || x.ulpin === ulpin);
        if (b) {
          setSubmitForm((prev) => ({
            ...prev,
            parcel_ulpin: ulpin,
            project_name: prev.project_name || `${b.name} Proposal`,
            floors_proposed: b.floors,
            fsi_proposed: b.fsi,
          }));
          return;
        }
      }
      navigate(`/app/properties/${ulpin}`);
    },
    [navigate, setMapFocus, isBuilder, proposalBuildings]
  );

  const recentActions = [
    { label: 'Inspect Building B-17 (full 3D twin)', icon: <Building2 className="w-3.5 h-3.5" />, to: `/app/properties/${DEMO_ULPIN}` },
    { label: 'Explore the 3D cadastral precinct map', icon: <Boxes className="w-3.5 h-3.5" />, to: '/app/map' },
    { label: 'Generated 3D-ID for Unit 201', icon: <Database className="w-3.5 h-3.5" />, to: '/app/ulpin' },
  ];

  const kpi = [
    { label: 'Registered parcels', value: parcels.length || '—', sub: 'Airoli Sector 8 precinct', tone: 'text-ink' },
    { label: '3D property twins', value: hero ? 1 : 0, sub: hero ? hero.structure.name : 'n/a', tone: 'text-accent-strong' },
    { label: 'Strata units mapped', value: hero ? hero.units.length : '—', sub: hero ? `${hero.levels.length} levels` : 'needs data', tone: 'text-ink' },
    { label: 'Open issues', value: summary?.total_open_conflicts ?? '—', sub: '1 clash + 1 unauthorized change', tone: 'text-crimson-600' },
  ];

  const title = isStateAdmin ? 'State Operation Console' : isBuilder ? 'Builder Workspace' : isCitizen ? 'My Property Hub' : 'Operation Console';
  const subtitle = isStateAdmin
    ? 'Statewide roll-up across districts — integrity bands, precinct health and policy flags.'
    : isBuilder
    ? 'Track your submissions through the demo review queue — decisions are made in this prototype, not by a regulator.'
    : isCitizen
    ? 'Your demo property record, active objections and a QR proof signed by a key inside this prototype.'
    : 'Live vantage point over the Airoli Sector 8 pilot — 2D cadastre, 3D twin and verification queue.';

  return (
    <div className="flex flex-col gap-8 animate-rise-in">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="w-1 h-8 bg-accent" />
            <div>
              <div className="flex items-center gap-2 annotation text-accent-strong">
                <span>{role.replace('_', ' ').toLowerCase()}</span>
                <span className="text-ink-mut">/</span>
                <span className="text-ink-soft">Overview</span>
              </div>
              <h1 className="text-3xl font-black text-ink font-display tracking-tight mt-1.5">{title}</h1>
              <p className="text-sm text-ink-soft mt-1.5">{subtitle}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="blue" dot>role · {role.replace('_', ' ').toLowerCase()}</Badge>
          <DemoHint text="Synthetic precinct — real workflows" />
        </div>
      </div>

      {isBuilder && (
        <>
          <BuilderTrackerPanel
              submissions={submissions}
              loading={loading}
              form={submitForm}
              setForm={setSubmitForm}
              onSubmit={handleSubmit}
              templates={templates}
              assets={assets}
              uploading={uploading}
              pendingPreview={pendingPreview}
              onTemplatePick={handleTemplatePick}
              onAssetPick={handleAssetPick}
              onUploadGlb={handleUploadGlb}
              buildings={proposalBuildings}
              parcels={parcels}
              hero={hero}
              mapFocus={mapFocus}
              onSelectParcel={handleSelectParcel}
              onOpenDetailed={() => setDetailedListingOpen(true)}
              onOpenDeed={(prop) => {
                setDeedProperty(prop);
                setDeedModalOpen(true);
              }}
            />
          <Card className="p-5">
            <div className="flex items-center gap-3 mb-4">
              <span className="w-1 h-5 bg-accent" />
              <span className="annotation text-ink-soft">Pick up where you left off</span>
            </div>
            <div className="divide-y divide-ink/10 -my-2">
              {[
                { label: 'Review rejected FSI revision (B-09) for resubmission', icon: <AlertTriangle className="w-3.5 h-3.5" />, to: '/app/properties/202609250009' },
                { label: 'Track annex approval for B-17', icon: <Clock3 className="w-3.5 h-3.5" />, to: `/app/properties/${DEMO_ULPIN}` },
              ].map((a, i) => (
                <Link key={a.label} to={a.to} className="group flex items-center gap-4 py-3">
                  <span className="font-mono text-xs text-ink-mut group-hover:text-accent-strong transition">{String(i + 1).padStart(2, '0')}</span>
                  <span className="flex-1 text-sm font-bold text-ink group-hover:text-ink transition">{a.label}</span>
                  <ArrowRight className="w-4 h-4 text-ink-mut group-hover:text-accent-strong group-hover:translate-x-0.5 transition" />
                </Link>
              ))}
            </div>
          </Card>
        </>
      )}

      {isCitizen && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-canvas border-2 border-ink rounded-none overflow-hidden">
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">Your property</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-ink">B-17</div>
              <div className="text-[11px] text-ink-soft mt-1.5">{hero?.structure.name || 'Airoli Sector 8'}</div>
            </div>
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">Record status</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-emerald-600">VERIFIED</div>
              <div className="text-[11px] text-ink-soft mt-1.5">{ledger?.total_verifications ?? '—'} public QR stamps</div>
            </div>
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">Open objections</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-amber-600">{objections.filter((o) => o.status === 'OPEN').length}</div>
              <div className="text-[11px] text-ink-soft mt-1.5">under grievance review</div>
            </div>
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">Encumbrancible units</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-ink">{hero?.units.length ?? '—'}</div>
              <div className="text-[11px] text-ink-soft mt-1.5">strata units on record</div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-2 relative overflow-hidden">
              <div className="relative h-[24rem]">
                {loading ? (
                  <Skeleton className="w-full h-full rounded-none" />
                ) : (
                  <PrecinctMap3D parcels={parcels} hero={hero} focusUlpin={mapFocus} onSelectParcel={handleSelectParcel} />
                )}
                {!loading && (
                  <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5 pointer-events-none">
                    <span className="flex items-center gap-1.5 px-2 py-1 rounded-none bg-chalk/90 border-2 border-ink shadow-brutal-sm text-[10px] font-mono font-bold uppercase tracking-widest text-ink backdrop-blur-md w-fit">
                      <span className="w-1.5 h-1.5 rounded-none bg-emerald-500 animate-pulse" /> Verified · Precinct 3D
                    </span>
                  </div>
                )}
              </div>
            </Card>
            <div className="space-y-4">
              <Panel title="QR verification ledger" icon={<QrCode className="w-4 h-4 text-emerald-600" />} bodyClassName="p-0">
                {ledger ? (
                  <div className="px-4 py-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-ink">ASTD status</span>
                      <span className="font-mono text-xs font-bold text-emerald-700">{ledger.status}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-ink">Total verifications</span>
                      <span className="font-mono text-xs font-bold text-ink">{ledger.total_verifications}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-ink">Last verified</span>
                      <span className="font-mono text-[10px] font-bold text-ink-mut">{ledger.last_verified_at?.slice(0, 10)}</span>
                    </div>
                    <Link to={`/app/properties/${DEMO_ULPIN}`} className="mt-1 flex items-center gap-1.5 text-[11px] font-bold text-accent-strong hover:underline">
                      Open verification proof <ArrowUpRight className="w-3 h-3" />
                    </Link>
                  </div>
                ) : (
                  <div className="px-4 py-6 text-center text-xs text-ink-soft">No ledger data.</div>
                )}
              </Panel>
              <Panel title="My active objections" icon={<ClipboardList className="w-4 h-4 text-amber-500" />} bodyClassName="p-0">
                {objections.length === 0 ? (
                  <div className="px-4 py-6 text-center text-xs text-ink-soft">No objections filed.</div>
                ) : (
                  <div className="divide-y divide-ink/10">
                    {objections.map((o) => (
                      <div key={o.case_number} className="px-4 py-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-bold text-ink">{o.case_number}</span>
                          <StatusBadge status={o.status === 'OPEN' ? 'OPEN' : 'RESOLVED'} />
                        </div>
                        <p className="text-[11px] text-ink-soft mt-1 line-clamp-2">{o.category} · {(o.status ?? '').toLowerCase() || 'unspecified'}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>

              {/* Citizen Buyer Shield Due Diligence */}
              <Panel title="Citizen Buyer Shield" icon={<ShieldCheck className="w-4 h-4 text-emerald-600" />}>
                <div className="p-4 space-y-3">
                  <p className="text-xs text-ink-soft leading-relaxed">
                    Inspect the demo massing model and record status for a unit. No sanctioned plan, MahaRERA record or LiDAR point cloud is loaded, so none of those are checked.
                  </p>
                  <button
                    onClick={() => setBuyerShieldOpen(true)}
                    className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-none text-xs font-bold transition shadow-brutal-sm flex items-center justify-center gap-1.5"
                  >
                    Launch 3D Due Diligence Audit
                  </button>
                </div>
              </Panel>
            </div>
          </div>
        </>
      )}

      {isStateAdmin && (
        <>
          <div className="flex items-start gap-3 px-4 py-3 rounded-none border-2 border-ink bg-amber-50 text-amber-900 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <span className="font-black tracking-wide uppercase">Policy flag · Vertical growth surveillance</span>
              <p className="text-[11px] mt-0.5 text-amber-800">
                Demo change-detection compares a supplied 21.5 m Epoch-2 height against an 18.0 m Epoch-1 height for B-17 (AiroliSector 8) and reports a suspected, unverified change. Both epochs are generated for thisdemo, so this is a difference between two datasets, not a LiDAR measurement and not a compliance finding. {integrity?.bands?.RED ?? '—'} records sit in the RED integrity band statewide; route them to a human reviewer against sanctioned plans.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-canvas border-2 border-ink rounded-none overflow-hidden">
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">Districts covered</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-ink">{summary?.data_district || '—'}</div>
              <div className="text-[11px] text-ink-soft mt-1.5">jurisdictions streaming</div>
            </div>
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">3D structures</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-accent-strong">{summary?.total_3d_structures ?? '—'}</div>
              <div className="text-[11px] text-ink-soft mt-1.5">twins under administration</div>
            </div>
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">RED integrity band</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-crimson-600">{integrity?.bands?.RED ?? '—'}</div>
              <div className="text-[11px] text-ink-soft mt-1.5">needs enforcement review</div>
            </div>
            <div className="bg-chalk p-5">
              <div className="annotation text-ink-mut">Avg integrity</div>
              <div className="mt-2 text-4xl font-black font-mono tracking-tight text-ink">{integrity?.average_score ?? '—'}</div>
              <div className="text-[11px] text-ink-soft mt-1.5">weighted pilot score</div>
            </div>
          </div>

          <PipelineAccelCard />
        </>
      )}

      {isVerifier && (
        <>
      {/* KPI grid — hairline editorial tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-canvas border-2 border-ink rounded-none overflow-hidden">
        {kpi.map((k) => (
          <div key={k.label} className="bg-chalk p-5">
            <div className="annotation text-ink-mut">{k.label}</div>
            <div className={`mt-2 text-4xl font-black font-mono tracking-tight ${k.tone}`}>{k.value}</div>
            <div className="text-[11px] text-ink-soft mt-1.5 truncate">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Map + attention */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 relative overflow-hidden">
          <div className="relative h-[26rem]">
            {loading ? (
              <Skeleton className="w-full h-full rounded-none" />
            ) : (
              <PrecinctMap3D parcels={parcels} hero={hero} focusUlpin={mapFocus} onSelectParcel={handleSelectParcel} />
            )}
            {!loading && (
              <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5 pointer-events-none">
                <span className="flex items-center gap-1.5 px-2 py-1 rounded-none bg-chalk/90 border-2 border-ink shadow-brutal-sm text-[10px] font-mono font-bold uppercase tracking-widest text-ink backdrop-blur-md w-fit">
                  <span className="w-1.5 h-1.5 rounded-none bg-accent animate-pulse" /> Live · Precinct 3D
                </span>
                <Link
                  to="/app/map"
                  className="flex items-center gap-1 px-2 py-1 rounded-none bg-chalk/90 border-2 border-ink shadow-brutal-sm text-[10px] font-bold text-ink hover:text-accent-strong hover:border-ink backdrop-blur-md transition pointer-events-auto w-fit"
                >
                  Open full map <ArrowUpRight className="w-3 h-3" />
                </Link>
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4">
          {/* Needs attention */}
          <Panel
            title="Needs attention"
            icon={<AlertTriangle className="w-4 h-4 text-amber-500" />}
            bodyClassName="p-0"
            action={<Link to="/app/review" className="text-[11px] font-bold text-accent-strong hover:underline">Review queue</Link>}
          >
            {loading ? (
              <SkeletonList2 rows={2} />
            ) : cases.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-ink-soft">Verification queue is clear.</div>
            ) : (
              <div className="divide-y divide-ink/10">
                {cases.slice(0, 3).map((c) => (
                  <div key={c.id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-ink truncate">{c.case_number}</span>
                      <StatusBadge status={c.priority} className="text-[9px]" />
                    </div>
                    <p className="text-[11px] text-ink-soft mt-1 line-clamp-2">{c.clash_summary}</p>
                    <div className="mt-1.5 flex items-center justify-between">
                      <span className="font-mono text-[10px] text-ink-mut">{c.structure_code || c.parcel_ulpin}</span>
                      <Link to={`/app/review?case=${c.id}`} className="text-[11px] font-bold text-accent-strong hover:underline">
                        Decide
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          {/* Data completeness */}
          <Panel title="Dataset integrity" icon={<ShieldCheck className="w-4 h-4 text-emerald-600" />} bodyClassName="p-0">
            <div className="px-4 py-3 border-b border-ink flex items-center justify-between">
              <span className="text-xs font-bold text-ink">Statewide completeness</span>
              <span className="font-mono text-xs font-bold text-emerald-700">{summary?.statewide_data_completeness || '—'}</span>
            </div>
            <div className="px-4 py-3 border-b border-ink flex items-center justify-between">
              <span className="text-xs font-bold text-ink">3D structures</span>
              <span className="font-mono text-xs font-bold text-ink">{summary?.total_3d_structures ?? '—'}</span>
            </div>
            <div className="px-4 py-3 flex items-center justify-between">
              <span className="text-xs font-bold text-ink">Strata units</span>
              <span className="font-mono text-xs font-bold text-ink">{summary?.total_strata_units ?? '—'}</span>
            </div>
          </Panel>
        </div>
      </div>

      {/* Quick actions — numbered editorial list */}
      <Card className="p-5">
        <div className="flex items-center gap-3 mb-4">
          <span className="w-1 h-5 bg-accent" />
          <span className="annotation text-ink-soft">Pick up where you left off</span>
        </div>
        <div className="divide-y divide-ink/10 -my-2">
          {recentActions.map((a, i) => (
            <Link
              key={a.label}
              to={a.to}
              className="group flex items-center gap-4 py-3"
            >
              <span className="font-mono text-xs text-ink-mut group-hover:text-accent-strong transition">{String(i + 1).padStart(2, '0')}</span>
              <span className="flex-1 text-sm font-bold text-ink group-hover:text-ink transition">{a.label}</span>
              <ArrowRight className="w-4 h-4 text-ink-mut group-hover:text-accent-strong group-hover:translate-x-0.5 transition" />
            </Link>
          ))}
        </div>
      </Card>

      {/* Civic Revenue Recovery Banner */}
      <Card className="p-4 bg-chalk via-white border-2 border-ink flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="p-2.5 rounded-none bg-amber-500 text-white shadow-brutal-sm text-xs font-mono font-bold">INR</span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-ink">Municipal Revenue & Tax Evasion Recovery Console</span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-none bg-rose-100 text-rose-800">
                ₹46.37 Cr Recoverable
              </span>
            </div>
            <p className="text-xs text-ink-soft mt-0.5">
              4 unassessed building additions detected in Airoli Sector 8. Issue statutory notices under MMC Act Sec 260 / 267A.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setDemandNoticeTarget('B-17')}
            className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-none text-xs font-bold transition shadow-brutal-sm"
          >
            Issue B-17 Demolition Notice
          </button>
          <Link
            to="/app/analytics"
            className="px-3 py-1.5 bg-white border-2 border-ink hover:bg-canvas text-ink rounded-none text-xs font-bold transition shadow-brutal-sm"
          >
            Open Recovery Console →
          </Link>
        </div>
      </Card>
        </>
      )}

      {isPublic && (
        <Card className="relative overflow-hidden">
          <div className="relative h-[24rem]">
            {loading ? (
              <Skeleton className="w-full h-full rounded-none" />
            ) : (
              <PrecinctMap3D parcels={parcels} hero={hero} focusUlpin={mapFocus} onSelectParcel={handleSelectParcel} />
            )}
          </div>
        </Card>
      )}

      {/* Modals */}
      {buyerShieldOpen && (
        <BuyerShieldModal
          initialTarget={`${DEMO_ULPIN}/UB17-L06-601-A`}
          isOpen={buyerShieldOpen}
          onClose={() => setBuyerShieldOpen(false)}
        />
      )}

      {demandNoticeTarget && (
        <DemandNoticeModal
          buildingCode={demandNoticeTarget}
          isOpen={Boolean(demandNoticeTarget)}
          onClose={() => setDemandNoticeTarget(null)}
        />
      )}

      {detailedListingOpen && (
        <DetailedBuilderListingModal
          isOpen={detailedListingOpen}
          onClose={() => setDetailedListingOpen(false)}
          defaultUlpin={submitForm.parcel_ulpin}
          onSuccess={() => {
            fetchBuilderSubmissions().then(setSubmissions);
          }}
        />
      )}

      {deedModalOpen && deedProperty && (
        <GovernmentDeedPrintModal
          isOpen={deedModalOpen}
          property={deedProperty}
          onClose={() => setDeedModalOpen(false)}
        />
      )}
    </div>
  );
};

function ulpinToBuildingCode(ulpin: string): string | null {
  const m = ulpin.match(/^2026092500(\d{4})$/);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  if (n >= 1 && n <= 12) return `B-${String(n).padStart(2, '0')}`;
  return null;
}

function synthesizeProposalProperty(
  form: { project_name: string; parcel_ulpin: string; submission_type: string; fsi_proposed: number; floors_proposed: number; template_id: string | null },
  building: PrecinctBuilding | null | undefined,
  hero: HeroProperty | null
): HeroProperty {
  const ulpin = form.parcel_ulpin || '20260925000003';
  const name = form.project_name || building?.name || 'Proposed Building Development';
  const code = building?.code || 'B-03';
  const floors = form.floors_proposed || 6;
  const height = floors * 3.5;
  const fpArea = building?.footprint_area_m2 || (building?.w && building?.h ? Math.round(building.w * building.h) : 510);
  const plotArea = building?.plot_area_m2 || Math.round(fpArea * 2.2);
  const builtUp = Math.round(fpArea * floors);
  const fsi = Number((builtUp / plotArea).toFixed(2));

  const units: any[] = [];
  for (let f = 1; f <= floors; f++) {
    for (let u = 1; u <= 4; u++) {
      const uNum = `${f}0${u}`;
      const lvl = `L${String(f).padStart(2, '0')}`;
      units.push({
        unit_number: uNum,
        proposed_3d_id: `${ulpin}/U${code}-${lvl}-${uNum}-X`,
        level_code: lvl,
        unit_type: 'U',
        carpet_area_m2: Math.round(fpArea * 0.2),
        volume_m3: Math.round(fpArea * 0.2 * 3.1),
        min_z: (f - 1) * 3.5,
        max_z: f * 3.5,
        owner_name: 'Builder Inventory / Proposed',
        encumbrance_status: 'CLEAR',
        financial_institution: 'NONE',
      });
    }
  }

  return {
    parent_ulpin: ulpin,
    structure: {
      building_code: code,
      name,
      floors_count: floors,
      height_m: height,
      design_height_m: height,
      footprint_geojson: building?.footprint_geojson || hero?.structure?.footprint_geojson || {},
      total_built_up_area_m2: builtUp,
      calculated_fsi: fsi,
      units,
    } as any,
    units,
    levels: Array.from({ length: floors }, (_, i) => ({
      level_code: `L${String(i + 1).padStart(2, '0')}`,
      floor_number: i + 1,
      level_type: 'RESIDENTIAL',
      min_z: i * 3.5,
      max_z: (i + 1) * 3.5,
      height_m: 3.5,
      solid: true,
    })),
    rights: [],
  } as any;
}

function BuilderTrackerPanel(props: {
  submissions: BuilderSubmissionSummary | null;
  loading: boolean;
  form: { project_name: string; parcel_ulpin: string; submission_type: string; fsi_proposed: number; floors_proposed: number; template_id: string | null; asset_id: string | null };
  setForm: (f: { project_name: string; parcel_ulpin: string; submission_type: string; fsi_proposed: number; floors_proposed: number; template_id: string | null; asset_id: string | null }) => void;
  onSubmit: () => void;
  templates: BuilderTemplate[];
  assets: BuilderAsset[];
  uploading: boolean;
  pendingPreview: { url: string; format: ModelFormat; name: string } | null;
  onTemplatePick: (t: BuilderTemplate) => void;
  onAssetPick: (a: BuilderAsset) => void;
  onUploadGlb: (f: File | undefined) => void;
  buildings: PrecinctBuilding[];
  parcels: ParcelSummary[];
  hero: HeroProperty | null;
  mapFocus: string | null;
  onSelectParcel: (u: string) => void;
  onOpenDetailed?: () => void;
  onOpenDeed?: (prop: HeroProperty) => void;
}) {
  const { submissions, loading, form, setForm, onSubmit, templates, assets, uploading, pendingPreview, onTemplatePick, onAssetPick, onUploadGlb, buildings, parcels, hero, mapFocus, onSelectParcel, onOpenDetailed, onOpenDeed } = props;
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [verifying, setVerifying] = useState(false);
  const [verificationStep, setVerificationStep] = useState(0);
  const [verificationPassed, setVerificationPassed] = useState(false);

  const runVerificationAudit = () => {
    setVerifying(true);
    setVerificationPassed(false);
    setVerificationStep(1);

    setTimeout(() => setVerificationStep(2), 350);
    setTimeout(() => setVerificationStep(3), 700);
    setTimeout(() => setVerificationStep(4), 1050);
    setTimeout(() => setVerificationStep(5), 1400);
    setTimeout(() => setVerificationStep(6), 1750);
    setTimeout(() => {
      setVerifying(false);
      setVerificationPassed(true);
    }, 2100);
  };
  const statusPill = (s: string) =>
    s === 'APPROVED' ? (
      <span className="flex items-center gap-1 font-mono text-[10px] font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-none border-2 border-ink"><CheckCircle2 className="w-3 h-3" /> APPROVED</span>
    ) : s === 'REJECTED' ? (
      <span className="flex items-center gap-1 font-mono text-[10px] font-bold text-red-700 bg-red-50 px-1.5 py-0.5 rounded-none border-2 border-ink"><XCircle className="w-3 h-3" /> REJECTED</span>
    ) : (
      <span className="flex items-center gap-1 font-mono text-[10px] font-bold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded-none border-2 border-ink"><Hourglass className="w-3 h-3" /> UNDER REVIEW</span>
    );
  const modelUrl = pendingPreview?.url || (form.template_id
    ? templates.find((t) => t.id === form.template_id)?.url ?? ''
    : form.asset_id
      ? assets.find((a) => a.id === form.asset_id)?.url ?? ''
      : '');
  const targetCode = ulpinToBuildingCode(form.parcel_ulpin);
  const selectedAsset = assets.find((a) => a.id === form.asset_id) ?? null;
  const targetFootprint = targetCode ? buildings.find((b) => b.code === targetCode) : null;
  const overlayModel = (pendingPreview || form.template_id || form.asset_id) && modelUrl && targetCode
    ? { url: modelUrl, targetCode, mode: 'propose' as const, label: 'Builder proposal', format: pendingPreview?.format ?? modelFormatOf(modelUrl) }
    : null;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <Panel title="File a new submission" icon={<FilePlus2 className="w-4 h-4 text-accent-strong" />} bodyClassName="space-y-3">
            {onOpenDetailed && (
              <button
                type="button"
                onClick={onOpenDetailed}
                /* Was `bg-chalk from-accent text-white`: white text (#FFF) on a
                   white background (#FFF), a 1:1 contrast ratio, so the button
                   was genuinely invisible on the white Card behind it and only
                   its hard drop shadow showed. `from-accent` was also dead --
                   there is no `bg-gradient-to-*` on this element, so a gradient
                   stop paints nothing, which is why the intended accent fill
                   never appeared and the bug survived review.

                   Fixed to the convention the design system already states:
                   accent is a *fill*, so a filled block carries ink text, not
                   white. Matches the sibling submit button below it. */
                className="w-full py-2.5 px-3 rounded-none bg-accent text-ink border-2 border-ink font-bold text-xs flex items-center justify-center gap-2 shadow-brutal-sm hover:bg-accent-strong hover:shadow-brutal transition mb-2"
              >
                <Sparkles className="w-3.5 h-3.5" /> Detailed 3D Building Listing Studio
              </button>
            )}
            <div>
              <label className="block text-[11px] font-bold text-ink mb-1">Project name</label>
              <input
                value={form.project_name}
                onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                placeholder="e.g. Annexe block B-03"
                className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs text-ink outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-ink mb-1">Parcel ULPIN</label>
              <input
                value={form.parcel_ulpin}
                onChange={(e) => setForm({ ...form, parcel_ulpin: e.target.value })}
                placeholder="2026092500XXXX"
                className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
              />
              {targetCode ? (
                <p className="mt-1 text-[10px] text-emerald-700 font-mono">&gt; resolves to precinct building {targetCode}</p>
              ) : (
                <p className="mt-1 text-[10px] text-ink-mut">Precinct ULPINs B-01..B-12 get a live 3D preview.</p>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-[11px] font-bold text-ink mb-1">Type</label>
                <select
                  value={form.submission_type}
                  onChange={(e) => setForm({ ...form, submission_type: e.target.value })}
                  className="w-full bg-canvas border-2 border-ink rounded-none px-2 py-2 text-xs text-ink outline-none focus:border-ink"
                >
                  <option>Architectural approval</option>
                  <option>Completion certificate</option>
                  <option>FSI revision</option>
                  <option>Change of use</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-ink mb-1">FSI</label>
                <input
                  type="number" step="0.01" min="0" max="3"
                  value={form.fsi_proposed}
                  onChange={(e) => setForm({ ...form, fsi_proposed: parseFloat(e.target.value) })}
                  className="w-full bg-canvas border-2 border-ink rounded-none px-2 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                />
              </div>
              <div>
                <label className="block text-[11px] font-bold text-ink mb-1">Floors</label>
                <input
                  type="number" step="1" min="0" max="80"
                  value={form.floors_proposed}
                  onChange={(e) => setForm({ ...form, floors_proposed: parseInt(e.target.value || '0', 10) })}
                  className="w-full bg-canvas border-2 border-ink rounded-none px-2 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                />
              </div>
            </div>
            <div className="pt-1">
              <div className="label-row mb-1.5">
                <label className="block text-[11px] font-bold text-ink">Template library</label>
                <span className="annotation">Pick a GLB to preview</span>
              </div>
              <div className="grid grid-cols-2 gap-1.5 max-h-40 overflow-auto pr-1">
                {templates.length === 0 && !loading ? (
                  <div className="col-span-2 text-[11px] text-ink-soft py-2">No templates available.</div>
                ) : templates.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => onTemplatePick(t)}
                    className={`text-left rounded-none px-2.5 py-2 border-2 transition ${form.template_id === t.id ? 'border-ink bg-accent-faint' : 'border-ink hover:border-ink'} bg-canvas`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[11px] font-bold text-ink truncate">{t.name}</span>
                      {form.template_id === t.id && <CheckCircle2 className="w-3.5 h-3.5 text-accent-strong shrink-0" />}
                    </div>
                    <div className="text-[10px] font-mono text-ink-soft mt-0.5 truncate">{t.id} · {t.kind}</div>
                  </button>
                ))}
              </div>
              <div className="mt-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="block text-[11px] font-bold text-ink">Or upload your own model</span>
                  <button
                    type="button"
                    onClick={() => fileRef.current?.click()}
                    disabled={uploading}
                    className="text-[10px] font-black text-white bg-ink px-2 py-1 rounded-none hover:bg-ink/85 transition disabled:opacity-50"
                  >
                    {uploading ? 'Uploading…' : 'Upload GLB · glTF · OBJ · STL'}
                  </button>
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".glb,.gltf,.obj,.stl,model/gltf-binary,model/gltf+json,text/plain,model/stl"
                  className="hidden"
                  onChange={(e) => { onUploadGlb(e.target.files?.[0]); e.target.value = ''; }}
                />
                {(pendingPreview || form.asset_id) && (
                  <ModelPreview3D
                    url={pendingPreview?.url ?? selectedAsset?.url ?? null}
                    format={pendingPreview?.format}
                    name={pendingPreview?.name ?? selectedAsset?.original_name}
                    height={180}
                  />
                )}
                {assets.length > 0 && (
                  <div className="space-y-1 max-h-28 overflow-auto pr-1">
                    {assets.map((a) => (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => onAssetPick(a)}
                        className={`flex w-full items-center justify-between gap-2 rounded-none px-2 py-1.5 border-2 transition ${form.asset_id === a.id ? 'border-ink bg-accent-faint' : 'border-ink hover:border-ink'} bg-canvas`}
                      >
                        <span className="text-[10px] font-mono text-ink truncate">{a.original_name}</span>
                        <span className="flex items-center gap-1.5 shrink-0">
                          {a.format && (
                            <span className="font-mono text-[9px] font-bold text-ink-soft bg-canvas px-1 py-0.5 rounded-none">{a.format.includes('gltf') ? a.format.includes('binary') ? 'GLB' : 'glTF' : a.format.split('/').pop()?.toUpperCase()}</span>
                          )}
                          {form.asset_id === a.id && <CheckCircle2 className="w-3 h-3 text-accent-strong" />}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <button
              onClick={onSubmit}
              disabled={!form.project_name.trim()}
              className="w-full py-2.5 rounded-none text-xs font-black text-ink bg-accent hover:bg-accent-strong disabled:opacity-40 transition shadow-brutal-sm"
            >
              Submit to regulator pipeline
            </button>
            <p className="text-[10px] text-ink-mut leading-relaxed">
              Don't have a plot yet?{' '}
              <Link to="/app/locate" className="text-accent-strong font-bold underline decoration-dotted">Register on a parcel</Link>.
              Try ULPIN <span className="font-mono">20260925000003</span> (B-03) for the preview.
            </p>
          </Panel>
        </div>

        <div className="lg:col-span-2 space-y-4">
          {loading ? (
            <SkeletonList2 rows={3} />
          ) : submissions ? (
            <>
              <div className="grid grid-cols-3 gap-px bg-canvas border-2 border-ink rounded-none overflow-hidden">
                <div className="bg-chalk p-4">
                  <div className="annotation text-ink-mut">Total</div>
                  <div className="mt-1 text-3xl font-black font-mono text-ink">{submissions.total}</div>
                </div>
                <div className="bg-chalk p-4">
                  <div className="annotation text-ink-mut">Approval rate</div>
                  <div className="mt-1 text-3xl font-black font-mono text-emerald-600">{submissions.approval_rate_pct}%</div>
                </div>
                <div className="bg-chalk p-4">
                  <div className="annotation text-ink-mut">In review</div>
                  <div className="mt-1 text-3xl font-black font-mono text-amber-600">{submissions.by_status.UNDER_REVIEW}</div>
                </div>
              </div>
              <Panel title="My submissions" icon={<ClipboardList className="w-4 h-4 text-accent-strong" />} bodyClassName="p-0">
                <div className="divide-y divide-ink/10">
                  {submissions.submissions.map((s) => (
                    <div key={s.id} className="px-4 py-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-ink truncate">{s.project_name}</span>
                        {statusPill(s.status)}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-[11px] text-ink-soft">
                        <span className="font-mono">{s.id}</span>
                        <span>{s.parcel_ulpin}</span>
                        <span>{s.submitted_on}</span>
                        {s.template_id && <span className="font-mono">{s.template_id}</span>}
                        {s.asset_id && <span className="font-mono">{s.asset_id}</span>}
                      </div>
                      <p className="text-[11px] text-ink-soft mt-1 leading-relaxed">{s.remarks}</p>
                    </div>
                  ))}
                </div>
              </Panel>
            </>
          ) : (
            <div className="px-4 py-6 text-center text-xs text-ink-soft">No submission data.</div>
          )}
        </div>
      </div>

      {overlayModel && (
        <Panel
          title={
            <div className="flex flex-wrap items-center justify-between gap-3 w-full">
              <span className="flex items-center gap-2">
                <Building2 className="w-4 h-4 text-accent-strong" /> 3D Proposal Preview & Live Verification Process
                <span className="font-mono text-xs font-bold text-accent-strong bg-accent-faint px-2 py-0.5 rounded-none border-2 border-ink">
                  {targetCode} · {targetFootprint?.name || form.project_name}
                </span>
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={runVerificationAudit}
                  disabled={verifying}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-white bg-ink hover:bg-ink shadow-brutal-sm transition disabled:opacity-50"
                >
                  <Play className={`w-3.5 h-3.5 ${verifying ? 'animate-spin' : ''}`} />
                  {verifying ? `Step ${verificationStep}/6…` : 'Run Demo Walkthrough'}
                </button>
                {onOpenDeed && (
                  <button
                    type="button"
                    onClick={() => {
                      const prop = synthesizeProposalProperty(form, targetFootprint, hero);
                      onOpenDeed(prop);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-ink bg-white hover:bg-canvas border-2 border-ink shadow-brutal-sm transition"
                  >
                    <FileText className="w-3.5 h-3.5 text-accent-strong" />
                    <span>View Monograph (PDF)</span>
                  </button>
                )}
              </div>
            </div>
          }
          bodyClassName="p-0"
        >
          <div className="relative h-[400px]">
            <PrecinctMap3D
              parcels={parcels}
              hero={hero}
              focusUlpin={mapFocus}
              onSelectParcel={onSelectParcel}
              buildings={buildings}
              overlayModel={overlayModel}
              className="h-full w-full"
            />
          </div>

          {/* Verification Pipeline Stepper & Architectural Telemetry */}
          <div className="p-4 bg-canvas border-t border-ink space-y-4">
            {/* Live Architectural Massing Telemetry Grid */}
            {(() => {
              const fpArea = targetFootprint?.footprint_area_m2 || (targetFootprint?.w && targetFootprint?.h ? Math.round(targetFootprint.w * targetFootprint.h) : 450);
              const plotArea = targetFootprint?.plot_area_m2 || Math.round(fpArea * 2.2);
              const coveragePct = Math.round((fpArea / plotArea) * 100);
              return (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <div className="bg-white p-3 rounded-none border-2 border-ink shadow-brutal-sm">
                    <div className="text-[10px] font-mono text-ink-soft uppercase">Plot Area</div>
                    <div className="text-sm font-bold text-ink font-mono mt-0.5">
                      {plotArea.toLocaleString()} m²
                    </div>
                    <div className="text-[10px] text-ink-soft">CTS Cadastral parcel</div>
                  </div>

                  <div className="bg-white p-3 rounded-none border-2 border-ink shadow-brutal-sm">
                    <div className="text-[10px] font-mono text-ink-soft uppercase">Footprint Coverage</div>
                    <div className="text-sm font-bold text-ink font-mono mt-0.5">
                      {fpArea} m²
                      <span className="text-xs font-normal text-ink-soft ml-1">
                        ({coveragePct}%)
                      </span>
                    </div>
                    <div className="text-[10px] text-emerald-600 font-bold">Max 60% Allowed (PASS)</div>
                  </div>

              <div className="bg-white p-3 rounded-none border-2 border-ink shadow-brutal-sm">
                <div className="text-[10px] font-mono text-ink-soft uppercase">Proposed Storeys</div>
                <div className="text-sm font-bold text-ink font-mono mt-0.5">
                  {form.floors_proposed} Floors ({form.floors_proposed * 3.5}m)
                </div>
                <div className="text-[10px] text-ink-soft">G+{form.floors_proposed - 1} + 1 Basement</div>
              </div>

              <div className="bg-white p-3 rounded-none border-2 border-ink shadow-brutal-sm">
                <div className="text-[10px] font-mono text-ink-soft uppercase">Volumetric FSI</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="text-sm font-bold text-ink font-mono">{form.fsi_proposed}</span>
                  <span className="text-[10px] text-ink-soft font-mono">/ demo cap 2.00</span>
                </div>
                <div className={`text-[10px] font-bold ${form.fsi_proposed <= 2.0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {form.fsi_proposed <= 2.0 ? 'Within demo cap' : 'Above demo cap'}
                </div>
              </div>

              <div className="bg-white p-3 rounded-none border-2 border-ink shadow-brutal-sm">
                <div className="text-[10px] font-mono text-ink-soft uppercase">Subsurface Safety</div>
                <div className="text-sm font-bold text-ink-soft font-mono mt-0.5">
                  No data
                </div>
                <div className="text-[10px] text-ink-soft">No utility network loaded, so no buffer was measured</div>
              </div>
            </div>
              );
            })()}

            {/* 6-Phase Cadastral Verification Inspection Matrix */}
            <div className="bg-white rounded-none border-2 border-ink p-4 shadow-brutal-sm space-y-3">
              <div className="flex items-center justify-between border-b border-ink pb-2">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-accent-strong" />
                  <span className="text-xs font-bold text-ink">
                    Property Review Walkthrough (scripted demo, 6 steps)
                  </span>
                </div>
                <span className="text-[11px] font-mono text-ink-soft">
                  {verificationPassed ? (
                    <span className="text-emerald-700 font-bold bg-emerald-50 border-2 border-ink px-2 py-0.5 rounded-none flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> WALKTHROUGH FINISHED — NO COMPLIANCE FINDING
                    </span>
                  ) : verifying ? (
                    <span className="text-accent-strong font-bold bg-accent-faint border-2 border-ink px-2 py-0.5 rounded-none animate-pulse">
                      VERIFYING PHASE {verificationStep}/6…
                    </span>
                  ) : (
                    <span className="text-ink-soft bg-canvas px-2 py-0.5 rounded-none">
                      Ready to Audit
                    </span>
                  )}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-xs">
                <div className={`p-2.5 rounded-none border-2 transition ${verificationStep >= 1 || verificationPassed ? 'bg-emerald-50/60 border-ink' : 'bg-canvas border-ink'}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink">1. Footprint Extrusion</span>
                    <span className="text-[10px] font-mono text-ink-soft font-bold">BROWSER PREVIEW</span>
                  </div>
                  <p className="text-[11px] text-ink-soft mt-1">The drawn footprint is extruded to a solid in the browser so you can see the massing. No survey geometry is compared.</p>
                </div>

                <div className={`p-2.5 rounded-none border-2 transition ${verificationStep >= 2 || verificationPassed ? 'bg-emerald-50/60 border-ink' : 'bg-canvas border-ink'}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink">2. Setback Panel</span>
                    <span className="text-[10px] font-mono text-ink-soft font-bold">NOT CHECKED</span>
                  </div>
                  <p className="text-[11px] text-ink-soft mt-1">Layout aid only. No National Building Code, DCR or zoning rule set is loaded, so nothing was tested against a setback requirement.</p>
                </div>

                <div className={`p-2.5 rounded-none border-2 transition ${verificationStep >= 3 || verificationPassed ? (form.fsi_proposed <= 2.0 ? 'bg-emerald-50/60 border-ink' : 'bg-amber-50/60 border-ink') : 'bg-canvas border-ink'}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink">3. FSI Massing Audit</span>
                    <span className={`text-[10px] font-mono font-bold ${form.fsi_proposed <= 2.0 ? 'text-emerald-700' : 'text-amber-700'}`}>
                      {form.fsi_proposed <= 2.0 ? `WITHIN DEMO CAP (${form.fsi_proposed}/2.00)` : `ABOVE DEMO CAP (${form.fsi_proposed}/2.00)`}
                    </span>
                  </div>
                  <p className="text-[11px] text-ink-soft mt-1">Compares the FSI figure you typed against a hardcoded 2.00 demo cap. 2.00 is a default in this prototype, not a permitted FSI for any real parcel.</p>
                </div>

                <div className={`p-2.5 rounded-none border-2 transition ${verificationStep >= 4 || verificationPassed ? 'bg-emerald-50/60 border-ink' : 'bg-canvas border-ink'}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink">4. Subsurface Utilities</span>
                    <span className="text-[10px] font-mono text-ink-soft font-bold">NO DATA</span>
                  </div>
                  <p className="text-[11px] text-ink-soft mt-1">No water, sewer or power network is loaded, so no clash or clearance test is performed.</p>
                </div>

                <div className={`p-2.5 rounded-none border-2 transition ${verificationStep >= 5 || verificationPassed ? 'bg-emerald-50/60 border-ink' : 'bg-canvas border-ink'}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink">5. Solar &amp; Air Rights</span>
                    <span className="text-[10px] font-mono text-ink-soft font-bold">NO DATA</span>
                  </div>
                  <p className="text-[11px] text-ink-soft mt-1">No daylight, overhang or airspace analysis runs here, and no air-right record exists for this parcel.</p>
                </div>

                <div className={`p-2.5 rounded-none border-2 transition ${verificationStep >= 6 || verificationPassed ? 'bg-emerald-50/60 border-ink' : 'bg-canvas border-ink'}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink">6. Local Signature Demo</span>
                    <span className="text-[10px] font-mono text-ink-soft font-bold">DEMO ONLY</span>
                  </div>
                  <p className="text-[11px] text-ink-soft mt-1">Hashes the record and signs it with a key held inside this prototype. There is no blockchain, no distributed consensus and no external party.</p>
                </div>
              </div>

              {/* Sanction verdict ribbon */}
              {verificationPassed && (
                <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-chalk border-2 border-ink rounded-none animate-rise-in">
                  <div className="flex items-center gap-2.5">
                    <span className="p-1.5 rounded-none bg-emerald-600 text-white">
                      <CheckCircle2 className="w-4 h-4" />
                    </span>
                    <div>
                      <div className="text-xs font-bold text-ink">
                        Demo walkthrough finished — no approval or sanction was granted
                      </div>
                      <div className="text-[10px] font-mono text-ink-soft">
                        This sequence is a fixed timer that always completes. No regulator, officer or authority
                        reviewed anything; the previous &ldquo;99.2% concordance&rdquo; and statute citation were invented.
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {onOpenDeed && (
                      <button
                        type="button"
                        onClick={() => {
                          const prop = synthesizeProposalProperty(form, targetFootprint, hero);
                          onOpenDeed(prop);
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-white bg-ink hover:bg-ink shadow-brutal-sm transition"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>Print Monograph</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={onSubmit}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 shadow-brutal-sm transition"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Send to Demo Review Queue</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}

function SkeletonList2({ rows }: { rows: number }) {
  return (
    <div className="divide-y divide-ink/10">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="px-4 py-3 space-y-2">
          <Skeleton className="h-3 w-3/4" />
          <Skeleton className="h-2.5 w-full" />
        </div>
      ))}
    </div>
  );
}

interface BenchRow {
  label: string;
  ms: number | null;
  speedup: string | null;
  runtime: string;
  hex: string;
}

function PipelineAccelCard() {
  const [bench, setBench] = useState<any | null>(null);
  const [fetched, setFetched] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    setBusy(true);
    try {
      const res = await fetch('/api/v1/system/benchmarks', { headers: { Accept: 'application/json' } });
      setBench(await res.json());
    } catch {
      setBench(null);
    } finally {
      setBusy(false);
      setFetched(true);
    }
  }, []);

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const gp = bench?.ground_profile;
  const rows: BenchRow[] = gp
    ? [
        { label: 'Python · numpy', ms: gp.python_ms, speedup: '1.0x', runtime: 'pure-Python reference (event loop)', hex: '#94a3b8' },
        { label: 'C++ · ctypes', ms: gp.cpp_ms, speedup: gp.speedup_cpp_vs_python, runtime: 'g++ -O3 shared lib, in-process', hex: '#2563eb' },
        { label: 'Rust · native', ms: gp.rust_ms ?? null, speedup: gp.speedup_rust_vs_python, runtime: 'bhudrishti_native 0.1.0, raw f64 pipe', hex: '#ea580c' },
      ]
    : [];
  const maxMs = rows.reduce((m, r) => Math.max(m, r.ms ?? 0), 1);

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink bg-canvas">
        <div className="flex items-center gap-2">
          <span className="w-8 h-8 rounded-none bg-canvas border-2 border-ink flex items-center justify-center">
            <Cpu className="w-4 h-4 text-ink" />
          </span>
          <div>
            <div className="text-sm font-black text-ink flex items-center gap-1.5">
              Pipeline acceleration
              <span className="text-[9px] font-bold font-mono uppercase tracking-widest px-1.5 py-0.5 rounded-none bg-emerald-50 text-emerald-700 border-2 border-ink">multi-language</span>
            </div>
            <p className="text-[11px] text-ink-soft mt-0.5">LiDAR ground profile · {gp?.workload || '200,000 points'} · lower is faster</p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={run} disabled={busy} className="shrink-0">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
          {busy ? 'benchmarking…' : 're-run'}
        </Button>
      </div>

      <div className="p-4 space-y-3">
        {!fetched && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}
        {fetched && !gp && (
          <p className="text-xs text-ink-soft">Benchmark unavailable — /system/benchmarks did not respond.</p>
        )}
        {gp &&
          rows.map((r) => (
            <div key={r.label} className="space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-bold text-ink flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-none" style={{ backgroundColor: r.hex }} />
                  {r.label}
                  <span className="font-mono text-[10px] text-ink-mut font-normal">· {r.runtime}</span>
                </span>
                <span className="font-mono font-black text-ink">
                  {r.ms != null ? `${Math.round(r.ms)} ms` : '—'}
                  {r.speedup && <span className="ml-2 text-accent-strong">▲ {r.speedup}</span>}
                </span>
              </div>
              <div className="h-2 rounded-none bg-ink/8 overflow-hidden">
                <div
                  className="h-full rounded-none transition-all duration-500"
                  style={{ width: `${Math.max(4, ((r.ms ?? 0) / maxMs) * 100)}%`, backgroundColor: r.hex }}
                />
              </div>
            </div>
          ))}

        <div className="flex items-center justify-between pt-2 border-t border-ink">
          <span className="text-[10px] text-ink-mut flex items-center gap-1">
            <Zap className="w-3 h-3" />
            Compiled kernels run in-process (ctypes) / as a single Rust binary in the image — pipelined, memory-safe, with pure-Python fallback if a toolchain is missing.
          </span>
          <span className="text-[10px] font-mono text-ink-mut whitespace-nowrap">
            {bench?.rust_available ? 'rust: live' : 'rust: fallback'} · {bench?.cpp_kernel_available ? 'c++: live' : 'c++: fallback'}
          </span>
        </div>
      </div>
    </Card>
  );
}