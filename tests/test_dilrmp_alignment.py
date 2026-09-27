"""The DILRMP panel must not imply participation, certification or endorsement.

The programme is real and the subject matter is relevant, so a panel is
legitimate. The failure mode is subtler than fabrication: listing capabilities
under a government programme's heading is read as that programme having assessed
them, regardless of any disclaimer printed underneath. So the assertions here
are about implication, not just about explicit claims.

The two things worth pinning are that the accreditation fields cannot acquire a
value, and that no unverified programme number can appear without a source and a
retrieval date attached to it.
"""
import pytest


@pytest.fixture()
def align(anon_client):
    res = anon_client.get("/api/v1/dilrmp/alignment")
    assert res.status_code == 200, res.text
    return res.json()


def test_alignment_is_labelled_as_self_assessment(align):
    assert align["alignment_kind"] == "policy_alignment_only"
    assert "not a claim of participation" in align["disclaimer"].lower()


def test_no_certification_or_participation_is_claimed(align):
    """The fields exist so a consumer checking them sees nothing held."""
    not_held = align["not_held"]
    for field in ("participant", "certified", "accredited", "official_status"):
        assert not_held[field] is None, f"{field} must not be claimed"


def test_component_mapping_is_not_faked(align):
    """Unverified beats reconstructed: no component list is published."""
    mapping = align["component_mapping"]
    assert mapping["verified"] is False
    assert mapping["reason"].strip()


def test_verified_programme_numbers_carry_a_source(align):
    prog = align["programme"]
    assert prog["source_url"].startswith("https://www.pib.gov.in/")
    assert prog["verified_on"]
    assert prog["verification_method"].strip()
    # Stating how the fact was read is what makes it re-checkable.
    assert "search" in prog["verification_method"].lower()


def test_period_and_outlay_are_specific_not_vague(align):
    prog = align["programme"]
    assert prog["period"] == "2026-2031"
    assert prog["outlay_inr_crore"] == 565.50


def test_every_row_states_a_limitation(align):
    """A row with no limitation reads as complete, which none of these are."""
    for row in align["rows"]:
        assert row["state"] in {
            "implemented",
            "partial",
            "not_implemented",
            "out_of_scope",
        }, row
        assert row["limitation"].strip(), f"{row['capability']} has no limitation"
        assert row["evidence"].strip()


def test_implemented_is_defined_as_code_not_compliance(align):
    """'implemented' appears in the rows and must not read as 'compliant'."""
    assert "does not mean a statutory requirement is satisfied" in align["summary"][
        "implemented_means"
    ]


def test_legal_capabilities_are_not_implemented(align):
    """Title and official issuance cannot be 'implemented' in a prototype."""
    forbidden = ("title", "ownership", "official ulpin issuance")
    for row in align["rows"]:
        if any(f in row["capability"].lower() for f in forbidden):
            assert row["state"] == "not_implemented", row


def test_out_of_scope_is_distinct_from_unfinished(align):
    """Beneficiary linkage is deliberately not attempted, not merely late."""
    row = next(
        r for r in align["rows"] if "Aadhaar" in r["capability"] or "Bank" in r["capability"]
    )
    assert row["state"] == "out_of_scope"
    assert "deliberately" in row["limitation"]


def test_alignment_does_not_contradict_source_status(align, anon_client):
    """The two panels describe one system, so they must not disagree.

    Rows name a capability the status endpoint also reports on. Where a row's
    subject is one of those capabilities, its state has to be consistent with
    that endpoint: claiming to implement something the source panel calls
    unavailable is the specific contradiction a reviewer would catch.
    """
    status = anon_client.get("/api/v1/datasources/status").json()
    denied = {c["key"] for c in status["capabilities"] if not c["available"]}

    # Capability key that each row's subject is about, where the row names one.
    subject = {
        "official ulpin issuance": None,
        "cadastral boundary source": "cadastral_parcel_boundaries",
        "airborne lidar coverage": "point_cloud_lidar",
        "title and ownership": "property_title_ownership",
    }

    for row in align["rows"]:
        key = None
        for needle, candidate in subject.items():
            if needle in row["capability"].lower():
                key = candidate
                break
        if key is None or key not in denied:
            continue
        # Denied by the source panel, so it cannot be implemented or partial.
        assert row["state"] == "not_implemented", (
            f"{row['capability']} is {row['state']} but /datasources/status "
            f"reports {key} unavailable"
        )