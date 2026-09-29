import React, { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { X, ShieldCheck, Download, ExternalLink, Lock } from 'lucide-react';
import { HeroProperty } from '../../types/cadastre';
import { fetchBlockchainQrProof } from '../../services/api';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  property: HeroProperty;
}

type ProofState =
  | { status: 'loading' }
  | { status: 'ready'; url: string; fingerprint: string; signature: string }
  | { status: 'absent' };

export const QRVerificationModal: React.FC<Props> = ({
  isOpen,
  onClose,
  property,
}) => {
  const [proof, setProof] = useState<ProofState>({ status: 'loading' });

  const ulpin = property.parent_ulpin;

  useEffect(() => {
    if (!isOpen || !ulpin) return;
    let live = true;
    setProof({ status: 'loading' });
    fetchBlockchainQrProof(ulpin)
      .then((p) => {
        if (!live) return;
        // The server builds the link against its own configured base URL. Retarget
        // it at whichever host actually served this page, so a scan works on a
        // preview deployment instead of bouncing to the production hostname.
        const origin = window.location.origin;
        const remote = new URL(p.verify_url);
        const local = new URL(origin);
        remote.protocol = local.protocol;
        remote.host = local.host;
        setProof({
          status: 'ready',
          url: remote.toString(),
          fingerprint: p.sha256_fingerprint ?? '',
          signature: p.ed25519_signature ?? '',
        });
      })
      .catch(() => {
        if (live) setProof({ status: 'absent' });
      });
    return () => {
      live = false;
    };
  }, [isOpen, ulpin]);

  if (!isOpen) return null;

  const publicUrl = proof.status === 'ready' ? proof.url : null;

  /**
   * Downloads a statement of what this deployment can and cannot attest.
   *
   * The previous version produced a text file headed
   *   GOVERNMENT OF MAHARASHTRA - DEPARTMENT OF REVENUE & LAND RECORDS
   *   BHU-DRISHTI 3D CADASTRAL VERIFICATION CERTIFICATE
   * with "Verification Status: APPROVED & OFFICIALLY REGISTERED", an Ed25519
   * signature, a signing authority, and a "Tamper-Evident Hash:
   * VALID_AUDIT_ANCHOR". None of that existed: the fingerprint was a constant
   * string, the signature was the literal text "sig_ed25519_...", no key was
   * held, and nothing had been registered with anyone. A user could download
   * that file and send it to a buyer, a bank or a government office as though
   * the Revenue Department had issued it. This replacement states the actual
   * position instead.
   */
  const handleDownloadCertificate = () => {
    const lines = [
      'BHUDRISHTI 3D - DATA PROVENANCE STATEMENT',
      '='.repeat(72),
      '',
      'THIS IS NOT A GOVERNMENT DOCUMENT AND NOT A CERTIFICATE.',
      '',
      'No government department has issued, registered, verified or signed',
      'anything described here. This deployment holds no signing key and is not',
      'authorised to attest to the ownership, title, height, floor count, Floor',
      'Space Index or compliance status of any property.',
      '',
      '-'.repeat(72),
      'WHAT THE UNDERLYING DATA ACTUALLY IS',
      '-'.repeat(72),
      `Parent parcel ULPIN    : ${property.parent_ulpin ?? 'not available'}`,
      `Proposed 3D identifier   : ${property.proposed_3d_id ?? 'not available'}`,
      `Data source              : ${property.provenance?.source ?? 'not stated'}`,
      `Treated as authoritative : ${property.provenance?.authoritative ?? false}`,
      '',
      'Height, floor count, FSI and strata unit counts are absent from open',
      'data for most parcels. Where they are missing this tool reports them as',
      'missing. It does not estimate them, and it does not derive a compliance',
      'verdict from them.',
      '',
      '-'.repeat(72),
      'WHAT THIS TOOL CANNOT DO',
      '-'.repeat(72),
      '- Cannot issue a ULPIN. Only the DOLR / state registry can.',
      '- Cannot verify title, lien or encumbrance. CERSAI is not queried.',
      '- Cannot confirm a municipal sanction or occupancy certificate.',
      '- Cannot produce a signature or a tamper-evident hash.',
      '- Cannot state a Floor Space Index that no source has stated.',
      '',
      'Generated from the Bhu-Drishti 3D prototype. No signature, no seal,',
      'no registration, and no verification endpoint that a third party could',
      'check against.',
      '='.repeat(72),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `BhuDrishti_3D_provenance_statement.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-lg bg-chalk border-2 border-ink rounded-none shadow-brutal overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-canvas border-b border-ink">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-none bg-emerald-600 text-white flex items-center justify-center shadow-brutal-sm">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-ink">Data provenance statement</h3>
              <p className="text-[11px] text-ink-soft font-bold">
                What this record is, and what it is not. Not a government
                certificate, and not a signature.
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

        {/* Content */}
        <div className="p-6 space-y-5 text-xs">
          {/* QR Code Graphic */}
          <div className="flex flex-col items-center justify-center p-5 bg-canvas rounded-none border-2 border-ink mx-auto max-w-[220px]">
            {proof.status === 'ready' && publicUrl ? (
              <>
                <div className="p-2 bg-chalk rounded-none shadow-brutal-sm border-2 border-ink">
                  <QRCodeSVG value={publicUrl} size={150} level="H" includeMargin />
                </div>
                <span className="text-[10px] font-mono text-ink-soft mt-2.5 font-bold uppercase tracking-widest">
                  Signed ledger proof
                </span>
              </>
            ) : proof.status === 'loading' ? (
              <p className="text-[11px] font-mono text-ink-soft py-8">Requesting proof…</p>
            ) : (
              <p className="text-[11px] font-mono text-ink-soft py-6 text-center leading-relaxed">
                No ledger proof exists
                <br />
                for ULPIN {ulpin}.
              </p>
            )}
          </div>

          {/* Cryptographic Badges */}
          <div className="p-3.5 bg-canvas rounded-none border-2 border-ink space-y-2 font-mono text-[11px]">
            <div className="flex justify-between items-center">
              <span className="text-ink-soft font-sans">Cadastral Status:</span>
              <span className="text-ink font-bold flex items-center gap-1 bg-canvas px-2 py-0.5 rounded-none border-2 border-ink">
                Unverified record
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-ink-soft font-sans">Proposed 3D ID:</span>
              <span className="text-accent-strong font-bold">{property.proposed_3d_id}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-ink-soft font-sans">Digital Signature:</span>
              <span className="text-ink-soft font-bold">
                {proof.status === 'ready' ? 'Ed25519, in QR' : 'None produced'}
              </span>
            </div>
            <div className="flex flex-col pt-1.5 border-t border-ink">
              <span className="text-ink-soft font-sans text-[10px]">
                {proof.status === 'ready'
                  ? 'The QR carries the signed fields, so anyone can check the signature. Signing is not approval.'
                  : 'No fingerprint: nothing is signed, so there is nothing to hash.'}
              </span>
            </div>
          </div>

          {/* Privacy Notice */}
          <div className="flex items-start gap-2.5 p-3 rounded-none bg-accent-faint border-2 border-ink text-[11px] text-ink">
            <Lock className="w-4 h-4 text-accent-strong shrink-0 mt-0.5" />
            <p>
              Ownership names and loan values are left out of the public proof payload. That is a
              deliberate data-minimisation choice in this codebase, not a certified DPDP Act 2023
              compliance claim: no audit has been carried out here.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleDownloadCertificate}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-none bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-brutal-sm shadow-emerald-500/20 transition"
            >
              <Download className="w-4 h-4" />
              <span>Download Certificate</span>
            </button>
            {publicUrl ? (
              <a
                href={publicUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-none bg-canvas hover:bg-canvas text-ink font-bold border-2 border-ink transition"
              >
                <ExternalLink className="w-4 h-4 text-ink-soft" />
                <span>Open Public Page</span>
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};
