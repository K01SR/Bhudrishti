"""Phase C1: the schema surfaces a submitter's address and floor names.

Builder-submitted records carry an address and per-floor names/uses, so the
parcel and level tables need those columns. They are added idempotently because
there is no Alembic here: create_all() skips existing tables, so new columns go
in through explicit ALTER TABLE ADD COLUMN IF NOT EXISTS backed by the same
columns on the declarative models.
"""
import pathlib
import ast

import pytest


def test_migration_statements_live_in_ensure_schema():
    """The ALTERs must be part of the bootstrapped schema, not only of this
    test's transcripts."""
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "core" / "cadastre_store.py"
    ).read_text()
    for stmt in (
        "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS address varchar(300)",
        "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS locality varchar(200)",
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS name varchar(200)",
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS use varchar(100)",
    ):
        assert stmt in src, f"{stmt!r} missing from ensure_schema"


def test_models_declare_the_new_columns():
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "models" / "cadastre.py"
    ).read_text()
    tree = ast.parse(src)

    attrs = {
        "parcels": {"address", "locality"},
        "levels": {"name", "use"},
    }
    classes = {
        n.name: {
            a.targets[0].id
            for a in ast.walk(n)
            if isinstance(a, ast.Assign) and isinstance(a.targets[0], ast.Name)
        }
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef)
    }
    for table, cols in attrs.items():
        cls_name = {"parcels": "Parcel", "levels": "Level"}[table]
        for col in cols:
            assert col in classes[cls_name], f"{cls_name}.{col} not declared as a column"


def _postgres_reachable() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import sync_engine
        with sync_engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _postgres_reachable(),
    reason="no Postgres reachable from this environment",
)
def test_migrations_are_idempotent_against_a_live_database():
    """ensure_schema must create the columns without error, and a second run
    must not complain: this is the whole idempotency contract, because the
    fixtures run ensure_schema at every vertical-cadastre run."""
    import asyncio

    from app.core.database import AsyncSessionLocal
    from app.core.cadastre_store import ensure_schema

    async def _run():
        async with AsyncSessionLocal() as db:
            await ensure_schema(db)
        async with AsyncSessionLocal() as db:
            await ensure_schema(db)  # second run must not raise

    asyncio.run(_run())

    from app.core.database import sync_engine
    from sqlalchemy import text

    with sync_engine.connect() as c:
        cols = {
            r[0]
            for r in c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='parcels'"
                )
            )
        }
        assert {"address", "locality"} <= cols
        lcols = {
            r[0]
            for r in c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='levels'"
                )
            )
        }
        assert {"name", "use"} <= lcols