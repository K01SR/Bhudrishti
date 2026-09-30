import json
import re

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

# The demonstration signing key, published in app.core.crypto. It is no longer
# a config default; it is reachable only while ENABLE_DEMO_MODE is on. Kept here
# so a change of key is a deliberate decision rather than a silent drift, and
# so the disclosure assertions above cannot pass vacuously.
_KNOWN_DEV_KEYS = {
    "7a4d9526786c2e36b3df516147bb0630b9101d2d3a37c92b23c2a382c40c1110",
}

client = TestClient(app)


def test_root_and_health():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "OPERATIONAL"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "HEALTHY"


def test_demo_accounts_endpoint():
    res = client.get("/api/v1/auth/demo-accounts")
    assert res.status_code == 200
    accounts = res.json()
    assert len(accounts) >= 5
    usernames = [a["username"] for a in accounts]
    assert "state.admin" in usernames
    assert "district.admin" in usernames
    assert "builder.demo" in usernames


def test_canonical_hero_property_endpoint():
    res = client.get("/api/v1/properties/hero")
    assert res.status_code == 200
    prop = res.json()
    assert prop["parent_ulpin"] == "12345678901234"
    assert prop["structure"]["building_code"] == "B-17"
    assert len(prop["units"]) >= 21
    assert "cryptographic_proof" in prop
    # The proof is self-signed with a published key. Reporting it as verified
    # claimed an authority had confirmed the record, which none has.
    proof = prop["cryptographic_proof"]
    assert proof["verification_status"] == "SELF_SIGNED_BY_THIS_SERVICE"
    assert proof["signer_authority"] is None
    assert "does not establish" in proof["disclosure"]["signature_does_not_validate"]


def test_public_qr_verify_endpoint():
    """
    The public QR endpoint is a database lookup, not a verification service.

    This test previously asserted the opposite: it required
    verification_result == "OFFICIAL_RECORD_VERIFIED", status == "APPROVED" and
    signature_status == "VALID", which pinned the fabricated government claims
    in place. It now asserts that none of those strings can come back, so a
    regression reintroducing them fails the suite.
    """
    res = client.get("/api/v1/qr/verify/token-airoli-b17-hero-proof")
    assert res.status_code == 200
    data = res.json()

    assert data["verified"] is False
    assert data["verification_result"] == "UNVERIFIED_PROTOTYPE_LOOKUP"
    assert data["status"] == "PROTOTYPE_DEMO_RECORD"
    assert data["verifying_authority"] is None
    assert data["cryptographic_proof"]["signature_status"] == "SELF_VALIDATED_ONLY"
    assert data["cryptographic_proof"]["tamper_evident_hash_chain"] is None
    # No authority, seal or "officially registered" language anywhere in the body.
    body = json.dumps(data)
    for forged in (
        "OFFICIAL_RECORD_VERIFIED",
        "Settlement Commissioner",
        "Director of Land Records",
        "APPROVED",
        "VALID_AUDIT_ANCHOR",
        "Survey of India",
        "Airborne LiDAR",
    ):
        assert forged not in body, f"public endpoint still claims {forged!r}"


def test_public_qr_lookup_signing_key_is_public_so_signature_proves_nothing():
    """
    Guards the disclosure shipped with the response: the Ed25519 key is a
    committed development constant, so the self-validation is circular and the
    endpoint says so rather than implying authenticity.
    """
    from app.core import crypto

    res = client.get("/api/v1/qr/verify/token-airoli-b17-hero-proof")
    disclosure = res.json()["cryptographic_proof"]["disclosure"]

    assert disclosure["public_key_published"] is False
    assert disclosure["independent_auditor"] is None
    assert "does not establish" in disclosure["signature_does_not_validate"]
    # If the key ever stops being a known dev constant, this test should be
    # revisited, because the disclosure above would no longer be accurate.
    # The key is no longer a config default: it resolves from the demo keypair
    # that is published in app.core.crypto, so the disclosure still holds.
    assert settings.ED25519_PRIVATE_KEY_HEX is None
    assert crypto._resolve_private_key_hex() in _KNOWN_DEV_KEYS
    assert crypto.DEMO_ED25519_PRIVATE_KEY_HEX in _KNOWN_DEV_KEYS


def test_public_certificate_is_not_titled_as_government_document():
    """The certificate endpoint used to emit a Government of Maharashtra title."""
    res = client.get("/api/v1/qr/certificate/token-airoli-b17-hero-proof")
    assert res.status_code == 200
    data = res.json()
    assert data["is_government_document"] is False
    body = json.dumps(data)
    assert "GOVERNMENT OF MAHARASHTRA" not in body
    assert "BHU-DRISHTI 3D CADASTRAL CERTIFICATE" not in body


def test_ask_the_map_clash_query():
    res = client.post("/api/v1/queries/ask", json={"query": "Show underground clashes"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent_category"] == "UNDERGROUND_CLASH_SEARCH"
    assert "PIPE-DRAIN-01" in data["matched_entity_ids"]
    assert data["highlight_3d"]["mode"] == "underground"


def test_interoperability_cityjson_export():
    res = client.get("/api/v1/exports/cityjson")
    assert res.status_code == 200
    cj = res.json()
    assert cj["type"] == "CityJSON"
    assert "Building_B17" in cj["CityObjects"]


def test_osm_endpoints_and_geodetic_conversion():
    client = TestClient(app)
    
    # 1. Test OSM streets endpoint
    res_streets = client.get("/api/v1/osm/streets")
    assert res_streets.status_code == 200
    streets_data = res_streets.json()
    assert streets_data["total_street_segments"] >= 8
    assert streets_data["total_streetlights"] > 0
    assert streets_data["total_roadside_trees"] > 0
    
    # 2. Test OSM amenities endpoint
    res_amenities = client.get("/api/v1/osm/amenities")
    assert res_amenities.status_code == 200
    amenities_data = res_amenities.json()
    assert amenities_data["total_amenities"] >= 8
    
    # 3. Test coordinate conversion endpoint
    res_coords = client.get("/api/v1/osm/coordinates/convert?x=160&y=152.5&z=18")
    assert res_coords.status_code == 200
    coords_data = res_coords.json()
    assert "wgs84" in coords_data
    assert "utm_zone_43n" in coords_data
    assert "elevation_msl" in coords_data
    assert coords_data["utm_zone_43n"]["easting"] == 298160.0
    assert coords_data["utm_zone_43n"]["northing"] == 2113652.5
    
    # 4. Test civic dossier endpoint
    res_dossier = client.get("/api/v1/osm/civic-dossier/B-17")
    assert res_dossier.status_code == 200
    dossier = res_dossier.json()
    assert dossier["building_code"] == "B-17"
    assert "property_tax_dossier" in dossier
    assert "water_and_sewage_dossier" in dossier
    assert "electrical_utility_dossier" in dossier
    assert "maharera_concordance" in dossier
    assert "environmental_green_dossier" in dossier
    # The seismic zone is an assumption behind a placeholder model, so it has to
    # say so. It previously read "Zone III (Moderate Seismic Zone, Z=0.16)" and
    # was pinned here as if the value had come from a hazard map.
    assert "Assumed" in dossier["structural_and_seismic_dossier"]["seismic_zone"]


def test_civic_dossier_invents_no_registries_or_instruments():
    """
    generate_civic_dossier_for_building used to fabricate, for every OSM
    building in the precinct, a property tax assessment with arrears and a no-dues
    certificate, a water connection with a sanctioned quota, an MSEDCL consumer
    account, a structural certificate from a "NABL Accredited Testing Lab", a
    fire NOC, a MahaRERA project id, an occupancy certificate, a named escrow
    bank and a statutory clearance. All of it derived from abs(hash(code)).
    """
    client = TestClient(app)
    dossier = client.get("/api/v1/osm/civic-dossier/B-17").json()

    assert dossier["synthetic"] is True
    assert "Nothing here is a record" in dossier["disclaimer"]

    # Nothing may look like a real instrument, account or clearance.
    for path, field in (
        (("property_tax_dossier",), "assessment_id"),
        (("property_tax_dossier",), "no_dues_certificate_no"),
        (("property_tax_dossier",), "authority"),
        (("water_and_sewage_dossier",), "consumer_meter_no"),
        (("water_and_sewage_dossier",), "sewerage_connection_id"),
        (("electrical_utility_dossier",), "consumer_account_no"),
        (("electrical_utility_dossier",), "utility_provider"),
        (("electrical_utility_dossier",), "tariff_category"),
        (("structural_and_seismic_dossier",), "audit_agency"),
        (("structural_and_seismic_dossier",), "certificate_valid_till"),
        (("structural_and_seismic_dossier",), "fire_noc_status"),
        (("maharera_concordance",), "rera_project_id"),
        (("maharera_concordance",), "occupancy_certificate_no"),
        (("maharera_concordance",), "escrow_bank"),
        (("maharera_concordance",), "statutory_clearance"),
        (("maharera_concordance",), "rera_status"),
    ):
        node = dossier
        for key in path:
            node = node[key]
        assert node[field] is None, f"{'.'.join(path)}.{field} still fabricates a value"

    # And no compliance verdict survives in any value. The note fields are
    # excluded because they describe the previous behaviour, so they legitimately
    # contain the words they are disowning.
    prose = {"note", "disclaimer", "model_basis", "solid_waste_note",
             "nbc_standard", "seismic_zone", "concrete_grade", "supply_voltage",
             "meter_type", "project_name", "promoter", "model_basis_note"}

    def scan(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in prose:
                    continue
                yield from scan(value)
        elif isinstance(node, list):
            for item in node:
                yield from scan(item)
        elif isinstance(node, str):
            yield node

    claims = " ".join(scan(dossier))
    for verdict in ("COMPLIANT", "CERTIFIED", "VALID_TILL", "NOTICE_ISSUED",
                    "CLEARED", "NABL", "MSEDCL", "HDFC", "PAID_NO_ARREARS",
                    "DEFAULT_OVERDUE", "REGISTERED_COMPLETED", "UNDER_SCRUTINY",
                    "UNAUTHORIZED"):
        assert verdict not in claims, f"civic dossier still claims {verdict}"


def test_dynamic_property_card_pdf_and_latex():
    """Permanent regression test for arbitrary ULPIN property card generation without 404."""
    test_ulpin = "3D-ULPIN-NZIUOTK4MJZFMT"
    
    # 1. Test PDF generation
    pdf_res = client.get(f"/api/v1/exports/pdf/property-card/{test_ulpin}")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")
    assert len(pdf_res.content) > 5000

    # 2. Test LaTeX generation
    tex_res = client.get(f"/api/v1/exports/latex/property-card/{test_ulpin}")
    assert tex_res.status_code == 200
    assert tex_res.headers["content-type"] == "application/x-tex"
    # This previously asserted "FORM 3D-ULPIN" was present, which pinned the
    # forged government form title in place. The exports are prototype output
    # and now say so on every page.
    tex = tex_res.text
    assert "NOT A GOVERNMENT DOCUMENT" in tex
    assert "FORM 3D-ULPIN" not in tex
    for forged in (
        "GOVERNMENT OF MAHARASHTRA",
        "Settlement Commissionerate",
        "Sunita Patil",
        "Deshmukh",
        "SOVEREIGN SEAL",
    ):
        assert forged not in tex, f"export still claims {forged!r}"


def test_universal_lidar_streaming_endpoints():
    """Permanent regression test for universal classified point cloud streaming."""
    test_ulpin = "3D-ULPIN-NZIUOTK4MJZFMT"

    # 1. JSON endpoint
    json_res = client.get(f"/api/v1/lidar/pointcloud?ulpin={test_ulpin}")
    assert json_res.status_code == 200
    data = json_res.json()
    assert data["point_count"] > 0
    assert "classifications" in data
    assert "ground" in data["classifications"]
    assert "roof" in data["classifications"]
    assert "wall" in data["classifications"]

    # 2. Binary Float32Array endpoint
    bin_res = client.get(f"/api/v1/lidar/pointcloud/binary?ulpin={test_ulpin}")
    assert bin_res.status_code == 200
    assert bin_res.headers["content-type"] == "application/octet-stream"
    pt_count = int(bin_res.headers["x-point-count"])
    assert pt_count > 0
    # Each point is 8 float32 values (32 bytes per point)
    assert len(bin_res.content) == pt_count * 32


def test_precinct_buildings_and_heatmap():
    """Test multi-building precinct and FSI/Risk heatmap endpoints."""
    res_blds = client.get("/api/v1/precinct/buildings")
    assert res_blds.status_code == 200
    blds = res_blds.json()
    assert len(blds) >= 13

    res_heat = client.get("/api/v1/precinct/heatmap/fsi")
    assert res_heat.status_code == 200
    heat = res_heat.json()
    assert heat["mode"] == "fsi"
    assert len(heat["buildings"]) >= 12


def test_floorplan_ingestion_api():
    """Test architectural floor plan ingestion via manual trace and DXF upload."""
    import io
    import ezdxf

    # 1. Test Manual Trace endpoint
    payload = {
        "unit_polygons": [
            [[0.0, 0.0], [10.0, 0.0], [10.0, 8.0], [0.0, 8.0], [0.0, 0.0]],
            [[10.0, 0.0], [20.0, 0.0], [20.0, 8.0], [10.0, 8.0], [10.0, 0.0]]
        ],
        "parent_ulpin": "12345678901234",
        "building_code": "B17",
        "level_code": "L01",
        "base_elevation_m": 3.6,
        "floor_height_m": 3.6
    }
    trace_res = client.post("/api/v1/evidence/floorplan/trace", json=payload)
    assert trace_res.status_code == 200
    data = trace_res.json()
    assert data["source_type"] == "FLOOR_PLAN_MANUAL_TRACE"
    assert data["units_count"] == 2
    assert data["total_level_volume_m3"] == 576.0
    assert len(data["units"]) == 2

    # 2. Test DXF upload endpoint
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (15, 0), (15, 10), (0, 10)], close=True)
    dxf_stream = io.StringIO()
    doc.write(dxf_stream)
    dxf_bytes = dxf_stream.getvalue().encode("utf-8")

    files = {"file": ("floorplan.dxf", dxf_bytes, "application/dxf")}
    data_form = {
        "parent_ulpin": "12345678901234",
        "building_code": "B17",
        "level_code": "L03",
        "base_elevation_m": "10.8",
        "floor_height_m": "3.6"
    }
    dxf_res = client.post("/api/v1/evidence/floorplan/dxf", files=files, data=data_form)
    assert dxf_res.status_code == 200
    dxf_data = dxf_res.json()
    assert dxf_data["source_type"] == "FLOOR_PLAN_DXF"
    assert dxf_data["units_count"] >= 1
    assert dxf_data["units"][0]["min_z"] == 10.8




def test_property_card_pdf_contains_no_government_identity():
    """
    The property-card PDF is the artifact most likely to be forwarded to a bank,
    a buyer or an official, so it is checked as rendered text rather than as
    source.

    It previously rendered a Government of Maharashtra letterhead, a
    "REVENUE AND FOREST DEPARTMENT - SETTLEMENT COMMISSIONERATE" title, a
    "Certificate of Sovereign Gazetted Endorsement", a "Sovereign State Seal",
    an "Attested & Gazetted By" block naming two individuals including a
    serving civil servant, a "MAHABHUMI DIGITAL LAND RECORDS SYSTEM" banner, a
    MahaRERA registration number, and claims of a Land Revenue Code mandate and
    a sovereign proof-of-work blockchain.
    """
    import base64
    import zlib

    res = client.get("/api/v1/exports/pdf/property-card/12345678901234")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")

    # ReportLab writes content streams as /ASCII85Decode + /FlateDecode, so
    # decoding has to undo both. An earlier version of this test only tried
    # zlib, decoded nothing, and therefore passed while asserting nothing.
    decoded = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", res.content, re.S):
        blob = m.group(1).strip()
        if blob.endswith(b"~>"):
            # ReportLab strips the "<~" prefix and keeps the "~>" EOD marker,
            # which the non-adobe decoder rejects.
            blob = blob[:-2]
        try:
            blob = base64.a85decode(blob, adobe=False)
        except Exception:
            pass
        try:
            decoded.append(zlib.decompress(blob).decode("latin-1"))
        except Exception:
            continue
    raw = "\n".join(decoded)

    # Guard the guard: if the extraction ever stops working the assertions below
    # would silently pass, so require that text was actually recovered.
    assert len(raw) > 1000, "no PDF text recovered; the checks below would be vacuous"
    assert "Bhu-Drishti" in raw, "extraction did not recover the document text"

    for forged in (
        "GOVERNMENT OF MAHARASHTRA",
        "GOVT OF MAHARASHTRA",
        "REVENUE AND FOREST",
        "REVENUE & FOREST",
        "Settlement Commissioner",
        "Director of Land Records",
        "Deshmukh",
        "Sunita Patil",
        "MAHABHUMI",
        "SOVEREIGN SEAL",
        "P51700018942",
    ):
        assert forged.lower() not in raw.lower(), f"PDF renders {forged!r}"


def test_property_card_pdf_states_no_utility_clearance_was_assessed():
    """
    The card asserted a confirmed NMMC potable-water clearance, a Metro Rail
    buffer distance and a LiDAR-confirmed zero overhang. No municipal utility
    layer, rail-corridor geometry or surveyed LiDAR return is ever ingested, so
    each of those numbers was invented and presented as a measured result.
    """
    import base64
    import zlib

    from app.id_engine.latex_pdf_generator import generate_property_card_pdf

    content = generate_property_card_pdf()
    decoded = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", content, re.S):
        blob = m.group(1).strip()
        if blob.endswith(b"~>"):
            blob = blob[:-2]
        try:
            blob = base64.a85decode(blob, adobe=False)
        except Exception:
            pass
        try:
            decoded.append(zlib.decompress(blob).decode("latin-1"))
        except Exception:
            continue
    raw = "\n".join(decoded)
    assert len(raw) > 1000, "no PDF text recovered; the checks below would be vacuous"

    for forged in (
        "NMMC",
        "Metro Rail",
        "Water Utility Clearance:</b> Clear",
        "Laser scan confirms",
        "drone scans confirm",
        "automated quality assurance checks against municipal GIS",
    ):
        assert forged.lower() not in raw.lower(), f"PDF renders {forged!r}"

    # The clearance headings survive as an explicit non-result, so a reader
    # sees that the check was skipped rather than quietly omitted.
    assert "NOT ASSESSED" in raw, "the unassessed-utility disclosure is missing"


def test_latex_property_card_makes_no_authority_claim():
    """
    The LaTeX card carried a second, independent forgery that the reportlab
    card had already been cleared of: the genuine postal address of the
    Directorate of Land Records, Pune, rendered directly under the prototype
    banner as if it were the issuing office. It also asserted the same
    invented utility clearances as the reportlab card.
    """
    from app.id_engine.latex_pdf_generator import generate_latex_property_card

    tex = generate_latex_property_card()
    assert len(tex) > 5000, "LaTeX body looks truncated; the checks below would be vacuous"

    for forged in (
        "Directorate of Land Records",
        "NMMC",
        "drone scans confirm",
        "automated quality assurance checks against municipal GIS",
        "satisfying the Maharashtra Metro Railways",
    ):
        assert forged.lower() not in tex.lower(), f"LaTeX card renders {forged!r}"

    assert "NOT ASSESSED" in tex, "the unassessed-utility disclosure is missing"
    assert "No departmental or government affiliation" in tex


def test_evidence_streams_report_nothing_as_obtained():
    """
    Every evidence stream was reported available with an official provenance, a
    Tier A survey grade, a measured quality metric and a file hash, for surveys
    and approvals that do not exist.
    """
    from app.api.v1.evidence import EVIDENCE_STREAMS

    assert EVIDENCE_STREAMS, "catalogue should be retained for the pipeline"
    for ev in EVIDENCE_STREAMS:
        assert ev["available"] is False, f"{ev['id']} claims data was obtained"
        assert ev["provenance_kind"] if "provenance_kind" in ev else True
        assert "file_hash" not in ev, f"{ev['id']} carries a fabricated hash"
        assert ev["confidence_tier"] == "None"
        assert "provenance" in ev


def test_ask_the_map_reads_the_dataset_per_request(monkeypatch):
    """The router used to hold one snapshot taken when it was first imported.

    `load_demo_dataset()` returns the empty stand-in while the demo gate is
    shut, and the demo flag is read from the environment, so importing this
    module before the flag was set left every answer built from nothing for the
    life of the process -- silently, because the empty answer is a well-formed
    "no match" rather than an error. The gate being read on each call is
    exactly what `demo_mode_enabled` documents; this pins that the router
    honours it.
    """
    from app.api.v1 import ask_map

    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    found = ask_map.parse_query_deterministically("Show underground clashes")
    assert found["matched_ids"], "a live demo dataset must yield clashes"

    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    shut = ask_map.parse_query_deterministically("Show underground clashes")
    assert shut["matched_ids"] == []
    assert shut["category"] == "UNDERGROUND_CLASH_SEARCH"

    # No module-level snapshot left behind to answer from.
    src = open(ask_map.__file__).read()
    assert "\n_DATASET = load_demo_dataset()" not in src
