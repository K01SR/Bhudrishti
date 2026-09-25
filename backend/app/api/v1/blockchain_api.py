from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel, Field
from app.core.blockchain import (
    get_cadastral_blockchain,
    verify_qr_proof,
    Transaction,
    TransactionNotFound,
    SmartContractEngine
)
from app.core.security import get_current_user_required, require_roles, TokenPayload, RoleEnum

router = APIRouter(prefix="/blockchain", tags=["Sovereign Cadastral Blockchain Ledger"])

AUTHED = require_roles([RoleEnum.STATE_ADMIN, RoleEnum.DISTRICT_VERIFIER, RoleEnum.TALUKA_VERIFIER, RoleEnum.BUILDER])
STATE_OPERATOR = require_roles([RoleEnum.STATE_ADMIN])

class CreateTransactionRequest(BaseModel):
    tx_type: str = Field(..., description="Transaction type, e.g. TITLE_CONVEYANCE, BUILDING_3D_SANCTION, MORTGAGE_LIEN")
    ulpin: str = Field(..., description="14-digit Base ULPIN")
    spatial_id: str = Field(..., description="Spatial unit or building identifier, e.g. 12345678901234/U/B17/L05/501")
    parties: Dict[str, str] = Field(..., description="Involved parties, e.g. {'SELLER': '...', 'BUYER': '...'}")
    payload: Dict[str, Any] = Field(..., description="Transaction details and spatial metadata")
    signatures: Optional[Dict[str, str]] = Field(default_factory=dict, description="Digital signatures")

class TamperSimulationRequest(BaseModel):
    block_index: int = Field(5, ge=1, description="Block index to tamper with")
    field: str = Field("consideration_inr", description="Field to alter")
    malicious_value: Any = Field(500000, description="Tampered value")

class SmartContractSimRequest(BaseModel):
    contract_type: str = Field(..., description="'FSI_GUARD', 'THREE_PARTY_CONSENSUS', or 'PUBLIC_NOTICE_ESCROW'")
    built_up_m2: Optional[float] = 2550.0
    plot_area_m2: Optional[float] = 1000.0
    max_allowed_fsi: Optional[float] = 2.0
    signatures: Optional[Dict[str, str]] = None
    filing_timestamp_iso: Optional[str] = None


@router.get("/blocks")
def list_blocks():
    """Returns chronological list of records in the in-process event list.

    There is no network and no chain. get_cadastral_blockchain() builds a plain
    Python list when the process starts and discards it on exit, so it previously
    reported a "Sovereign Cadastral Ledger" on a "MAHA-CADASTRAL-MAINNET" chain
    id with "Proof-of-Work" consensus, none of which exists anywhere.
    """
    bc = get_cadastral_blockchain()
    return {
        "network": "In-process list in this prototype (not a network)",
        "chain_id": None,
        "consensus": (
            "None. No mining, no distributed consensus, no multi-party "
            "signing, and no other participant."
        ),
        "total_blocks": len(bc.chain),
        "blocks": [b.to_dict() for b in bc.chain]
    }


@router.get("/blocks/{index}")
def get_block(index: int):
    """Returns detailed view of a specific block including transaction Merkle proofs."""
    bc = get_cadastral_blockchain()
    if index < 0 or index >= len(bc.chain):
        raise HTTPException(status_code=404, detail=f"Block #{index} not found on chain")
    block = bc.chain[index]
    b_dict = block.to_dict()

    # Include Merkle proof for each transaction in the block
    for tx in b_dict["transactions"]:
        tx["merkle_proof"] = block.merkle_tree.get_proof(tx["tx_id"])

    return b_dict


@router.get("/verify")
def verify_blockchain_integrity():
    """
    Performs exhaustive cryptographic verification across all blocks, previous-hash linkages,
    Merkle roots, and transaction data hashes.
    """
    bc = get_cadastral_blockchain()
    return bc.verify_chain_integrity()


@router.get("/stats")
def get_blockchain_stats():
    """Returns real-time network statistics, active validator nodes, and deployed smart contracts."""
    bc = get_cadastral_blockchain()
    total_txs = sum(len(b.transactions) for b in bc.chain)
    return {
        "network": "Bhu-Drishti Cadastral Blockchain",
        # The genesis block hash of the chain actually loaded above. This was
        # previously a hardcoded hex constant that did not match any block in
        # the chain, so it read as a verified state commitment while agreeing
        # with nothing that could be recomputed.
        "state_root": bc.chain[0].block_hash if bc.chain else None,
        "total_blocks": len(bc.chain),
        "total_transactions": total_txs,
        "mempool_pending_txs": len(bc.mempool),
        "difficulty": 2,
        "latest_block_index": len(bc.chain) - 1,
        "latest_block_hash": bc.chain[-1].block_hash,
        "genesis_hash": bc.chain[0].block_hash,
        "peer_nodes": bc.peer_nodes,
        "smart_contracts": bc.smart_contracts,
        "chain_health": bc.verify_chain_integrity()["integrity"],
    }


@router.post("/transactions/create")
def create_transaction(req: CreateTransactionRequest, _auth: TokenPayload = Depends(AUTHED)):
    """
    Submits a transaction to the mempool after validating smart contract rules.
    """
    bc = get_cadastral_blockchain()

    # Ratio check on a caller-supplied limit. This is a sanity gate on the
    # submitted numbers, not a sanction decision, so it is phrased as a
    # validation failure and cites no provision.
    if req.tx_type == "BUILDING_3D_SANCTION":
        built_up = float(req.payload.get("built_up_area_m2", 0))
        plot = float(req.payload.get("plot_area_m2", 1000))
        fsi_eval = SmartContractEngine.evaluate_fsi_contract(built_up, plot)
        if not fsi_eval["within_caller_supplied_limit"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Submitted ratio is out of range: FSI {fsi_eval['calculated_fsi']} "
                    f"against the limit {fsi_eval['caller_supplied_fsi_limit']} supplied in "
                    "the same request. This is an input check, not a determination of "
                    "compliance with any sanctioned plan."
                )
            )

    tx = Transaction(
        tx_type=req.tx_type,
        ulpin=req.ulpin,
        spatial_id=req.spatial_id,
        parties=req.parties,
        payload=req.payload,
        signatures=req.signatures,
    )
    result = bc.add_transaction_to_mempool(tx)
    return result


@router.post("/blocks/mine")
def mine_block(validator: str = Query("local-process", description="Label for the in-process block builder; there is no network node"), _auth: TokenPayload = Depends(STATE_OPERATOR)):
    """
    Mines all pending mempool transactions into a new cryptographically sealed block.
    """
    bc = get_cadastral_blockchain()
    result = bc.mine_pending_block(validator=validator)
    return result


@router.post("/tamper-simulate")
def simulate_tampering(req: TamperSimulationRequest, _auth: TokenPayload = Depends(STATE_OPERATOR)):
    """
    Simulates a malicious attack or silent database modification.
    Demonstrates that the blockchain cryptographic verifier instantly detects the anomaly!
    """
    bc = get_cadastral_blockchain()
    res = bc.simulate_tampering(block_index=req.block_index, field=req.field, malicious_val=req.malicious_value)
    return res


@router.post("/self-heal")
def self_heal_chain(_auth: TokenPayload = Depends(STATE_OPERATOR)):
    """
    Recovers from tampering by syncing with the peer consensus nodes and restoring authentic state.
    """
    bc = get_cadastral_blockchain()
    res = bc.self_heal_from_consensus()
    return res


@router.post("/qr-proof/verify")
def verify_qr_proof_endpoint(payload: Dict[str, Any] = Body(...)):
    """
    Verifies a scanned QR proof: Merkle path and Ed25519 signature, reported
    separately.

    Deliberately unauthenticated. The point of a proof you can put in a QR code
    is that a member of the public can check it without an account, and a
    verifier that needs a login is not a verifier. Nothing is read from the
    caller's session and nothing is written; the submitted bytes are checked
    against the hashes and the public key they carry.

    The response states what a pass does and does not mean, because "verified"
    is otherwise read as "the government confirmed this property".
    """
    result = verify_qr_proof(payload)
    result["disclosure"] = {
        "merkle_path_proves": (
            "That the transaction id in this proof really does hash up to the "
            "Merkle root the proof names, via the sibling hashes it carries. "
            "This needs no key."
        ),
        "signature_proves": (
            "That this deployment's Ed25519 key signed exactly these fields. "
            "A signature cannot cover itself, so the fingerprint, the signature "
            "and the public key sit outside the signed body."
        ),
        "does_not_prove": [
            "That the parcel, its boundaries, its floors or its Floor Space Index are correct.",
            "That any government office, registrar or authority issued or endorses this.",
            "That the deployment is authoritative. It is a prototype, not a registry.",
            "That the person who showed you the QR code is who they say they are.",
        ],
        "signature_uses_published_demo_key": bool(
            result.get("signature_uses_published_demo_key")
        ),
    }
    return result


@router.get("/qr-proof/{identifier}")
def get_qr_proof(identifier: str):
    """
    Generates cryptographic QR verification payload for instant mobile or
    third-party validation.

    Declared after POST /qr-proof/verify on purpose. FastAPI matches routes in
    declaration order, and "/qr-proof/{identifier}" would otherwise capture the
    literal segment "verify" and answer with a proof for a parcel called
    "verify" instead of running the check. Keeping the specific route first
    means the check is reachable, and an identifier genuinely named "verify"
    can still be looked up through /qr-proof/verify?identifier=... on the
    explicit route below.
    """
    bc = get_cadastral_blockchain()
    try:
        proof = bc.generate_qr_proof(identifier)
    except TransactionNotFound as exc:
        # 404, not a proof for some other parcel. The previous fallback made an
        # unknown identifier resolve to the B-17 hero record, so a QR could be
        # issued for a parcel that was never in the ledger.
        raise HTTPException(
            status_code=404,
            detail=(
                f"No ledger transaction matches '{identifier}'. "
                "No proof can be issued for an identifier that is not recorded."
            ),
        )
    return proof


@router.post("/smart-contracts/simulate")
def simulate_smart_contract(req: SmartContractSimRequest, _auth: TokenPayload = Depends(AUTHED)):
    """Simulates on-chain smart contract execution."""
    if req.contract_type == "FSI_GUARD":
        return SmartContractEngine.evaluate_fsi_contract(
            built_up_m2=req.built_up_m2 or 2550.0,
            plot_area_m2=req.plot_area_m2 or 1000.0,
            max_allowed_fsi=req.max_allowed_fsi or 2.0
        )
    elif req.contract_type == "THREE_PARTY_CONSENSUS":
        return SmartContractEngine.evaluate_multi_sig_gate(req.signatures or {"BUILDER": "sig1", "DISTRICT_VERIFIER": "sig2"})
    elif req.contract_type == "PUBLIC_NOTICE_ESCROW":
        return SmartContractEngine.evaluate_objection_window(req.filing_timestamp_iso or "2026-09-20T00:00:00Z")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown contract type: {req.contract_type}")
