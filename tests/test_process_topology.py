"""The API process topology must be explicit, and its cost must stay bounded.

Measured on this stack, 200 requests to ``/ready`` at concurrency 20 (an
endpoint that touches both Redis and Postgres, so it exercises the connection
path rather than just the event loop):

    1 worker   ~4310 ms   ~46 req/s
    4 workers  ~1280 ms  ~156 req/s

Roughly 3.4x. That is the throughput lever this deployment was missing -- the
image shipped a single-worker uvicorn, which is why the read-heavy load harness
in ``tests/load`` plateaued in the high-20s req/s.

It is not free, and the tests here exist to keep the cost visible:

* Each worker is a process with its own event loop and its own connections.
  Postgres runs ``max_connections=300`` and is shared with the celery worker and
  the per-call engines in ``app/tiles/tiles.py`` and
  ``app/scene/scene_architect.py``.
* The shared ``async_engine`` is ``NullPool``, which is correct for one loop and
  the wrong shape once a second loop exists. A pooled multi-worker run has
  already exhausted all 300 connections, with 166 backends ``idle in
  transaction`` at ``BEGIN`` while the SQLAlchemy pool reported zero
  checked-out connections.

So the default stays 1 -- the configuration every number in
``tests/load/README.md`` was measured under -- and raising it is an explicit,
deliberate act via ``UVICORN_WORKERS`` rather than a silent default change that
would alter the connection budget of every existing deployment.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.yml").read_text()


def _backend_block() -> str:
    lines = COMPOSE.splitlines()
    start = next(i for i, l in enumerate(lines) if l == "  backend:")
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("  ") and not lines[j].startswith("   ") and lines[j].strip():
            return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


def test_worker_count_is_configurable_and_defaults_to_one():
    """Default 1 keeps the documented load-test baseline meaningful."""
    block = _backend_block()
    assert "--workers" in block, (
        "the backend image shipped a single-worker uvicorn with no way to change "
        "it; expose it via UVICORN_WORKERS"
    )
    assert "${UVICORN_WORKERS:-1}" in block, (
        "UVICORN_WORKERS must default to 1, the topology every "
        "tests/load/README.md measurement was taken under"
    )


def test_connection_budget_is_documented_at_the_worker_setting():
    """Whoever raises the worker count has to see the cost first."""
    block = _backend_block()
    for token in ("max_connections=300", "NullPool", "idle-in-transaction"):
        assert token in block, (
            f"the worker-count comment must mention {token!r}; raising workers "
            f"without stating the connection budget is how the previous "
            f"300-connection exhaustion happened"
        )


def test_postgres_connection_ceiling_is_unchanged():
    """The budget the comment relies on must actually be configured."""
    assert "max_connections=300" in COMPOSE, (
        "postgres must keep an explicit max_connections; the default (100) does "
        "not match what the compose comments claim"
    )


def test_liveness_and_readiness_are_separate_endpoints():
    """/health must not depend on anything, /ready must depend on real deps.

    Folding readiness into liveness is the specific failure mode worth guarding:
    several endpoints do blocking I/O against Overpass, terrain and GlobalML with
    10-60s timeouts, so a sync /health can be starved of the anyio threadpool
    while the process is perfectly alive. That marked the container unhealthy and
    cascaded into the frontend via `depends_on: service_healthy`.
    """
    from app.main import app

    # getattr, not r.path: as of starlette 1.3 / fastapi 0.142 the route table
    # contains _IncludedRouter entries for mounted sub-apps, which have no
    # `path`. Reading it directly raises AttributeError and fails this test for
    # a reason that has nothing to do with what it asserts.
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in paths, "liveness endpoint missing"
    assert "/ready" in paths, (
        "readiness endpoint missing; /ready is the route name (not /readiness)"
    )