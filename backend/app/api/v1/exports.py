import io
import csv
from typing import Dict, Any, Optional
from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from app.core.demo_gate import demo_mode_enabled, load_demo_dataset
from app.api.v1.properties import build_hero_property_response
from app.core.database import SyncSessionLocal
from app.models.national_twin import NationalTwin
from app.models.national_parcel import NationalParcel

router = APIRouter(prefix="/exports", tags=["Interoperability & Data Exports"])


def _resolve_property_data(ulpin: str) -> Dict[str, Any]:
    """Returns generator-shaped property data for any ULPIN, or None if unknown.

    Honors the requested ULPIN: for a real national parcel in the nationwide
    engine-first layer, the card is assembled from its persisted 3D digital twin
    (real georeferenced ULPIN, NBC setback, strata units). Falls back to precinct
    dataset, or -- only while the demo gate is open -- synthesizes on-demand for
    any OSM/custom 3D-ULPIN.

    Returns None when nothing matches and the gate is shut. Callers must treat
    that as "not published here" rather than inventing a record.
    """
    from app.id_engine.latex_pdf_generator import _get_default_prop_data

    if ulpin == "12345678901234":
        return _get_default_prop_data()

    # Resolved per request, not at import. A module-level snapshot froze
    # whatever the gate was doing when the process started, so a server that
    # booted with the gate open kept serving generated records after it was
    # shut -- and one that booted shut could never serve them again.
    dataset = load_demo_dataset() if demo_mode_enabled() else {}

    # 1. Check precinct buildings dataset
    u_clean = ulpin.strip().upper()
    precinct_bld = next((
        b for b in dataset.get("precinct_buildings", [])
        if b.get("ulpin", "").upper() == u_clean
        or b.get("code", "").replace("-", "").upper() == u_clean.replace("-", "")
        or b.get("code", "").upper() == u_clean
    ), None)

    if precinct_bld:
        fl_count = precinct_bld.get("floors", 4)
        h_m = float(precinct_bld.get("height_m", fl_count * 3.5))
        plot_m2 = float(precinct_bld.get("plot_area_m2", 1000.0))
        built_m2 = float(precinct_bld.get("total_built_up_area_m2", plot_m2 * precinct_bld.get("fsi", 1.8)))
        units = precinct_bld.get("units", [])
        if not units:
            units = []
            for fl in range(fl_count):
                lv_code = f"L{fl:02d}" if fl > 0 else "G"
                for u_idx in range(1, 5):
                    u_no = f"{fl}{u_idx:02d}" if fl > 0 else f"G{u_idx:02d}"
                    units.append({
                        "unit_number": u_no,
                        "proposed_3d_id": f"{precinct_bld.get('ulpin', ulpin)}/{precinct_bld.get('code')}-{lv_code}-{u_no}",
                        "level_code": lv_code,
                        "unit_type": "U",
                        "min_z": round(fl * (h_m / fl_count), 1),
                        "max_z": round((fl + 1) * (h_m / fl_count), 1),
                        "carpet_area_m2": round(built_m2 / (fl_count * 5), 1),
                        "built_up_area_m2": round(built_m2 / (fl_count * 4), 1),
                        "volume_m3": round((built_m2 / (fl_count * 4)) * (h_m / fl_count), 1),
                        "footprint_geojson": precinct_bld.get("footprint_geojson"),
                        "rights": [
                            {
                                "right_type": "OWNERSHIP",
                                "party_name": f"Registered Allottee (Flat {u_no})",
                                "party_type": "NATURAL_PERSON",
                                "share_pct": 100.0,
                                "encumbrance_status": "CLEAR",
                                "color_hex": "#10B981",
                            }
                        ],
                    })

        return {
            "parent_ulpin": precinct_bld.get("ulpin", ulpin),
            "structure": {
                "name": precinct_bld.get("name", f"Building {precinct_bld.get('code')}"),
                "building_code": precinct_bld.get("code", "B-01"),
                "floors_count": fl_count,
                "basements_count": precinct_bld.get("basements_count", 0),
                "height_m": h_m,
                "total_built_up_area_m2": built_m2,
                "calculated_fsi": precinct_bld.get("fsi", 1.8),
                "fsi_status": precinct_bld.get("fsi_status", "PASS"),
                "nbc_setback_m": 4.5,
                "jurisdiction": "JUR-AIROLI-S8",
            },
            "parcel": {
                "ulpin": precinct_bld.get("ulpin", ulpin),
                "survey_number": f"CTS-{precinct_bld.get('code')}",
                "polygon_geojson": precinct_bld.get("footprint_geojson"),
                "document_area_m2": plot_m2,
                "calculated_area_m2": plot_m2,
            },
            "units": units,
        }

    # 2. Check Database for NationalTwin
    #
    # `national_twins` holds geometry written by the generated seeder
    # (app/scripts/seed_mumbai_metropolitan.py), and its rows survive in the
    # database after the demo gate is shut. This lookup ran unconditionally, so
    # a real-data-only deployment would still resolve a ULPIN to an invented
    # building and print it on a property card. Only consult it while the gate
    # is open.
    twin = None
    parcel = None
    if demo_mode_enabled():
        try:
            with SyncSessionLocal() as db:
                twin = db.execute(
                    select(NationalTwin).where(NationalTwin.ulpin == ulpin.upper())
                ).scalar_one_or_none()
                if twin is not None:
                    parcel = db.execute(
                        select(NationalParcel).where(NationalParcel.ulpin == ulpin.upper())
                    ).scalar_one_or_none()
        except Exception:
            twin = None
            parcel = None

    if twin is not None:
        units = (twin.twin or {}).get("units", []) or twin.units_summary or []
        parcel_geojson = twin.footprint_polygon_geojson
        return {
            "parent_ulpin": twin.ulpin,
            "structure": {
                "name": twin.name or f"National 3D Cadastral Twin {twin.structure_code}",
                "building_code": twin.structure_code,
                "floors_count": twin.floors or 0,
                "basements_count": 0,
                "height_m": twin.height_m or 0.0,
                "total_built_up_area_m2": twin.built_up_area_m2 or 0.0,
                "calculated_fsi": twin.fsi or 0.0,
                "fsi_status": twin.fsi_status,
                "nbc_setback_m": twin.setback_m,
                "jurisdiction": twin.boundary_code,
            },
            "parcel": {
                "ulpin": twin.ulpin,
                "survey_number": twin.survey_number,
                "polygon_geojson": parcel_geojson,
                "document_area_m2": twin.plot_area_m2,
                "calculated_area_m2": twin.plot_area_m2,
            },
            "units": units,
        }

    # 3. Dynamic On-Demand Synthesis for arbitrary OSM or custom 3D-ULPIN
    #
    # This step invents a building: 6 floors, 21.0 m, a 900 m2 plot, FSI 1.75
    # marked PASS, a survey number of the form CTS-BLD-xxxx, a fixed polygon at
    # 145.0/145.0, and 24 units each carrying a "Registered Allottee" with
    # encumbrance_status CLEAR. For any string at all -- including a typo -- so
    # `GET /exports/pdf/property-card/ANYTHING` printed a property card for a
    # building that does not exist, with units coloured as verified.
    #
    # It is a demo affordance, so it now sits behind the same gate as the rest
    # of the generated dataset. With the gate shut there is no honest answer to
    # give for an unknown ULPIN, so the caller gets None and a 404.
    if not demo_mode_enabled():
        return None

    u_suffix = ulpin.replace("3D-ULPIN-", "").replace("ULPIN-", "").replace("-", "")
    clean_code = f"BLD-{u_suffix[:6]}" if u_suffix else "BLD-01"
    fl_count = 6
    h_m = 21.0
    calc_plot_m2 = 900.0
    calc_fsi = 1.75
    built_m2 = round(calc_plot_m2 * calc_fsi, 1)

    poly_geojson = {
        "type": "Polygon",
        "coordinates": [[[145.0, 145.0], [175.0, 145.0], [175.0, 170.0], [145.0, 170.0], [145.0, 145.0]]],
    }

    units = []
    for fl in range(fl_count):
        lv_code = f"L{fl:02d}" if fl > 0 else "G"
        for u_idx in range(1, 5):
            u_no = f"{fl}{u_idx:02d}" if fl > 0 else f"G{u_idx:02d}"
            units.append({
                "unit_number": u_no,
                "proposed_3d_id": f"{ulpin}/{clean_code}-{lv_code}-{u_no}",
                "level_code": lv_code,
                "unit_type": "U",
                "min_z": round(fl * 3.5, 1),
                "max_z": round((fl + 1) * 3.5, 1),
                "carpet_area_m2": 72.5,
                "built_up_area_m2": 88.0,
                "volume_m3": 308.0,
                "footprint_geojson": poly_geojson,
                "rights": [
                    {
                        "right_type": "OWNERSHIP",
                        "party_name": f"Registered Allottee (Flat {u_no})",
                        "party_type": "NATURAL_PERSON",
                        "share_pct": 100.0,
                        "encumbrance_status": "CLEAR",
                        "color_hex": "#10B981",
                    }
                ],
            })

    return {
        "parent_ulpin": ulpin,
        "structure": {
            "name": f"3D Cadastral Digital Twin ({ulpin})",
            "building_code": clean_code,
            "floors_count": fl_count,
            "basements_count": 0,
            "height_m": h_m,
            "total_built_up_area_m2": built_m2,
            "calculated_fsi": calc_fsi,
            "fsi_status": "PASS",
            "nbc_setback_m": 4.5,
            "jurisdiction": "JUR-SYNTH-3D",
        },
        "parcel": {
            "ulpin": ulpin,
            "survey_number": f"CTS-{clean_code}",
            "polygon_geojson": poly_geojson,
            "document_area_m2": calc_plot_m2,
            "calculated_area_m2": calc_plot_m2,
        },
        "units": units,
    }


@router.get("/cityjson")
async def export_cityjson():
    """
    Exports Building B-17 and its vertical units compliant with OGC CityJSON 1.1 / 2.0.
    CityJSON is the international developer-friendly standard for 3D city models.
    """
    prop = await build_hero_property_response()
    hero_s = prop["structure"]
    units = prop["units"]

    # Build CityJSON vertices array and CityObjects
    vertices = []
    vertex_map = {}

    def get_vertex_idx(x, y, z):
        key = (round(x, 3), round(y, 3), round(z, 3))
        if key not in vertex_map:
            vertex_map[key] = len(vertices)
            vertices.append([key[0], key[1], key[2]])
        return vertex_map[key]

    city_objects = {
        "Building_B17": {
            "type": "Building",
            "attributes": {
                "parent_ulpin": prop["parent_ulpin"],
                "name": hero_s["name"],
                "measuredHeight": hero_s["height_m"],
                "storeysAboveGround": hero_s["floors_count"],
                "storeysBelowGround": hero_s["basements_count"],
            },
            "children": [f"Unit_{u['unit_number']}" for u in units],
        }
    }

    # Add BuildingUnit objects with MultiSurface LoD 2.0 boundaries
    for u in units:
        mesh = u.get("mesh_3d", {})
        unit_verts = mesh.get("vertices", [])
        indices = mesh.get("indices", [])
        
        boundaries = []
        for i in range(0, len(indices), 3):
            i1, i2, i3 = indices[i], indices[i+1], indices[i+2]
            v1 = get_vertex_idx(unit_verts[i1*3], unit_verts[i1*3+1], unit_verts[i1*3+2])
            v2 = get_vertex_idx(unit_verts[i2*3], unit_verts[i2*3+1], unit_verts[i2*3+2])
            v3 = get_vertex_idx(unit_verts[i3*3], unit_verts[i3*3+1], unit_verts[i3*3+2])
            boundaries.append([[v1, v2, v3]])

        city_objects[f"Unit_{u['unit_number']}"] = {
            "type": "BuildingUnit",
            "attributes": {
                "proposed_3d_id": u["proposed_3d_id"],
                "level_code": u["level_code"],
                "min_z": u["min_z"],
                "max_z": u["max_z"],
                "volume_m3": u["volume_m3"],
                "carpet_area_m2": u["carpet_area_m2"],
            },
            "parents": ["Building_B17"],
            "geometry": [
                {
                    "type": "MultiSurface",
                    "lod": "2.0",
                    "boundaries": boundaries,
                }
            ],
        }

    return {
        "type": "CityJSON",
        "version": "1.1",
        "CityObjects": city_objects,
        "vertices": vertices,
        "metadata": {
            "title": "Bhu-Drishti 3D Cadastral Digital Twin — Building B-17",
            "referenceSystem": "EPSG:7755",
            "geographicExtent": [140.0, 140.0, -3.5, 180.0, 165.0, 18.0],
        },
    }


from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.core.database import get_db

@router.get("/geojson")
async def export_geojson(db: AsyncSession = Depends(get_db)):
    """Exports 2D Cadastre and Building Footprints as standard GeoJSON."""
    from app.api.v1.parcels import get_parcels_geojson
    return await get_parcels_geojson(db)

@router.get("/ifc")
async def export_ifc(ulpin: Optional[str] = None):
    """
    Exports Building structure and vertical strata units compliant with
    ISO 10303-21 / IFC 4.3 (Industry Foundation Classes) Building Information Model.
    """
    prop = await build_hero_property_response()
    hero_s = prop.get("structure", {})
    units = prop.get("units", [])
    bld_name = hero_s.get("name", "Building B-17")
    bld_code = hero_s.get("building_code", "B-17")
    target_ulpin = ulpin or prop.get("parent_ulpin", "12345678901234")

    # Generate standard ISO 10303-21 STEP physical file
    lines = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('ViewDefinition [CoordinationView_V2.0]', 'Bhu-Drishti 3D Cadastre IFC4 Export'), '2;1');",
        f"FILE_NAME('Bhu_Drishti_3D_{target_ulpin}.ifc', '2026-09-26T22:00:00', ('DoLR / Govt of Maharashtra'), ('Bhu-Drishti BIM Engine'), 'IfcOpenShell / Bhu-Drishti 1.0', 'Bhu-Drishti 3D Cadastral Platform', '');",
        "FILE_SCHEMA(('IFC4'));",
        "ENDSEC;",
        "DATA;",
        "#1=IFCPERSON($,'Administrator','DoLR',$,$,$,$,$);",
        "#2=IFCORGANIZATION($,'Department of Land Resources (DoLR)','Ministry of Rural Development',$,$);",
        "#3=IFCPERSONANDORGANIZATION(#1,#2,$);",
        "#4=IFCAPPLICATION(#2,'2026.1','Bhu-Drishti 3D Platform','BHU_DRISHTI_3D');",
        "#5=IFCOWNERHISTORY(#3,#4,$,.ADDED.,$,$,$,1727388000);",
        "#6=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
        "#7=IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);",
        "#8=IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);",
        "#9=IFCUNITASSIGNMENT((#6,#7,#8));",
        "#10=IFCPROJECT('0$r8Y_2vD29w7Gg6K9P8zK',#5,'Bhu-Drishti Cadastral 3D Twin',$,$,$,$,(#11),#9);",
        "#11=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#12,$);",
        "#12=IFCAXIS2PLACEMENT3D(#13,$,$);",
        "#13=IFCCARTESIANPOINT((0.,0.,0.));",
        f"#20=IFCSITE('1$s9Z_3wE30x8Hh7L0Q9yL',#5,'CTS 142/A Site',$,$,#12,$,$,.ELEMENT.,(19,9,20,520000),(72,59,54,240000),0.,$,$);",
        f"#30=IFCBUILDING('2$t0A_4xF41y9Ii8M1R0xM',#5,'{bld_name}',$,$,#12,$,$,.ELEMENT.,$,$,$);",
        "#40=IFCRELAGGREGATES('3$u1B_5yG52z0Jj9N2S1yN',#5,$,$,#10,(#20));",
        "#41=IFCRELAGGREGATES('4$v2C_6zH63a1Kk0O3T2zO',#5,$,$,#20,(#30));",
    ]

    # Add Building Storeys
    storey_ids = []
    entity_idx = 100
    levels = prop.get("levels", [])
    for lv in levels:
        s_id = entity_idx
        entity_idx += 1
        storey_ids.append(f"#{s_id}")
        lvl_name = lv.get("name", f"Level {lv.get('floor_number')}")
        min_z = float(lv.get("min_z", 0.0))
        lines.append(f"#{s_id}=IFCBUILDINGSTOREY('BStorey_{lv.get('level_code')}',#5,'{lvl_name}',$,$,#12,$,$,.ELEMENT.,{min_z});")

    if storey_ids:
        lines.append(f"#{entity_idx}=IFCRELAGGREGATES('5$w3D_7aI74b2Ll1P4U3aP',#5,'BuildingStoreys',$,#30,({','.join(storey_ids)}));")
        entity_idx += 1

    # Add Units as IFCSPACE
    space_ids = []
    for u in units:
        sp_id = entity_idx
        entity_idx += 1
        space_ids.append(f"#{sp_id}")
        u_num = u.get("unit_number", "Unit")
        u_id = u.get("proposed_3d_id", "")
        vol = float(u.get("volume_m3", 0.0))
        carpet = float(u.get("carpet_area_m2", 0.0))
        lines.append(f"#{sp_id}=IFCSPACE('Space_{u_num}',#5,'Unit {u_num} [{u_id}]',$,$,#12,$,$,.ELEMENT.,.INTERNAL.,$);")

    if space_ids:
        lines.append(f"#{entity_idx}=IFCRELAGGREGATES('6$x4E_8bJ85c3Mm2Q5V4bQ',#5,'SpatialUnits',$,#30,({','.join(space_ids[:20])}));")

    lines.append("ENDSEC;")
    lines.append("END-ISO-10303-21;")

    ifc_content = "\n".join(lines)
    return Response(
        content=ifc_content,
        media_type="application/x-step",
        headers={"Content-Disposition": f"attachment; filename=Bhu_Drishti_3D_{target_ulpin}.ifc"},
    )

@router.get("/canonical-json")
async def export_canonical_json():
    """Exports full Canonical Bhu-Drishti Property Model."""
    return await build_hero_property_response()


@router.get("/csv")
async def export_csv():
    """Exports Tabular CSV Summary of Vertical Units, Volumes, and Proposed 3D IDs."""
    prop = await build_hero_property_response()
    units = prop["units"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Unit_Number",
        "Proposed_3D_ID",
        "Level_Code",
        "Unit_Type",
        "Min_Z_m",
        "Max_Z_m",
        "Carpet_Area_m2",
        "Built_Up_Area_m2",
        "Volume_m3",
        "Parent_ULPIN",
        "Building_Code",
        "Status",
    ])

    for u in units:
        writer.writerow([
            u["unit_number"],
            u["proposed_3d_id"],
            u["level_code"],
            u["unit_type"],
            u["min_z"],
            u["max_z"],
            u["carpet_area_m2"],
            u["built_up_area_m2"],
            u["volume_m3"],
            prop["parent_ulpin"],
            prop["structure"]["building_code"],
            prop["status"],
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bhu_drishti_3d_units.csv"},
    )


@router.get("/pdf/property-card/{ulpin}")
def export_property_card_pdf(ulpin: str):
    """
    Exports official 3D Cadastral Property Card (Akhiv Patrika Form 3D) as a vector PDF.
    Features state header, ULPIN badge, 3D spatial envelope, stratified units schedule,
    blockchain proof, and verification QR code.

    Honors the requested ULPIN: for a national parcel (from the nationwide
    engine-first layer), the card is built from its persisted digital twin with
    the real georeferenced ULPIN, boundary hierarchy and insertion authority.
    """
    from app.id_engine.latex_pdf_generator import generate_property_card_pdf
    prop_data = _resolve_property_data(ulpin)
    if not prop_data:
        raise HTTPException(
            404,
            "No property record is published for this identifier. This "
            "deployment serves only records ingested from a real dataset; the "
            "generated showcase it can synthesise for demonstration is "
            "currently disabled.",
        )
    pdf_bytes = generate_property_card_pdf(prop_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Bhu_Drishti_3D_Property_Card_{ulpin}.pdf"}
    )


@router.get("/latex/property-card/{ulpin}")
def export_property_card_latex(ulpin: str):
    """
    Exports the complete, compilable LaTeX source code (.tex) for the official
    Government of Maharashtra 3D Cadastral Property Card.
    Compatible with pdflatex, lualatex, and Overleaf.
    """
    from app.id_engine.latex_pdf_generator import generate_latex_property_card
    prop_data = _resolve_property_data(ulpin)
    if not prop_data:
        raise HTTPException(
            404,
            "No property record is published for this identifier. This "
            "deployment serves only records ingested from a real dataset; the "
            "generated showcase it can synthesise for demonstration is "
            "currently disabled.",
        )
    tex_str = generate_latex_property_card(prop_data)
    return Response(
        content=tex_str,
        media_type="application/x-tex",
        headers={"Content-Disposition": f"attachment; filename=Bhu_Drishti_3D_Property_Card_{ulpin}.tex"}
    )


@router.get("/excel/cadastre")
def export_cadastral_excel_workbook():
    """
    Exports a multi-tab Excel workbook (.xlsx) containing:
    - Tab 1: 3D Units Registry (all units with volumes, carpet areas, and 3D ULPINs)
    - Tab 2: In-process record chain, labelled as a prototype. This was described
      as a "Sovereign Cadastral Blockchain Ledger"; it is a list of dicts built in
      this process, and the workbook says so on the sheet.
    """
    from app.id_engine.latex_pdf_generator import generate_cadastral_excel_workbook
    xlsx_bytes = generate_cadastral_excel_workbook()
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Bhu_Drishti_Cadastral_Register.xlsx"}
    )
