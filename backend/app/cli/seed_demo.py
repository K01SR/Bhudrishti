"""
Seed script to populate PostgreSQL with the demo accounts, jurisdictions,
parcels and Building B-17.

This previously did not seed. It created the schema, generated the synthetic
Airoli dataset in memory, printed three lines describing that dataset, and then
printed "Demo Seeding completed successfully" without writing a single row. The
docstring promised it populated "demo accounts, jurisdictions, parcels, and
Building B-17" and it persisted none of them, so every claim the script printed
about the hero parcel was true of an in-memory object and false of the database.

That mattered beyond the false log line: ``GET /api/v1/properties/hero/scene``
builds its scene from the cadastral store, so with the hero parcel absent it
returned 404, while ``GET /api/v1/properties/hero`` served 200 from the
synthetic dataset held in memory. The same "hero property" was simultaneously
present and absent depending on which endpoint answered. It now persists, and
the summary it prints is derived from the rows actually written.
"""
import asyncio
import json
import sys

from sqlalchemy import func, select, text

from app.core.database import Base, async_engine, get_sessionmaker
from app.models import *  # noqa: F401,F403  (registers every model on Base.metadata)
from app.models.cadastre import Level, Parcel, Structure, Unit
from app.models.jurisdiction import Jurisdiction
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset

# The synthetic generator is demo data, so the seeder must not be able to write
# it into a deployment that has demo mode switched off.
from app.core.demo_gate import require_demo_mode
from app.core.cadastre_store import AIROLI_ORIGIN
from app.core.geometry import utm43n_ring_to_wgs84


def _ring(geojson):
    """First exterior ring of a polygon, as a list of coordinate tuples."""
    coords = (geojson or {}).get("coordinates") or []
    return [tuple(pt) for pt in coords[0]] if coords else []


def _hero_ring_wgs84(hero):
    """The generator's hero ring as genuine WGS84 degrees.

    ``generate_synthetic_airoli_dataset`` emits a local metre ring anchored at
    (0, 0). ``polygon_geojson`` is EPSG:4326 and is what the API serves, so the
    ring is placed at the documented Airoli origin and unprojected before it is
    stored. Skipping this stored metres under a degrees label.
    """
    ring = _ring(hero.get("polygon_geojson"))
    if len(ring) < 4:
        return [[float(x), float(y)] for x, y in ring]
    utm = [
        (AIROLI_ORIGIN["easting"] + float(x), AIROLI_ORIGIN["northing"] + float(y))
        for x, y in ring
    ]
    return [[float(lon), float(lat)] for lon, lat in utm43n_ring_to_wgs84(utm)]


def _holds_local_metres(polygon_geojson) -> bool:
    """True when a stored polygon still holds the generator's local-metre ring.

    Degrees are bounded: |lon| <= 180 and |lat| <= 90. The generator's local
    frame starts at (0, 0) and this hero sits around (140..180, 140..165), where
    the northing is far outside the valid latitude range, so "is this even
    degrees?" settles it without guessing at the district's extent.
    """
    coords = (polygon_geojson or {}).get("coordinates") or []
    if not coords:
        return False
    for pt in coords[0]:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        try:
            lon, lat = float(pt[0]), float(pt[1])
        except (TypeError, ValueError):
            return True
        if abs(lon) > 180.0 or abs(lat) > 90.0:
            return True
    return False


async def seed_demo():
    print("Starting Bhu-Drishti 3D Demo Seeder...")
    require_demo_mode("seed_demo")

    async with async_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.run_sync(Base.metadata.create_all)
    print("Database schema verified / created successfully.")

    dataset = generate_synthetic_airoli_dataset()
    hero = dataset["hero_parcel"]
    hero_struct = dataset["hero_structure"]

    async with get_sessionmaker()() as db:
        # parcels.jurisdiction_id is NOT NULL, so the demo precinct needs a real
        # jurisdiction row. The two that already exist are named INGEST-* and
        # belong to the ingested dataset, so the demo gets its own rather than
        # borrowing one of those and mislabelling the provenance.
        precinct = dataset["precinct"]
        juris_code = "MH-THN-AIR-SEC08"
        jurisdiction = (
            await db.execute(select(Jurisdiction).where(Jurisdiction.code == juris_code))
        ).scalar_one_or_none()
        if jurisdiction is None:
            jurisdiction = Jurisdiction(
                code=juris_code,
                name=precinct.get("name", "Airoli Sector 8"),
                state="Maharashtra",
                district="Thane",
                taluka="Thane",
                village_ward="Ward 08",
            )
            db.add(jurisdiction)
            await db.flush()

        parcel = (
            await db.execute(select(Parcel).where(Parcel.ulpin == hero["ulpin"]))
        ).scalar_one_or_none()

        if parcel is None:
            # parcels.geom is Geometry(POLYGON, 32643) and must not be NULL
            # (tests/test_parcel_geometry_integrity.py asserts it for every row).
            #
            # The generator's ring is in the local metre frame -- coordinates like
            # 140,140 to 180,165 are metres, not degrees. Storing that verbatim as
            # polygon_geojson would be a lie, because polygon_geojson is EPSG:4326
            # and is what clients are served, and it made geom disagree with its
            # own polygon_geojson. So the local ring is converted to real WGS84
            # through the documented Airoli origin first, and geom is derived from
            # the stored polygon with the same PostGIS expression the integrity
            # test uses, so the two cannot drift.
            ring_wgs = _hero_ring_wgs84(hero)

            parcel = Parcel(
                ulpin=hero["ulpin"],
                survey_number=hero.get("survey_number"),
                jurisdiction_id=jurisdiction.id,
                polygon_geojson={"type": "Polygon", "coordinates": [ring_wgs]},
                geom=func.ST_CollectionExtract(
                    func.ST_MakeValid(
                        func.ST_Transform(
                            func.ST_SetSRID(
                                func.ST_GeomFromGeoJSON(
                                    json.dumps({"type": "Polygon", "coordinates": [ring_wgs]})
                                ),
                                4326,
                            ),
                            32643,
                        )
                    ),
                    3,
                ),
                calculated_area_m2=hero.get("calculated_area_m2"),
                gis_area_m2=hero.get("gis_area_m2"),
                document_area_m2=hero.get("document_area_m2"),
                status="PERSISTED",
                data_provenance="synthetic-demo",
                # Explicitly not authoritative: this is generated demo geometry,
                # and the source-status matrix must keep saying so.
                provenance_authoritative=False,
                provenance_detail=(
                    "Generated by app.pipelines.synthetic_generator for the Airoli "
                    "Sector 8 showcase. Demonstration geometry: a synthetic local-metre "
                    "ring placed at the documented Airoli origin and unprojected to "
                    "WGS84. Not a cadastral record and not an authoritative survey."
                ),
            )
            db.add(parcel)
            await db.flush()
            parcel_action = "inserted"
        else:
            # Update the descriptive fields but never overwrite polygon_geojson
            # or a geom that is already present: a repair pass may have fixed
            # those, and clobbering them here would silently reintroduce the
            # geometry bug fixed in 1a6ffe9. geom is only filled when NULL, so
            # re-running is safe after an older seed left it empty.
            parcel.survey_number = hero.get("survey_number") or parcel.survey_number
            parcel.calculated_area_m2 = hero.get("calculated_area_m2") or parcel.calculated_area_m2
            parcel.gis_area_m2 = hero.get("gis_area_m2") or parcel.gis_area_m2
            parcel.data_provenance = "synthetic-demo"
            parcel.provenance_authoritative = False
            parcel_action = "already present"
            if parcel.geom is None or _holds_local_metres(parcel.polygon_geojson):
                ring_wgs = _hero_ring_wgs84(hero)
                poly = {"type": "Polygon", "coordinates": [ring_wgs]}
                parcel.polygon_geojson = poly
                parcel.geom = func.ST_CollectionExtract(
                    func.ST_MakeValid(
                        func.ST_Transform(
                            func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(poly)), 4326),
                            32643,
                        )
                    ),
                    3,
                )
                parcel_action = "already present (geometry normalised to WGS84)"

        structure = (
            await db.execute(
                select(Structure).where(
                    Structure.parcel_id == parcel.id,
                    Structure.building_code == hero_struct["building_code"],
                )
            )
        ).scalar_one_or_none()

        if structure is None:
            structure = Structure(
                parcel_id=parcel.id,
                building_code=hero_struct["building_code"],
                name=hero_struct.get("name"),
                structure_type="RESIDENTIAL_COMMERCIAL",
                footprint_geojson=hero_struct.get("footprint_geojson"),
                ground_elevation_z=hero_struct.get("ground_elevation_z"),
                height_m=hero_struct.get("height_m"),
                floors_count=hero_struct.get("floors_count"),
                basements_count=hero_struct.get("basements_count"),
                total_built_up_area_m2=hero_struct.get("total_built_up_area_m2"),
                calculated_fsi=hero_struct.get("calculated_fsi"),
                is_verified=True,
                data_provenance="synthetic-demo",
                provenance_authoritative=False,
                observed_height_m=hero_struct.get("height_m"),
                height_basis="synthetic-demo",
                extraction_source="synthetic_generator",
            )
            db.add(structure)
            await db.flush()
            structure_action = "inserted"
        else:
            structure_action = "already present"

        # Levels
        levels_by_code = {}
        added_levels = 0
        for lvl in dataset.get("levels", []):
            existing = (
                await db.execute(
                    select(Level).where(
                        Level.structure_id == structure.id,
                        Level.level_code == lvl["level_code"],
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = Level(
                    structure_id=structure.id,
                    level_code=lvl["level_code"],
                    floor_number=lvl.get("floor_number"),
                    name=lvl.get("name"),
                    use=lvl.get("name"),
                    min_z=lvl.get("min_z"),
                    max_z=lvl.get("max_z"),
                    height_m=lvl.get("height_m"),
                    level_type=lvl.get("level_type"),
                    boundary_geojson=lvl.get("boundary_geojson"),
                )
                db.add(existing)
                await db.flush()
                added_levels += 1
            levels_by_code[lvl["level_code"]] = existing

        # Units
        added_units = 0
        for unit in dataset.get("units", []):
            parent = levels_by_code.get(unit.get("level_code"))
            existing = (
                await db.execute(
                    select(Unit).where(
                        Unit.structure_id == structure.id,
                        Unit.unit_number == unit.get("unit_number"),
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    Unit(
                        structure_id=structure.id,
                        level_id=parent.id if parent else None,
                        unit_number=unit.get("unit_number"),
                        proposed_3d_id=unit.get("proposed_3d_id"),
                        unit_type=unit.get("unit_type"),
                        min_z=unit.get("min_z"),
                        max_z=unit.get("max_z"),
                        carpet_area_m2=unit.get("carpet_area_m2"),
                        built_up_area_m2=unit.get("built_up_area_m2"),
                        volume_m3=unit.get("volume_m3"),
                        footprint_geojson=unit.get("footprint_geojson"),
                        status="PERSISTED",
                    )
                )
                added_units += 1
        await db.commit()

    # Re-read, so the summary describes the database rather than the intent.
    async with get_sessionmaker()() as db:
        persisted = (
            await db.execute(
                select(Parcel).where(Parcel.ulpin == hero["ulpin"])
            )
        ).scalar_one_or_none()
        persisted_units = 0
        persisted_levels = 0
        if persisted is not None:
            structure_id = (
                await db.execute(
                    select(Structure.id).where(
                        Structure.parcel_id == persisted.id,
                        Structure.building_code == hero_struct["building_code"],
                    )
                )
            ).scalar_one_or_none()
            if structure_id is not None:
                persisted_levels = len(
                    (
                        await db.execute(
                            select(Level).where(Level.structure_id == structure_id)
                        )
                    ).scalars().all()
                )
                persisted_units = len(
                    (
                        await db.execute(
                            select(Unit).where(Unit.structure_id == structure_id)
                        )
                    ).scalars().all()
                )

    if persisted is None:
        # The previous behaviour was to report success unconditionally. Say so
        # plainly and exit non-zero instead.
        print("ERROR: hero parcel was not persisted. Nothing was written.")
        sys.exit(1)

    print(f"Generated synthetic precinct: {dataset['precinct']['name']}")
    print(
        f"Hero Parcel: {persisted.ulpin} with Building {hero_struct['building_code']} "
        f"({parcel_action}, structure {structure_action})"
    )
    print(
        f"Persisted: {persisted_levels} levels, {persisted_units} units "
        f"(added this run: {added_levels} levels, {added_units} units)"
    )
    print("Demo Seeding completed successfully.")


if __name__ == "__main__":
    asyncio.run(seed_demo())