"""
Keeps the CARTO basemap key out of version control, and the credit in.

The key is a credential in the ordinary sense -- it identifies an account and
CARTO asks that it not be shared -- but it is also necessarily public, because
Vite inlines it into the client bundle where any visitor can read it. That is
why raster basemap keys are published rather than treated as secrets, and why
the real control is a domain restriction in CARTO's dashboard.

Both halves matter and are easy to conflate:

  * Public does not mean committable. A key in a tracked file is in the history
    forever, is shared with everyone who clones, and is not covered by the
    "raster basemap keys are publishable" reasoning at all.
  * The OSM and CARTO attribution is an ODbL and CARTO licence condition that
    survives the key being present. Adding a key is not a licence to drop the
    credit, and CARTO's own key email asks for the attribution to stay visible.

The leak check is a pattern rather than a stored copy of the key on purpose. A
gate that embedded the real key would itself be a committed copy of the key.
"""

import pathlib
import re

import pytest

from frontend_source import executable_source

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# CARTO basemap keys look like cb1_<account>_<hash>. Matched generically so this
# file never contains a usable key of its own.
CARTO_KEY_RE = re.compile(r"cb1_[A-Za-z0-9_]{8,}")

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    "build",
    ".artifacts",
}

TEXT_SUFFIXES = {
    ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".yml", ".yaml",
    ".py", ".css", ".html", ".txt", ".example", ".conf", ".sh", ".env",
}


def _tracked_candidates() -> list[pathlib.Path]:
    """Every file git would consider, minus the ignored directories."""
    found: list[pathlib.Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        found.append(path)
    return found


def test_no_carto_key_in_any_non_ignored_file() -> None:
    """
    No file outside the gitignored .env may contain a CARTO key.

    frontend/.env is the intended home and is gitignored, so it is expected to
    hold one; everything else is scanned. The suffix filter keeps binaries from
    producing false positives while still covering every file type a key could
    plausibly be pasted into.
    """
    offenders: list[str] = []
    for path in _tracked_candidates():
        if path.name == ".env":
            # The gitignored local env is where the key belongs.
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in {".env", ".env.example"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in CARTO_KEY_RE.findall(text):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {match[:12]}...")

    assert not offenders, (
        "A CARTO basemap key appears in a file that is not the gitignored "
        f"frontend/.env. Remove it, rotate the key in the CARTO dashboard, and "
        f"rewrite the history if it was already committed: {offenders}"
    )


def test_env_example_documents_the_key_without_containing_one() -> None:
    """
    The example must tell the next person a key is needed, without holding it.

    A missing key produces a blank basemap and no error, so an example file
    that implies setup is complete without a key is how this stays broken.
    """
    example = (REPO_ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")
    assert "VITE_CARTO_API_KEY" in example
    assert "carto.com/basemaps/apikey" in example
    # The placeholder form is fine; a real key is not.
    assert not CARTO_KEY_RE.search(example), "the example file must not contain a usable key"


def test_carto_tile_helper_is_used_by_both_basemaps() -> None:
    """
    Both CARTO basemaps must go through the key-appending helper.

    Easy to add a third CARTO source later and forget the key, which produces
    the same silent blank tile rather than an error.

    The style name now comes from basemapTileUrl rather than being written out
    in each view, so this checks that each view calls the builder -- which is
    where the key is attached -- rather than that a hostname appears literally
    in the component. The host is asserted in cartoBasemap.ts instead, which
    is the one place it is now written down.
    """
    src = REPO_ROOT / "frontend" / "src"
    for rel in (
        "components/openstudio/OpenTwinStudio.tsx",
        "components/map2d/MapLibreCadastreMap.tsx",
    ):
        text = executable_source(src / rel)
        assert "basemapTileUrl(" in text, (
            f"{rel} does not build its CARTO tiles through basemapTileUrl(), so "
            "they will not carry VITE_CARTO_API_KEY and will come back as the "
            "keyless placeholder"
        )
        # And it must not reach for the OSM tile host or a bare CARTO style.
        assert "tile.openstreetmap.org" not in text, (
            f"{rel} is using the public OSM tile host directly"
        )

    builder = (src / "services" / "cartoBasemap.ts").read_text(encoding="utf-8")
    assert "basemaps.cartocdn.com" in builder
    assert "rastertiles/" in builder, "the tile builder no longer points at CARTO's raster path"
    assert "cartoTile(" in builder, "the tile builder no longer attaches the key"


def test_attribution_kept_alongside_the_key() -> None:
    """The OSM/CARTO credit must survive the key being added."""
    src = REPO_ROOT / "frontend" / "src"
    for rel in (
        "components/openstudio/OpenTwinStudio.tsx",
        "components/map2d/MapLibreCadastreMap.tsx",
    ):
        text = executable_source(src / rel)
        assert "OpenStreetMap contributors" in text, f"{rel} dropped the OSM credit"
        assert "CARTO" in text, f"{rel} dropped the CARTO credit"


def test_keyless_basemap_would_be_a_placeholder() -> None:
    """
    Pin the failure mode, so nobody 'simplifies' the key away.

    Uses urllib from the standard library rather than requests, so the check
    runs wherever the suite runs instead of skipping on a missing optional
    dependency. Skips only when the network is genuinely unavailable.
    """
    import urllib.request

    def fetch(z: int, x: int, y: int) -> bytes:
        url = f"https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
        with urllib.request.urlopen(url, timeout=20) as resp:
            assert resp.status == 200
            return resp.read()

    try:
        first = fetch(13, 5757, 3651)
        second = fetch(14, 11514, 7303)
    except Exception as exc:  # pragma: no cover - network dependent
        pytest.skip(f"CARTO unreachable: {exc}")

    assert first == second, (
        "Keyless CARTO raster tiles are byte-identical across coordinates, which "
        "is the placeholder. If this now differs, CARTO has made raster basemaps "
        "keyless again and VITE_CARTO_API_KEY can be dropped from the tile URLs."
    )
