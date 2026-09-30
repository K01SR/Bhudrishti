import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.pipelines.spatial_pipelines import spatial_pipelines_registry
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset

client = TestClient(app)


def test_synthetic_architectural_elements():
    """Verify that synthetic dataset produces deep LOD 2/3 architectural elements."""
    data = generate_synthetic_airoli_dataset()
    assert "architectural_elements" in data
    arch = data["architectural_elements"]
    assert "slabs" in arch
    assert "columns" in arch
    assert "central_core" in arch
    assert "balconies" in arch
    assert "roof_crown" in arch
    assert "foundation" in arch

    # Check slabs: 7 slabs (B1, G, L01-L04, Roof)
    assert len(arch["slabs"]) == 7
    # Check columns: 12 structural columns
    assert len(arch["columns"]) == 12
    # Check balconies: 16 cantilevered balconies
    assert len(arch["balconies"]) == 16
    # Check foundation piles: 16 deep concrete piles
    assert len(arch["foundation"]["piles"]) == 16
    assert arch["foundation"]["depth_m"] == 8.0
    # Check roof crown
    assert arch["roof_crown"]["solar_pv_array"]["panel_count"] == 24
    assert len(arch["roof_crown"]["water_tanks"]) == 2


def test_pipeline_catalog_endpoint():
    """Verify that all 8 specialized pipelines are returned in the catalog."""
    response = client.get("/api/v1/pipelines/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 8
    assert len(data["pipelines"]) == 8

    expected_ids = [
        "cad-vectorize",
        "boundary-concordance",
        "subsurface-utility",
        "nbc-encroachment",
        "solar-air-rights",
        "fsi-massing",
        "multiepoch-diff",
        "topology-healer",
    ]
    catalog_ids = [p["id"] for p in data["pipelines"]]
    for exp_id in expected_ids:
        assert exp_id in catalog_ids


def test_pipeline_benchmarks_endpoint():
    """Verify benchmarks report REAL measured speedup (Python vs native C++ kernel)."""
    response = client.get("/api/v1/pipelines/benchmarks")
    assert response.status_code == 200
    data = response.json()
    assert data["measured"] is True
    assert "workload" in data
    assert "python_ms" in data
    assert "cpp_ms" in data
    assert "speedup_factor" in data
    if data.get("available"):
        assert data["speedup_factor"] is not None
        assert str(data["speedup_factor"]).rstrip("x")
        assert data["cpp_ms"] is not None
        assert data["cpp_ms"] < data["python_ms"]


@pytest.mark.parametrize("pipeline_id", [
    "cad-vectorize",
    "boundary-concordance",
    "subsurface-utility",
    "nbc-encroachment",
    "solar-air-rights",
    "fsi-massing",
    "multiepoch-diff",
    "topology-healer",
])
def test_pipeline_execution(pipeline_id, authed_state):
    """Verify execution of each of the 8 pipelines via REST API."""
    client = authed_state
    response = client.post("/api/v1/pipelines/run", json={"pipeline_id": pipeline_id, "parameters": {}})
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    data = res_data["data"]
    assert data["pipeline_id"] == pipeline_id
    assert "execution_telemetry" in data
    telem = data["execution_telemetry"]
    # The telemetry reports one real per-call wall time. The previous version
    # synthesised rust/cpp timings by dividing the elapsed time by constants and
    # asserted speedup_factor == "14.9x"; this pipeline runs pure python +
    # shapely and never imports rust_accel or cpp_kernels, so no speedup may be
    # reported here.
    assert telem["wall_time_ms"] is not None
    assert telem["wall_time_ms"] >= 0
    assert telem["runtime"] == "pure python + shapely (single process)"
    for fabricated in (
        "speedup_factor", "rust_simd_ms", "cpp_sfcgal_ms", "python_baseline_ms",
        "active_worker_runtime", "memory_consumption_mb", "vertices_processed",
        "throughput_vertices_sec",
    ):
        assert fabricated not in telem, f"{fabricated} must not be reported on an unaccelerated path"


def test_native_benchmark_reports_measured_speedup():
    """The genuine native chain is the only place a speedup may be reported."""
    from app.pipelines.cpp_kernels import benchmark_ground_profile

    res = benchmark_ground_profile(n=20_000, repeat=1)
    assert "available" in res
    if res.get("available"):
        # A speedup must be derived from two real timings, not a constant.
        assert res["cpp_ms"] is not None and res["python_ms"] is not None
        assert res["speedup_factor"] is not None
        assert res["speedup_factor"] != "14.9x"
    else:
        assert res["cpp_ms"] is None and res["speedup_factor"] is None


def test_hero_property_includes_architectural_elements():
    """Verify that /properties/hero delivers architectural elements to the frontend."""
    response = client.get("/api/v1/properties/hero")
    assert response.status_code == 200
    prop = response.json()
    assert "architectural_elements" in prop
    arch = prop["architectural_elements"]
    assert len(arch["slabs"]) > 0
    assert len(arch["columns"]) > 0
    assert len(arch["balconies"]) > 0
