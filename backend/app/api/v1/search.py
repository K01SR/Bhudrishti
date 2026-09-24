from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from sqlalchemy import text
from app.core.database import async_engine
from app.core.demo_gate import demo_mode_enabled, load_demo_dataset

router = APIRouter(prefix="/search", tags=["Global Spatial Search"])

_DATASET = load_demo_dataset()


def _polygon_centroid(coords: Any) -> List[float]:
    """Centroid of the outer ring of a GeoJSON Polygon in the local EPSG:7755 grid."""
    ring = coords["coordinates"][0] if isinstance(coords, dict) else coords
    pts = [p for p in ring[:-1]] if ring and ring[0] == ring[-1] else ring
    n = len(pts)
    if n == 0:
        return [0.0, 0.0]
    xs = sum(p[0] for p in pts) / n
    ys = sum(p[1] for p in pts) / n
    return [round(xs, 2), round(ys, 2)]


def _normalize(q: str) -> str:
    return (q or "").strip().upper().replace(" ", "")


LEVEL_ZOOM = {
    "STATE": 6.5,
    "DISTRICT": 9.5,
    "TALUKA": 12.0,
    "VILLAGE": 14.0,
}

LEVEL_RADIUS = {
    "STATE": 250000.0,
    "DISTRICT": 45000.0,
    "TALUKA": 12000.0,
    "VILLAGE": 3000.0,
}

ALIAS_MAP = {
    "BENGALURU": "BANGALORE",
    "BANGALORE": "BENGALURU",
    "BOMBAY": "MUMBAI",
    "MUMBAI": "BOMBAY",
    "CALCUTTA": "KOLKATA",
    "KOLKATA": "CALCUTTA",
    "MADRAS": "CHENNAI",
    "CHENNAI": "MADRAS",
    "GURGAON": "GURUGRAM",
    "GURUGRAM": "GURGAON",
    "PONDICHERRY": "PUDUCHERRY",
    "PUDUCHERRY": "PONDICHERRY",
    "ALLAHABAD": "PRAYAGRAJ",
    "PRAYAGRAJ": "ALLAHABAD",
    "ORISSA": "ODISHA",
    "ODISHA": "ORISSA",
}


@router.get("")
async def search(
    q: str = Query("", description="Search ULPIN, survey number, state, district, taluka, village, building or code"),
    limit: int = Query(25, ge=1, le=100),
    mode: str = Query(
        "all",
        pattern="^(all|places|records)$",
        description=(
            "all: every index, each result individually labelled (default). "
            "places: only the real LGD gazetteer and place assets. "
            "records: only the generated land-record/parcel indices."
        ),
    ),
):
    """
    Consolidated global spatial search across India.

    Searches across, in result order:
    1. 15,091 Administrative Boundaries (States, Districts, Talukas, Villages) in PostGIS.
    2. 44,323 National Parcels (by ULPIN or survey number) in PostGIS.
    3. 44,323 National 3D Twins (by structure code or ULPIN) in PostGIS.
    4. The real LGD village directory, by official village name and code.
    5. Pilot Precinct Assets (B-17 hero, units, subsurface utilities, elevated corridors).

    Only group 4 is a real administrative gazetteer. The PostGIS boundary and
    parcel rows and the pilot assets are generated demo data and are marked as
    such in the payload.

    ``mode`` exists because mixing them in one list is the problem, not the
    solution: a caller asking for a village name and a caller asking for a land
    record want different things and must not have to filter by reading a
    provenance field on every row. ``places`` returns the real gazetteer only;
    ``records`` returns the generated record indices only.

    Returns exact spatial coordinates (lng/lat/center), zoom guidance, and metadata
    enabling the UI to fly the camera directly to any entity across India.
    """
    clean_q = (q or "").strip()
    qq = _normalize(clean_q)
    # Direct callers (tests, internal code) pass a plain string; FastAPI passes
    # the Query wrapper. Comparing the wrapper against "all" silently failed and
    # made every mode check dead for non-HTTP callers.
    mode = getattr(mode, "default", mode) or "all"
    results: List[Dict[str, Any]] = []

    def add(kind, title, subtitle, status, focus, extra=None, id_value=None):
        results.append({
            "kind": kind,
            "id": id_value or title,
            "title": title,
            "subtitle": subtitle,
            "status": status,
            "focus": focus,
            "is_hero": bool(extra and extra.get("is_hero")),
            "has_3d": bool(extra and extra.get("has_3d", True)),
            **(extra or {}),
        })

    # 1. Search Admin Boundaries in PostGIS
    #
    # Groups 1-3 are the generated record/boundary index; group 4 is the real
    # gazetteer. `mode` is applied here rather than by filtering at the end, so a
    # `places` query never pays for the PostGIS scans and never returns a row the
    # caller has to discard.
    if clean_q and mode != "places":
        alias = ALIAS_MAP.get(clean_q.upper(), clean_q)
        pattern = f"%{clean_q}%"
        alias_pattern = f"%{alias}%"

        # `national_parcels` and `national_twins` only ever held procedurally
        # generated geometry (see app/scripts/seed_mumbai_metropolitan.py).
        # These two sections read them directly rather than through the demo
        # dataset, so nothing stopped them returning generated records after
        # the gate was shut -- the rows are still in the database. A
        # real-data-only deployment must not search them at all, so the sections
        # are skipped entirely rather than filtered down to nothing.
        generated_records = demo_mode_enabled()

        # TALUKA and VILLAGE rows in admin_boundaries are grid-synthesised
        # subdivisions clipped to a real parent. Each one is labelled
        # `authoritative: false` in the response below, but a real-data-only
        # deployment should not return them either: an honest label on a
        # generated subdivision is still a generated subdivision. ADM1/ADM2
        # carry real geoBoundaries geometry and are always searched.
        synthetic_boundary_filter = (
            "" if generated_records else "AND COALESCE(source, 'unknown') <> 'synthetic'"
        )

        try:
            async with async_engine.connect() as conn:
                # Query boundaries
                #
                # `source` is selected because the table mixes two provenances:
                # ADM1 states and ADM2 districts carry real geoBoundaries
                # geometry, while TALUKA and VILLAGE are grid-synthesised
                # subdivisions clipped to a real parent. A search row that
                # presented both as "Admin Code" let a generated subdivision
                # read as an official boundary.
                b_res = await conn.execute(
                    text(f"""
                        SELECT name, code, level, state_code, COALESCE(source, 'unknown') AS source,
                               ST_X(ST_Centroid(geom)) as lng,
                               ST_Y(ST_Centroid(geom)) as lat
                        FROM admin_boundaries
                        WHERE (unaccent(name) ILIKE unaccent(:pattern)
                           OR unaccent(name) ILIKE unaccent(:alias_pattern)
                           OR code ILIKE :pattern)
                          {synthetic_boundary_filter}
                        ORDER BY CASE level
                            WHEN 'STATE' THEN 1
                            WHEN 'DISTRICT' THEN 2
                            WHEN 'TALUKA' THEN 3
                            ELSE 4 END, name ASC
                        LIMIT :limit
                    """),
                    {"pattern": pattern, "alias_pattern": alias_pattern, "limit": min(limit, 15)},
                )
                for b in b_res.fetchall():
                    b_name, b_code, b_level, b_state, b_source, lng, lat = b
                    z = LEVEL_ZOOM.get(b_level, 10.0)
                    r = LEVEL_RADIUS.get(b_level, 25000.0)
                    b_real = b_source != "synthetic"
                    add(
                        "jurisdiction",
                        f"{b_name} ({b_level.capitalize()})",
                        (
                            f"{'Real boundary' if b_real else 'Modelled subdivision'} • "
                            f"{b_source} • State: {b_state}"
                        ),
                        "ACTIVE",
                        {"center": [round(lng, 5), round(lat, 5), 0.0], "height": 0.0, "radius": r},
                        {
                            "code": b_code,
                            "level": b_level,
                            "state_code": b_state,
                            "source": b_source,
                            "data_provenance": "geoboundaries" if b_real else "demo-generated",
                            "authoritative": b_real,
                            "geometry_note": (
                                None if b_real else
                                "Grid-synthesised subdivision clipped to a real parent "
                                "boundary. Not an official administrative boundary."
                            ),
                            "zoom": z,
                            "lng": round(lng, 5),
                            "lat": round(lat, 5),
                            "has_3d": False,
                        },
                        id_value=b_code,
                    )

                # Sections 2 and 3 are skipped entirely while the gate is shut:
                # the tables behind them are written only by the generated
                # seeder and their rows are not real records. See
                # `generated_records` above.
                if generated_records:
                    # 2. Query National Parcels in PostGIS
                    p_res = await conn.execute(
                        text("""
                            SELECT ulpin, survey_number, zonal_class, state_code, boundary_code,
                                   ST_X(ST_Centroid(geom)) as lng,
                                   ST_Y(ST_Centroid(geom)) as lat
                            FROM national_parcels
                            WHERE ulpin ILIKE :pattern
                               OR survey_number ILIKE :pattern
                            LIMIT :limit
                        """),
                        {"pattern": pattern, "limit": min(limit, 10)},
                    )
                    for p in p_res.fetchall():
                        ulpin, survey_no, z_class, s_code, b_code, lng, lat = p
                        add(
                            "parcel",
                            f"Parcel {survey_no or ulpin}",
                            f"ULPIN {ulpin} • {z_class} • {s_code}",
                            "ACTIVE",
                            {"center": [round(lng, 5), round(lat, 5), 0.0], "height": 0.0, "radius": 35.0},
                            {
                                "ulpin": ulpin,
                                "survey_number": survey_no,
                                "zonal_class": z_class,
                                "state_code": s_code,
                                "boundary_code": b_code,
                                "zoom": 15.5,
                                "lng": round(lng, 5),
                                "lat": round(lat, 5),
                                "has_3d": True,
                            },
                            id_value=ulpin,
                        )

                    # 3. Query National 3D Twins in PostGIS
                    t_res = await conn.execute(
                        text("""
                            SELECT ulpin, structure_code, name, height_m, floors, fsi, fsi_status,
                                   ST_X(ST_Centroid(footprint_polygon)) as lng,
                                   ST_Y(ST_Centroid(footprint_polygon)) as lat
                            FROM national_twins
                            WHERE unaccent(name) ILIKE unaccent(:pattern)
                               OR structure_code ILIKE :pattern
                               OR ulpin ILIKE :pattern
                            LIMIT :limit
                        """),
                        {"pattern": pattern, "limit": min(limit, 12)},
                    )
                    for t in t_res.fetchall():
                        ulpin, struct_code, b_name, h_m, flrs, fsi_val, fsi_st, lng, lat = t
                        t_title = f"{b_name} ({struct_code})" if b_name else f"Twin {struct_code}"
                        add(
                            "structure",
                            t_title,
                            f"ULPIN {ulpin} • {flrs}F • {h_m:.1f}m • FSI {fsi_val:.2f} ({fsi_st})",
                            fsi_st,
                            {"center": [round(lng, 5), round(lat, 5), round(h_m / 2, 1)], "height": round(h_m, 1), "radius": 45.0},
                            {
                                "ulpin": ulpin,
                                "structure_code": struct_code,
                                "name": b_name,
                                "height_m": h_m,
                                "floors": flrs,
                                "fsi": fsi_val,
                                "zoom": 16.5,
                                "lng": round(lng, 5),
                                "lat": round(lat, 5),
                                "has_3d": True,
                            },
                            id_value=f"TWIN-{ulpin}",
                        )
        except Exception:
            # Fallback gracefully if database table connection is busy
            pass

    # 4. Search the real LGD village directory.
    #
    # These are the only *real* places in this index: official LGD codes and
    # names from the Ministry of Panchayati Raj. They are matched first so a
    # village a user actually names outranks the synthetic pilot rows below.
    #
    # Everything added from here to the pilot group is the gazetteer proper, so
    # `mode=places` keeps exactly this slice and drops the generated groups on
    # either side of it.
    _places_start = len(results)
    #
    # No coordinate is attached here. The directory publishes no geometry, and
    # geocoding is rate-limited to one request per second, so a 25-result page
    # cannot geocode inline. The result carries the official code and the UI
    # calls /locations/lgd/villages/{code}/locate when the row is opened, which
    # is cached and returns a real position or an honest failure.
    if clean_q and mode != "records":
        from app.pipelines import lgd_villages

        if lgd_villages.is_available():
            for village in lgd_villages.search_villages(clean_q, min(limit, 10)):
                prov = village["provenance"]
                add(
                    "village",
                    village["village_name"],
                    (
                        f"LGD {village['village_code']} • "
                        f"{village['subdistrict_name']}, {village['district_name']}, "
                        f"{village['state_name']}"
                    ),
                    "ACTIVE",
                    None,
                    {
                        "source": "lgd",
                        "village_code": village["village_code"],
                        "state_name": village["state_name"],
                        "district_name": village["district_name"],
                        "subdistrict_name": village["subdistrict_name"],
                        "census_2011_code": village["census_2011_code"],
                        "has_focus": False,
                        # The directory publishes no geometry, so there is
                        # nothing to extrude. `has_3d` here means the map can
                        # navigate and show real building footprints once the
                        # village is located, not that this row is 3D geometry.
                        "has_3d": True,
                        "locate_url": f"/api/v1/locations/lgd/villages/{village['village_code']}/locate",
                        "is_cadastre": False,
                        "provenance": prov,
                    },
                    id_value=f"LGD-{village['village_code']}",
                )

    # 5. Search Local Pilot Precinct / Synthetic Data (Hero, Units, Subsurface, Elevated)
    #
    # Generated, so it is part of the record indices and is excluded from a
    # `places` query for the same reason groups 1-3 are.
    hero_p = _DATASET["hero_parcel"]
    hero_s = _DATASET["hero_structure"]
    units: List[Dict[str, Any]] = _DATASET["units"]
    subsurface: List[Dict[str, Any]] = _DATASET["subsurface_objects"]
    elevated: List[Dict[str, Any]] = _DATASET["elevated_objects"]
    all_parcels = [hero_p] + _DATASET["surrounding_parcels"]
    if mode == "places":
        # Generated assets contribute nothing to a places query. Emptying the
        # inputs lets the loops below run unchanged and match nothing, rather
        # than reindenting this whole group behind a mode check.
        results = results[_places_start:]
        all_parcels, units, subsurface, elevated = [], [], [], []
        _pilot_excluded = True
    else:
        _pilot_excluded = False

    for p in all_parcels:
        is_hero = p["ulpin"] == "12345678901234"
        cx, cy = _polygon_centroid(p["polygon_geojson"])
        matches = qq and (qq in _normalize(p["ulpin"]) or qq in _normalize(p.get("survey_number", "")))
        if matches:
            add(
                "parcel",
                f"Pilot Parcel {p.get('survey_number', p['ulpin'])}",
                f"ULPIN {p['ulpin']} • {p.get('document_area_m2', 0):.0f} m²",
                p.get("status", "ACTIVE"),
                {"center": [cx, cy, 0.0], "height": 0.0, "radius": 22.0},
                {"ulpin": p["ulpin"], "is_hero": is_hero, "has_3d": is_hero},
            )

    # Hero structure / building
    s_matches = qq and (qq in _normalize(hero_s["building_code"]) or qq in _normalize(hero_s["name"]))
    if not _pilot_excluded and (s_matches or (not qq and not results)):
        add(
            "structure",
            hero_s["name"],
            f"Building {hero_s['building_code']} • 20 units + basement • {hero_s['height_m']} m",
            hero_s["status"],
            {"center": [160.0, 152.5, 9.0], "height": 18.0, "radius": 40.0},
            {"ulpin": hero_p["ulpin"], "is_hero": True, "has_3d": True},
        )

    for u in units:
        uq = u["proposed_3d_id"]
        uq_hash = _normalize(uq)
        matches = (
            qq
            and (
                qq in uq_hash
                or qq in _normalize(u["unit_number"])
                or qq in _normalize(u["level_code"])
            )
        )
        if matches:
            add(
                "unit",
                f"Unit {u['unit_number']} · {u['level_code']}",
                u["proposed_3d_id"],
                "APPROVED",
                {
                    "center": [
                        round((u["coords"][0][0] + u["coords"][2][0]) / 2, 2) if "coords" in u else 160.0,
                        round((u["coords"][0][1] + u["coords"][2][1]) / 2, 2) if "coords" in u else 152.5,
                        round((u["min_z"] + u["max_z"]) / 2, 2),
                    ],
                    "height": u["max_z"] - u["min_z"],
                    "radius": 12.0,
                },
                {
                    "ulpin": hero_p["ulpin"],
                    "is_hero": True,
                    "has_3d": True,
                    "unit_number": u["unit_number"],
                    "level_code": u["level_code"],
                    "proposed_3d_id": uq,
                },
            )

    for s in subsurface:
        if qq and (qq in _normalize(s["code"]) or qq in _normalize(s.get("proposed_3d_id", ""))):
            g = s.get("geometry_3d", {})
            start = g.get("start", [160.0, 152.5, -4.0])
            end = g.get("end", [160.0, 152.5, -4.0])
            add(
                "subsurface",
                s.get("description", s["code"]),
                f"{s['code']} • {s.get('proposed_3d_id', '')}",
                "CLASH" if s.get("has_clash") else "CLEAR",
                {
                    "center": [
                        round((start[0] + end[0]) / 2, 2),
                        round((start[1] + end[1]) / 2, 2),
                        round((start[2] + end[2]) / 2, 2),
                    ],
                    "height": 4.0,
                    "radius": 14.0,
                },
                {"ulpin": hero_p["ulpin"], "is_hero": True, "has_3d": True, "code": s["code"]},
            )

    for e in elevated:
        if qq and (qq in _normalize(e["code"]) or qq in _normalize(e.get("proposed_3d_id", ""))):
            add(
                "elevated",
                e.get("description", e["code"]),
                f"{e['code']} • {e.get('proposed_3d_id', '')}",
                "ACTIVE",
                {"center": [160.0, 152.5, 6.0], "height": 8.0, "radius": 16.0},
                {"ulpin": hero_p["ulpin"], "is_hero": True, "has_3d": True, "code": e["code"]},
            )

    # If empty query, provide default high-level jurisdictions and hero structure
    if not clean_q and not results and not _pilot_excluded:
        try:
            async with async_engine.connect() as conn:
                st_res = await conn.execute(
                    text("""
                        SELECT name, code, level, state_code, COALESCE(source, 'unknown') AS source,
                               ST_X(ST_Centroid(geom)) as lng,
                               ST_Y(ST_Centroid(geom)) as lat
                        FROM admin_boundaries
                        WHERE level = 'STATE'
                        ORDER BY name ASC
                        LIMIT 6
                    """)
                )
                for b in st_res.fetchall():
                    b_name, b_code, b_level, b_state, b_source, lng, lat = b
                    add(
                        "jurisdiction",
                        f"{b_name} (State)",
                        f"Real boundary • {b_source}",
                        "ACTIVE",
                        {"center": [round(lng, 5), round(lat, 5), 0.0], "height": 0.0, "radius": 250000.0},
                        {
                            "code": b_code,
                            "level": b_level,
                            "state_code": b_state,
                            "source": b_source,
                            "data_provenance": "geoboundaries" if b_source != "synthetic" else "demo-generated",
                            "authoritative": b_source != "synthetic",
                            "zoom": 6.5,
                            "lng": round(lng, 5),
                            "lat": round(lat, 5),
                            "has_3d": False,
                        },
                        id_value=b_code,
                    )
        except Exception:
            pass

    return {
        "query": q,
        "mode": mode,
        "count": len(results[:limit]),
        "dataset": "bhudrishti_national_and_pilot",
        # Mixed index: real LGD villages alongside generated PostGIS boundaries,
        # parcels, twins and pilot assets. Callers must read each result's
        # `source` and `provenance` rather than assuming the whole page is real.
        "is_mixed_provenance": mode == "all",
        # In `places` mode the page is real end to end, so the flag flips rather
        # than staying true and telling a caller to keep checking every row for
        # a provenance it cannot possibly fail to find.
        "real_sources": ["lgd"],
        "results": results[:limit],
    }