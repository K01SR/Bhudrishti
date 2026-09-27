# Load test

Measures the API as deployed and records what produced the numbers. The point
is not to publish a flattering p99; it is to have a number at all, with its
context attached, so "how does it perform?" has an answer instead of an estimate.

## Running it

Locust is deliberately **not** in `backend/requirements.txt`. It pulls in a web
server and a large dependency tree, and shipping that inside the application
image would enlarge every deployment's attack surface for a tool that only runs
against a load-test target.

```bash
python -m venv /tmp/loadenv
/tmp/loadenv/bin/pip install -r tests/load/requirements.txt

# Demo mode must be on: with ENABLE_DEMO_MODE=0 the data endpoints correctly
# return 503 and the run measures refusals rather than the read path.
/tmp/loadenv/bin/python tests/load/run_load_test.py \
  --host http://localhost:8000 --users 40 --spawn-rate 8 --run-time 120s --label c40
```

`--host` has no default. A load test that defaults to something reachable
eventually runs against a real environment unattended.

## Deployment these numbers describe

Read from the running system, not asserted:

| Property | Value |
|---|---|
| Backend | `uvicorn app.main:app`, **one** worker, no `--workers` |
| Resource limits | none declared in `docker-compose.yml` |
| Cache | none in front of the API |
| Proxy | nginx in the frontend image proxies `/api` to the backend |
| Postgres | single container, `max_connections=300` |
| Data | demo mode on (serving generated demo data) |

The runner probes `/api/v1/lidar/inspect/scene` to determine demo mode rather
than trusting its own environment. An earlier version recorded the *load
generator's* env, which reported `unset` for a run that was entirely serving
demo data — precisely the unverified context that makes a result unciteable.

## Measured results

Single uvicorn worker, read-heavy mix, demo data. 90–180 s per run.

| Concurrency | Requests | Failures | Aggregate p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|---|
| 10 users | 1,197 | 0 | 68 ms | 500 ms | 740 ms | 13.4 rps |
| 40 users | 2,420 | 0 | 650 ms | 2,300 ms | 2,800 ms | 27.1 rps |
| 80 users | 2,387 | 0 | 1,700 ms | 6,000 ms | 6,900 ms | 26.7 rps |

Per-endpoint at 40 users:

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| `POST /auth/login` | 150 ms | 670 ms | 670 ms |
| `GET /verification/cases` | 410 ms | 1,100 ms | 1,300 ms |
| `GET /health` | 240 ms | 780 ms | 1,100 ms |
| `GET /lidar/inspect/scene` | 600 ms | 1,300 ms | 1,500 ms |
| `GET /precinct/buildings` | 660 ms | 1,300 ms | 1,500 ms |
| `GET /properties/hero` | 870 ms | 1,700 ms | 2,200 ms |
| `GET /search` | 1,900 ms | 2,700 ms | 2,900 ms |
| `GET /parcels/` | 1,800 ms | 2,800 ms | 3,200 ms |

At 80 users the two slow paths reach p50 5,600 ms (`/parcels/`) and 5,100 ms
(`/search`), with p99 past 6,900 ms.

These are **single-node figures for one worker**. They are not a capacity claim
for a scaled deployment, and runs of 90–180 s are far too short to characterise
tail latency properly.

## What the numbers say

**Throughput plateaus at about 27 rps.** Going from 40 to 80 concurrent users
issued *fewer* total requests than the 40-user run (2,387 vs 2,420) because each
user was waiting longer between them, while aggregate p95 rose from 2.3 s to
6.0 s. The server was already saturated at 40; adding users bought nothing.

**`/health` costing 240 ms at p50 (730 ms at 80 users) is the most informative
number here.** It
returns 38 bytes and touches no database. It should be effectively free. That it
is not means the bottleneck is the server's ability to accept requests at all,
not any particular endpoint — so per-endpoint optimisation would not help much.

**Zero failures at every level is itself a finding, not a comfort.** Nothing ever
returned an error; the system degraded purely into latency. Queueing is invisible
in an error rate, so a dashboard showing 0% errors would have shown this system
as healthy while `/search` sat at 1.9 s.

**`/search` and `/parcels/` are the slow paths** at every concurrency level.
`/precinct/buildings` returns 363 KB per response against `/parcels/` at 38 KB.

## Root cause of the per-request cost

`async_engine` in `backend/app/core/database.py` uses `NullPool`, so **every
request opens a fresh Postgres connection and closes it**. A bare connect+close
measured **25.5 ms** against this database. The handshake, not the query, is a
large part of the request.

Pooling the async engine was trialled and measured clearly better:

| Endpoint | NullPool p50 | Pooled p50 |
|---|---|---|
| `GET /parcels/` | 2,000 ms | 1,200 ms |
| `GET /search` | 2,100 ms | 1,100 ms |
| `GET /properties/hero` | 1,000 ms | 740 ms |

**It was reverted, and is not enabled.** The engine is a module-level global
imported by the Celery worker, which runs `asyncio.run()` on its own event loop.
A pooled connection belongs to the loop that opened it, so a shared pool hands a
worker's connection to uvicorn's loop and asyncpg raises a cross-loop error.
Enabling the pool needs the engine to stop being shared across loops first.

### Open anomaly, not yet explained

While trialling pooling, Postgres connections climbed monotonically (81 → 149
over a 90 s run) and eventually refused new ones with `sorry, too many clients
already`, surfacing as 287 HTTP 503s on `/parcels/`. `pg_stat_activity` showed
**166 backends in `idle in transaction`** at `BEGIN;`, while the SQLAlchemy pool
reported `checkedout=0, checkedin=0` — so the traffic was not using that pool at
all. Two candidate sources exist outside it:

- `backend/app/tiles/tiles.py:156` calls `asyncpg.connect()` directly, bypassing
  SQLAlchemy's pool entirely (not on the measured read path, but real).
- `backend/app/scene/scene_architect.py:54` builds a separate `NullPool` engine
  per call.

This is recorded as unresolved rather than guessed at. It did not affect the
shipped configuration.

## Also fixed as a result

`get_db` used `except Exception`, but `asyncio.CancelledError` inherits from
`BaseException`, so a client disconnecting mid-request skipped the rollback — and
the `await session.close()` in the `finally` was itself cancelled the moment it
was reached, so the connection was never returned. This is now `BaseException`
with `asyncio.shield` around the cleanup. It is a latent-bug fix rather than the
cause of the numbers above, and measurements with it applied show no regression.

## Worker count (added after the run above)

The image shipped a single-worker uvicorn with no way to change it, which is
the main reason the figures above plateau in the high-20s req/s. `UVICORN_WORKERS`
is now exposed in `docker-compose.yml`, defaulting to **1** so every measurement
on this page keeps its original meaning.

Measured on this stack, 200 requests to `/ready` at concurrency 20. That endpoint
touches both Redis and Postgres, so it exercises the connection path and not just
the event loop:

| Workers | Wall clock (200 reqs) | Throughput |
| ------- | --------------------- | ---------- |
| 1       | ~4310 ms              | ~46 req/s  |
| 4       | ~1280 ms              | ~156 req/s |

About 3.4x. With 4 workers running, `pg_stat_activity` showed 5 backends (4
workers plus the querying session), 4 idle and **0 `idle in transaction`** at
rest.

This is not a free win and the default stays at 1. Each worker is a process with
its own event loop and its own connections; Postgres runs `max_connections=300`
shared with the Celery worker and the per-call engines noted above. The shared
`async_engine` is `NullPool`, which is right for one loop and the wrong shape
once a second loop exists. A pooled multi-worker run has already exhausted all
300 connections with 166 backends `idle in transaction` at `BEGIN` while the pool
reported zero checked-out connections. Raise the worker count deliberately and
re-measure. Settling the engine topology first is the prerequisite.

#7: write path (added after the read-path runs above)

## The finding that matters more than the throughput

Before measuring write throughput, it is worth establishing what a write in
this system actually *is*. Grepping the API modules for `commit()`:

    backend/app/api/v1/parcels.py: 3
    backend/app/api/v1/pipelines_api.py: 1
    (every other module: 0)

Of those, `parcels.py` commits only inside `POST /parcels/ingest-area`, which
fetches footprints from OpenStreetMap. So there is no authenticated write
endpoint that reaches Postgres without an external network dependency.

This is not inferred; it was observed. `POST /builder/submissions/detailed`
returns:

    "persistence": {
      "persisted": false,
      "reason": "the submitter is not a database account yet; submission kept in memory only"
    }

and `select count(*) from submissions` returns `0` afterwards.

**So the write path has no database write in it.** Every citizen-facing write is
a list append or dict mutation in module-level state, lost on restart. A
harness that reported "write throughput" from these endpoints would be reporting
the throughput of `list.append`. That is the honest ceiling on what section #7
can establish, and it is why this section is short.

## Measured handler throughput

`POST /api/v1/objections/`, single uvicorn worker, 1 uvicorn worker process,
demo account authenticated, 12 CPUs:

| concurrency | p50 | p95 | p99 | 201s | duplicate case numbers |
|---|---|---|---|---|---|
| 40  | 49.4ms  | 53.4ms  | 53.8ms  | 40/40  | 0 |
| 100 | 101.8ms | 158.4ms | 161.8ms | 100/100| 0 |
| 200 | 173.0ms | 295.9ms | 301.4ms | 200/200| 0 |
| 400 | 487.7ms | 724.3ms | 729.1ms | 400/400| 0 |

Cumulative writes across the session: 40 + 150 + 900 probes, zero 5xx, zero
duplicate case numbers, store reached 1012 in-memory records.

Latency grows superlinearly with concurrency (100 x 101.8ms, 200 x 173ms,
400 x 487.7ms), which means writes are queueing rather than running in
parallel. They queue on the anyio threadpool: `create_objection` is a sync
`def`, so FastAPI serves it from the 40-thread default pool. Correctness holds
to 400; capacity does not, and this is a CPU-bound in-process store, not a
database.

## The lost-update race that did not fire

`create_objection` assigns `case_number = f"OBJ-2026-{len(_OBJECTIONS_DB) + 1:04d}"`
and *then* appends. It runs in a worker thread, so another thread can read the
same length in between and two objections come back with the same case number.
Both return 201, so a status-code assertion does not catch it; one citizen's
objection becomes unreachable by its own reference.

It did not reproduce at 400 concurrent requests. Recorded as latent, not fixed
and not dismissed. `tests/test_write_path_concurrency.py` asserts the invariant
(no duplicate case numbers across 64 barrier-synchronised threads) so that a
future refactor which breaks it fails rather than passing quietly.

## Still not tested

`POST /parcels/ingest-area` is the only real Postgres write and it is untested
under load, because exercising it means hammering OpenStreetMap. The durable
write path, when the submitter becomes a database account, has no load coverage
at all. `POST /builder/assets/upload` writes files to disk and has no coverage.
## Re-measuring the connection anomaly (does it reproduce on stock HEAD?)

The 166 `idle in transaction` at `BEGIN` above was observed during a *pooled*
trial, so it was worth asking whether stock HEAD has the same problem. Measured
against `docker compose` on 2026-10-04, `max_connections=300`, sampling
`pg_stat_activity` from the `postgres` service.

`GET /api/v1/properties/hero`, 60 concurrent:

| Point | Connections |
| ----- | ----------- |
| Baseline (at rest) | 2 |
| Warm (1 request) | 2 |
| Peak during load | 8 |
| After settling | 2 |

`GET /api/v1/tiles/{z}/{x}/{y}.pbf` with `layers=state,district,taluka,village,parcel,twin`,
150 concurrent across three tiles, with the Redis tile cache flushed first so
every request took the cache-miss path and opened one connection per layer:

| Point | Connections |
| ----- | ----------- |
| Baseline (at rest) | 2 |
| Peak during load | 25 |
| After settling | 2 |

Peak states were `active` 12 / `idle` 7. **No `idle in transaction` at any
sample point on either endpoint.**

So the anomaly does not reproduce on stock HEAD, and connections return to
baseline in both cases. It was a property of the pooled configuration that was
trialled, not of the `NullPool` engine that actually ships. That reframes item
#2/#5: the pooling change is what needs explaining before it is trusted, not
`NullPool`.

## Why `NullPool` is still the shipped default

The constraint is real and it is architectural. `asyncio.run()` appears in
request paths in two API modules:

- `backend/app/api/v1/properties.py` -- 3 call sites, including
  `_load_scene3d()` and `GET /hero/scene`, both reached through
  `build_hero_property_response()`.
- `backend/app/api/v1/exports.py` -- 4 `async def`-less handlers
  (`/cityjson`, `/ifc`, `/canonical-json`, `/csv`) that are all `def`, so
  FastAPI runs them in the threadpool.

Each of these is a sync handler, so it runs off the main loop and calls
`asyncio.run()`, which creates a **new event loop per request**. A pooled
connection belongs to the loop that opened it, so one shared pool cannot be
shared across a main loop and a per-request loop. That is what forces
`NullPool`, and it is also why `scene_architect._own_session()` builds and
disposes a throwaway engine per call.

The fix is to stop calling `asyncio.run()` from request handlers: convert the
nine call sites to `async def` and pass a session from `AsyncSessionLocal`, so
every request shares one loop and one pooled engine. That is a multi-module
refactor of `properties.py`, `exports.py` and `pipelines_api.py` with real
behavioural risk, and it is not started. Until it is done, raising
`UVICORN_WORKERS` trades a real per-request handshake for connection budget, and
pooling the async engine before it would re-create the 166-backend exhaustion
with less visibility.

## Pooled engine on the server loop (measured after conversion)

All nine `asyncio.run()` request-path call sites are gone: `properties.py`
(`_load_pipeline_provenance`, `_load_scene3d`, `build_hero_property_response`,
`/hero`, `/hero/scene`), `pipelines_api.py` (`/runs`, `/assets`) and
`exports.py` (`/cityjson`, `/ifc`, `/canonical-json`, `/csv`) are now `async def`
sharing the server loop. `get_async_engine()` resolves per loop: a real
`AsyncAdaptedQueuePool` on the loop latched at startup, `NullPool` on any other
loop, which is what keeps `asyncio.run()` inside a Celery task from orphaning a
pool it is about to abandon.

`POSTGRES ... SELECT count(*) FROM pg_stat_activity` on the same database:

| Scenario | Before | After |
| -------- | ------ | ----- |
| 600 sequential `/pipelines/runs` | one handshake per request | **3 transactions total** |
| 80 concurrent `/properties/hero` | up to ~80 backends | **peak 7 backends** |
| Idle backends afterwards | 2 | 7 (pool held warm) |

7 = `POOL_SIZE` 5 + `MAX_OVERFLOW` 2 in flight. Four workers therefore stay near
40 backends against `max_connections=300`, so the earlier 300-connection
exhaustion is not reachable at the current settings.

`tests/test_engine_topology.py` includes a structural guard that fails if
`asyncio.run(` reappears anywhere under `backend/app/api/`, since that reversion
is silent -- nothing else would notice pooling had stopped being used.

# Tile path: pooled, and the connection ceiling it removed

## What was wrong

`_query_tile` called `asyncpg.connect()` and closed the connection, once per
layer, per tile. The default tile asks for six layers, so one uncached request
cost six TCP handshakes and six authentications before any geometry was
computed. The connection count therefore tracked `requests x layers`, not
`requests`.

Measured on the same 150-concurrent cold-tile workload recorded above, which
peaked at **25 connections**.

## What it is now

A per-loop `asyncpg.Pool`, keyed by the running event loop in a
`WeakKeyDictionary` for the same reason `app.core.database` keys its engines:
pool connections belong to the loop that created them, so a pool shared across
loops raises "attached to a different loop" the moment a Celery task or a test
touches it.

`_query_tile_layers()` additionally acquires **one** connection for all layers
of a tile and runs them over it, since the layers of a tile share a bounding
envelope. So one six-layer tile went from six handshakes to one acquire.

| | before | after |
|---|---|---|
| handshakes per 6-layer tile | 6 | 1 (pooled) |
| peak connections, 150 concurrent cold tiles | 25 | **7** |
| statuses | 200 | 200 (150/150) |

Latency, 150 concurrent cold tiles: p50 307-457ms, p95 485-632ms. Two runs,
both peaking at 7. Pool `max_size=5`, so 7 is the tile pool's ceiling plus the
ORM connections and the sampler itself; the ceiling is now a configured number
rather than a function of how many layers the client asked for.

## The bug the mock could not see

`asyncpg.create_pool` is a coroutine function. The first version of this called
it without `await` and stored the resulting coroutine in the registry, which
failed on the first real request with `InterfaceError: pool is not initialized`.

Every unit test here monkeypatches the pool, so all of them passed against a
`get_tile_pool` that returned something unusable. `get_tile_pool` only breaks
against a real database, which is why `test_get_tile_pool_returns_a_real_pool`
asks for an actual `asyncpg.Pool` and asserts its type instead of trusting a
mock. It is the only test in this file that touches Postgres, and it is the one
that found the defect.

## Still true

`national_parcels` is empty in this deployment, so the `parcel` layer always
returns an empty tile and is not exercised by these numbers. Tile requests are
cache misses by definition here, so this pool removes a handshake; it is not a
buffer against a cold-start stampede, and the first wave of a cold cache still
queues on `max_size`.
