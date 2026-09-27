"""
Real multi-language acceleration: compiles ``kernels/ground_profile.cpp`` into a
native shared library at first use (gcc/g++ ship in the backend image) and
exposes a drop-in ``grid_ground_profile_fast`` with a numpy reference for
benchmarking. If compilation is unavailable the platform gracefully falls back
to the pure-Python path — pipelines never break on missing toolchains.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import tempfile
from typing import Optional

import numpy as np

_KERNEL_SRC = os.path.join(os.path.dirname(__file__), "kernels", "ground_profile.cpp")
_LIB_PATH = os.path.join(tempfile.gettempdir(), "bhudrishti_kernels.so")

_lib: Optional[ctypes.CDLL] = None
_compile_error: Optional[str] = None


def _compile() -> Optional[ctypes.CDLL]:
    global _lib, _compile_error
    if _lib is not None:
        return _lib
    if _compile_error is not None:
        return None
    try:
        cc = shutil.which("g++") or shutil.which("gcc") or shutil.which("clang++")
        if not cc:
            raise RuntimeError("No C++ compiler available in this environment")
        cmd = [
            cc, "-O3", "-fPIC", "-shared",
            "-std=c++17", _KERNEL_SRC, "-o", _LIB_PATH,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        _lib = ctypes.CDLL(_LIB_PATH)
        fn = _lib.ground_profile
        fn.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int64,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
        ]
        fn.restype = None
        return _lib
    except Exception as e:  # pragma: no cover
        _compile_error = str(e)
        return None


def grid_ground_profile_fast(points: np.ndarray, cell: float = 2.0, pct: float = 5.0) -> np.ndarray:
    """Per-cell percentile ground estimate via the native C++ kernel."""
    pts = np.ascontiguousarray(points[:, :3], dtype=np.float64)
    n = pts.shape[0]
    out = np.full(n, float(np.percentile(pts[:, 2], pct)), dtype=np.float64)
    if n == 0:
        return out
    lib = _compile()
    if lib is None:
        return grid_ground_profile_slow(pts, cell=cell, pct=pct)
    pts_ptr = pts.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    out_ptr = out.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    lib.ground_profile(pts_ptr, ctypes.c_int64(n), ctypes.c_double(cell), ctypes.c_double(pct), out_ptr)
    return out


def grid_ground_profile_slow(points: np.ndarray, cell: float = 2.0, pct: float = 5.0) -> np.ndarray:
    """Pure-numpy reference: per-cell ground-elevation estimate per point."""
    out = np.full(len(points), float(np.percentile(points[:, 2], pct)))
    if len(points) == 0:
        return out
    ox, oy = float(np.floor(points[:, 0].min())), float(np.floor(points[:, 1].min()))
    i = np.floor((points[:, 0] - ox) / cell).astype(np.int64)
    j = np.floor((points[:, 1] - oy) / cell).astype(np.int64)
    keys = i * 1_000_000_000 + j
    for k in np.unique(keys):
        mask = keys == k
        out[mask] = float(np.percentile(points[mask, 2], pct))
    return out


def benchmark_ground_profile(n: int = 500_000, repeat: int = 5) -> dict:
    """Real wall-clock comparison between the pure-numpy and native C++ kernels."""
    import time

    rng = np.random.default_rng(42)
    pts = np.column_stack(
        [rng.uniform(120, 200, n), rng.uniform(125, 185, n), rng.uniform(-4, 40, n)]
    )
    lib = _compile()

    times_python: list[float] = []
    times_cpp: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        grid_ground_profile_slow(pts)
        times_python.append((time.perf_counter() - t0) * 1000.0)

    if lib is None:
        return {
            "available": False,
            "workload": "per-cell ground profile %d pts" % n,
            "python_ms": round(float(np.mean(times_python)), 3),
            "cpp_ms": None,
            "speedup_factor": None,
            "note": "C++ kernel unavailable (no compiler); Python reference used.",
        }

    for _ in range(repeat):
        t0 = time.perf_counter()
        grid_ground_profile_fast(pts)
        times_cpp.append((time.perf_counter() - t0) * 1000.0)

    py_ms = float(np.mean(times_python))
    cpp_ms = float(np.mean(times_cpp))
    return {
        "available": True,
        "workload": "per-cell ground profile %d pts" % n,
        "python_ms": round(py_ms, 3),
        "cpp_ms": round(cpp_ms, 3),
        "speedup_factor": (f"{py_ms / cpp_ms:.1f}x" if cpp_ms > 0 else "n/a"),
        "runtime_used": "C++ native (g++ -O3) via ctypes",
    }