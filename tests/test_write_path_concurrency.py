"""The write path's concurrency invariant, asserted rather than assumed.

``POST /api/v1/objections/`` assigns a case number as ``len(_OBJECTIONS_DB) + 1``
and then appends. The handler is sync ``def``, so FastAPI serves it from the
anyio threadpool where those two statements can be interleaved by another
thread, and if they are, two objections come back with the same case number and
one citizen's objection becomes unreachable through its own reference. That is a
lost update, and it is the kind of defect that no status-code assertion finds:
both requests return 201.

A load run of 400 concurrent writes on 2026-10-04 produced zero duplicates, so
this is a latent race, not one that fires in practice at that scale. The test
below does not try to reproduce the interleaving by timing, which would be flaky
in both directions: it asserts the property that makes the race survivable, that
every accepted write is durable in the returned case number set and that case
numbers do not collide.

It also pins the honest limit of this path. Of the API modules only
``parcels.py`` and ``pipelines_api.py`` call ``commit()``, and ``parcels.py``
only via an endpoint that fetches from OpenStreetMap, so an objection is a
list append that a restart discards. These tests assert concurrency behaviour,
not durability, because there is none to assert.
"""
from __future__ import annotations

import threading
from collections import Counter

import pytest

from app.api.v1 import objections as objections_mod
from app.api.v1.objections import ObjectionCreate


def _reset_store() -> None:
    objections_mod._OBJECTIONS_DB.clear()


def test_case_numbers_are_unique_under_concurrent_writes() -> None:
    """Hammer the handler from real threads and require no collisions."""
    _reset_store()
    barrier = threading.Barrier(64)
    results: list[str | None] = []
    lock = threading.Lock()

    def write(index: int) -> None:
        req = ObjectionCreate(
            ulpin=f"12345678{index:08d}",
            category="OTHER",
            description=f"concurrent write {index}",
            contact_email=f"probe{index}@example.invalid",
            priority="LOW",
        )
        # Synchronise the start so the threads are actually contending on the
        # counter rather than arriving in sequence by accident.
        barrier.wait(timeout=30)
        record = objections_mod.create_objection(req, _auth=objections_mod.TokenPayload(
            sub=f"probe-{index}", role="CITIZEN", scopes=["citizen:file"]
        ))
        with lock:
            results.append(record["case_number"])

    threads = [threading.Thread(target=write, args=(i,)) for i in range(64)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(results) == 64, "some writers did not return"
    assert all(results), "a writer returned no case number"
    duplicates = {k: v for k, v in Counter(results).items() if v > 1}
    assert not duplicates, f"lost update: {len(duplicates)} duplicated case numbers, e.g. {duplicates}"
    assert len(set(results)) == 64


def test_every_accepted_write_is_listed_afterwards() -> None:
    """A 201 must correspond to a record the system can serve back."""
    _reset_store()
    auth = objections_mod.TokenPayload(sub="probe", role="CITIZEN", scopes=["citizen:file"])
    written = []
    for index in range(10):
        req = ObjectionCreate(
            ulpin=f"87654321{index:08d}",
            description=f"durability probe {index}",
            contact_email="probe@example.invalid",
        )
        written.append(objections_mod.create_objection(req, _auth=auth)["case_number"])

    rows = objections_mod.list_objections()
    served = {row["case_number"] for row in rows}
    missing = set(written) - served
    assert not missing, f"accepted writes missing from the store: {sorted(missing)}"
    assert len(written) == len(set(written))


def test_store_is_in_memory_and_not_durable_across_restart() -> None:
    """Documents the limit rather than hiding it.

    The store is a module-level list, so it is lost on restart. This test
    exists so that when someone adds real persistence it fails, which is the
    moment the durability claim becomes true and this assertion should be
    revisited.
    """
    _reset_store()
    auth = objections_mod.TokenPayload(sub="probe", role="CITIZEN", scopes=["citizen:file"])
    # A cleared list makes the next handler call re-seed, so the seed is run
    # up front and the write is measured as a delta against a settled baseline.
    objections_mod._seed_if_empty()
    baseline = len(objections_mod._OBJECTIONS_DB)
    objections_mod.create_objection(
        ObjectionCreate(ulpin="11223344556677", description="ephemeral"),
        _auth=auth,
    )
    assert len(objections_mod._OBJECTIONS_DB) == baseline + 1
    assert isinstance(objections_mod._OBJECTIONS_DB, list), (
        "the objection store is no longer the in-memory list this test assumed; "
        "if it is now durable, update the durability claim in tests/load/README.md"
    )


@pytest.mark.parametrize("category", ["OTHER", "BOUNDARY", "SURVEY"])
def test_case_number_format_is_preserved(category: str) -> None:
    _reset_store()
    auth = objections_mod.TokenPayload(sub="probe", role="CITIZEN", scopes=["citizen:file"])
    record = objections_mod.create_objection(
        ObjectionCreate(ulpin="12345678901234", category=category, description="format probe"),
        _auth=auth,
    )
    assert record["case_number"].startswith("OBJ-2026-")
    assert record["status"] == "OPEN"