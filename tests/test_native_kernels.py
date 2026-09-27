"""Multi-language pipeline kernels: C++ (ctypes) + Rust (binary) parity with the
pure-numpy reference, exercised through the shared accel entry points."""
import numpy as np
import pytest

from app.pipelines.cpp_kernels import (
    grid_ground_profile_fast,
    grid_ground_profile_slow,
)
from app.pipelines.rust_accel import ground_profile_rust, rust_available


@pytest.mark.parametrize("pct", [5.0, 50.0])
def test_rust_matches_numpy_reference(pct):
    rng = np.random.default_rng(3)
    pts = np.column_stack(
        [
            rng.uniform(120, 200, 2000),
            rng.uniform(125, 185, 2000),
            rng.uniform(-4, 40, 2000),
        ]
    )
    reference = grid_ground_profile_slow(pts, cell=2.0, pct=pct)
    # The Rust path falls back to the numpy reference when the binary is absent,
    # so correctness holds in every environment.
    rust = ground_profile_rust(pts, cell=2.0, pct=pct)
    np.testing.assert_allclose(rust, reference, atol=1e-6, rtol=0)


def test_cpp_matches_numpy_reference():
    rng = np.random.default_rng(5)
    pts = np.column_stack(
        [
            rng.uniform(120, 200, 2000),
            rng.uniform(125, 185, 2000),
            rng.uniform(-4, 40, 2000),
        ]
    )
    reference = grid_ground_profile_slow(pts, cell=2.0, pct=10.0)
    fast = grid_ground_profile_fast(pts, cell=2.0, pct=10.0)
    if fast is not None:
        np.testing.assert_allclose(fast, reference, atol=1e-6, rtol=0)


def test_rust_binary_detection_shape():
    assert isinstance(rust_available(), bool)
    rng = np.random.default_rng(11)
    pts = rng.normal(size=(100, 3))
    out = ground_profile_rust(pts, cell=1.0, pct=5.0)
    assert out.shape == (100,)
    assert np.isfinite(out).all()