import asyncio
import logging
import weakref
from contextlib import suppress
from typing import AsyncGenerator, Optional
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Async Engine for FastAPI Endpoints.
#
# NullPool is deliberate and is not merely a default. This engine is imported by
# the Celery worker, which runs `asyncio.run()` on its own event loop. A pooled
# connection is bound to the loop that opened it, so a shared pool hands a
# worker connection to uvicorn's loop (or the reverse) and asyncpg raises a
# cross-loop error.
#
# The cost is real and was measured with tests/load: a bare connect+close against
# this database is 25.5 ms, so every request pays the handshake rather than
# reusing a warm connection. At 40 concurrent clients /parcels/ had p50 2000 ms
# and /search p50 2100 ms on one uvicorn worker.
#
# Pooling the API engine measured substantially better (p50 2000 -> 1200 ms on
# /parcels/, and /search 2100 -> 1100 ms), so it is the right direction, but it
# must not be enabled until the engine is no longer shared across loops -- either
# by giving the worker its own engine or by keying the pool per event loop.
# See tests/load/README.md for the numbers and the connection-growth anomaly
# observed while trialling it.
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool,
)


# --------------------------------------------------------------------------- #
# Loop-aware engine resolution
# --------------------------------------------------------------------------- #
# The original comment on `async_engine` explained why NullPool was necessary: a
# pooled connection belongs to the event loop that opened it, and this module is
# reached from two different kinds of loop. That was correct, but it left the
# API paying a full handshake per request forever, because the fix for "one pool
# cannot span two loops" was applied to the process rather than to the loops.
#
# Resolved per loop instead:
#   * The server loop, latched once at startup, is long-lived and issues every
#     request, so it gets a real pooled engine. This is where reuse is safe.
#   * Any other loop -- chiefly `asyncio.run()` inside a Celery task, which
#     builds a new loop per task and throws it away -- gets NullPool, because a
#     pool built inside a loop that is about to close would be orphaned with its
#     connections still open. That is precisely how the 166 `idle in
#     transaction` exhaustion appeared during the earlier pooled trial.
#
# Pool sizing is deliberately modest and per-process: 5 + 5 overflow means 10
# per uvicorn worker, so four workers plus the Celery worker stay far below
# Postgres `max_connections=300`. Measured on stock HEAD before this change,
# peak usage was 25 connections under 150 concurrent tile requests.
_server_loop: Optional[asyncio.AbstractEventLoop] = None
# Keyed by the loop object in a WeakKeyDictionary, not by id(loop). An id is
# recycled once a loop is garbage collected, so a short-lived Celery loop could
# inherit the engine of a dead one and hand asyncpg a connection bound to a
# closed loop -- precisely the cross-loop error NullPool existed to prevent.
# Keying on the object drops the entry automatically when the loop dies.
_engines: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_sessionmakers: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()

POOL_SIZE = 5
MAX_OVERFLOW = 5
POOL_TIMEOUT = 30


def set_server_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Latch the loop that serves requests. Called once from the app lifespan."""
    global _server_loop
    _server_loop = loop


def server_loop_is_registered() -> bool:
    """True when a server loop has been latched. Tests assert on this."""
    return _server_loop is not None


def get_async_engine():
    """The async engine for the currently running loop.

    Pooled on the latched server loop, NullPool everywhere else. Raises rather
    than falling back, because guessing here is what produces the cross-loop
    error the NullPool default existed to prevent.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError(
            "get_async_engine() requires a running event loop; "
            "a sync engine (SyncSessionLocal) is the right choice here"
        ) from None

    engine = _engines.get(running)
    if engine is not None:
        return engine

    if running is _server_loop:
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_pre_ping=True,
        )
        logger.info("pooled async engine created for the server loop")
    else:
        # Ephemeral loop: never pool.
        engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True, poolclass=NullPool)

    _engines[running] = engine
    return engine


def get_sessionmaker() -> async_sessionmaker:
    """Session factory bound to the current loop's engine."""
    running = asyncio.get_running_loop()
    maker = _sessionmakers.get(running)
    if maker is None:
        maker = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        _sessionmakers[running] = maker
    return maker


async def dispose_async_engines() -> None:
    """Close every engine handed out, so shutdown leaves no backend behind."""
    for loop, engine in list(_engines.items()):
        with suppress(Exception):
            await engine.dispose()
        with suppress(Exception):
            _engines.pop(loop, None)
    with suppress(Exception):
        _sessionmakers.clear()


AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Sync Engine for Celery tasks, migrations, and CLI seeds
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=3,
    pool_pre_ping=True,
    pool_recycle=300,
)

SyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session, and hand the connection back whatever happens.

    ``asyncio.CancelledError`` inherits from ``BaseException``, not
    ``Exception``, so the original ``except Exception`` never fired when a client
    disconnected mid-request. The rollback was skipped and the ``await`` in the
    ``finally`` was itself cancelled the moment it was reached, so the
    connection stayed checked out with its transaction open. Measured under
    load: 132 connections sitting in ``idle in transaction`` and Postgres
    refusing new ones with "sorry, too many clients already", while the error
    rate stayed at zero because queued requests are not failing requests.

    ``BaseException`` catches cancellation, and ``shield`` keeps the cleanup
    running to completion rather than being torn down with the request.
    """
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except BaseException:
        with suppress(Exception):
            await asyncio.shield(session.rollback())
        raise
    finally:
        with suppress(Exception):
            await asyncio.shield(session.close())


def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except BaseException:
        # BaseException, for the same reason as get_db: a generator closed by
        # cancellation must still roll back rather than leave a transaction open.
        with suppress(Exception):
            db.rollback()
        raise
    finally:
        db.close()
