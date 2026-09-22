"""DILRMP programme facts and an honest alignment statement.

The programme is real, so a panel about it is legitimate. What is not legitimate
is presenting a prototype's feature list as though the programme had assessed
it. Two failures are designed against here.

**Fabricated programme facts.** Any number about DILRMP — outlay, period,
coverage, adoption counts — has to come from a citable release and carry its
retrieval date and the method used to read it. Facts that could not be verified
that way are recorded as ``None`` rather than filled from memory. This is why
there is no component-by-component breakdown below: the component list could not
be confirmed against the release text, so the mapping is declared unverified
instead of reconstructed.

**Implied accreditation.** Listing capabilities next to a government programme
reads as endorsement even with a disclaimer underneath, so the alignment rows
carry their own per-row verdict, the certificate fields are ``None``, and the
official status is stated as not held.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Verified programme facts. Each carries where it came from and how it was read,
# so a reviewer can re-check it rather than take it on trust.
_VERIFIED_RELEASE = {
    "programme": "Digital India Land Record Modernization Programme (DILRMP) 3.0",
    "publisher": "Press Information Bureau, Government of India",
    "source_url": (
        "https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2308966&lang=1&reg=3"
    ),
    "verified_on": "2026-10-04",
    "verification_method": (
        "Located via search of the official PIB domain and read from the search "
        "result summary. The PIB release page renders its body via JavaScript "
        "and was not parsed in full, so only the facts repeated below should be "
        "treated as confirmed; anything beyond them is unverified."
    ),
    "period": "2026-2031",
    "outlay_inr_crore": 565.50,
    "guidelines_launched": "10 September 2026",
}


# Fields that would imply the programme has assessed or accredited this system.
# They are declared, set to None, and asserted to stay None: a panel cannot
# quietly acquire a certification by omitting the field.
_NOT_HELD: Dict[str, Optional[str]] = {
    "participant": None,
    "certified": None,
    "accredited": None,
    "official_status": None,
    "component_mapping_verified": None,
}


@dataclass(frozen=True)
class AlignmentRow:
    """One platform capability against one programme-adjacent concern."""

    area: str
    capability: str
    #: implemented | partial | not_implemented | out_of_scope
    state: str
    evidence: str
    #: Why it cannot be more than it is. Empty only when genuinely complete.
    limitation: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "area": self.area,
            "capability": self.capability,
            "state": self.state,
            "evidence": self.evidence,
            "limitation": self.limitation,
        }


_ROWS: tuple = (
    AlignmentRow(
        area="Parcel identification",
        capability="Deterministic coordinate-derived 14-character parcel identifier",
        state="implemented",
        evidence="app/id_engine/national.py; verified by round-trip in tests",
        limitation=(
            "Derived in-repo. Not an official ULPIN, not issued by any authority, "
            "and no compliance with a published specification is claimed or tested."
        ),
    ),
    AlignmentRow(
        area="Parcel identification",
        capability="Official ULPIN issuance",
        state="not_implemented",
        evidence="No official API client exists in this codebase",
        limitation=(
            "Requires the DOLR/state ULPIN issuance API and a state rollout. "
            "Until then a derived identifier is not a substitute."
        ),
    ),
    AlignmentRow(
        area="Land record geometry",
        capability="Parcel boundary rendering and 3D extrusion",
        state="implemented",
        evidence="app/api/v1/ids.py extrude endpoints; /app/map",
        limitation=(
            "Operates on the generated demo dataset. No survey-grade or "
            "authoritative boundary source is connected."
        ),
    ),
    AlignmentRow(
        area="Land record geometry",
        capability="Cadastral boundary source",
        state="not_implemented",
        evidence="GET /api/v1/datasources/status reports cadastral_parcel_boundaries unavailable",
        limitation=(
            "Surveys are held by state revenue departments and are not available "
            "as an open dataset."
        ),
    ),
    AlignmentRow(
        area="3D / vertical mapping",
        capability="Vertical layer composition on a parent parcel identifier",
        state="implemented",
        evidence="app/id_engine/national.py compose_vertical_ulpin; ids router",
        limitation="Prototype additive encoding; carries no statutory meaning.",
    ),
    AlignmentRow(
        area="3D / vertical mapping",
        capability="Floor segmentation from structure geometry",
        state="partial",
        evidence="app/pipelines/floor_segmentation.py",
        limitation=(
            "Uniform storey bands from total height divided by an expected storey "
            "height. No clustering, and no slab or structure detection."
        ),
    ),
    AlignmentRow(
        area="Survey / spatial data",
        capability="Point cloud ingestion and inspection",
        state="partial",
        evidence="app/api/v1/ingest.py; /api/v1/lidar/inspect",
        limitation=(
            "Reads LAS/LAZ and serves it unmodified. The shipped capture is a "
            "deterministic synthetic demo file, not airborne survey data."
        ),
    ),
    AlignmentRow(
        area="Survey / spatial data",
        capability="Airborne LiDAR coverage for an area",
        state="not_implemented",
        evidence="datasources status reports point_cloud_lidar unavailable",
        limitation="No open Indian airborne LiDAR distribution exists.",
    ),
    AlignmentRow(
        area="Record of rights",
        capability="Title and ownership",
        state="not_implemented",
        evidence="datasources status reports property_title_ownership unavailable",
        limitation=(
            "Title is established by registration under state law and is not "
            "published as an open dataset. This cannot be added by engineering."
        ),
    ),
    AlignmentRow(
        area="Record of rights",
        capability="Mutation / change history ledger",
        state="partial",
        evidence="app change and audit routers; verification cases",
        limitation=(
            "An append-only ledger over demo records. Not a statutory register "
            "and not tamper-evident against a state record."
        ),
    ),
    AlignmentRow(
        area="Beneficiary integration",
        capability="Bank account / Aadhaar / PAN linkage",
        state="out_of_scope",
        evidence="No integration present",
        limitation=(
            "Out of scope without a statutory mandate. Not attempted deliberately, "
            "not merely unfinished."
        ),
    ),
)


def alignment() -> Dict[str, Any]:
    """Verified programme facts plus a per-capability alignment statement."""
    rows: List[Dict[str, Any]] = [r.as_dict() for r in _ROWS]
    by_state: Dict[str, int] = {}
    for row in rows:
        by_state[row["state"]] = by_state.get(row["state"], 0) + 1

    return {
        "programme": dict(_VERIFIED_RELEASE),
        "alignment_kind": "policy_alignment_only",
        "disclaimer": (
            "This is a self-assessment of how the prototype relates to the "
            "programme's subject matter. It is not a claim of participation, "
            "certification or accreditation, and no government body has "
            "reviewed or endorsed this system."
        ),
        "not_held": dict(_NOT_HELD),
        "component_mapping": {
            "verified": False,
            "reason": (
                "DILRMP's component list could not be confirmed against the "
                "release text, so no component-by-component mapping is published "
                "here. Rows below are organised by concern, not by programme "
                "component, and must not be read as one."
            ),
        },
        "rows": rows,
        "summary": {
            "counts": by_state,
            "total_rows": len(rows),
            # No row may claim completion of anything legal. Stated explicitly
            # because "implemented" appears in the rows above and is otherwise
            # easy to read as "the programme's requirement is met".
            "implemented_means": (
                "The code path exists and is tested in this repository. It does "
                "not mean a statutory requirement is satisfied."
            ),
        },
    }