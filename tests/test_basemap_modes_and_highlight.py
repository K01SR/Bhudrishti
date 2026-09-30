"""
The basemap light/dark + label toggle, and the highlight pointer on the 2D maps.

Three things here were previously absent and are easy to regress silently,
because each one fails by rendering something plausible rather than by
throwing:

1. Neither map view could change its basemap. Both styles were hardcoded --
   `dark_all` in the open-twin studio, `light_all` in the cadastral atlas -- so
   a user stuck on a bright room with a dark map, or vice versa, had no way out.
2. Ask-The-Map set highlight state that only the 3D view acted on. Both 2D maps
   ignored it entirely, and the toast said "Highlight applied to the 3D view"
   while the user was left looking at an unchanged map.
3. The query's focus point is in the 3D studio's local scene coordinates, not
   longitude and latitude. Handing it straight to a 2D map's flyTo would send
   the camera to longitude 160 east -- the middle of the Pacific -- so the
   conversion is asserted here rather than left to be discovered at runtime.
"""

import pathlib
import re

import pytest

from frontend_source import executable_source

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "frontend" / "src"

OPEN_TWIN = SRC / "components" / "openstudio" / "OpenTwinStudio.tsx"
CADASTRE = SRC / "components" / "map2d" / "MapLibreCadastreMap.tsx"
POINTER = SRC / "components" / "map2d" / "HighlightPointer.tsx"
TOGGLE = SRC / "components" / "map2d" / "BasemapModeToggle.tsx"
CARTO = SRC / "services" / "cartoBasemap.ts"
CONTEXT = SRC / "context" / "AppContext.tsx"
MODAL = SRC / "components" / "workspace" / "AskTheMapModal.tsx"

MAP_VIEWS = [OPEN_TWIN, CADASTRE]


def test_both_views_hardcoded_a_single_basemap_before():
    """
    Guard the premise, not the feature.

    If someone later makes these views read their basemap from somewhere better
    -- a server-driven style, say -- the per-view assertions below stop being
    the whole story, and this failure is the signal to re-read them rather than
    delete them.
    """
    for path in MAP_VIEWS:
        text = path.read_text(encoding="utf-8")
        # No bare style name may be baked into a tile URL again.
        for style in ("dark_all", "light_all", "dark_nolabels", "light_nolabels"):
            assert f".cartocdn.com/{style}/" not in text, (
                f"{path.name} hardcodes the CARTO style {style} into a tile URL, "
                "so the light/dark and label toggles cannot change it"
            )


@pytest.mark.parametrize("path", MAP_VIEWS, ids=lambda p: p.name)
def test_view_builds_tiles_from_the_preference(path: pathlib.Path) -> None:
    text = executable_source(path)
    assert "basemapStyleFor(" in text, (
        f"{path.name} does not derive its basemap style from the user's "
        "theme/label preference"
    )
    assert "basemapTileUrl(" in text


@pytest.mark.parametrize("path", MAP_VIEWS, ids=lambda p: p.name)
def test_view_swaps_tiles_without_rebuilding_the_style(path: pathlib.Path) -> None:
    """
    The swap must go through setTiles, not setStyle.

    setStyle re-runs style load: it drops every layer added after load (the
    national vector parcels, the Airoli demo geometry, the subgrade fill in the
    atlas; the terrain and imagery sources in the studio) and resets the camera
    the user positioned. The symptom would be a basemap toggle that quietly
    empties the map.
    """
    text = executable_source(path)
    assert ".setTiles(" in text, f"{path.name} does not swap tiles in place"
    assert "map.setStyle(" not in text, (
        f"{path.name} calls setStyle, which would drop its post-load layers and "
        "camera when the basemap is toggled"
    )


@pytest.mark.parametrize("path", MAP_VIEWS, ids=lambda p: p.name)
def test_view_renders_the_toggle(path: pathlib.Path) -> None:
    text = executable_source(path)
    assert "BasemapModeToggle" in text, f"{path.name} never renders the basemap toggle"
    assert "loadBasemapPref(" in text and "saveBasemapPref(" in text, (
        f"{path.name} does not persist the choice, so it resets on every reload"
    )


def test_each_view_persists_under_its_own_key() -> None:
    """
    The two views must not share a preference key.

    They have opposite defaults -- the studio is dark-first because its
    extrusions and utility overlay are tuned for a dark ground, the atlas is
    light-first because its parcel fills are legible on white. A shared key
    would make flipping one map silently restyle the other.
    """
    keys = {}
    for path in MAP_VIEWS:
        text = path.read_text(encoding="utf-8")
        found = re.findall(r"loadBasemapPref\(\s*'([^']+)'", text)
        assert len(found) == 1, f"{path.name} should load exactly one basemap pref key"
        keys[path.name] = found[0]
    assert len(set(keys.values())) == 2, f"both views share the pref key {keys}"


def test_defaults_match_each_views_design() -> None:
    """Studio dark-first, atlas light-first."""
    studio = OPEN_TWIN.read_text(encoding="utf-8")
    atlas = CADASTRE.read_text(encoding="utf-8")
    assert re.search(r"loadBasemapPref\('open_twin',\s*\{\s*theme:\s*'dark'", studio), (
        "the open-twin studio is built dark and should default to dark"
    )
    assert re.search(r"loadBasemapPref\('cadastre',\s*\{\s*theme:\s*'light'", atlas), (
        "the cadastral atlas parcel fills are tuned for a light basemap"
    )


def test_toggle_offers_both_themes_and_a_label_switch() -> None:
    text = executable_source(TOGGLE)
    assert "aria-pressed" in text, "the toggle needs pressed state to be announceable"
    for label in ("Dark basemap", "Light basemap"):
        assert label in text, f"the toggle is missing its {label} control"
    assert "labels: !pref.labels" in text, "the toggle cannot switch labels off"


def test_all_four_carto_variants_are_usable() -> None:
    """
    `<theme>_nolabels` is a real CARTO style, not a guess.

    The obvious way to hide labels is to stack `only_labels` over `all`, which
    looks identical but doubles the tile request count -- and this project has
    a 5M/month CARTO allowance. Verified present on the rastertiles endpoint for
    both themes, so the nolabels variants are the cheap correct answer.
    """
    text = CARTO.read_text(encoding="utf-8")
    for style in ("dark_all", "dark_nolabels", "light_all", "light_nolabels"):
        assert style in text, f"{style} is not offered"


def test_key_still_attaches_to_every_generated_tile() -> None:
    """
    The tile builder must go through cartoTile, or a theme change silently
    drops the key and returns the placeholder.
    """
    text = CARTO.read_text(encoding="utf-8")
    assert "cartoTile(" in text
    assert "VITE_CARTO_API_KEY" in text


# ---------------------------------------------------------------- pointer --

def test_highlight_carries_a_focus_point() -> None:
    """
    Without a focus point the 2D pointer has nothing to fly to, and the
    highlight state reverts to being 3D-only.
    """
    text = executable_source(CONTEXT)
    assert "focusPoint" in text, "HighlightState carries no focus point"
    assert "color" in text, "HighlightState carries no highlight colour"


def test_modal_forwards_the_focus_point_and_colour() -> None:
    text = executable_source(MODAL)
    assert "focus_point" in text, "the query's focus_point is dropped on the floor"
    assert "focusPoint:" in text, "focus_point is not put on the highlight state"
    assert "highlight_color" in text, "the backend's highlight colour is discarded"


def test_modal_offers_both_2d_destinations() -> None:
    """
    The old button navigated to /app/map with no view parameter, which lands on
    whichever view is the default and places nothing.
    """
    text = executable_source(MODAL)
    assert "/app/map?view=cadastre" in text, "no jump to the 2D cadastral view"
    assert "/app/map?view=open_twin" in text, "no jump to the 3D open-twin view"


@pytest.mark.parametrize("path", MAP_VIEWS, ids=lambda p: p.name)
def test_view_renders_the_pointer(path: pathlib.Path) -> None:
    text = executable_source(path)
    assert "HighlightPointer" in text, f"{path.name} ignores the highlight entirely"


def test_pointer_converts_scene_coordinates_rather_than_using_them_raw() -> None:
    """
    The load-bearing assertion of this file.

    focus_point comes back as scene coordinates like [160, 152.5, -3.2]. Used
    as [lng, lat] that is longitude 160 east, latitude 152.5 north -- which
    clamps to the top of the map, off the coast of the Arctic. So the pointer
    must convert through the same local-to-geo transform the atlas uses for its
    demo geometry.
    """
    text = executable_source(POINTER)
    assert "localToGeo" in text
    # The anchor and scale must match MapLibreCadastreMap's, or the dot lands
    # somewhere other than the building the query is about.
    m = re.search(r"AIROLI_CENTER[^=]*=\s*\[([-\d.]+),\s*([-\d.]+)\]", text)
    assert m, "the pointer does not declare a geo anchor"
    assert float(m.group(1)) == 72.9984 and float(m.group(2)) == 19.1557, (
        "the pointer's anchor has drifted from Airoli; the dot would land away "
        "from the building the query is about"
    )
    assert "0.000009" in text, "the pointer's scene-to-degree scale has drifted from the atlas"
    # North is scene -y, hence the subtraction.
    assert re.search(r"AIROLI_CENTER\[1\]\s*-\s*\(", text), (
        "latitude must subtract the scene y offset: scene y grows south"
    )


def test_anchor_matches_the_cadastral_atlas() -> None:
    """The two must not drift apart; the dot is compared against demo geometry."""
    atlas = CADASTRE.read_text(encoding="utf-8")
    assert "const AIROLI_CENTER: [number, number] = [72.9984, 19.1557];" in atlas
    assert "const SCALE = 0.000009;" in atlas


def test_pointer_drops_the_scene_z() -> None:
    """
    The third component is a depth or floor level and has no meaning on a 2D
    map. Carrying it into the transform would corrupt the latitude, so only x/y
    may be used.
    """
    text = executable_source(POINTER)
    fn = text.split("export function localToGeo")[1]
    body = fn.split("}")[0]
    assert "focus" not in body, "localToGeo must take only the x/y pair"
    # Matched loosely: executable_source() strips comments, so the assertion
    # cannot depend on how the expression happens to be wrapped.
    modal = executable_source(MODAL)
    assert re.search(r"focusPoint:[^;]*?Number\(fp\[0\]\)[^;]*?Number\(fp\[1\]\)", modal), (
        "the modal must pass exactly the x/y pair"
    )
    assert "Number(fp[2])" not in modal, "the scene z must not be carried into a 2D map"


def test_pointer_is_removed_before_a_new_one_is_placed() -> None:
    """
    Without the removal, running a second query stacks a second dot and the
    older one no longer means anything.
    """
    text = executable_source(POINTER)
    assert "markerRef.current?.remove()" in text


def test_pointer_needs_a_real_map_instance() -> None:
    """
    The map is built in an effect, so a ref read during render is null on the
    first pass. In the studio this is mirrored into state; in the atlas the
    render is gated on mapLoaded. A ref passed straight to the child would leave
    it permanently inactive with no error.
    """
    studio = executable_source(OPEN_TWIN)
    assert "map={mapInstance}" in studio, (
        "the studio passes mapRef.current, which is null on first render and "
        "never re-renders, so the pointer would never appear"
    )
    atlas = executable_source(CADASTRE)
    assert re.search(r"mapLoaded\s*&&\s*<HighlightPointer", atlas), (
        "the atlas pointer must be gated on mapLoaded for the same reason"
    )
