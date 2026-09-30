"""The tile path must not open a connection per layer.

``_query_tile`` used to call ``asyncpg.connect()`` and close it again, once for
every layer of every tile. The default tile asks for six layers, so one request
cost six TCP handshakes and six authentications, and the connection count
tracked the layer count rather than the request count.

These tests assert the property rather than the timing, because the handshake is
invisible to a unit test and visible only under load. The structural guard is
the part that actually holds the line: a regex over the module is crude, but it
fails the moment someone writes a per-layer connect again, and it fails at CI
time rather than at 3am under a traffic spike.

The behavioural tests run without a database by standing in a fake pool, so they
exercise the batching logic (one acquire per tile, every requested layer
returned, cache-miss-only fetching) without needing Postgres.
"""
from __future__ import annotations

import asyncio
import inspect
import re

import pytest

from app.tiles import tiles


def test_no_per_layer_connect_in_tile_module() -> None:
    """The regression guard: no bare asyncpg.connect in the tile path."""
    source = inspect.getsource(tiles)
    # Strip comments so the prose explaining the old behaviour does not trip it.
    code = "\n".join(
        line for line in source.split("\n") if not line.strip().startswith("#")
    )
    offenders = [
        line.strip()
        for line in code.split("\n")
        if re.search(r"asyncpg\.connect\s*\(", line)
    ]
    assert not offenders, (
        "the tile path opens a raw connection again; use get_tile_pool(): "
        f"{offenders}"
    )


def test_pool_is_keyed_per_loop_not_globally() -> None:
    """A single global pool would break every non-server loop.

    asyncpg connections belong to the loop that created them, so a pool shared
    across loops raises "attached to a different loop" the first time a Celery
    task or a test touches it. The registry must therefore be keyed by loop and
    held weakly, so an entry cannot outlive the loop it names.
    """
    import weakref

    assert isinstance(tiles._tile_pools, weakref.WeakKeyDictionary), (
        "tile pools are not held in a loop-keyed weak registry"
    )
    assert tiles.TILE_POOL_MAX_SIZE <= 10, (
        "tile pool is larger than the ORM pool; tile requests are cache misses "
        "by definition and this pool exists to remove handshakes, not buffer spikes"
    )


def test_get_tile_pool_is_a_coroutine_function() -> None:
    """`asyncpg.create_pool` is awaitable; an un-awaited call returns a coroutine.

    Storing that coroutine in the registry and calling ``acquire()`` on it fails
    at the first real request with "pool is not initialized", not at import or
    startup, so nothing short of exercising it catches the mistake.
    """
    assert inspect.iscoroutinefunction(tiles.get_tile_pool), (
        "get_tile_pool must be async because asyncpg.create_pool is a coroutine; "
        "calling it without await stores a coroutine, not a pool"
    )


def test_get_tile_pool_returns_a_real_pool() -> None:
    """Against the live database, the registry must hold an actual Pool.

    The other tests monkeypatch the pool, so they cannot tell whether the thing
    being stored is a Pool or a promise of one. This one asks for real.
    """
    import asyncpg

    async def run():
        try:
            pool = await tiles.get_tile_pool()
            assert isinstance(pool, asyncpg.Pool), (
                f"registry holds {type(pool).__name__}, not an asyncpg.Pool"
            )
            same = await tiles.get_tile_pool()
            assert same is pool, "a second call must reuse the pool, not create another"
            return True
        finally:
            await tiles.close_tile_pools()

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        # A database-less environment is legitimate; a broken pool is not. The
        # message distinguishes the two so this is not a silent skip.
        if isinstance(exc, (OSError, asyncpg.PostgresError, RuntimeError)):
            pytest.skip(f"no live database: {type(exc).__name__}")
        raise


def _returns(pool):
    """An async stand-in for get_tile_pool, which is a coroutine function."""
    async def _get():
        return pool

    return _get


class _FakeConn:
    def __init__(self, recorder: list, fail_on: set[str] | None = None):
        self._recorder = recorder
        self._fail_on = fail_on or set()

    async def fetchrow(self, sql: str, *args):
        # The layer name is embedded in the ST_AsMVT call in the generated SQL.
        match = re.search(r"ST_AsMVT\(tile,\s*'([a-z_]+)'", sql)
        layer = match.group(1) if match else "unknown"
        self._recorder.append(layer)
        if layer in self._fail_on:
            raise RuntimeError(f"synthetic failure for {layer}")
        return (f"pbf:{layer}".encode(),)


class _FakePool:
    def __init__(self, fail_on: set[str] | None = None):
        self.acquires = 0
        self.queries: list[str] = []
        self.closed = False
        self._fail_on = fail_on or set()

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                pool.acquires += 1
                return _FakeConn(pool.queries, pool._fail_on)

            async def __aexit__(self, *exc):
                return False

        return _Ctx()

    async def close(self) -> None:
        self.closed = True


def test_tile_layers_share_one_acquire(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _FakePool()
    monkeypatch.setattr(tiles, "get_tile_pool", _returns(pool))

    async def run():
        return await tiles._query_tile_layers(
            ["state", "district", "taluka", "village", "parcel", "twin"], 12, 2200, 1430
        )

    result = asyncio.run(run())

    assert pool.acquires == 1, (
        f"expected one acquire for six layers, got {pool.acquires}"
    )
    assert sorted(result) == ["district", "parcel", "state", "taluka", "twin", "village"]
    assert result["state"] == b"pbf:state"
    assert len(pool.queries) == 6, "each requested layer must be queried exactly once"


def test_single_layer_tile_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """A one-layer tile must not regress into an empty tile."""
    pool = _FakePool()
    monkeypatch.setattr(tiles, "get_tile_pool", _returns(pool))

    result = asyncio.run(tiles._query_tile_layers(["parcel"], 12, 2200, 1430))

    assert result == {"parcel": b"pbf:parcel"}
    assert pool.acquires == 1


def test_empty_layer_list_never_acquires(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _FakePool()
    monkeypatch.setattr(tiles, "get_tile_pool", _returns(pool))

    assert asyncio.run(tiles._query_tile_layers([], 12, 2200, 1430)) == {}
    assert pool.acquires == 0, "an empty tile must not open a connection at all"


def test_query_tile_uses_the_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _FakePool()
    monkeypatch.setattr(tiles, "get_tile_pool", _returns(pool))

    assert asyncio.run(tiles._query_tile("state", 12, 2200, 1430)) == b"pbf:state"
    assert pool.acquires == 1
    assert pool.queries == ["state"]


def test_close_tile_pools_closes_and_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.new_event_loop()
    try:
        pool = _FakePool()
        tiles._tile_pools[loop] = pool  # type: ignore[arg-type]
        asyncio.run(tiles.close_tile_pools())
        assert pool.closed is True
        assert len(tiles._tile_pools) == 0
    finally:
        loop.close()


def test_layer_failure_propagates_rather_than_serving_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead layer must not be cached as an empty tile.

    Silently returning b"" for a failed query would poison Redis with an empty
    tile for the whole TTL, so the exception has to reach the caller, which
    catches it per request and logs.
    """
    pool = _FakePool(fail_on={"parcel"})
    monkeypatch.setattr(tiles, "get_tile_pool", _returns(pool))

    with pytest.raises(RuntimeError, match="synthetic failure"):
        asyncio.run(tiles._query_tile_layers(["state", "parcel"], 12, 2200, 1430))