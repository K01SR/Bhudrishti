import React, { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import {
  Lock,
  ShieldCheck,
  ShieldAlert,
  ArrowDown,
  RefreshCw,
  AlertTriangle,
  Sparkles,
  FileText,
  QrCode,
  CheckCircle2,
  Layers,
  Cpu,
  Server,
  Download,
  Key,
  Database,
  X
} from 'lucide-react';
import {
  fetchBlockchainBlocks,
  verifyBlockchain,
  fetchBlockchainStats,
  simulateBlockchainTamper,
  selfHealBlockchain,
  fetchBlockchainQrProof,
  verifyBlockchainQrProof,
  simulateSmartContract,
  mineBlockchainBlock,
  CADASTRAL_EXCEL_URL,
  PROPERTY_CARD_PDF_URL,
  PROPERTY_CARD_LATEX_URL
} from '../../services/api';
import { BlockchainBlock, BlockchainVerification, BlockchainStats, BlockchainQrProof, BlockchainQrProofVerification } from '../../types/cadastre';
import { Card, Badge, Skeleton } from '../../components/ui';

/**
 * Rewrites the proof's verification link onto the origin currently being
 * viewed.
 *
 * The server builds the link from PUBLIC_BASE_URL, which is unset by default
 * and so resolves to http://localhost:3000. Left alone, a QR generated in the
 * browser would then hand a phone a dead localhost address in production. Only
 * the host changes here: the path and the encoded payload come from the server
 * untouched, and the signature covers the payload, not the host, so
 * re-pointing the link does not weaken or alter the proof.
 */
const scannableProofUrl = (proof: BlockchainQrProof): string => {
  try {
    const url = new URL(proof.verify_url);
    return `${window.location.origin}${url.pathname}${url.search}`;
  } catch {
    return proof.verify_url;
  }
};

export const AuditPage: React.FC = () => {
  const [blocks, setBlocks] = useState<BlockchainBlock[]>([]);
  const [verification, setVerification] = useState<BlockchainVerification | null>(null);
  const [, setStats] = useState<BlockchainStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedProof, setSelectedProof] = useState<BlockchainQrProof | null>(null);
  const [proofCheck, setProofCheck] = useState<BlockchainQrProofVerification | null>(null);
  const [proofChecking, setProofChecking] = useState(false);
  const [proofError, setProofError] = useState<string | null>(null);
  const [smartContractModal, setSmartContractModal] = useState(false);
  const [contractResult, setContractResult] = useState<any | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [blocksRes, verifyRes, statsRes] = await Promise.all([
        fetchBlockchainBlocks(),
        verifyBlockchain(),
        fetchBlockchainStats()
      ]);
      setBlocks(blocksRes.blocks || []);
      setVerification(verifyRes);
      setStats(statsRes);
    } catch (err) {
      console.error('Error loading blockchain data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const triggerToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const handleSimulateTamper = async () => {
    setActionLoading(true);
    try {
      await simulateBlockchainTamper(5, 'consideration_inr', 500000);
      const v = await verifyBlockchain();
      setVerification(v);
      triggerToast('[Alert] Tamper Injected! Block #5 consideration altered to ₹5,00,000. Blockchain integrity compromised!');
    } catch (e: any) {
      triggerToast(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSelfHeal = async () => {
    setActionLoading(true);
    try {
      await selfHealBlockchain();
      await loadData();
      triggerToast('Blockchain Self-Healed! Consensus restored from 5 peer validator nodes.');
    } catch (e: any) {
      triggerToast(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleMineBlock = async () => {
    setActionLoading(true);
    try {
      const res = await mineBlockchainBlock('demo-local-process');
      await loadData();
      triggerToast(`Appended demo record #${res.block?.index ?? 'new'} (hash ${res.block?.hash?.slice(0, 12)}…). No mining or consensus is involved.`);
    } catch (e: any) {
      triggerToast(`Mining error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenQrProof = async (ulpin: string) => {
    setProofError(null);
    try {
      const proof = await fetchBlockchainQrProof(ulpin);
      setSelectedProof(proof);
      setProofCheck(null);
      setProofChecking(false);
    } catch (e) {
      // An identifier with no ledger transaction now returns 404 instead of a
      // proof for a different parcel, so this is a case the user can hit. It
      // has to say so; swallowing it would look like the button did nothing.
      setProofError(
        e instanceof Error
          ? e.message
          : 'No proof is available for this transaction.'
      );
    }
  };

  /**
   * Asks the server to check the proof the way a third party holding only the
   * QR would: submit the payload, get back the Merkle result and the signature
   * result as two separate answers.
   */
  const handleVerifyProof = async () => {
    if (!selectedProof) return;
    setProofChecking(true);
    try {
      setProofCheck(await verifyBlockchainQrProof(selectedProof));
    } catch (e) {
      setProofCheck({
        signature_valid: false,
        merkle_path_valid: false,
        fingerprint_matches: false,
        recomputed_sha256: '',
        claimed_sha256: null,
        signed_fields: [],
        algorithm: '',
        error: e instanceof Error ? e.message : 'Verification request failed',
      });
    } finally {
      setProofChecking(false);
    }
  };

  const handleRunSmartContract = async (type: string) => {
    try {
      const res = await simulateSmartContract(type);
      setContractResult(res);
    } catch (e) {
      console.error(e);
    }
  };

  const isCorrupted = verification?.integrity === 'CORRUPTED';

  return (
    <div className="flex flex-col gap-6 animate-rise-in max-w-7xl mx-auto pb-16">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-5 py-3 rounded-none shadow-brutal-xl border-2 border-white/10 flex items-center gap-3 animate-slide-up text-sm font-bold">
          <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
          <span>{toastMessage}</span>
          <button onClick={() => setToastMessage(null)} className="ml-2 text-ink-soft hover:text-white" aria-label="Dismiss"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-accent-strong uppercase tracking-widest">
            <span>Demo Log</span>
            <span>/</span>
            <span>Event History</span>
          </div>
          <h1 className="text-3xl font-black text-ink font-display tracking-tight mt-1 flex items-center gap-3">
            Append-only Prototype Event Log
            <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-none bg-accent-faint text-accent-strong border-2 border-ink">
              Not a blockchain
            </span>
          </h1>
          <p className="text-sm text-ink-soft mt-1 max-w-3xl">
            A list of events held in this prototype&apos;s own memory, signed with a key it generates itself. There
            is no distributed network, no mining, no consensus between parties, and no signature from a builder,
            verifier or citizen — the single &ldquo;miner&rdquo; label below is a string passed to an in-process function.
          </p>
        </div>

        {/* Global Chain Health Badge */}
        {verification && (
          <div className={`flex items-center gap-2.5 px-4 py-2.5 rounded-none text-xs font-bold border-2 shadow-brutal-sm ${
            isCorrupted
              ? 'bg-rose-50 border-ink text-rose-800 animate-pulse'
              : 'bg-emerald-50 border-ink text-emerald-800'
          }`}>
            {isCorrupted ? (
              <>
                <ShieldAlert className="w-5 h-5 text-rose-600 shrink-0" />
                <div>
                  <div className="text-[11px] font-black tracking-wide">TAMPER DETECTED ON-CHAIN</div>
                  <div className="text-[10px] opacity-80">Block #{verification.broken_block_index} Payload Corrupted</div>
                </div>
              </>
            ) : (
              <>
                <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" />
                <div>
                  <div className="text-[11px] font-black tracking-wide">CONSENSUS VERIFIED (IMMUTABLE)</div>
                  <div className="text-[10px] opacity-80">{blocks.length} Blocks & Merkle Roots Intact</div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Network Stats & Control Ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-4 border-ink flex flex-col justify-between">
          <div className="flex items-center justify-between text-ink-soft text-xs font-bold">
            <span>CHAIN HEIGHT</span>
            <Layers className="w-4 h-4 text-accent-strong" />
          </div>
          <div className="text-2xl font-black font-mono text-ink mt-2">
            #{blocks.length > 0 ? blocks.length - 1 : 0}
          </div>
          <div className="text-[11px] text-ink-soft mt-1 font-mono">
            {blocks.length} Total Sealed Blocks
          </div>
        </Card>

        <Card className="p-4 border-ink flex flex-col justify-between">
          <div className="flex items-center justify-between text-ink-soft text-xs font-bold">
            <span>ACTIVE PEERS</span>
            <Server className="w-4 h-4 text-accent-strong" />
          </div>
          <div className="text-2xl font-black font-mono text-ink mt-2">
            5 / 5
          </div>
          <div className="text-[11px] text-emerald-800 font-bold mt-1">
            No external party is a party to this log
          </div>
        </Card>

        <Card className="p-4 border-ink flex flex-col justify-between">
          <div className="flex items-center justify-between text-ink-soft text-xs font-bold">
            <span>CONSENSUS ALGORITHM</span>
            <Cpu className="w-4 h-4 text-amber-600" />
          </div>
          <div className="text-2xl font-black font-mono text-ink mt-2">
            PoW + Multi-Sig
          </div>
          <div className="text-[11px] text-ink-soft mt-1 font-mono">
            Difficulty: 2 Leading Zeros
          </div>
        </Card>

        <Card className="p-4 border-ink flex flex-col justify-between">
          <div className="flex items-center justify-between text-ink-soft text-xs font-bold">
            <span>SMART CONTRACTS</span>
            <Database className="w-4 h-4 text-accent-strong" />
          </div>
          <div className="text-2xl font-black font-mono text-ink mt-2">
            4 Active
          </div>
          <div className="text-[11px] text-accent-strong font-bold mt-1">
            FSI Guard, Multi-Sig Escrow
          </div>
        </Card>
      </div>

      {/* Interactive Actions Toolbar */}
      {/* Was `bg-chalk text-white`: white heading text on a white card, and
          `border-none` removed the only other edge, so the whole toolbar
          disappeared. The inner Lock tile is already light, so the card is the
          dark element and `bg-ink` is what makes its `text-white` children
          legible. */}
        <Card className="p-4 bg-ink text-white border-2 border-ink shadow-brutal-lg flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-none bg-canvas border-2 border-ink flex items-center justify-center text-ink-mut">
            <Lock className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-sm text-white">Cryptographic Fault Injection & Self-Healing Console</h3>
            <p className="text-xs text-canvas/70">Test Byzantine tamper-detection or restore authentic state from peer validators</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Verify Integrity Button */}
          <button
            onClick={loadData}
            disabled={actionLoading}
            className="px-3.5 py-2 rounded-none bg-chalk hover:bg-accent text-ink border-2 border-ink shadow-brutal hover:shadow-none hover:translate-x-[3px] hover:translate-y-[3px] text-xs font-black uppercase tracking-wide transition flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${actionLoading ? 'animate-spin' : ''}`} />
            Audit Ledger
          </button>

          {/* Tamper Attack Simulation */}
          <button
            onClick={handleSimulateTamper}
            disabled={actionLoading || isCorrupted}
            className={`px-3.5 py-2 rounded-none text-xs font-bold transition flex items-center gap-1.5 ${
              isCorrupted
                ? 'bg-crimson-600 border-2 border-ink text-white opacity-60 cursor-not-allowed'
                : 'bg-crimson-600 hover:bg-crimson-700 text-white border-2 border-ink shadow-brutal'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            Simulate Tamper
          </button>

          {/* Self-Heal Button */}
          <button
            onClick={handleSelfHeal}
            disabled={actionLoading || !isCorrupted}
            className={`px-4 py-2 rounded-none text-xs font-bold transition flex items-center gap-1.5 ${
              isCorrupted
                ? 'bg-emerald-500 hover:bg-emerald-600 text-black border-2 border-ink shadow-brutal'
                : 'bg-canvas text-ink-mut border-2 border-ink opacity-50 cursor-not-allowed'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            Peer Consensus Heal
          </button>

          {/* Mine Pending Block */}
          <button
            onClick={handleMineBlock}
            disabled={actionLoading}
            className="px-3.5 py-2 rounded-none bg-amber-600 hover:bg-amber-700 text-ink text-xs font-bold transition flex items-center gap-1.5 shadow-brutal"
            title="Mine next block on the sovereign cadastral blockchain"
          >
            <Cpu className="w-3.5 h-3.5" />
            Mine Block
          </button>

          {/* Smart Contract Console */}
          <button
            onClick={() => { setSmartContractModal(true); handleRunSmartContract('FSI_GUARD'); }}
            className="px-3.5 py-2 rounded-none bg-ink hover:bg-ink text-white text-xs font-bold transition flex items-center gap-1.5"
          >
            <Cpu className="w-3.5 h-3.5" />
            Smart Contracts
          </button>

          {/* Export Excel Cadastre */}
          <a
            href={CADASTRAL_EXCEL_URL}
            download="Bhu_Drishti_Cadastral_Register.xlsx"
            className="px-3.5 py-2 rounded-none bg-ink hover:bg-ink text-white text-xs font-bold transition flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Export Excel
          </a>
        </div>
      </Card>

      {/* Tamper Alert Banner */}
      {isCorrupted && verification && (
        <Card className="p-4 bg-rose-50 border-ink text-rose-900 animate-rise-in">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-none bg-rose-200/60 text-rose-800">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <h4 className="font-bold text-sm text-rose-900">
                CRITICAL HASH LINKAGE VIOLATION AT BLOCK #{verification.broken_block_index}
              </h4>
              <p className="text-xs text-rose-800 mt-1 leading-relaxed">
                {verification.reason}
              </p>
              <div className="mt-3 flex items-center gap-3">
                <button
                  onClick={handleSelfHeal}
                  className="px-3.5 py-1.5 bg-rose-700 text-white rounded-none text-xs font-bold hover:bg-rose-800 transition flex items-center gap-1.5"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Restore Chain from Peer Nodes
                </button>
                <span className="text-[11px] text-rose-700 font-mono">
                  Fault Detected: Silent Payload Modification without Valid Private Key
                </span>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Chronological Blocks Feed */}
      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-44 rounded-none" />
          <Skeleton className="h-44 rounded-none" />
          <Skeleton className="h-44 rounded-none" />
        </div>
      ) : (
        <div className="space-y-4">
          {blocks.map((b, i) => {
            const isCorruptBlock = isCorrupted && verification?.broken_block_index === b.index;
            const primaryTx = b.transactions[0];

            return (
              <div key={b.index} className="relative">
                <Card className={`p-5 text-xs transition duration-200 ${
                  isCorruptBlock
                    ? 'border-2 border-rose-500 bg-rose-50/40 shadow-brutal-lg'
                    : 'border-ink hover:border-ink hover:shadow-brutal'
                }`}>
                  {/* Block Header */}
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink pb-3">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <div className={`px-2.5 py-1 rounded-none font-mono font-black text-xs ${
                        isCorruptBlock
                          ? 'bg-rose-600 text-white'
                          : 'bg-ink text-white'
                      }`}>
                        Block #{b.index}
                      </div>

                      <span className="font-bold text-ink text-sm">
                        {primaryTx ? primaryTx.tx_type.replace(/_/g, ' ') : 'EMPTY BLOCK'}
                      </span>

                      <span className="font-mono text-[10px] px-2 py-0.5 rounded-none bg-canvas text-ink font-bold">
                        Nonce: {b.nonce} (PoW Target: 00)
                      </span>

                      {b.index === 0 && (
                        <Badge tone="purple">GENESIS STATE ROOT</Badge>
                      )}
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="font-mono text-ink-soft text-[11px]">
                        {new Date(b.timestamp).toLocaleString()}
                      </span>
                      <button
                        onClick={() => primaryTx && handleOpenQrProof(primaryTx.ulpin)}
                        className="p-1.5 rounded-none bg-canvas hover:bg-accent-faint hover:text-accent-strong transition"
                        title="View Cryptographic QR Verification Proof"
                      >
                        <QrCode className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Transaction Details & Spatial Envelope */}
                  {primaryTx && (
                    <div className="mt-3.5 space-y-2">
                      <div className="flex items-center justify-between text-[11px] text-ink-soft">
                        <span className="font-mono font-bold text-accent-strong">
                          ULPIN: {primaryTx.ulpin} &nbsp;|&nbsp; Spatial ID: {primaryTx.spatial_id}
                        </span>
                        <span className="text-ink-soft">
                          TX ID: <code className="font-mono">{primaryTx.tx_id.slice(0, 16)}...</code>
                        </span>
                      </div>

                      {/* Transaction Payload Box */}
                      <div className="p-3 bg-canvas rounded-none border-2 border-ink font-mono text-[11px] text-ink overflow-x-auto">
                        <pre className="whitespace-pre-wrap">{JSON.stringify(primaryTx.payload, null, 2)}</pre>
                      </div>

                      {/* Multi-Party Threshold Signatures */}
                      <div className="mt-2.5 pt-2 border-t border-ink flex flex-wrap items-center gap-2">
                        <span className="text-[10px] uppercase font-bold text-ink-soft flex items-center gap-1">
                          <Key className="w-3 h-3 text-amber-500" /> Multi-Sig Seals:
                        </span>
                        {Object.keys(b.multi_signatures ?? {}).length === 0 ? (
                          <span className="px-2 py-0.5 rounded-none bg-canvas border-2 border-ink text-ink-soft text-[10px] font-mono">
                            None. No third party has signed this block.
                          </span>
                        ) : (
                          Object.entries(b.multi_signatures).map(([auth, sig]) => (
                            <span key={auth} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-none bg-emerald-50 border-2 border-ink text-emerald-800 text-[10px] font-mono">
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                              <span className="font-bold">{auth}:</span> {sig.slice(0, 10)}...
                            </span>
                          ))
                        )}
                      </div>
                    </div>
                  )}

                  {/* Hash Proof Ribbon (Previous Hash -> Merkle Root -> Block Hash) */}
                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2.5 font-mono text-[10px]">
                    <div className="p-2.5 rounded-none bg-slate-100/80 border-2 border-ink">
                      <span className="block text-ink-soft font-sans font-bold text-[9px] uppercase tracking-widest">
                        Previous Block Hash
                      </span>
                      <span className="block truncate text-ink-soft mt-0.5">
                        {b.previous_hash}
                      </span>
                    </div>

                    <div className="p-2.5 rounded-none bg-accent-faint border-2 border-ink">
                      <span className="block text-accent-strong font-sans font-bold text-[9px] uppercase tracking-widest">
                        Merkle Tree Root
                      </span>
                      <span className="block truncate font-bold text-ink mt-0.5">
                        {b.merkle_root}
                      </span>
                    </div>

                    <div className={`p-2.5 rounded-none border-2 ${
                      isCorruptBlock
                        ? 'bg-rose-100 border-ink'
                        : 'bg-emerald-50 border-ink'
                    }`}>
                      <span className={`block font-sans font-bold text-[9px] uppercase tracking-widest ${
                        isCorruptBlock ? 'text-rose-700 font-bold' : 'text-emerald-700'
                      }`}>
                        {isCorruptBlock ? 'Corrupted Block Hash' : 'Sealed Block Hash (PoW)'}
                      </span>
                      <span className={`block truncate font-bold mt-0.5 ${
                        isCorruptBlock ? 'text-rose-900' : 'text-emerald-900'
                      }`}>
                        {b.block_hash}
                      </span>
                    </div>
                  </div>

                  {/* Official Export Links for Building Block */}
                  {b.index === 5 && (
                    <div className="mt-3 pt-3 border-t border-ink flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[11px] font-bold text-ink flex items-center gap-1.5">
                        <FileText className="w-3.5 h-3.5 text-accent-strong" />
                        Official 3D Cadastral Deed & Property Card (Form 3D-ULPIN)
                      </span>
                      <div className="flex items-center gap-2">
                        <a
                          href={primaryTx?.ulpin ? PROPERTY_CARD_PDF_URL(primaryTx.ulpin) : undefined}
                          aria-disabled={!primaryTx?.ulpin}
                          title={primaryTx?.ulpin ? undefined : 'No cadastral record for this transaction'}
                          download="Property_Card_3D.pdf"
                          className="px-2.5 py-1 bg-accent-faint hover:bg-accent-faint text-accent-strong border-2 border-ink rounded-none text-[10px] font-bold transition flex items-center gap-1"
                        >
                          <Download className="w-3 h-3" />
                          Deed PDF
                        </a>
                        <a
                          href={primaryTx?.ulpin ? PROPERTY_CARD_LATEX_URL(primaryTx.ulpin) : undefined}
                          aria-disabled={!primaryTx?.ulpin}
                          title={primaryTx?.ulpin ? undefined : 'No cadastral record for this transaction'}
                          download="Property_Card_3D.tex"
                          className="px-2.5 py-1 bg-canvas hover:bg-canvas text-ink border-2 border-ink rounded-none text-[10px] font-bold transition flex items-center gap-1"
                        >
                          LaTeX (.tex)
                        </a>
                      </div>
                    </div>
                  )}
                </Card>

                {/* Chain Link Indicator */}
                {i < blocks.length - 1 && (
                  <div className="flex justify-center my-1.5 text-ink-soft">
                    <ArrowDown className={`w-4 h-4 ${isCorrupted ? 'text-rose-400' : 'text-accent-strong'}`} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* No proof available. Shown instead of a modal rather than a silent
          no-op, so a missing ledger record is legible. */}
      {proofError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
          <Card className="max-w-md w-full p-6 bg-white rounded-none shadow-brutal-xl space-y-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-crimson-700" />
              <h3 className="font-bold text-ink text-base">No proof available</h3>
            </div>
            <p className="text-xs text-ink-soft leading-relaxed">{proofError}</p>
            <p className="text-xs text-ink-soft leading-relaxed">
              A proof is only issued for a transaction that is actually in the
              ledger. Nothing is substituted for a missing record.
            </p>
            <button
              onClick={() => setProofError(null)}
              className="w-full py-2.5 bg-ink text-white rounded-none text-xs font-bold hover:bg-ink transition"
            >
              Close
            </button>
          </Card>
        </div>
      )}

      {/* QR Proof Modal */}
      {selectedProof && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
          <Card className="max-w-md w-full p-6 bg-white rounded-none shadow-brutal-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <QrCode className="w-5 h-5 text-accent-strong" />
                {/* Not "On-Chain": this ledger is an in-process list, not a
                    distributed chain, and the word would imply a stronger
                    guarantee than exists. */}
                <h3 className="font-bold text-ink text-base">Signed Ledger Proof</h3>
              </div>
              <button onClick={() => setSelectedProof(null)} className="text-ink-soft hover:text-ink">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex flex-col items-center justify-center p-4 bg-canvas rounded-none border-2">
              {/* A real, scannable QR. This used to be a black box with the
                  words "[ CRYPTOGRAPHIC VERIFY QR ]" printed inside it, which
                  no camera could read and which therefore verified nothing --
                  it looked like a QR and was decorative only.

                  It now encodes the whole signed proof, so scanning it yields
                  the exact bytes this deployment signed. A third party can
                  recompute the SHA-256, check the Ed25519 signature against the
                  embedded public key, and walk the Merkle path to the root,
                  with no account and no trust in this app. */}
              <div className="w-56 h-56 bg-white p-3 rounded-none border-2 flex items-center justify-center">
                {selectedProof.ed25519_signature ? (
                  <QRCodeSVG
                    value={scannableProofUrl(selectedProof)}
                    size={200}
                    level="M"
                    includeMargin
                    data-testid="blockchain-qr"
                  />
                ) : (
                  <div className="text-center font-mono text-[10px] text-ink-soft px-2">
                    No QR issued.
                    <br />
                    <br />
                    This deployment holds no signing key, so it has nothing to
                    put its name to. {selectedProof.signing_error}
                  </div>
                )}
              </div>
              <p className="text-[11px] text-ink-soft font-mono mt-3 text-center max-w-sm">
                Scan with any camera. The link carries the transaction id, the
                block, the Merkle root and path, and this deployment&apos;s
                Ed25519 signature over all of it. It opens without a login and
                still checks out if this deployment is later switched off.
              </p>
            </div>

            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex justify-between py-1 border-b">
                <span className="text-ink-soft">Block Height:</span>
                <span className="font-bold text-ink">#{selectedProof.block_height}</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <span className="text-ink-soft">ULPIN:</span>
                <span className="font-bold text-accent-strong">{selectedProof.ulpin}</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <span className="text-ink-soft">Merkle Root:</span>
                <span className="truncate max-w-[200px] text-ink">{selectedProof.merkle_root}</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <span className="text-ink-soft">Validator:</span>
                <span className="text-emerald-700 font-bold">{selectedProof.validator}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-ink-soft">SHA-256:</span>
                <span className="truncate max-w-[200px] text-ink">
                  {selectedProof.sha256_fingerprint ?? 'not signed'}
                </span>
              </div>
            </div>

            {/* Real verification: the same check a third party with only the QR
                would run. Two independent answers, because they fail
                differently -- a valid Merkle path says the transaction really is
                in the block, the signature says this deployment vouched for the
                body. Collapsing them into one "VERIFIED" would hide the case
                that matters. */}
            <button
              onClick={handleVerifyProof}
              disabled={proofChecking}
              className="w-full py-2.5 bg-ink text-white rounded-none text-xs font-bold hover:bg-ink transition disabled:opacity-40"
            >
              {proofChecking ? 'Checking…' : 'Verify this proof now'}
            </button>

            {proofCheck && (
              <div
                className="space-y-2 text-[11px]"
                data-testid="proof-verification"
                data-signature={proofCheck.signature_valid ? 'valid' : 'invalid'}
                data-merkle={proofCheck.merkle_path_valid ? 'valid' : 'invalid'}
              >
                {proofCheck.error ? (
                  <div className="p-2.5 border-2 border-crimson-600 text-crimson-700 font-mono">
                    {proofCheck.error}
                  </div>
                ) : (
                  <>
                    <div
                      className={`flex items-start gap-2 p-2.5 border-2 font-mono ${
                        proofCheck.merkle_path_valid
                          ? 'border-emerald-600 text-emerald-800'
                          : 'border-crimson-600 text-crimson-700'
                      }`}
                    >
                      {proofCheck.merkle_path_valid ? (
                        <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                      ) : (
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                      )}
                      <span>
                        Merkle path:{' '}
                        {proofCheck.merkle_path_valid
                          ? 'transaction id hashes up to the stated root'
                          : `does NOT reach the stated root${proofCheck.merkle_error ? ` (${proofCheck.merkle_error})` : ''}`}
                      </span>
                    </div>
                    <div
                      className={`flex items-start gap-2 p-2.5 border-2 font-mono ${
                        proofCheck.signature_valid
                          ? 'border-emerald-600 text-emerald-800'
                          : 'border-crimson-600 text-crimson-700'
                      }`}
                    >
                      {proofCheck.signature_valid ? (
                        <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                      ) : (
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                      )}
                      <span>
                        Ed25519 signature:{' '}
                        {proofCheck.signature_valid
                          ? 'signed by this deployment'
                          : proofCheck.signature_error || 'does not match the public key'}
                      </span>
                    </div>
                  </>
                )}

                {proofCheck.disclosure && (
                  <div className="p-2.5 border-2 border-ink bg-canvas font-mono space-y-1">
                    <p className="font-bold text-ink">What this does and does not establish</p>
                    {proofCheck.disclosure.does_not_prove.map((line) => (
                      <p key={line} className="text-ink-soft">- {line}</p>
                    ))}
                    {proofCheck.disclosure.signature_uses_published_demo_key && (
                      <p className="text-crimson-700 font-bold">
                        - The signature was made with the keypair published in
                        this repository. It identifies the software, not a person
                        or an office.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <a
                href={scannableProofUrl(selectedProof)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 text-center px-3 py-2.5 bg-canvas text-ink border-2 border-ink text-xs font-bold hover:bg-accent transition"
              >
                Open verification page
              </a>
              <button
                onClick={() => setSelectedProof(null)}
                className="flex-1 py-2.5 bg-ink text-white rounded-none text-xs font-bold hover:bg-ink transition"
              >
                Done
              </button>
            </div>
          </Card>
        </div>
      )}

      {/* Smart Contract Simulator Modal */}
      {smartContractModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
          <Card className="max-w-xl w-full p-6 bg-white rounded-none shadow-brutal-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <Cpu className="w-5 h-5 text-accent-strong" />
                <h3 className="font-bold text-ink text-base">Autonomous Cadastral Smart Contracts</h3>
              </div>
              <button onClick={() => setSmartContractModal(false)} className="text-ink-soft hover:text-ink">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex gap-2">
              {[
                { id: 'FSI_GUARD', name: 'FSI Guard Contract' },
                { id: 'THREE_PARTY_CONSENSUS', name: '3-Party Multi-Sig' },
                { id: 'PUBLIC_NOTICE_ESCROW', name: '30-Day Notice Escrow' },
              ].map(c => (
                <button
                  key={c.id}
                  onClick={() => handleRunSmartContract(c.id)}
                  className="flex-1 py-2 px-3 text-xs font-bold rounded-none border-2 border-ink hover:border-ink hover:bg-accent-faint transition"
                >
                  {c.name}
                </button>
              ))}
            </div>

            {contractResult && (
              <div className="p-4 bg-slate-900 text-emerald-400 rounded-none font-mono text-xs overflow-x-auto space-y-2">
                <div className="text-ink-soft text-[10px] uppercase font-bold tracking-widest">
                  Contract Execution Trace:
                </div>
                <pre className="whitespace-pre-wrap">{JSON.stringify(contractResult, null, 2)}</pre>
              </div>
            )}

            <button
              onClick={() => setSmartContractModal(false)}
              className="w-full py-2.5 bg-ink text-white rounded-none text-xs font-bold hover:bg-ink/90 transition"
            >
              Close Console
            </button>
          </Card>
        </div>
      )}
    </div>
  );
};