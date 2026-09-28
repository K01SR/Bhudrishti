from typing import Dict, Any, List, Optional
import json
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.boundary import AdminBoundary

router = APIRouter(prefix="/locations", tags=["Locations & Jurisdictions"])

# Static administrative reference hierarchy used by the guided location search.
# Authority: demo seed for the SIH pilot — Maharashtra is fully populated for the
# Airoli Sector 8 pilot; Karnataka and Gujarat carry shallow entries so the
# cascading lookup (State -> District -> Taluka -> Village) feels national.
ADMIN_HIERARCHY: Dict[str, Any] = {
    "MH": {
        "name": "Maharashtra",
        "districts": {
            "THN": {
                "name": "Thane",
                "talukas": {
                    "THN-THA": {
                        "name": "Thane",
                        "villages": [
                            {"code": "AIR-SEC08", "name": "Airoli Sector 8"},
                            {"code": "WAGLE-IND", "name": "Wagle Estate Industrial Ward"},
                        ],
                    },
                    "THN-BHI": {
                        "name": "Bhiwandi",
                        "villages": [
                            {"code": "BHI-TOWN", "name": "Bhiwandi Town"},
                            {"code": "PADGHA", "name": "Padgha Village"},
                        ],
                    },
                },
            },
            "MSB": {
                "name": "Mumbai Suburban",
                "talukas": {
                    "MSB-AND": {
                        "name": "Andheri",
                        "villages": [
                            {"code": "AND-EAST", "name": "Andheri East"},
                            {"code": "BANDRA-EAST", "name": "Bandra East"},
                        ],
                    },
                },
            },
            "PUN": {
                "name": "Pune",
                "talukas": {
                    "PUN-HAV": {
                        "name": "Haveli",
                        "villages": [
                            {"code": "KOREGAON", "name": "Koregaon Park"},
                            {"code": "SHIVAJI-NAGAR", "name": "Shivajinagar"},
                        ],
                    },
                },
            },
            "NGP": {
                "name": "Nagpur",
                "talukas": {
                    "NGP-RUR": {
                        "name": "Nagpur Rural",
                        "villages": [{"code": "HINGNA-IND", "name": "Hingna Industrial Area"}],
                    },
                },
            },
        },
    },
    "KA": {
        "name": "Karnataka",
        "districts": {
            "BLR": {
                "name": "Bengaluru Urban",
                "talukas": {
                    "BLR-NOR": {
                        "name": "Bengaluru North",
                        "villages": [
                            {"code": "YELAHANKA", "name": "Yelahanka"},
                            {"code": "HEBBAL", "name": "Hebbal"},
                        ],
                    },
                },
            },
            "BEL": {
                "name": "Belagavi",
                "talukas": {
                    "BEL-CITY": {
                        "name": "Belagavi",
                        "villages": [{"code": "MACCHE-IND", "name": "Macche Industrial"}],
                    },
                },
            },
        },
    },
    "GJ": {
        "name": "Gujarat",
        "districts": {
            "AHD": {
                "name": "Ahmedabad",
                "talukas": {
                    "AHD-DAS": {
                        "name": "Daskroi",
                        "villages": [
                            {"code": "NIKOL", "name": "Nikol"},
                            {"code": "NARODA-GIDC", "name": "Naroda GIDC"},
                        ],
                    },
                },
            },
            "SUR": {
                "name": "Surat",
                "talukas": {
                    "SUR-CHO": {
                        "name": "Choryasi",
                        "villages": [{"code": "SACHIN-GIDC", "name": "Sachin GIDC"}],
                    },
                },
            },
        },
    },
}


def resolve_hierarchy(
    state_code: str,
    district_code: str,
    taluka_code: str,
    village_code: str,
) -> Dict[str, Any] | None:
    """Resolves a 4-level code tuple into a flat location object (or None)."""
    state = ADMIN_HIERARCHY.get(state_code)
    if not state:
        return None
    district = state["districts"].get(district_code)
    if not district:
        return None
    taluka = district["talukas"].get(taluka_code)
    if not taluka:
        return None
    village = next((v for v in taluka["villages"] if v["code"] == village_code), None)
    if not village:
        return None
    return {
        "state": state["name"],
        "state_code": state_code,
        "district": district["name"],
        "district_code": district_code,
        "taluka": taluka["name"],
        "taluka_code": taluka_code,
        "village_ward": village["name"],
        "village_code": village_code,
        "jurisdiction_code": f"{state_code}-{district_code}-{village_code}",
    }


@router.get("/states")
async def list_states(db: AsyncSession = Depends(get_db)):
    """Lists all states available in the national PostGIS cadastre (falls back to static)."""
    if (await _db_count(db)) > 0:
        return await _db_level_rows(db, "STATE")
    return [{"code": c, "name": d["name"], "parent_code": None} for c, d in ADMIN_HIERARCHY.items()]


@router.get("/states/{state_code}/districts")
async def list_districts(state_code: str, db: AsyncSession = Depends(get_db)):
    """Lists districts for a state from PostGIS."""
    sc = state_code.upper()
    if (await _db_count(db)) > 0:
        rows = await _db_level_rows(db, "DISTRICT", parent_code=sc)
        if not rows:
            q = select(AdminBoundary).where(
                AdminBoundary.level == "DISTRICT",
                AdminBoundary.state_code == sc,
            ).order_by(AdminBoundary.name)
            res = (await db.execute(q)).scalars().all()
            if res:
                return [{"code": r.code, "name": r.name, "parent_code": r.parent_code} for r in res]
            raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
        return rows
    state = ADMIN_HIERARCHY.get(sc)
    if not state:
        raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
    return [{"code": c, "name": d["name"], "parent_code": sc} for c, d in state["districts"].items()]


@router.get("/states/{state_code}/districts/{district_code}/talukas")
async def list_talukas(state_code: str, district_code: str, db: AsyncSession = Depends(get_db)):
    """Lists talukas for a state + district from PostGIS."""
    dc = district_code.upper()
    if (await _db_count(db)) > 0:
        rows = await _db_level_rows(db, "TALUKA", parent_code=dc)
        if not rows:
            q = select(AdminBoundary).where(
                AdminBoundary.level == "TALUKA",
                (AdminBoundary.parent_code == dc) | (AdminBoundary.district_code == dc),
            ).order_by(AdminBoundary.name)
            res = (await db.execute(q)).scalars().all()
            if res:
                return [{"code": r.code, "name": r.name, "parent_code": r.parent_code} for r in res]
            raise HTTPException(status_code=404, detail=f"District '{district_code}' not found.")
        return rows
    sc = state_code.upper()
    state = ADMIN_HIERARCHY.get(sc)
    if not state:
        raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
    district = state["districts"].get(dc)
    if not district:
        raise HTTPException(status_code=404, detail=f"District '{district_code}' not found.")
    return [{"code": c, "name": t["name"], "parent_code": dc} for c, t in district["talukas"].items()]


@router.get("/states/{state_code}/districts/{district_code}/talukas/{taluka_code}/villages")
async def list_villages(state_code: str, district_code: str, taluka_code: str, db: AsyncSession = Depends(get_db)):
    """Lists villages/wards for a state + district + taluka from PostGIS."""
    tc = taluka_code.upper()
    if (await _db_count(db)) > 0:
        rows = await _db_level_rows(db, "VILLAGE", parent_code=tc)
        if not rows:
            q = select(AdminBoundary).where(
                AdminBoundary.level == "VILLAGE",
                (AdminBoundary.parent_code == tc) | (AdminBoundary.taluka_code == tc),
            ).order_by(AdminBoundary.name)
            res = (await db.execute(q)).scalars().all()
            if res:
                return [{"code": r.code, "name": r.name, "parent_code": r.parent_code} for r in res]
            raise HTTPException(status_code=404, detail=f"Taluka '{taluka_code}' not found.")
        return rows
    sc = state_code.upper()
    dc = district_code.upper()
    state = ADMIN_HIERARCHY.get(sc)
    if not state:
        raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
    district = state["districts"].get(dc)
    if not district:
        raise HTTPException(status_code=404, detail=f"District '{district_code}' not found.")
    taluka = district["talukas"].get(tc)
    if not taluka:
        raise HTTPException(status_code=404, detail=f"Taluka '{taluka_code}' not found.")
    return taluka["villages"]


# --------------------------------------------------------------------------- #
# Full-India DB-backed hierarchy (national boundary ingest backed)
# --------------------------------------------------------------------------- #
async def _db_count(db: AsyncSession) -> int:
    from sqlalchemy import func
    return int((await db.execute(select(func.count(AdminBoundary.id)))).scalar() or 0)


async def _db_level_rows(db: AsyncSession, level: str, parent_code: Optional[str] = None):
    q = select(AdminBoundary).where(AdminBoundary.level == level)
    if parent_code is not None:
        q = q.where(AdminBoundary.parent_code == parent_code)
    rows = (await db.execute(q.order_by(AdminBoundary.name))).scalars().all()
    return [{"code": r.code, "name": r.name, "parent_code": r.parent_code} for r in rows]


@router.get("/services/national")
async def national_status(db: AsyncSession = Depends(get_db)):
    """Reports whether the full-India boundary hierarchy is loaded from PostGIS."""
    from sqlalchemy import func, text
    counts = {}
    if (await _db_count(db)) > 0:
        for lvl in ("STATE", "DISTRICT", "TALUKA", "VILLAGE"):
            counts[lvl.lower() + "s"] = int(
                (await db.execute(
                    select(func.count(AdminBoundary.id)).where(AdminBoundary.level == lvl)
                )).scalar() or 0
            )
        return {"loaded": True, "backend": "postgis", "counts": counts}
    return {"loaded": False, "backend": "static-hierarchy", "counts": {}}


@router.get("/boundaries/{level}")
async def list_boundaries(level: str, db: AsyncSession = Depends(get_db)):
    """Full-India boundary listing for a level: STATE|DISTRICT|TALUKA|VILLAGE."""
    lvl = level.upper()
    if lvl not in ("STATE", "DISTRICT", "TALUKA", "VILLAGE"):
        raise HTTPException(status_code=400, detail="level must be one of STATE/DISTRICT/TALUKA/VILLAGE")
    if (await _db_count(db)) == 0:
        raise HTTPException(status_code=503, detail="National boundaries not ingested yet. Run the boundary_ingest pipeline.")
    return await _db_level_rows(db, lvl)


@router.get("/db/states")
async def db_list_states(db: AsyncSession = Depends(get_db)):
    """States from the national PostGIS hierarchy (falls back to static list)."""
    if (await _db_count(db)) > 0:
        return await _db_level_rows(db, "STATE")
    return [{"code": c, "name": d["name"], "parent_code": None} for c, d in ADMIN_HIERARCHY.items()]


@router.get("/db/states/{state_code}/districts")
async def db_list_districts(state_code: str, db: AsyncSession = Depends(get_db)):
    """Districts of a state from the national hierarchy (fallback: static)."""
    if (await _db_count(db)) > 0:
        rows = await _db_level_rows(db, "DISTRICT", parent_code=state_code.upper())
        if not rows:
            raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
        return rows
    state = ADMIN_HIERARCHY.get(state_code.upper())
    if not state:
        raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
    return [{"code": c, "name": d["name"], "parent_code": state_code.upper()} for c, d in state["districts"].items()]


@router.get("/db/states/{state_code}/districts/{district_code}/talukas")
async def db_list_talukas(state_code: str, district_code: str, db: AsyncSession = Depends(get_db)):
    """Talukas of a state + district from the national hierarchy (fallback: static)."""
    if (await _db_count(db)) > 0:
        rows = await _db_level_rows(db, "TALUKA", parent_code=district_code.upper())
        if not rows:
            raise HTTPException(status_code=404, detail=f"District '{district_code}' not found.")
        return rows
    state = ADMIN_HIERARCHY.get(state_code.upper())
    if not state:
        raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
    district = state["districts"].get(district_code.upper())
    if not district:
        raise HTTPException(status_code=404, detail=f"District '{district_code}' not found.")
    return [{"code": c, "name": t["name"], "parent_code": district_code.upper()} for c, t in district["talukas"].items()]


@router.get("/db/states/{state_code}/districts/{district_code}/talukas/{taluka_code}/villages")
async def db_list_villages(state_code: str, district_code: str, taluka_code: str, db: AsyncSession = Depends(get_db)):
    """Villages of a state + district + taluka (fallback: static)."""
    if (await _db_count(db)) > 0:
        rows = await _db_level_rows(db, "VILLAGE", parent_code=taluka_code.upper())
        if not rows:
            raise HTTPException(status_code=404, detail=f"Taluka '{taluka_code}' not found.")
        return rows
    state = ADMIN_HIERARCHY.get(state_code.upper())
    if not state:
        raise HTTPException(status_code=404, detail=f"State '{state_code}' not found.")
    district = state["districts"].get(district_code.upper())
    if not district:
        raise HTTPException(status_code=404, detail=f"District '{district_code}' not found.")
    taluka = district["talukas"].get(taluka_code.upper())
    if not taluka:
        raise HTTPException(status_code=404, detail=f"Taluka '{taluka_code}' not found.")
    return [{"code": f"{taluka_code.upper()}-{v['code']}", "name": v["name"], "parent_code": taluka_code.upper()} for v in taluka["villages"]]

@router.get("/db/boundaries/geojson/{level}")
async def db_boundaries_geojson(level: str, db: AsyncSession = Depends(get_db)):
    """GeoJSON FeatureCollection for a boundary level (STATE/DISTRICT/TALUKA/VILLAGE).

    Clipped to clean EPSG:4326 polygons ready for MapLibre. Optional
    ``?state_code=IN-<code>`` narrows to one state for lighter payloads.
    """
    lvl = level.upper()
    if lvl not in ("STATE", "DISTRICT", "TALUKA", "VILLAGE"):
        raise HTTPException(status_code=400, detail="level must be one of STATE/DISTRICT/TALUKA/VILLAGE")
    if (await _db_count(db)) == 0:
        raise HTTPException(status_code=503, detail="National boundaries not ingested yet.")
    from sqlalchemy import text
    rows = (await db.execute(
        text(f"""
        SELECT code, name, parent_code,
               ST_AsGeoJSON(geom) AS geojson
        FROM admin_boundaries
        WHERE level = :lvl
        ORDER BY name
        """),
        {"lvl": lvl},
    )).all()
    features = []
    for code, name, parent_code, geojson in rows:
        try:
            g = json.loads(geojson) if geojson else None
        except Exception:
            g = None
        if not g:
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "code": code,
                "name": name,
                "parent_code": parent_code,
                "level": lvl,
            },
            "geometry": g,
        })
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Census 2011 administrative-unit counts
#
# The Census release published how many districts, sub-districts, towns and
# villages each state had in 2011. It published no names, so these endpoints
# answer only "how many" and are kept separate from the name-bearing cascade
# above: a district listed there is one this system can name, and a count here
# is the official total, which is often larger than what is nameable.
# ---------------------------------------------------------------------------


@router.get("/census2011/national")
async def census2011_national():
    """Published India-wide administrative-unit counts, Census 2011."""
    from app.pipelines.census_units import national_counts

    return national_counts()


@router.get("/census2011/states")
async def census2011_states():
    """Per-state administrative-unit counts, Census 2011."""
    from app.pipelines.census_units import PROVENANCE, state_names, state_counts

    rows = []
    for name in state_names():
        entry = state_counts(name)
        if entry:
            rows.append(entry)
    return {
        "census_year": 2011,
        "state_count": len(rows),
        "states": rows,
        "provenance": dict(PROVENANCE),
    }


@router.get("/census2011/states/{state}")
async def census2011_state(state: str):
    """Administrative-unit counts for one state, Census 2011.

    A 404 means the state is not in the release. It never returns a zero,
    because 'not published' and 'none exist' are different facts.
    """
    from app.pipelines.census_units import PROVENANCE, coverage_note, state_counts

    entry = state_counts(state)
    if not entry:
        raise HTTPException(status_code=404, detail=f"no Census 2011 figures published for {state!r}")
    entry = dict(entry)
    entry["provenance"] = dict(PROVENANCE)
    entry["note"] = coverage_note("state")
    return entry


# ---------------------------------------------------------------------------
# LGD village directory
#
# These routes serve the official Local Government Directory: real
# administrative villages with real LGD codes. They replace the synthetic
# admin_boundaries rows for anything a user searches or navigates by place.
#
# They are not a cadastre. No response here carries a parcel boundary, plot
# area, ownership, land use or ULPIN, and callers must not synthesise one.
# ---------------------------------------------------------------------------


@router.get("/lgd/status")
async def lgd_status():
    """Whether the LGD build is present, and its vintage."""
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        return {
            "available": False,
            "detail": "lgd_villages.sqlite has not been built",
            "rebuild": "python scripts/build_lgd_villages.py '<downloadDir*.zip>'",
        }
    meta = lgd_villages.manifest()
    return {
        "available": True,
        "villages": lgd_villages.count_villages(),
        # The directory publishes 36 state/UT entries; Chandigarh carries no
        # revenue villages, so only 35 of them appear in the village table.
        # Reporting a single `states` number would hide that difference, so both
        # figures are stated and named for what they count.
        "state_entities": meta.get("state_entities") or meta.get("states_present"),
        "states_with_villages": meta.get("states_present"),
        "states": meta.get("states_present"),
        "states_note": (
            "The LGD directory publishes 36 state/union-territory entries. Chandigarh "
            "is published with no revenue villages, so 35 appear in this table."
        ),
        "retrieved": meta.get("retrieved_utc"),
        "source_url": meta.get("source_url"),
        "is_cadastre": False,
        "geometry_kind": "none",
        "note": (
            "Administrative village directory: official LGD codes and hierarchy. "
            "Carries no parcel boundaries, ownership, plot area or land use."
        ),
    }


@router.get("/lgd/search")
async def lgd_search(q: str = Query("", description="village name"), limit: int = Query(25, ge=1, le=100)):
    """Search real LGD villages by name, best match first."""
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        raise HTTPException(status_code=503, detail="LGD village directory has not been built")
    return {
        "query": q,
        "count": len(results := lgd_villages.search_villages(q, limit)),
        "results": results,
    }


@router.get("/lgd/states")
async def lgd_states():
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        raise HTTPException(status_code=503, detail="LGD village directory has not been built")
    rows = lgd_villages.list_states()
    return {"count": len(rows), "states": rows}


@router.get("/lgd/states/{state_name}/districts")
async def lgd_districts(state_name: str):
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        raise HTTPException(status_code=503, detail="LGD village directory has not been built")
    rows = lgd_villages.list_districts(state_name)
    if not rows:
        raise HTTPException(status_code=404, detail=f"no LGD districts for {state_name!r}")
    return {"state": state_name, "count": len(rows), "districts": rows}


@router.get("/lgd/states/{state_name}/districts/{district_name}/subdistricts")
async def lgd_subdistricts(state_name: str, district_name: str):
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        raise HTTPException(status_code=503, detail="LGD village directory has not been built")
    rows = lgd_villages.list_subdistricts(state_name, district_name)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"no LGD sub-districts for {district_name!r} in {state_name!r}",
        )
    return {
        "state": state_name,
        "district": district_name,
        "count": len(rows),
        "subdistricts": rows,
    }


@router.get("/lgd/subdistricts/{subdistrict_code}/villages")
async def lgd_villages_in_subdistrict(subdistrict_code: str):
    """Every LGD village in one sub-district."""
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        raise HTTPException(status_code=503, detail="LGD village directory has not been built")
    rows = lgd_villages.villages_in_subdistrict(subdistrict_code)
    if not rows:
        raise HTTPException(
            status_code=404, detail=f"no LGD villages in sub-district {subdistrict_code!r}"
        )
    return {"subdistrict_code": subdistrict_code, "count": len(rows), "villages": rows}


@router.get("/lgd/villages/{village_code}")
async def lgd_village(village_code: str):
    """One real LGD village record, by official LGD village code."""
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        raise HTTPException(status_code=503, detail="LGD village directory has not been built")
    record = lgd_villages.get_village(village_code)
    if not record:
        raise HTTPException(status_code=404, detail=f"no LGD village with code {village_code!r}")
    return record


@router.get("/lgd/villages/{village_code}/locate")
async def lgd_village_locate(village_code: str):
    """Resolve a real LGD village to a real coordinate on the map.

    The directory itself publishes no geometry, so the position comes from
    OpenStreetMap's Nominatim geocoder, queried with the village's own district
    and state to disambiguate the many places in India that share a name. The
    result is a *geocoded centroid*, not a survey measurement, so it is returned
    with the match it achieved and the query that produced it. An unresolved
    village is reported as unresolved rather than dropped at a guessed location.
    """
    from app.pipelines import lgd_villages
    from app.sources.base import NoAuthenticSourceError
    from app.sources.nominatim import geocode_place

    if not lgd_villages.is_available():
        raise HTTPException(status_code=503, detail="LGD village directory has not been built")

    village = lgd_villages.get_village(village_code)
    if not village:
        raise HTTPException(status_code=404, detail=f"no LGD village with code {village_code!r}")

    try:
        position = geocode_place(
            village["village_name"],
            district_name=village["district_name"],
            subdistrict_name=village["subdistrict_name"],
            state_name=village["state_name"],
        )
    except NoAuthenticSourceError as exc:
        # The village is real; only the geocoder is down. Say which, and keep
        # the record usable for everything that does not need a coordinate.
        return {
            "village": village,
            "located": False,
            "detail": f"geocoder unavailable: {exc}",
            "provenance": village["provenance"],
        }

    return {"village": village, "located": position.get("found", False), **position}
