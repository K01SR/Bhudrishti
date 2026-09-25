from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response
from app.core.crypto import verify_record_signature, sign_canonical_record
from app.core.crypto_disclosure import CRYPTO_DISCLOSURE
from app.core.config import settings
from app.core.demo_gate import demo_mode_dependency, load_demo_dataset

router = APIRouter(prefix="/qr", tags=["Public QR Lookup & Cryptographic Proofs"])

_DATASET = load_demo_dataset()


# Statement of what the signature below does and does not establish, returned
# with every response. It lives in app.core.crypto_disclosure because
# properties.py and verification.py used to ship their own claim instead: this
# response previously said "OFFICIAL_RECORD_VERIFIED" and named the Settlement
# Commissioner as the verifying authority.

@router.get("/verify/{token}")
def verify_public_token(token: str, _guard: None = Depends(demo_mode_dependency)):
    """
    Public lookup endpoint accessed via QR code. Does not require login.

    This is a database lookup. It performs no validation of any property claim
    and issues no certificate. The response deliberately does not report a
    verification result, because nothing is verified: there is no comparison
    against a state registry, no authority behind it, and the signing key is
    public.
    """
    hero_p = _DATASET["hero_parcel"]
    hero_s = _DATASET["hero_structure"]

    canonical_payload = {
        "parent_ulpin": hero_p["ulpin"],
        "structure_code": hero_s["building_code"],
        "total_units": len(_DATASET["units"]),
        "status": "PROTOTYPE_DEMO_RECORD",
    }

    fingerprint, signature = sign_canonical_record(canonical_payload)
    signature_self_validates = verify_record_signature(canonical_payload, signature)

    return {
        # Was "OFFICIAL_RECORD_VERIFIED" with "status": "APPROVED" and
        # "verifying_authority": "Settlement Commissioner & Director of Land
        # Records, Maharashtra". No such office verified anything, and naming a
        # real officer's post as the attesting authority is impersonation.
        "verification_result": "UNVERIFIED_PROTOTYPE_LOOKUP",
        "verified": False,
        "verification_note": (
            "This endpoint performed a database lookup. It did not verify this "
            "record against the Maharashtra cadastre or any other registry, and "
            "no government official or agency has reviewed or approved it. Do "
            "not rely on this for a property transaction."
        ),
        "token": token,
        "property_id": "12345678901234/B17-G-001-X",
        "parent_cadastral_ulpin": hero_p["ulpin"],
        "proposed_3d_id": "12345678901234/B17-G-001-X",
        "record_version": "V1.0",
        "status": "PROTOTYPE_DEMO_RECORD",
        "verifying_authority": None,
        "verifying_authority_note": (
            "None. This deployment is not connected to the DoLR, CERSAI, any "
            "municipal office, or any other authority."
        ),
        "cryptographic_proof": {
            "geometry_fingerprint_sha256": fingerprint,
            "ed25519_signature": signature,
            "signature_self_validates": signature_self_validates,
            "signature_status": "SELF_VALIDATED_ONLY",
            "tamper_evident_hash_chain": None,
            "hash_chain_note": (
                "No hash chain exists. This field previously returned a fixed "
                "string asserting a valid audit anchor, with no chain, no "
                "anchor and nothing behind it."
            ),
            "disclosure": CRYPTO_DISCLOSURE,
        },
        "spatial_summary": {
            "structure_name": hero_s["name"],
            "structure_name_note": (
                "A label from the demo dataset, not a registered building name."
            ),
            "building_height_m": hero_s["height_m"],
            "building_height_note": (
                "Demo value, not a surveyed or sanctioned height."
            ),
            "floors_count": hero_s["floors_count"],
            "floors_count_note": (
                "Demo value, not a sanctioned storey count."
            ),
            "basements_count": hero_s["basements_count"],
            "total_cadastral_units": len(_DATASET["units"]),
            "total_cadastral_units_note": (
                "Units present in the demo dataset. These are NOT registered "
                "cadastral strata units and have no registry entry."
            ),
            "parcel_area_m2": hero_p["document_area_m2"],
            "parcel_area_note": (
                "A figure from the source document, not a measured survey."
            ),
            "simplified_footprint": hero_s["footprint_geojson"],
        },
        "data_provenance": [
            "Demo dataset bundled with this prototype. Not a government source.",
        ],
        "data_provenance_note": (
            "This previously listed three authoritative-sounding sources: the "
            "national geodetic control network, the state land-records GIS "
            "cadastre, and a high-density airborne LiDAR survey flown at a "
            "stated point density. None of them were accessed and no such "
            "survey was obtained."
        ),
        "privacy_notice": (
            "Owner names, financial values and citizen records are not exposed "
            "here. No claim of DPDP Act 2023 compliance is made; that is a legal "
            "assessment this prototype has not undergone."
        ),
    }


@router.get("/certificate/{token}")
def get_verification_certificate(token: str, _guard: None = Depends(demo_mode_dependency)):
    """
    Returns the lookup result as JSON.

    This is not a certificate. It previously returned a Government of
    Maharashtra document title with a government-style serial number attached to
    a demo row.
    """
    verification_data = verify_public_token(token)
    return {
        "document_type": "Prototype lookup result (not a certificate)",
        "is_government_document": False,
        "title_note": (
            "This was previously titled a Government of Maharashtra cadastral "
            "certificate. No government body issues or endorses this output."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_reference": f"LOOKUP-{token.upper()}",
        "lookup": verification_data,
    }


# In-memory record of lookup calls. This is an application log, not an audit
# trail: it lives in process memory, is lost on restart, is not append-only, and
# is not signed. The seeded entries below are illustrative strings, not records
# of real scans by real devices.
_VERIFICATION_LEDGER: list = []
_LEDGER_COUNTER = 0

_LOOKUP_RESULT = "UNVERIFIED_PROTOTYPE_LOOKUP"


@router.get("/ledger/{token}")
def get_verification_ledger(token: str, _guard: None = Depends(demo_mode_dependency)):
    """
    In-memory log of lookup calls made against this token.
    Not an audit trail and not evidence of anything.
    """
    global _LEDGER_COUNTER
    _LEDGER_COUNTER += 1
    _VERIFICATION_LEDGER.append({
        "entry": f"LOG-{_LEDGER_COUNTER:04d}",
        "looked_up_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "result": _LOOKUP_RESULT,
    })
    return {
        "token": token,
        "parcel_ulpin": "12345678901234",
        "record_version": "V1.0",
        "status": "PROTOTYPE_DEMO_RECORD",
        "ledger_status": "IN_MEMORY_APPLICATION_LOG",
        "ledger_note": (
            "This is a process-local log of lookups against this prototype. It "
            "is not an audit trail, is lost on restart, cannot be relied on, and "
            "the previously seeded stamp entries carrying device and IP-hash "
            "columns were illustrative strings presented as real scan records."
        ),
        "total_lookups_this_process": len(_VERIFICATION_LEDGER),
        "entries": _VERIFICATION_LEDGER[-18:],
        "privacy_notice": (
            "No IP address or device identifier is recorded or retained by this "
            "endpoint."
        ),
    }
