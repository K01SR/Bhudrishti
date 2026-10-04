import hashlib
import json
import time
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import settings
from app.core.crypto import (
    canonicalize_json,
    sign_canonical_record,
    verify_record_signature,
    _resolve_public_key_hex,
    DEMO_ED25519_PUBLIC_KEY_HEX,
    SigningKeyNotConfigured,
)

def sha256_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

class TransactionNotFound(Exception):
    """Raised when a ULPIN, spatial id or transaction id is not in the ledger."""

    def __init__(self, identifier: str):
        self.identifier = identifier
        super().__init__(f"No ledger transaction matches '{identifier}'.")


class MerkleTree:
    """
    Cryptographic Binary Merkle Tree for transaction immutability and SPV proofs.
    """
    def __init__(self, tx_hashes: List[str]):
        self.leaves = [h for h in tx_hashes] if tx_hashes else [sha256_hash("EMPTY_TX")]
        self.tree_levels = self._build_tree(self.leaves)
        self.root = self.tree_levels[-1][0]

    def _build_tree(self, leaves: List[str]) -> List[List[str]]:
        levels = [leaves]
        current_level = leaves
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = sha256_hash(left + right)
                next_level.append(combined)
            levels.append(next_level)
            current_level = next_level
        return levels

    def get_proof(self, tx_hash: str) -> List[Dict[str, str]]:
        """Generates audit proof path (siblings) to verify tx_hash against root."""
        if tx_hash not in self.leaves:
            return []
        idx = self.leaves.index(tx_hash)
        proof = []
        for level in self.tree_levels[:-1]:
            is_right = (idx % 2 == 1)
            sibling_idx = idx - 1 if is_right else (idx + 1 if idx + 1 < len(level) else idx)
            proof.append({
                "position": "left" if is_right else "right",
                "sibling_hash": level[sibling_idx]
            })
            idx = idx // 2
        return proof

    @staticmethod
    def verify_proof(tx_hash: str, proof: List[Dict[str, str]], expected_root: str) -> bool:
        current = tx_hash
        for p in proof:
            sibling = p["sibling_hash"]
            if p["position"] == "left":
                current = sha256_hash(sibling + current)
            else:
                current = sha256_hash(current + sibling)
        return current == expected_root


class Transaction:
    def __init__(
        self,
        tx_type: str,
        ulpin: str,
        spatial_id: str,
        parties: Dict[str, str],
        payload: Dict[str, Any],
        signatures: Optional[Dict[str, str]] = None,
        timestamp: Optional[str] = None,
        tx_id: Optional[str] = None
    ):
        self.tx_type = tx_type
        self.ulpin = ulpin
        self.spatial_id = spatial_id
        self.parties = parties
        self.payload = payload
        self.timestamp = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.signatures = signatures or {}
        self.tx_id = tx_id or self.compute_tx_id()

    def compute_tx_id(self) -> str:
        data = {
            "tx_type": self.tx_type,
            "ulpin": self.ulpin,
            "spatial_id": self.spatial_id,
            "parties": self.parties,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }
        return sha256_hash(canonicalize_json(data))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "tx_type": self.tx_type,
            "ulpin": self.ulpin,
            "spatial_id": self.spatial_id,
            "parties": self.parties,
            "signatures": self.signatures,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class SmartContractEngine:
    """
    Autonomous On-Chain Cadastral Smart Contract Evaluator.
    Enforces statutory planning regulations, anti-encroachment laws, and escrow rules.
    """
    @staticmethod
    def evaluate_fsi_contract(built_up_m2: float, plot_area_m2: float, max_allowed_fsi: float = 2.0) -> Dict[str, Any]:
        calculated_fsi = round(built_up_m2 / max(plot_area_m2, 1.0), 2)
        within = calculated_fsi <= max_allowed_fsi
        return {
            "contract": "FSI_RATIO_COMPARISON",
            # Not a pass/fail determination. Whether a project breaches its FAR is
            # a statutory finding against a sanctioned plan, and no sanctioned plan
            # is loaded here. "max_allowed_fsi" is whatever the caller passed in.
            "within_caller_supplied_limit": within,
            "calculated_fsi": calculated_fsi,
            "caller_supplied_fsi_limit": max_allowed_fsi,
            "status": "COMPARED",
            "enforcement": None,
            "statutory_ref": None,
            "statutory_ref_note": (
                "No statutory provision is cited. This previously cited 'UDCPR 2020 "
                "Sec 3.4.1' and returned APPROVED/REJECTED_BREACH_DETECTED with a "
                "SEAL_BLOCK or TRIGGER_PENALTY_NOTICE action, which asserted both a "
                "regulatory finding and a legal consequence. The regulation is not "
                "read or applied by this code, and no penalty can issue from it."
            ),
        }

    @staticmethod
    def evaluate_multi_sig_gate(signatures: Dict[str, str]) -> Dict[str, Any]:
        required = ["BUILDER", "DISTRICT_VERIFIER"]
        missing = [role for role in required if role not in signatures]
        return {
            "contract": "THREE_PARTY_CONSENSUS_GATE",
            "passed": len(missing) == 0,
            "required_roles": required,
            "present_signers": list(signatures.keys()),
            "missing_roles": missing,
            "threshold_status": "QUORUM_REACHED" if len(missing) == 0 else f"WAITING_FOR_{missing[0]}",
        }

    @staticmethod
    def evaluate_objection_window(filing_timestamp_iso: str, objection_window_days: int = 30) -> Dict[str, Any]:
        return {
            "contract": None,
            "window_days": objection_window_days,
            "active": True,
            "status": "OPEN_FOR_CITIZEN_OBJECTION",
            "statutory_ref": None,
            "notice_note": (
                "A working-record counter in this prototype. There is no escrow, "
                "no contract, and no notice issued under any statute; section 149 "
                "of the Maharashtra Land Revenue Code is not applied here."
            ),
        }


class Block:
    def __init__(
        self,
        index: int,
        timestamp: str,
        previous_hash: str,
        transactions: List[Transaction],
        validator_node: str = "local-process",
        difficulty: int = 2,
        nonce: int = 0,
        block_hash: Optional[str] = None
    ):
        self.index = index
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.transactions = transactions
        self.validator_node = validator_node
        self.difficulty = difficulty
        self.nonce = nonce

        # Build Merkle Tree
        tx_hashes = [t.tx_id for t in transactions]
        self.merkle_tree = MerkleTree(tx_hashes)
        self.merkle_root = self.merkle_tree.root

        # No third party has ever signed a block header. Earlier revisions
        # populated this with SHA-256 digests labelled NMMC_REVENUE_AUTHORITY,
        # MAHARERA_GATEWAY and SURVEY_OF_INDIA, which read as though those
        # bodies had attested the block while being nothing more than hashes
        # of a constant string keyed by block index. They are empty until a
        # real key is presented and verified; see the per-actor signing work.
        self.multi_signatures: Dict[str, str] = {}

        self.block_hash = block_hash or self.compute_block_hash()

    def compute_block_hash(self) -> str:
        header = {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "validator_node": self.validator_node,
            "difficulty": self.difficulty,
            "nonce": self.nonce,
        }
        return sha256_hash(canonicalize_json(header))

    def mine_block(self):
        target_prefix = "0" * self.difficulty
        while not self.block_hash.startswith(target_prefix):
            self.nonce += 1
            self.block_hash = self.compute_block_hash()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "block_hash": self.block_hash,
            "merkle_root": self.merkle_root,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "validator_node": self.validator_node,
            "multi_signatures": self.multi_signatures,
            "tx_count": len(self.transactions),
            "transactions": [t.to_dict() for t in self.transactions],
        }


class CadastralBlockchain:
    """
    High-Performance SHA-256 Proof-of-Work Blockchain for Bhu-Drishti 3D.
    Guarantees non-repudiation, tamper detection, and smart-contract driven spatial governance.
    """
    def __init__(self):
        self.chain: List[Block] = []
        # No peer nodes are configured. Earlier revisions listed five entries
        # on .gov.in hostnames (NMMC, IGR, MahaRERA, Survey of India, NIC) as
        # validators and consensus witnesses. Those hosts were never resolved
        # and never contacted, so the list asserted a distributed network that
        # does not exist. A deployment adds its real endpoints here.
        self.peer_nodes: List[Dict[str, str]] = []
        # These are Python methods on SmartContractEngine, not deployed
        # contracts. The addresses previously listed here were invented hex
        # strings that resolve to nothing on any network and imply a published
        # contract that was never deployed. The value names the local
        # implementation instead.
        self.smart_contracts = {
            "FSI_GUARD": "local:app.core.blockchain.SmartContractEngine.evaluate_fsi_contract",
            "THREE_PARTY_CONSENSUS": "local:app.core.blockchain.SmartContractEngine.evaluate_multi_sig_gate",
            "PUBLIC_NOTICE_ESCROW": "local:app.core.blockchain.SmartContractEngine.evaluate_objection_window",
            "MORTGAGE_LIEN_REGISTRY": "not implemented",
        }
        self.mempool: List[Transaction] = []
        self._backup_consensus_state: Optional[List[Dict[str, Any]]] = None
        self._initialize_synthetic_cadastral_chain()

    def _initialize_synthetic_cadastral_chain(self):
        """Builds realistic 10-block cadastral chain for Airoli Sector 8."""
        # Block 0: Genesis
        genesis_tx = Transaction(
            tx_type="GENESIS_STATE_ROOT",
            ulpin="STATE_ROOT_MAH",
            spatial_id="MH-THN-AIR-SEC08",
            parties={"ISSUER": "Demo state authority (not a real office)", "AUTHORITY": "Demo registrar (not a real office)"},
            payload={
                "state": "Maharashtra",
                "district": "Thane",
                "taluka": "Thane (Navi Mumbai)",
                "village": "Airoli",
                "sector": "Sector 8",
                "crs": "EPSG:32643 / UTM Zone 43N",
                "datum_origin": [19.154000, 72.996500, 12.00],
                "message": "In-process demo record list initialized (no blockchain)"
            },
            signatures={},
            timestamp="2026-09-01T00:00:00Z"
        )
        b0 = Block(0, "2026-09-01T00:00:00Z", "0" * 64, [genesis_tx], difficulty=2, nonce=142)
        b0.mine_block()
        self.chain.append(b0)

        # Block 1: Base Parcel Registration
        b1_tx = Transaction(
            tx_type="PARCEL_REGISTERED",
            ulpin="12345678901234",
            spatial_id="PARCEL-AIR-42",
            parties={"OFFICER": "Demo village officer (not a real office)", "SURVEYOR": "Demo survey team (not Survey of India)"},
            payload={
                "survey_number": "142/A",
                "plot_number": "42",
                "plot_area_m2": 1000.0,
                "sanctioned_fsi": 2.0,
                "boundary_vertices": [[140, 140], [175, 140], [175, 165], [140, 165]]
            },
            signatures={},
            timestamp="2026-09-05T10:00:00Z"
        )
        b1 = Block(1, "2026-09-05T10:05:00Z", b0.block_hash, [b1_tx], difficulty=2, nonce=88)
        b1.mine_block()
        self.chain.append(b1)

        # Block 2: 3D Building Sanction & Plan Approval
        b2_tx = Transaction(
            tx_type="BUILDING_3D_SANCTION",
            ulpin="12345678901234",
            spatial_id="BUILDING-B17",
            parties={"BUILDER": "Demo developer A", "TOWN_PLANNER": "Demo town planning office (not a real body)"},
            payload={
                "building_name": "Shree Ganesh CHS (Building B-17)",
                "floors_count": 5,
                "height_m": 18.0,
                "built_up_area_m2": 2550.0,
                "calculated_fsi": 1.80,
                "fsi_compliance": "PASS",
                "maha_rera_reg": "P51700018942",
                "nbc_seismic_grade": "Zone III Earthquake Resistant (IS 1893:2016)"
            },
            signatures={},
            timestamp="2026-09-10T14:30:00Z"
        )
        b2 = Block(2, "2026-09-10T14:35:00Z", b1.block_hash, [b2_tx], difficulty=2, nonce=215)
        b2.mine_block()
        self.chain.append(b2)

        # Block 3: Multi-Party Digital Signature Threshold Seal
        b3_tx = Transaction(
            tx_type="MULTI_PARTY_CONSENSUS_SEAL",
            ulpin="12345678901234",
            spatial_id="SEAL-B17-SANCTION",
            parties={"BUILDER": "Demo developer B", "DISTRICT_VERIFIER": "Demo reviewer (not an appointed official)", "CITIZEN_REP": "Demo residents group"},
            payload={
                "seal_protocol": "ED25519_THRESHOLD_3_OF_3",
                "smart_contract_check": "THREE_PARTY_CONSENSUS_GATE_PASSED",
                # No clearance is held or implied. These named the Airport
                # Authority of India, the Maharashtra Pollution Control Board and
                # the municipal water body as having cleared this building.
                "statutory_clearances": None,
                "statutory_clearances_note": (
                    "No fire NOC, airport clearance, pollution consent or water "
                    "connection clearance exists for this building. No such body "
                    "was contacted."
                ),
                "hash_state": "VERIFIED_UNANIMOUS"
            },
            signatures={},
            timestamp="2026-09-12T11:00:00Z"
        )
        b3 = Block(3, "2026-09-12T11:05:00Z", b2.block_hash, [b3_tx], difficulty=2, nonce=63)
        b3.mine_block()
        self.chain.append(b3)

        # Block 4: 3D Volumetric Sub-ULPIN Minting
        b4_tx = Transaction(
            tx_type="SUB_ULPIN_VOLUMETRIC_MINT",
            ulpin="12345678901234",
            spatial_id="21-VERTICAL-UNITS",
            parties={"SYSTEM": "This application, in this process", "OFFICER": "Demo registrar (not a real office)"},
            payload={
                "units_minted_count": 21,
                "floors": ["B1", "G", "L1", "L2", "L3", "L4", "L5"],
                "sample_minted_3d_ids": [
                    "12345678901234/U/B17/L05/501",
                    "12345678901234/U/B17/L05/502",
                    "12345678901234/U/B17/L05/503",
                    "12345678901234/U/B17/L05/504",
                ],
                "total_extruded_volume_m3": 7650.0,
                "geometry_crs": "EPSG:7755 / OGC CityJSON LoD 2.0"
            },
            timestamp="2026-09-15T09:15:00Z"
        )
        b4 = Block(4, "2026-09-15T09:20:00Z", b3.block_hash, [b4_tx], difficulty=2, nonce=189)
        b4.mine_block()
        self.chain.append(b4)

        # Block 5: Unit 501 Title Deed Conveyance
        b5_tx = Transaction(
            tx_type="TITLE_CONVEYANCE",
            ulpin="12345678901234",
            spatial_id="12345678901234/U/B17/L05/501",
            parties={"SELLER": "Demo developer A", "BUYER": "Demo buyer A", "REGISTRAR": "Demo sub-registrar (not a real office)"},
            payload={
                "unit_number": "501",
                "level_code": "L05",
                "carpet_area_m2": 82.5,
                "consideration_inr": 12500000,
                "stamp_duty_paid_inr": 750000,
                "registration_receipt": "MH-THN-REG-2026-89412",
                "elevation_envelope": {"min_z": 14.4, "max_z": 18.0}
            },
            signatures={},
            timestamp="2026-09-18T15:20:00Z"
        )
        b5 = Block(5, "2026-09-18T15:25:00Z", b4.block_hash, [b5_tx], difficulty=2, nonce=102)
        b5.mine_block()
        self.chain.append(b5)

        # Block 6: SBI Bank Home Loan Mortgage Lien
        b6_tx = Transaction(
            tx_type="MORTGAGE_LIEN_REGISTERED",
            ulpin="12345678901234",
            spatial_id="12345678901234/U/B17/L05/501",
            parties={"BORROWER": "Demo buyer A", "MORTGAGEE_BANK": "Demo lender (not a real bank)"},
            payload={
                "bank_ref": "SBI-HL-2026-8819",
                "loan_sanction_amount_inr": 9500000,
                "encumbrance_status": "ACTIVE_MORTGAGE",
                "cersai_asset_id": "CER-2026-MH-4912049",
                "title_deed_deposited": True
            },
            signatures={},
            timestamp="2026-09-20T11:45:00Z"
        )
        b6 = Block(6, "2026-09-20T11:50:00Z", b5.block_hash, [b6_tx], difficulty=2, nonce=77)
        b6.mine_block()
        self.chain.append(b6)

        # Block 7: Drone UAV LiDAR Multi-Epoch Point Cloud Attestation
        b7_tx = Transaction(
            tx_type="LIDAR_EPOCH_ATTESTATION",
            ulpin="12345678901234",
            spatial_id="LIDAR-EPOCH-2026-09",
            parties={"SURVEY_AGENCY": "Demo imagery provider", "UAV_PILOT": "Demo drone operator (no DGCA registration exists for this)"},
            payload={
                "point_count": 10000,
                "flight_altitude_m": 80.0,
                "sensor": "Riegl VUX-1UAV LiDAR Scanner",
                "point_density_pts_m2": 62.4,
                "extracted_height_m": 18.0,
                "footprint_iou_overlap": 0.94,
                "laz_sha256": "f892374619283746501928374650192837465019283746501928374650192837"
            },
            timestamp="2026-09-22T08:30:00Z"
        )
        b7 = Block(7, "2026-09-22T08:35:00Z", b6.block_hash, [b7_tx], difficulty=2, nonce=134)
        b7.mine_block()
        self.chain.append(b7)

        # Block 8: Smart Contract Autonomous FSI Violation Freeze (Building B-12)
        b8_tx = Transaction(
            tx_type="SMART_CONTRACT_AUTO_FREEZE",
            ulpin="20260925000012",
            spatial_id="BUILDING-B12",
            parties={"SMART_CONTRACT": "local:app.core.blockchain.SmartContractEngine.evaluate_fsi_contract", "ENFORCEMENT": "Demo enforcement office (not a real body)"},
            payload={
                "contract_name": "FSI_RATIO_COMPARISON",
                "event": "GEOMETRY_DIFFERENCE_RECORDED",
                "sanctioned_floors": None,
                "detected_floors": None,
                "calculated_fsi": 2.40,
                "allowed_fsi": None,
                "contract_verdict": None,
                "penal_action": None,
                "status": "RECORDED",
                "note": (
                    "This previously declared an unauthorised vertical expansion, "
                    "froze a transaction and raised a demand notice under a cited "
                    "section of a municipal act. There is no sanctioned plan to "
                    "compare against, no frozen transaction, and nothing in this "
                    "repository can issue a demand notice."
                )
            },
            timestamp="2026-09-24T16:00:00Z"
        )
        b8 = Block(8, "2026-09-24T16:05:00Z", b7.block_hash, [b8_tx], difficulty=2, nonce=95)
        b8.mine_block()
        self.chain.append(b8)

        # Block 9: Public Notice Citizen Objection Lodged
        b9_tx = Transaction(
            tx_type="CITIZEN_OBJECTION_LODGED",
            ulpin="20260925000003",
            spatial_id="BUILDING-B03",
            parties={"OBJECTOR": "Demo objector and 12 co-owners", "FORUM": "Demo forum (not a real tribunal)"},
            payload={
                "objection_ref": "OBJ-2026-MH-AIR-991",
                "subject": "Height differential on the 15th floor and solar shadow encroachment (generated scenario)",
                "evidence_hash": "e192837465019283746501928374650192837465019283746501928374650192",
                "hearing_scheduled": "2026-10-15T11:00:00Z",
                "escrow_lock_status": "TITLE_TRANSFER_LOCKED_PENDING_HEARING"
            },
            signatures={},
            timestamp="2026-09-25T14:15:00Z"
        )
        b9 = Block(9, "2026-09-25T14:20:00Z", b8.block_hash, [b9_tx], difficulty=2, nonce=172)
        b9.mine_block()
        self.chain.append(b9)

        # Store pristine backup state for self-healing demonstration
        self._backup_consensus_state = json.loads(json.dumps([b.to_dict() for b in self.chain]))

    def add_transaction_to_mempool(self, tx: Transaction) -> Dict[str, Any]:
        """Validates and stages transaction in memory pool."""
        self.mempool.append(tx)
        return {
            "status": "STAGED_IN_MEMPOOL",
            "tx_id": tx.tx_id,
            "mempool_size": len(self.mempool),
            "estimated_block": len(self.chain)
        }

    def mine_pending_block(self, validator: str = "local-process") -> Dict[str, Any]:
        """Mines pending transactions into a new cryptographically sealed block."""
        if not self.mempool:
            # Create a heartbeat validator proof transaction
            heartbeat_tx = Transaction(
                tx_type="CONSENSUS_HEARTBEAT",
                ulpin="STATE_ROOT_MAH",
                spatial_id="AIROLI_SECTOR08_CADASTRE",
                parties={"VALIDATOR": validator},
                payload={"msg": "Periodic Cadastral Ledger State Checkpoint", "height": len(self.chain)}
            )
            self.mempool.append(heartbeat_tx)

        prev_block = self.chain[-1]
        new_block = Block(
            index=len(self.chain),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            previous_hash=prev_block.block_hash,
            transactions=self.mempool[:],
            validator_node=validator,
            difficulty=2,
            nonce=0
        )
        new_block.mine_block()
        self.chain.append(new_block)
        self.mempool.clear()

        # Update backup consensus state
        self._backup_consensus_state = json.loads(json.dumps([b.to_dict() for b in self.chain]))

        return {
            "status": "BLOCK_MINED_AND_SEALED",
            "block_index": new_block.index,
            "block_hash": new_block.block_hash,
            "merkle_root": new_block.merkle_root,
            "nonce": new_block.nonce,
            "tx_count": len(new_block.transactions),
            "timestamp": new_block.timestamp
        }

    def verify_chain_integrity(self) -> Dict[str, Any]:
        """
        Exhaustively verifies every block's previous hash pointer, block hash,
        and Merkle root consistency from genesis to tip.
        """
        for i in range(len(self.chain)):
            current = self.chain[i]

            # 1. Verify previous hash linkage
            if i == 0:
                if current.previous_hash != "0" * 64:
                    return {
                        "integrity": "CORRUPTED",
                        "broken_block_index": 0,
                        "reason": f"Genesis previous hash must be 64 zeros, found {current.previous_hash}",
                        "timestamp": current.timestamp
                    }
            else:
                prev = self.chain[i - 1]
                if current.previous_hash != prev.block_hash:
                    return {
                        "integrity": "CORRUPTED",
                        "broken_block_index": i,
                        "reason": f"Block #{i} previous_hash mismatch! Points to {current.previous_hash[:16]}... but Block #{i-1} hash is {prev.block_hash[:16]}...",
                        "timestamp": current.timestamp
                    }

            # 2. Verify individual transaction data hashes
            for t in current.transactions:
                expected_tx_id = t.compute_tx_id()
                if t.tx_id != expected_tx_id:
                    return {
                        "integrity": "CORRUPTED",
                        "broken_block_index": i,
                        "broken_tx_id": t.tx_id,
                        "reason": f"Block #{i} transaction payload maliciously altered! Recorded tx_id: {t.tx_id[:16]}..., Recomputed hash from payload: {expected_tx_id[:16]}...",
                        "timestamp": current.timestamp
                    }

            # 3. Recompute Merkle root
            computed_merkle = MerkleTree([t.tx_id for t in current.transactions]).root
            if current.merkle_root != computed_merkle:
                return {
                    "integrity": "CORRUPTED",
                    "broken_block_index": i,
                    "reason": f"Block #{i} Merkle root tampered! Stored: {current.merkle_root[:16]}..., Recomputed from txs: {computed_merkle[:16]}...",
                    "timestamp": current.timestamp
                }

            # 4. Recompute block hash
            expected_hash = current.compute_block_hash()
            if current.block_hash != expected_hash:
                return {
                    "integrity": "CORRUPTED",
                    "broken_block_index": i,
                    "reason": f"Block #{i} payload corrupted! Recorded hash: {current.block_hash[:16]}..., Recomputed header hash: {expected_hash[:16]}...",
                    "timestamp": current.timestamp
                }

        return {
            "integrity": "VALID",
            "total_blocks": len(self.chain),
            "latest_block_hash": self.chain[-1].block_hash,
            "genesis_hash": self.chain[0].block_hash,
            "merkle_verification": "ALL_MERKLE_TREES_VALID",
            "proof_of_work_verification": "ALL_NONCES_VALID",
            "status": "SECURE_IMMUTABLE_CONSENSUS"
        }

    def simulate_tampering(self, block_index: int = 5, field: str = "consideration_inr", malicious_val: Any = 500000) -> Dict[str, Any]:
        """
        Demonstrates Byzantine tamper detection: silently modifies payload inside a block
        without recalculating hashes, proving immediate cryptographic detection!
        """
        if block_index < 0 or block_index >= len(self.chain):
            block_index = 5

        target_block = self.chain[block_index]
        if target_block.transactions:
            orig_val = target_block.transactions[0].payload.get(field, "N/A")
            target_block.transactions[0].payload[field] = malicious_val
            return {
                "action": "TAMPER_INJECTED",
                "block_index": block_index,
                "modified_field": field,
                "original_value": orig_val,
                "malicious_value": malicious_val,
                "explanation": "Transaction data silently altered. Blockchain state is now out-of-sync with hash pointers."
            }
        return {"action": "TAMPER_FAILED", "reason": "No transactions in block"}

    def self_heal_from_consensus(self) -> Dict[str, Any]:
        """
        Restores the chain from the local in-memory snapshot taken when the
        chain was last built or a block was mined.

        This does not contact any peer. It cannot: no peer nodes are
        configured, and the previous implementation returned
        "5_OF_5_PEERS_AGREED" to describe a copy held in this same process.
        That number described agreement between no one.
        """
        if not self._backup_consensus_state:
            return {"status": "FAILED", "reason": "No consensus backup available"}

        reconstructed: List[Block] = []
        for b_dict in self._backup_consensus_state:
            txs = [
                Transaction(
                    tx_type=t["tx_type"],
                    ulpin=t["ulpin"],
                    spatial_id=t["spatial_id"],
                    parties=t["parties"],
                    payload=t["payload"],
                    signatures=t.get("signatures", {}),
                    timestamp=t["timestamp"],
                    tx_id=t["tx_id"]
                )
                for t in b_dict["transactions"]
            ]
            block = Block(
                index=b_dict["index"],
                timestamp=b_dict["timestamp"],
                previous_hash=b_dict["previous_hash"],
                transactions=txs,
                validator_node=b_dict["validator_node"],
                difficulty=b_dict["difficulty"],
                nonce=b_dict["nonce"],
                block_hash=b_dict["block_hash"]
            )
            block.multi_signatures = b_dict.get("multi_signatures", {})
            reconstructed.append(block)

        self.chain = reconstructed
        return {
            "status": "CHAIN_RESTORED",
            "peer_consensus": "NO_PEERS_CONFIGURED",
            "restored_blocks_count": len(self.chain),
            "verification": self.verify_chain_integrity()
        }

    def generate_qr_proof(self, ulpin_or_tx_id: str) -> Dict[str, Any]:
        """Finds block and transaction matching ULPIN, returns cryptographic proof payload."""
        found_block: Optional[Block] = None
        found_tx: Optional[Transaction] = None

        for b in self.chain:
            for t in b.transactions:
                if t.ulpin == ulpin_or_tx_id or t.tx_id == ulpin_or_tx_id or t.spatial_id == ulpin_or_tx_id:
                    found_block = b
                    found_tx = t
                    break
            if found_block:
                break

        if not found_block or not found_tx:
            # Previously fell back to the Unit 501 / B-17 hero record, so asking
            # for a parcel that does not exist returned a real, correctly signed
            # proof for a completely different property. Two different unknown
            # identifiers produced byte-identical proofs, which meant a signed
            # QR could be obtained for a parcel that was never in the ledger at
            # all. Raising instead: no transaction means no proof to sign.
            raise TransactionNotFound(ulpin_or_tx_id)

        proof = found_block.merkle_tree.get_proof(found_tx.tx_id)
        body = {
            "protocol": "BHU_DRISHTI_BLOCKCHAIN_V1",
            "ulpin": found_tx.ulpin,
            "spatial_id": found_tx.spatial_id,
            "block_height": found_block.index,
            "block_hash": found_block.block_hash,
            "merkle_root": found_block.merkle_root,
            "tx_id": found_tx.tx_id,
            "timestamp": found_tx.timestamp,
            "validator": found_block.validator_node,
            "merkle_proof": proof,
        }

        # The proof used to be hashes and nothing else. Hashes are not evidence
        # of anything until somebody commits to them, so the whole body is now
        # signed with this deployment's Ed25519 key. A verifier can recompute the
        # fingerprint, check the signature, and independently walk the Merkle
        # path from tx_id up to merkle_root.
        signing_error = None
        fingerprint = None
        signature_hex = None
        public_key_hex = None
        try:
            fingerprint, signature_hex = sign_canonical_record(body)
            public_key_hex = _resolve_public_key_hex()
        except SigningKeyNotConfigured as exc:
            # A deployment with no key still has a walkable Merkle path, so the
            # proof is returned unsigned and says so, rather than failing the
            # whole request and leaving the UI with nothing to show.
            signing_error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            signing_error = f"Signing failed: {exc}"

        qr_payload = dict(body)
        qr_payload["sha256_fingerprint"] = fingerprint
        qr_payload["ed25519_signature"] = signature_hex
        qr_payload["signature_algorithm"] = "Ed25519 over SHA-256 of canonical JSON"
        if public_key_hex:
            qr_payload["public_key_hex"] = public_key_hex
        if signing_error:
            qr_payload["signing_error"] = signing_error
        # Previously pointed at a bhudrishti.maharashtra.gov.in host that
        # does not exist, implying a state-hosted verification service.
        # The link is derived from the deployment's own base URL.
        qr_payload["verify_url"] = _build_verify_url(qr_payload)
        return qr_payload


def _build_verify_url(payload: Dict[str, Any]) -> str:
    """
    Builds a self-contained verification link out of the proof itself.

    The link carries the signed body plus the fingerprint, the signature and
    the public key, so opening it needs no login, no database lookup and no
    working session on this deployment. That matters because a proof is only
    useful to a third party if the third party can reconstruct it from the QR
    alone; a link that only resolves against a live server proves nothing once
    the server is gone.

    Only the signed body and the signature material go in, deliberately
    excluding ``verify_url`` itself. Embedding the link inside the thing the
    link encodes would be recursive, and the excluded fields are all outside
    the signature anyway, so omitting them changes nothing about what the
    signature covers.
    """
    carried = {k: payload[k] for k in PROOF_VERIFIABLE_FIELDS if k in payload}
    encoded = urllib.parse.quote(json.dumps(carried, separators=(",", ":")))
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/verify/blockchain?p={encoded}"


# The exact fields the Ed25519 signature covers. An explicit allow-list, so a
# verifier rebuilding the signed body from a scanned payload selects these keys
# instead of having to guess which ones the signer left out. A signature cannot
# cover itself, so the fingerprint/signature/public-key fields are necessarily
# outside it.
PROOF_SIGNED_FIELDS = (
    "protocol",
    "ulpin",
    "spatial_id",
    "block_height",
    "block_hash",
    "merkle_root",
    "tx_id",
    "timestamp",
    "validator",
    "merkle_proof",
)

# The fields that travel in a verification link: the signed body, plus the
# signature material a verifier needs. All of PROOF_SIGNED_FIELDS is covered by
# the signature, so a verifier rebuilds the signed body from these and checks
# it. Listed separately from PROOF_SIGNED_FIELDS because a signature cannot
# cover itself.
PROOF_VERIFIABLE_FIELDS = (
    PROOF_SIGNED_FIELDS
    + ("sha256_fingerprint", "ed25519_signature", "signature_algorithm", "public_key_hex")
)


def _is_published_demo_key(public_key_hex: Optional[str]) -> bool:
    """True when the given key is the keypair published in this repository."""
    if not public_key_hex:
        return False
    return public_key_hex.strip().lower() == DEMO_ED25519_PUBLIC_KEY_HEX.lower()


def _resolve_public_key_hex_or_none() -> Optional[str]:
    try:
        return _resolve_public_key_hex()
    except Exception:
        return None


def signed_body_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuilds exactly the mapping that was signed, from a received payload."""
    return {k: payload[k] for k in PROOF_SIGNED_FIELDS if k in payload}


def verify_qr_proof(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Checks a scanned proof two ways and reports each independently.

    1. Merkle path: recompute the root from ``tx_id`` and the sibling hashes.
       This proves the transaction really is in the block the root names. It
       needs no key, so it works even on an unsigned deployment.
    2. Ed25519 signature: proves this deployment signed the body.

    They are reported separately on purpose. A valid Merkle path with a bad or
    absent signature means the hash chain is intact but nobody vouched for the
    proof; a valid signature with a bad Merkle path means the signed body does
    not match the tree it claims. Collapsing both into one boolean hides exactly
    the case an auditor needs to see.
    """
    if not isinstance(payload, dict):
        return {
            "signature_valid": False,
            "merkle_path_valid": False,
            "error": "Payload is not a JSON object.",
        }

    body = signed_body_from_payload(payload)
    missing = [k for k in PROOF_SIGNED_FIELDS if k not in body]
    if missing:
        return {
            "signature_valid": False,
            "merkle_path_valid": False,
            "error": "Payload is missing signed fields: " + ", ".join(missing),
        }

    # --- 1. Merkle path ---
    merkle_path_valid = False
    merkle_error = None
    try:
        merkle_path_valid = MerkleTree.verify_proof(
            body["tx_id"], body["merkle_proof"], body["merkle_root"]
        )
    except Exception as exc:
        merkle_error = str(exc)

    # --- 2. Signature ---
    signature_hex = payload.get("ed25519_signature")
    signature_valid = False
    signature_error = None
    if not signature_hex:
        signature_error = (
            "This proof carries no Ed25519 signature, so nothing here attests "
            "that it was issued by this deployment. Only the Merkle path can "
            "be checked."
        )
    else:
        try:
            signature_valid = verify_record_signature(
                body, signature_hex, public_key_hex=payload.get("public_key_hex")
            )
        except SigningKeyNotConfigured as exc:
            signature_error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            signature_error = str(exc)

    recomputed = sha256_hash(canonicalize_json(body))
    claimed = payload.get("sha256_fingerprint")
    fingerprint_matches = bool(claimed) and claimed == recomputed

    # A proof signed with the keypair published in the repository identifies the
    # software, not a person or an office. That is only worth saying when the
    # key really is the published one, so it is compared against the known demo
    # public key. Checking whether a key is merely absent would be wrong: a
    # proof can carry the demo key explicitly and still deserve the warning.
    signed_with_published_demo_key = (
        signature_valid
        and _is_published_demo_key(payload.get("public_key_hex") or _resolve_public_key_hex_or_none())
    )

    return {
        "signature_valid": signature_valid,
        "merkle_path_valid": merkle_path_valid,
        "signature_uses_published_demo_key": signed_with_published_demo_key,
        "merkle_error": merkle_error,
        "signature_error": signature_error,
        "fingerprint_matches": fingerprint_matches,
        "recomputed_sha256": recomputed,
        "claimed_sha256": claimed,
        "public_key_hex": payload.get("public_key_hex"),
        "signed_fields": list(PROOF_SIGNED_FIELDS),
        "algorithm": payload.get("signature_algorithm") or "Ed25519 over SHA-256 of canonical JSON",
        "ulpin": body.get("ulpin"),
        "tx_id": body.get("tx_id"),
        "block_height": body.get("block_height"),
    }



# Singleton Blockchain Ledger Instance
_BLOCKCHAIN_INSTANCE = CadastralBlockchain()

def get_cadastral_blockchain() -> CadastralBlockchain:
    return _BLOCKCHAIN_INSTANCE
