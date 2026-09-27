"""The identifier resolver that selection and deep links share.

A canonical 3D ID is ``{ulpin}/{building}-{level}-{unit}``, and its ``/`` is a
path separator, so ``/parcels/{ulpin}`` could not address one: the request
matched no route and came back as a bare ``{"detail": "Not Found"}``. The UI
mints exactly that form (``PropertyDetail`` builds ``property_id`` as
``{ulpin}/{code}``), so the product could produce an identifier it was unable to
resolve back. These tests pin the resolver's contract, including the part that
matters most: a well-formed identifier with no ingested record resolves to
nothing, and says so.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SyncSessionLocal
from app.main import app
from app.models.cadastre import Parcel
from app.models.jurisdiction import Jurisdiction

client = TestClient(app)

_RESOLVE = "/api/v1/ids/resolve"
_TEST_ULPIN = "X-RSLV0000001"

_SQUARE = {"type": "Polygon", "coordinates": [[[72.83, 19.05], [72.831, 19.05], [72.831, 19.051], [72.83, 19.05]]]}


def _seed_parcel(ulpin: str) -> None:
    """Write one parcel the way the ingest path does, via the sync session.

    The app serves requests on anyio's event loop, and its async engine holds
    connections bound to the loop that opened them. Seeding through
    ``asyncio.run`` opens a *second* loop, and the resulting pool reuse made this
    fixture order-dependent - the same assertion passed standalone and failed in
    the file. A sync session commits through the same database without taking
    ownership of any loop, so the app sees the row deterministically.
    """
    with SyncSessionLocal() as db:
        existing = db.execute(select(Parcel).where(Parcel.ulpin == ulpin)).scalar_one_or_none()
        if existing is not None:
            return
        juris = db.execute(select(Jurisdiction).limit(1)).scalar_one_or_none()
        if juris is None:
            juris = Jurisdiction(code="MH-THN-RSLV", name="Resolver fixture")
            db.add(juris)
            db.flush()
        db.add(
            Parcel(
                ulpin=ulpin,
                survey_number=f"RSLV-{ulpin}",
                jurisdiction_id=juris.id,
                polygon_geojson=_SQUARE,
                # `document_area_m2` and `calculated_area_m2` are NOT NULL. The
                # ingest path computes them from the ring, so a fixture that
                # omits them satisfies the model as declared but not the table as
                # migrated - which is why this fixture passed alone and errored
                # only in a full-suite run, after another test had run
                # `ensure_schema` against a populated database.
                document_area_m2=1000.0,
                calculated_area_m2=1000.0,
                gis_area_m2=1000.0,
                status="SURVEYED",
                data_provenance="globalml",
            )
        )
        db.commit()


@pytest.fixture(scope="module", autouse=True)
def _parcel():
    _seed_parcel(_TEST_ULPIN)
    return _TEST_ULPIN


def _resolve(identifier: str):
    return client.get(_RESOLVE, params={"identifier": identifier})


def test_a_3d_id_resolves_its_parent_parcel_instead_of_matching_no_route(_parcel):
    """The whole point: the multi-segment form is addressable now.

    Only the parent parcel is ingested for a footprint-derived area, so the
    assertions are on the parent resolving and a route being offered - not on
    the unit existing, which would be a fabricated claim.
    """
    res = _resolve(f"{_parcel}/UB17-L05-501-W")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["parent_ulpin"] == _parcel
    assert body["parcel"]["ulpin"] == _parcel
    assert body["parcel"]["geometry_present"] is True
    # A route the UI can actually follow, rather than a bare identifier.
    assert body["route"].startswith(f"/app/properties/{_parcel}")
    # The name that was asked for survives into the message.
    assert body["unresolved"]["building_code"] == "UB17-L05-501-W"
    assert "no structure" in body["unresolved"]["reason"]


def test_an_unbuilt_3d_id_resolves_to_its_parent_rather_than_404ing(_parcel):
    """A link a human can follow should not dead-end.

    The parcel is real, so the resolver gives the parcel route and reports the
    structure as unresolved. 404-ing a valid parent because the unit was never
    ingested would hide a record that does exist.
    """
    res = _resolve(f"{_parcel}/ZZ99-ZZ-999-ZZ")

    assert res.status_code == 200
    body = res.json()
    assert body["exists"] is False
    assert body["parcel"]["ulpin"] == _parcel
    assert body["route"].startswith(f"/app/properties/{_parcel}")
    assert body["structure"] is None


def test_a_bare_ulpin_that_exists_reports_no_structure_and_no_unit(_parcel):
    res = _resolve(_parcel)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["exists"] is True
    assert body["structure"] is None
    assert body["level"] is None
    assert body["unit"] is None
    # Nothing was claimed about a unit that was never named.
    assert body["unit_exists"] is None
    assert body["unresolved"] is None
    assert body["parsed_components"] is None


def test_a_missing_record_reports_validity_separately_from_existence():
    """A correct checksum is a claim about syntax, not about existence.

    Uses ``12345678909999``, a plausible parcel ULPIN with no record behind it.
    It used to use ``12345678901234`` on the grounds that the demo parcel grid
    was purged. That stopped being true when ``seed_demo`` was fixed to actually
    persist the hero parcel, and the identifier then resolved 200. The point of
    the test is the separation of syntax from existence, so it now names an
    identifier that is genuinely absent rather than relying on a gap in the seed.
    """
    absent_ulpin = "12345678909999"
    res = _resolve(absent_ulpin)

    assert res.status_code == 404
    detail = res.json()["detail"]
    assert detail["parent_ulpin"] == absent_ulpin
    assert detail["error"] == "no dataset ingested for this identifier"
    assert detail["not_available"], "a dead end must say what is missing"
    # A bare parcel ID has no syntax validator here, so no claim is made about
    # it in either direction.
    assert detail["identifier_valid"] is None


def test_an_unknown_identifier_explains_where_real_geometry_does_come_from():
    res = _resolve("Y0B6YWPJVLTYGR")

    assert res.status_code == 404
    detail = res.json()["detail"]
    assert detail["identifier_valid"] is None
    assert "ingest-area" in detail["explanation"] or "opendata/area" in detail["explanation"]
    assert len(detail["not_available"]) >= 3
    # The three not-available items are the fabricated-data red lines.
    joined = " ".join(detail["not_available"]).lower()
    assert "land-record" in joined
    assert "compliance" in joined or "fsi" in joined
