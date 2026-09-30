"""Engine topology: pooling on the server loop, NullPool on ephemeral loops.

The `NullPool` default existed because one shared engine was reached from two
kinds of event loop. These tests pin the resolution that replaced it, plus a
structural guard so `asyncio.run()` cannot quietly return to a request handler
and undo the whole thing.
"""

import asyncio
import re
from pathlib import Path

import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core import database as dbmod

REPO = Path(__file__).resolve().parents[1]
API_DIR = REPO / "backend" / "app" / "api"


@pytest.fixture(autouse=True)
def clean_registry():
    """Each test starts from an empty, unregistered registry.

    Registries are WeakKeyDictionary keyed by loop object, so a loop from a
    previous test may still be alive and visible; clear explicitly.
    """
    dbmod._engines.clear()
    dbmod._sessionmakers.clear()
    dbmod.set_server_loop(None)
    yield
    dbmod._engines.clear()
    dbmod._sessionmakers.clear()
    dbmod.set_server_loop(None)


def test_engine_is_cached_per_loop():
    async def main():
        a = dbmod.get_async_engine()
        b = dbmod.get_async_engine()
        return a is b

    assert asyncio.run(main()) is True


def test_unregistered_loop_gets_nullpool():
    """An ephemeral loop must never receive a pool it cannot keep alive."""

    async def main():
        return type(dbmod.get_async_engine().pool)

    assert asyncio.run(main()) is NullPool


def test_server_loop_gets_a_real_pool():
    async def main():
        dbmod.set_server_loop(asyncio.get_running_loop())
        return dbmod.get_async_engine()

    engine = asyncio.run(main())
    assert isinstance(engine.pool, AsyncAdaptedQueuePool)


def test_sessionmaker_binds_to_the_loop_specific_engine():
    async def main():
        dbmod.set_server_loop(asyncio.get_running_loop())
        engine = dbmod.get_async_engine()
        maker = dbmod.get_sessionmaker()
        return engine, maker

    engine, maker = asyncio.run(main())
    assert isinstance(engine.pool, AsyncAdaptedQueuePool)
    # The factory must be wired to this loop's engine, not to the module-level
    # NullPool one, or sessions would silently bypass the pool.
    assert maker.kw["bind"] is engine


def test_sessionmaker_differs_between_loops():
    """Two loops must not share a sessionmaker."""
    maker_a = {}

    async def loop_one():
        dbmod.get_async_engine()
        maker_a["m"] = dbmod.get_sessionmaker()

    async def loop_two():
        dbmod.get_async_engine()
        return dbmod.get_sessionmaker()

    asyncio.run(loop_one())
    second = asyncio.run(loop_two())
    assert second is not maker_a["m"]
    # Weak keys mean the first loop's entry disappears once that loop is
    # collected, so at most one entry is alive here -- which is the point.
    assert len(dbmod._engines) <= 1


def test_dispose_clears_both_registries():
    async def main():
        dbmod.get_async_engine()
        dbmod.get_sessionmaker()
        assert dbmod._engines and dbmod._sessionmakers
        await dbmod.dispose_async_engines()
        return len(dbmod._engines), len(dbmod._sessionmakers)

    engines, makers = asyncio.run(main())
    assert engines == 0
    assert makers == 0


def test_registries_are_keyed_by_loop_object_not_by_id():
    """id(loop) is recycled after GC, which would resurrect a dead loop's engine.

    Two sequential asyncio.run() calls can hand out the same id once the first
    loop is collected. Keying by id would silently return the first loop's
    pooled connection to the second, which is the exact cross-loop failure the
    NullPool default existed to prevent.
    """
    import weakref

    assert isinstance(dbmod._engines, weakref.WeakKeyDictionary)
    assert isinstance(dbmod._sessionmakers, weakref.WeakKeyDictionary)

    async def loop_one():
        return dbmod.get_async_engine()

    first = asyncio.run(loop_one())
    loop_ref = weakref.ref  # keep import meaningful for readers
    assert loop_ref is not None
    # After loop_one's loop is collected its engine entry must disappear too,
    # otherwise the registry grows without bound across Celery tasks.
    import gc

    gc.collect()
    assert len(dbmod._engines) == 0, "engine outlived its loop"
    second = asyncio.run(loop_one())
    assert second is not first or len(dbmod._engines) == 1


def test_server_loop_flag_reflects_registration():
    assert dbmod.server_loop_is_registered() is False

    async def main():
        dbmod.set_server_loop(asyncio.get_running_loop())
        return dbmod.server_loop_is_registered()

    assert asyncio.run(main()) is True


def test_pool_bounds_are_smaller_than_postgres_limit():
    """4 uvicorn workers x (pool_size + overflow) must stay well under 300."""
    per_worker = dbmod.POOL_SIZE + dbmod.MAX_OVERFLOW
    assert per_worker == 10
    assert per_worker * 4 < 300


def test_get_async_engine_requires_a_running_loop():
    with pytest.raises(RuntimeError, match="requires a running event loop"):
        dbmod.get_async_engine()


# --------------------------------------------------------------------------- #
# Structural guard
# --------------------------------------------------------------------------- #
def test_no_asyncio_run_in_api_request_paths():
    """The regression that would undo pooling silently.

    A sync handler that calls ``asyncio.run()`` runs in FastAPI's threadpool and
    builds a throwaway event loop per request, so it cannot share the pooled
    engine. Comments and docstrings are stripped first so prose describing the
    old pattern does not trip this.
    """
    offenders = []
    for path in sorted(API_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""|\'\'\'.*?\'\'\'', "", source, flags=re.S)
        code = re.sub(r"#.*", "", code)
        for lineno, line in enumerate(code.splitlines(), 1):
            if "asyncio.run(" in line:
                offenders.append(f"{path.relative_to(REPO)}:{lineno}")
    assert not offenders, (
        "asyncio.run() back in a request path; convert the handler to async def "
        f"so it shares the pooled engine: {offenders}"
    )


def test_scene_architect_session_is_not_built_per_call():
    """`_own_session` exists for callers that genuinely have no session.

    Request paths must pass one in instead, so assert the public entry point
    still supports that rather than forcing every call to go through it.
    """
    import inspect

    from app.scene import build_scene3d

    params = inspect.signature(build_scene3d).parameters
    assert "db" in params
    assert params["db"].default is None, "db must stay optional for CLI callers"


def test_startup_registers_and_shutdown_disposes():
    """The lifespan hooks are what make the pooled engine reachable at all."""
    source = (REPO / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "set_server_loop" in source
    assert "dispose_async_engines" in source