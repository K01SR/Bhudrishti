import React, { useState, useEffect } from 'react';
import { X, CheckCircle2, XCircle, AlertTriangle, UserCheck, MessageSquare } from 'lucide-react';
import { fetchVerificationCases, decideVerificationCase } from '../../services/api';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCaseUpdated?: () => void;
}

export const VerificationQueueModal: React.FC<Props> = ({
  isOpen,
  onClose,
  onCaseUpdated,
}) => {
  const [cases, setCases] = useState<any[]>([]);
  const [selectedCase, setSelectedCase] = useState<any | null>(null);
  const [officerNotes, setOfficerNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadCases();
    }
  }, [isOpen]);

  const loadCases = async () => {
    try {
      const data = await fetchVerificationCases();
      setCases(data);
      if (data.length > 0 && !selectedCase) {
        setSelectedCase(data[0]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDecision = async (decision: 'APPROVE' | 'REJECT' | 'CORRECTION_REQUESTED') => {
    if (!selectedCase) return;
    setIsSubmitting(true);
    setSuccessMessage('');

    try {
      const notes = officerNotes.trim() || `Officer decision: ${decision} executed during technical review.`;
      const res = await decideVerificationCase(selectedCase.id, decision, notes);
      setSuccessMessage(res.message);
      await loadCases();
      if (onCaseUpdated) onCaseUpdated();
    } catch (err) {
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-4xl bg-chalk border-2 border-ink rounded-none shadow-brutal overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-canvas border-b border-ink">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-none bg-accent text-ink flex items-center justify-center shadow-brutal-sm">
              <UserCheck className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-base text-ink">District Verification Queue</h3>
              <p className="text-xs text-ink-soft font-bold">
                Authorized Cadastral Officer Case Review (Thane Jurisdiction)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-ink-mut hover:text-ink-soft p-1.5 rounded-none hover:bg-canvas transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-ink/10 overflow-y-auto">
          {/* Left: Case List */}
          <div className="p-4 space-y-2 bg-canvas/50">
            <span className="text-[11px] font-bold uppercase tracking-widest text-ink-soft font-sans block">
              Active Cases ({cases.length})
            </span>
            <div className="space-y-2 mt-2">
              {cases.map((c) => {
                const isSelected = selectedCase?.id === c.id;
                const isApproved = c.status === 'APPROVED';

                return (
                  <div
                    key={c.id}
                    onClick={() => setSelectedCase(c)}
                    className={`p-3 rounded-none border-2 cursor-pointer transition text-xs ${
                      isSelected
                        ? 'bg-accent-faint border-ink text-ink shadow-brutal-sm'
                        : 'bg-chalk border-ink hover:border-ink text-ink'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-accent-strong">
                        {c.case_number}
                      </span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-none ${
                          isApproved
                            ? 'bg-emerald-50 text-emerald-700 border-2 border-ink'
                            : 'bg-amber-50 text-amber-700 border-2 border-ink'
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>
                    <div className="font-bold text-ink mt-1">{c.property_name}</div>
                    <div className="text-[11px] text-ink-soft mt-0.5">{c.case_type}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right: Detailed Inspection & Decision Actions */}
          <div className="md:col-span-2 p-6 space-y-5 bg-chalk">
            {selectedCase ? (
              <>
                <div className="flex items-center justify-between pb-3 border-b border-ink">
                  <div>
                    <h4 className="font-bold text-base text-ink">
                      Case: {selectedCase.case_number}
                    </h4>
                    <span className="text-xs text-ink-soft font-mono">
                      ULPIN: {selectedCase.parcel_ulpin} | Structure: {selectedCase.structure_code}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-ink-soft bg-canvas border-2 border-ink px-2.5 py-1 rounded-none">
                    Priority: <strong className="text-amber-700">{selectedCase.priority}</strong>
                  </span>
                </div>

                {/* Case Metadata */}
                <div className="grid grid-cols-2 gap-3 text-xs bg-canvas p-3.5 rounded-none border-2 border-ink font-mono">
                  <div>
                    <span className="text-ink-mut font-sans block">Submitted By:</span>
                    <div className="text-ink font-bold mt-0.5">{selectedCase.submitted_by}</div>
                  </div>
                  <div>
                    <span className="text-ink-mut font-sans block">Submission Date:</span>
                    <div className="text-ink font-bold mt-0.5">{new Date(selectedCase.created_at).toLocaleString()}</div>
                  </div>
                  <div className="col-span-2">
                    <span className="text-ink-mut font-sans block">Topology Discrepancy Alert:</span>
                    <div className="text-red-700 font-bold mt-0.5">{selectedCase.clash_summary}</div>
                  </div>
                </div>

                {/* Decision Notes Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-ink flex items-center gap-1.5 font-sans">
                    <MessageSquare className="w-3.5 h-3.5 text-accent-strong" />
                    Authorized Officer Review Notes & Remarks:
                  </label>
                  <textarea
                    rows={3}
                    value={officerNotes}
                    onChange={(e) => setOfficerNotes(e.target.value)}
                    placeholder="Enter official cadastral findings, conditions of approval, or required boundary rectifications..."
                    className="w-full bg-canvas border-2 border-ink rounded-none p-3 text-xs text-ink placeholder-slate-400 focus:outline-none focus:border-ink focus:bg-chalk transition"
                  />
                </div>

                {/* Success Notification */}
                {successMessage && (
                  <div className="p-3 bg-emerald-50 border-2 border-ink text-emerald-800 rounded-none text-xs font-bold flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                    <span>{successMessage}</span>
                  </div>
                )}

                {/* Decision Actions */}
                <div className="pt-2 flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => handleDecision('APPROVE')}
                    disabled={isSubmitting}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-none bg-emerald-600 hover:bg-emerald-700 text-white font-bold shadow-brutal-sm shadow-emerald-500/20 text-xs transition disabled:opacity-50"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>APPROVE CADASTRAL RECORD</span>
                  </button>

                  <button
                    onClick={() => handleDecision('CORRECTION_REQUESTED')}
                    disabled={isSubmitting}
                    className="flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-none bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs shadow-brutal-sm transition disabled:opacity-50"
                  >
                    <AlertTriangle className="w-4 h-4" />
                    <span>Request Correction</span>
                  </button>

                  <button
                    onClick={() => handleDecision('REJECT')}
                    disabled={isSubmitting}
                    className="flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-none bg-red-600 hover:bg-red-700 text-white font-bold text-xs shadow-brutal-sm transition disabled:opacity-50"
                  >
                    <XCircle className="w-4 h-4" />
                    <span>Reject</span>
                  </button>
                </div>
              </>
            ) : (
              <div className="p-8 text-center text-ink-mut text-xs">
                Select a verification case from the queue to inspect details.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
