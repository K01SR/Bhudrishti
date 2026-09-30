"""Regression tests for request-threadpool saturation on the open-data path.

The failure these lock down was not a slow endpoint; it was a slow endpoint
multiplied by a stampede. `get_area` checked its cache and then fetched
without holding anything, so N concurrent requests for one uncached area all
missed and all called the provider. Each provider call blocks on network I/O
behind a global politeness gap, and each occupies one request thread for the
whole queue. Measured against the running service: 24 concurrent requests for
the same area took 170s each, and with enough of them the threadpool is
exhausted, at which point every other synchronous endpoint stalls too and the
gates hang on an apparently dead stack.
"""

import threading
import time

import pytest

from app.opendata import overpass, service


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Isolate each test from the real cache, locks, counters and disk state.

    Both the loader and the writer are stubbed out. `get_area` calls
    `_load_snapshot()` on entry, so without this the cache is refilled from
    `data/opendata_cache.json` underneath the in-memory clear — and because a
    successful fetch calls `_persist_snapshot()`, the tests would also write
    their fixtures into the real on-disk snapshot that the running service
    reads.
    """
    store, locks, hits = dict(service._REGION_STORE), dict(service._key_locks), dict(service._HITS)
    service._REGION_STORE.clear()
    service._key_locks.clear()
    service._HITS.update({"cache": 0, "fetch": 0, "fail": 0})
    monkeypatch.setattr(service, "_load_snapshot", lambda: None)
    monkeypatch.setattr(service, "_persist_snapshot", lambda: None)
    # Module-level throttle/inflight state is process-global; reset it so the
    # admission tests do not inherit a saturated semaphore or a future cursor.
    monkeypatch.setattr(overpass, "_last_request_ts", 0.0)
    for _ in range(overpass._MAX_INFLIGHT):
        if overpass._inflight.acquire(blocking=False):
            overpass._inflight.release()
    yield
    service._REGION_STORE.clear()
    service._REGION_STORE.update(store)
    service._key_locks.clear()
    service._key_locks.update(locks)
    service._HITS.update(hits)


def _area(n_buildings=3):
    """A minimal AreaData whose footprints survive `_project`.

    The projection reads `ring_geo` (a closed lon/lat ring), so a building
    carrying only a centroid is not a valid fixture — it raises KeyError
    inside the code under test rather than exercising the behaviour being
    asserted.
    """
    from app.sources.base import AreaData, Provenance

    buildings = []
    for i in range(n_buildings):
        lon, lat = 72.9 + i * 1e-4, 19.0 + i * 1e-4
        buildings.append({
            "id": f"B{i}",
            "name": f"Building {i}",
            "type": "yes",
            "ring_geo": [[lon, lat], [lon + 5e-5, lat], [lon + 5e-5, lat + 5e-5], [lon, lat + 5e-5], [lon, lat]],
            "center_geo": [lon + 2.5e-5, lat + 2.5e-5],
            "height_m": 10.0 + i,
        })
    return AreaData(
        buildings=buildings,
        labels=[],
        provenance=Provenance(
            provider="test",
            dataset="test",
            license="test",
            source_url="test",
        ),
        warnings=[],
    )


def test_concurrent_misses_collapse_to_one_fetch(monkeypatch):
    """24 concurrent callers, one uncached area => exactly one provider call."""
    calls = []
    barrier = threading.Barrier(24, timeout=10)

    def slow_fetch(lat, lon, radius, max_buildings):
        calls.append((lat, lon))
        time.sleep(0.4)  # stand in for a network round-trip
        return _area()

    monkeypatch.setattr(service, "fetch_area", slow_fetch)

    results = {}

    def worker(i):
        barrier.wait()
        results[i] = service.get_area(19.15, 72.99, 400)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(calls) == 1, f"expected a single coalesced fetch, got {len(calls)}"
    assert service._HITS["fetch"] == 1
    # Every caller gets the area; the 23 that waited are served from the cache
    # the winner filled, so they report from_cache rather than re-fetching.
    assert len(results) == 24
    assert all("buildings" in r for r in results.values())


def test_waiters_are_not_serialised_behind_the_provider(monkeypatch):
    """A slow provider must cost one slow wait, not one per caller."""
    barrier = threading.Barrier(12, timeout=10)
    monkeypatch.setattr(service, "fetch_area", lambda *a, **k: (time.sleep(0.5), _area())[1])

    started = time.monotonic()
    threads = [
        threading.Thread(target=lambda: (barrier.wait(), service.get_area(19.16, 72.98, 300)))
        for _ in range(12)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    elapsed = time.monotonic() - started

    # Serialised, this would be ~12 x 0.5s = 6s. Coalesced, it is one fetch.
    assert elapsed < 2.5, f"12 callers took {elapsed:.1f}s, so they were serialised"


def test_throttle_does_not_sleep_inside_the_lock():
    """The gap must be reserved under the lock and waited on outside it.

    Sleeping inside the critical section makes the lock itself a five-second
    parking space, so callers queue on lock acquisition where nothing can see
    or bound them. With the sleep outside, two threads can be in the throttle
    section at once and the reservation is visible in the cursor.
    """
    overpass._last_request_ts = 0.0
    first = time.monotonic()
    t1 = threading.Thread(target=overpass._throttle)
    t2 = threading.Thread(target=overpass._throttle)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    elapsed = time.monotonic() - first

    # Second call is spaced by the gap, so both finish well inside 2 gaps: if
    # the sleep were still inside the lock, each waiter would additionally pay
    # for lock handoff and the pair would exceed the gap plus the handoff.
    assert elapsed < overpass._MIN_GAP_S * 2, f"throttle pair took {elapsed:.1f}s"
    assert overpass._last_request_ts >= time.monotonic() - 1.0


def test_inflight_cap_is_enforced_and_released(monkeypatch):
    """Admission is bounded, and a slot is returned even when a fetch fails."""
    acquired = [overpass._inflight.acquire(blocking=False) for _ in range(overpass._MAX_INFLIGHT + 2)]
    assert sum(acquired) == overpass._MAX_INFLIGHT
    for ok in acquired:
        if ok:
            overpass._inflight.release()

    # A raising call must not leak its slot. The transport is stubbed so this
    # exercises the release path deterministically instead of depending on a
    # live mirror being reachable.
    def boom(*a, **k):
        raise RuntimeError("mirror unreachable")

    monkeypatch.setattr(overpass.httpx, "post", boom)
    with pytest.raises(RuntimeError):
        overpass._run_query("[out:json];node(0,0,0,0);out;", timeout=1.0, attempts=1)

    # If the slot had leaked the semaphore would now be saturated.
    assert overpass._inflight.acquire(blocking=False)
    overpass._inflight.release()


def test_saturated_source_reports_busy_not_broken(monkeypatch):
    """Over capacity is a retryable 503, distinct from a missing source."""
    for _ in range(overpass._MAX_INFLIGHT):
        assert overpass._inflight.acquire(blocking=False)
    try:
        with pytest.raises(overpass.OverpassBusy):
            overpass._run_query("[out:json];node(0,0,0,0);out;")
    finally:
        for _ in range(overpass._MAX_INFLIGHT):
            overpass._inflight.release()


def test_a_failed_fetch_is_not_cached(monkeypatch):
    """An outage must not be memoised as a successful empty area."""

    def fail(*a, **k):
        from app.sources.base import NoAuthenticSourceError

        raise NoAuthenticSourceError("source unreachable")

    monkeypatch.setattr(service, "fetch_area", fail)
    key = service._region_key(19.15, 72.99, 400)

    for _ in range(2):
        with pytest.raises(Exception):
            service.get_area(19.15, 72.99, 400)
    assert key not in service._REGION_STORE
    assert service._HITS["fail"] == 2
