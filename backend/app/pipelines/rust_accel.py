"""
Rust pipeline kernel: zero-dependency ``bhudrishti_native`` binary compiled in the
Docker image (``/usr/local/bin/``) — or, in dev, from ``backend/native/target/release``
via the bind mount. Falls back to the pure-numpy reference if the binary is missing,
so pipelines never break on an absent toolchain.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

import numpy as np

# Candidate locations, highest priority first. DEV_COPY covers host-compiled
# binaries surfaced through the backend's bind mount at runtime.
_CANDIDATES = [
    os.environ.get("BHU_DRISHTI_NATIVE", ""),
    "bhudrishti_native",
    "/usr/local/bin/bhudrishti_native",
    "/app/native/target/release/bhudrishti_native",
    "/app/backend/native/target/release/bhudrishti_native",
]
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CANDIDATES.append(os.path.join(_APP_DIR, "native", "target", "release", "bhudrishti_native"))

_binary: Optional[str] = None
_binary_probed = False


def find_binary() -> Optional[str]:
    """Locates the Rust kernel binary (memoised) or returns None."""
    global _binary, _binary_probed
    if _binary_probed:
        return _binary
    _binary_probed = True
    for cand in _CANDIDATES:
        if not cand:
            continue
        path = shutil.which(cand) if os.sep not in cand and "/" not in cand else cand
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            _binary = path
            return _binary
    return None


def rust_available() -> bool:
    return find_binary() is not None


def ground_profile_rust(
    points: np.ndarray, cell: float = 2.0, pct: float = 5.0
) -> np.ndarray:
    """Per-cell percentile ground estimate via the Rust binary (raw f64 pipe)."""
    pts = np.ascontiguousarray(points[:, :3], dtype=np.float64)
    n = pts.shape[0]
    out = np.full(n, float(np.percentile(pts[:, 2], pct)), dtype=np.float64)
    if n == 0:
        return out
    binary = find_binary()
    if binary is None:
        from app.pipelines.cpp_kernels import grid_ground_profile_slow

        return grid_ground_profile_slow(pts, cell=cell, pct=pct)
    res = subprocess.run(
        [binary, "ground-profile", "--binary", "--cell", f"{cell}", "--pct", f"{pct}"],
        input=pts.tobytes(),
        capture_output=True,
        check=True,
        timeout=120,
    )
    vals = np.frombuffer(res.stdout, dtype=np.float64)
    if vals.size != n:
        raise RuntimeError(f"Rust kernel returned {vals.size} values for {n} points")
    out[:] = vals
    return out


def benchmark_native(n: int = 200_000, repeat: int = 3) -> dict:
    """Wall-clock comparison: numpy reference vs C++ ctypes vs Rust binary."""
    import time

    from app.pipelines.cpp_kernels import (
        grid_ground_profile_fast,
        grid_ground_profile_slow,
        _compile,
    )

    rng = np.random.default_rng(7)
    pts = np.column_stack(
        [rng.uniform(120, 200, n), rng.uniform(125, 185, n), rng.uniform(-4, 40, n)]
    )
    cpp_lib = _compile()

    def timeit(fn) -> float:
        fn(pts)
        vals = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            fn(pts)
            vals.append((time.perf_counter() - t0) * 1000.0)
        import statistics

        return round(float(statistics.mean(vals)), 3)

    py_ms = timeit(grid_ground_profile_slow)
    cpp_ms = timeit(grid_ground_profile_fast)
    rust_ms = timeit(ground_profile_rust) if rust_available() else None

    return {
        "available": rust_available(),
        "workload": "per-cell ground profile (%d pts) — bulk LiDAR" % n,
        "python_ms": py_ms,
        "cpp_ms": cpp_ms,
        "rust_ms": rust_ms,
        "runtimes": {
            "python": "numpy reference (event loop)",
            "cpp": "C++ native (g++ -O3) via ctypes",
            "rust": "Rust native (bhudrishti_native 0.1.0) via raw f64 pipe",
        },
        "speedup_cpp_vs_python": f"{py_ms / cpp_ms:.1f}x" if cpp_ms > 0 else "n/a",
        "speedup_rust_vs_python": (f"{py_ms / rust_ms:.1f}x" if rust_ms and rust_ms > 0 else None),
        "note": "C++ runs in-process (ctypes); Rust pipes TSV through a subprocess boundary.",
    }