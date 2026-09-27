"""Make the test database deterministic before pytest runs.

The suite has always been run by hand against whatever database happened to be
lying around, which is why it was never run at all. Two things have to be true
before the tests mean anything:

1. The schema exists. `app.core.cadastre_store.ensure_schema` creates the
   tables; without it every query raises UndefinedTable and the Postgres-backed
   tests error during collection.

2. There is at least one jurisdiction row. `test_builder_disposition` and
   `test_builder_footprint` seed their own throwaway parent rows, but they take
   a `jurisdiction_id` from `SELECT id FROM jurisdictions LIMIT 1` and call
   `.scalar_one()`. On an empty database that raises NoResultFound, so both
   tests failed on a fresh database and passed on a second run only because
   some earlier test had left a jurisdiction behind. That is order dependence,
   not a real pass.

This inserts one demo jurisdiction and nothing else. It is deliberately not a
production seed: `max_fsi` is left NULL, which is what suppresses any FSI
verdict, and `provenance_authoritative` is False because no planning-authority
record was consulted.
"""
import asyncio
import pathlib
import sys


def _bootstrap() -> None:
    # Run from the repo root or from tests/; make `app` importable either way.
    here = pathlib.Path(__file__).resolve()
    for candidate in (here.parents[2] / "backend", here.parents[1] / "backend"):
        if (candidate / "app").is_dir():
            sys.path.insert(0, str(candidate))
            break

    from sqlalchemy import text

    from app.core.cadastre_store import ensure_schema
    from app.core.database import AsyncSessionLocal, sync_engine

    async def create_schema() -> None:
        async with AsyncSessionLocal() as session:
            await ensure_schema(session)

    asyncio.run(create_schema())

    with sync_engine.begin() as conn:
        already = conn.execute(
            text("SELECT count(*) FROM jurisdictions")
        ).scalar_one()
        if already:
            print(f"fixtures: {already} jurisdiction row(s) already present")
            return

        conn.execute(
            text(
                "INSERT INTO jurisdictions "
                "(id, code, name, state, district, taluka, village_ward, "
                " center_lat, center_lng, max_fsi, provenance_authoritative) "
                "VALUES (:id, :code, :name, 'Maharashtra', 'Thane', 'Thane', "
                "        'Ward 08', 19.1557, 72.9984, NULL, false)"
            ),
            {
                "id": "jur-test-0001",
                "code": "TEST-THN-DEMO",
                "name": "Test Jurisdiction (demo fixture)",
            },
        )
        print("fixtures: inserted one demo jurisdiction")


if __name__ == "__main__":
    _bootstrap()
