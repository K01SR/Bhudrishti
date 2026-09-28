"""Purge the generated national parcel/twin layer.

Why this exists
---------------
``app/scripts/seed_mumbai_metropolitan.py`` and
``app/scripts/national_bulk.py`` generated 45,489 ``national_parcels`` rows
procedurally: 45-60 rectangles per locality on a synthetic grid, under
``random.seed(42)``. Those rows were not merely synthetic, they were synthetic
while *asserting government provenance*:

* 1,166 rows carried ``derivation->>'source' = 'MMRDA_CADASTRAL_DIRECT'``,
  naming the Mumbai Metropolitan Region Development Authority as the origin.
  The value came from a seeded RNG. The real Maharashtrian CTS survey format is
  ``CTS-9295/B`` and the generated rows reproduced it exactly, so a reader
  comparing a row against a genuine 7/12 would see a plausible match.
* 44,323 more rows carried no provenance label but were equally generated.
* ``national_twins`` carried 45,489 FSI verdicts computed from that invented
  geometry: 24,119 ``PASS`` and 21,351 ``EXCEEDED``. A regulatory compliance
  verdict on a parcel that does not exist is the most serious class of error
  this system can emit, because it is indistinguishable from a real one to
  anyone reading the response.

``GET /parcels/{ulpin}`` also synthesised, per parcel, four floors at 3.2 m,
16 strata units with areas and volumes, an ``OWNERSHIP`` right for a
"Registered Allottee" holding 100%, a permitted-FAR limit and a
``status: "APPROVED"``. None of it was sourced. All of it was reachable without
a demo-mode flag.

What is preserved
-----------------
``national_twins`` rows are kept rather than dropped, so the 3D/explode layer
still has geometry to render, but every FSI verdict is nulled with an explicit
reason and the geometry is marked as modelled-from-synthetic. It is a showcase
asset, never a land record.

The 12 genuine OSM parcels ingested via ``POST /parcels/ingest-area`` live in
the separate ``parcels``/``structures`` tables and are not touched here.

Usage
-----
    python -m app.cli.purge_national_parcels            # dry run
    python -m app.cli.purge_national_parcels --apply    # backup, then delete
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

# The reason recorded against every nulled FSI verdict.
VERDICT_REASON = "nulled: parcel geometry was procedurally generated, not surveyed"


def _data_dir() -> Path:
    """Repo/container data directory.

    In the container the app lives at /app/app, so /app/data is the data dir.
    Locally the package is at <repo>/backend/app, so the repo's data/ is used.
    Resolved from this file rather than assumed, so a snapshot never lands
    outside the repository.
    """
    if Path("/app/data").is_dir():
        return Path("/app/data")
    # .../backend/app/cli/purge_national_parcels.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / "data"


_SNAPSHOT_DIR = _data_dir() / "purge_backups"


async def survey(conn) -> dict:
    parcels = (await conn.execute(text(
        "SELECT ulpin, survey_number, boundary_code, area_m2, derivation->>'source' AS claimed_source "
        "FROM national_parcels ORDER BY ulpin"
    ))).mappings().all()
    claimed = (await conn.execute(text(
        "SELECT derivation->>'source' AS src, count(*) FROM national_parcels "
        "GROUP BY 1 ORDER BY 2 DESC"
    ))).mappings().all()
    verdicts = (await conn.execute(text(
        "SELECT coalesce(fsi_status, '<null>') AS v, count(*) FROM national_twins GROUP BY 1 ORDER BY 2 DESC"
    ))).mappings().all()
    twins = await conn.scalar(text("SELECT count(*) FROM national_twins"))
    return {
        "parcels": [dict(r) for r in parcels],
        "claimed_sources": {str(r["src"]): int(r["count"]) for r in claimed},
        "fsi_verdicts": {str(r["v"]): int(r["count"]) for r in verdicts},
        "twins": int(twins or 0),
    }


async def backup(report: dict) -> Path:
    """Write a JSON snapshot so the deletion is reversible.

    ``pg_dump`` was unavailable in the backend container when this was written,
    so the JSON path is the primary mechanism rather than a fallback.
    """
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _SNAPSHOT_DIR / f"national_parcels_before_purge_{stamp}.json"
    try:
        out = subprocess.run(
            ["pg_dump", "--data-only", "--table=public.national_parcels", "--table=public.national_twins",
             "--file", str(path.with_suffix(".sql"))],
            capture_output=True, text=True, timeout=300,
        )
        if out.returncode == 0:
            print(f"Backup written: {path.with_suffix('.sql')}")
            return path.with_suffix(".sql")
        print(f"WARNING: pg_dump failed ({out.stderr.strip()[:160]}); writing JSON snapshot instead")
    except FileNotFoundError:
        print("pg_dump unavailable; writing JSON snapshot")
    path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Backup written: {path}")
    return path


async def main() -> int:
    parser = argparse.ArgumentParser(description="Purge the generated national parcel/twin layer")
    parser.add_argument("--apply", action="store_true", help="perform the deletion (default: dry run)")
    parser.add_argument("--keep-twins", action="store_true",
                        help="also delete national_twins instead of only nulling their verdicts")
    args = parser.parse_args()

    async with async_engine.begin() as conn:
        report = await survey(conn)
        print("Generated national records found:")
        print(f"  parcels           : {len(report['parcels'])}")
        print(f"  twins             : {report['twins']}")
        print("  claimed provenance:")
        for src, n in report["claimed_sources"].items():
            print(f"      {src or '<none>':<28} {n}")
        print("  FSI verdicts on generated geometry:")
        for verdict, n in report["fsi_verdicts"].items():
            print(f"      {verdict:<28} {n}")

        if not report["parcels"]:
            print("\nNothing to purge.")
            return 0

        if not args.apply:
            print("\nDry run. Re-run with --apply to delete (a backup is taken first).")
            return 0

        await backup(report)

        # The twin model gained these columns as part of this cleanup.
        for ddl in (
            "ALTER TABLE national_twins ADD COLUMN IF NOT EXISTS fsi_status_reason varchar(200)",
            "ALTER TABLE national_twins ADD COLUMN IF NOT EXISTS provenance jsonb",
        ):
            await conn.execute(text(ddl))

        # Null the verdicts before removing the parcels they were computed from,
        # so no PASS/EXCEEDED value ever outlives its fabricated geometry. The
        # numeric fsi goes too: it was derived from the same invented plot.
        await conn.execute(
            text(
                "UPDATE national_twins SET fsi = NULL, fsi_status = NULL, fsi_status_reason = :reason, "
                "provenance = coalesce(provenance,'{}'::jsonb) || jsonb_build_object("
                "'geometry_basis', 'modelled_from_synthetic_parcel', 'authoritative', false)"
            ),
            {"reason": VERDICT_REASON},
        )
        if args.keep_twins:
            await conn.execute(text("DELETE FROM national_twins"))

        await conn.execute(text("DELETE FROM national_parcels"))

        after = await survey(conn)
        print(f"\nDeleted. Remaining generated parcels: {len(after['parcels'])}")
        if not args.keep_twins:
            print(f"Twins retained as modelled geometry: {after['twins']} (FSI verdicts nulled)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
