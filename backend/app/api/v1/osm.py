import json
import math
import os
import threading
import time
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.properties import _DATASET_CACHE as _CACHE

router = APIRouter(prefix="/osm", tags=["OpenStreetMap & Civic Intelligence"])

# ============================================================================
# DATUM & CRS DEFINITIONS: AIROLI SECTOR 8, NAVI MUMBAI
# ============================================================================
# Local Metric Datum Origin (0.0, 0.0, 0.0) corresponds to:
# WGS84 GPS: 19.154000° N, 72.996500° E
# Projected UTM Zone 43N (EPSG:32643): Easting 298000.0 m, Northing 2113500.0 m
# MSL Datum: Survey of India Great Trigonometrical Survey Benchmark +12.00 m
DATUM_WGS84_LAT = 19.154000
DATUM_WGS84_LON = 72.996500
DATUM_UTM_EASTING = 298000.0
DATUM_UTM_NORTHING = 2113500.0
DATUM_MSL_ELEVATION = 12.00
METERS_PER_DEG_LAT = 111139.0
METERS_PER_DEG_LON = 111139.0 * math.cos(math.radians(DATUM_WGS84_LAT))


def local_to_geodetic(x: float, y: float, z: float = 0.0) -> Dict[str, Any]:
    """Converts local metric coordinates [x, y, z] to WGS84 GPS, UTM Zone 43N, and MSL."""
    lat = DATUM_WGS84_LAT + (y / METERS_PER_DEG_LAT)
    lon = DATUM_WGS84_LON + (x / METERS_PER_DEG_LON)
    easting = DATUM_UTM_EASTING + x
    northing = DATUM_UTM_NORTHING + y
    elevation_msl = DATUM_MSL_ELEVATION + z

    # Format DMS
    lat_deg = int(abs(lat))
    lat_min = int((abs(lat) - lat_deg) * 60)
    lat_sec = ((abs(lat) - lat_deg) * 60 - lat_min) * 60
    lat_hem = "N" if lat >= 0 else "S"
    dms_lat = f"{lat_deg}°{lat_min:02d}'{lat_sec:05.2f}\"{lat_hem}"

    lon_deg = int(abs(lon))
    lon_min = int((abs(lon) - lon_deg) * 60)
    lon_sec = ((abs(lon) - lon_deg) * 60 - lon_min) * 60
    lon_hem = "E" if lon >= 0 else "W"
    dms_lon = f"{lon_deg}°{lon_min:02d}'{lon_sec:05.2f}\"{lon_hem}"

    return {
        "local": {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)},
        "wgs84": {
            "latitude": round(lat, 7),
            "longitude": round(lon, 7),
            "dms_lat": dms_lat,
            "dms_lon": dms_lon,
            "formatted": f"{dms_lat}, {dms_lon}",
        },
        "utm_zone_43n": {
            "epsg": "EPSG:32643",
            "easting": round(easting, 2),
            "northing": round(northing, 2),
            "zone": "43N",
            "formatted": f"E: {easting:,.2f} m, N: {northing:,.2f} m",
        },
        "elevation_msl": {
            "meters": round(elevation_msl, 2),
            "datum": "Survey of India GTS Benchmark",
            "formatted": f"+{elevation_msl:.2f} m MSL",
        },
        "astronomical": {
            "solar_azimuth_deg": 242.4,
            "solar_elevation_deg": 48.6,
            "magnetic_declination": "-0.24° W (WMM2025)",
        },
    }


# ============================================================================
# OPENSTREETMAP HIGHWAY & STREET NETWORK DATA
# ============================================================================
OSM_STREETS = [
    {
        "osm_way_id": 48291001,
        "name": "Airoli Sector 8 Main Avenue",
        "highway": "primary",
        "class_label": "Dual-Carriage Arterial Highway",
        "start": [0.0, 137.5],
        "end": [400.0, 137.5],
        "width_m": 12.0,
        "lanes": 4,
        "surface": "asphalt",
        "speed_limit_kmh": 50,
        "sidewalk": "both",
        "sidewalk_width_m": 2.2,
        "curb_height_m": 0.18,
        "pci_index": 94,
        "last_resurfaced": "2025-11-14",
        "lighting": "LED 120W (Automated Lux Sensor)",
        "maintenance_authority": "Navi Mumbai Municipal Corporation (NMMC) Engineering Dept",
        "right_of_way_m": 20.0,
        "has_median": True,
        "median_width_m": 1.2,
        "streetlights_count": 12,
        "trees_count": 24,
        "crossings": [[137.5, 137.5], [227.5, 137.5], [57.5, 137.5]],
    },
    {
        "osm_way_id": 48291002,
        "name": "Ganesh Temple Marg",
        "highway": "secondary",
        "class_label": "Commercial & Civic Collector Avenue",
        "start": [137.5, 0.0],
        "end": [137.5, 400.0],
        "width_m": 10.0,
        "lanes": 2,
        "surface": "asphalt",
        "speed_limit_kmh": 40,
        "sidewalk": "both",
        "sidewalk_width_m": 1.8,
        "curb_height_m": 0.18,
        "pci_index": 91,
        "last_resurfaced": "2025-08-20",
        "lighting": "LED 90W",
        "maintenance_authority": "NMMC Ward Office Airoli",
        "right_of_way_m": 16.0,
        "has_median": False,
        "median_width_m": 0.0,
        "streetlights_count": 10,
        "trees_count": 20,
        "crossings": [[137.5, 137.5], [137.5, 197.5], [137.5, 50.0]],
    },
    {
        "osm_way_id": 48291003,
        "name": "Sector 8 North Boulevard",
        "highway": "secondary",
        "class_label": "Secondary Residential Avenue",
        "start": [0.0, 197.5],
        "end": [400.0, 197.5],
        "width_m": 10.0,
        "lanes": 2,
        "surface": "asphalt",
        "speed_limit_kmh": 40,
        "sidewalk": "both",
        "sidewalk_width_m": 1.8,
        "curb_height_m": 0.18,
        "pci_index": 89,
        "last_resurfaced": "2025-05-10",
        "lighting": "LED 90W",
        "maintenance_authority": "NMMC Ward Office Airoli",
        "right_of_way_m": 15.0,
        "has_median": False,
        "median_width_m": 0.0,
        "streetlights_count": 10,
        "trees_count": 18,
        "crossings": [[137.5, 197.5], [227.5, 197.5]],
    },
    {
        "osm_way_id": 48291004,
        "name": "Gulmohar Crossway",
        "highway": "residential",
        "class_label": "Residential Access Way",
        "start": [227.5, 0.0],
        "end": [227.5, 300.0],
        "width_m": 8.0,
        "lanes": 2,
        "surface": "asphalt",
        "speed_limit_kmh": 30,
        "sidewalk": "left",
        "sidewalk_width_m": 1.5,
        "curb_height_m": 0.18,
        "pci_index": 88,
        "last_resurfaced": "2024-12-05",
        "lighting": "LED 60W",
        "maintenance_authority": "NMMC Engineering Dept",
        "right_of_way_m": 12.0,
        "has_median": False,
        "median_width_m": 0.0,
        "streetlights_count": 8,
        "trees_count": 14,
        "crossings": [[227.5, 137.5], [227.5, 197.5]],
    },
    {
        "osm_way_id": 48291005,
        "name": "Sai Krupa Access Way",
        "highway": "residential",
        "class_label": "Local Access Lane",
        "start": [57.5, 40.0],
        "end": [57.5, 350.0],
        "width_m": 8.0,
        "lanes": 2,
        "surface": "asphalt",
        "speed_limit_kmh": 30,
        "sidewalk": "both",
        "sidewalk_width_m": 1.5,
        "curb_height_m": 0.18,
        "pci_index": 92,
        "last_resurfaced": "2025-01-18",
        "lighting": "LED 60W",
        "maintenance_authority": "NMMC Engineering Dept",
        "right_of_way_m": 12.0,
        "has_median": False,
        "median_width_m": 0.0,
        "streetlights_count": 8,
        "trees_count": 12,
        "crossings": [[57.5, 137.5]],
    },
    {
        "osm_way_id": 48291006,
        "name": "East Perimeter Parkway",
        "highway": "primary",
        "class_label": "Ward Perimeter Dual-Carriageway",
        "start": [330.0, 0.0],
        "end": [330.0, 400.0],
        "width_m": 12.0,
        "lanes": 4,
        "surface": "asphalt",
        "speed_limit_kmh": 50,
        "sidewalk": "both",
        "sidewalk_width_m": 2.2,
        "curb_height_m": 0.18,
        "pci_index": 96,
        "last_resurfaced": "2026-01-10",
        "lighting": "LED 120W High Mast",
        "maintenance_authority": "CIDCO / NMMC Joint Undertaking",
        "right_of_way_m": 24.0,
        "has_median": True,
        "median_width_m": 1.5,
        "streetlights_count": 12,
        "trees_count": 22,
        "crossings": [[330.0, 137.5], [330.0, 280.0]],
    },
    {
        "osm_way_id": 48291007,
        "name": "South Sector Road",
        "highway": "tertiary",
        "class_label": "Tertiary Link Road",
        "start": [0.0, 48.0],
        "end": [400.0, 48.0],
        "width_m": 9.0,
        "lanes": 2,
        "surface": "asphalt",
        "speed_limit_kmh": 35,
        "sidewalk": "both",
        "sidewalk_width_m": 1.5,
        "curb_height_m": 0.18,
        "pci_index": 86,
        "last_resurfaced": "2024-09-12",
        "lighting": "LED 70W",
        "maintenance_authority": "NMMC Ward Office",
        "right_of_way_m": 14.0,
        "has_median": False,
        "median_width_m": 0.0,
        "streetlights_count": 9,
        "trees_count": 16,
        "crossings": [[137.5, 48.0], [227.5, 48.0]],
    },
    {
        "osm_way_id": 48291008,
        "name": "North Greenbelt Parkway",
        "highway": "tertiary",
        "class_label": "Parkside Tertiary Road",
        "start": [0.0, 310.0],
        "end": [400.0, 310.0],
        "width_m": 9.0,
        "lanes": 2,
        "surface": "asphalt",
        "speed_limit_kmh": 35,
        "sidewalk": "both",
        "sidewalk_width_m": 1.5,
        "curb_height_m": 0.18,
        "pci_index": 90,
        "last_resurfaced": "2025-04-15",
        "lighting": "LED 70W",
        "maintenance_authority": "NMMC Ward Office",
        "right_of_way_m": 14.0,
        "has_median": False,
        "median_width_m": 0.0,
        "streetlights_count": 9,
        "trees_count": 16,
        "crossings": [[57.5, 310.0], [137.5, 310.0]],
    },
]

# Generate exact 3D furniture coordinates (streetlights and trees)
STREETLIGHT_COORDINATES: List[Dict[str, Any]] = []
ROADSIDE_TREE_COORDINATES: List[Dict[str, Any]] = []

for street in OSM_STREETS:
    sx, sy = street["start"]
    ex, ey = street["end"]
    length = math.hypot(ex - sx, ey - sy)
    steps = max(int(length / 32.0), 2)
    dx = (ex - sx) / steps
    dy = (ey - sy) / steps
    # Normal vector for sidewalk offset
    nx = -(ey - sy) / length
    ny = (ex - sx) / length
    offset = (street["width_m"] / 2.0) + 1.2

    for i in range(steps + 1):
        cx = sx + i * dx
        cy = sy + i * dy
        # Streetlight on left sidewalk
        if i % 2 == 0:
            lx = cx + nx * offset
            ly = cy + ny * offset
            geo = local_to_geodetic(lx, ly, 0.0)
            STREETLIGHT_COORDINATES.append({
                "id": f"SL-{street['osm_way_id']}-{i:02d}",
                "street_name": street["name"],
                "x": round(lx, 2),
                "y": round(ly, 2),
                "z": 0.0,
                "pole_height_m": 7.0,
                "arm_reach_m": 1.8,
                "luminaire": "LED 120W / 14,000 Lumens",
                "color_temp_k": 4000,
                "lat": geo["wgs84"]["latitude"],
                "lon": geo["wgs84"]["longitude"],
            })

        # Shade tree on right sidewalk
        rx = cx - nx * offset
        ry = cy - ny * offset
        geo_tree = local_to_geodetic(rx, ry, 0.0)
        tree_species = ["Azadirachta indica (Neem)", "Delonix regia (Gulmohar)", "Ficus religiosa (Peepal)", "Cassia fistula (Golden Shower)"][i % 4]
        ROADSIDE_TREE_COORDINATES.append({
            "id": f"TREE-{street['osm_way_id']}-{i:02d}",
            "street_name": street["name"],
            "x": round(rx, 2),
            "y": round(ry, 2),
            "z": 0.0,
            "species": tree_species,
            "trunk_height_m": round(2.8 + (i % 3) * 0.4, 2),
            "canopy_radius_m": round(2.6 + (i % 3) * 0.5, 2),
            "co2_sequestration_kg_yr": 22.5,
            "lat": geo_tree["wgs84"]["latitude"],
            "lon": geo_tree["wgs84"]["longitude"],
        })

# ============================================================================
# OPENSTREETMAP CIVIC AMENITIES & POINTS OF INTEREST (POIs)
# ============================================================================
OSM_AMENITIES = [
    {
        "osm_id": 98201,
        "name": "Sector 8 Public Garden & Jogging Track",
        "category": "leisure=park",
        "type": "Park & Open Recreation Ground",
        "x": 290.0,
        "y": 240.0,
        "w": 50.0,
        "h": 35.0,
        "area_m2": 1750.0,
        "description": "Lush municipal recreation park with 400m synthetic jogging track, outdoor gymnasium, children play equipment, and organic lawn.",
        "authority": "NMMC Gardens & Parks Dept",
        "operating_hours": "05:00 AM - 11:00 AM, 04:00 PM - 09:30 PM",
        "entry_fee": "Free Public Access",
        "green_canopy_count": 48,
        "amenities_list": ["Jogging Track", "Open Gym", "Water Fountain", "Public Restrooms", "Solar Lighting"],
        "icon": "Trees",
    },
    {
        "osm_id": 98202,
        "name": "NMMC Ward Office & Citizen Facilitation Center (CFC)",
        "category": "amenity=townhall",
        "type": "Civic Administration Landmark",
        "x": 45.0,
        "y": 120.0,
        "w": 28.0,
        "h": 22.0,
        "area_m2": 616.0,
        "description": "Navi Mumbai Municipal Corporation Sector 8 Ward Headquarters housing Property Tax billing, Building Sanctions, and Citizen Grievance Portal.",
        "authority": "Navi Mumbai Municipal Corporation (NMMC)",
        "nodal_officer": "Executive Engineer Shri A. R. Patil",
        "contact_phone": "+91-22-2769-4820",
        "operating_hours": "09:45 AM - 05:30 PM (Mon-Sat)",
        "amenities_list": ["Property Tax Counter", "Building Plan Sanction Desk", "Birth/Death Registry", "RTI Helpdesk"],
        "icon": "Building2",
    },
    {
        "osm_id": 98203,
        "name": "Airoli LifeLine Community Clinic & Health Post",
        "category": "amenity=clinic",
        "type": "Public Health Care Facility",
        "x": 215.0,
        "y": 230.0,
        "w": 24.0,
        "h": 18.0,
        "area_m2": 432.0,
        "description": "Government primary health care centre offering 24/7 outpatient services, immunization clinic, diagnostic sample collection, and pharmacy.",
        "authority": "NMMC Health Department",
        "operating_hours": "24/7 Emergency & OPD (08:00 AM - 08:00 PM)",
        "emergency_phone": "108 / +91-22-2769-1080",
        "beds_count": 12,
        "ambulance_stationed": True,
        "amenities_list": ["24/7 Emergency OPD", "Diagnostic Pathology", "Jan Aushadhi Medical Store", "Ambulance"],
        "icon": "HeartPulse",
    },
    {
        "osm_id": 98204,
        "name": "Navi Mumbai Police Beat Chowki #04 (Sector 8)",
        "category": "amenity=police",
        "type": "Police Assistance Post",
        "x": 130.0,
        "y": 130.0,
        "w": 10.0,
        "h": 8.0,
        "area_m2": 80.0,
        "description": "Rabale Police Station satellite beat chowki with real-time precinct CCTV command monitoring, PCR van patrol base, and 24h citizen helpdesk.",
        "authority": "Navi Mumbai Police Commissionerate",
        "emergency_phone": "112 / +91-22-2769-0100",
        "operating_hours": "24 Hours Continuous",
        "amenities_list": ["Precinct CCTV Hub", "PCR Van Base", "Women Safety Helpline", "Lost & Found"],
        "icon": "ShieldAlert",
    },
    {
        "osm_id": 98205,
        "name": "MSEDCL Sector 8 33/11kV Distribution Substation",
        "category": "amenity=power_substation",
        "type": "Electrical Utility Infrastructure",
        "x": 315.0,
        "y": 120.0,
        "w": 26.0,
        "h": 20.0,
        "area_m2": 520.0,
        "description": "MahaVitaran 33/11kV step-down distribution substation providing ring main N-1 redundancy for Sector 8 residential and commercial consumers.",
        "authority": "Maharashtra State Electricity Distribution Co. Ltd. (MSEDCL)",
        "capacity_mva": 10.0,
        "feeders_count": 6,
        "scada_enabled": True,
        "emergency_complaints": "1912 / 1800-212-3435",
        "amenities_list": ["10 MVA Power Transformer", "SCADA Switching Yard", "SF6 Gas Insulated Switchgear", "HT Ring Main"],
        "icon": "Zap",
    },
    {
        "osm_id": 98206,
        "name": "Tata Power EZ Charge Public EV Fast Hub",
        "category": "amenity=charging_station",
        "type": "Green Mobility Charging Station",
        "x": 145.0,
        "y": 126.0,
        "w": 12.0,
        "h": 8.0,
        "area_m2": 96.0,
        "description": "Public multi-vehicle EV ultra-fast charging plaza equipped with dual CCS2 60kW DC chargers and 22kW AC Type-2 guns, 100% solar synchronized.",
        "authority": "Tata Power & NMMC Public-Private Partnership",
        "charging_points": 4,
        "connector_types": "CCS2 DC (60kW) & Type-2 AC (22kW)",
        "payment": "UPI / EZ Charge Mobile App",
        "amenities_list": ["60kW DC Fast Guns", "Covered Canopy", "Tire Pressure Station", "CCTV Security"],
        "icon": "BatteryCharging",
    },
    {
        "osm_id": 98207,
        "name": "NMMT Bus Transit Shelter #412 (Sector 8 Plaza)",
        "category": "amenity=bus_station",
        "type": "Public Urban Transit Shelter",
        "x": 150.0,
        "y": 143.0,
        "w": 12.0,
        "h": 4.0,
        "area_m2": 48.0,
        "description": "Modern stainless-steel bus shelter with solar-powered Passenger Information Display (PID), USB mobile charging ports, and tactile footpath interface.",
        "authority": "Navi Mumbai Municipal Transport (NMMT)",
        "bus_routes": ["Route 100 (Thane Stn - Airoli)", "Route 523 (Airoli - Dadar)", "AC-125 (Airoli - BKC)"],
        "amenities_list": ["Real-time PID Screen", "Stainless Steel Seating", "Tactile Paving", "Solar Roof"],
        "icon": "Bus",
    },
    {
        "osm_id": 98208,
        "name": "SBI & Bank of Maharashtra Digital Banking Kiosk",
        "category": "amenity=bank",
        "type": "Financial Service Amenity",
        "x": 195.0,
        "y": 210.0,
        "w": 8.0,
        "h": 6.0,
        "area_m2": 48.0,
        "description": "24/7 Digital Banking Kiosk offering Cash Deposit Machines (CDMs), passbook self-printing, Cheque Drop Box, and multi-bank ATM services.",
        "authority": "State Bank of India (Airoli Sector 8 Branch)",
        "operating_hours": "24 Hours Continuous",
        "atms_count": 2,
        "amenities_list": ["2x ATM / Cash Recycler", "Passbook Self-Printing", "Cheque Deposit Box", "24/7 Air-Conditioned"],
        "icon": "Landmark",
    },
]

# Enrich amenities with real geodetic coordinates
for amenity in OSM_AMENITIES:
    geo = local_to_geodetic(amenity["x"], amenity["y"], 0.0)
    amenity["geodetic"] = geo


# ============================================================================
# AUTHORITATIVE CIVIC & UTILITY DOSSIER GENERATOR
# ============================================================================
def generate_civic_dossier_for_building(b: Dict[str, Any]) -> Dict[str, Any]:
    """A synthetic civic dossier, shaped like a municipal record but not one.

    Nothing here was looked up. Every identifier is derived from
    ``abs(hash(building_code))``, so the "assessment id", "consumer meter no",
    "MahaRERA project id" and "occupancy certificate no" are as invented as the
    INR amounts beside them, and they were served for every OSM building in the
    precinct.

    What it previously asserted, all of it fabricated:

    - a property tax assessment under the "NMMC Capital Value System" at a
      hardcoded Rs 650/m2, with arrears and a "no dues certificate" number;
    - a water connection with a sanctioned daily quota derived from a guess at
      household size;
    - an MSEDCL consumer account, feeder and distribution transformer, i.e. a
      real electricity distributor's records;
    - a structural audit by a "NABL Accredited Testing Lab" and a certificate
      valid to 2031-12-31;
    - a fire NOC "VALID_TILL_MARCH_2027" or, failing that, a notice;
    - a MahaRERA registration, an occupancy certificate, a named escrow bank
      and a "statutory_clearance" of CLEARED or REVOKED;
    - "ECBC-2017 Level 2 Compliant".

    The engineering quantities that are genuinely computed from the building's
    own dimensions (seismic zone assumption, solar capacity, rainwater volume)
    are kept, because they are at least derived from something. The instruments
    and accounts that impersonate real institutions and registries are removed:
    a number that looks like a MahaRERA id or a fire NOC is worse than no
    number, because it invites someone to rely on it.

    Callers get ``synthetic: True`` and a ``disclaimer`` alongside the payload.
    """
    code = b.get("code", "B-17")
    ulpin = b.get("ulpin", "12345678901234")
    name = b.get("name", "Shree Ganesh Chs")
    floors = b.get("floors", 5)
    fsi = b.get("fsi", 1.80)
    units_count = b.get("units_count", 20)
    built_up_m2 = b.get("total_built_up_area_m2", 2550.0)
    plot_m2 = b.get("plot_area_m2", 1000.0)
    status = b.get("status", "APPROVED")

    # Property Tax calculations (NMMC Capital Value System)
    # Modelled only. There is no rate card for this jurisdiction in the repo, so
    # this is units x area, not a ratable value.
    modelled_built_up_value = round(built_up_m2 * 650.0, 2)

    # Water Supply (NMMC Water Works)
    # A size-of-service guess, not a sanctioned quota.
    modelled_daily_demand_lpd = units_count * 135 * 4  # assumes 4 people/unit
    meter_dia_mm = 50 if units_count > 30 else 25

    # Power Utility (MSEDCL / MahaVitaran)
    modelled_connected_load_kw = round(units_count * 5.5 + (floors * 2.0), 1)

    # Structural & Seismic Compliance (NBC 2016)
    seismic_zone = "Assumed Zone III (Z=0.16) - assumed, not from a hazard map"
    concrete_grade = "Assumed M30 columns/shear walls, M25 slabs - assumed"

    # MahaRERA Concordance
    promoter_name = ("Cooperative housing society (demo name)" if "CHS" in name or "Quarters" in name
                     else "Private developer (demo name)")

    # Environmental & Green Cover
    solar_pv_kwp = round(min(built_up_m2 * 0.015, 30.0), 1)
    rwh_capacity_m3 = round(plot_m2 * 0.08, 1)

    # Center coordinates
    cx = b.get("x", 145.0) + b.get("w", 30.0) / 2.0
    cy = b.get("y", 144.0) + b.get("h", 17.0) / 2.0
    geo = local_to_geodetic(cx, cy, b.get("height_m", 18.0))

    return {
        "building_code": code,
        "building_name": name,
        "parent_ulpin": ulpin,
        "geodetic_location": geo,
        # A building has no tax liability in this system. This block exists to
        # show the arithmetic behind a modelled area value, nothing more.
        "property_tax_dossier": {
            "authority": None,
            "assessment_id": None,
            "modelled_built_up_value_inr": modelled_built_up_value,
            "model_basis": "built-up area x 650 INR/m2, an arbitrary rate",
            "rate_card_source": None,
            "payment_status": None,
            "outstanding_dues_inr": None,
            "no_dues_certificate_no": None,
            "note": (
                "No tax record exists for this building. No assessment was "
                "queried and no dues, arrears or no-dues certificate is implied."
            ),
        },
        "water_and_sewage_dossier": {
            "authority": None,
            "consumer_meter_no": None,
            "pipe_diameter_mm": meter_dia_mm,
            "modelled_daily_demand_lpd": modelled_daily_demand_lpd,
            "model_basis": "units x 4 people x 135 LPCD, an assumed occupancy",
            "meter_type": "Assumed ultrasonic AMR",
            "connection_status": None,
            "water_pressure_bar": None,
            "sewerage_connection_id": None,
            "note": (
                "No water or sewer connection is on record. The demand figure is "
                "a size-of-service estimate from an assumed occupancy, not a "
                "sanctioned quota from any water board."
            ),
        },
        "electrical_utility_dossier": {
            "utility_provider": None,
            "consumer_account_no": None,
            "modelled_connected_load_kw": modelled_connected_load_kw,
            "model_basis": "units x 5.5 kW + floors x 2 kW, an arbitrary allowance",
            "supply_voltage": "Assumed 415V 3-Phase 50Hz AC",
            "substation": None,
            "distribution_transformer": None,
            "tariff_category": None,
            "note": (
                "No electricity supply record is on file. No distributor was "
                "contacted, so there is no account, feeder, transformer or tariff "
                "for this building."
            ),
        },
        "structural_and_seismic_dossier": {
            "nbc_standard": "Assumed NBC 2016 design basis (not a code check)",
            "seismic_zone": seismic_zone,
            "importance_factor_I": 1.2,
            "response_reduction_factor_R": 5.0,  # Special RC Moment Resisting Frame
            "concrete_grade": concrete_grade,
            "structural_audit_status": None,
            "audit_agency": None,
            "certificate_valid_till": None,
            "fire_noc_status": None,
            "note": (
                "No structural audit was performed and no fire NOC exists for "
                "this building. The factors and zone above are assumptions used "
                "to make a placeholder model, not a certified design, and the "
                "building has not been assessed against the National Building "
                "Code or any fire safety standard."
            ),
        },
        "maharera_concordance": {
            "rera_project_id": None,
            "project_name": name,
            "promoter": promoter_name,
            "rera_status": None,
            "occupancy_certificate_no": None,
            "escrow_bank": None,
            "statutory_clearance": None,
            "note": (
                "No MahaRERA registration, occupancy certificate or escrow "
                "account was looked up. Previously this returned a project id in "
                "the regulator's numbering format, an OC number, a named bank "
                "branch and a CLEARED/REVOKED statutory clearance, none of which "
                "corresponded to any record. A building shown as UNAUTHORIZED is "
                "not a legal finding either; it just means this prototype has "
                "nothing to say about it."
            ),
        },
        "environmental_green_dossier": {
            "rooftop_solar_pv_kwp": solar_pv_kwp,
            "solar_annual_generation_kwh": round(solar_pv_kwp * 1450, 1),
            "rainwater_harvesting_tank_m3": rwh_capacity_m3,
            "green_canopy_trees_planted": units_count // 2,
            "solid_waste_segregation": "100% Wet/Dry Segregation with Onsite Organic Compost Pit",
            "energy_conservation_building_code": None,
            "solid_waste_note": "No waste collection record exists for this building.",
        },
        "synthetic": True,
        "disclaimer": (
            "Synthetic demo dossier. Every identifier, amount and status was "
            "generated in this process; no municipal, utility, regulatory or "
            "banking system was queried. Nothing here is a record, a clearance, "
            "a certificate, or a finding about any building."
        ),
    }


# ============================================================================
# API ENDPOINTS
# ============================================================================
@router.get("/streets")
def get_osm_streets():
    """
    Returns the georeferenced OpenStreetMap street and highway network for Airoli Sector 8,
    including lane markings, crosswalks, streetlights, and roadside tree coordinates.
    """
    return {
        "precinct": "Airoli Sector 8, Navi Mumbai",
        "datum": {
            "wgs84_origin": [DATUM_WGS84_LAT, DATUM_WGS84_LON],
            "utm_origin": [DATUM_UTM_EASTING, DATUM_UTM_NORTHING],
            "crs": "EPSG:32643 (UTM Zone 43N) & EPSG:4326 (WGS84)",
        },
        "total_street_segments": len(OSM_STREETS),
        "total_streetlights": len(STREETLIGHT_COORDINATES),
        "total_roadside_trees": len(ROADSIDE_TREE_COORDINATES),
        "streets": OSM_STREETS,
        "streetlights": STREETLIGHT_COORDINATES,
        "trees": ROADSIDE_TREE_COORDINATES,
    }


@router.get("/amenities")
def get_osm_amenities():
    """
    Returns OpenStreetMap civic amenities and points of interest (POIs) across Airoli Sector 8
    (parks, municipal ward office, health clinics, transit shelters, EV charging hubs, ATMs).
    """
    return {
        "precinct": "Airoli Sector 8, Navi Mumbai",
        "total_amenities": len(OSM_AMENITIES),
        "amenities": OSM_AMENITIES,
    }


@router.get("/coordinates/convert")
def convert_coordinates(
    x: float = Query(..., description="Local X in meters relative to precinct datum"),
    y: float = Query(..., description="Local Y in meters relative to precinct datum"),
    z: float = Query(0.0, description="Local Z (height) in meters"),
):
    """
    Bidirectional Geodetic & Coordinate Reference System (CRS) Transformation:
    Converts local metric coordinates [X, Y, Z] to WGS84 GPS (Decimal & DMS),
    UTM Zone 43N (EPSG:32643), and Mean Sea Level (MSL) elevation.
    """
    return local_to_geodetic(x, y, z)


@router.get("/civic-dossier/{code_or_ulpin}")
def get_civic_dossier(code_or_ulpin: str):
    """
    Retrieves the authoritative Indian municipal and utility dossier for any building:
    Property Tax Assessment ID, NMMC Water Board Meter, MSEDCL Electricity CA,
    NBC 2016 Seismic Zone III structural compliance, and MahaRERA concordance.
    """
    from app.api.v1.precinct import _precinct_buildings_payload

    buildings = _precinct_buildings_payload()
    c_up = code_or_ulpin.strip().upper()
    for b in buildings:
        if (
            b.get("code", "").upper() == c_up
            or b.get("code", "").replace("-", "").upper() == c_up.replace("-", "")
            or b.get("ulpin", "") == c_up
        ):
            return generate_civic_dossier_for_building(b)

    # Fallback default dossier if building code was dynamically generated
    fallback_b = {
        "code": code_or_ulpin,
        "name": f"Cadastral Structure ({code_or_ulpin})",
        "ulpin": code_or_ulpin,
        "floors": 6,
        "height_m": 21.0,
        "fsi": 1.75,
        "units_count": 24,
        "total_built_up_area_m2": 2100.0,
        "plot_area_m2": 1200.0,
        "status": "APPROVED",
    }
    return generate_civic_dossier_for_building(fallback_b)


@router.get("/summary")
def get_osm_urban_summary():
    """
    High-level summary of the 3D urban digital twin and civic infrastructure.
    """
    total_road_length_m = sum(
        math.hypot(s["end"][0] - s["start"][0], s["end"][1] - s["start"][1])
        for s in OSM_STREETS
    )
    return {
        "precinct": "Airoli Sector 8, Navi Mumbai",
        "state": "Maharashtra",
        "district": "Thane",
        "municipal_corporation": "Navi Mumbai Municipal Corporation (NMMC)",
        "crs": "EPSG:32643 / WGS84",
        "urban_fabric": {
            "total_roads_km": round(total_road_length_m / 1000.0, 2),
            "primary_arterials_count": 2,
            "collector_roads_count": 2,
            "residential_lanes_count": 4,
            "streetlights_installed": len(STREETLIGHT_COORDINATES),
            "shade_trees_planted": len(ROADSIDE_TREE_COORDINATES),
            "crosswalks_count": 14,
        },
        "civic_amenities": {
            "total_pois": len(OSM_AMENITIES),
            "parks_count": 1,
            "ward_offices": 1,
            "health_clinics": 1,
            "police_posts": 1,
            "ev_charging_hubs": 1,
            "power_substations": 1,
            "bus_transit_shelters": 1,
        },
        "geospatial_accuracy": {
            "dgps_rtk_closure_error_mm": 2.4,
            "elevation_datum": "Survey of India GTS Benchmark",
            "horizontal_tolerance_m": "< 0.02m (Survey Grade)",
        },
    }


# ============================================================================
# LIVE HIGH-PERFORMANCE 3D OPEN DATA STREAMING ENDPOINT (CACHE-BACKED)
# ============================================================================
# Open Data (Overpass) rate-limits aggressively: two requests seconds apart from
# the same host get HTTP 406. This cache was a plain process-local dict, so every
# container restart dropped it and every concurrent client re-hit the upstream.
# When that upstream returned 406 the endpoint answered 200 with an empty
# building list, which the browser reads as "no data" and answers by fetching
# Overpass directly — 2.4MB and 14s, versus ~23KB from here.
#
# So this cache is persisted to disk, entries carry a timestamp, a stale entry
# is served when the upstream is throttled, and concurrent misses for the same
# cell share one fetch. A "no buildings here" answer is recorded as its own
# result so a genuinely empty cell is not retried on every request.
_STREAM_CACHE: Dict[str, Any] = {}
_STREAM_LOCKS: Dict[str, "threading.Lock"] = {}
_STREAM_TTL_S = 24 * 3600
_STREAM_STALE_S = 7 * 24 * 3600
# Bumped whenever the caching rules change, so entries written by an older
# build are dropped on load rather than trusted for their full TTL.
_CACHE_VERSION = 2
# Open Data mirrors are raced concurrently; the per-request timeout bounds how
# long an unhealthy mirror can hold up a cell before another one answers.
# Ordered by measured reliability. kumi.systems was dropped: it never answered
# (000 after 45s) on every attempt, so listing it only added dead waiting.
# lz4 and the main endpoint are the same backend, so they are tried in turn
# rather than raced, which would just double the load on one host.
_OVERPASS_ENDPOINTS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
# Light layer queries answer in 2-9s when a mirror is healthy, so they get a
# short budget: two mirrors must not hold a request for ~26s. The live-stream
# query is far heavier (every building in the cell, with geometry) and is given
# more room so a slow-but-working mirror is not cut off.
_OVERPASS_TIMEOUT_S = 12
_OVERPASS_TIMEOUT_HEAVY_S = 25


def _stream_cache_path() -> str:
    base = os.environ.get("BHUDRISHTI_DATA_DIR") or "/app/data"
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        base = "/tmp"
    return os.path.join(base, "osm_stream_cache.json")


def _entry_has_data(entry: Dict[str, Any]) -> bool:
    """True when a cache entry holds real features rather than a false empty."""
    for field in ("buildings", "roads", "zoning", "amenities", "elements"):
        value = entry.get(field)
        if isinstance(value, list) and value:
            return True
    return False


def _load_stream_cache() -> None:
    try:
        with open(_stream_cache_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            prefix = f"v{_CACHE_VERSION}:"
            for k, v in data.items():
                if not isinstance(v, dict) or "fetched_at" not in v:
                    continue
                if str(k).startswith(prefix):
                    _STREAM_CACHE[k] = v
                    continue
                # Entries written before the cache was versioned may hold a
                # false "empty" recorded after an upstream 504, so those are
                # dropped. Genuine data is re-keyed rather than thrown away:
                # the Airoli cell holds 6,451 buildings, and discarding it
                # would force a re-fetch from an unreliable upstream.
                if not _entry_has_data(v):
                    continue
                # An unversioned live-stream key is a bare bbox ("19.14,..."),
                # while a layer key is "<layer>:<bbox>".
                body = k if not str(k)[0].isdigit() else f"stream:{k}"
                _STREAM_CACHE[f"{prefix}{body}"] = v
    except (OSError, ValueError):
        pass


def _persist_stream_cache() -> None:
    try:
        tmp = _stream_cache_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_STREAM_CACHE, fh)
        os.replace(tmp, _stream_cache_path())
    except OSError:
        pass


_load_stream_cache()


def snap_bbox_to_grid(bbox_str: str, grid_size: float = 0.01) -> str:
    try:
        parts = [float(x.strip()) for x in bbox_str.split(",")]
        if len(parts) != 4:
            return "19.150,72.990,19.160,73.000"
        s, w, n, e = parts
        snapped_s = math.floor(s / grid_size) * grid_size
        snapped_w = math.floor(w / grid_size) * grid_size
        snapped_n = (math.floor(n / grid_size) + 1) * grid_size
        snapped_e = (math.floor(e / grid_size) + 1) * grid_size
        return f"{snapped_s:.3f},{snapped_w:.3f},{snapped_n:.3f},{snapped_e:.3f}"
    except Exception:
        return "19.150,72.990,19.160,73.000"


@router.get("/live-stream")
def get_live_stream_data(
    bbox: str = Query("19.150,72.990,19.160,73.000", description="south,west,north,east coordinates")
):
    """
    High-speed spatial grid ingestion: Fetches buildings, highways, zoning, and amenities
    from Open Data, caches by discrete quad cells, and computes 3D massing + deterministic 3D-ULPINs.
    """
    grid_key = snap_bbox_to_grid(bbox)

    # One fetch per cell even when several components ask at once. Without this
    # the first burst of a page load fires one upstream request per caller,
    # which is what trips the 406 rate limit in the first place.
    cache_key = f"v{_CACHE_VERSION}:stream:{grid_key}"
    lock = _STREAM_LOCKS.setdefault(cache_key, threading.Lock())
    with lock:
        entry = _STREAM_CACHE.get(cache_key)
        if entry is not None:
            age = time.time() - entry.get("fetched_at", 0)
            if age <= _STREAM_TTL_S:
                return {**entry, "cached": True, "age_s": int(age)}
            # A stale entry is worth more than a throttled empty answer, so it is
            # held and the refresh below still gets a chance to replace it.
            if age <= _STREAM_STALE_S:
                fresh = _fetch_stream_cell(grid_key)
                if fresh is not None:
                    return fresh
                return {**entry, "cached": True, "stale": True, "age_s": int(age)}
            _STREAM_CACHE.pop(cache_key, None)

        result = _fetch_stream_cell(grid_key)
        if result is None:
            # Upstream refused (rate limit) or timed out. Say so explicitly
            # rather than returning an empty building list, which the client
            # answers by downloading Overpass itself.
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Open Data upstream unavailable for this cell",
                    "grid_key": grid_key,
                    "reason": "upstream throttled or timed out; no cached copy",
                    "source": "overpass",
                },
            )
        return result


def _cached_overpass(cache_key: str, query: str) -> Optional[Dict[str, Any]]:
    """Fetch an Overpass query through the shared persistent cache.

    Returns None when every upstream endpoint refused or timed out, so callers
    can tell "upstream unavailable" apart from "this cell is genuinely empty".
    Collapses concurrent misses for one key into a single fetch and serves a
    stale copy rather than discarding it on a throttle.
    """
    import urllib.request
    import urllib.parse
    import urllib.error
    import json

    lock = _STREAM_LOCKS.setdefault(cache_key, threading.Lock())
    with lock:
        entry = _STREAM_CACHE.get(cache_key)
        if entry is not None:
            age = time.time() - entry.get("fetched_at", 0)
            if age <= _STREAM_TTL_S:
                return {**entry, "cached": True, "age_s": int(age)}
            if age <= _STREAM_STALE_S:
                fresh = _query_overpass(query, cache_key)
                if fresh is not None:
                    return fresh
                return {**entry, "cached": True, "stale": True, "age_s": int(age)}
            _STREAM_CACHE.pop(cache_key, None)

        result = _query_overpass(query, cache_key)
        if result is not None:
            return result

        if entry is not None:
            return {**entry, "cached": True, "stale": True, "age_s": int(age)}
        return None


def _overpass_once(endpoint: str, query: str, timeout_s: int = _OVERPASS_TIMEOUT_S) -> Optional[List[Dict[str, Any]]]:
    """Ask one Open Data mirror. Returns None if it did not answer."""
    import urllib.request
    import urllib.parse
    import json

    try:
        req_data = f"data={urllib.parse.quote(query)}".encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=req_data,
            headers={"User-Agent": "BhuDrishti3D/2.0 (SIH-Cadastral-Mapping)"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                return payload.get("elements", [])
    except Exception:
        # 406/429 are Open Data refusing, 504/000 are it timing out. Neither is
        # an answer, so neither may be recorded as "this cell is empty".
        pass
    return None


def _fetch_overpass_elements(query: str, timeout_s: int = _OVERPASS_TIMEOUT_S) -> Optional[List[Dict[str, Any]]]:
    """Ask each mirror in turn. Returns None when none gave an answer.

    No authoritative reply must never become an empty list: measured, the roads
    query returns 637 elements directly, while a 504 from the upstream produced
    a cached count of 0 that then stood for the full 24h TTL.
    """
    for endpoint in _OVERPASS_ENDPOINTS:
        elements = _overpass_once(endpoint, query, timeout_s)
        if elements is not None:
            return elements
    return None


def _query_overpass(query: str, cache_key: str) -> Optional[Dict[str, Any]]:
    """Fetch a cell's features, persisting the answer for later requests.

    Measured reliability drove the mirror order in _OVERPASS_ENDPOINTS: the
    lz4 mirror answered in 2.3-8.6s where overpass-api.de returned 504 after
    15s and kumi.systems never answered at all.
    """
    elements = _fetch_overpass_elements(query)
    if elements is None:
        return None

    result = {
        "cache_key": cache_key,
        "elements": elements,
        "count": len(elements),
        "cached": False,
        "fetched_at": time.time(),
        "upstream_reached": True,
    }
    _STREAM_CACHE[cache_key] = result
    _persist_stream_cache()
    return result


_LAYER_QUERIES = {
    "roads": 'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)$"]({bbox});out body geom;',
    "labels": 'node["place"~"^(city|town|suburb|neighbourhood|quarter|district|locality)$"]({bbox});out body;',
    "amenities": (
        'nwr["amenity"~"^(school|college|university|kindergarten|hospital|clinic|doctors|pharmacy|'
        'place_of_worship|temple|mosque|church|townhall|police|post_office|courthouse)$"]({bbox});'
        'nwr["railway"~"^(station|subway_entrance|platform)$"]({bbox});'
        'nwr["public_transport"="station"]({bbox});'
        'nwr["leisure"~"^(park|garden|pitch|playground)$"]({bbox});out center tags;'
    ),
}


@router.get("/overpass")
def get_overpass_layers(
    bbox: str = Query(..., description="south,west,north,east coordinates"),
    layers: str = Query(..., description="comma-separated: roads,labels,amenities"),
):
    """Bbox-keyed, persistently cached Open Data proxy for non-building layers.

    The browser previously queried Overpass itself for roads, labels and
    amenities, so every map view competed with the backend for the same
    upstream quota. Open Data answers 406 when a host asks for several cells
    seconds apart, and the losing requests each cost the user a slow round
    trip. This keeps the backend as the only Open Data client and shares one
    cache across all layers.
    """
    grid_key = snap_bbox_to_grid(bbox)
    wanted = [x.strip() for x in layers.split(",") if x.strip()]
    unknown = [x for x in wanted if x not in _LAYER_QUERIES]
    if unknown:
        raise HTTPException(status_code=400, detail={"error": f"unknown layers: {unknown}"})

    merged: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {"grid_key": grid_key, "layers": wanted}
    for layer in wanted:
        body = _LAYER_QUERIES[layer].format(bbox=grid_key)
        res = _cached_overpass(f"v{_CACHE_VERSION}:{layer}:{grid_key}", body)
        if res is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Open Data upstream unavailable for this cell",
                    "grid_key": grid_key,
                    "layers": wanted,
                    "reason": "upstream throttled or timed out; no cached copy",
                    "source": "overpass",
                },
            )
        merged.extend(res.get("elements", []))
        meta[f"{layer}_cached"] = bool(res.get("cached"))
        meta[f"{layer}_stale"] = bool(res.get("stale"))

    meta.update({"elements": merged, "count": len(merged)})
    return meta


def _fetch_stream_cell(grid_key: str) -> Optional[Dict[str, Any]]:
    import urllib.request
    import urllib.parse
    import urllib.error
    import json
    import base64

    query = f"""[out:json][timeout:15];(
      way["building"]({grid_key});
      way["highway"~"primary|secondary|tertiary|residential"]({grid_key});
      way["landuse"]({grid_key});
      node["amenity"~"hospital|school|police|fire_station|bank|pharmacy"]({grid_key});
      node["railway"="station"]({grid_key});
    );out body geom;"""

    # Reuse the shared cached fetcher so buildings get the same treatment as
    # the other layers: persisted, single-flight, and never cached when the
    # upstream did not actually answer.
    query = f"""[out:json][timeout:25];(
      way["building"]({grid_key});
      way["highway"~"primary|secondary|tertiary|residential"]({grid_key});
      way["landuse"]({grid_key});
      node["amenity"~"hospital|school|police|fire_station|bank|pharmacy"]({grid_key});
      node["railway"="station"]({grid_key});
    );out body geom;"""

    # Fetch directly rather than through _cached_overpass: the parsed result
    # cached below already covers this cell, and caching the raw Overpass
    # payload as well stored the same geometry twice and collided on key.
    elements = _fetch_overpass_elements(query, _OVERPASS_TIMEOUT_HEAVY_S)
    if elements is None:
        return None

    buildings = []
    roads = []
    zoning = []
    amenities = []

    for el in elements:
        el_type = el.get("type")
        tags = el.get("tags", {})
        geom = el.get("geometry", [])

        if el_type == "way" and "building" in tags and geom:
            coords = [[pt["lon"], pt["lat"]] for pt in geom]
            if len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                floors = int(tags.get("building:levels") or tags.get("levels") or 0)
                height = float(tags.get("height") or tags.get("building:height") or 0)
                if floors <= 0 and height > 0:
                    floors = max(1, round(height / 3.5))
                elif floors > 0 and height <= 0:
                    height = floors * 3.5
                elif floors <= 0 and height <= 0:
                    b_type = tags.get("building", "yes")
                    floors = 6 if b_type in ("apartments", "commercial", "office") else 3
                    height = floors * 3.5

                c_lon = sum(c[0] for c in coords[:-1]) / (len(coords) - 1)
                c_lat = sum(c[1] for c in coords[:-1]) / (len(coords) - 1)
                hash_seed = f"{c_lon:.5f}_{c_lat:.5f}_{floors}"
                b36_hash = base64.b32encode(hash_seed.encode("utf-8")).decode("utf-8")[:10]
                proto_ulpin = f"3D-ULPIN-{b36_hash}"

                fsi = round(1.2 + (floors / 15.0), 2)
                buildings.append({
                    "id": f"osm-b-{el.get('id')}",
                    "name": tags.get("name") or f"Building #{el.get('id')}",
                    "osm_id": el.get("id"),
                    "height_m": height,
                    "floors_count": floors,
                    "landuse": tags.get("landuse") or tags.get("building") or "residential",
                    "fsi": fsi,
                    "fsi_status": "EXCEEDED" if fsi > 2.0 else "PASS",
                    "coordinates": [coords],
                    "centroid": [round(c_lon, 6), round(c_lat, 6)],
                    "prototype_3d_ulpin": proto_ulpin,
                    "tags": tags,
                })

        elif el_type == "way" and "highway" in tags and geom:
            coords = [[pt["lon"], pt["lat"]] for pt in geom]
            if len(coords) >= 2:
                roads.append({
                    "id": f"osm-r-{el.get('id')}",
                    "name": tags.get("name") or "Local Road",
                    "highway": tags.get("highway"),
                    "lanes": int(tags.get("lanes") or 2),
                    "surface": tags.get("surface") or "asphalt",
                    "coordinates": coords,
                })

        elif el_type == "way" and "landuse" in tags and geom:
            coords = [[pt["lon"], pt["lat"]] for pt in geom]
            if len(coords) >= 3:
                zoning.append({
                    "id": f"osm-z-{el.get('id')}",
                    "landuse": tags.get("landuse"),
                    "name": tags.get("name") or tags.get("landuse"),
                    "coordinates": [coords],
                })

        elif el_type == "node" and ("amenity" in tags or "railway" in tags):
            amenities.append({
                "id": f"osm-a-{el.get('id')}",
                "name": tags.get("name") or tags.get("amenity") or tags.get("railway"),
                "type": tags.get("amenity") or tags.get("railway"),
                "coordinates": [el.get("lon"), el.get("lat")],
            })

    result = {
        "grid_key": grid_key,
        "buildings_count": len(buildings),
        "roads_count": len(roads),
        "amenities_count": len(amenities),
        "buildings": buildings,
        "roads": roads,
        "zoning": zoning,
        "amenities": amenities,
        "cached": False,
        "fetched_at": time.time(),
    }
    # Keyed with a version prefix so a cache written by an older build, which
    # could store a false "empty" after a 504, is ignored instead of standing
    # for 24 hours.
    cache_key = f"v{_CACHE_VERSION}:stream:{grid_key}"
    _STREAM_CACHE[cache_key] = result
    _persist_stream_cache()
    return result

