import React, { useEffect, useState } from 'react';
import { X, Printer, AlertTriangle, FileText, LogIn } from 'lucide-react';
import { generateDemandNotice } from '../../services/api';
import { DemandNoticeResponse } from '../../types/cadastre';

interface Props {
  buildingCode: string;
  isOpen: boolean;
  onClose: () => void;
  noticeType?: string;
  /**
   * Called when generation fails for want of a session, so the host can open its
   * sign-in dialog. Optional: without it the modal still explains what is wrong,
   * it just cannot offer the fix itself.
   */
  onRequestSignIn?: () => void;
}

export const DemandNoticeModal: React.FC<Props> = ({
  buildingCode,
  isOpen,
  onClose,
  noticeType = 'SEC_260_DEMOLITION',
  onRequestSignIn,
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [data, setData] = useState<DemandNoticeResponse | null>(null);

  useEffect(() => {
    if (!isOpen || !buildingCode) return;
    setLoading(true);
    setError(null);
    setNeedsSignIn(false);
    setData(null);
    generateDemandNotice(buildingCode, noticeType)
      .then((res) => setData(res))
      .catch((err) => {
        // 401 is the case worth separating: it is not a failure of the notice
        // generator, it is a missing session, and the remedy is different.
        const status = (err as { status?: number })?.status;
        if (status === 401 || status === 403) {
          setNeedsSignIn(true);
          setError(
            'Generating a statutory notice requires a signed-in account. Sign in and try again.',
          );
        } else {
          setError(err.message || 'Failed to generate statutory notice');
        }
      })
      .finally(() => setLoading(false));
  }, [buildingCode, isOpen, noticeType]);

  if (!isOpen) return null;

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-rise-in">
      <div className="relative w-full max-w-3xl max-h-[92vh] bg-white rounded-none shadow-brutal-xl border-2 border-ink flex flex-col overflow-hidden">
        {/* Header bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-ink bg-canvas">
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-none bg-rose-100 text-rose-700">
              <FileText className="w-5 h-5" />
            </span>
            <div>
              <h3 className="font-bold text-ink text-base">Municipal Statutory Notice Generator</h3>
              <p className="text-xs text-ink-soft font-mono">Maharashtra Municipal Corporations Act (LIX of 1949)</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePrint}
              disabled={!data || loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-ink bg-white border-2 border-ink hover:bg-canvas transition shadow-brutal-sm disabled:opacity-50"
            >
              <Printer className="w-3.5 h-3.5" /> Print / Save PDF
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

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 text-ink-soft gap-3">
              <div className="w-8 h-8 border-3 border-ink border-t-transparent rounded-none animate-spin" />
              <p className="text-sm font-bold">Generating the signed scenario demand notice…</p>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-none bg-rose-50 border-2 border-ink text-rose-700 text-sm">
              <p className="font-bold">
                {needsSignIn ? 'Sign in to generate a notice' : 'Error Generating Notice'}
              </p>
              <p className="mt-1">{error}</p>
              {needsSignIn ? (
                /* The notice endpoint requires a session, and the analytics page
                   is reachable without one, so clicking Generate Notice while
                   signed out returned a bare 401 and rendered a red error box
                   with no way forward. That read as "the button does nothing".
                   Offer the actual next step instead. */
                <button
                  onClick={onRequestSignIn ?? (() => window.dispatchEvent(new Event('bhudrishti:request-signin')))}
                  className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-white bg-ink border-2 border-ink hover:bg-rose-700 transition"
                >
                  <LogIn className="w-3.5 h-3.5" /> Sign in
                </button>
              ) : null}
            </div>
          )}

          {data && !loading && (
            <div className="bg-white border-2 border-ink rounded-none p-8 shadow-brutal-sm space-y-6 text-ink font-sans print:border-none print:shadow-none print:p-0">
              {/* Was a real municipal letterhead: "Navi Mumbai Municipal
                  Corporation / Town Planning, Building Sanctions & Property Tax
                  Assessment Directorate / CBD Belapur". This deployment is not
                  that body and cannot issue anything on its behalf. */}
              <div className="text-center border-b pb-4 border-ink">
                <div className="text-xs uppercase tracking-widest font-mono text-rose-700 font-bold mb-1">
                  Simulated scenario &mdash; not a government document
                </div>
                <h2 className="text-lg font-black tracking-wide text-ink uppercase">
                  Generated enforcement scenario
                </h2>
                <p className="text-xs font-bold text-ink-soft">
                  Demonstration output from the Bhu-Drishti prototype
                </p>
                <p className="text-[11px] text-ink-soft mt-0.5">
                  No municipal authority, no legal effect, no statutory rate
                </p>
              </div>

              {/* Notice Metadata */}
              <div className="flex flex-wrap justify-between text-xs border-b pb-3 border-ink font-mono">
                <div>
                  <span className="text-ink-soft">Notice Ref: </span>
                  <span className="font-bold text-ink">{data.notice_number}</span>
                </div>
                <div>
                  <span className="text-ink-soft">Generated at: </span>
                  <span className="font-bold text-ink">{data.generated_at}</span>
                </div>
              </div>

              {/* Title & Target */}
              <div>
                <div className="p-3 rounded-none bg-rose-50 border-2 border-ink text-center">
                  <h4 className="text-xs font-black text-rose-900 tracking-wide uppercase">
                    {data.legal_notice_title}
                  </h4>
                  <div className="flex flex-wrap justify-center gap-2 mt-1.5 text-[10px] text-rose-700 font-mono">
                    {data.statutory_sections.map((sec, i) => (
                      <span key={i} className="bg-rose-100/70 px-2 py-0.5 rounded-none">
                        {sec}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
                  <div className="p-3 bg-canvas rounded-none border-2 border-ink">
                    <span className="text-ink-soft text-[10px] uppercase font-bold tracking-widest">Addressee & Property</span>
                    <div className="font-bold text-ink text-sm mt-1">{data.target_property.building_name}</div>
                    <div className="text-ink-soft mt-0.5">Code: <span className="font-mono font-bold text-accent-strong">{data.target_property.building_code}</span></div>
                    <div className="text-ink-soft">Ward: {data.target_property.ward}</div>
                  </div>
                  <div className="p-3 bg-canvas rounded-none border-2 border-ink">
                    <span className="text-ink-soft text-[10px] uppercase font-bold tracking-widest">Cadastral Reference</span>
                    <div className="font-mono font-bold text-ink mt-1">ULPIN: {data.target_property.ulpin}</div>
                    <div className="text-ink-soft mt-0.5">Jurisdiction: {data.target_property.district}</div>
                    <div className="text-ink-soft">Survey Baseline: Airoli Sector 8 Cadastre</div>
                  </div>
                </div>
              </div>

              {/* Volumetric Violations */}
              <div className="space-y-2">
                <h5 className="text-xs font-bold uppercase tracking-widest text-ink flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  3D Spatial Volumetric Audit Findings (LiDAR Evidence)
                </h5>
                <div className="p-3.5 bg-amber-50/70 border-2 border-ink rounded-none text-xs space-y-2">
                  <p className="text-ink leading-relaxed font-bold">
                    {data.volumetric_violations.sanction_plan_discrepancy}
                  </p>
                  <div className="grid grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
                    <div className="bg-white p-2 rounded-none border-2 border-ink">
                      <span className="text-ink-soft block text-[10px]">Unassessed Area</span>
                      <span className="font-bold text-rose-700">+{data.volumetric_violations.unassessed_built_up_area_m2} m²</span>
                    </div>
                    <div className="bg-white p-2 rounded-none border-2 border-ink">
                      <span className="text-ink-soft block text-[10px]">Illegal Volume</span>
                      <span className="font-bold text-rose-700">+{data.volumetric_violations.illegal_volume_m3} m³</span>
                    </div>
                    <div className="bg-white p-2 rounded-none border-2 border-ink">
                      <span className="text-ink-soft block text-[10px]">Evidence Stream</span>
                      <span className="font-bold text-accent-strong truncate block">Epoch 2 LiDAR</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Financial Assessment Table */}
              <div className="space-y-2">
                <h5 className="text-xs font-bold uppercase tracking-widest text-ink">
                  Statutory Penalty & Tax Demand Assessment
                </h5>
                <table className="w-full text-xs border-2 border-ink rounded-none overflow-hidden">
                  <thead className="bg-canvas text-ink font-bold border-b border-ink">
                    <tr>
                      <th className="py-2 px-3 text-left">Head of Demand</th>
                      <th className="py-2 px-3 text-left">Statutory Basis</th>
                      <th className="py-2 px-3 text-right">Amount (INR)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                    <tr>
                      <td className="py-2 px-3 font-sans text-ink">Unassessed Base Property Tax</td>
                      <td className="py-2 px-3 text-ink-soft">2.5 Years Evasion @ 1.4% RRR</td>
                      <td className="py-2 px-3 text-right text-ink">₹{data.financial_demand.unassessed_tax_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 font-sans text-ink">Section 267A Penal Assessment</td>
                      <td className="py-2 px-3 text-ink-soft">2x Property Tax + 18% Compound Interest</td>
                      <td className="py-2 px-3 text-right text-rose-700 font-bold">₹{data.financial_demand.statutory_penalty_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    </tr>
                    {data.financial_demand.compounding_fee_inr > 0 && (
                      <tr>
                        <td className="py-2 px-3 font-sans text-ink">Regularization / Premium FSI Compounding</td>
                        <td className="py-2 px-3 text-ink-soft">50% Ready Reckoner Rate</td>
                        <td className="py-2 px-3 text-right text-ink">₹{data.financial_demand.compounding_fee_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      </tr>
                    )}
                    <tr className="bg-rose-50 font-bold text-xs">
                      <td className="py-2.5 px-3 font-sans text-rose-900" colSpan={2}>
                        TOTAL SUM PAYABLE WITHIN 30 DAYS (Due: {data.financial_demand.due_date})
                      </td>
                      <td className="py-2.5 px-3 text-right text-rose-900">
                        ₹{data.financial_demand.total_payable_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Directives */}
              <div className="space-y-1.5 text-xs text-ink bg-canvas p-3.5 rounded-none border-2 border-ink">
                <span className="font-bold text-ink block uppercase text-[10px] tracking-widest">Statutory Directives:</span>
                {data.directives.map((dir, i) => (
                  <p key={i} className="leading-relaxed">{dir}</p>
                ))}
              </div>

              {/* Cryptographic signature
                  This panel used to render a QrCode, "Digitally Verified & Sealed",
                  a SHA256 digest and a "Valid State Government Cadastral Seal" with
                  the Municipal Commissioner as signatory over "Government of
                  Maharashtra". The API field behind it was a bare sha256() of a
                  string, and the system is not a signatory to anything.

                  It then rendered nothing at all, which was honest but threw away
                  the one true thing available. The document is now signed with
                  real Ed25519 over its own SHA-256 fingerprint, and that is shown
                  here in full so it can be checked independently. What is
                  deliberately NOT shown: any government seal, any signatory, any
                  "verified" badge. The signature is this deployment's own and
                  proves the bytes are unaltered, nothing more. */}
              {data.cryptographic_verification && (
                <div className="pt-4 border-t-2 border-ink bg-canvas p-3.5 rounded-none">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-ink uppercase text-[10px] tracking-widest">
                      Cryptographic signature
                    </span>
                    <span className="px-1.5 py-0.5 border border-ink text-[9px] font-mono uppercase">
                      {data.cryptographic_verification.algorithm}
                    </span>
                  </div>

                  <div className="space-y-2">
                    <div>
                      <div className="text-[9px] uppercase text-ink-soft font-bold tracking-wider">
                        SHA-256 fingerprint
                      </div>
                      <code className="block text-[10px] font-mono text-ink break-all mt-0.5 bg-white/50 p-1.5 border border-ink/20">
                        {data.cryptographic_verification.sha256_fingerprint}
                      </code>
                    </div>
                    <div>
                      <div className="text-[9px] uppercase text-ink-soft font-bold tracking-wider">
                        Ed25519 signature
                      </div>
                      <code className="block text-[10px] font-mono text-ink break-all mt-0.5 bg-white/50 p-1.5 border border-ink/20">
                        {data.cryptographic_verification.ed25519_signature}
                      </code>
                    </div>
                  </div>

                  <p className="text-[10px] text-ink mt-2.5 leading-relaxed">
                    This signature is real: change one byte of this document and
                    verification fails. It was produced by this deployment, and it
                    proves only that the text has not been altered since it was
                    signed. It is <strong>not</strong> a government record, not a
                    municipal instrument, and not a review by any authority.
                  </p>

                  {data.cryptographic_verification.signing_key_is_published_demo_key && (
                    <p className="text-[10px] text-ink mt-2 leading-relaxed border-l-2 border-ink pl-2">
                      This deployment is using the published demonstration key, which ships in
                      this repository. Anyone with a copy of the code can produce a signature
                      that verifies here, so the signature establishes nothing about who wrote
                      the document. Set <code className="font-mono">ED25519_PRIVATE_KEY_HEX</code>{' '}
                      before serving real traffic.
                    </p>
                  )}
                </div>
              )}

              <div className="pt-4 border-t-2 border-ink bg-canvas p-3.5 rounded-none">
                <div className="font-bold text-ink block uppercase text-[10px] tracking-widest">
                  Not a government record
                </div>
                <p className="text-[11px] text-ink mt-1.5 leading-relaxed">
                  {data.provenance?.warning ?? 'Simulated scenario data. Not a legal instrument.'}
                </p>
                <p className="text-[10px] text-ink-soft mt-1.5">
                  There is no issuing authority. This deployment cannot issue a demand, and
                  nothing here should be presented to anyone as a municipal or legal record.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
