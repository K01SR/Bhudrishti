"""The UI must not present this prototype as a government system.

Found during the honesty sweep. The backend had already been through several
passes -- `app.core.cadastre_store` reports PENDING_REVIEW instead of SURVEYED,
`app.id_engine.types` calls itself a proposed demo specification, and
`test_precinct_authority.py` pins the removal of invented municipal instruments
from the precinct endpoints. The frontend had not kept up, and the gap was not
cosmetic. It fell into three kinds:

Claims about the data, where a static string described a measurement that was
never taken. The builder's six-step "audit" was a setTimeout chain that ended in
`setVerificationPassed(true)` regardless of input and then printed "Regulator
Fast-Track Sanction Approved (Concordance: 99.2%)" above a hardcoded Ed25519
seal attributed to section 148A of the Maharashtra Land Revenue Code. Its
setback step claimed "NBC 2016 PASS" with Front 6.0m / Rear 4.5m figures, its
utility step claimed "ZERO CLASH" against a 600mm trunk water main and an 82.4m
metro corridor satisfying "Metro Railways Safety Clearance rules", and the deed
monograph printed a MahaRERA registration number, P51700018942, invented in the
numbering format of a real regulator.

Claims about the system itself, which are worse because they are about who built
it. The landing page footer rendered a "DEPARTMENT OF LAND RESOURCES (DOLR)"
wordmark over "Ministry of Rural Development - Government of India & Government
of Maharashtra", and the i18n badge read "GOVERNMENT OF INDIA - MoHUA & DoLR".
The seed accounts were fictional officials -- a "State Cadastral Commissioner",
a "Thane District Land Records Verifier", a "Taluka Survey Officer" -- on
addresses at a bhudrishti.gov.in domain that does not exist. The LaTeX export
named `node-01.airoli.cadastre.gov.in` as consensus validator directly beneath a
line reading "Consensus Protocol: None".

And numbers that could not be true, where a hardcoded figure had drifted from
what the API returns. The identifier page advertised "44,323" national parcels
and "15,091" admin boundaries as "full georeferenced coverage" while the
catalogue held 469 identifiers across 13 buildings -- figures it had already
fetched and was not using. The registry showed an "Approved" tile equal to
`parcels.length - 1` in success green when nothing had been approved.

These tests pin the removal of each of those. They read source rather than
render, so they hold without a browser; a matching rendered-DOM check lives in
the Playwright scripts under artifacts/.
"""
import inspect
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
BACKEND = REPO / "backend" / "app"


def _frontend_sources():
    for path in SRC.rglob("*.ts*"):
        if "node_modules" in path.parts:
            continue
        yield path


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# Words that turn a mention of a body into a denial of a connection. A line
# containing one of these is a disclaimer, not a claim.
_NEGATIONS = (
    "not connected",
    "no such",
    "not affiliated",
    "is not a",
    "not a government",
    "not a real",
    "NOT A GOVERNMENT",
    "no government department",
    "never",
    "none",
    "cannot",
    "without",
    "not issued",
    "not published",
)


def _is_negated(line: str) -> bool:
    return any(token in line for token in _NEGATIONS)


def _line_at(text: str, index: int) -> str:
    """
    The whole source line containing `index`.

    Deliberately not `text[:index].splitlines()[-1]`: that returns only the part
    of the line *before* the match, which silently drops any negation that
    follows the term. "connected to the DoLR ... and cannot attest" would read
    as a bare claim.
    """
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return text[start:] if end == -1 else text[start:end]


_TRIPLE_QUOTED = re.compile("\"\"\"(?:.|\\n)*?\"\"\"|'''(?:.|\\n)*?'''")


def _python_code(path: pathlib.Path) -> str:
    """
    Source with docstrings and comments removed, keeping ordinary string literals.

    Several of the fixes below explain in prose exactly which claim they removed,
    so a naive scan of the file finds the very tokens it is looking for. The
    checks that matter target *quoted* patterns: a dict key, a status value or an
    f-string prefix. Those only exist in real code.
    """
    text = _TRIPLE_QUOTED.sub('""', _read(path))
    import io
    import tokenize

    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                continue
            out.append(tok)
    except tokenize.TokenError:
        return text
    # untokenize, not " ".join: the checks below include multi-token patterns
    # like '"status": "PASS" if', and joining with spaces would silently make
    # them unfindable, which is a test that can never fail.
    return tokenize.untokenize(out)


def _strip_docstrings_and_comments(source: str) -> str:
    """
    Same treatment as _python_code(), for callers holding a source string
    (inspect.getsource) rather than a path.
    """
    text = _TRIPLE_QUOTED.sub('""', source)
    import io
    import tokenize

    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                continue
            out.append(tok)
    except tokenize.TokenError:
        return text
    return tokenize.untokenize(out)



# --------------------------------------------------------------------------- #
# 1. Government affiliation                                                    #
# --------------------------------------------------------------------------- #

# Strings that would be a false claim of endorsement if rendered. Each is
# checked across the whole frontend, not just the file it was found in, so the
# phrasing cannot simply move.
AFFILIATION_BANNED = [
    "GOVERNMENT OF INDIA",
    "Government of India &",
    "Ministry of Rural Development",
    "DEPARTMENT OF LAND RESOURCES",
    "MoHUA",
    "DoLR",
    "Cadastral Commissioner",
    "Taluka Survey Officer",
    "District Land Records Verifier",
]


def test_frontend_makes_no_claim_of_government_affiliation():
    """
    Banned strings are only a violation where the page asserts the affiliation.
    A disclaimer that names a department in order to deny a connection -- "is not
    connected to the DoLR" -- is the opposite of a claim, so each hit is checked
    for a negation in the same sentence.
    """
    offenders = []
    for path in _frontend_sources():
        text = _read(path)
        for needle in AFFILIATION_BANNED:
            for match in re.finditer(re.escape(needle), text):
                line = _line_at(text, match.start())
                if _is_negated(line):
                    continue
                offenders.append(f"{path.relative_to(REPO)}: {line.strip()[:80]}")
    assert not offenders, (
        "The UI claims endorsement by a government body. This is a student "
        "prototype with no such affiliation:\n  " + "\n  ".join(offenders)
    )


def test_landing_page_footer_names_the_student_team():
    footer = _read(SRC / "pages" / "LandingPage.tsx")
    # The wordmark is still there, but it must not be a department's name.
    assert "DEPARTMENT OF LAND RESOURCES" not in footer
    assert "SIH26011 STUDENT TEAM" in footer
    assert "not affiliated with or endorsed by any government department" in footer


# --------------------------------------------------------------------------- #
# 2. Fabricated government email addresses                                    #
# --------------------------------------------------------------------------- #

def test_no_invented_gov_in_addresses():
    """
    bhudrishti.gov.in was used for seed accounts and a LaTeX validator node. The
    domain is not registered to this project, so presenting officials on it is a
    fabricated identity rather than a placeholder.
    """
    offenders = []
    for root in (SRC, BACKEND, REPO / "tests"):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if "node_modules" in path.parts:
                continue
            # This file names the domain in order to ban it.
            if path.resolve() == pathlib.Path(__file__).resolve():
                continue
            if "bhudrishti.gov.in" in _read(path):
                offenders.append(str(path.relative_to(REPO)))
    assert not offenders, (
        "Invented .gov.in addresses still present: " + ", ".join(offenders)
    )


def test_seed_accounts_do_not_pose_as_officials():
    """
    Usernames and ids stay put because permission logic and tests read them; the
    displayed identity is what had to change.
    """
    auth = _read(BACKEND / "api" / "v1" / "auth.py")
    assert "not a real official" in auth
    assert "not a surveyor" in auth
    for banned in ("Commissioner", "Survey Officer", "Land Records Verifier"):
        assert banned not in auth, f"seed account still titled {banned}"


# --------------------------------------------------------------------------- #
# 3. Invented regulatory verdicts and attestations                             #
# --------------------------------------------------------------------------- #

VERDICT_BANNED = [
    # Regulator sanction that was never granted.
    "Regulator Fast-Track Sanction",
    "Concordance: 99.2",
    "Land Revenue Code 1966 Section 148A",
    # Building-code compliance never checked against a real rule set.
    "NBC 2016 PASS",
    "DCR Compliant",
    "Requires TDR",
    # Measurements that were typed in by hand.
    "ZERO CLASH",
    "0 Clashes",
    "Metro Railways Safety Clearance",
    "0.00mm Overhang",
    "0.00mm shift",
    "100% Manifold",
    # PoW / quorum / a regulator's registration number in its own format.
    "PoW Nonce",
    "Unanimous Endorsement",
    "P51700018942",
    "MahaRERA Sanction",
    # A deed implies an executed legal instrument.
    "Gazetted Deed",
    "Official Deed",
    # A fabricated validator host, directly under a "Consensus: None" row.
    "node-01.airoli.cadastre.gov.in",
]


def test_frontend_states_no_invented_regulatory_verdicts():
    offenders = []
    for path in _frontend_sources():
        text = _read(path)
        for needle in VERDICT_BANNED:
            if needle in text:
                offenders.append(f"{path.relative_to(REPO)}: {needle}")
    assert not offenders, (
        "The UI asserts a regulatory finding or attestation that was never "
        "made:\n  " + "\n  ".join(offenders)
    )


def test_audit_chain_is_not_described_as_a_blockchain():
    audit = _read(SRC / "pages" / "app" / "AuditPage.tsx")
    # The endpoint is a hardcoded list appended to in-process memory.
    for banned in ("Sovereign Ledger", "Sovereign Cadastral Blockchain",
                   "Maha-Cadastral Mainnet", "Blockchain Explorer"):
        assert banned not in audit, f"AuditPage still presents {banned}"
    assert "Not a blockchain" in audit


def test_audit_endpoint_is_an_in_process_list():
    """Pins the fact the relabelling depends on: there is no chain to describe."""
    audit = _read(BACKEND / "api" / "v1" / "audit.py")
    assert "_AUDIT_LOGS" in audit
    for banned in ("web3", "eth_tester", "blockchain", "Solidity"):
        assert banned not in audit, f"audit.py now references {banned}"


def test_builder_audit_is_documented_as_a_fixed_timer():
    """
    runVerificationAudit is a setTimeout chain that always finishes, so the copy
    beside it has to admit that. If someone later wires it to real checks, this
    test should fail and the copy should change with it.
    """
    home = _read(SRC / "pages" / "app" / "AppHome.tsx")
    assert "setVerificationPassed(true)" in home, "the walkthrough moved; update this test"
    assert "fixed timer that always completes" in home
    for banned in ("Run Live Verification Audit", "Auditing Step"):
        assert banned not in home


# --------------------------------------------------------------------------- #
# 4. Figures that cannot be true                                               #
# --------------------------------------------------------------------------- #

def test_identifier_page_reads_counts_from_the_api():
    """
    44,323 parcels and 15,091 boundaries were hardcoded while the catalogue held
    469 across 13 buildings. The page already fetched the real totals and was not
    using them in these tiles.
    """
    ulpin = _read(SRC / "pages" / "app" / "ULPINPage.tsx")
    for banned in ("44,323", "15,091", "NBC 2016 Setback Engine"):
        assert banned not in ulpin, f"ULPINPage still hardcodes {banned}"
    assert "catalogueTotals.total_3d_ids" in ulpin
    assert "catalogueTotals.total_buildings" in ulpin
    assert "No national parcel dataset is loaded" in ulpin


def test_registry_derives_twin_and_verified_counts():
    """
    "Approved" was `parcels.length - 1` in success green, and the twin count was
    a literal 1 with the table column keyed off the hero ULPIN rather than has_3d,
    so a second twin could not be represented.
    """
    registry = _read(SRC / "pages" / "app" / "PropertyRegistry.tsx")
    assert "twinCount" in registry
    assert "verifiedCount" in registry
    assert "p.has_3d" in registry
    assert ">Approved<" not in registry
    # The "Approved" tile derived from a subtraction on the parcel count.
    assert "parcels.length - 1" not in registry


def test_identifier_totals_count_emitted_units_not_stored_metadata():
    """
    The 3D registry printed two precinct totals for the same data. It summed the
    stored `units_count` on one side and the emitted `units` on the other, and the
    two disagree whenever a record carries a count but no unit list -- which the
    hero tower did. `units_count || units?.length` trusted the metadata first.
    """
    ulpin = _read(SRC / "pages" / "app" / "ULPINPage.tsx")
    assert "b.units_count || b.units?.length" not in ulpin
    assert "selectedBuilding.units_count || selectedBuilding.units?.length" not in ulpin
    assert "b?.units?.length ?? b?.units_count" in ulpin
    inspector = _read(SRC / "components" / "lidarinspector" / "LiDARInspector.tsx")
    assert "p.units_count || (p.units ? p.units.length : 0)" not in inspector


def test_locate_page_does_not_call_a_seed_list_official():
    locate = _read(SRC / "pages" / "app" / "LocatePage.tsx")
    assert "official State" not in locate
    assert "Official 3D ULPIN" not in locate
    assert "not an official gazetteer" in locate


def test_hierarchy_is_a_hardcoded_seed():
    """
    Pins why the Locate copy had to change: the administrative hierarchy is a
    literal dict in the backend, not a gazetteer.
    """
    locations = _read(BACKEND / "api" / "v1" / "locations.py")
    assert "ADMIN_HIERARCHY" in locations
    assert "demo seed" in locations


def test_buyer_shield_header_agrees_with_its_own_footer():
    """
    The header claimed MahaRERA, LiDAR as-built, OC sanction and CERSAI lookups
    while the footer of the same modal said none of them were queried.
    """
    shield = _read(SRC / "components" / "modals" / "BuyerShieldModal.tsx")
    assert "No MahaRERA, CERSAI, municipal or LiDAR source is queried" in shield
    assert "Multi-Pillar Verification" not in shield
    assert "No MahaRERA, CERSAI or municipal registry was queried" in shield


def test_deed_monograph_drops_its_invented_identifiers():
    """
    The monograph claimed it was issued under the Land Revenue Code, conformed to
    ISO 19152 and was millimetre-accurate, and printed a MahaRERA number in that
    regulator's format.
    """
    deed = _read(SRC / "components" / "modals" / "GovernmentDeedPrintModal.tsx")
    for banned in ("P51700018942", "MahaRERA Sanction",
                   "conforming to ISO 19152", "GTS)", "Proof-of-Work"):
        assert banned not in deed, f"deed monograph still contains {banned}"
    assert "Not looked up" in deed


def test_legal_references_stay_disclaimed():
    """
    Citing the Land Revenue Code and MahaRERA is fine as vocabulary, provided the
    sheet says no provision of them was applied. The disclaimer is load-bearing.
    """
    deed = _read(SRC / "components" / "modals" / "GovernmentDeedPrintModal.tsx")
    assert "not applied as legal authority" in deed
    assert "No provision" in deed


def test_latex_export_names_no_validator_host():
    latex = _read(BACKEND / "id_engine" / "latex_pdf_generator.py")
    assert "node-01.airoli.cadastre.gov.in" not in latex
    # It sits directly under this row, so the two must agree.
    assert "Consensus Protocol:" in latex
    assert "None. This is an in-memory list, not a chain." in latex
    assert "no validator node" in latex
    # "Authenticity ... any citizen, financial institution, or judiciary court"
    # overclaimed a list that dies with the process.
    assert "Nothing here establishes authenticity" in latex


# --------------------------------------------------------------------------- #
# 5. The demo role is not an appointment                                       #
# --------------------------------------------------------------------------- #

def test_district_verifier_is_not_presented_as_a_role_title():
    """
    DISTRICT_VERIFIER stays as an enum because permission logic branches on it.
    What had to go is the idea that signing in makes you a government official.
    """
    offenders = []
    for path in _frontend_sources():
        text = _read(path)
        # Any remaining mention must be inside a key or a nav id, not rendered
        # to a person.
        for match in re.finditer(r"District Verifier", text):
            line = _line_at(text, match.start())
            if "DISTRICT_VERIFIER" in line:
                continue
            offenders.append(f"{path.relative_to(REPO)}: {line.strip()[:70]}")
    assert not offenders, (
        "The demo role is still labelled as a government appointment:\n  "
        + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# 6. Invented municipal instruments, served per building                     #
# --------------------------------------------------------------------------- #

def test_civic_dossier_mints_no_registry_or_utility_records():
    """
    generate_civic_dossier_for_building was documented as generating an
    "exhaustive, authoritative municipal and utility dossier", and it did so for
    every OSM building in the precinct. Every identifier in it came from
    abs(hash(building_code)), which means the following were invented wholesale
    and served as records: an NMMC property tax assessment id with arrears and a
    no-dues certificate, a water connection with a sanctioned daily quota, an
    MSEDCL consumer account, feeder and distribution transformer, a structural
    audit attributed to a "CIDCO Empanelled Structural Consultant & NABL
    Accredited Testing Lab" with a certificate valid to 2031, a fire NOC
    "VALID_TILL_MARCH_2027", and a MahaRERA project id, occupancy certificate,
    named escrow bank branch and statutory clearance of CLEARED or REVOKED.

    A null in these fields now means "no record exists", which is the honest
    answer, so the checks are on the fabricating patterns rather than the words.
    """
    path = BACKEND / "api" / "v1" / "osm.py"

    # The docstring made the strongest claim of all, so check it before stripping.
    assert "authoritative municipal" not in _read(path)

    code = _python_code(path)
    for pattern in (
        'f"NMMC-PT-SEC8-',
        'f"NMMC-WTR-2026-',
        'f"SEW-{water_consumer_no}',
        'f"0286',
        'f"DTR-SEC8-',
        'f"NDC-NMMC-',
        'f"P517000',
        'f"OC-NMMC-2026-',
        '"HDFC Bank Airoli Sector 8 Branch"',
        '"VALID_TILL_MARCH_2027"',
        '"PAID_NO_ARREARS"',
        '"DEFAULT_OVERDUE"',
        '"COMPLIANT_DUAL_RECHARGE_WELLS"',
        '"ECBC-2017 Level 2 Compliant"',
        '"EXPIRED_NOTICE_ISSUED"',
        '"NON_COMPLIANT_SETBACK_DEFECT"',
        '"CERTIFIED_SAFE"',
        '"AUDIT_REQUIRED_DEFECTS_DETECTED"',
        '"REGISTERED_COMPLETED"',
        '"UNAUTHORIZED_NO_RERA"',
        '"REVOKED_NOTICE_ISSUED"',
        # Every field that carried a real institution or registry must be null
        # or absent now, never an f-string.
        '"audit_agency": f',
        '"fire_noc_status": f',
        '"utility_provider": f',
        '"consumer_account_no": f',
        '"rera_project_id": f',
    ):
        assert pattern not in code, f"osm.py still fabricates civic records: {pattern}"

    # And the response has to say what it is.
    assert '"synthetic": True' in code
    assert "Nothing here is a record" in code
    # A null has to mean "no record exists", not "we forgot to look".
    assert '"fire_noc_status": None' in code
    assert '"rera_project_id": None' in code


def test_spatial_pipelines_issue_no_compliance_verdicts():
    """
    Every pipeline in this registry returned a verdict it had not earned. The
    fsi-massing pipeline hardcoded a 1800 m2 built-up area and then declared
    PASS or VIOLATION, adding that basements were "correctly exempted from FSI
    calculation under DCR". solar-air-rights published a
    transferable_development_rights_m3, which asserts a statutory entitlement
    only a planning authority can grant, and reported a fixed 28,450 kWh
    generation with 2.1% shading loss. multiepoch-diff reported a "CRITICAL
    CADASTRE ALERT: Unauthorized 6th floor" against a building nobody had
    surveyed. topology-healer claimed FULLY_COMPLIANT to ISO 19152, a real
    published standard, having touched no geometry: 21 solids validated, 2
    non-manifold edges healed and a passing Euler check were all literals.
    """
    path = BACKEND / "pipelines" / "spatial_pipelines.py"
    code = _python_code(path)

    for verdict in (
        '"FULLY_COMPLIANT"',
        '"UNAUTHORIZED_CHANGE_DETECTED"',
        '"CRITICAL CADASTRE ALERT',
        '"unauthorized_voxels_count"',
        '"unauthorized_floors_detected"',
        '"iso_19152_ladm_compliance"',
        '"transferable_development_rights_m3": air_volume_m3',
        '"total_voxels_analyzed": 142000',
        '"solids_validated_count": 21',
        '"euler_poincare_check": "PASS',
    ):
        assert verdict not in code, f"spatial_pipelines.py still reports {verdict}"

    # No pipeline may answer with a PASS/VIOLATION determination, and none may
    # describe an FSI exemption under a DCR it has not read.
    assert '"status": "PASS" if' not in code
    assert "correctly exempted" not in code
    assert "complying with the maximum permissible" not in code

    # The catalog advertised these as enforcement tools. "NBC 2016 Enforced" and
    # an "FSI Compliance" badge are claims, not labels.
    for badge in ('"NBC 2016 Enforced"', '"FSI Compliance"', '"SoI Survey Concordance"'):
        assert badge not in code, f"catalog still badges a pipeline as {badge}"

    # A caller-supplied limit is an assumption, and the entry has to say so.
    assert "regulatory_ref_note" in code


def test_pipeline_catalog_states_it_is_not_an_authority():
    """
    The catalog is the first thing a user reads, so it is the first place that
    has to say what the menu is not: these pipelines do not read a regulation,
    load a sanctioned plan, validate against a standard or report to anybody.
    """
    api = _read(BACKEND / "api" / "v1" / "pipelines_api.py")
    assert "scope_note" in api, "the pipeline catalog endpoint states no scope limit"
    assert "compliance" in api.lower()


def test_integrity_summary_is_not_a_remembered_constant():
    """
    The duplicate-sweep summary read "All 12 ULPINs structured and unique" while
    the endpoint above it reported whatever the dataset actually held, and it
    told the reader the reconciliation items were "flagged for department
    follow-up", as though a department had been notified.
    """
    code = _python_code(BACKEND / "api" / "v1" / "integrity.py")
    assert "All 12 ULPINs" not in code, "the 12-ULPIN figure is hardcoded again"
    assert "department follow-up" not in code, (
        "the summary still implies a department was notified"
    )
    # The count has to come from the data that was actually checked.
    assert "len(ulpins)" in code
    assert "len(ids)" in code


# --------------------------------------------------------------------------- #
# 7. Real institutions as parties to records that never happened              #
# --------------------------------------------------------------------------- #

def test_synthetic_chain_names_no_real_institution_as_a_party():
    """
    _initialize_synthetic_cadastral_chain built a 10-block chain in which the
    parties were a real government, a real registration office, the Survey of
    India, an NMMC town planning department, a sub-registrar of Thane II, the
    State Bank of India, the Maharashtra Remote Sensing Application Centre, an
    NMMC ward flying squad and the District Land Grievance Tribunal, plus a
    fabricated DGCA drone registration "DGCA-IND-94".

    Naming a real bank, a real satellite agency, a real municipal enforcement
    squad or a real tribunal as a counterparty to invented transactions is the
    most serious kind of overclaim here: it implies those bodies participated in
    and stand behind records they have never seen. Each is now a plain demo
    label, and the fake drone registration is gone.
    """
    code = _python_code(BACKEND / "core" / "blockchain.py")
    for real_party in (
        '"Government of Maharashtra"',
        '"Inspector General of Registration"',
        '"Talathi Office Airoli"',
        '"Survey of India Team 4"',
        '"NMMC Town Planning Dept"',
        '"Sub-Registrar Thane-II"',
        '"State Bank of India (Airoli Branch)"',
        '"Maharashtra Remote Sensing Application Centre (MRSAC)"',
        '"DGCA-IND-94"',
        '"NMMC Ward D Flying Squad"',
        '"District Land Grievance Tribunal"',
        '"Sunita Patil"',
        '"Rajesh M. Sharma"',
    ):
        assert real_party not in code, f"blockchain.py still names {real_party} as a party"

    # The FSI "smart contract" cited a section of a real regulation and returned
    # a penalty action. It is now a ratio comparison with no citation and no
    # enforcement.
    for claim in (
        '"UDCPR 2020 Sec 3.4.1"',
        '"APPROVED" if passed else "REJECTED_BREACH_DETECTED"',
        '"TRIGGER_PENALTY_NOTICE"',
    ):
        assert claim not in code, f"blockchain.py still asserts {claim}"


def test_smart_contract_registry_does_not_point_at_undeployed_contracts():
    """
    self.smart_contracts used to hold hex-looking identifiers and the string
    "public" for entries, implying contracts published on a network. They now
    name the local function, or say plainly that nothing is implemented.
    """
    code = _python_code(BACKEND / "core" / "blockchain.py")
    for lie in ('"public"', '"deployed"', '0x7F18', '0x'):
        assert lie not in code, f"blockchain.py still points at a contract as {lie}"


# --------------------------------------------------------------------------- #
# 8. The landing page's own description of itself                             #
# --------------------------------------------------------------------------- #

def test_how_it_works_does_not_claim_official_records():
    """
    The "How Bhu-Drishti 3D Works" block described the pipeline as turning "raw
    geospatial evidence into verified vertical property governance", called the
    parent ULPIN "Official", said 12 PostGIS rules "evaluate inter-unit
    disjointness, FSI limits, and detect subterranean utility clashes", titled a
    step "05 Governed Verification", and closed with "06 Verifiable Public
    Proof — Approved records are anchored to a SHA-256 audit chain; citizens scan
    QR for DPDP-compliant verification".

    Each clause was a claim the code does not support. The identifiers are
    generated here, the pipelines issue no compliance verdict, nothing is
    approved, the chain is in-process and unanchored, and DPDP compliance is a
    legal determination nobody has made.
    """
    i18n = _read(REPO / "frontend" / "src" / "i18n" / "translations.ts")
    for claim in (
        "vertical property governance",
        "Official 14-character parent ULPIN",
        "anchored immutably",
        "12 PostGIS/SFCGAL rules",
        "05 Governed Verification",
        "06 Verifiable Public Proof",
        "Approved records are anchored",
        "DPDP-compliant verification",
    ):
        assert claim not in i18n, f"translations.ts still claims: {claim}"


def test_page_title_does_not_call_the_platform_governed():
    """
    The browser tab title read "Governed 3D Cadastral & Vertical Property
    Platform". It is the single most visible string in the app, it is what ends
    up in a screenshot and in a judge's browser history, and "Governed" asserts
    a governance relationship that does not exist.
    """
    index = _read(REPO / "frontend" / "index.html")
    assert "Governed 3D Cadastral" not in index, (
        "the page title still describes the platform as governed"
    )
    assert "Prototype" in index, "the page title should say what this is"


def test_api_description_does_not_call_the_backend_governed():
    """
    The FastAPI description served at / read "Governed 3D Cadastral & Vertical
    Property Intelligence Platform" and promised "public QR proofs". That page is
    reachable by anyone who can reach the API, so on an instance with the port
    published it is the first thing an unauthenticated visitor sees.
    """
    main = _read(BACKEND / "main.py")
    assert "Governed 3D Cadastral" not in main
    assert "not a government or regulatory system" in main


def test_ask_map_focus_point_is_derived_not_hardcoded():
    """
    ask_map._hero_point() returned a literal [160.0, 152.5, 9.0]. Those numbers
    are the centroid of the synthetic footprint and half the synthetic height, so
    they were correct by coincidence at the moment they were written: move the
    footprint in synthetic_generator and the camera would keep pointing at the
    old spot while the answer text still described the new structure.

    It must now be computed from the dataset's own footprint_geojson.
    """
    from app.api.v1 import ask_map

    # Strip docstrings and comments first. The docstring of _hero_point() quotes
    # the old literal to explain what changed, so a raw substring search fails
    # on the very fix it is meant to police -- the same trap as the earlier
    # 0x00-hydrate test.
    source = _strip_docstrings_and_comments(inspect.getsource(ask_map))
    assert "[160.0, 152.5" not in source, "focus point is still a hardcoded literal"
    assert "[160.0, 152.5, 19.5]" not in source

    # And it has to agree with the footprint the scene actually extrudes.
    dataset = ask_map.load_demo_dataset()
    if dataset.get("demo_disabled"):
        pytest.skip("demo dataset disabled; nothing to compare against")

    point = ask_map._hero_point(dataset)
    if point is None:
        pytest.skip("dataset carries no hero_structure footprint")

    from app.scene.scene_architect import center_of

    ring = ask_map._footprint_ring(dataset)
    cx, cy = center_of(ring)
    assert point[0] == pytest.approx(cx)
    assert point[1] == pytest.approx(cy)
    assert point[2] == pytest.approx(
        float(dataset["hero_structure"]["height_m"]) / 2.0, abs=0.01
    )


def test_ask_map_reports_no_match_when_store_is_empty(monkeypatch):
    """
    The refusal path has to survive a store with no rows in it. This is the
    real-data-only configuration the project is trying to reach
    (ENABLE_DEMO_MODE=0), so every category must degrade to an honest "nothing
    matched" rather than falling back to a canned hit.

    An earlier version of this test just called the router and asserted the
    result was empty, which passed for the wrong reason: the populated demo
    store returns real rows, so the assertion could only ever hold if the router
    were broken. Empty the dataset explicitly.
    """
    from app.api.v1 import ask_map

    empty = {"demo_disabled": False}
    monkeypatch.setattr(ask_map, "_CASES_DB", [])
    monkeypatch.setattr(ask_map, "load_demo_dataset", lambda: empty)

    probes = [
        ("is there an underground clash", "UNDERGROUND_CLASH_SEARCH"),
        ("show me a mortgage on flat 201", "RIGHTS_SEARCH"),
        ("any unauthorized change to the building", "CHANGE_SEARCH"),
        ("how many are pending review", "VERIFICATION_STATUS"),
        ("find the property at Airoli", "PROPERTY_SEARCH"),
    ]
    for text, expected_category in probes:
        parsed = ask_map.parse_query_deterministically(text, empty)
        assert parsed["category"] == expected_category, text
        assert parsed["matched_ids"] == [], f"{text} invented {parsed['matched_ids']}"
        assert parsed["filter"].get("matched") is False, text
        assert parsed["highlight"]["object_ids"] == [], text
        # No focus point either: there is nothing to point a camera at.
        assert parsed["highlight"]["focus_point"] is None, text
        assert "No record in the demo dataset matches" in parsed["explanation"], text


def test_ask_map_routes_all_five_intent_categories():
    """
    Guards the allowlist itself. An unknown question has to land in
    PROPERTY_SEARCH with an empty match set rather than being guessed at.
    """
    from app.api.v1 import ask_map

    expected = {
        "clash": "UNDERGROUND_CLASH_SEARCH",
        "mortgage": "RIGHTS_SEARCH",
        "unauthorized change": "CHANGE_SEARCH",
        "pending review": "VERIFICATION_STATUS",
        "zzzz nonsense token": "PROPERTY_SEARCH",
    }
    for phrase, category in expected.items():
        parsed = ask_map.parse_query_deterministically(phrase)
        assert parsed["category"] == category, f"{phrase!r} routed to {parsed['category']}"


def test_ask_map_coverage_queries_do_not_imply_defect():
    """
    "which buildings have no height" is answerable from the dataset and useful --
    it is the same shape of question as the one that was answered with a
    fabricated mortgage. The answer must report a gap in the data without
    characterising the building, because a missing OSM height says nothing about
    whether anything is wrong with the real structure.
    """
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    if dataset.get("demo_disabled"):
        pytest.skip("demo dataset disabled")

    parsed = ask_map.parse_query_deterministically("show buildings with no height data", dataset)
    assert parsed["category"] == "COVERAGE_QUERY", parsed["category"]
    joined = " ".join(parsed["limitations"]).lower()
    assert "not evidence" in joined
    for banned in ("illegal", "violation", "unauthorised", "unauthorized", "non-compliant"):
        assert banned not in " ".join(parsed["limitations"]).lower()


def test_ask_map_counts_are_not_fabricated():
    """
    The count categories have to report a number the dataset can actually
    reproduce, and a count answer must not claim to describe the real world.
    """
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    if dataset.get("demo_disabled"):
        pytest.skip("demo dataset disabled")

    buildings = len(dataset.get("precinct_buildings", []))
    units = len(dataset.get("units", [])) + len(dataset.get("all_precinct_units", []))

    parsed = ask_map.parse_query_deterministically("how many buildings", dataset)
    assert parsed["category"] == "COUNT_QUERY"
    assert f"{buildings} buildings" in parsed["explanation"], parsed["explanation"]

    parsed = ask_map.parse_query_deterministically("how many units", dataset)
    assert parsed["category"] == "COUNT_QUERY"
    assert f"{units} units" in parsed["explanation"], parsed["explanation"]

    for phrase in ("how many buildings", "how many units"):
        parsed = ask_map.parse_query_deterministically(phrase, dataset)
        assert "synthetic" in " ".join(parsed["limitations"]).lower()
