"""national_bulk: synthesize parcels + extrude twins across ALL of India.

Phase 7 scale-up of the national cadastral layer. Sweeps every VILLAGE
boundary (falling back to child-less TALUKA boundaries so no territory is
skipped) and deterministically synthesizes its parcel lattice, then extrudes
a persisted 3D digital twin for every synthesized parcel. Idempotent by
derived ULPIN, so re-runs are safe and can be resumed.

Usage (inside the backend container):

    docker exec bhudrishti_backend python3 -m app.scripts.national_bulk \
        --parcels --twins --limit 2000
"""

from __future__ import annotations

import argparse
import time

from sqlalchemy import select, text

from app.core.database import SyncSessionLocal
from app.models.boundary import AdminBoundary
from app.pipelines.national_parcels import synthesize_parcels_for_boundary
from app.pipelines.national_twins import extrude_national_parcel


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def synthesize_villages(limit: int | None = None) -> dict:
    with SyncSessionLocal() as db:
        codes = db.execute(
            select(AdminBoundary.code)
            .where(AdminBoundary.level == "VILLAGE")
            .order_by(AdminBoundary.code)
            .limit(limit)
        ).scalars().all()

    done = inserted = recomputed = 0
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        with SyncSessionLocal() as db:
            r = synthesize_parcels_for_boundary(db, code)
        if "error" in r:
            _log(f"  skip {code}: {r['error']}")
            continue
        inserted += r.get("synthesized_new", 0)
        recomputed += r.get("recomputed_existing", 0)
        done += 1
        if i % 500 == 0:
            _log(f"  {i}/{len(codes)} villages, +{inserted} parcels, "
                 f"{time.time()-t0:.0f}s elapsed")
    _log(f"synthesize done: {done} villages, {inserted} new / {recomputed} "
         f"recomputed parcels in {time.time()-t0:.0f}s")
    return {"villages": done, "new_parcels": inserted, "recomputed": recomputed}


def extrude_all(limit: int | None = None) -> dict:
    with SyncSessionLocal() as db:
        ulpins = db.execute(
            text("SELECT ulpin FROM national_parcels ORDER BY ulpin LIMIT :lim")
            if limit is not None
            else text("SELECT ulpin FROM national_parcels ORDER BY ulpin"),
            {"lim": limit} if limit is not None else {},
        ).scalars().all()

    t0 = time.time()
    done = errors = 0
    for i, ulpin in enumerate(ulpins, 1):
        try:
            with SyncSessionLocal() as db:
                extrude_national_parcel(db, ulpin)
            done += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 5:
                _log(f"  extrude fail {ulpin}: {exc}")
        if i % 2000 == 0:
            _log(f"  {i}/{len(ulpins)} twins, {time.time()-t0:.0f}s elapsed")
    _log(f"extrude done: {done} twins ({errors} errors) in {time.time()-t0:.0f}s")
    return {"twins": done, "errors": errors}


def _total(table: str) -> int:
    with SyncSessionLocal() as db:
        return db.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def main() -> None:
    parser = argparse.ArgumentParser(description="Nationwide parcel + twin build.")
    parser.add_argument("--parcels", action="store_true", help="synthesize all villages")
    parser.add_argument("--twins", action="store_true", help="extrude all parcels")
    parser.add_argument("--limit", type=int, default=None, help="cap sweep size")
    args = parser.parse_args()

    if not args.parcels and not args.twins:
        parser.error("choose at least one of --parcels / --twins")

    _log(f"baseline: parcels={_total('national_parcels')} "
         f"twins={_total('national_twins')}")
    if args.parcels:
        synthesize_villages(args.limit)
    if args.twins:
        extrude_all(args.limit)
    _log(f"final: parcels={_total('national_parcels')} "
         f"twins={_total('national_twins')}")


if __name__ == "__main__":
    main()