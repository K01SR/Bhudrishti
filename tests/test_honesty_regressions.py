"""Regressions for the four honesty/correctness defects found in the audit.

These are not style preferences. Each test here pins down a specific way the
application previously asserted something the underlying data does not
support, so that reintroducing the assertion fails a test instead of passing
review.

1. The LiDAR inspector appended generated points to the uploaded LAS - four
   synthetic floor slabs, a fabricated "Epoch-2" band at 18.0-21.5 m carrying a
   magic intensity of 245 and return_number 2, and a copy of every precinct
   building's points. The frontend then reported the fabricated band as a
   measured "unauthorized 6th floor". The capture is single-pass and its own
   ground truth stops at L04/18.0 m, so no vertical-change claim was available.
2. The 3D viewer placed unit geometry by `unit_number % 4`, inventing four
   repeated blocks regardless of the real footprint.
3. Pipeline `method` strings described clustering that the code never performed.
4. A failed point-cloud ingest answered HTTP 200 with an error body.
"""
import json
import re
import struct
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAS_REL = Path("data/sample_pointcloud/airoli_s8_hero.las")
METADATA_REL = Path("data/sample_pointcloud/metadata.json")


def _las_header(path: Path) -> dict:
    """Reads the LAS 1.2 public header without needing laspy.

    Independent of the loader under test: if both this and the endpoint agree
    with metadata.json, the loader is not inventing points.
    """
    b = path.read_bytes()
    assert b[:4] == b"LASF", "not a LAS file"
    point_format = b[104]
    record_len = struct.unpack_from("<H", b, 105)[0]
    num_points = struct.unpack_from("<I", b, 107)[0]
    header_size = struct.unpack_from("<H", b, 94)[0]
    point_offset = struct.unpack_from("<I", b, 96)[0]
    return {
        "version": (b[24], b[25]),
        "point_format": point_format,
        "record_len": record_len,
        "num_points": num_points,
        "header_size": header_size,
        "point_offset": point_offset,
        "file_size": len(b),
        "min_z": struct.unpack_from("<d", b, 219)[0],
        "max_z": struct.unpack_from("<d", b, 211)[0],
    }


def _container_las() -> Path:
    """The LAS as the container sees it, falling back to the repo copy."""
    for candidate in (Path("/app/data/sample_pointcloud/airoli_s8_hero.las"), REPO / LAS_REL):
        if candidate.exists():
            return candidate
    pytest.skip("sample point cloud not present in this environment")


def _strip_comments(src: str) -> str:
    """Removes line, block and JSX comments so prose about a bug cannot
    satisfy an assertion that the bug is absent."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    src = src.replace("{/*", " ").replace("*/}", " ")
    return src


def _strip_py_comments(src: str) -> str:
    """Drops Python comments by parsing to an AST and unparsing.

    Comments never survive an AST round trip, so prose describing a bug cannot
    satisfy an assertion that the bug is absent. Working on the parsed tree also
    keeps the slice well-formed, which tokenize on a mid-function fragment is not.
    """
    import ast

    return ast.unparse(ast.parse(src))


def _pointcloud_failure_handler() -> str:
    """The `except` handler of the point-cloud route, as parsed code.

    Bounded to the handler itself, so the success response built further down the
    function cannot be mistaken for part of the failure path.
    """
    import ast

    tree = ast.parse(_ingest_source())
    route = next(
        fn
        for fn in ast.walk(tree)
        if isinstance(fn, ast.AsyncFunctionDef)
        and any(
            isinstance(d, ast.Call)
            and getattr(d.func, "attr", "") == "post"
            and d.args
            and getattr(d.args[0], "value", "") == "/point-cloud"
            for d in fn.decorator_list
        )
    )
    handlers = [h for h in ast.walk(route) if isinstance(h, ast.ExceptHandler)]
    assert handlers, "point-cloud route has no exception handler"
    return "\n".join(ast.unparse(h) for h in handlers)


def _method_strings(src: str) -> list:
    """Every `method` string in a pipeline module.

    Handles parenthesised implicit concatenation and f-string prefixes, so a
    wrapped or interpolated value is read as one string rather than reported as
    missing.
    """
    found = []
    for match in re.finditer(r'"method"\s*:\s*', src):
        rest = src[match.end():]
        literal = re.match(r'\(\s*((?:[fru]*"[^"]*"\s*)+)\)', rest)
        if literal:
            found.append("".join(re.findall(r'"([^"]*)"', literal.group(1))))
            continue
        simple = re.match(r'[fru]*"([^"]*)"', rest)
        if simple:
            found.append(simple.group(1))
    return found


# ---------------------------------------------------------------------------
# Fix 1 - the inspector must serve the uploaded file, unmodified
# ---------------------------------------------------------------------------


def test_lidar_loader_does_not_synthesise_points():
    """No generated geometry in the loader that builds the point arrays."""
    src = (REPO / "backend/app/api/v1/lidar_inspect.py").read_text()
    loader = src[src.index("def _load_las"):]

    # The loader used to seed an RNG and build arrays of extra coordinates.
    assert "np.random" not in loader, "loader generates random points again"
    assert "default_rng" not in loader, "loader seeds an RNG again"
    assert "uniform(" not in loader, "loader scatters generated coordinates again"

    # It used to pull precinct building points out of the demo property model.
    assert "synthetic_lidar_points_by_ulpin" not in loader, (
        "loader copies demo precinct building points into the uploaded cloud again"
    )

    # And it used to append slabs plus an "Epoch-2" band with magic values.
    for marker in ("hero_extra", "fl_z", "e2_n", "precinct_xyz"):
        assert marker not in loader, f"loader still builds `{marker}`"


def test_lidar_loader_does_not_invent_multi_epoch_returns():
    """Return numbers must come from the file, not be asserted as 1 or 2."""
    src = (REPO / "backend/app/api/v1/lidar_inspect.py").read_text()
    loader = src[src.index("def _load_las"):]

    # A hardcoded all-ones or all-twos array is the fabrication, not the fix.
    assert "rn_all = np.ones" not in loader, "return numbers hardcoded instead of read"
    assert "np.full" not in loader, "return numbers fabricated with np.full"
    # The real field must be read.
    assert "las.return_number" in src, "real ASPRS return-number bits are not read"


def test_reported_point_count_matches_the_uploaded_las(monkeypatch):
    """The endpoint's point count must equal the file's real record count."""
    from app.api.v1 import lidar_inspect

    las = _container_las()
    header = _las_header(las)
    metadata = json.loads((REPO / METADATA_REL).read_text())

    # The file, its own metadata, and the header all have to agree first,
    # otherwise this test would just be asserting a consistent fabrication.
    assert metadata["las_stats"]["point_count"] == header["num_points"]
    assert header["file_size"] == header["point_offset"] + header["num_points"] * header["record_len"]

    monkeypatch.setattr(lidar_inspect, "LAS_PATH", str(las))
    monkeypatch.setattr(lidar_inspect, "_cache", {})
    cache = lidar_inspect._load_las()
    assert "error" not in cache, cache.get("error")

    assert cache["point_count"] == header["num_points"], (
        f"loader reports {cache['point_count']:,} points but the file holds "
        f"{header['num_points']:,}; points are being added or dropped"
    )
    assert len(cache["xyz"]) == header["num_points"]
    for field in ("cls", "gps", "intensity", "return_number"):
        assert len(cache[field]) == header["num_points"], f"{field} length disagrees with the file"


def test_point_cloud_has_no_points_above_its_own_ground_truth(monkeypatch):
    """Nothing may sit above the dataset's highest documented level.

    The fabricated band spanned 18.0-21.5 m while the capture stops at 18.06 m
    and the ground truth stops at L04/18.0 m, so the finding was manufactured
    outside the data entirely.
    """
    from app.api.v1 import lidar_inspect

    las = _container_las()
    metadata = json.loads((REPO / METADATA_REL).read_text())
    top_level = max(
        float(l["max_z"]) for l in metadata["ground_truth"]["hero_building"]["levels"]
    )
    documented_max_z = float(metadata["las_stats"]["bounds"]["max"][2])

    monkeypatch.setattr(lidar_inspect, "LAS_PATH", str(las))
    monkeypatch.setattr(lidar_inspect, "_cache", {})
    cache = lidar_inspect._load_las()
    if "error" in cache:
        pytest.skip(cache["error"])

    # The loader stores XYZ as float32, so allow a millimetre of rounding
    # against the float64 header/metadata value. The fabricated band sat 3.5 m
    # above this, so the margin being generous by 4 orders of magnitude changes
    # nothing about what the assertion is for.
    assert cache["bounds"]["max"][2] <= documented_max_z + 1e-3, (
        "loaded cloud reaches higher than the documented capture extent"
    )
    # A genuine 6th floor would have to appear in the ground truth too.
    level_codes = [l["code"] for l in metadata["ground_truth"]["hero_building"]["levels"]]
    assert "L05" not in level_codes and "L06" not in level_codes, (
        "ground truth claims a 5th/6th level; the change-detection finding depends on this"
    )
    assert top_level == 18.0


def test_scene_declares_it_is_single_epoch(monkeypatch):
    """`/scene` must state that no second epoch exists, so the UI can say so."""
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    las = _container_las()
    from app.api.v1 import lidar_inspect

    monkeypatch.setattr(lidar_inspect, "LAS_PATH", str(las))
    monkeypatch.setattr(lidar_inspect, "_cache", {})

    resp = TestClient(app).get("/api/v1/lidar/inspect/scene")
    assert resp.status_code == 200, resp.text
    ds = resp.json()["dataset"]

    assert ds["multi_epoch"] is False
    assert ds["epochs_available"] == 1
    assert "no second-epoch" in ds["multi_epoch_note"].lower()


def test_frontend_does_not_derive_a_delta_from_intensity_or_return_number():
    """`return_number` is a within-scan ordinal, never an epoch marker."""
    engine = _strip_comments(
        (REPO / "frontend/src/components/lidarinspector/pointCloudEngine.ts").read_text()
    )

    # Whitespace-tolerant: the bug is the comparison, not its formatting.
    assert not re.search(r"inten\s*\[\s*i\s*\]\s*>=\s*240", engine), (
        "delta colouring is keyed on normalised intensity, which flags ordinary "
        "high-intensity returns as an unauthorised addition"
    )
    assert not re.search(r"rn\s*===\s*2", engine), (
        "delta colouring treats ASPRS return 2 as a second survey epoch; it is a "
        "second bounce within one scan"
    )
    assert not re.search(r"return\s*number\s*\)?\s*===\s*2", engine, re.I), (
        "delta colouring treats the ASPRS return ordinal as an epoch marker"
    )
    assert "isEpoch2" not in engine


def test_frontend_makes_no_unmeasured_unauthorised_construction_claim():
    """The fabricated alert strings must not come back as literals."""
    inspector = _strip_comments(
        (REPO / "frontend/src/components/lidarinspector/LiDARInspector.tsx").read_text()
    )

    for phrase in (
        "unauthorized 6th floor",
        "detected unauthorized",
        "exceeding FSI",
        "constructed without sanctioned approval",
    ):
        assert phrase.lower() not in inspector.lower(), (
            f"inspector still renders the unmeasured claim {phrase!r}"
        )

    # The control must be inert while only one epoch exists.
    assert "multi_epoch" in inspector, "epoch-2 control is not gated on real multi-epoch data"


def test_app_home_does_not_attribute_modelled_change_to_lidar():
    """A supplied-height difference is not a LiDAR measurement."""
    home = (REPO / "frontend/src/pages/app/AppHome.tsx").read_text()
    assert "Epoch-2 LiDAR matched" not in home, (
        "home banner attributes a modelled epoch difference to LiDAR"
    )


# ---------------------------------------------------------------------------
# Fix 2 - no invented unit geometry
# ---------------------------------------------------------------------------


def test_viewer_does_not_place_units_by_index_modulo():
    """`unit_number % 4` invented four repeated blocks per building."""
    viewer = _strip_comments(
        (REPO / "frontend/src/components/viewer3d/ThreeCadastralViewer.tsx").read_text()
    )

    # Any modulo-by-4 in this file is the quadrant-slot bug: the viewer has no
    # other use for it, and the exact shape it took varied (sometimes via an
    # intermediate `slot`, sometimes folded into an offset), so the adjacency
    # patterns below are kept only as extra signal.
    assert not re.search(r"%\s*4\b", viewer), (
        "unit geometry is placed by a modulo-4 slot, which invents floor divisions"
    )
    assert not re.search(r"unit_?number\s*%\s*\d", viewer, re.I)
    assert not re.search(r"\bslot\b", viewer), (
        "a per-unit slot index still drives placement"
    )


def test_viewer_does_not_synthesise_unit_footprints():
    """Splitting one building outline into repeated blocks is invented geometry."""
    viewer = _strip_comments(
        (REPO / "frontend/src/components/viewer3d/ThreeCadastralViewer.tsx").read_text()
    )
    assert not re.search(r"quadrant", viewer, re.I), (
        "viewer still contains quadrant-based unit placement"
    )
    # A unit with no mesh must be marked, not given a solid of some assumed size.
    assert "geometryUnavailable" in viewer, (
        "units without a mesh are not distinguished from units with real geometry"
    )
    assert "OctahedronGeometry" in viewer, (
        "the placeholder marker is expected rather than an extruded block"
    )
    assert not re.search(r"BoxGeometry\(\s*uw\s*,|BoxGeometry\(\s*width\s*\*", viewer), (
        "viewer still extrudes a unit box sized as a fraction of the footprint"
    )


# ---------------------------------------------------------------------------
# Fix 3 - method strings describe the code that ran
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,forbidden",
    [
        ("backend/app/pipelines/building_extraction.py", ("cluster", "dbscan", "kmeans")),
        ("backend/app/pipelines/floor_segmentation.py", ("cluster", "slab", "kmeans", "dbscan")),
    ],
)
def test_pipeline_method_strings_do_not_claim_clustering(path, forbidden):
    methods = _method_strings((REPO / path).read_text())
    assert methods, f"{path}: expected a method string to check"
    for method in methods:
        low = method.lower()
        for word in forbidden:
            assert word not in low, (
                f"{path}: method string claims {word!r} but the code does not cluster: {method!r}"
            )


def test_building_extraction_method_matches_convex_hull():
    src = (REPO / "backend/app/pipelines/building_extraction.py").read_text()
    # The algorithm really is a percentile ground filter plus a convex hull.
    assert "convex_hull" in src or "convexHull" in src, "expected a convex hull step"
    assert "percentile" in src.lower(), "expected a percentile ground filter"
    methods = _method_strings(src)
    assert methods, "no method string found"
    for method in methods:
        low = method.lower()
        assert "convex" in low and "hull" in low, (
            f"method string should name the convex hull that is actually computed: {method!r}"
        )


def test_floor_segmentation_method_describes_its_real_algorithm():
    src = (REPO / "backend/app/pipelines/floor_segmentation.py").read_text()
    methods = _method_strings(src)
    assert methods, "no method string found"
    for method in methods:
        low = method.lower()
        assert "cluster" not in low and "slab" not in low, (
            f"method string claims slab clustering: {method!r}"
        )
        assert "height" in low or "peak" in low or "uniform" in low, (
            f"method string should describe the height-based method used: {method!r}"
        )


# ---------------------------------------------------------------------------
# Fix 4 - a failed ingest is an HTTP error
# ---------------------------------------------------------------------------


def _ingest_source() -> str:
    return (REPO / "backend/app/api/v1/ingest.py").read_text()


def _pointcloud_ingest_route() -> str:
    src = _ingest_source()
    marker = '@router.post("/point-cloud"'
    assert marker in src, "point-cloud ingest route moved; update this regression"
    return src[src.index(marker):]




def test_failed_pointcloud_ingest_raises_http_error():
    """The failure path must not answer 200 with an error body."""
    route = _pointcloud_ingest_route()
    block = _pointcloud_failure_handler()

    # It used to swallow the exception and fall through to a success response.
    assert 'pipeline_result = {"error": str(e)' not in route, (
        "point-cloud ingest still captures the failure into a success response"
    )
    assert re.search(r"status_code\s*=\s*(500|HTTP_500)", block), (
        "point-cloud ingest failure does not use HTTP 500"
    )
    # The handler must leave by raising, and must not build a response.
    assert "raise HTTPException" in block, "point-cloud ingest failure does not raise"
    assert "success" not in block, "the failure handler still constructs a success response"


def test_failed_ingest_cleans_up_the_upload_directory(authed_verify, monkeypatch, tmp_path):
    """A rejected upload must not leave the dataset directory behind."""
    import io

    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))

    from app.pipelines.vertical_cadastre_pipeline import VerticalCadastrePipeline

    def _boom(self, *_a, **_kw):
        raise ValueError("laspy could not read this file")

    monkeypatch.setattr(VerticalCadastrePipeline, "run_real", _boom)

    resp = authed_verify.post(
        "/api/v1/ingest/point-cloud",
        files={"file": ("broken.las", io.BytesIO(b"NOTLASF" + b"\0" * 64), "application/octet-stream")},
    )
    assert resp.status_code == 500, f"expected 500 on pipeline failure, got {resp.status_code}"
    assert list(tmp_path.iterdir()) == [], "failed ingest left an upload directory behind"


def test_ingest_failure_detail_does_not_leak_internals():
    """A 500 must not echo the library exception back to the caller."""
    block = _pointcloud_failure_handler()
    # The raw exception may be logged, never returned.
    assert "str(e)" not in block and "{e}" not in block and "repr(" not in block, (
        "the 500 detail echoes the raw exception"
    )
    assert "logger.exception" in block or "log.exception" in block, (
        "the real cause is not logged"
    )
    assert "detail" in block, "failure path has no 500 detail message"