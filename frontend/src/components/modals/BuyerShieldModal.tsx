import React, { useEffect, useState } from 'react';
import { X, ShieldCheck, ShieldAlert, CheckCircle2, Search, Printer } from 'lucide-react';
import { fetchBuyerShieldVerify } from '../../services/api';
import { BuyerShieldAuditResponse } from '../../types/cadastre';
import { cn } from '../../lib/cn';
import { DEMO_ULPIN } from '../../constants';

interface Props {
  initialTarget?: string;
  isOpen: boolean;
  onClose: () => void;
}

export const BuyerShieldModal: React.FC<Props> = ({ initialTarget = `${DEMO_ULPIN}/UB17-L06-601-A`, isOpen, onClose }) => {
  const [targetInput, setTargetInput] = useState(initialTarget);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [audit, setAudit] = useState<BuyerShieldAuditResponse | null>(null);

  const runAudit = (target: string) => {
    if (!target.trim()) return;
    setLoading(true);
    setError(null);
    fetchBuyerShieldVerify(target)
      .then((res) => setAudit(res))
      .catch((err) => setError(err.message || 'Verification failed'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (isOpen && initialTarget) {
      setTargetInput(initialTarget);
      runAudit(initialTarget);
    }
  }, [isOpen, initialTarget]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-rise-in">
      <div className="relative w-full max-w-3xl max-h-[92vh] bg-white rounded-none shadow-brutal-xl border-2 border-ink flex flex-col overflow-hidden">
        {/* Header bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-ink bg-chalk via-white">
          <div className="flex items-center gap-3">
            <span className="p-2.5 rounded-none bg-emerald-600 text-white shadow-brutal">
              <ShieldCheck className="w-5 h-5" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-black text-ink text-base">Buyer Shield 3D Due Diligence</h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-none bg-emerald-100 text-emerald-800 uppercase tracking-widest">
                  Demo Scenario
                </span>
              </div>
              <p className="text-xs text-ink-soft">
                Illustrative scenario built from the demo dataset. No MahaRERA, CERSAI, municipal or LiDAR source is queried.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => window.print()}
              disabled={!audit || loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-ink bg-white border-2 border-ink hover:bg-canvas transition shadow-brutal-sm disabled:opacity-50"
            >
              <Printer className="w-3.5 h-3.5" /> Download Certificate
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-none text-ink-soft hover:text-ink hover:bg-canvas transition"
              aria-label="Close modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Quick Search Bar */}
        <div className="px-6 py-3 bg-canvas border-b border-ink flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-ink-soft absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={targetInput}
              onChange={(e) => setTargetInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runAudit(targetInput)}
              placeholder="Enter 3D-ULPIN, Unit Number (e.g. 601 vs 501), or Building Code (B-17)..."
              className="w-full pl-9 pr-4 py-2 bg-white border-2 border-ink rounded-none text-xs font-mono text-ink placeholder:text-ink-soft focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <button
            onClick={() => runAudit(targetInput)}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-none text-xs font-bold transition shadow-brutal-sm"
          >
            Audit Unit
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 text-ink-soft gap-3">
              <div className="w-8 h-8 border-3 border-emerald-600 border-t-transparent rounded-none animate-spin" />
              <p className="text-sm font-bold">Building the demo scenario…</p>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-none bg-rose-50 border-2 border-ink text-rose-700 text-sm">
              <p className="font-bold">Verification Error</p>
              <p className="mt-1">{error}</p>
            </div>
          )}

          {audit && !loading && (
            <div className="space-y-6 text-ink">
              {/* Verdict Card */}
              <div
                className="p-5 rounded-none border-2 shadow-brutal-sm flex items-start justify-between"
                style={{
                  backgroundColor: `${audit.verdict.status_color}10`,
                  borderColor: `${audit.verdict.status_color}40`,
                }}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-black uppercase px-2.5 py-0.5 rounded-none text-white"
                      style={{ backgroundColor: audit.verdict.status_color }}
                    >
                      GRADE {audit.overall_grade}
                    </span>
                    <span className="font-mono text-xs text-ink-soft">
                      ID: {audit.target_identifier}
                    </span>
                  </div>
                  <h4
                    className="text-base font-black tracking-tight"
                    style={{ color: audit.verdict.status_color }}
                  >
                    {audit.verdict.status_label}
                  </h4>
                  <div className="text-xs text-ink-soft flex items-center gap-4 mt-2">
                    <span>
                      Building: <strong className="text-ink">{audit.building_name} ({audit.building_code})</strong>
                    </span>
                    <span>
                      Unit: <strong className="text-ink">{audit.unit_code}</strong>
                    </span>
                  </div>
                </div>

                <div className="text-right space-y-1">
                  <div className="text-[11px] font-bold">
                    Safe to Purchase:{' '}
                    <span className={audit.verdict.safe_for_purchase ? 'text-emerald-700' : 'text-rose-700'}>
                      {audit.verdict.safe_for_purchase ? 'YES (Verified)' : 'NO (Unsafe)'}
                    </span>
                  </div>
                  <div className="text-[11px] font-bold">
                    Bank Loan Eligible:{' '}
                    <span className={audit.verdict.bank_loan_eligible ? 'text-emerald-700' : 'text-rose-700'}>
                      {audit.verdict.bank_loan_eligible ? 'ELIGIBLE' : 'PROHIBITED'}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-rose-700">
                    Simulated scenario &mdash; no certificate is issued
                  </div>
                </div>
              </div>

              {/* 5-Pillar Checklist */}
              <div className="space-y-3">
                <h5 className="text-xs font-bold uppercase tracking-widest text-ink">
                  5-Pillar Cadastral & Statutory Verification
                </h5>
                <div className="grid grid-cols-1 gap-2.5">
                  {audit.checks.map((chk, i) => (
                    <div
                      key={i}
                      className={cn(
                        'p-3.5 rounded-none border-2 flex items-start gap-3 transition',
                        chk.passed
                          ? 'bg-emerald-50/40 border-ink'
                          : 'bg-rose-50/60 border-ink'
                      )}
                    >
                      <div className="mt-0.5">
                        {chk.passed ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                        ) : (
                          <ShieldAlert className="w-4 h-4 text-rose-600" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-ink">{chk.pillar}</span>
                          <span
                            className={cn(
                              'text-[10px] font-mono font-bold px-2 py-0.5 rounded-none',
                              chk.passed
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-rose-100 text-rose-800'
                            )}
                          >
                            {chk.status}
                          </span>
                        </div>
                        <p className="text-xs text-ink-soft mt-1 leading-relaxed">{chk.remark}</p>
                        {chk.rera_number === null && (
                          <div className="text-[10px] font-mono text-ink-soft mt-1">
                            Registration number: not looked up
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Consumer Guidance */}
              <div className="bg-canvas border-2 border-ink rounded-none p-4 space-y-2">
                <span className="text-xs font-bold text-ink uppercase tracking-widest block">
                  Citizen Legal Advisory:
                </span>
                <ul className="text-xs text-ink space-y-1.5 list-disc list-inside">
                  {audit.consumer_guidance.map((g, idx) => (
                    <li key={idx} className="leading-relaxed">
                      {g}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Certificate Seal Footer */}
              {/* Was a QrCode with "Verified via Bhu-Drishti 3D Cadastral
                  Blockchain" and a CERT-BUYER-SHIELD token derived from a sha256
                  of the input. No blockchain record backs this and no certificate
                  is issued, so both claims are gone. */}
              <div className="pt-3 border-t-2 border-ink bg-canvas p-3 rounded-none text-[11px] text-ink leading-relaxed">
                <div className="font-bold uppercase text-[10px] tracking-widest text-rose-700">
                  Not a government record
                </div>
                <p className="mt-1">
                  {audit.provenance?.warning ??
                    'Simulated scenario data. Not a due-diligence finding.'}
                </p>
                <p className="mt-1 text-ink-soft">
                  No MahaRERA, CERSAI or municipal registry was queried, no certificate
                  is issued, and nothing here is a purchase or financing opinion.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
