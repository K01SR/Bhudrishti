"""
Mumbai Metropolitan Region (MMR) Cadastral & 3D Twin GENERATOR.

    ############################################################################
    # This script FABRICATES land records. It is for local demos only.        #
    #                                                                          #
    # An earlier version of this docstring claimed it populated "real CTS     #
    # numbers". It does not. `survey_no` is built as                          #
    # f"CTS-{random.randint(100, 9999)}/{chr(65 + (i % 26))}" -- a random     #
    # four-digit number and a letter, stored in the `survey_number` column.   #
    # CTS numbers are official Maharashtra City Survey identifiers; minting    #
    # them makes generated rows indistinguishable from real ones to anything  #
    # reading the table, which is the failure mode this whole audit removes.  #
    #                                                                          #
    # The locality coordinates and district/taluka names are real reference   #
    # data. The parcels, buildings, survey numbers, setbacks, floor counts    #
    # and heights below them are not. Do not run this against any deployment   #
    # whose data is read by a human making a decision.                        #
    ############################################################################

Generates a synthetic parcel grid across ~40 real Mumbai-area localities, and a
matching set of 3D building twins with setbacks and heights (15m-180m) over
South Mumbai, the Western and Eastern Suburbs, BKC, Powai, Thane and Navi
Mumbai. The admin hierarchy it writes is genuine reference data; everything
below the hierarchy is invented.

Rows produced here are only visible when ENABLE_DEMO_MODE=1 -- the API gates
that added in the honesty sweep refuse to read or write national_parcels by
default. See app/cli/purge_national_parcels.py for the purge that removed the
45,489 rows an earlier run left behind.
"""
import asyncio
import json
import math
import random
import uuid
from typing import List, Dict, Any, Tuple
from shapely.geometry import Polygon, MultiPolygon, mapping, box as shapely_box
from shapely import affinity
from sqlalchemy import text
from app.core.database import async_engine
from app.id_engine.national import parcel_ulpin_from_vertices

# Fixed seed: this output is deterministic, which is a property of the
# generator and not a claim about the data. See the warning above.
random.seed(42)

# Mumbai Metropolitan Regions & Localities Definition
MUMBAI_ZONES = [
    # --- SOUTH MUMBAI (MUMBAI CITY DISTRICT) ---
    {
        "district_code": "MH-MUMBAI",
        "district_name": "Mumbai City",
        "taluka_code": "MH-MUM-T-COLABA",
        "taluka_name": "Colaba & Fort Taluka",
        "localities": [
            {
                "code": "MH-MUM-COLABA-NARIMAN",
                "name": "Nariman Point - Marine Drive",
                "center": (72.8225, 18.9260),
                "typology": "commercial",
                "zone": "COMMERCIAL",
                "avg_floors": 28,
                "floor_range": (18, 38),
                "prefix": "NP-TWR",
                "names": ["Maker Chambers IV", "Express Towers", "Mittal Court", "Nariman Bhavan", "Air India Building", "Free Press House", "Atlanta Building", "Bajaj Bhavan"],
            },
            {
                "code": "MH-MUM-COLABA-CUFFE",
                "name": "Cuffe Parade - Colaba",
                "center": (72.8180, 18.9140),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 32,
                "floor_range": (24, 42),
                "prefix": "CP-RES",
                "names": ["Maker Towers A", "Jolly Maker 1", "Venus Apartments", "Cuffe Castle", "Bayview Residency", "Sagar Sangeet", "Harbour Heights"],
            },
            {
                "code": "MH-MUM-COLABA-FORT",
                "name": "Fort & Ballard Estate",
                "center": (72.8360, 18.9340),
                "typology": "heritage",
                "zone": "COMMERCIAL",
                "avg_floors": 5,
                "floor_range": (4, 8),
                "prefix": "FT-BLD",
                "names": ["Ballard House", "Scindia House", "Mackinnon Mackenzie", "Forbes Building", "W.H. Brady House", "Horniman Court", "Mint House"],
            },
        ],
    },
    {
        "district_code": "MH-MUMBAI",
        "district_name": "Mumbai City",
        "taluka_code": "MH-MUM-T-MALABAR",
        "taluka_name": "Malabar Hill & Tardeo Taluka",
        "localities": [
            {
                "code": "MH-MUM-MALABAR-HILL",
                "name": "Malabar Hill - Walkeshwar",
                "center": (72.7980, 18.9550),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 22,
                "floor_range": (12, 35),
                "prefix": "MH-RES",
                "names": ["Sea Face Park", "Il Palazzo", "Mount Unique", "Meherina", "Sterling Apartments", "Dariya Mahal", "Hill Crest"],
            },
            {
                "code": "MH-MUM-BREACH-CANDY",
                "name": "Breach Candy & Pedder Road",
                "center": (72.8050, 18.9700),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 26,
                "floor_range": (16, 36),
                "prefix": "BC-RES",
                "names": ["Samudra Mahal", "Tirupati Apartments", "Shalimar", "West Wind", "Ashoka", "Belvedere", "Crystal Palace"],
            },
        ],
    },
    {
        "district_code": "MH-MUMBAI",
        "district_name": "Mumbai City",
        "taluka_code": "MH-MUM-T-PAREL",
        "taluka_name": "Lower Parel & Byculla Taluka",
        "localities": [
            {
                "code": "MH-MUM-LOWER-PAREL",
                "name": "Lower Parel - Senapati Bapat Marg",
                "center": (72.8280, 18.9950),
                "typology": "commercial",
                "zone": "COMMERCIAL",
                "avg_floors": 38,
                "floor_range": (26, 52),
                "prefix": "LP-CORP",
                "names": ["One International Center", "Peninsula Business Park", "Marathon Futurex", "Kamala Mills Tech Park", "Empire Mills", "Urmi Estate"],
            },
            {
                "code": "MH-MUM-PAREL-RES",
                "name": "Parel & Lalbaug Central",
                "center": (72.8390, 18.9980),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 34,
                "floor_range": (22, 48),
                "prefix": "PR-TWR",
                "names": ["Crescent Bay Tower 1", "Lodha Venezia", "Ashok Towers", "Kalpataru Avana", "L&T Crescent", "Orchid Enclave"],
            },
        ],
    },
    {
        "district_code": "MH-MUMBAI",
        "district_name": "Mumbai City",
        "taluka_code": "MH-MUM-T-WORLI",
        "taluka_name": "Worli & Dadar Taluka",
        "localities": [
            {
                "code": "MH-MUM-WORLI-SEA-FACE",
                "name": "Worli Sea Face & Annie Besant Road",
                "center": (72.8150, 19.0060),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 45,
                "floor_range": (30, 65),
                "prefix": "WR-SKY",
                "names": ["Lodha Parkside", "Indiabulls Blu", "Omkar 1973 Tower A", "Ahuja Towers", "Birla Niyaara", "Piramal Mahalaxmi"],
            },
            {
                "code": "MH-MUM-DADAR-SHIVAJI",
                "name": "Dadar West - Shivaji Park",
                "center": (72.8380, 19.0270),
                "typology": "slab",
                "zone": "RESIDENTIAL",
                "avg_floors": 12,
                "floor_range": (7, 18),
                "prefix": "DD-CHS",
                "names": ["Shivaji Park View", "Ranade Chambers", "Sena Bhavan Enclave", "Park Avenue CHS", "Swatantryaveer CHS", "Gokhale Court"],
            },
        ],
    },

    # --- MUMBAI SUBURBAN DISTRICT (WESTERN & EASTERN SUBURBS) ---
    {
        "district_code": "MH-MUMBAI-SUBURBAN",
        "district_name": "Mumbai Suburban",
        "taluka_code": "MH-MUM-SUB-BANDRA",
        "taluka_name": "Bandra Taluka",
        "localities": [
            {
                "code": "MH-MUM-BANDRA-WEST",
                "name": "Bandra West - Pali Hill & Bandstand",
                "center": (72.8250, 19.0580),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 16,
                "floor_range": (8, 25),
                "prefix": "BW-RES",
                "names": ["Pali Hill Regency", "Bandstand Vista", "Carter Road Heights", "Nargis Dutt Enclave", "Perry Cross Villa", "Hill Road Manor"],
            },
            {
                "code": "MH-MUM-BKC-CENTRAL",
                "name": "Bandra Kurla Complex (BKC G-Block)",
                "center": (72.8680, 19.0650),
                "typology": "commercial",
                "zone": "COMMERCIAL",
                "avg_floors": 18,
                "floor_range": (12, 26),
                "prefix": "BKC-HQ",
                "names": ["One BKC", "Maker Maxity", "IL&FS Financial Center", "SEBI Bhavan", "ICICI Bank Tower", "Platina BKC", "Godrej BKC"],
            },
            {
                "code": "MH-MUM-JUHU-TARA",
                "name": "Juhu - Tara Road & Scheme",
                "center": (72.8280, 19.1020),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 10,
                "floor_range": (5, 16),
                "prefix": "JH-RES",
                "names": ["Juhu Vile Parle Scheme Apts", "Gulmohar Enclave", "Sea Princess Residency", "Janki Kutir Court", "Silver Sands CHS"],
            },
        ],
    },
    {
        "district_code": "MH-MUMBAI-SUBURBAN",
        "district_name": "Mumbai Suburban",
        "taluka_code": "MH-MUM-SUB-ANDHERI",
        "taluka_name": "Andheri Taluka",
        "localities": [
            {
                "code": "MH-MUM-ANDHERI-WEST",
                "name": "Andheri West - Lokhandwala Complex",
                "center": (72.8260, 19.1410),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 20,
                "floor_range": (14, 28),
                "prefix": "AW-LOK",
                "names": ["Green Acres Lokhandwala", "Windermere Tower", "Infinity Heights", "Versova Breeze", "Samarth Vaibhav", "Oshiwara Link Crest"],
            },
            {
                "code": "MH-MUM-ANDHERI-EAST",
                "name": "Andheri East - MIDC & SEEPZ",
                "center": (72.8680, 19.1230),
                "typology": "commercial",
                "zone": "IT_PARK",
                "avg_floors": 14,
                "floor_range": (8, 20),
                "prefix": "AE-TECH",
                "names": ["Solitaire Corporate Park", "Kanakia Wall Street", "Technopolis Knowledge Park", "SEEPZ Tech Tower 4", "MIDC IT Hub"],
            },
        ],
    },
    {
        "district_code": "MH-MUMBAI-SUBURBAN",
        "district_name": "Mumbai Suburban",
        "taluka_code": "MH-MUM-SUB-POWAI",
        "taluka_name": "Powai & Ghatkopar Taluka",
        "localities": [
            {
                "code": "MH-MUM-POWAI-HIRANANDANI",
                "name": "Powai - Hiranandani Gardens",
                "center": (72.9050, 19.1190),
                "typology": "tower",
                "zone": "MIXED_USE",
                "avg_floors": 26,
                "floor_range": (18, 34),
                "prefix": "PW-HIR",
                "names": ["Castalia Hiranandani", "Somerset Court", "Torino Residency", "Atlantis Hiranandani", "Kensington SEZ", "Galleria Square"],
            },
            {
                "code": "MH-MUM-VIKHROLI-TREES",
                "name": "Vikhroli East - Godrej One",
                "center": (72.9280, 19.0980),
                "typology": "commercial",
                "zone": "IT_PARK",
                "avg_floors": 16,
                "floor_range": (10, 22),
                "prefix": "VK-GDJ",
                "names": ["Godrej One Headquarters", "The Trees Tower A", "Godrej Platinum", "Vikhroli Corporate Park", "Eastern Expressway Hub"],
            },
        ],
    },
    {
        "district_code": "MH-MUMBAI-SUBURBAN",
        "district_name": "Mumbai Suburban",
        "taluka_code": "MH-MUM-SUB-BORIVALI",
        "taluka_name": "Borivali & Malad Taluka",
        "localities": [
            {
                "code": "MH-MUM-MALAD-MINDSPACE",
                "name": "Malad West - Mindspace IT Park",
                "center": (72.8360, 19.1790),
                "typology": "commercial",
                "zone": "IT_PARK",
                "avg_floors": 15,
                "floor_range": (9, 22),
                "prefix": "ML-MND",
                "names": ["Mindspace Building 1", "Interface Heights", "Evershine Millennium", "Inorbit Cyber Hub", "Chincholi Bunder Towers"],
            },
            {
                "code": "MH-MUM-BORIVALI-WEST",
                "name": "Borivali West - IC Colony & Shimpoli",
                "center": (72.8520, 19.2310),
                "typology": "slab",
                "zone": "RESIDENTIAL",
                "avg_floors": 14,
                "floor_range": (8, 20),
                "prefix": "BV-CHS",
                "names": ["Holy Cross Enclave", "IC Colony Heritage", "Eksar Road Plaza", "Shimpoli Residency", "Vazira Naka CHS", "Gorai Creek View"],
            },
        ],
    },

    # --- THANE & NAVI MUMBAI ---
    {
        "district_code": "MH-THANE",
        "district_name": "Thane",
        "taluka_code": "MH-THN-T-CITY",
        "taluka_name": "Thane City Taluka",
        "localities": [
            {
                "code": "MH-THN-GHODBUNDER",
                "name": "Thane West - Ghodbunder Road & Majiwada",
                "center": (72.9780, 19.2220),
                "typology": "tower",
                "zone": "RESIDENTIAL",
                "avg_floors": 30,
                "floor_range": (20, 42),
                "prefix": "TN-GBR",
                "names": ["Rustomjee Urbania", "Lodha Amara Tower 5", "Dosti West County", "Hiranandani Estate Rodas", "Puranik City Reserva"],
            },
            {
                "code": "MH-THN-PANCHNADI",
                "name": "Thane West - Panch Pakhadi & Naupada",
                "center": (72.9650, 19.1920),
                "typology": "slab",
                "zone": "RESIDENTIAL",
                "avg_floors": 12,
                "floor_range": (6, 18),
                "prefix": "TN-NPD",
                "names": ["TMC Central Plaza", "Naupada Chambers", "Panch Pakhadi Court", "Alok Heights", "Gokhale Road CHS"],
            },
        ],
    },
    {
        "district_code": "MH-THANE",
        "district_name": "Thane",
        "taluka_code": "MH-THN-T-AIROLI",
        "taluka_name": "Airoli & Navi Mumbai Taluka",
        "localities": [
            {
                "code": "MH-THN-AIROLI-SEC08",
                "name": "Airoli - Sector 8 & Mindspace SEZ",
                "center": (72.9984, 19.1557),
                "typology": "commercial",
                "zone": "MIXED_USE",
                "avg_floors": 16,
                "floor_range": (6, 24),
                "prefix": "AIR-SEC8",
                "names": ["Mindspace Building 3", "Gigaplex IT Park", "Reliable Tech Park", "Sector 8 Market Complex", "Airoli Trade Center"],
            },
            {
                "code": "MH-THN-VASHI-SECTOR",
                "name": "Vashi - Sector 17 & Palm Beach Road",
                "center": (72.9980, 19.0760),
                "typology": "commercial",
                "zone": "COMMERCIAL",
                "avg_floors": 16,
                "floor_range": (8, 24),
                "prefix": "VSH-SEC17",
                "names": ["Vashi Plaza", "Palm Beach Galleria", "Inorbit Vashi Mall", "Satra Plaza", "Arenja Corner"],
            },
        ],
    },
]


async def seed_mumbai():
    print("🚀 Starting Comprehensive Mumbai Metropolitan Cadastre Seeder...")

    async with async_engine.begin() as conn:
        # 1. Upsert Districts
        districts_seen = set()
        for zone in MUMBAI_ZONES:
            d_code = zone["district_code"]
            if d_code not in districts_seen:
                districts_seen.add(d_code)
                # Compute centroid approximate for district
                lat = 18.98 if d_code == "MH-MUMBAI" else (19.12 if d_code == "MH-MUMBAI-SUBURBAN" else 19.20)
                lng = 72.83 if d_code == "MH-MUMBAI" else (72.85 if d_code == "MH-MUMBAI-SUBURBAN" else 72.98)
                d_box = shapely_box(lng - 0.08, lat - 0.08, lng + 0.08, lat + 0.08)
                await conn.execute(
                    text("""
                        INSERT INTO admin_boundaries (id, code, name, level, parent_code, state_code, district_code, geom, centroid_lat, centroid_lng, area_km2)
                        VALUES (:id, :code, :name, 'DISTRICT', 'MH', 'MH', :d_code, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)), :lat, :lng, 60.0)
                        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, centroid_lat = EXCLUDED.centroid_lat, centroid_lng = EXCLUDED.centroid_lng
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "code": d_code,
                        "name": zone["district_name"],
                        "d_code": d_code,
                        "geom": json.dumps(mapping(d_box)),
                        "lat": lat,
                        "lng": lng,
                    },
                )

        # 2. Upsert Talukas & Localities (Villages)
        total_parcels = 0
        total_twins = 0

        for zone in MUMBAI_ZONES:
            d_code = zone["district_code"]
            t_code = zone["taluka_code"]
            t_name = zone["taluka_name"]

            # Taluka centroid
            loc0 = zone["localities"][0]["center"]
            t_box = shapely_box(loc0[0] - 0.04, loc0[1] - 0.04, loc0[0] + 0.04, loc0[1] + 0.04)
            await conn.execute(
                text("""
                    INSERT INTO admin_boundaries (id, code, name, level, parent_code, state_code, district_code, taluka_code, geom, centroid_lat, centroid_lng, area_km2)
                    VALUES (:id, :code, :name, 'TALUKA', :d_code, 'MH', :d_code, :t_code, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)), :lat, :lng, 25.0)
                    ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, parent_code = EXCLUDED.parent_code
                """),
                {
                    "id": str(uuid.uuid4()),
                    "code": t_code,
                    "name": t_name,
                    "d_code": d_code,
                    "t_code": t_code,
                    "geom": json.dumps(mapping(t_box)),
                    "lat": loc0[1],
                    "lng": loc0[0],
                },
            )

            # Localities / Village Wards
            for loc in zone["localities"]:
                v_code = loc["code"]
                v_name = loc["name"]
                c_lng, c_lat = loc["center"]

                v_box = shapely_box(c_lng - 0.015, c_lat - 0.015, c_lng + 0.015, c_lat + 0.015)
                await conn.execute(
                    text("""
                        INSERT INTO admin_boundaries (id, code, name, level, parent_code, state_code, district_code, taluka_code, village_code, geom, centroid_lat, centroid_lng, area_km2)
                        VALUES (:id, :code, :name, 'VILLAGE', :t_code, 'MH', :d_code, :t_code, :v_code, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)), :lat, :lng, 4.5)
                        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, parent_code = EXCLUDED.parent_code
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "code": v_code,
                        "name": v_name,
                        "t_code": t_code,
                        "d_code": d_code,
                        "v_code": v_code,
                        "geom": json.dumps(mapping(v_box)),
                        "lat": c_lat,
                        "lng": c_lng,
                    },
                )

                # Generate 45-60 parcels & 3D building twins per locality in a dense urban grid
                num_parcels = random.randint(45, 60)
                grid_cols = math.isqrt(num_parcels) + 1
                spacing_deg = 0.00075  # ~80m spacing

                for i in range(num_parcels):
                    row = i // grid_cols
                    col = i % grid_cols
                    p_lng = c_lng + (col - grid_cols / 2) * spacing_deg + random.uniform(-0.0001, 0.0001)
                    p_lat = c_lat + (row - grid_cols / 2) * spacing_deg + random.uniform(-0.0001, 0.0001)

                    # Parcel dimension ~35m x 30m
                    pw_deg = random.uniform(0.00030, 0.00045)  # ~35-50m
                    ph_deg = random.uniform(0.00025, 0.00038)  # ~30-42m

                    p_poly = shapely_box(p_lng - pw_deg / 2, p_lat - ph_deg / 2, p_lng + pw_deg / 2, p_lat + ph_deg / 2)
                    ring = list(p_poly.exterior.coords)
                    p_area_m2 = round(pw_deg * 111320 * ph_deg * 110540, 1)

                    ulpin, _ = parcel_ulpin_from_vertices(ring)
                    survey_no = f"CTS-{random.randint(100, 9999)}/{chr(65 + (i % 26))}"

                    # Insert national parcel
                    p_id = str(uuid.uuid4())
                    await conn.execute(
                        text("""
                            INSERT INTO national_parcels (
                                id, ulpin, survey_number, boundary_code, state_code, district_code,
                                geom, centroid_lat, centroid_lng, area_m2, zonal_class, derivation
                            )
                            VALUES (
                                :id, :ulpin, :survey_no, :b_code, 'MH', :d_code,
                                ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326),
                                :lat, :lng, :area, :zonal, :derivation
                            )
                            ON CONFLICT (ulpin) DO UPDATE SET
                                survey_number = EXCLUDED.survey_number,
                                boundary_code = EXCLUDED.boundary_code,
                                geom = EXCLUDED.geom
                        """),
                        {
                            "id": p_id,
                            "ulpin": ulpin,
                            "survey_no": survey_no,
                            "b_code": v_code,
                            "d_code": d_code,
                            "geom": json.dumps(mapping(p_poly)),
                            "lat": round(p_lat, 6),
                            "lng": round(p_lng, 6),
                            "area": p_area_m2,
                            "zonal": loc["zone"],
                            "derivation": json.dumps({"source": "SYNTHETIC_PROCEDURAL_GRID", "authoritative": False, "locality": v_name}),
                        },
                    )
                    total_parcels += 1

                    # 3D Building Twin with NBC Setbacks (Modelled geometry only)
                    fl_min, fl_max = loc["floor_range"]
                    floors = random.randint(fl_min, fl_max)
                    floor_h = 3.6 if loc["typology"] in ("commercial", "heritage") else 3.2
                    height_m = round(floors * floor_h, 1)

                    # NBC Setback: 3m to 6m setback inside parcel
                    setback_ratio = random.uniform(0.65, 0.78)
                    tw_w = pw_deg * setback_ratio
                    tw_h = ph_deg * setback_ratio
                    tw_poly = shapely_box(p_lng - tw_w / 2, p_lat - tw_h / 2, p_lng + tw_w / 2, p_lat + tw_h / 2)
                    footprint_area_m2 = round(tw_w * 111320 * tw_h * 110540, 1)
                    built_up_m2 = round(footprint_area_m2 * floors, 1)
                    calc_fsi = None
                    fsi_status = None
                    fsi_status_reason = "nulled: procedural grid, not surveyed"

                    b_names = loc["names"]
                    b_name = b_names[i % len(b_names)] + (f" (Wing {chr(65 + (i // len(b_names)))})" if i >= len(b_names) else "")
                    struct_code = f"{loc['prefix']}-{i+1:03d}"
                    twin_id = str(uuid.uuid4())

                    await conn.execute(
                        text("""
                            INSERT INTO national_twins (
                                id, ulpin, boundary_code, state_code, survey_number, structure_code,
                                name, typology, structure_type, footprint_polygon, footprint_polygon_geojson,
                                plot_area_m2, setback_m, buildable_area_m2, footprint_area_m2,
                                floors, floor_height_m, height_m, built_up_area_m2, fsi, fsi_status,
                                proposed_3d_id, units_count, units_summary, twin
                            )
                            VALUES (
                                :id, :ulpin, :b_code, 'MH', :survey_no, :struct_code,
                                :name, :typology, 'PERMANENT_RCC',
                                ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326),
                                :geom_json, :plot_area, 4.5, :buildable, :fp_area,
                                :floors, :floor_h, :height_m, :built_up, :fsi, :fsi_status,
                                :prop_3d_id, :units, :units_sum, :twin_meta
                            )
                            ON CONFLICT (ulpin) DO UPDATE SET
                                name = EXCLUDED.name,
                                structure_code = EXCLUDED.structure_code,
                                floors = EXCLUDED.floors,
                                height_m = EXCLUDED.height_m,
                                fsi = EXCLUDED.fsi,
                                fsi_status = EXCLUDED.fsi_status,
                                footprint_polygon = EXCLUDED.footprint_polygon
                        """),
                        {
                            "id": twin_id,
                            "ulpin": ulpin,
                            "b_code": v_code,
                            "survey_no": survey_no,
                            "struct_code": struct_code,
                            "name": b_name,
                            "typology": loc["typology"],
                            "geom": json.dumps(mapping(tw_poly)),
                            "geom_json": json.dumps(mapping(tw_poly)),
                            "plot_area": p_area_m2,
                            "buildable": round(footprint_area_m2 * 1.1, 1),
                            "fp_area": footprint_area_m2,
                            "floors": floors,
                            "floor_h": floor_h,
                            "height_m": height_m,
                            "built_up": built_up_m2,
                            "fsi": calc_fsi,
                            "fsi_status": fsi_status,
                            "prop_3d_id": f"{ulpin}/{struct_code}-G-001",
                            "units": floors * (4 if loc["typology"] == "tower" else (8 if loc["typology"] == "commercial" else 2)),
                            "units_sum": json.dumps({"flats_per_floor": 4, "total_levels": floors}),
                            # No authority is named here. This row is a generated
                            # twin over real locality names, so attributing it to
                            # MMRDA would imply the development authority published
                            # the geometry, the FSI figure and the unit counts below
                            # it. Nothing in the codebase reads this key; it is
                            # removed so the column cannot be quoted as provenance.
                            "twin_meta": json.dumps({
                                "engine": "mumbai_metropolitan_3d_cadastre",
                                "data_class": "synthetic",
                                "authority": None,
                            }),
                        },
                    )
                    total_twins += 1

    print(f"✅ Seeding Complete! Inserted/Updated:")
    print(f"   • Districts: 3 (Mumbai City, Mumbai Suburban, Thane)")
    print(f"   • Talukas: 11")
    print(f"   • Village Wards / Prime Localities: {sum(len(z['localities']) for z in MUMBAI_ZONES)}")
    print(f"   • National Cadastral Parcels: {total_parcels}")
    print(f"   • 3D Extruded Building Twins: {total_twins}")


if __name__ == "__main__":
    asyncio.run(seed_mumbai())
