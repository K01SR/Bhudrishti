import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ShieldCheck, Download, Lock, ArrowLeft } from 'lucide-react';

export const PublicVerifyPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchVerifyData();
  }, [token]);

  const fetchVerifyData = async () => {
    try {
      if (!token) {
        setData(null);
        setLoading(false);
        return;
      }
      const res = await fetch(`/api/v1/qr/verify/${encodeURIComponent(token)}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Downloads a statement of what this deployment can and cannot attest.
   *
   * The previous version emitted a text file headed
   *   GOVERNMENT OF MAHARASHTRA - DEPARTMENT OF REVENUE & LAND RECORDS
   *   BHU-DRISHTI 3D CADASTRAL VERIFICATION CERTIFICATE
   * carrying "Official Status", "Verifying Authority" and an Ed25519
   * signature block. This is the page a bank, a buyer or a government office
   * would be sent to, so that file would have been treated as a government
   * record. Nothing here is signed, no authority has verified anything, and no
   * such record exists.
   */
  const handleDownloadStatement = () => {
    if (!data) return;
    const sp = data.spatial_summary ?? {};
    const lines = [
      'BHUDRISHTI 3D - PUBLIC LOOKUP RESULT',
      '='.repeat(72),
      '',
      'THIS IS NOT A GOVERNMENT DOCUMENT AND NOT A CERTIFICATE.',
      '',
      'No government department has issued, registered, verified or signed',
      'anything shown below. This deployment holds no signing key, is not',
      'connected to the DoLR or any other registry, and cannot attest to the',
      'ownership, title, height, storey count or compliance of any property.',
      '',
      '-'.repeat(72),
      'WHAT THIS LOOKUP FOUND',
      '-'.repeat(72),
      `Token                  : ${token}`,
      `Parent parcel ULPIN    : ${data.parent_cadastral_ulpin ?? 'not available'}`,
      `Proposed 3D identifier : ${data.proposed_3d_id ?? 'not available'}`,
      `Structure label        : ${sp.structure_name ?? 'not available'}`,
      `Height                 : ${sp.building_height_m ?? 'not in source'} m`,
      `Storeys                : ${sp.floors_count ?? 'not in source'}`,
      '',
      'Values shown as "not in source" are absent from the underlying open',
      'data. They are not estimates and no value has been substituted.',
      '',
      '-'.repeat(72),
      'WHAT THIS TOOL CANNOT DO',
      '-'.repeat(72),
      '- Cannot issue or verify a ULPIN. Only the state registry can.',
      '- Cannot verify title, lien or encumbrance. CERSAI is not queried.',
      '- Cannot confirm a municipal sanction or occupancy certificate.',
      '- Cannot produce a signature, a fingerprint or a hash chain.',
      '- Cannot confirm any unit is a "registered" cadastral strata unit.',
      '',
      'The token above identifies a row in this prototype database. It is not',
      'a credential and it is not transferable evidence of anything.',
      '='.repeat(72),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'BhuDrishti_3D_lookup_result.txt';
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[80vh] text-ink-soft bg-canvas">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-emerald-600 border-t-transparent rounded-none animate-spin"></div>
          <span className="text-xs font-mono font-bold">Looking up record...</span>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center min-h-[80vh] text-red-600 bg-canvas">
        <div className="text-xs font-mono font-bold">Invalid or expired public verification token.</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Navigation Back */}
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-soft hover:text-ink transition"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Overview</span>
        </Link>

        {/* Verification Header Banner */}
        <div className="bg-white border-2 border-ink p-6 rounded-none shadow-brutal flex items-center gap-5">
          <div className="w-14 h-14 rounded-none bg-emerald-50 text-emerald-700 border-2 border-ink flex items-center justify-center shrink-0 shadow-brutal-sm">
            <ShieldCheck className="w-8 h-8" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-ink">
                Lookup result from a research prototype
              </h1>
              <span className="text-[10px] font-bold bg-amber-100 text-amber-900 border-2 border-ink px-2.5 py-0.5 rounded-none">
                NOT VERIFIED
              </span>
            </div>
            <p className="text-xs text-ink-soft mt-1 font-bold leading-relaxed">
              This is a Bhu-Drishti 3D prototype, not a government service. It is
              not connected to the Maharashtra Department of Revenue &amp; Land
              Records or to any other registry, and it does not verify anything.
              Do not rely on this page for a property transaction.
            </p>
          </div>
        </div>

        {/* Property Details Card */}
        <div className="bg-white border-2 border-slate-200/90 rounded-none p-6 sm:p-8 space-y-5 shadow-brutal text-xs">
          <h2 className="text-sm font-bold text-ink border-b border-ink pb-3">
            Cadastral Identifiers & Physical Summary
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono">
            <div className="bg-canvas p-3.5 rounded-none border-2 border-ink">
              <span className="text-ink-soft font-sans block text-[11px] font-bold">Proposed 3D Spatial ID:</span>
              <span className="text-accent-strong font-bold text-sm">{data.proposed_3d_id}</span>
            </div>

            <div className="bg-canvas p-3.5 rounded-none border-2 border-ink">
              <span className="text-ink-soft font-sans block text-[11px] font-bold">Parent Cadastral ULPIN:</span>
              <span className="text-ink font-bold text-sm">{data.parent_cadastral_ulpin}</span>
            </div>

            <div className="bg-canvas p-3.5 rounded-none border-2 border-ink">
              <span className="text-ink-soft font-sans block text-[11px] font-bold">Structure Envelope:</span>
              <span className="text-ink font-bold">{data.spatial_summary.structure_name}</span>
              <div className="text-[11px] text-ink-soft mt-1">
                Height:{' '}
                {data.spatial_summary.building_height_m != null
                  ? `${data.spatial_summary.building_height_m} m`
                  : 'not in source'}{' '}
                |{' '}
                {data.spatial_summary.floors_count != null
                  ? `${data.spatial_summary.floors_count} storeys`
                  : 'storey count not in source'}
              </div>
            </div>

            <div className="bg-canvas p-3.5 rounded-none border-2 border-ink">
              <span className="text-ink-soft font-sans block text-[11px] font-bold">Total Strata Units:</span>
              <span className="text-ink font-bold text-sm">
                {data.spatial_summary.total_cadastral_units ?? '--'} units in the
                source record
              </span>
              <div className="text-[11px] text-ink-soft mt-1">
                Plot Area: {data.spatial_summary.parcel_area_m2} m²
              </div>
            </div>
          </div>

          {/*
            This block previously showed "Asymmetric Digital Signature: VALID
            (Ed25519)", "Tamper-Evident Hash Chain: VERIFIED CONTINUOUS" and a
            SHA-256 fingerprint. No key was held, nothing was hashed and there
            is no chain. On a page a bank would open, that is a forged
            attestation, so the whole block is replaced by a statement of the
            position.
          */}
          <div className="p-4 bg-canvas rounded-none border-2 border-ink space-y-2 font-mono text-[11px]">
            <div className="flex justify-between items-center">
              <span className="text-ink-soft font-sans">Asymmetric Digital Signature:</span>
              <span className="text-ink font-bold">None produced</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-ink-soft font-sans">Tamper-Evident Hash Chain:</span>
              <span className="text-ink font-bold">Does not exist</span>
            </div>
            <div className="flex flex-col pt-1.5 border-t border-ink">
              <span className="text-ink-soft font-sans text-[10px] leading-relaxed">
                There is no fingerprint either: nothing is signed, so there is
                nothing to hash. This page performs a database lookup and
                displays whatever that row contains. It performs no cryptography
                and no validation.
              </span>
            </div>
          </div>

          {/* DPDP Compliance Notice */}
          <div className="flex items-start gap-3 p-3.5 rounded-none bg-accent-faint border-2 border-ink text-[11px] text-ink font-sans">
            <Lock className="w-4 h-4 text-accent-strong shrink-0 mt-0.5" />
            <div>
              <strong className="block text-ink font-bold">Privacy notice</strong>
              <p className="mt-0.5 text-ink leading-relaxed">{data.privacy_notice}</p>
            </div>
          </div>

          {/* Certificate Download Action */}
          <button
            onClick={handleDownloadStatement}
            className="w-full flex items-center justify-center gap-2 py-3.5 px-4 rounded-none bg-emerald-600 hover:bg-emerald-700 text-white font-bold shadow-brutal shadow-emerald-500/20 text-xs transition"
          >
            <Download className="w-4 h-4" />
            <span>Download Official Cadastral Certificate (PDF/TXT)</span>
          </button>
        </div>
      </div>
    </div>
  );
};
