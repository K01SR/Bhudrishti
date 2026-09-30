"""The source-status surface must not overstate what any source can answer.

A status endpoint is where an overclaim becomes durable. It is read once by the
frontend and then trusted, so a wrong ``authoritative`` flag here is worse than
no endpoint at all: it is a claim the product makes about itself, in the one
place a reviewer would look to check it.

These tests therefore pin the negative facts, not the positive ones. That no
source is authoritative for cadastre, title or ownership is the assertion worth
making; that footprints are available is incidental and depends on which
providers happen to be configured in the test environment.
"""
import pytest

CAPS = {
    "cadastral_parcel_boundaries",
    "property_title_ownership",
    "building_approvals",
    "zoning_regulations",
    "enforcement_violations",
    "point_cloud_lidar",
}

# Capabilities a source may never claim authority over, whatever its credentials
# or its .gov.in domain. A government portal hosting a contributed dataset does
# not make that dataset authoritative for property records.
NEVER_AUTHORITATIVE = CAPS


@pytest.fixture()
def status(anon_client):
    res = anon_client.get("/api/v1/datasources/status")
    assert res.status_code == 200, res.text
    return res.json()


def test_endpoint_is_public(status):
    # No auth required: a capability gap should be visible before login, and the
    # payload holds no secret values (asserted below).
    assert "sources" in status and "capabilities" in status


def test_no_authoritative_cadastral_source(status):
    """The single most load-bearing claim: nothing cadastre is authoritative."""
    assert status["summary"]["authoritative_cadastral_source"] is None
    assert "cadastral" in status["summary"]["authoritative_cadastral_note"].lower()


def test_no_source_claims_authority_over_legal_capabilities(status):
    for source in status["sources"]:
        for capability in source["authoritative_for"]:
            assert capability not in NEVER_AUTHORITATIVE, (
                f"{source['id']} claims authority for {capability}"
            )


def test_no_capability_marked_authoritative_when_unavailable(status):
    for cap in status["capabilities"]:
        if not cap["available"]:
            assert cap["authoritative"] is False
            assert cap["source_id"] is None


def test_unavailable_capabilities_carry_a_reason(status):
    """A bare `false` is indistinguishable from a bug; say why."""
    for cap in status["capabilities"]:
        if not cap["available"]:
            assert cap["basis"].strip(), f"{cap['key']} unavailable with no basis"


def test_data_gov_in_is_a_catalogue_not_an_authority(status):
    ogd = next(s for s in status["sources"] if s["id"] == "data.gov.in")
    assert ogd["authoritative_for"] == []
    assert ogd["configured"] is False
    assert any("resource id" in c for c in ogd["cannot_provide"])


def test_status_never_echoes_credential_values(anon_client, monkeypatch):
    """A GET must name missing variables, never print their values."""
    monkeypatch.setenv("OGD_API_KEY", "super-secret-key-value")
    monkeypatch.setenv("OGD_RESOURCE_ID", "")
    body = anon_client.get("/api/v1/datasources/status").text
    assert "super-secret-key-value" not in body

    ogd = next(
        s
        for s in anon_client.get("/api/v1/datasources/status").json()["sources"]
        if s["id"] == "data.gov.in"
    )
    # The key is present now, so only the resource id is named as missing.
    assert ogd["missing_configuration"] == ["OGD_RESOURCE_ID"]


def test_footprints_available_without_claiming_cadastre(status):
    """The tempting failure mode: footprints yes, therefore cadastre yes."""
    footprints = next(
        c for c in status["capabilities"] if c["key"] == "building_footprints"
    )
    if footprints["available"]:
        assert footprints["key"] != "cadastral_parcel_boundaries"
        assert footprints["authoritative"] is False


def test_height_is_not_claimed(status):
    """GlobalML is 2D roof outlines; a height here would be invented."""
    height = next(c for c in status["capabilities"] if c["key"] == "building_height")
    assert height["available"] is False


def test_lgd_supplies_admin_boundaries_not_parcels(status):
    """The real government source, described at the limit of what it is."""
    lgd_cap = next(
        c for c in status["capabilities"] if c["key"] == "village_admin_boundaries"
    )
    if lgd_cap["available"]:
        assert lgd_cap["authoritative"] is True
    lgd = next(s for s in status["sources"] if s["id"] == "lgd")
    assert any("parcel" in c for c in lgd["cannot_provide"])