"""
Guards the provenance claims the open-twin layer panel makes.

Every source label in that panel is a statement to the user about where a layer's
geometry came from. Three of them were false, and false in the specific way that
is hardest to notice: the layer looked real, the toggle looked live, and the
credit named a real institution.

    'Municipal GPR Survey'          two hardcoded line segments; no scan
    'State Cadastre API'            nothing fetched
    'Civic Intelligence API'        nothing fetched
    'OSM Place Hierarchy'           fetched, result discarded, nothing drawn

A ground-penetrating-radar survey is measured subsurface data from real
instrumentation, so that label told the user the app had been to the ground. The
others named data sources that were never called.

These are text gates rather than a Playwright run because the failure they exist
to catch is a string regression, and because a browser gate that only runs
occasionally is a gate that quietly stops running. The assertions are on
executable source, so a match inside a comment does not satisfy them and cannot
disguise itself as one.
"""

import pathlib

import pytest

from frontend_source import executable_source

OPEN_TWIN_FILES = (
    "components/openstudio/LeftLayerPanel.tsx",
    "components/openstudio/OpenTwinStudio.tsx",
    "services/prototypeUtilities.ts",
)


def _open_twin_source() -> str:
    root = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"
    chunks = []
    for rel in OPEN_TWIN_FILES:
        path = root / rel
        assert path.exists(), f"open-twin source missing, gate is vacuous: {rel}"
        chunks.append(executable_source(path))
    return "\n".join(chunks)


@pytest.fixture(scope="module")
def source() -> str:
    return _open_twin_source()


@pytest.mark.parametrize(
    "false_claim",
    [
        "Municipal GPR Survey",
        "State Cadastre API",
        "Civic Intelligence API",
        "OSM Place Hierarchy",
        "State Directorate",
    ],
)
def test_false_provenance_claims_are_gone(source: str, false_claim: str) -> None:
    """No source label may name data the view does not actually receive."""
    assert false_claim not in source, (
        f"{false_claim!r} is presented as a layer source in the open-twin panel but "
        "no data from it is fetched or drawn. Either wire the source up or label "
        "the layer as not connected."
    )


def test_prototype_network_declares_itself_non_authoritative(source: str) -> None:
    """The derived utility network must carry its caveat in code, not only in UI copy."""
    assert "PROTOTYPE-DERIVED" in source
    assert "authoritative: false" in source
    assert "UtilitiesNotAuthoritative" in source


def test_unconnected_layers_are_marked(source: str) -> None:
    """
    Toggles with no data behind them must be inert rather than switchable.

    Two layers still have no source in this view and must keep saying so:
    `landParcels` (no cadastral feed is connected) and `officialCadastre`
    (there is no government 3D-twin pilot behind this). `civicAmenities` and
    `localityLabels` used to be listed here too and no longer are, because both
    are now fetched from Overpass and drawn in this view; the gate keeps the
    remaining pair honest rather than being satisfied by a blanket string.
    """
    assert "Not connected in this view" in source
    assert "connected: false" in source
    # The two that genuinely have nothing behind them, and only those two.
    assert source.count("connected: false") == 2


def test_map_attribution_survives() -> None:
    """
    The OSM/CARTO credit is an ODbL condition, not decoration.

    It is easy to tidy a map by deleting the credit pill. The basemap is
    OpenStreetMap data served by CARTO and the building geometry is OSM data via
    Overpass, so removing it is a licence breach. The styling is allowed to
    change; the string is not.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"
    studio = executable_source(root / "components/openstudio/OpenTwinStudio.tsx")
    assert "OpenStreetMap contributors" in studio
    assert "CARTO" in studio


def test_panel_never_attributes_geometry_to_a_gpr_survey() -> None:
    """
    No layer in the panel may name GPR as the origin of its geometry.

    Deliberately scoped to the panel rather than the whole frontend. An earlier
    version of this gate banned the token "GPR" everywhere, which failed on
    prototypeUtilities.ts -- because the caveat shown on screen says "No
    leak-detection, GPR or municipal asset record was consulted". Banning the
    word punishes the honest disclaimer that denies the survey, and would have
    pushed someone to delete the caveat to make the gate green. The panel is
    where source labels live, so that is where the word is forbidden.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"
    panel = executable_source(root / "components/openstudio/LeftLayerPanel.tsx")
    assert "GPR" not in panel, (
        "A layer source in the panel names a GPR survey. No scan was performed."
    )


def test_disclaimer_still_denies_the_survey() -> None:
    """
    The notice must keep saying the survey did not happen.

    This is the positive counterpart to the gate above, and it exists because a
    future cleanup that strips the word 'GPR' from the panel could equally strip
    the sentence that denies the survey. Both halves matter: the panel must not
    claim a scan, and the caveat must not quietly go away.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"
    utils = executable_source(root / "services/prototypeUtilities.ts")
    assert "not authoritative utility data" in utils
    assert "No leak-detection, GPR or municipal asset record was consulted" in utils
