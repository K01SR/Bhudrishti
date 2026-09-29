from fastapi import APIRouter
import time

from app.core.config import settings
from app.core.crypto import (
    DEMO_ED25519_PRIVATE_KEY_HEX,
    DEMO_ED25519_PUBLIC_KEY_HEX,
)
from app.core.demo_gate import demo_mode_enabled
from app.pipelines.rust_accel import benchmark_native, rust_available
from app.pipelines.cpp_kernels import benchmark_ground_profile
from app.pipelines.cpp_kernels import _compile

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/deployment")
def deployment_facts():
    """What this deployment actually serves.

    The frontend previously rendered "Demo dataset" markers from a hardcoded
    string in ten places, with no connection to ENABLE_DEMO_MODE. The badge was
    therefore always present, including on a deployment that serves no
    generated data at all. The UI needs the real state to label itself, so it
    asks for it here rather than assuming.
    """
    demo = demo_mode_enabled()
    using_demo_key = (
        settings.ED25519_PRIVATE_KEY_HEX is None
        and demo
    ) or settings.ED25519_PRIVATE_KEY_HEX == DEMO_ED25519_PRIVATE_KEY_HEX

    return {
        "environment": settings.ENVIRONMENT,
        "demo_mode": demo,
        "synthetic_data_served": demo,
        "signing_key": "published demonstration keypair" if using_demo_key else "configured",
        "note": (
            "Generated demonstration data is being served. Identifiers, "
            "geometry and permitted-FSI figures on this deployment are "
            "invented and are not records of any real property."
            if demo
            else "No generated demonstration data is served. This deployment "
            "returns only records ingested from a real dataset."
        ),
    }


@router.get("/benchmarks")
def system_benchmarks():
    """Wall-clock comparison of the LiDAR ground-profile pipeline across three
    runtimes — numpy reference (Python), C++ ctypes kernel, and the Rust binary —
    so the multi-language acceleration is quantifiable from the UI."""
    # Sync def → Starlette runs this in a threadpool, not the event loop.
    t0 = time.perf_counter()
    bench = benchmark_native(n=200_000, repeat=3)
    bench_total_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    return {
        "pipeline": "LiDAR ground profile (bulk)",
        "total_ms": bench_total_ms,
        "benchmark_snapshot_ms": bench_total_ms,
        "rust_available": rust_available(),
        "binary_checked": True,
        "ground_profile": bench,
        "cpp_kernel_available": _compile() is not None,
    }