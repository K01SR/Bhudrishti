import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ShieldCheck, ShieldAlert, ArrowLeft, CheckCircle2, AlertTriangle } from 'lucide-react';
import {
  fetchBlockchainQrProof,
  verifyBlockchainQrProof,
} from '../services/api';
import { BlockchainQrProof, BlockchainQrProofVerification } from '../types/cadastre';

/**
 * The page a scanned blockchain proof lands on.
 *
 * Two properties are deliberate:
 *
 * 1. It works from the query string alone. The proof travels in the URL, so
 *    this page needs no login and no session, and the checks below still
 *    succeed if this deployment is offline. A verifier must not have to trust
 *    the server that issued the proof in order to check the proof.
 *
 * 2. It never renders a bare "VERIFIED". A valid Merkle path and a valid
 *    signature are two different findings, and neither of them means a
 *    government office confirmed the property. The page says which is which.
 */
export const BlockchainVerifyPage: React.FC = () => {
  const [params] = useSearchParams();
  const encoded = params.get('p');

  const [proof, setProof] = useState<BlockchainQrProof | null>(null);
  const [result, setResult] = useState<BlockchainQrProofVerification | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      if (!encoded) {
        setLoadError(
          'This link carries no proof. Scan the QR code, or open the full link exactly as issued.'
        );
        setLoading(false);
        return;
      }

      let parsed: BlockchainQrProof;
      try {
        parsed = JSON.parse(decodeURIComponent(encoded)) as BlockchainQrProof;
      } catch {
        setLoadError('The proof in this link could not be read. It may have been truncated by the scanner or messaging app.');
        setLoading(false);
        return;
      }

      if (cancelled) return;
      setProof(parsed);

      // Server-side check of the submitted bytes. The signature and Merkle path
      // are both re-derived here rather than trusted from the URL.
      try {
        const check = await verifyBlockchainQrProof(parsed);
        if (!cancelled) setResult(check);
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error
              ? `Could not reach the verification service: ${err.message}`
              : 'Could not reach the verification service.'
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [encoded]);

  // The issued proof is retrievable from the ledger too. Offered as a second
  // opinion: if the scanned payload and the ledger disagree, the ledger copy
  // is what this deployment currently holds.
  const [ledgerCopy, setLedgerCopy] = useState<BlockchainQrProof | null>(null);
  const [ledgerNote, setLedgerNote] = useState<string | null>(null);
  const [loadingLedger, setLoadingLedger] = useState(false);

  const checkLedger = async () => {
    if (!proof) return;
    setLoadingLedger(true);
    setLedgerNote(null);
    try {
      const fresh = await fetchBlockchainQrProof(proof.tx_id);
      setLedgerCopy(fresh);
      setLedgerNote(
        fresh.sha256_fingerprint === proof.sha256_fingerprint
          ? 'The ledger holds a proof with the same fingerprint. The scanned payload matches what is recorded here.'
          : 'The ledger holds a DIFFERENT fingerprint for this transaction. Treat the scanned code as suspect.'
      );
    } catch {
      setLedgerNote('The ledger copy could not be retrieved right now.');
    } finally {
      setLoadingLedger(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[80vh] text-ink-soft bg-canvas">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-emerald-600 border-t-transparent animate-spin"></div>
          <span className="text-xs font-mono font-bold">Checking proof...</span>
        </div>
      </div>
    );
  }

  const sigOk = !!result?.signature_valid;
  const merkleOk = !!result?.merkle_path_valid;
  const bothOk = sigOk && merkleOk;

  return (
    <div className="min-h-screen bg-canvas py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-soft hover:text-ink transition"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Overview</span>
        </Link>

        <div className="bg-white border-2 border-ink p-6 rounded-none shadow-brutal flex items-start gap-5">
          <div
            className={`w-14 h-14 rounded-none border-2 border-ink flex items-center justify-center shrink-0 shadow-brutal-sm ${
              bothOk ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-crimson-700'
            }`}
          >
            {bothOk ? <ShieldCheck className="w-8 h-8" /> : <ShieldAlert className="w-8 h-8" />}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-ink">
                {loadError
                  ? 'Proof could not be checked'
                  : bothOk
                    ? 'Hash chain and signature both check out'
                    : 'This proof did not fully check out'}
              </h1>
              <span className="text-[10px] font-bold bg-amber-100 text-amber-900 border-2 border-ink px-2.5 py-0.5 rounded-none">
                NOT A GOVERNMENT RECORD
              </span>
            </div>
            <p className="text-xs text-ink-soft mt-2 font-bold leading-relaxed">
              Bhu-Drishti is a research prototype. It is not connected to the
              Maharashtra Department of Revenue &amp; Land Records or to any
              registry. What follows is a cryptographic consistency check on
              this deployment&apos;s own data, not a validation of any property.
            </p>
          </div>
        </div>

        {loadError && (
          <div className="p-4 border-2 border-crimson-600 text-crimson-700 font-mono text-xs">
            {loadError}
          </div>
        )}

        {result?.error && (
          <div className="p-4 border-2 border-crimson-600 text-crimson-700 font-mono text-xs">
            {result.error}
          </div>
        )}

        {proof && !loadError && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div
                className={`p-4 border-2 font-mono text-xs space-y-1 ${
                  merkleOk ? 'border-emerald-600' : 'border-crimson-600'
                }`}
              >
                <p className={`font-bold flex items-center gap-2 ${merkleOk ? 'text-emerald-800' : 'text-crimson-700'}`}>
                  {merkleOk ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                  Merkle path
                </p>
                <p className={merkleOk ? 'text-emerald-800' : 'text-crimson-700'}>
                  {merkleOk
                    ? 'The transaction id hashes up to the Merkle root this proof names.'
                    : `Does not reach the stated root.${result?.merkle_error ? ` (${result.merkle_error})` : ''}`}
                </p>
                <p className="text-ink-soft">
                  {result?.merkle_path_valid
                    ? 'Requires no key: it only checks the block\'s own hashes.'
                    : 'The block\'s hash chain does not support this payload.'}
                </p>
              </div>

              <div
                className={`p-4 border-2 font-mono text-xs space-y-1 ${
                  sigOk ? 'border-emerald-600' : 'border-crimson-600'
                }`}
              >
                <p className={`font-bold flex items-center gap-2 ${sigOk ? 'text-emerald-800' : 'text-crimson-700'}`}>
                  {sigOk ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                  Ed25519 signature
                </p>
                <p className={sigOk ? 'text-emerald-800' : 'text-crimson-700'}>
                  {sigOk
                    ? 'Signed by the key this proof carries.'
                    : result?.signature_error || 'Does not match the public key supplied.'}
                </p>
                <p className="text-ink-soft">
                  {sigOk
                    ? 'The signature covers the ten fields listed below.'
                    : 'Nothing here attests that this deployment issued the payload.'}
                </p>
              </div>
            </div>

            {result?.disclosure && (
              <div className="bg-white border-2 border-ink p-5 rounded-none font-mono text-xs space-y-2">
                <p className="font-bold text-ink">What this does and does not establish</p>
                <div className="space-y-1 text-ink-soft">
                  <p><span className="text-ink font-bold">The Merkle path proves:</span> {result.disclosure.merkle_path_proves}</p>
                  <p><span className="text-ink font-bold">The signature proves:</span> {result.disclosure.signature_proves}</p>
                </div>
                <div className="pt-2 space-y-1">
                  <p className="font-bold text-crimson-700">It does NOT prove:</p>
                  {result.disclosure.does_not_prove.map((line) => (
                    <p key={line} className="text-crimson-700">- {line}</p>
                  ))}
                  {result.disclosure.signature_uses_published_demo_key && (
                    <p className="text-crimson-700 font-bold">
                      - The signature was made with a keypair published in this
                      repository. It identifies the software, not a person or an
                      office.
                    </p>
                  )}
                </div>
              </div>
            )}

            <div className="bg-white border-2 border-ink p-5 rounded-none font-mono text-xs space-y-1.5">
              <p className="font-bold text-ink mb-2">Proof contents</p>
              {[
                ['ULPIN', proof.ulpin],
                ['Transaction', proof.tx_id],
                ['Block', `#${proof.block_height}`],
                ['Validator', proof.validator],
                ['Recorded', proof.timestamp],
                ['Merkle root', proof.merkle_root],
                ['Block hash', proof.block_hash],
                ['SHA-256', proof.sha256_fingerprint ?? 'not signed'],
                ['Signature', proof.ed25519_signature ?? 'not signed'],
                ['Public key', proof.public_key_hex ?? 'not published'],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-0.5 border-b border-dashed border-ink-soft">
                  <span className="text-ink-soft shrink-0">{k}</span>
                  <span className="text-ink break-all text-right">{v}</span>
                </div>
              ))}
              {result?.signed_fields && (
                <p className="text-ink-soft pt-2">
                  Signature covers: {result.signed_fields.join(', ')}
                </p>
              )}
            </div>

            <div className="bg-white border-2 border-ink p-5 rounded-none font-mono text-xs space-y-3">
              <p className="font-bold text-ink">Second opinion: the ledger copy</p>
              <p className="text-ink-soft">
                The checks above examine the bytes in this link. This compares
                them against the proof this deployment currently holds for the
                same transaction.
              </p>
              <button
                onClick={checkLedger}
                disabled={loadingLedger}
                className="px-3 py-2 bg-ink text-white text-xs font-bold hover:bg-ink transition disabled:opacity-40"
              >
                {loadingLedger ? 'Retrieving...' : 'Compare against ledger'}
              </button>
              {ledgerNote && (
                <p className="text-ink-soft">{ledgerNote}</p>
              )}
              {ledgerCopy && (
                <p className="text-ink-soft break-all">
                  Ledger fingerprint: {ledgerCopy.sha256_fingerprint ?? 'not signed'}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
