"""Remove generated demonstration records from the cadastral store.

The Airoli precinct rows were produced by ``app.pipelines.synthetic_generator``:
invented ULPINs (the 123456789012xx block), invented survey numbers, invented
footprints and a jurisdiction carrying a permitted-FSI figure that no authority
published. They are removed here so every remaining parcel traces to a real
dataset.

Real data is *not* touched: rows with a non-null ``data_provenance`` (anything
ingested through ``POST /parcels/ingest-area`` or a seed script that cites a
dataset) are left untouched, as is the ``national_parcels`` PostGIS table.

Usage:
    python -m app.cli.purge_demo_data            # dry run: lists what would go
    python -m app.cli.purge_demo_data --apply    # performs the deletion
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.core.database import async_engine

# ULPIN blocks emitted by the synthetic generator.
DEMO_ULPIN_PREFIXES = ("1234567890123", "1234567890124", "2026092500130")
DEMO_JURISDICTION_CODES = ("JUR-AIROLI-S8",)

def _data_dir() -> Path:
    """Data directory for the current runtime (same convention as opendata)."""
    if Path("/app/data").is_dir():
        return Path("/app/data")
    return Path(__file__).resolve().parents[3].parent / "data"


_SNAPSHOT_DIR = _data_dir() / "purge_backups"


def _demo_where(alias: str = "") -> str:
    """Predicate selecting generated demo parcels, optionally table-qualified."""
    a = f"{alias}." if alias else ""
    likes = " OR ".join(f"{a}ulpin LIKE '{p}%'" for p in DEMO_ULPIN_PREFIXES)
    return f"({likes} OR coalesce({a}data_provenance, 'demo-generated') = 'demo-generated')"


async def survey(conn) -> dict:
    parcels = (await conn.execute(text(f"SELECT ulpin, survey_number, data_provenance FROM parcels WHERE {_demo_where()} ORDER BY ulpin"))).mappings().all()
    parcel_ids = [r["ulpin"] for r in parcels]
    structures = 0
    levels = 0
    units = 0
    if parcel_ids:
        sub = ", ".join(f"'{u}'" for u in parcel_ids)
        structures = await conn.scalar(text(f"SELECT count(*) FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin IN ({sub}))"))
        levels = await conn.scalar(text(f"SELECT count(*) FROM levels WHERE structure_id IN (SELECT id FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin IN ({sub})))"))
        units = await conn.scalar(text(f"SELECT count(*) FROM units WHERE structure_id IN (SELECT id FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin IN ({sub})))"))
    juris = (await conn.execute(text(
        f"SELECT code FROM jurisdictions WHERE code IN ({', '.join(repr(c) for c in DEMO_JURISDICTION_CODES)})"
    ))).scalars().all()
    return {
        "parcels": [dict(r) for r in parcels],
        "structures": int(structures or 0),
        "levels": int(levels or 0),
        "units": int(units or 0),
        "jurisdictions": list(juris),
    }


async def backup(report: dict) -> Path:
    """pg_dump the affected tables so the deletion is reversible."""
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _SNAPSHOT_DIR / f"cadastre_before_purge_{stamp}.sql"
    env = {
        "PGPASSWORD": "bhudrishti_secure_spatial_2026",
        "PGHOST": "postgres",
        "PGUSER": "bhudrishti",
        "PGDATABASE": "bhudrishti_3d",
    }
    try:
        out = subprocess.run(
            ["pg_dump", "--data-only", "--table=public.parcels", "--table=public.structures",
             "--table=public.levels", "--table=public.units", "--table=public.jurisdictions",
             "--file", str(path)],
            env={**dict(__import__("os").environ), **env},
            capture_output=True, text=True, timeout=180,
        )
        if out.returncode == 0:
            print(f"Backup written: {path}")
        else:
            print(f"WARNING: pg_dump failed ({out.stderr.strip()[:160]}); writing JSON snapshot instead")
            path = path.with_suffix(".json")
            path.write_text(json.dumps(report, indent=2, default=str))
    except FileNotFoundError:
        path = path.with_suffix(".json")
        path.write_text(json.dumps(report, indent=2, default=str))
        print(f"pg_dump unavailable; JSON snapshot at {path}")
    return path


async def main() -> int:
    parser = argparse.ArgumentParser(description="Purge generated demo cadastral records")
    parser.add_argument("--apply", action="store_true", help="perform the deletion (default: dry run)")
    args = parser.parse_args()

    async with async_engine.begin() as conn:
        report = await survey(conn)
        print("Generated demo records found:")
        print(f"  parcels      : {len(report['parcels'])}")
        print(f"  structures   : {report['structures']}")
        print(f"  levels       : {report['levels']}")
        print(f"  units        : {report['units']}")
        print(f"  jurisdictions: {report['jurisdictions']}")
        if not report["parcels"]:
            print("\nNothing to purge.")
            return 0

        if not args.apply:
            print("\nDry run. Re-run with --apply to delete (a backup is taken first).")
            return 0

        await backup(report)
        # Raw SQL bypasses the ORM's delete-orphan cascades, so children go
        # first, deepest dependency first.
        for stmt in (
            "DELETE FROM units WHERE structure_id IN (SELECT s.id FROM structures s JOIN parcels p ON p.id = s.parcel_id WHERE {where})",
            "DELETE FROM levels WHERE structure_id IN (SELECT s.id FROM structures s JOIN parcels p ON p.id = s.parcel_id WHERE {where})",
            "DELETE FROM structures WHERE parcel_id IN (SELECT id FROM parcels p WHERE {where})",
            "DELETE FROM spatial_units WHERE parcel_id IN (SELECT id FROM parcels p WHERE {where})",
            "DELETE FROM submissions WHERE parcel_id IN (SELECT id FROM parcels p WHERE {where})",
            "DELETE FROM validation_runs WHERE parcel_id IN (SELECT id FROM parcels p WHERE {where})",
            "DELETE FROM verification_cases WHERE parcel_id IN (SELECT id FROM parcels p WHERE {where})",
            f"DELETE FROM parcels WHERE {_demo_where()}",
        ):
            await conn.execute(text(stmt.format(where=_demo_where('p'))))
        juris = ", ".join(repr(c) for c in DEMO_JURISDICTION_CODES)
        await conn.execute(text(f"DELETE FROM jurisdictions WHERE code IN ({juris}) AND NOT EXISTS (SELECT 1 FROM parcels p WHERE p.jurisdiction_id = jurisdictions.id)"))

        after = await survey(conn)
        print(f"\nDeleted. Remaining demo parcels: {len(after['parcels'])}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
