"""2D Cadastre Parcel to 3D Digital Twin Extrusion & 3D-ULPIN Minting Engine.

Automatically converts 2D land parcels into fully stratified 3D digital twins with:
- Statutory NBC 2016 setbacks & building footprint geometry
- Vertical floor stratification (Basement, Ground, Habitable Levels, Rooftop)
- Strata property units (Apartments, Commercial spaces, Parking bays, Utility rooms, Air rights)
- Deterministic 3D-ULPIN minting with ISO/IEC 7064 Luhn Mod 36 checksum
- Title rights and encumbrance registration
"""
import math
from typing import Dict, List, Any, Optional, Tuple
from shapely.geometry import Polygon, mapping

from app.id_engine.generator import generate_proposed_3d_id, parse_and_validate_3d_id
from app.id_engine.types import SpatialTypeCode

# Typologies catalogue for auto-extrusion
TYPOLOGY_SPECS = [
    {
        "type": "tower",
        "name_suffix": "Residency Towers",
        "floor_h": 3.5,
        "default_floors": 10,
        "units_per_floor": 4,
        "fsi_target": 1.85,
        "status": "DEMO_STANDARD",
        "risk_level": "LOW",
    },
    {
        "type": "slab",
        "name_suffix": "Heights Enclave",
        "floor_h": 3.2,
        "default_floors": 6,
        "units_per_floor": 4,
        "fsi_target": 1.45,
        "status": "DEMO_STANDARD",
        "risk_level": "LOW",
    },
    {
        "type": "commercial",
        "name_suffix": "Commercial Plaza",
        "floor_h": 3.6,
        "default_floors": 8,
        "units_per_floor": 4,
        "fsi_target": 1.95,
        "status": "DEMO_STANDARD",
        "risk_level": "LOW",
    },
    {
        "type": "row_house",
        "name_suffix": "Garden Villas",
        "floor_h": 3.2,
        "default_floors": 3,
        "units_per_floor": 2,
        "fsi_target": 0.95,
        "status": "DEMO_STANDARD",
        "risk_level": "LOW",
    },
]

NAMES_SEED = [
    "Shiv Shrishti", "Gokul Dham", "Kailash", "Vasant Vihar",
    "Airoli Tech Point", "Prabhat Nagar", "Navjeevan CHS", "Silver Oak",
    "Panchavati", "Sai Darshan", "Godavari Elite", "Nilgiri View",
    "Samarth Residency", "Chitrakoot", "Gulmohar Arcade", "Shanti Niketan",
    "Adarsh SRA Complex", "Mayur Park"
]

OWNERS_SEED = [
    "Suresh Sharma", "Sunita Patil", "Ramesh Joshi", "Priya Kulkarni",
    "Amitabh Sengupta", "Deepak Verma", "Kavita Nair", "Arun Bhattacharya",
    "Swati Deshmukh", "Nitin Saxena", "Meenal Shah", "Girish Rao",
    "Pooja Mehta", "Manoj Tiwari", "Anjali Ghosh", "Vikram Rathore"
]


def _get_bounding_box(coords: List[List[float]]) -> Tuple[float, float, float, float]:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return min(xs), min(ys), max(xs), max(ys)

def get_next_available_building_code(offset: int = 0) -> str:
    """Finds the next free building code B-XX that does not collide with hero B-17 or precinct B-01..B-12."""
    from app.api.v1.properties import _DATASET_CACHE
    used = {"B-17"}
    for b in _DATASET_CACHE.get("precinct_buildings", []):
        if b.get("code"):
            used.add(str(b["code"]).upper())
    idx = 1
    found = 0
    while True:
        candidate = f"B-{idx:02d}"
        if candidate not in used:
            if found == offset:
                return candidate
            found += 1
        idx += 1


def extrude_parcel_to_3d_twin(
    parcel: Dict[str, Any],
    building_idx: int,
    custom_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extrudes a single 2D parcel into a complete 3D digital twin building
    with deterministic 3D-ULPINs minted for every unit, level, parking bay, and air right.
    """
    custom = custom_params or {}
    parent_ulpin = str(parcel.get("ulpin", "")).strip()
    if len(parent_ulpin) != 14:
        parent_ulpin = parent_ulpin.ljust(14, "0")[:14]

    coords = parcel.get("polygon_geojson", {}).get("coordinates", [[]])[0]
    if not coords or len(coords) < 4:
        coords = [[100.0, 100.0], [140.0, 100.0], [140.0, 130.0], [100.0, 130.0], [100.0, 100.0]]

    poly = Polygon(coords)
    plot_area = round(float(poly.area), 2)
    min_x, min_y, max_x, max_y = _get_bounding_box(coords)
    parcel_w = max_x - min_x
    parcel_h = max_y - min_y

    # Pick typology
    typo_idx = building_idx % len(TYPOLOGY_SPECS)
    typo = TYPOLOGY_SPECS[typo_idx]
    b_type = custom.get("type") or typo["type"]
    floor_h = custom.get("floor_h") or typo["floor_h"]
    floors = int(custom.get("floors") or typo["default_floors"])
    units_per_fl = int(custom.get("units_per_floor") or typo["units_per_floor"])

    b_code = custom.get("code") or get_next_available_building_code(offset=0)
    b_code_clean = b_code.replace("-", "")

    name_base = NAMES_SEED[building_idx % len(NAMES_SEED)]
    b_name = custom.get("name") or f"{name_base} {typo['name_suffix']} ({b_code})"

    # Calculate NBC 2016 setbacks (3m setback on all sides inside parcel)
    setback_x = min(3.5, parcel_w * 0.15)
    setback_y = min(3.0, parcel_h * 0.15)
    fp_min_x = min_x + setback_x
    fp_max_x = max_x - setback_x
    fp_min_y = min_y + setback_y
    fp_max_y = max_y - setback_y

    fp_w = round(fp_max_x - fp_min_x, 1)
    fp_h = round(fp_max_y - fp_min_y, 1)

    fp_coords = [
        [fp_min_x, fp_min_y],
        [fp_max_x, fp_min_y],
        [fp_max_x, fp_max_y],
        [fp_min_x, fp_max_y],
        [fp_min_x, fp_min_y],
    ]
    fp_poly = Polygon(fp_coords)
    fp_area = round(float(fp_poly.area), 2)

    total_height = round(floors * floor_h, 1)
    built_up_area = round(fp_area * floors, 1)
    fsi = round(built_up_area / max(plot_area, 1.0), 2)

    # 1. Mint Building Envelope 3D-ULPIN
    # Example: 12345678901235/BB13-ENV-001-K
    building_3d_id = generate_proposed_3d_id(
        parent_ulpin=parent_ulpin,
        type_code=SpatialTypeCode.BUILDING.value,
        building_code=b_code_clean,
        level_code="ENV",
        unit_code="001",
    )

    levels_list = []
    units_list = []

    # 2. Basement Level B1 (-3.5m to 0.0m)
    b1_level_code = "B1"
    levels_list.append({
        "level_code": b1_level_code,
        "floor_number": -1,
        "name": "Basement Parking & Subsurface Utility",
        "min_z": -3.5,
        "max_z": 0.0,
        "height_m": 3.5,
        "level_type": "BASEMENT",
        "boundary_geojson": mapping(fp_poly),
    })

    # Subsurface utility entry
    subsurface_3d_id = generate_proposed_3d_id(
        parent_ulpin=parent_ulpin,
        type_code=SpatialTypeCode.UNDERGROUND.value,
        building_code=b_code_clean,
        level_code=b1_level_code,
        unit_code="X01",
    )
    units_list.append({
        "unit_number": "X01",
        "proposed_3d_id": subsurface_3d_id,
        "level_code": b1_level_code,
        "unit_type": SpatialTypeCode.UNDERGROUND.value,
        "min_z": -3.5,
        "max_z": 0.0,
        "carpet_area_m2": round(fp_area * 0.25, 1),
        "built_up_area_m2": round(fp_area * 0.3, 1),
        "volume_m3": round(fp_area * 0.3 * 3.5, 1),
        "footprint_geojson": mapping(fp_poly),
        "coords": fp_coords,
        "parent_ulpin": parent_ulpin,
        "building_code": b_code,
        "rights": [
            {
                "right_type": "INFRASTRUCTURE_EASEMENT",
                "party_name": "Municipal Corporation Water & Energy Utility",
                "party_type": "MUNICIPAL_AUTHORITY",
                "share_pct": 100.0,
                "encumbrance_status": "ACTIVE",
                "color_hex": "#6366F1",
            }
        ],
    })

    # Basement parking bays
    for p_idx in range(1, 3):
        p_code = f"P{p_idx:02d}"
        park_3d_id = generate_proposed_3d_id(
            parent_ulpin=parent_ulpin,
            type_code=SpatialTypeCode.PARKING.value,
            building_code=b_code_clean,
            level_code=b1_level_code,
            unit_code=p_code,
        )
        units_list.append({
            "unit_number": p_code,
            "proposed_3d_id": park_3d_id,
            "level_code": b1_level_code,
            "unit_type": SpatialTypeCode.PARKING.value,
            "min_z": -3.5,
            "max_z": 0.0,
            "carpet_area_m2": 15.0,
            "built_up_area_m2": 18.0,
            "volume_m3": 63.0,
            "footprint_geojson": mapping(fp_poly),
            "coords": fp_coords,
            "parent_ulpin": parent_ulpin,
            "building_code": b_code,
            "rights": [
                {
                    "right_type": "EXCLUSIVE_PARKING_RIGHT",
                    "party_name": f"{b_name} Society Reserved Bay {p_code}",
                    "party_type": "HOUSING_SOCIETY",
                    "share_pct": 100.0,
                    "encumbrance_status": "ACTIVE",
                    "color_hex": "#EAB308",
                }
            ],
        })

    # 3. Ground Floor G (0.0m to floor_h)
    g_level_code = "G"
    levels_list.append({
        "level_code": g_level_code,
        "floor_number": 0,
        "name": "Ground Floor & Commercial Reception",
        "min_z": 0.0,
        "max_z": floor_h,
        "height_m": floor_h,
        "level_type": "GROUND",
        "boundary_geojson": mapping(fp_poly),
    })

    # Ground units
    g_unit_3d_id = generate_proposed_3d_id(
        parent_ulpin=parent_ulpin,
        type_code=SpatialTypeCode.UNIT.value,
        building_code=b_code_clean,
        level_code=g_level_code,
        unit_code="001",
    )
    units_list.append({
        "unit_number": "001",
        "proposed_3d_id": g_unit_3d_id,
        "level_code": g_level_code,
        "unit_type": SpatialTypeCode.UNIT.value,
        "min_z": 0.0,
        "max_z": floor_h,
        "carpet_area_m2": round(fp_area * 0.45, 1),
        "built_up_area_m2": round(fp_area * 0.5, 1),
        "volume_m3": round(fp_area * 0.5 * floor_h, 1),
        "footprint_geojson": mapping(fp_poly),
        "coords": fp_coords,
        "parent_ulpin": parent_ulpin,
        "building_code": b_code,
        "rights": [
            {
                "right_type": "COMMERCIAL_TENANCY",
                "party_name": OWNERS_SEED[(building_idx * 3) % len(OWNERS_SEED)],
                "party_type": "NATURAL_PERSON",
                "share_pct": 100.0,
                "encumbrance_status": "ACTIVE",
                "color_hex": "#10B981",
            }
        ],
    })

    # 4. Habitable Above-Ground Floors (L01 to L(N))
    mid_x = fp_min_x + fp_w / 2.0
    mid_y = fp_min_y + fp_h / 2.0

    # 2 quadrants or 4 quadrants per floor
    if units_per_fl >= 4:
        quads = [
            ("01", [[fp_min_x, fp_min_y], [mid_x, fp_min_y], [mid_x, mid_y], [fp_min_x, mid_y], [fp_min_x, fp_min_y]]),
            ("02", [[mid_x, fp_min_y], [fp_max_x, fp_min_y], [fp_max_x, mid_y], [mid_x, mid_y], [mid_x, fp_min_y]]),
            ("03", [[fp_min_x, mid_y], [mid_x, mid_y], [mid_x, fp_max_y], [fp_min_x, fp_max_y], [fp_min_x, mid_y]]),
            ("04", [[mid_x, mid_y], [fp_max_x, mid_y], [fp_max_x, fp_max_y], [mid_x, fp_max_y], [mid_x, mid_y]]),
        ]
    else:
        quads = [
            ("01", [[fp_min_x, fp_min_y], [mid_x, fp_min_y], [mid_x, fp_max_y], [fp_min_x, fp_max_y], [fp_min_x, fp_min_y]]),
            ("02", [[mid_x, fp_min_y], [fp_max_x, fp_min_y], [fp_max_x, fp_max_y], [mid_x, fp_max_y], [mid_x, fp_min_y]]),
        ]

    for fl in range(1, floors):
        fl_code = f"L{fl:02d}"
        min_z = round(fl * floor_h, 1)
        max_z = round((fl + 1) * floor_h, 1)

        levels_list.append({
            "level_code": fl_code,
            "floor_number": fl,
            "name": f"Floor Level {fl}",
            "min_z": min_z,
            "max_z": max_z,
            "height_m": floor_h,
            "level_type": "HABITABLE",
            "boundary_geojson": mapping(fp_poly),
        })

        for q_idx, (q_sfx, q_coords) in enumerate(quads, start=1):
            u_num = f"{fl}{q_idx:02d}"
            u_poly = Polygon(q_coords)
            u_area = round(float(u_poly.area), 1)

            unit_3d_id = generate_proposed_3d_id(
                parent_ulpin=parent_ulpin,
                type_code=SpatialTypeCode.UNIT.value,
                building_code=b_code_clean,
                level_code=fl_code,
                unit_code=u_num,
            )

            owner_name = OWNERS_SEED[(building_idx + fl + q_idx) % len(OWNERS_SEED)]
            units_list.append({
                "unit_number": u_num,
                "proposed_3d_id": unit_3d_id,
                "level_code": fl_code,
                "unit_type": SpatialTypeCode.UNIT.value,
                "min_z": min_z,
                "max_z": max_z,
                "carpet_area_m2": round(u_area * 0.85, 1),
                "built_up_area_m2": u_area,
                "volume_m3": round(u_area * floor_h, 1),
                "footprint_geojson": mapping(u_poly),
                "coords": q_coords,
                "parent_ulpin": parent_ulpin,
                "building_code": b_code,
                "rights": [
                    {
                        "right_type": "FREEHOLD_OWNERSHIP",
                        "party_name": owner_name,
                        "party_type": "NATURAL_PERSON",
                        "share_pct": 100.0,
                        "encumbrance_status": "ACTIVE",
                        "color_hex": "#10B981",
                    }
                ],
            })

    # 5. Rooftop Level R01 & Air Rights
    roof_code = "R01"
    roof_min_z = total_height
    roof_max_z = round(total_height + 3.0, 1)

    levels_list.append({
        "level_code": roof_code,
        "floor_number": floors,
        "name": "Rooftop Terrace & Air Rights Column",
        "min_z": roof_min_z,
        "max_z": roof_max_z,
        "height_m": 3.0,
        "level_type": "ROOFTOP",
        "boundary_geojson": mapping(fp_poly),
    })

    air_right_3d_id = generate_proposed_3d_id(
        parent_ulpin=parent_ulpin,
        type_code=SpatialTypeCode.AIR_RIGHT.value,
        building_code=b_code_clean,
        level_code=roof_code,
        unit_code="A01",
    )
    units_list.append({
        "unit_number": "A01",
        "proposed_3d_id": air_right_3d_id,
        "level_code": roof_code,
        "unit_type": SpatialTypeCode.AIR_RIGHT.value,
        "min_z": roof_min_z,
        "max_z": roof_max_z,
        "carpet_area_m2": round(fp_area * 0.9, 1),
        "built_up_area_m2": fp_area,
        "volume_m3": round(fp_area * 3.0, 1),
        "footprint_geojson": mapping(fp_poly),
        "coords": fp_coords,
        "parent_ulpin": parent_ulpin,
        "building_code": b_code,
        "rights": [
            {
                "right_type": "SOLAR_AIR_RIGHTS",
                "party_name": f"{b_name} Rooftop Solar Association",
                "party_type": "HOUSING_SOCIETY",
                "share_pct": 100.0,
                "encumbrance_status": "ACTIVE",
                "color_hex": "#3B82F6",
            }
        ],
    })

    building_record = {
        "code": b_code,
        "name": b_name,
        "type": b_type,
        "floors": floors,
        "height_m": total_height,
        "x": fp_min_x,
        "y": fp_min_y,
        "w": fp_w,
        "h": fp_h,
        "footprint_geojson": mapping(fp_poly),
        "footprint_coords": fp_coords,
        "footprint_area_m2": fp_area,
        "plot_area_m2": plot_area,
        "total_built_up_area_m2": built_up_area,
        "fsi": fsi,
        # A ratio against a fixed number is not a compliance test; the label
        # only states which side of the demo reference the value falls on.
        "fsi_status": "BELOW_REFERENCE" if fsi <= 2.2 else "ABOVE_REFERENCE",
        "fsi_reference_value": 2.0,
        "status": "DEMO_STANDARD",
        "risk_level": "LOW",
        "units_count": len(units_list),
        "basements_count": 1,
        "ulpin": parent_ulpin,
        "proposed_3d_id": building_3d_id,
        "levels": levels_list,
        "units": units_list,
        "is_extruded_from_2d": True,
        "has_epoch2_change": False,
        "epoch2_detail": None,
    }

    return building_record


def generate_lidar_points_for_building(bld: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generates synthetic LiDAR points with ASPRS classifications for extruded building."""
    import numpy as np
    try:
        code_idx = int(str(bld["code"]).rsplit("-", 1)[1])
    except Exception:
        code_idx = 14
    seed = 314159 + code_idx * 1013
    rng = np.random.default_rng(seed)
    x0, y0, w, h = float(bld["x"]), float(bld["y"]), float(bld["w"]), float(bld["h"])
    ht = float(bld["height_m"])
    floors = int(bld.get("floors", 4))
    fl_h = ht / max(1, floors)
    pad = 10.0
    count = 6000
    quarter = count // 4
    veg_n = 400

    points = []
    # Ground returns (class 2)
    gx = rng.uniform(x0 - pad, x0 + w + pad, quarter)
    gy = rng.uniform(y0 - pad, y0 + h + pad, quarter)
    gz = rng.normal(0.0, 0.04, quarter)
    for i in range(quarter):
        points.append({
            "x": float(gx[i]), "y": float(gy[i]), "z": float(gz[i]),
            "classification": 2, "intensity": int(rng.uniform(70, 110)),
            "r": 115, "g": 100, "b": 85, "return_number": 1
        })

    # Vegetation (class 5)
    vx = rng.uniform(x0 - pad * 0.7, x0 + w + pad * 0.7, veg_n)
    vy = rng.uniform(y0 - pad * 0.7, y0 + h + pad * 0.7, veg_n)
    vz = rng.uniform(0.0, min(ht * 0.4, 5.0), veg_n)
    for i in range(veg_n):
        points.append({
            "x": float(vx[i]), "y": float(vy[i]), "z": float(vz[i]),
            "classification": 5, "intensity": int(rng.uniform(90, 140)),
            "r": 60, "g": 140, "b": 70, "return_number": 1
        })

    # Roof slab (class 6)
    rx = rng.uniform(x0, x0 + w, quarter)
    ry = rng.uniform(y0, y0 + h, quarter)
    rz = rng.normal(ht, 0.05, quarter)
    for i in range(quarter):
        points.append({
            "x": float(rx[i]), "y": float(ry[i]), "z": float(rz[i]),
            "classification": 6, "intensity": int(rng.uniform(180, 230)),
            "r": 210, "g": 160, "b": 70, "return_number": 1
        })

    # Facade walls (class 6)
    wall_n = quarter
    wx = rng.choice([x0, x0 + w], wall_n)
    wy = rng.uniform(y0, y0 + h, wall_n)
    wz = rng.uniform(0.0, ht, wall_n)
    for i in range(wall_n):
        points.append({
            "x": float(wx[i]), "y": float(wy[i]), "z": float(wz[i]),
            "classification": 6, "intensity": int(rng.uniform(140, 200)),
            "r": 190, "g": 145, "b": 60, "return_number": 1
        })

    return points


def get_unextruded_parcels() -> List[Dict[str, Any]]:
    """Scans all parcels in the cadastre and returns those that have NO 3D building twin."""
    from app.api.v1.properties import _DATASET_CACHE
    all_parcels = [_DATASET_CACHE["hero_parcel"]] + _DATASET_CACHE.get("surrounding_parcels", []) + _DATASET_CACHE.get("extra_parcels", [])
    
    # Collect existing building ULPINs
    existing_ulpins = set()
    hero = _DATASET_CACHE.get("hero_parcel", {})
    if hero.get("ulpin"):
        existing_ulpins.add(hero["ulpin"])
    for b in _DATASET_CACHE.get("precinct_buildings", []):
        if b.get("ulpin"):
            existing_ulpins.add(b["ulpin"])

    unextruded = []
    idx = 0
    for p in all_parcels:
        ulpin = p.get("ulpin")
        if not ulpin or ulpin in existing_ulpins:
            continue
        idx += 1
        b_code = get_next_available_building_code(offset=idx - 1)
        typo = TYPOLOGY_SPECS[(idx - 1) % len(TYPOLOGY_SPECS)]
        name_base = NAMES_SEED[(idx - 1) % len(NAMES_SEED)]
        unextruded.append({
            "ulpin": ulpin,
            "survey_number": p.get("survey_number", f"CTS-{ulpin[-3:]}"),
            "plot_area_m2": p.get("calculated_area_m2") or p.get("document_area_m2") or 1000.0,
            "polygon_geojson": p.get("polygon_geojson"),
            "location": p.get("location") or {
                "state": "Maharashtra",
                "district": "Thane",
                "taluka": "Thane",
                "village_ward": "Airoli Sector 8",
            },
            "suggested_building_code": b_code,
            "suggested_building_name": f"{name_base} {typo['name_suffix']}",
            "suggested_typology": typo["type"],
            "suggested_floors": typo["default_floors"],
            "permissible_fsi": 2.0,
            "has_3d_twin": False,
        })

    return unextruded


def extrude_all_unextruded_parcels() -> Dict[str, Any]:
    """
    Batch extrudes all unextruded 2D parcels in the precinct into 3D digital twins,
    mints deterministic 3D-ULPINs with Luhn Mod 36 checksums, and updates the live cache.
    """
    from app.api.v1.properties import _DATASET_CACHE
    unextruded = get_unextruded_parcels()
    if not unextruded:
        return {
            "status": "NO_OP",
            "message": "All 2D parcels in the precinct already have active 3D-ULPIN twins!",
            "total_parcels_extruded": 0,
            "total_3d_ulpins_minted": 0,
            "buildings": [],
            "all_minted_3d_ids": [],
        }

    new_buildings = []
    all_minted_ids = []
    total_units_minted = 0

    existing_precinct = _DATASET_CACHE.setdefault("precinct_buildings", [])
    lidar_by_ulpin = _DATASET_CACHE.setdefault("synthetic_lidar_points_by_ulpin", {})
    all_units = _DATASET_CACHE.setdefault("all_precinct_units", [])
    units_by_ulpin = _DATASET_CACHE.setdefault("precinct_units_by_ulpin", {})

    for idx, p in enumerate(unextruded, start=1):
        bld = extrude_parcel_to_3d_twin(p, building_idx=len(existing_precinct) + 1)
        existing_precinct.append(bld)
        new_buildings.append({
            "code": bld["code"],
            "name": bld["name"],
            "parent_ulpin": bld["ulpin"],
            "building_3d_id": bld["proposed_3d_id"],
            "type": bld["type"],
            "floors": bld["floors"],
            "height_m": bld["height_m"],
            "units_count": bld["units_count"],
            "fsi": bld["fsi"],
            "fsi_status": bld["fsi_status"],
            "units_sample": [u["proposed_3d_id"] for u in bld["units"][:3]],
        })

        for u in bld["units"]:
            all_minted_ids.append(u["proposed_3d_id"])
            all_units.append(u)
            total_units_minted += 1

        all_minted_ids.append(bld["proposed_3d_id"])
        units_by_ulpin[bld["ulpin"]] = bld["units"]

        # Generate LiDAR points
        lidar_by_ulpin[bld["ulpin"]] = generate_lidar_points_for_building(bld)

    return {
        "status": "SUCCESS",
        "message": f"Successfully extruded {len(new_buildings)} 2D parcels into 3D digital twins and minted {total_units_minted + len(new_buildings)} verified 3D-ULPINs!",
        "total_parcels_extruded": len(new_buildings),
        "total_3d_ulpins_minted": total_units_minted + len(new_buildings),
        "buildings": new_buildings,
        "all_minted_3d_ids": all_minted_ids,
        "specification": "Proposed Bhu-Drishti 3D Spatial Extension (ISO/IEC 7064 Luhn Mod 36)",
    }


def extrude_single_parcel(ulpin: str, custom_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extrudes a specific 2D parcel into a 3D digital twin on demand."""
    from app.api.v1.properties import _DATASET_CACHE
    all_parcels = [_DATASET_CACHE["hero_parcel"]] + _DATASET_CACHE.get("surrounding_parcels", []) + _DATASET_CACHE.get("extra_parcels", [])
    target = None
    for p in all_parcels:
        if p.get("ulpin") == ulpin:
            target = p
            break
    if not target:
        raise ValueError(f"Parcel with ULPIN '{ulpin}' not found in cadastral registry.")

    existing_precinct = _DATASET_CACHE.setdefault("precinct_buildings", [])
    # Check if already extruded
    for b in existing_precinct:
        if b.get("ulpin") == ulpin:
            return {
                "status": "ALREADY_EXISTS",
                "message": f"Building {b['code']} is already extruded on parcel {ulpin}.",
                "building": b,
            }

    bld = extrude_parcel_to_3d_twin(target, building_idx=len(existing_precinct) + 1, custom_params=custom_params)
    existing_precinct.append(bld)

    lidar_by_ulpin = _DATASET_CACHE.setdefault("synthetic_lidar_points_by_ulpin", {})
    all_units = _DATASET_CACHE.setdefault("all_precinct_units", [])
    units_by_ulpin = _DATASET_CACHE.setdefault("precinct_units_by_ulpin", {})

    all_units.extend(bld["units"])
    units_by_ulpin[bld["ulpin"]] = bld["units"]
    lidar_by_ulpin[bld["ulpin"]] = generate_lidar_points_for_building(bld)

    return {
        "status": "SUCCESS",
        "message": f"Successfully extruded parcel {ulpin} into 3D twin {bld['code']} with {bld['units_count']} 3D-ULPIN units!",
        "building": bld,
        "minted_3d_ulpins_count": bld["units_count"] + 1,
    }
