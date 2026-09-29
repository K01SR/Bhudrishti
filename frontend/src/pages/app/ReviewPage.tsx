import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ShieldCheck,
  Inbox,
  Check,
  Plus,
  X,
} from 'lucide-react';
import {
  fetchVerificationCases,
  decideVerificationCase,
  fetchObjections,
  fetchObjectionDepartments,
  resolveObjection,
  fileObjection,
  fetchBuilderSubmissions,
  decideBuilderSubmission,
  ObjectionRecord,
} from '../../services/api';
import { Card, Badge, StatusBadge, Button, Skeleton, EmptyState, DemoHint } from '../../components/ui';
import { cn } from '../../lib/cn';
import { useApp } from '../../context/AppContext';
import { DEMO_ULPIN } from '../../constants';

type CaseRow = {
  id: string;
  case_number: string;
  parcel_ulpin: string;
  structure_code?: string;
  property_name?: string;
  case_type: string;
  status: string;
  priority: string;
  assigned_verifier?: string;
  submitted_by?: string;
  created_at?: string;
  discrepancies_count?: number;
  clash_summary?: string;
  officer_notes?: string | null;
  proposed_id?: string;
  decision_timestamp?: string | null;
};

/**
 * What accepting a submission produced: a prototype-derived identifier and a
 * tamper-evident audit entry.
 *
 * The identifier is the part that matters for honesty. It is computed by this
 * prototype from the parcel's geometry -- it is not a DOLR or state ULPIN
 * allocation, it confers no title, and the Ed25519 signature is over the
 * prototype's own key. So it is labelled as derived, never presented as an
 * issued identifier, and the backend's own caveat text is rendered verbatim
 * rather than replaced with something friendlier.
 */
const AcceptanceRecordPanel: React.FC<{ submission: any }> = ({ submission: s }) => {
  const derived = Boolean(s.derived_ulpin);
  const status = s.derived_ulpin_status;
  const proof = s.audit_proof || null;
  const hasProof = proof && (proof.hash || proof.ed25519_signature || proof.chained === false);

  if (s.status !== 'ACCEPTED_FOR_RECORD') return null;
  if (!derived && !s.derivation_note && !hasProof) return null;

  return (
    <div className="mt-3 pt-3 border-t border-ink/20 space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] uppercase font-bold text-ink-mut">Acceptance record</span>
        <Badge tone="amber">Prototype-derived identifier</Badge>
      </div>

      {derived ? (
        <div className="p-3 bg-accent-faint border-2 border-ink space-y-1.5">
          <div className="text-[10px] uppercase font-bold text-ink-mut">
            Prototype-derived identifier (not an issued ULPIN)
          </div>
          <div className="font-mono text-sm font-bold text-ink break-all">{s.derived_ulpin}</div>
          {s.derivation_note && (
            <p className="text-[10px] text-ink-soft leading-relaxed">{s.derivation_note}</p>
          )}
        </div>
      ) : (
        <div className="p-3 bg-canvas border-2 border-ink space-y-1.5">
          <div className="text-[10px] uppercase font-bold text-ink-mut">
            No identifier derived{status === 'NOT_DERIVED' ? ' (NOT_DERIVED)' : ''}
          </div>
          <p className="text-[10px] text-ink-soft leading-relaxed">
            {s.derivation_note ||
              'No identifier could be derived from this parcel. The review decision is still recorded.'}
          </p>
        </div>
      )}

      {/* Authority, straight from the backend, not a label chosen here. */}
      <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-ink-mut">
        <span className="uppercase">Authority</span>
        <span className="px-1.5 py-0.5 border-2 border-ink bg-white text-ink font-bold">
          {s.identifier_authority || 'NOT_A_REGISTRY_ALLOCATION'}
        </span>
      </div>

      {s.ulpin_note && (
        <p className="text-[10px] text-ink-soft leading-relaxed border-l-2 border-ink/30 pl-2">
          {s.ulpin_note}
        </p>
      )}

      {hasProof && (
        <div className="p-3 bg-emerald-50 border-2 border-ink font-mono text-[10px] text-emerald-900 space-y-1">
          <div className="font-bold flex items-center gap-1.5">
            {proof.chained ? (
              <Check className="w-3.5 h-3.5 text-emerald-600" />
            ) : (
              <X className="w-3.5 h-3.5 text-amber-600" />
            )}
            <span>{proof.chained ? 'Audit entry chained' : 'Audit entry not written'}</span>
          </div>
          {proof.chained ? (
            <>
              {proof.table && <div className="text-emerald-700">Table: {proof.table}</div>}
              {proof.event_type && <div className="text-emerald-700">Event: {proof.event_type}</div>}
              {proof.timestamp && <div className="text-emerald-700">At: {proof.timestamp}</div>}
              {proof.previous_hash && (
                <div className="text-emerald-700 break-all">Prev: {proof.previous_hash}</div>
              )}
              {proof.hash && <div className="text-emerald-700 break-all">Hash: {proof.hash}</div>}
              {proof.record_fingerprint && (
                <div className="text-emerald-700 break-all">
                  Fingerprint: {proof.record_fingerprint}
                </div>
              )}
              {proof.ed25519_signature && (
                <div className="text-emerald-700 break-all">Ed25519: {proof.ed25519_signature}</div>
              )}
            </>
          ) : (
            <div className="text-amber-700">{proof.reason || 'No reason was returned.'}</div>
          )}
          {proof.signature_note && (
            <p className="text-emerald-700 leading-relaxed pt-1">{proof.signature_note}</p>
          )}
        </div>
      )}
    </div>
  );
};

export const ReviewPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { role, showToast } = useApp();

  const [activeTab, setActiveTab] = useState<'CASES' | 'OBJECTIONS' | 'SUBMISSIONS'>('CASES');

  // Verification Cases State
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(searchParams.get('case'));
  const [caseNotes, setCaseNotes] = useState('');
  const [actingDecision, setActingDecision] = useState<string | null>(null);
  const [caseProof, setCaseProof] = useState<any | null>(null);

  // Citizen Objections State
  const [objections, setObjections] = useState<ObjectionRecord[]>([]);
  const [departments, setDepartments] = useState<Array<{ department: string; total: number; open: number; resolved: number; latest: string }>>([]);
  const [loadingObjections, setLoadingObjections] = useState(false);
  const [selectedObjection, setSelectedObjection] = useState<ObjectionRecord | null>(null);
  const [objectionStatusFilter, setObjectionStatusFilter] = useState<'ALL' | 'OPEN' | 'RESOLVED'>('ALL');
  const [resolveModalOpen, setResolveModalOpen] = useState(false);
  const [resolveText, setResolveText] = useState('');
  const [resolving, setResolving] = useState(false);

  // File Objection Modal
  const [fileModalOpen, setFileModalOpen] = useState(false);
  const [newObj, setNewObj] = useState({
    ulpin: DEMO_ULPIN,
    category: 'AUTHORIZATION',
    description: '',
    contact_email: 'verifier@example.com',
    priority: 'HIGH',
  });
  const [filing, setFiling] = useState(false);

  // Builder submissions State (the disposition timeline)
  const [subs, setSubs] = useState<Array<any>>([]);
  const [loadingSubs, setLoadingSubs] = useState(false);
  const [dispTarget, setDispTarget] = useState<string | null>(null);
  const [dispReason, setDispReason] = useState('');
  const [dispBusy, setDispBusy] = useState<string | null>(null);
  const [dispNotice, setDispNotice] = useState<{ id: string; text: string; ok: boolean } | null>(null);

  const selectedCase = cases.find((c) => c.id === selectedCaseId) || null;

  const loadCases = async () => {
    try {
      const data = await fetchVerificationCases();
      setCases(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingCases(false);
    }
  };

  const loadObjections = async () => {
    setLoadingObjections(true);
    try {
      const [objs, depts] = await Promise.all([fetchObjections(), fetchObjectionDepartments()]);
      setObjections(objs || []);
      setDepartments(depts || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingObjections(false);
    }
  };

  useEffect(() => {
    loadCases();
    loadObjections();
    loadSubs();
  }, []);

  const loadSubs = async () => {
    setLoadingSubs(true);
    try {
      const data = await fetchBuilderSubmissions();
      setSubs(data?.submissions || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingSubs(false);
    }
  };

  const decideSubmission = async (id: string, decision: 'ACCEPTED_FOR_RECORD' | 'REJECTED') => {
    if (dispReason.trim().length < 8) {
      setDispNotice({ id, ok: false, text: 'A reason of at least 8 characters is required to record a disposition.' });
      return;
    }
    setDispBusy(id);
    setDispNotice(null);
    try {
      const res = await decideBuilderSubmission(id, decision, dispReason.trim());
      setSubs((prev) =>
        prev.map((s) =>
          s.id === id
            ? {
                ...s,
                status: res.record_status,
                review: res.review || s.review,
                review_history: res.review_history || s.review_history,
                persistence: res.persistence,
                derived_ulpin: res.derived_ulpin,
                derived_ulpin_status: res.derived_ulpin_status,
                derivation_note: res.derivation_note,
                identifier_authority: res.identifier_authority,
                audit_proof: res.audit_proof,
                ulpin_note: res.ulpin_note,
              }
            : s
        )
      );
      const persisted = res.persistence?.persisted;
      setDispNotice({
        id,
        ok: true,
        text:
          `Disposition recorded (${res.record_status}). ` +
          (persisted
            ? `Persisted to ${res.persistence?.table}.`
            : `Kept in memory only: ${res.persistence?.reason || 'no database write'}.`),
      });
      setDispTarget(null);
      setDispReason('');
    } catch (e) {
      setDispNotice({ id, ok: false, text: e instanceof Error ? e.message : 'Disposition failed' });
    } finally {
      setDispBusy(null);
    }
  };

  const decideCase = async (decision: string) => {
    if (!selectedCase) return;
    setActingDecision(decision);
    try {
      const res = await decideVerificationCase(selectedCase.id, decision, caseNotes);
      setCaseProof(res.cryptographic_proof || null);
      showToast(res.message);
      setCases((prev) => prev.map((c) => (c.id === selectedCase.id ? { ...c, ...res.case } : c)));
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Decision failed');
    } finally {
      setActingDecision(null);
    }
  };

  const openCase = (id: string) => {
    setSelectedCaseId(id);
    setSearchParams({ case: id }, { replace: true });
    setCaseProof(null);
    setCaseNotes('');
  };

  const handleResolveObjection = async () => {
    if (!selectedObjection || !resolveText.trim()) return;
    setResolving(true);
    try {
      await resolveObjection(selectedObjection.case_number, resolveText, `verifier-${role.toLowerCase()}`);
      showToast(`Objection ${selectedObjection.case_number} resolved`);
      setResolveModalOpen(false);
      setResolveText('');
      loadObjections();
    } catch (e: any) {
      showToast(e.message || 'Failed to resolve objection');
    } finally {
      setResolving(false);
    }
  };

  const handleFileObjection = async () => {
    if (!newObj.description.trim()) return;
    setFiling(true);
    try {
      await fileObjection(newObj);
      showToast(`Objection submitted successfully for ${newObj.ulpin}`);
      setFileModalOpen(false);
      setNewObj({
        ulpin: DEMO_ULPIN,
        category: 'AUTHORIZATION',
        description: '',
        contact_email: 'verifier@example.com',
        priority: 'HIGH',
      });
      loadObjections();
    } catch (e: any) {
      showToast(e.message || 'Failed to submit objection');
    } finally {
      setFiling(false);
    }
  };

  const filteredObjections = objections.filter((o) => {
    if (objectionStatusFilter === 'ALL') return true;
    return o.status === objectionStatusFilter;
  });

  return (
    <div className="flex flex-col gap-5 animate-rise-in">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 annotation text-accent-strong">
            <span className="text-accent-strong">{role.replace('_', ' ')}</span>
            <span>/</span>
            <span>Decisions & Clearances</span>
          </div>
          <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">Review & Decisions Hub</h1>
          <p className="text-sm text-ink-soft mt-1">
            Official decision desk for technical cadastral sanction verification and statutory citizen grievance clearing.
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-canvas border-2 border-ink rounded-none p-1">
            <Button
              variant={activeTab === 'CASES' ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setActiveTab('CASES')}
            >
              Sanction Cases ({cases.length})
            </Button>
            <Button
              variant={activeTab === 'OBJECTIONS' ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setActiveTab('OBJECTIONS')}
            >
              Citizen Objections ({objections.length})
            </Button>
            <Button
              variant={activeTab === 'SUBMISSIONS' ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setActiveTab('SUBMISSIONS')}
            >
              Builder Submissions ({subs.filter((s) => s.status === 'PENDING_REVIEW').length} pending)
            </Button>
          </div>
          <DemoHint />
        </div>
      </div>

      {/* ===================================================================== */}
      {/* TAB 1: SANCTION VERIFICATION CASES                                    */}
      {/* ===================================================================== */}
      {activeTab === 'CASES' && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
          {/* Queue List */}
          <div className="lg:col-span-2 space-y-2.5">
            {loadingCases ? (
              <Skeleton className="h-40 rounded-none" />
            ) : cases.length === 0 ? (
              <Card>
                <EmptyState icon={<Inbox className="w-5 h-5" />} title="Queue clear" description="No verification cases pending." />
              </Card>
            ) : (
              cases.map((c) => {
                const active = c.id === selectedCaseId;
                return (
                  <div
                    key={c.id}
                    onClick={() => openCase(c.id)}
                    className={cn(
                      'cursor-pointer transition border-l-4 rounded-none',
                      active ? 'border-l-accent' : c.priority === 'CRITICAL' ? 'border-l-crimson-500' : 'border-l-amber-500'
                    )}
                  >
                    <Card className={cn('p-3.5', active ? 'bg-accent/40' : '')}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[11px] font-bold text-ink">{c.case_number}</span>
                        <Badge tone={c.priority === 'CRITICAL' ? 'red' : 'amber'}>{c.priority}</Badge>
                      </div>
                      <p className="text-xs font-bold text-ink mt-1.5 line-clamp-1">{c.case_type.replace(/_/g, ' ')}</p>
                      <p className="text-[11px] text-ink-soft mt-0.5 line-clamp-2">{c.clash_summary}</p>
                      <div className="flex items-center justify-between mt-2 text-[10px] text-ink-mut font-mono">
                        <span>{c.structure_code || c.parcel_ulpin}</span>
                        <span>{c.submitted_by?.split(' (')[0]}</span>
                      </div>
                    </Card>
                  </div>
                );
              })
            )}
          </div>

          {/* Case Detail View */}
          <div className="lg:col-span-3">
            {!selectedCase ? (
              <Card>
                <EmptyState
                  icon={<ShieldCheck className="w-5 h-5" />}
                  title="Select a verification case"
                  description="Choose a pending case from the left list to review clashes, inspect evidence, and sign a decision."
                />
              </Card>
            ) : (
              <Card className="p-5 space-y-4">
                <div className="flex items-start justify-between gap-3 pb-3 border-b border-ink">
                  <div>
                    <span className="font-mono text-xs text-ink-soft">{selectedCase.case_number}</span>
                    <h2 className="text-lg font-bold text-ink">{selectedCase.property_name || selectedCase.case_type}</h2>
                    <p className="text-xs text-ink-soft mt-0.5 font-mono">ULPIN: {selectedCase.parcel_ulpin}</p>
                  </div>
                  <StatusBadge status={selectedCase.status} />
                </div>

                <div className="space-y-2 text-xs">
                  <div className="p-3 bg-canvas rounded-none border-2 border-ink space-y-1">
                    <div className="text-[10px] uppercase font-bold text-ink-mut">Clash & Topology Summary</div>
                    <div className="text-ink font-bold">{selectedCase.clash_summary || 'No clashes reported.'}</div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="p-2.5 bg-canvas rounded-none border-2 border-ink">
                      <span className="text-ink-mut">Assigned verifier:</span>
                      <div className="font-bold text-ink mt-0.5">{selectedCase.assigned_verifier || 'Reviewer (demo)'}</div>
                    </div>
                    <div className="p-2.5 bg-canvas rounded-none border-2 border-ink">
                      <span className="text-ink-mut">Submitted by:</span>
                      <div className="font-bold text-ink mt-0.5">{selectedCase.submitted_by || 'Surveyor'}</div>
                    </div>
                  </div>
                </div>

                {/* Notes Input */}
                <div className="space-y-1.5 pt-2">
                  <label className="text-xs font-bold text-ink">Decision Notes & Statutory Justification</label>
                  <textarea
                    value={caseNotes}
                    onChange={(e) => setCaseNotes(e.target.value)}
                    placeholder="Enter compliance reasons, setback findings, or conditions for sanction..."
                    className="w-full p-3 border-2 border-ink rounded-none text-xs bg-canvas focus:bg-white focus:outline-none focus:border-ink"
                    rows={3}
                  />
                </div>

                {/* Decision Buttons */}
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-ink">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => decideCase('REJECT')}
                    disabled={actingDecision !== null}
                    className="text-red-600 hover:bg-red-50"
                  >
                    Reject Sanction
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => decideCase('REQUEST_MORE_INFO')}
                    disabled={actingDecision !== null}
                  >
                    Request Modification
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => decideCase('APPROVE')}
                    disabled={actingDecision !== null}
                  >
                    {actingDecision === 'APPROVE' ? 'Signing Ed25519...' : 'Approve & Seal 3D Twin'}
                  </Button>
                </div>

                {caseProof && (
                  <div className="p-3 bg-emerald-50 border-2 border-ink rounded-none text-xs font-mono space-y-1 text-emerald-900 animate-rise-in">
                    <div className="font-bold flex items-center gap-1.5">
                      <Check className="w-4 h-4 text-emerald-600" />
                      <span>Cryptographic Proof Minted</span>
                    </div>
                    <div className="text-[10px] text-emerald-700 truncate">SHA256: {caseProof.fingerprint_sha256}</div>
                    <div className="text-[10px] text-emerald-700 truncate">Ed25519: {caseProof.digital_signature_ed25519}</div>
                  </div>
                )}
              </Card>
            )}
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 2: CITIZEN OBJECTIONS & GRIEVANCES                                */}
      {/* ===================================================================== */}
      {activeTab === 'OBJECTIONS' && (
        <div className="space-y-6">
          {/* Department Worklist Overview Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {departments.map((d) => (
              <Card key={d.department} className="p-4 bg-white border-ink">
                <div className="text-[10px] uppercase font-bold text-ink-mut">{d.department}</div>
                <div className="flex items-baseline justify-between mt-1">
                  <div className="text-2xl font-black font-mono text-ink">{d.total}</div>
                  <div className="text-xs font-bold text-amber-600 font-mono">{d.open} open</div>
                </div>
                <div className="text-[10px] text-emerald-600 font-bold mt-1">
                  {d.resolved} resolved
                </div>
              </Card>
            ))}
          </div>

          {/* Action & Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 p-1 bg-canvas rounded-none text-xs font-mono">
              {(['ALL', 'OPEN', 'RESOLVED'] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setObjectionStatusFilter(filter)}
                  className={`px-3 py-1 rounded-none font-bold transition ${
                    objectionStatusFilter === filter
                      ? 'bg-ink text-white'
                      : 'text-ink-soft hover:text-ink'
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={() => setFileModalOpen(true)}
              className="flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" /> File New Objection
            </Button>
          </div>

          {/* Objections List */}
          <div className="space-y-3">
            {loadingObjections ? (
              <Skeleton className="h-32 rounded-none" />
            ) : filteredObjections.length === 0 ? (
              <Card className="p-8 text-center text-ink-soft">No objections found under this filter.</Card>
            ) : (
              filteredObjections.map((obj) => (
                <Card key={obj.case_number} className="p-4 border-ink hover:border-ink transition">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-ink">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-ink bg-canvas px-2 py-0.5 rounded-none">
                        {obj.case_number}
                      </span>
                      <span className="text-xs font-bold text-accent-strong bg-accent-faint px-2 py-0.5 rounded-none border-2 border-ink">
                        {obj.department}
                      </span>
                      <Badge tone={obj.priority === 'HIGH' ? 'red' : 'amber'}>{obj.priority}</Badge>
                    </div>

                    <div className="flex items-center gap-2">
                      <StatusBadge status={obj.status} />
                      {obj.status === 'OPEN' && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            setSelectedObjection(obj);
                            setResolveModalOpen(true);
                          }}
                          className="text-xs font-bold border-ink text-emerald-800 hover:bg-emerald-50"
                        >
                          Resolve →
                        </Button>
                      )}
                    </div>
                  </div>

                  <p className="text-xs text-ink mt-3 leading-relaxed">{obj.description}</p>

                  <div className="flex flex-wrap items-center justify-between gap-2 mt-3 pt-2 border-t border-ink text-[11px] font-mono text-ink-mut">
                    <span>Target ULPIN: <strong className="text-ink">{obj.ulpin}</strong></span>
                    <span>Role: {obj.assigned_role}</span>
                    {obj.resolution && (
                      <span className="text-emerald-700 font-bold">Resolution: {obj.resolution}</span>
                    )}
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>
      )}

      {/* RESOLVE OBJECTION MODAL */}
      {resolveModalOpen && selectedObjection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-white rounded-none max-w-lg w-full p-6 space-y-4 shadow-brutal-xl border-2 border-ink font-mono text-xs">
            <div className="flex items-center justify-between border-b pb-3">
              <span className="font-bold text-sm text-ink">Resolve Objection #{selectedObjection.case_number}</span>
              <button onClick={() => setResolveModalOpen(false)} className="p-1 hover:bg-canvas rounded-none">
                <X className="w-4 h-4 text-ink-soft" />
              </button>
            </div>

            <div className="p-3 bg-canvas rounded-none space-y-1">
              <div className="text-[10px] text-ink-soft uppercase">Objection Detail</div>
              <div className="text-ink font-sans text-xs">{selectedObjection.description}</div>
              <div className="text-[10px] text-ink-soft mt-1">Target ULPIN: {selectedObjection.ulpin}</div>
            </div>

            <div className="space-y-1.5">
              <label className="font-bold text-ink">Official Resolution Findings & Mutation Ref</label>
              <textarea
                value={resolveText}
                onChange={(e) => setResolveText(e.target.value)}
                placeholder="Enter field survey findings, mutation number recorded, or dimensional verification note..."
                className="w-full p-3 border-2 border-ink rounded-none font-sans text-xs focus:outline-none focus:border-ink"
                rows={4}
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-ink">
              <Button variant="ghost" size="sm" onClick={() => setResolveModalOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleResolveObjection}
                disabled={!resolveText.trim() || resolving}
              >
                {resolving ? 'Recording...' : 'Submit Resolution'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* FILE OBJECTION MODAL */}
      {fileModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-white rounded-none max-w-lg w-full p-6 space-y-4 shadow-brutal-xl border-2 border-ink font-mono text-xs">
            <div className="flex items-center justify-between border-b pb-3">
              <span className="font-bold text-sm text-ink">File Citizen Objection</span>
              <button onClick={() => setFileModalOpen(false)} className="p-1 hover:bg-canvas rounded-none">
                <X className="w-4 h-4 text-ink-soft" />
              </button>
            </div>

            <div className="space-y-3 font-sans">
              <div>
                <label className="text-[11px] font-bold text-ink">Parcel ULPIN</label>
                <input
                  type="text"
                  value={newObj.ulpin}
                  onChange={(e) => setNewObj({ ...newObj, ulpin: e.target.value })}
                  className="w-full mt-1 p-2.5 border-2 border-ink rounded-none font-mono text-xs"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-ink">Category</label>
                <select
                  value={newObj.category}
                  onChange={(e) => setNewObj({ ...newObj, category: e.target.value })}
                  className="w-full mt-1 p-2.5 border-2 border-ink rounded-none text-xs"
                >
                  <option value="AUTHORIZATION">Urban Development / Height / Sanction</option>
                  <option value="DATA">Survey & Mapping / Boundary</option>
                  <option value="RESOLUTION">Revenue & Land Records / Title</option>
                  <option value="OTHER">General Citizen Services</option>
                </select>
              </div>

              <div>
                <label className="text-[11px] font-bold text-ink">Grievance Description</label>
                <textarea
                  value={newObj.description}
                  onChange={(e) => setNewObj({ ...newObj, description: e.target.value })}
                  placeholder="Detail the boundary dispute, unauthorized addition, or recorded discrepancy..."
                  className="w-full mt-1 p-3 border-2 border-ink rounded-none text-xs"
                  rows={3}
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-ink">
              <Button variant="ghost" size="sm" onClick={() => setFileModalOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleFileObjection}
                disabled={!newObj.description.trim() || filing}
              >
                {filing ? 'Submitting...' : 'Submit Objection'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 3: BUILDER SUBMISSIONS · DISPOSITION TIMELINE                      */}
      {/* ===================================================================== */}
      {activeTab === 'SUBMISSIONS' && (
        <div className="space-y-4">
          <div className="p-3.5 bg-accent-faint border-2 border-ink text-xs text-ink">
            <strong>Record a disposition.</strong> Accepting a submission adds it to this prototype's working
            record. It is an internal attestation by a reviewer account: not a government certification, not a legal
            clearance, and conferring no title. Every submission sits at PENDING_REVIEW until a reviewer decides.
          </div>

          {loadingSubs ? (
            <Skeleton className="h-40 rounded-none" />
          ) : subs.length === 0 ? (
            <Card>
              <EmptyState icon={<Inbox className="w-5 h-5" />} title="No submissions" description="No builder submissions on record." />
            </Card>
          ) : (
            subs.map((s) => {
              const decided = s.status === 'ACCEPTED_FOR_RECORD' || s.status === 'REJECTED';
              const review = s.review || s.review_history?.[s.review_history.length - 1] || null;
              const open = dispTarget === s.id;
              const notice = dispNotice && dispNotice.id === s.id ? dispNotice : null;
              return (
                <Card key={s.id} className="p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-sm font-bold text-ink block truncate">{s.project_name}</span>
                      <span className="text-[11px] font-mono text-ink-mut">
                        {s.id} · {s.parcel_ulpin} · {s.submission_type}
                      </span>
                    </div>
                    <StatusBadge status={s.status} />
                  </div>

                  {/* Timeline */}
                  <div className="mt-3 flex items-center gap-2 text-[11px]">
                    <span className="w-4 h-4 rounded-full border-2 border-ink flex items-center justify-center text-[9px] font-black bg-emerald-200">1</span>
                    <span className="text-ink">Submitted {s.submitted_on}</span>
                    <span className="flex-1 h-px bg-ink/30" />
                    <span className="w-4 h-4 rounded-full border-2 border-ink flex items-center justify-center text-[9px] font-black bg-emerald-200">2</span>
                    <span className="text-ink">Recorded PENDING_REVIEW</span>
                    <span className="flex-1 h-px bg-ink/30" />
                    <span
                      className={`w-4 h-4 rounded-full border-2 border-ink flex items-center justify-center text-[9px] font-black ${
                        decided ? (s.status === 'ACCEPTED_FOR_RECORD' ? 'bg-emerald-200' : 'bg-red-200') : 'bg-amber-200'
                      }`}
                    >
                      3
                    </span>
                    <span className={decided ? 'text-ink font-bold' : 'text-ink-mut'}>
                      {decided ? `Disposition: ${s.status}` : 'Awaiting reviewer disposition'}
                    </span>
                  </div>

                  {review && (
                    <p className="mt-2 text-[10px] text-ink-mut font-mono">
                      by {review.verified_by} {review.verified_at ? `· ${review.verified_at}` : ''}
                      {review.reason ? ` · "${review.reason}"` : ''}
                    </p>
                  )}

                  {notice && (
                    <p className={`mt-2 text-[10px] px-2 py-1.5 border rounded-none ${notice.ok ? 'text-emerald-800 bg-emerald-50 border-emerald-200' : 'text-red-700 bg-red-50 border-red-200'}`}>
                      {notice.text}
                    </p>
                  )}

                  <AcceptanceRecordPanel submission={s} />

                  {!decided && (
                    <div className="mt-3 pt-3 border-t border-ink/20">
                      {!open ? (
                        <Button size="sm" variant="primary" onClick={() => { setDispTarget(s.id); setDispNotice(null); }}>
                          <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> Record disposition
                        </Button>
                      ) : (
                        <div className="space-y-2">
                          <textarea
                            value={dispReason}
                            onChange={(e) => setDispReason(e.target.value)}
                            placeholder="Why this decision? (required, at least 8 characters)"
                            rows={2}
                            className="w-full p-2.5 border-2 border-ink rounded-none text-xs"
                          />
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              variant="primary"
                              disabled={dispBusy === s.id}
                              onClick={() => decideSubmission(s.id, 'ACCEPTED_FOR_RECORD')}
                            >
                              <Check className="w-3.5 h-3.5 mr-1" /> Accept into record
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={dispBusy === s.id}
                              onClick={() => decideSubmission(s.id, 'REJECTED')}
                            >
                              <X className="w-3.5 h-3.5 mr-1" /> Reject
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => { setDispTarget(null); setDispReason(''); }}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};
export default ReviewPage;