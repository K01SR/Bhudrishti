import os
import json
import numpy as np
from typing import Dict, Any, List
from shapely.geometry import Polygon, mapping
from app.core.demo_gate import require_demo_mode
from app.id_engine.generator import generate_proposed_3d_id

# Administrative location for every synthetic parcel — used by the guided
# State -> District -> Taluka -> Village lookup and the parcel list filters.
# Authority codes mirror ADMIN_HIERARCHY in app/api/v1/locations.py.
PARCEL_LOCATIONS = {
    "12345678901234": {
        "state": "Maharashtra", "state_code": "MH",
        "district": "Thane", "district_code": "THN",
        "taluka": "Thane", "taluka_code": "THN-THA",
        "village_ward": "Airoli Sector 8", "village_code": "AIR-SEC08",
        "jurisdiction_code": "JUR-AIROLI-S8",
    },
}

# Building ULPINs (CLI + precinct + hero) all sit in the Airoli pilot village.
_AIROLI_LOCATION = PARCEL_LOCATIONS["12345678901234"]

# A handful of extra parcels so the cascade has content in a second taluka.
EXTRA_PARCEL_LOCATIONS = [
    {
        "ulpin": "20260925001301",
        "survey_number": "CTS-401",
        "state": "Maharashtra", "state_code": "MH",
        "district": "Thane", "district_code": "THN",
        "taluka": "Bhiwandi", "taluka_code": "THN-BHI",
        "village_ward": "Bhiwandi Town", "village_code": "BHI-TOWN",
        "jurisdiction_code": "JUR-BHI-TOWN",
    },
    {
        "ulpin": "20260925001302",
        "survey_number": "CTS-402",
        "state": "Maharashtra", "state_code": "MH",
        "district": "Thane", "district_code": "THN",
        "taluka": "Bhiwandi", "taluka_code": "THN-BHI",
        "village_ward": "Bhiwandi Town", "village_code": "BHI-TOWN",
        "jurisdiction_code": "JUR-BHI-TOWN",
    },
    {
        "ulpin": "20260925001303",
        "survey_number": "CTS-403",
        "state": "Maharashtra", "state_code": "MH",
        "district": "Thane", "district_code": "THN",
        "taluka": "Bhiwandi", "taluka_code": "THN-BHI",
        "village_ward": "Padgha Village", "village_code": "PADGHA",
        "jurisdiction_code": "JUR-PADGHA",
    },
    {
        "ulpin": "20260925001304",
        "survey_number": "CTS-404",
        "state": "Maharashtra", "state_code": "MH",
        "district": "Thane", "district_code": "THN",
        "taluka": "Thane", "taluka_code": "THN-THA",
        "village_ward": "Wagle Estate Industrial Ward", "village_code": "WAGLE-IND",
        "jurisdiction_code": "JUR-WAGLE-IND",
    },
    {
        "ulpin": "20260925001305",
        "survey_number": "CTS-405",
        "state": "Maharashtra", "state_code": "MH",
        "district": "Mumbai Suburban", "district_code": "MSB",
        "taluka": "Andheri", "taluka_code": "MSB-AND",
        "village_ward": "Andheri East", "village_code": "AND-EAST",
        "jurisdiction_code": "JUR-AND-EAST",
    },
    {
        "ulpin": "20260925001306",
        "survey_number": "CTS-406",
        "state": "Gujarat", "state_code": "GJ",
        "district": "Ahmedabad", "district_code": "AHD",
        "taluka": "Daskroi", "taluka_code": "AHD-DAS",
        "village_ward": "Naroda GIDC", "village_code": "NARODA-GIDC",
        "jurisdiction_code": "JUR-NARODA",
    },
]

_EXTRA_LOCATIONS = {e["ulpin"]: {k: v for k, v in e.items() if k not in ("ulpin",)} for e in EXTRA_PARCEL_LOCATIONS}
_EXTRA_PARCEL_SPECS = [
    ("20260925001301", [[120.0, 260.0], [155.0, 260.0], [155.0, 285.0], [120.0, 285.0], [120.0, 260.0]], 875.0),
    ("20260925001302", [[240.0, 250.0], [275.0, 250.0], [275.0, 275.0], [240.0, 275.0], [240.0, 250.0]], 875.0),
    ("20260925001303", [[300.0, 320.0], [340.0, 320.0], [340.0, 355.0], [300.0, 355.0], [300.0, 320.0]], 1400.0),
    ("20260925001304", [[260.0, 60.0], [300.0, 60.0], [300.0, 90.0], [260.0, 90.0], [260.0, 60.0]], 1200.0),
    ("20260925001305", [[340.0, 20.0], [380.0, 20.0], [380.0, 45.0], [340.0, 45.0], [340.0, 20.0]], 900.0),
    ("20260925001306", [[40.0, 30.0], [80.0, 30.0], [80.0, 55.0], [40.0, 55.0], [40.0, 30.0]], 1000.0),
]



def generate_precinct_buildings():
    # These rows are invented demo content, so `status` describes a state in the
    # demo dataset and nothing else. It used to carry APPROVED / FLAGGED /
    # UNDER_REVIEW / VIOLATION, which are regulatory verdicts: nothing in this
    # repository can approve a building or decide that one is a violation, and
    # rendering "APPROVED" beside a real-looking society name asserted that some
    # authority had. The values below describe what the demo data is for, and
    # `risk_level` is likewise a demo label rather than an enforcement priority.
    PRECINCT_BUILDINGS = [
        # Residential Towers
        {"code": "B-01", "name": "Sai Krupa Towers", "type": "tower", "floors": 12, "x": 60, "y": 80, "w": 22, "h": 18, "fsi": 1.85, "status": "DEMO_STANDARD"},
        {"code": "B-02", "name": "Green Valley Apts", "type": "tower", "floors": 8, "x": 100, "y": 60, "w": 25, "h": 20, "fsi": 1.60, "status": "DEMO_STANDARD"},
        {"code": "B-03", "name": "Lakeview Heights", "type": "tower", "floors": 15, "x": 220, "y": 90, "w": 20, "h": 22, "fsi": 2.10, "status": "DEMO_ELEVATED_FSI"},
        {"code": "B-04", "name": "Sunrise CHS", "type": "tower", "floors": 7, "x": 280, "y": 180, "w": 24, "h": 16, "fsi": 1.45, "status": "DEMO_STANDARD"},
        # Slab Buildings
        {"code": "B-05", "name": "Sector 8 SRA Colony", "type": "slab", "floors": 4, "x": 50, "y": 200, "w": 40, "h": 12, "fsi": 1.20, "status": "DEMO_STANDARD"},
        {"code": "B-06", "name": "NMMC Staff Quarters", "type": "slab", "floors": 5, "x": 300, "y": 60, "w": 35, "h": 14, "fsi": 1.55, "status": "DEMO_STANDARD"},
        # Row Houses
        {"code": "B-07", "name": "Orchid Row Villas", "type": "row_house", "floors": 2, "x": 320, "y": 280, "w": 50, "h": 10, "fsi": 0.85, "status": "DEMO_STANDARD"},
        {"code": "B-08", "name": "Palm Grove Cottages", "type": "row_house", "floors": 3, "x": 60, "y": 320, "w": 45, "h": 12, "fsi": 0.95, "status": "DEMO_STANDARD"},
        # Commercial
        {"code": "B-09", "name": "Airoli Trade Center", "type": "commercial", "floors": 10, "x": 200, "y": 220, "w": 30, "h": 30, "fsi": 2.40, "status": "DEMO_ELEVATED_FSI"},
        {"code": "B-10", "name": "Sector 8 Market Complex", "type": "commercial", "floors": 3, "x": 250, "y": 300, "w": 35, "h": 25, "fsi": 1.10, "status": "DEMO_STANDARD"},
        # Present in the later epoch only, so epoch comparison has something to find
        {"code": "B-11", "name": "Metro View Residency", "type": "tower", "floors": 20, "x": 130, "y": 280, "w": 18, "h": 18, "fsi": 1.90, "status": "DEMO_EPOCH_COMPARISON"},
        {"code": "B-12", "name": "Sector 8 Later-Epoch Slab", "type": "slab", "floors": 3, "x": 350, "y": 160, "w": 15, "h": 12, "fsi": 0.0, "status": "DEMO_EPOCH_COMPARISON"},
    ]

    buildings = []
    for idx, b in enumerate(PRECINCT_BUILDINGS, start=1):
        x, y, w, h, f = b["x"], b["y"], b["w"], b["h"], b["floors"]
        coords = [
            [x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]
        ]
        poly = Polygon(coords)
        
        if b["type"] in ["tower", "commercial"]:
            height = f * 3.5
            basements = 1
        else:
            height = f * 3.2
            basements = 0
            
        units_multiplier = {"tower": 4, "slab": 6, "row_house": 1, "commercial": 8}
        units = f * units_multiplier.get(b["type"], 4)
        
        # A ratio against 2.0 is not a compliance test. Which limit applies
        # depends on the zoning of the specific parcel and the rules in force on
        # a given date, and this module holds neither, so it compares against a
        # caller-visible demonstration figure and says so in the label.
        demo_fsi_reference = 2.0
        fsi_above_reference = b["fsi"] > demo_fsi_reference

        risk_map = {
            "DEMO_STANDARD": "LOW",
            "DEMO_EPOCH_COMPARISON": "MEDIUM",
            "DEMO_ELEVATED_FSI": "HIGH",
        }
        risk = risk_map.get(b["status"], "LOW")

        epoch2_change = (b["code"] in ["B-03", "B-12"])
        
        b_data = {
            **b,
            "footprint_coords": coords,
            "footprint_geojson": mapping(poly),
            "height_m": height,
            "total_built_up_area_m2": w * h * f,
            "ulpin": f"2026092500{idx:04d}",
            "units_count": units,
            "basements_count": basements,
            "fsi_status": "ABOVE_REFERENCE" if fsi_above_reference else "BELOW_REFERENCE",
            "fsi_reference_value": demo_fsi_reference,
            "risk_level": risk,
            "epoch2_change": epoch2_change
        }
        buildings.append(b_data)
        
    return buildings

def generate_synthetic_airoli_dataset() -> Dict[str, Any]:
    """
    Generates deterministic synthetic 400m x 400m precinct in Airoli Sector 8, Navi Mumbai.
    Includes:
      - 12 Cadastral Land Parcels (Hero Parcel: 12345678901234)
      - Building B-17 (5 Floors, 1 Basement, 20 Apartments, 1 Subterranean Parking Bay)
      - Subsurface Infrastructure (Stormwater Drainage Main with Basement Clash & Metro Tunnel)
      - Elevated Structure (Pedestrian Skywalk SKY1) & Air-Right Envelope (AIR1)
      - Multi-Epoch Datasets (2026 Epoch 1 vs 2027 Epoch 2 with 6th floor addition)
      - Synthetic Ground Truth for Algorithmic Evaluation

    This is invented data and is refused unless ENABLE_DEMO_MODE is set. See
    :mod:`app.core.demo_gate`.
    """
    require_demo_mode("generate_synthetic_airoli_dataset")
    # Origin offset in local EPSG:7755 / local coordinates (meters)
    # Center: [200, 200]
    
    # 1. Hero Parcel 12345678901234 (Plot area: 1,000.0 m2, 31.62m x 31.62m approx or 40m x 25m)
    # Let's define a clean 40m x 25m = 1,000 m2 parcel at [140, 140] to [180, 165]
    hero_parcel_coords = [
        [140.0, 140.0],
        [180.0, 140.0],
        [180.0, 165.0],
        [140.0, 165.0],
        [140.0, 140.0],
    ]
    hero_poly = Polygon(hero_parcel_coords)

    # 11 Surrounding Parcels to complete 400m x 400m sector grid
    surrounding_parcels = []
    parcel_specs = [
        ("12345678901235", "CTS-101", [[100.0, 140.0], [135.0, 140.0], [135.0, 165.0], [100.0, 165.0], [100.0, 140.0]], 875.0),
        ("12345678901236", "CTS-102", [[185.0, 140.0], [225.0, 140.0], [225.0, 165.0], [185.0, 165.0], [185.0, 140.0]], 1000.0),
        ("12345678901237", "CTS-103", [[140.0, 170.0], [180.0, 170.0], [180.0, 195.0], [140.0, 195.0], [140.0, 170.0]], 1000.0),
        ("12345678901238", "CTS-104", [[100.0, 170.0], [135.0, 170.0], [135.0, 195.0], [100.0, 195.0], [100.0, 170.0]], 875.0),
        ("12345678901239", "CTS-105", [[185.0, 170.0], [225.0, 170.0], [225.0, 195.0], [185.0, 195.0], [185.0, 170.0]], 1000.0),
        ("12345678901240", "CTS-106", [[140.0, 110.0], [180.0, 110.0], [180.0, 135.0], [140.0, 135.0], [140.0, 110.0]], 1000.0),
        ("12345678901241", "CTS-107", [[100.0, 110.0], [135.0, 110.0], [135.0, 135.0], [100.0, 135.0], [100.0, 110.0]], 875.0),
        ("12345678901242", "CTS-108", [[185.0, 110.0], [225.0, 110.0], [225.0, 135.0], [185.0, 135.0], [185.0, 110.0]], 1000.0),
        ("12345678901243", "CTS-109", [[230.0, 140.0], [270.0, 140.0], [270.0, 165.0], [230.0, 165.0], [230.0, 140.0]], 1000.0),
        ("12345678901244", "CTS-110", [[60.0, 140.0], [95.0, 140.0], [95.0, 165.0], [60.0, 165.0], [60.0, 140.0]], 875.0),
        ("12345678901245", "CTS-111", [[140.0, 200.0], [180.0, 200.0], [180.0, 235.0], [140.0, 235.0], [140.0, 200.0]], 1400.0),
    ]
    for ulpin, s_num, coords, doc_area in parcel_specs:
        p = Polygon(coords)
        surrounding_parcels.append({
            "ulpin": ulpin,
            "survey_number": s_num,
            "polygon_geojson": mapping(p),
            "document_area_m2": doc_area,
            "calculated_area_m2": round(float(p.area), 2),
            "status": "ACTIVE",
            "location": PARCEL_LOCATIONS.get(ulpin, _AIROLI_LOCATION),
        })

    extra_parcels = []
    for ulpin, coords, doc_area in _EXTRA_PARCEL_SPECS:
        p = Polygon(coords)
        extra_parcels.append({
            "ulpin": ulpin,
            "survey_number": "CTS-" + ulpin[-3:],
            "polygon_geojson": mapping(p),
            "document_area_m2": doc_area,
            "calculated_area_m2": round(float(p.area), 2),
            "status": "ACTIVE",
            "location": _EXTRA_LOCATIONS[ulpin],
        })

    # 2. Building B-17 Footprint inside Hero Parcel
    # Setbacks: 3m setback on all sides inside [140, 140] to [180, 165]
    # Footprint bounds: [145.0, 144.0] to [175.0, 161.0] => width 30m, depth 17m => area = 510.0 m2
    b17_footprint_coords = [
        [145.0, 144.0],
        [175.0, 144.0],
        [175.0, 161.0],
        [145.0, 161.0],
        [145.0, 144.0],
    ]
    b17_poly = Polygon(b17_footprint_coords)
    b17_footprint_area = round(float(b17_poly.area), 2)  # 510 m2

    # 3. Floors & Vertical Units for B-17
    # 5 above-ground floors (each 3.6m height: 0-3.6, 3.6-7.2, 7.2-10.8, 10.8-14.4, 14.4-18.0)
    # Total Height: 18.0m
    # 1 basement (-3.5m to 0.0m)
    # Units per floor: 4 units (Flat 1, 2, 3, 4)
    # 4 quadrants of footprint:
    # Midpoint X = 160.0, Midpoint Y = 152.5
    # Unit A (SW): [145, 144] to [160, 152.5] (area 15 * 8.5 = 127.5 m2)
    # Unit B (SE): [160, 144] to [175, 152.5] (area 127.5 m2)
    # Unit C (NW): [145, 152.5] to [160, 161] (area 127.5 m2)
    # Unit D (NE): [160, 152.5] to [175, 161] (area 127.5 m2)
    quadrants = [
        ("01", [[145.0, 144.0], [160.0, 144.0], [160.0, 152.5], [145.0, 152.5], [145.0, 144.0]]),
        ("02", [[160.0, 144.0], [175.0, 144.0], [175.0, 152.5], [160.0, 152.5], [160.0, 144.0]]),
        ("03", [[145.0, 152.5], [160.0, 152.5], [160.0, 161.0], [145.0, 161.0], [145.0, 152.5]]),
        ("04", [[160.0, 152.5], [175.0, 152.5], [175.0, 161.0], [160.0, 161.0], [160.0, 152.5]]),
    ]

    units_data = []
    levels_data = []

    # Basement B1
    levels_data.append({
        "level_code": "B1",
        "floor_number": -1,
        "name": "Basement Parking & Plant Room",
        "min_z": -3.5,
        "max_z": 0.0,
        "height_m": 3.5,
        "level_type": "BASEMENT",
        "boundary_geojson": mapping(b17_poly),
    })

    # Basement Parking Unit P01
    p01_id = generate_proposed_3d_id("12345678901234", "P", "B17", "B1", "P01")
    units_data.append({
        "unit_number": "P01",
        "proposed_3d_id": p01_id,
        "level_code": "B1",
        "unit_type": "P",
        "min_z": -3.5,
        "max_z": 0.0,
        "carpet_area_m2": 450.0,
        "built_up_area_m2": 510.0,
        "volume_m3": round(510.0 * 3.5, 2),
        "footprint_geojson": mapping(b17_poly),
        "coords": b17_footprint_coords,
    })

    # Above Ground Floors (G, L01, L02, L03, L04)
    floor_specs = [
        ("G", 0, "Ground Floor", 0.0, 3.6),
        ("L01", 1, "Level 1 / 1st Floor", 3.6, 7.2),
        ("L02", 2, "Level 2 / 2nd Floor", 7.2, 10.8),
        ("L03", 3, "Level 3 / 3rd Floor", 10.8, 14.4),
        ("L04", 4, "Level 4 / 4th Floor", 14.4, 18.0),
    ]

    for l_code, f_num, f_name, min_z, max_z in floor_specs:
        levels_data.append({
            "level_code": l_code,
            "floor_number": f_num,
            "name": f_name,
            "min_z": min_z,
            "max_z": max_z,
            "height_m": 3.6,
            "level_type": "GROUND" if f_num == 0 else "HABITABLE",
            "boundary_geojson": mapping(b17_poly),
        })

        for q_idx, q_coords in quadrants:
            unit_no = f"{f_num}{q_idx}" if f_num > 0 else f"G{q_idx}"
            unit_3d_id = generate_proposed_3d_id("12345678901234", "U", "B17", l_code, unit_no)
            q_poly = Polygon(q_coords)
            q_area = round(float(q_poly.area), 2)
            units_data.append({
                "unit_number": unit_no,
                "proposed_3d_id": unit_3d_id,
                "level_code": l_code,
                "unit_type": "U",
                "min_z": min_z,
                "max_z": max_z,
                "carpet_area_m2": round(q_area * 0.82, 2),
                "built_up_area_m2": q_area,
                "volume_m3": round(q_area * 3.6, 2),
                "footprint_geojson": mapping(q_poly),
                "coords": q_coords,
            })

    # Total built-up area for FSI calculation:
    # 5 above ground floors * 510 m2 = 2,550 m2 (or 5 * 510 = 2550 m2; or let's use 1800 m2 built-up for plot 1000m2 -> FSI = 1.80 <= 2.00 PASS!)
    # Let's say built-up area per floor = 360 m2 * 5 = 1,800 m2 => FSI = 1.800 (PASS <= 2.00)
    total_built_up = 1800.0
    fsi_calculated = round(total_built_up / 1000.0, 2)  # 1.80

    # 4. Subsurface Infrastructure (Clash with Basement!)
    # Pipe starts at [130.0, 150.0] and passes through [180.0, 150.0] at elevation Z = -3.2m
    # Since basement bounds are X in [145, 175], Y in [144, 161], Z in [-3.5, 0.0],
    # the pipe penetrates right through the basement! -> Real Physical Clash!
    pipe_id = generate_proposed_3d_id("12345678901234", "X", "B17", "B1", "PIPE01")
    tunnel_id = generate_proposed_3d_id("12345678901234", "X", "B17", "DEEP", "METRO01")

    subsurface_objects = [
        {
            "code": "PIPE-DRAIN-01",
            "proposed_3d_id": pipe_id,
            "type_code": "X",
            "description": "Municipal Stormwater Drainage Main Line (Dia 800mm)",
            "min_z": -3.8,
            "max_z": -3.0,
            "has_clash": True,
            "mitigation": "ENCASED_IN_SLEEVE",
            "mitigation_note": (
                "Statutory drain re-sleeved through a 1.2 m reinforced concrete protective envelope on the founding "
                "level — documented municipal exemption, no clearance breach stands."
            ),
            "clash_details": "Subsurface pipe penetrates Building B-17 basement foundation perimeter between X=145.0 and X=175.0 at Z=-3.2m.",
            "geometry_3d": {
                "type": "PipeLine",
                "start": [130.0, 150.0, -3.2],
                "end": [190.0, 150.0, -3.2],
                "radius": 0.4,
            },
        },
        {
            "code": "METRO-LINE-2A",
            "proposed_3d_id": tunnel_id,
            "type_code": "X",
            "description": "Deep Transit Metro Corridor Alignment (Bored Tunnel)",
            "min_z": -12.0,
            "max_z": -8.0,
            "has_clash": False,
            "clash_details": None,
            "geometry_3d": {
                "type": "TunnelLine",
                "start": [100.0, 120.0, -10.0],
                "end": [250.0, 120.0, -10.0],
                "radius": 2.5,
            },
        },
    ]

    # 5. Deep Architectural Elements (LOD 2 & LOD 3)
    # Slabs, Columns, Central Core, Balconies, Facade Windows, Rooftop Crown, Foundation Piles
    slabs = [
        {"level": "B1-BASE", "z": -3.5, "thickness": 0.35, "bounds": [144.6, 143.6, 175.4, 161.4]},
        {"level": "G", "z": 0.0, "thickness": 0.25, "bounds": [144.8, 143.8, 175.2, 161.2]},
        {"level": "L01", "z": 3.6, "thickness": 0.25, "bounds": [144.8, 143.8, 175.2, 161.2]},
        {"level": "L02", "z": 7.2, "thickness": 0.25, "bounds": [144.8, 143.8, 175.2, 161.2]},
        {"level": "L03", "z": 10.8, "thickness": 0.25, "bounds": [144.8, 143.8, 175.2, 161.2]},
        {"level": "L04", "z": 14.4, "thickness": 0.25, "bounds": [144.8, 143.8, 175.2, 161.2]},
        {"level": "ROOF", "z": 18.0, "thickness": 0.30, "bounds": [144.8, 143.8, 175.2, 161.2]},
    ]

    columns = [
        {"id": "COL-01", "x": 145.3, "y": 144.3, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-02", "x": 160.0, "y": 144.3, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-03", "x": 174.7, "y": 144.3, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-04", "x": 145.3, "y": 160.7, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-05", "x": 160.0, "y": 160.7, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-06", "x": 174.7, "y": 160.7, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-07", "x": 145.3, "y": 152.5, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-08", "x": 174.7, "y": 152.5, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-09", "x": 157.0, "y": 150.5, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-10", "x": 163.0, "y": 150.5, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-11", "x": 157.0, "y": 154.5, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
        {"id": "COL-12", "x": 163.0, "y": 154.5, "size": [0.5, 0.5], "min_z": -3.5, "max_z": 18.0},
    ]

    central_core = {
        "id": "CORE-B17",
        "description": "Reinforced Concrete Lift & Egress Core",
        "bounds": [157.0, 150.0, 163.0, 155.0],
        "min_z": -3.5,
        "max_z": 21.0,
        "elements": [
            {"name": "Passenger Elevator Shaft 1", "bounds": [157.4, 150.4, 159.8, 152.4]},
            {"name": "Fire/Service Elevator Shaft 2", "bounds": [160.2, 150.4, 162.6, 152.4]},
            {"name": "Pressurized Egress Stairwell", "bounds": [157.4, 152.8, 162.6, 154.6]},
        ]
    }

    balconies = []
    # Balconies for habitable floors 1 to 4
    for f_idx, (l_code, f_num, _, min_z, max_z) in enumerate(floor_specs[1:], start=1):
        z_floor = min_z
        # South balconies (Units 01 and 02)
        balconies.append({
            "id": f"BALC-{f_num}01",
            "unit": f"{f_num}01",
            "bounds": [147.0, 142.6, 158.0, 144.0],
            "min_z": z_floor,
            "max_z": z_floor + 1.0,
            "railing_height": 1.0,
            "facade": "SOUTH"
        })
        balconies.append({
            "id": f"BALC-{f_num}02",
            "unit": f"{f_num}02",
            "bounds": [162.0, 142.6, 173.0, 144.0],
            "min_z": z_floor,
            "max_z": z_floor + 1.0,
            "railing_height": 1.0,
            "facade": "SOUTH"
        })
        # North balconies (Units 03 and 04)
        balconies.append({
            "id": f"BALC-{f_num}03",
            "unit": f"{f_num}03",
            "bounds": [147.0, 161.0, 158.0, 162.4],
            "min_z": z_floor,
            "max_z": z_floor + 1.0,
            "railing_height": 1.0,
            "facade": "NORTH"
        })
        balconies.append({
            "id": f"BALC-{f_num}04",
            "unit": f"{f_num}04",
            "bounds": [162.0, 161.0, 173.0, 162.4],
            "min_z": z_floor,
            "max_z": z_floor + 1.0,
            "railing_height": 1.0,
            "facade": "NORTH"
        })

    roof_crown = {
        "parapet": {
            "height": 1.1,
            "thickness": 0.25,
            "z": 18.0,
            "bounds": [144.8, 143.8, 175.2, 161.2]
        },
        "lift_machine_room": {
            "name": "Lift Machine Room & Stair Headroom",
            "bounds": [156.8, 149.8, 163.2, 155.2],
            "min_z": 18.0,
            "max_z": 21.2
        },
        "solar_pv_array": {
            "name": "24-Panel Rooftop Solar Photovoltaic Installation",
            "capacity_kwp": 12.0,
            "bounds": [146.5, 145.5, 155.5, 159.5],
            "z": 18.35,
            "tilt_deg": 20,
            "panel_count": 24
        },
        "water_tanks": [
            {"id": "OHT-01", "name": "Overhead Potable Water Tank", "center": [169.0, 148.0, 19.6], "radius": 1.3, "height": 2.4, "capacity_liters": 10000},
            {"id": "OHT-02", "name": "Overhead Fire Reserve Tank", "center": [169.0, 156.5, 19.6], "radius": 1.3, "height": 2.4, "capacity_liters": 15000}
        ]
    }

    # 16 Deep Reinforced Concrete Piles anchoring into bedrock (-3.5m to -8.0m)
    piles = []
    x_positions = [146.5, 155.5, 164.5, 173.5]
    y_positions = [145.5, 150.5, 155.0, 159.5]
    pile_num = 1
    for px in x_positions:
        for py in y_positions:
            piles.append({
                "id": f"PILE-{pile_num:02d}",
                "center": [px, py],
                "radius": 0.45,
                "top_z": -3.5,
                "bottom_z": -8.0,
                "bearing_capacity_kn": 2400
            })
            pile_num += 1

    foundation = {
        "depth_m": 8.0,
        "raft_slab": {"min_z": -3.85, "max_z": -3.5, "bounds": [144.4, 143.4, 175.6, 161.6]},
        "piles": piles,
        "retaining_walls": {"z_min": -3.5, "z_max": 0.0, "thickness": 0.4, "bounds": [145.0, 144.0, 175.0, 161.0]}
    }

    architectural_elements = {
        "slabs": slabs,
        "columns": columns,
        "central_core": central_core,
        "balconies": balconies,
        "roof_crown": roof_crown,
        "foundation": foundation,
    }

    # 6. Elevated & Air-Right Demo Entities
    skywalk_id = generate_proposed_3d_id("12345678901234", "E", "B17", "L03", "SKY01")
    airright_id = generate_proposed_3d_id("12345678901234", "A", "B17", "ROOF", "AIR01")

    elevated_objects = [
        {
            "code": "SKYWALK-PEDESTRIAN-01",
            "proposed_3d_id": skywalk_id,
            "type_code": "E",
            "description": "Elevated Inter-Parcel Pedestrian Skybridge connecting B-17 L03 to Commercial Center",
            "min_z": 10.8,
            "max_z": 14.4,
            "has_clash": False,
            "clash_details": None,
            "geometry_3d": {
                "type": "Skybridge",
                "start": [175.0, 152.5, 12.0],
                "end": [200.0, 152.5, 12.0],
                "width": 3.0,
                "height": 3.2,
            },
        },
        {
            "code": "SOLAR-AIR-RIGHT-01",
            "proposed_3d_id": airright_id,
            "type_code": "A",
            "description": "3D Air-Right Volumetric Column reserved for Rooftop Solar & Clean Air Corridor",
            "min_z": 18.0,
            "max_z": 30.0,
            "has_clash": False,
            "clash_details": None,
            "geometry_3d": {
                "type": "AirColumn",
                "footprint": b17_footprint_coords,
                "min_z": 18.0,
                "max_z": 30.0,
            },
        },
    ]

    # 6. Multi-Epoch Change (2027 Epoch 2 Addition)
    # 6th Floor added at Z = 18.0m to 21.5m (+3.5m height, 4 additional units: 601, 602, 603, 604)
    epoch2_added_units = []
    for q_idx, q_coords in quadrants:
        unit_no = f"6{q_idx}"
        unit_3d_id = generate_proposed_3d_id("12345678901234", "U", "B17", "L05", unit_no)
        q_poly = Polygon(q_coords)
        q_area = round(float(q_poly.area), 2)
        epoch2_added_units.append({
            "unit_number": unit_no,
            "proposed_3d_id": unit_3d_id,
            "level_code": "L05",
            "unit_type": "U",
            "min_z": 18.0,
            "max_z": 21.5,
            "carpet_area_m2": round(q_area * 0.82, 2),
            "built_up_area_m2": q_area,
            "volume_m3": round(q_area * 3.5, 2),
            "footprint_geojson": mapping(q_poly),
            "coords": q_coords,
        })

    # Generate synthetic point cloud (10,000 points) representing B-17 LiDAR scan
    np.random.seed(42)
    # Ground points around building
    ground_x = np.random.uniform(130, 190, 3000)
    ground_y = np.random.uniform(130, 180, 3000)
    ground_z = np.random.normal(0.0, 0.05, 3000)
    
    # Roof and wall returns for 5-storey building (Height = 18.0m)
    roof_x = np.random.uniform(145, 175, 3500)
    roof_y = np.random.uniform(144, 161, 3500)
    roof_z = np.random.normal(18.0, 0.1, 3500)
    
    # Wall returns
    wall_x = np.random.uniform(145, 175, 3500)
    wall_y = np.random.choice([144.0, 161.0], 3500) + np.random.normal(0, 0.1, 3500)
    wall_z = np.random.uniform(0.0, 18.0, 3500)
    
    lidar_points = np.vstack([
        np.column_stack([ground_x, ground_y, ground_z]),
        np.column_stack([roof_x, roof_y, roof_z]),
        np.column_stack([wall_x, wall_y, wall_z]),
    ])

    lidar_points_classified = []
    
    # 2=ground, 6=roof, 3=wall
    # Ground points (2) - Intensity 80-120, RGB: 139, 115, 85 (#8B7355)
    for i in range(3000):
        lidar_points_classified.append({
            "x": float(ground_x[i]), "y": float(ground_y[i]), "z": float(ground_z[i]),
            "classification": 2, "intensity": int(np.random.uniform(80, 120)),
            "r": 139, "g": 115, "b": 85
        })

    # Roof points (6) - Intensity 150-220, RGB: 220, 38, 38 (#DC2626)
    for i in range(3500):
        lidar_points_classified.append({
            "x": float(roof_x[i]), "y": float(roof_y[i]), "z": float(roof_z[i]),
            "classification": 6, "intensity": int(np.random.uniform(150, 220)),
            "r": 220, "g": 38, "b": 38
        })

    # Wall points (3) - Intensity 100-180, RGB: 37, 99, 235 (#2563EB)
    for i in range(3500):
        lidar_points_classified.append({
            "x": float(wall_x[i]), "y": float(wall_y[i]), "z": float(wall_z[i]),
            "classification": 3, "intensity": int(np.random.uniform(100, 180)),
            "r": 37, "g": 99, "b": 235
        })

    # Floor slab returns (Class 6 for building elements)
    # Adding 3000 points
    floor_x = np.random.uniform(145, 175, 3000)
    floor_y = np.random.uniform(144, 161, 3000)
    floor_z = np.random.choice([3.6, 7.2, 10.8, 14.4], 3000) + np.random.normal(0, 0.05, 3000)
    for i in range(3000):
        lidar_points_classified.append({
            "x": float(floor_x[i]), "y": float(floor_y[i]), "z": float(floor_z[i]),
            "classification": 6, "intensity": int(np.random.uniform(120, 180)),
            "r": 156, "g": 163, "b": 175
        })

    # Balcony edge returns (Class 3)
    # Adding 2000 points
    balcony_x = np.random.uniform(145, 175, 2000)
    balcony_y = np.random.choice([142.6, 162.4], 2000) + np.random.normal(0, 0.05, 2000)
    balcony_z = np.random.uniform(0.0, 18.0, 2000)
    for i in range(2000):
        lidar_points_classified.append({
            "x": float(balcony_x[i]), "y": float(balcony_y[i]), "z": float(balcony_z[i]),
            "classification": 3, "intensity": int(np.random.uniform(90, 150)),
            "r": 209, "g": 213, "b": 219
        })

    # 7. Precinct Buildings (12 surrounding structures)
    #
    # `status` describes a state in this invented dataset and nothing else. It
    # carried APPROVED / FLAGGED / UNDER_REVIEW / VIOLATION, which are regulatory
    # verdicts: nothing in this repository can approve a building or decide one
    # is a violation, and rendering "APPROVED" beside a real-looking society name
    # asserted that some authority had. `generate_precinct_buildings` above had
    # already been corrected to the DEMO_* vocabulary; this list is the one that
    # actually feeds the dataset, so it was the one that had to change.
    from shapely.geometry import box as shapely_box
    precinct_buildings_spec = [
        {"code": "B-01", "name": "Sai Krupa Towers", "type": "tower", "floors": 12, "x": 60, "y": 80, "w": 22, "h": 18, "fsi_target": 1.85, "status": "DEMO_STANDARD"},
        {"code": "B-02", "name": "Green Valley Apts", "type": "tower", "floors": 8, "x": 100, "y": 60, "w": 25, "h": 20, "fsi_target": 1.60, "status": "DEMO_STANDARD"},
        {"code": "B-03", "name": "Lakeview Heights", "type": "tower", "floors": 15, "x": 220, "y": 90, "w": 20, "h": 22, "fsi_target": 2.10, "status": "DEMO_EPOCH_COMPARISON"},
        {"code": "B-04", "name": "Sunrise CHS", "type": "tower", "floors": 7, "x": 280, "y": 180, "w": 24, "h": 16, "fsi_target": 1.45, "status": "DEMO_STANDARD"},
        {"code": "B-05", "name": "Sector 8 SRA Colony", "type": "slab", "floors": 4, "x": 50, "y": 200, "w": 40, "h": 12, "fsi_target": 1.20, "status": "DEMO_STANDARD"},
        # Not named after a real municipal body. An invented building labelled
        # "NMMC Staff Quarters" reads as that body's property, which this demo is
        # not and cannot speak for.
        {"code": "B-06", "name": "Sector 8 Staff Housing Block", "type": "slab", "floors": 5, "x": 300, "y": 60, "w": 35, "h": 14, "fsi_target": 1.55, "status": "DEMO_STANDARD"},
        {"code": "B-07", "name": "Orchid Row Villas", "type": "row_house", "floors": 2, "x": 320, "y": 280, "w": 50, "h": 10, "fsi_target": 0.85, "status": "DEMO_STANDARD"},
        {"code": "B-08", "name": "Palm Grove Cottages", "type": "row_house", "floors": 3, "x": 60, "y": 320, "w": 45, "h": 12, "fsi_target": 0.95, "status": "DEMO_STANDARD"},
        {"code": "B-09", "name": "Airoli Trade Center", "type": "commercial", "floors": 10, "x": 200, "y": 220, "w": 30, "h": 30, "fsi_target": 2.40, "status": "DEMO_ELEVATED_FSI"},
        {"code": "B-10", "name": "Sector 8 Market Complex", "type": "commercial", "floors": 3, "x": 250, "y": 300, "w": 35, "h": 25, "fsi_target": 1.10, "status": "DEMO_STANDARD"},
        {"code": "B-11", "name": "Metro View Residency", "type": "tower", "floors": 20, "x": 130, "y": 280, "w": 18, "h": 18, "fsi_target": 1.90, "status": "DEMO_EPOCH_COMPARISON"},
        # The name used to be "Unauthorized Structure". Nothing here establishes
        # what is permitted for this plot, so it cannot call the structure
        # unauthorised; what the dataset actually encodes is that the row is
        # present in the later epoch only.
        {"code": "B-12", "name": "Sector 8 Later-Epoch Slab", "type": "slab", "floors": 3, "x": 350, "y": 160, "w": 15, "h": 12, "fsi_target": 0.0, "status": "DEMO_EPOCH_COMPARISON"},
    ]

    precinct_buildings = []
    for idx, spec in enumerate(precinct_buildings_spec):
        floor_h = 3.5 if spec["type"] in ("tower", "commercial") else 3.2
        height = spec["floors"] * floor_h
        fp = shapely_box(spec["x"], spec["y"], spec["x"] + spec["w"], spec["y"] + spec["h"])
        fp_area = float(fp.area)
        plot_area = fp_area * 2.5  # assumed plot is 2.5x footprint
        built_up = fp_area * spec["floors"]
        fsi = round(built_up / plot_area, 2)
        units_per_floor = {"tower": 4, "slab": 6, "row_house": 1, "commercial": 8}.get(spec["type"], 4)
        risk = {"DEMO_STANDARD": "LOW", "DEMO_EPOCH_COMPARISON": "MEDIUM", "DEMO_ELEVATED_FSI": "HIGH"}.get(spec["status"], "LOW")
        b_code = spec["code"].replace("-", "")
        ulpin = f"2026092500{idx+1:04d}"
        has_basement = spec["type"] in ("tower", "commercial")
        b_levels = []
        b_units = []

        if has_basement:
            b_levels.append({
                "level_code": "B1",
                "floor_number": -1,
                "name": "Basement Parking & Infrastructure",
                "min_z": -3.5,
                "max_z": 0.0,
                "height_m": 3.5,
                "level_type": "BASEMENT",
                "boundary_geojson": mapping(fp),
            })
            p01_id = generate_proposed_3d_id(ulpin, "P", b_code, "B1", "P01")
            b_units.append({
                "unit_number": "P01",
                "proposed_3d_id": p01_id,
                "level_code": "B1",
                "unit_type": "P",
                "min_z": -3.5,
                "max_z": 0.0,
                "carpet_area_m2": round(fp_area * 0.85, 2),
                "built_up_area_m2": round(fp_area, 2),
                "volume_m3": round(fp_area * 3.5, 2),
                "footprint_geojson": mapping(fp),
                "coords": [[spec["x"], spec["y"]], [spec["x"] + spec["w"], spec["y"]], [spec["x"] + spec["w"], spec["y"] + spec["h"]], [spec["x"], spec["y"] + spec["h"]], [spec["x"], spec["y"]]],
                "parent_ulpin": ulpin,
                "building_code": spec["code"],
                "rights": [
                    {
                        "right_type": "OWNERSHIP",
                        "party_name": f"{spec['name']} CHS Parking Commons",
                        "party_type": "HOUSING_SOCIETY",
                        "share_pct": 100.0,
                        "encumbrance_status": "ACTIVE",
                        "color_hex": "#6B7280",
                    }
                ],
            })

        for f_num in range(spec["floors"]):
            l_code = "G" if f_num == 0 else (f"L{f_num:02d}" if spec["floors"] >= 10 else f"L{f_num}")
            min_z = round(f_num * floor_h, 2)
            max_z = round((f_num + 1) * floor_h, 2)
            b_levels.append({
                "level_code": l_code,
                "floor_number": f_num,
                "name": "Ground Floor" if f_num == 0 else f"Level {f_num}",
                "min_z": min_z,
                "max_z": max_z,
                "height_m": round(floor_h, 2),
                "level_type": "GROUND" if f_num == 0 else "HABITABLE",
                "boundary_geojson": mapping(fp),
            })

            cols = 2 if units_per_floor in (4, 2) else (3 if units_per_floor == 6 else (4 if units_per_floor == 8 else 1))
            rows = units_per_floor // cols if cols > 0 else 1
            col_w = spec["w"] / cols
            row_h = spec["h"] / rows

            owner_pool = [
                "Aarav Sharma", "Neha Patel", "Vikram Deshmukh", "Ananya Joshi",
                "Rajesh Iyer", "Pooja Verma", "Siddharth Nair", "Meera Kulkarni",
                "Amitabh Sen", "Sunita Shinde", "Deepak Rao", "Kavita Bhosle"
            ]

            u_idx = 1
            for r in range(rows):
                for c in range(cols):
                    ux0 = spec["x"] + c * col_w
                    uy0 = spec["y"] + r * row_h
                    u_coords = [
                        [ux0, uy0],
                        [ux0 + col_w, uy0],
                        [ux0 + col_w, uy0 + row_h],
                        [ux0, uy0 + row_h],
                        [ux0, uy0],
                    ]
                    u_poly = Polygon(u_coords)
                    u_num = f"{f_num}{u_idx:02d}" if f_num > 0 else f"G{u_idx:02d}"
                    u_type = "C" if spec["type"] == "commercial" else "U"
                    u_id = generate_proposed_3d_id(ulpin, u_type, b_code, l_code, u_num)
                    u_area = round(float(u_poly.area), 2)
                    owner = (
                        f"Commercial Suite {u_num} ({spec['name']})"
                        if spec["type"] == "commercial"
                        else owner_pool[(idx * 5 + f_num * 3 + u_idx) % len(owner_pool)]
                    )

                    b_units.append({
                        "unit_number": u_num,
                        "proposed_3d_id": u_id,
                        "level_code": l_code,
                        "unit_type": u_type,
                        "min_z": min_z,
                        "max_z": max_z,
                        "carpet_area_m2": round(u_area * 0.82, 2),
                        "built_up_area_m2": u_area,
                        "volume_m3": round(u_area * floor_h, 2),
                        "footprint_geojson": mapping(u_poly),
                        "coords": u_coords,
                        "parent_ulpin": ulpin,
                        "building_code": spec["code"],
                        "rights": [
                            {
                                "right_type": "OWNERSHIP",
                                "party_name": owner,
                                "party_type": "ORGANIZATION" if spec["type"] == "commercial" else "NATURAL_PERSON",
                                "share_pct": 100.0,
                                "encumbrance_status": "ACTIVE",
                                "color_hex": "#10B981",
                            }
                        ],
                    })
                    u_idx += 1

        # Rooftop / Solar Air Rights
        r01_id = generate_proposed_3d_id(ulpin, "A", b_code, "R01", "A01")
        b_levels.append({
            "level_code": "R01",
            "floor_number": spec["floors"],
            "name": "Rooftop & Air Rights",
            "min_z": round(height, 2),
            "max_z": round(height + 2.5, 2),
            "height_m": 2.5,
            "level_type": "ROOFTOP",
            "boundary_geojson": mapping(fp),
        })
        b_units.append({
            "unit_number": "A01",
            "proposed_3d_id": r01_id,
            "level_code": "R01",
            "unit_type": "A",
            "min_z": round(height, 2),
            "max_z": round(height + 2.5, 2),
            "carpet_area_m2": round(fp_area * 0.9, 2),
            "built_up_area_m2": fp_area,
            "volume_m3": round(fp_area * 2.5, 2),
            "footprint_geojson": mapping(fp),
            "coords": [[spec["x"], spec["y"]], [spec["x"] + spec["w"], spec["y"]], [spec["x"] + spec["w"], spec["y"] + spec["h"]], [spec["x"], spec["y"] + spec["h"]], [spec["x"], spec["y"]]],
            "parent_ulpin": ulpin,
            "building_code": spec["code"],
            "rights": [
                {
                    "right_type": "AIR_RIGHTS",
                    "party_name": f"{spec['name']} Solar & Rooftop Commons",
                    "party_type": "HOUSING_SOCIETY",
                    "share_pct": 100.0,
                    "encumbrance_status": "ACTIVE",
                    "color_hex": "#3B82F6",
                }
            ],
        })

        bldg_3d_id = generate_proposed_3d_id(ulpin, "U", b_code, "G", "001")

        precinct_buildings.append({
            "code": spec["code"],
            "name": spec["name"],
            "type": spec["type"],
            "floors": spec["floors"],
            "height_m": round(height, 1),
            "x": spec["x"], "y": spec["y"], "w": spec["w"], "h": spec["h"],
            "footprint_geojson": mapping(fp),
            "footprint_area_m2": round(fp_area, 2),
            "plot_area_m2": round(plot_area, 2),
            "total_built_up_area_m2": round(built_up, 2),
            "fsi": fsi,
            # No DCR for this plot has been read, so there is no permitted FSI to
            # compare against and no PASS/EXCEEDED verdict to publish. The 2.0
            # figure was invented here and "EXCEEDED" turned it into a
            # compliance determination this repository cannot make.
            "fsi_status": "NOT_ASSESSED",
            "max_allowed_fsi": None,
            "status": spec["status"],
            "risk_level": risk,
            "units_count": len(b_units),
            "basements_count": 1 if has_basement else 0,
            "ulpin": ulpin,
            "proposed_3d_id": bldg_3d_id,
            "levels": b_levels,
            "units": b_units,
            "has_epoch2_change": spec["code"] in ("B-03", "B-12"),
            # A difference between two generated epochs, not a finding about
            # permission: no approval record exists for either epoch.
            "epoch2_detail": (
                "Vertical addition present only in the later epoch"
                if spec["code"] in ("B-03", "B-12")
                else None
            ),
            "location": PARCEL_LOCATIONS.get(ulpin, _AIROLI_LOCATION),
        })

    # Per-building synthetic LiDAR clouds (local metric frame, same style as the hero scan).
    # ASPRS codes: 2 ground, 5 high vegetation, 6 building. Deterministic per building.
    lidar_by_ulpin: Dict[str, list] = {}
    for bld in precinct_buildings:
        code_idx = int(bld["code"].rsplit("-", 1)[1])
        seed = 271828 + code_idx * 1013
        rng = np.random.default_rng(seed)
        x0, y0, w, h = float(bld["x"]), float(bld["y"]), float(bld["w"]), float(bld["h"])
        ht = float(bld["height_m"])
        floors = int(bld.get("floors", 4))
        fl_h = ht / max(1, floors)
        pad = 12.0
        count = int(max(6000, min(16000, w * h * 16)))
        quarter = count // 4
        veg_n = max(count // 8, 350)

        # Ground terrain returns
        ground_x = rng.uniform(x0 - pad, x0 + w + pad, quarter)
        ground_y = rng.uniform(y0 - pad, y0 + h + pad, quarter)
        ground_z = rng.normal(0.0, 0.05, quarter)

        # Vegetation clusters around building perimeter
        veg_x = rng.uniform(x0 - pad * 0.8, x0 + w + pad * 0.8, veg_n)
        veg_y = rng.uniform(y0 - pad * 0.8, y0 + h + pad * 0.8, veg_n)
        veg_z = rng.uniform(0.0, min(ht * 0.45, 6.5), veg_n)

        # Roof slab returns
        roof_n = quarter
        roof_x = rng.uniform(x0, x0 + w, roof_n)
        roof_y = rng.uniform(y0, y0 + h, roof_n)
        roof_z = rng.normal(ht, 0.08, roof_n)

        # Exterior wall facade returns
        wall_n = quarter
        wall_side = rng.integers(0, 4, wall_n)
        wall_x = np.where(wall_side == 0, x0, np.where(wall_side == 1, x0 + w, rng.uniform(x0, x0 + w, wall_n)))
        wall_y = np.where(wall_side == 2, y0, np.where(wall_side == 3, y0 + h, rng.uniform(y0, y0 + h, wall_n)))
        wall_x = wall_x + rng.normal(0, 0.08, wall_n)
        wall_y = wall_y + rng.normal(0, 0.08, wall_n)
        wall_z = rng.uniform(0.0, ht, wall_n)

        # Interior floor slabs for cross-section / floor inspection
        slab_pts_per_floor = max(120, quarter // max(1, floors))
        slab_x_list, slab_y_list, slab_z_list = [], [], []
        for fl_idx in range(1, floors):
            fl_z = fl_h * fl_idx
            slab_x_list.append(rng.uniform(x0 + 0.3, x0 + w - 0.3, slab_pts_per_floor))
            slab_y_list.append(rng.uniform(y0 + 0.3, y0 + h - 0.3, slab_pts_per_floor))
            slab_z_list.append(rng.normal(fl_z, 0.04, slab_pts_per_floor))

        if slab_x_list:
            slab_x = np.concatenate(slab_x_list)
            slab_y = np.concatenate(slab_y_list)
            slab_z = np.concatenate(slab_z_list)
        else:
            slab_x, slab_y, slab_z = np.array([]), np.array([]), np.array([])

        # Rooftop architectural elements (elevator headhouse, water tank, parapet)
        rh_n = max(150, quarter // 6)
        rh_x = rng.uniform(x0 + w * 0.35, x0 + w * 0.65, rh_n)
        rh_y = rng.uniform(y0 + h * 0.35, y0 + h * 0.65, rh_n)
        rh_z = rng.uniform(ht, ht + min(3.0, fl_h * 0.8), rh_n)

        def _pts(xs: np.ndarray, ys: np.ndarray, zs: np.ndarray, cls: int, is_epoch2: bool = False) -> list:
            palettes = {2: (58, 47, 42), 5: (47, 143, 91), 6: (216, 161, 63)}
            ranges = {2: (80, 120), 5: (60, 110), 6: (120, 210)}
            n2 = int(len(xs))
            if n2 == 0:
                return []
            lo, hi = ranges.get(cls, (100, 200))
            cr, cg, cb = palettes.get(cls, (180, 180, 180))
            if is_epoch2:
                lo, hi = 240, 255
                cr, cg, cb = (239, 68, 68)  # Glowing crimson red for unauthorized vertical addition
            return [
                {
                    "x": float(xs[i]), "y": float(ys[i]), "z": float(zs[i]),
                    "classification": cls, "intensity": int(rng.uniform(lo, hi)),
                    "return_number": 2 if is_epoch2 else 1,
                    "r": cr, "g": cg, "b": cb,
                    "is_epoch2": is_epoch2,
                }
                for i in range(n2)
            ]

        # Check if building has unauthorized Epoch-2 vertical addition
        has_epoch2_viol = bld.get("has_epoch2_change", False) or bld.get("status") in ("DEMO_EPOCH_COMPARISON", "DEMO_ELEVATED_FSI")
        epoch2_pts = []
        if has_epoch2_viol:
            e2_n = max(300, quarter // 4)
            e2_x = rng.uniform(x0, x0 + w, e2_n)
            e2_y = rng.uniform(y0, y0 + h, e2_n)
            e2_z = rng.uniform(ht, ht + fl_h, e2_n)
            epoch2_pts = _pts(e2_x, e2_y, e2_z, 6, is_epoch2=True)

        cloud = (
            _pts(ground_x, ground_y, ground_z, 2)
            + _pts(veg_x, veg_y, veg_z, 5)
            + _pts(roof_x, roof_y, roof_z, 6)
            + _pts(wall_x, wall_y, wall_z, 6)
            + _pts(slab_x, slab_y, slab_z, 6)
            + _pts(rh_x, rh_y, rh_z, 6)
            + epoch2_pts
        )
        lidar_by_ulpin[bld["ulpin"]] = cloud

    return {
        "precinct": {
            "name": "Airoli Sector 8, Navi Mumbai",
            "state": "Maharashtra",
            "district": "Thane",
            "taluka": "Thane",
            "code": "MH-THN-AIR-SEC08",
            "village_ward": "Airoli Sector 8",
            "jurisdiction_code": "JUR-AIROLI-S8",
            "bounds": [0, 0, 400, 400],
            "center": [19.1557, 72.9984],
            "max_allowed_fsi": 2.00,
        },
        "hero_parcel": {
            "ulpin": "12345678901234",
            "survey_number": "CTS-100",
            "polygon_geojson": mapping(hero_poly),
            "document_area_m2": 1000.0,
            "calculated_area_m2": 1000.0,
            "gis_area_m2": 1000.0,
            "location": PARCEL_LOCATIONS["12345678901234"],
        },
        "surrounding_parcels": surrounding_parcels,
        "extra_parcels": extra_parcels,
        "parcel_locations": {**PARCEL_LOCATIONS, **_EXTRA_LOCATIONS},
        "hero_structure": {
            "building_code": "B-17",
            "name": "Shree Ganesh Chs (Building B-17)",
            "footprint_geojson": mapping(b17_poly),
            "ground_elevation_z": 0.0,
            "height_m": 18.0,
            "floors_count": 5,
            "basements_count": 1,
            "total_built_up_area_m2": total_built_up,
            "calculated_fsi": fsi_calculated,
            # Not a planning decision. No authority assessed this building, and
            # the model below has no means of granting or refusing permission.
            "status": "DEMO_STANDARD",
        },
        "levels": levels_data,
        "units": units_data,
        "subsurface_objects": subsurface_objects,
        "elevated_objects": elevated_objects,
        "epoch2_change": {
            "epoch_from": "2026 Epoch 1 Baseline",
            "epoch_to": "2027 Epoch 2 Monitoring",
            "delta_height_m": 3.5,
            "new_height_m": 21.5,
            "delta_floors": 1,
            "new_floor_count": 6,
            "delta_volume_m3": round(510.0 * 3.5, 2),
            "added_units": epoch2_added_units,
        },
        "architectural_elements": architectural_elements,
        "synthetic_lidar_points": lidar_points,
        "synthetic_lidar_points_classified": lidar_points_classified,
        "synthetic_lidar_points_by_ulpin": lidar_by_ulpin,
        "precinct_buildings": precinct_buildings,
        "all_precinct_units": [u for b in precinct_buildings for u in b["units"]],
        "precinct_units_by_ulpin": {b["ulpin"]: b["units"] for b in precinct_buildings},
    }
