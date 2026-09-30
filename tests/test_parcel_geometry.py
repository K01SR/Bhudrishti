"""Parcel geometry is written in the frame it is actually in.

`parcels.geom` is `geometry(POLYGON, 32643)` -- projected metres in UTM zone
43N. Two write paths filled it with the wrong frame, and the database is holding
the result:

* 37 non-null rows, of which 36 have `ST_Area = 0` and all 37 are invalid.
* Every one of them sits within 3 m of easting 298072.8 / northing 2113519.05,
  which is the Airoli origin (298000, 2113500) plus a latitude and a longitude.
* Row `X-OSM-0BBA7639` carries `geom` X = 298073.0015 while its own
  `polygon_geojson` starts at 73.0012518, 19.05 -- the real UTM easting for that
  position is 289661.08. The two halves of one row disagree by ~8.8 km.

So these tests pin the conversion that was missing, and pin the refusal to guess
when the input is not degrees. Everything here runs without a database: a fake
session records what each write path assigns, which is the whole assertion, and
answers ST_Area by measuring the geometry it was actually handed.
"""
import asyncio
import ast
import math
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core import geometry  # noqa: E402
from app.core.cadastre_store import AIROLI_ORIGIN, polygon_wkt, shoelace_area_m2  # noqa: E402
from app.services.builder_records import _parcel_ring  # noqa: E402

# A real published footprint, from a row in the live database
# (X-OSM-4803898D, OpenStreetMap via Overpass). Degrees, [lon, lat].
OSM_RING = [
    (72.9964566, 19.0997482),
    (72.9966113, 19.1013159),
    (72.9980703, 19.1020432),
    (72.9971422, 19.1013613),
]
# pyproj (PROJ 9.x, EPSG:32643) for the four vertices above, in metres. Kept as
# literals so the test fails loudly if the projection ever stops being this one,
# rather than recomputing it with the same library and passing vacuously.
OSM_RING_UTM43N = [
    (289219.253, 2113070.669),
    (289237.520, 2113244.031),
    (289391.981, 2113322.788),
    (289293.448, 2113248.418),
]

# What the old code stored for that same ring: the Airoli origin plus the
# degrees, treated as metres. Kept as the formula, not as literals, so it cannot
# drift into a pair of numbers that happen to differ from the correct ones.
def _corrupt_ring(ring):
    return [
        (AIROLI_ORIGIN["easting"] + lon, AIROLI_ORIGIN["northing"] + lat)
        for lon, lat in ring
    ]


OSM_RING_CORRUPT_UTM43N = _corrupt_ring(OSM_RING)
OSM_RING_AREA_M2 = 6671.377

# What the builder studio draws (frontend DEFAULT_FOOTPRINT): local-frame metres.
BUILDER_RING_M = [[0.0, 0.0], [24.0, 0.0], [24.0, 12.0], [0.0, 12.0]]
BUILDER_ANCHORED = [
    (298000.0, 2113500.0),
    (298024.0, 2113500.0),
    (298024.0, 2113512.0),
    (298000.0, 2113512.0),
]


def _ewkt_ring(ewkt):
    """(x, y) pairs out of an `SRID=32643;POLYGON((...))` string."""
    body = ewkt.split("POLYGON", 1)[1].strip().strip("()")
    return [(float(c.split()[0]), float(c.split()[1])) for c in body.split(",")]


def _open_ring(ewkt):
    """Same, minus the repeated closing vertex."""
    return _ewkt_ring(ewkt)[:-1]


def _srid_of(ewkt):
    match = re.match(r"SRID=(\d+);", ewkt)
    assert match, f"EWKT carries no SRID: {ewkt!r}"
    return int(match.group(1))


def _area(ring):
    doubled = list(ring) + [ring[0]]
    return abs(
        sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(doubled, doubled[1:]))
    ) / 2.0


# --------------------------------------------------------------------------- #
# (a) a WGS84 ring converts to the right EPSG:32643 easting/northing
# --------------------------------------------------------------------------- #
def test_wgs84_ring_projects_to_the_expected_utm_zone_43n_coordinates():
    projected = geometry.geodetic_ring_to_utm43n(OSM_RING)

    assert len(projected) == len(OSM_RING)
    for (lon, lat), (easting, northing), (want_e, want_n) in zip(
        OSM_RING, projected, OSM_RING_UTM43N
    ):
        assert easting == pytest.approx(want_e, abs=0.01), (lon, lat)
        assert northing == pytest.approx(want_n, abs=0.01), (lon, lat)


def test_projected_ring_is_not_the_origin_plus_degrees():
    """The specific corruption in the 37 stored rows, ruled out explicitly."""
    projected = geometry.geodetic_ring_to_utm43n(OSM_RING)

    for (lon, lat), (easting, northing), (bad_e, bad_n) in zip(
        OSM_RING, projected, OSM_RING_CORRUPT_UTM43N
    ):
        assert (easting, northing) != pytest.approx((bad_e, bad_n), abs=0.01)
        # ... and the corrupt value really is origin + degrees, so this is not a
        # pair of arbitrary numbers being compared to each other.
        assert AIROLI_ORIGIN["easting"] + lon == pytest.approx(bad_e, abs=1e-9)
        assert AIROLI_ORIGIN["northing"] + lat == pytest.approx(bad_n, abs=1e-9)

    # The magnitude of the error the fix removes: about 8.8 km, due east.
    offset = math.hypot(
        projected[0][0] - OSM_RING_CORRUPT_UTM43N[0][0],
        projected[0][1] - OSM_RING_CORRUPT_UTM43N[0][1],
    )
    assert offset == pytest.approx(8800, abs=400)


def test_projection_round_trips_back_to_the_same_degrees():
    back = geometry.utm43n_ring_to_wgs84(geometry.geodetic_ring_to_utm43n(OSM_RING))
    for (lon, lat), (lon_back, lat_back) in zip(OSM_RING, back):
        assert lon_back == pytest.approx(lon, abs=1e-9)
        assert lat_back == pytest.approx(lat, abs=1e-9)


def test_projected_ring_measures_its_real_area_not_a_point():
    """A 32643 polygon must keep the footprint's area; zero is the stored failure."""
    ewkt = geometry.geodetic_polygon_ewkt(OSM_RING)
    assert ewkt is not None
    assert _srid_of(ewkt) == 32643

    area = _area(_open_ring(ewkt))
    assert area == pytest.approx(OSM_RING_AREA_M2, abs=1.0)  # ~6671 m2 OSM footprint
    assert area > 1.0


# --------------------------------------------------------------------------- #
# (b) local-frame metres are never stored as if they were a 32643 polygon
# --------------------------------------------------------------------------- #
def test_local_frame_metres_are_refused_as_geodetic_input():
    assert geometry.classify_frame(BUILDER_RING_M) == geometry.FRAME_LOCAL_METRES
    assert geometry.is_georeferenced(BUILDER_RING_M) is False
    assert geometry.geodetic_polygon_ewkt(BUILDER_RING_M) is None
    with pytest.raises(geometry.GeometryRefused):
        geometry.geodetic_ring_to_utm43n(BUILDER_RING_M)


def test_anchored_local_ring_is_exactly_origin_plus_metres():
    """Anchor to a declared origin -- never the origin plus degrees."""
    assert geometry.anchor_local_ring(BUILDER_RING_M) == BUILDER_ANCHORED

    # The corrupt pattern for this same ring would swap the axes: 298000 + y and
    # 2113500 + x, landing at (298012, 2113524) rather than (298024, 2113512).
    corrupt = [
        (AIROLI_ORIGIN["easting"] + y, AIROLI_ORIGIN["northing"] + x)
        for x, y in BUILDER_RING_M
    ]
    assert corrupt != geometry.anchor_local_ring(BUILDER_RING_M)


def test_anchored_local_polygon_measures_the_drawn_area_in_m2():
    """Anchoring must not disturb the area maths: 24 x 12 m is 288 m2."""
    ewkt = geometry.anchored_polygon_ewkt(BUILDER_RING_M)
    assert _srid_of(ewkt) == 32643
    assert _open_ring(ewkt) == BUILDER_ANCHORED
    assert _area(_open_ring(ewkt)) == pytest.approx(288.0, abs=0.01)
    assert shoelace_area_m2(BUILDER_RING_M) == pytest.approx(288.0, abs=1e-9)


def test_polygon_wkt_dispatches_on_frame_instead_of_always_adding_the_origin():
    """`polygon_wkt` is what both live callers of the parcel write use.

    The OSM/GlobalML ingest passes a ring in degrees; the generated hero parcel
    passes local metres. Both used to produce the same 32643 polygon, and the
    degrees case came out ~8.8 km wrong.
    """
    from_degrees = _open_ring(polygon_wkt([list(p) for p in OSM_RING]))
    for want_e, want_n in OSM_RING_UTM43N:
        assert (want_e, want_n) == pytest.approx(
            min(from_degrees, key=lambda p: math.hypot(p[0] - want_e, p[1] - want_n)),
            abs=0.01,
        )

    from_metres = _open_ring(polygon_wkt(BUILDER_RING_M))
    assert from_metres == BUILDER_ANCHORED


def test_a_ring_that_is_not_a_polygon_is_refused_not_guessed():
    for bad in (
        [[0.0, 0.0], [1.0, 1.0]],                        # two vertices
        [[0.0, 0.0], ["a", 1.0], [2.0, 2.0]],            # not numbers
        [[0.0, 0.0], [float("nan"), 1.0], [2.0, 2.0]],  # not finite
    ):
        assert geometry.classify_frame(bad) == geometry.FRAME_UNKNOWN
        assert geometry.geodetic_polygon_ewkt(bad) is None
        with pytest.raises(geometry.GeometryRefused):
            geometry.polygon_ewkt(bad)


def test_anchor_record_states_that_the_position_is_assumed():
    record = geometry.anchor_record()
    assert record["geometry_frame"] == geometry.FRAME_LOCAL_METRES
    assert record["georeferenced"] is False
    assert record["anchor_origin"]["easting"] == 298000.0
    assert record["anchor_origin"]["northing"] == 2113500.0
    assert record["anchor_origin"]["srid"] == 32643
    assert "not a survey" in record["anchor_note"]


# --------------------------------------------------------------------------- #
# (c) _parcel_ring: (lat, lon) for a real WGS84 polygon, None for local metres
# --------------------------------------------------------------------------- #
class _StubParcel:
    """Just the attributes _parcel_ring reads."""

    def __init__(self, polygon_geojson=None, provenance_detail=None):
        self.polygon_geojson = polygon_geojson
        self.provenance_detail = provenance_detail


def _geojson(ring):
    closed = list(ring) + [list(ring[0])]
    return {"type": "Polygon", "coordinates": [[[x, y] for x, y in closed]]}


def test_parcel_ring_returns_lat_lon_for_a_real_wgs84_polygon():
    ring = _parcel_ring(_StubParcel(_geojson(OSM_RING)))
    assert ring is not None
    assert ring == [(lat, lon) for lon, lat in OSM_RING]
    assert all(6.0 <= lat <= 36.0 for lat, _ in ring)
    assert all(68.0 <= lon <= 98.0 for _, lon in ring)


def test_parcel_ring_returns_none_for_local_frame_metres():
    """Every pre-fix builder row stored bare metres in polygon_geojson."""
    assert _parcel_ring(_StubParcel(_geojson(BUILDER_RING_M))) is None
    # The pattern from the 37 stored rows, read as metres: also out of bounds.
    assert _parcel_ring(_StubParcel(_geojson(OSM_RING_CORRUPT_UTM43N))) is None


def test_parcel_ring_returns_none_for_nothing_at_all():
    assert _parcel_ring(_StubParcel(None)) is None
    assert _parcel_ring(_StubParcel({})) is None
    assert _parcel_ring(_StubParcel({"type": "Polygon", "coordinates": []})) is None
    assert _parcel_ring(_StubParcel(_geojson([[72.99, 19.09], [72.99, 19.10]]))) is None



# --------------------------------------------------------------------------- #
# The two write paths, driven against a fake session (no database needed)
# --------------------------------------------------------------------------- #
class _Result:
    def __init__(self, *, one=None, many=None, scalar_value=None):
        self._one = one
        self._many = many or []
        self._scalar = scalar_value

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return list(self._many)

    def scalar(self):
        return self._scalar


class _FakeSession:
    """Enough AsyncSession for the two write paths, and it keeps the rows.

    ST_Area is answered by measuring whatever EWKT the writer assigned, so a wrong
    coordinate cannot be masked by a hard-coded number.
    """

    def __init__(self):
        self.parcels = []
        self.queries = []
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover - only on a failed commit
        pass

    async def refresh(self, obj):
        return obj

    def add(self, obj):
        if type(obj).__name__ == "Parcel":
            if obj.id is None:
                obj.id = f"parcel-{len(self.parcels)}"
            self.parcels.append(obj)
        elif type(obj).__name__ == "AuditEvent":
            # Audit rows are kept so tests can assert on what was actually
            # chained. append_audit_event assigns event_number and both hashes
            # before add(), and refresh() returns the object unchanged, so a row
            # reaching here is already fully populated.
            if obj.id is None:
                obj.id = f"audit-{len(getattr(self, 'audit_events', []))}"
            self.audit_events = getattr(self, "audit_events", [])
            self.audit_events.append(obj)

    async def flush(self):
        return None

    async def execute(self, statement):
        sql = str(statement)
        self.queries.append(sql)
        lowered = sql.lower()
        if "jurisdictions" in lowered:
            return _Result(one="jur-airoli-sec08")
        if "st_area" in lowered:
            return _Result(scalar_value=self._measured_area())
        if "from parcels" in lowered:
            return _Result(one=None)
        if "from structures" in lowered:
            return _Result(one=None)
        if "from levels" in lowered:
            return _Result(many=[])
        raise AssertionError(f"unexpected statement: {sql}")  # pragma: no cover

    def _measured_area(self):
        for parcel in self.parcels:
            if parcel.geom is None:
                return None
            return _area(_open_ring(parcel.geom))
        return None  # pragma: no cover


# --------------------------------------------------------------------------- #
# The identifier the acceptance path mints from this geometry
# --------------------------------------------------------------------------- #
class _DeriveSession(_FakeSession):
    """Also answers the audit-event chain the acceptance path appends to."""

    def __init__(self, *, chain_writes=True):
        super().__init__()
        self.chain_writes = chain_writes

    async def execute(self, statement):
        if "audit_events" in str(statement).lower():
            if not self.chain_writes:
                raise RuntimeError("audit table is gone")
            return _Result(one=_StubEvent())
        return await super().execute(statement)


class _StubEvent:
    def __init__(self):
        self.event_number = 41
        self.current_hash = "a" * 64
        self.previous_hash = "b" * 64


def _derivation_of(db, parcel):
    from datetime import datetime, timezone

    from app.services.builder_records import _derive_record_on_acceptance

    return asyncio.run(
        _derive_record_on_acceptance(
            db,
            parcel=parcel,
            submission_id="SUB-TEST-0001",
            parcel_ulpin="202609250004",
            decision="ACCEPTED_FOR_RECORD",
            reason="fit for the working record",
            reviewer_id="district.admin",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
    )


def _parcel_with(ring, geom="present", provenance=None):
    """A parcel stand-in with just the attributes the derivation path reads."""
    return SimpleNamespace(
        polygon_geojson=_geojson(ring) if ring is not None else None,
        geom=object() if geom == "present" else None,
        provenance_detail=provenance,
    )


def test_a_georeferenced_parcel_mints_an_identifier_and_reports_the_authority():
    """The whole point of reprojecting: with real degrees in
    `polygon_geojson`, the acceptance path has something to derive from."""
    result = _derivation_of(_DeriveSession(), _parcel_with(OSM_RING))

    assert result["derived_ulpin_status"] == "PROTOTYPE_DERIVED"
    assert len(result["derived_ulpin"]) == 14
    assert result["identifier_authority"] == "NOT_A_REGISTRY_ALLOCATION"
    assert "no state registry was contacted" in result["derivation_note"].lower()
    # A surveyed position must not pick up the anchor caveat.
    assert "assumption rather than a survey" not in result["derivation_note"]


def test_an_anchored_builder_parcel_mints_an_identifier_that_says_it_is_anchored(monkeypatch):
    """End to end: the row the builder path writes, fed to the acceptance path.

    A builder footprint gets an identifier, but the response must carry the
    assumption. Silent-approximate-location is the failure mode here.
    """
    from app.core import cadastre_store
    from app.services.builder_records import persist_builder_structure

    monkeypatch.setattr(cadastre_store, "_schema_ready", True)
    db = _DeriveSession()
    asyncio.run(
        persist_builder_structure(
            db,
            ulpin="GEOM-TEST-0003",
            project_name="Anchor Probe",
            structure_code="B-TEST",
            structure_type="tower",
            floors_above_ground=2,
            floor_to_floor_height_m=3.0,
            total_height_m=6.0,
            footprint_ring=BUILDER_RING_M,
            address="Plot 1",
            locality="Airoli",
            ground_z=0.0,
        )
    )

    result = _derivation_of(db, db.parcels[0])

    assert result["derived_ulpin_status"] == "PROTOTYPE_DERIVED"
    assert result["identifier_authority"] == "NOT_A_REGISTRY_ALLOCATION"
    assert "assumption rather than a survey" in result["derivation_note"]
    assert "approximate location, not a measured one" in result["derivation_note"]


def test_local_frame_geometry_derives_nothing_rather_than_the_wrong_place():
    """The 37 pre-fix rows: geometry present, but not in degrees. Minting an
    identifier from them would name a parcel tens of kilometres away."""
    result = _derivation_of(_DeriveSession(), _parcel_with(BUILDER_RING_M))

    assert result["derived_ulpin"] is None
    assert result["derived_ulpin_status"] == "NOT_DERIVED"
    assert "No identifier was minted" in result["derivation_note"]


def test_no_geometry_at_all_is_reported_as_missing_geometry_not_a_bad_frame():
    """Two different problems, and the note has to keep them apart."""
    result = _derivation_of(_DeriveSession(), _parcel_with(None, geom=None))

    assert result["derived_ulpin_status"] == "NOT_DERIVED"
    assert "not available" in result["derivation_note"]


def test_a_rejection_derives_nothing_and_chains_no_audit_event():
    from datetime import datetime, timezone

    from app.services.builder_records import _derive_record_on_acceptance

    db = _DeriveSession()
    result = asyncio.run(
        _derive_record_on_acceptance(
            db,
            parcel=_parcel_with(OSM_RING),
            submission_id="SUB-TEST-0002",
            parcel_ulpin="202609250005",
            decision="REJECTED",
            reason="the massing exceeds the setback",
            reviewer_id="district.admin",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
    )

    assert result == {}
    assert not any("audit_events" in q.lower() for q in db.queries)


def test_the_audit_proof_reports_chaining_and_signs_the_record():
    db = _DeriveSession()
    result = _derivation_of(db, _parcel_with(OSM_RING))

    proof = result["blockchain_proof"]
    assert proof["chained"] is True
    # previous_hash comes from the newest event, not from genesis, so the chain
    # is a chain rather than a bag of unrelated hashes.
    assert proof["previous_hash"] == "a" * 64
    assert proof["table"] == "audit_events"
    assert proof["event_type"] == "SUBMISSION_ACCEPTED"
    assert proof["ed25519_signature"]
    assert proof["record_fingerprint"]
    assert "not a government seal" in proof["signature_note"]


def test_a_failed_audit_write_is_reported_as_unchained_with_a_reason():
    """`chained: true` on a row that was never written is the failure mode worth
    guarding: it would show a hash proving nothing."""
    db = _DeriveSession(chain_writes=False)
    result = _derivation_of(db, _parcel_with(OSM_RING))

    proof = result["blockchain_proof"]
    assert proof["chained"] is False
    assert proof["reason"], "an unchained proof must say why"
    assert not proof.get("hash")
    # The decision is still recorded, and the signature is still attempted.
    assert result["derived_ulpin_status"] == "PROTOTYPE_DERIVED"

def test_builder_write_anchors_local_metres_and_stores_real_geojson(monkeypatch):
    from app.core import cadastre_store
    from app.services.builder_records import persist_builder_structure

    monkeypatch.setattr(cadastre_store, "_schema_ready", True)
    db = _FakeSession()

    result = asyncio.run(
        persist_builder_structure(
            db,
            ulpin="GEOM-TEST-0001",
            project_name="Anchor Probe",
            structure_code="B-TEST",
            structure_type="tower",
            floors_above_ground=2,
            floor_to_floor_height_m=3.0,
            total_height_m=6.0,
            footprint_ring=BUILDER_RING_M,
            address="Plot 1",
            locality="Airoli",
            ground_z=0.0,
        )
    )
    assert result["persisted"] is True, result

    parcel = db.parcels[0]

    # `geom` is a real 32643 polygon at origin + metres, not origin + degrees.
    assert _srid_of(parcel.geom) == 32643
    assert _open_ring(parcel.geom) == BUILDER_ANCHORED

    # `polygon_geojson` is now genuine WGS84 degrees, which is what the column
    # name promises and what `_parcel_ring` reads back.
    written = _parcel_ring(parcel)
    assert written is not None, "the written polygon_geojson must read as degrees"
    for lat, lon in written:
        assert 6.0 < lat < 36.0
        assert 68.0 < lon < 98.0
    # 1e-7 deg ~ 1 cm, so the GeoJSON round trip is faithful to the drawing: the
    # ring's 24 m east edge and 12 m north edge both survive projection and the
    # inverse projection. A degree of longitude is shorter than a degree of
    # latitude by cos(latitude) at this latitude.
    metres_per_deg_lon = 111320.0 * math.cos(math.radians(written[0][0]))
    east_edge = (written[1][1] - written[0][1]) * metres_per_deg_lon
    north_edge = (written[2][0] - written[1][0]) * 111139.0
    assert east_edge == pytest.approx(24.0, abs=0.1)
    assert north_edge == pytest.approx(12.0, abs=0.1)

    # Areas: the drawing's own area, and PostGIS over the geometry as stored.
    assert parcel.calculated_area_m2 == pytest.approx(288.0, abs=1e-6)
    assert parcel.gis_area_m2 == pytest.approx(288.0, abs=0.01)
    assert parcel.gis_area_m2 != 0.0

    # The assumption is recorded on the row and in the response, not buried.
    assert parcel.provenance_detail["geometry_frame"] == geometry.FRAME_LOCAL_METRES
    assert parcel.provenance_detail["georeferenced"] is False
    assert result["parcel_geometry_basis"]["georeferenced"] is False
    assert result["parcel_geometry_basis"]["crs"] == "EPSG:32643"


def test_upsert_parcel_reprojects_geojson_instead_of_trusting_the_wkt(monkeypatch):
    """The OSM/GlobalML ingest bug, as a write path.

    `ingest_area` builds `polygon_wkt_2d` from the source ring and hands it over;
    that value is what used to land in `geom`. Now the polygon's own WGS84
    coordinates are reprojected instead, and the supplied WKT is not read.
    """
    from app.core import cadastre_store
    from app.core.cadastre_store import upsert_parcel

    monkeypatch.setattr(cadastre_store, "_schema_ready", True)
    db = _FakeSession()

    parcel = asyncio.run(
        upsert_parcel(
            db,
            ulpin="GEOM-TEST-0002",
            survey_number="OSM-353375941",
            jurisdiction_id="jur-airoli-sec08",
            # Exactly what the caller passes today: origin + degrees, as metres.
            polygon_wkt_2d=polygon_wkt([list(p) for p in OSM_RING]),
            polygon_geojson={
                "type": "Polygon",
                "coordinates": [[list(p) for p in OSM_RING] + [list(OSM_RING[0])]],
            },
            document_area_m2=OSM_RING_AREA_M2,
            calculated_area_m2=OSM_RING_AREA_M2,
        )
    )

    assert _srid_of(parcel.geom) == 32643
    written = _open_ring(parcel.geom)
    for want_e, want_n in OSM_RING_UTM43N:
        assert (want_e, want_n) == pytest.approx(
            min(written, key=lambda p: math.hypot(p[0] - want_e, p[1] - want_n)),
            abs=0.01,
        )
    for bad_e, bad_n in OSM_RING_CORRUPT_UTM43N:
        assert math.hypot(bad_e - written[0][0], bad_n - written[0][1]) > 1000.0

    assert parcel.gis_area_m2 == pytest.approx(OSM_RING_AREA_M2, abs=1.0)
    assert parcel.gis_area_m2 != 0.0


def test_upsert_parcel_leaves_geom_null_when_the_polygon_is_not_degrees(monkeypatch):
    """The generated hero parcel hands over bare local metres.

    `polygon_geojson` is NOT NULL and is served straight to clients as GeoJSON, so
    this path refuses to invent a position: `geom` stays NULL and `gis_area_m2`
    is left alone rather than written as a measured 0.0.
    """
    from app.core import cadastre_store
    from app.core.cadastre_store import upsert_parcel

    monkeypatch.setattr(cadastre_store, "_schema_ready", True)
    db = _FakeSession()

    parcel = asyncio.run(
        upsert_parcel(
            db,
            ulpin="12345678901234",
            survey_number="S-17/SEC-08/AIROLI",
            jurisdiction_id="JUR-AIROLI-S8",
            polygon_wkt_2d=polygon_wkt(
                [[145.0, 144.0], [175.0, 144.0], [175.0, 161.0], [145.0, 161.0]]
            ),
            polygon_geojson={
                "type": "Polygon",
                "coordinates": [
                    [[145.0, 144.0], [175.0, 144.0], [175.0, 161.0], [145.0, 161.0], [145.0, 144.0]]
                ],
            },
            document_area_m2=510.0,
            calculated_area_m2=510.0,
        )
    )

    assert parcel.geom is None, "metres must not be stored as a 32643 polygon"
    assert parcel.gis_area_m2 is None, "a parcel with no geometry has no GIS area"
    assert parcel.document_area_m2 == 510.0
    assert parcel.calculated_area_m2 == 510.0


def test_no_write_path_assigns_a_caller_supplied_wkt_to_parcel_geom():
    """Source gate: `parcel.geom` is derived, never passed through.

    Assigning the caller's WKT was the bug in `upsert_parcel`; the builder path
    now assigns a locally anchored polygon and must keep doing so. Parsed rather
    than grepped, so a mention inside a comment cannot satisfy or break the gate.
    """
    root = Path(__file__).resolve().parents[1] / "backend" / "app"
    forbidden = {"polygon_wkt_2d", "polygon_wkt"}

    for relative in ("core/cadastre_store.py", "services/builder_records.py"):
        tree = ast.parse((root / relative).read_text())
        passed_through = [
            node.value.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name)
            and node.value.id in forbidden
            and any(
                isinstance(t, ast.Attribute) and t.attr == "geom" for t in node.targets
            )
        ]
        assert passed_through == [], f"{relative} assigns a supplied WKT to .geom"

    # The builder path must still put a real 32643 polygon in the column, derived
    # from an explicitly declared anchor rather than from the caller's WKT.
    builder = ast.parse((root / "services" / "builder_records.py").read_text())
    assigned_to_geom = {
        node.value.id
        for node in ast.walk(builder)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Name)
        and any(isinstance(t, ast.Attribute) and t.attr == "geom" for t in node.targets)
    }
    assert assigned_to_geom == {"parcel_ewkt"}, assigned_to_geom