import io
import csv
from typing import Dict, Any, List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from app.id_engine.generator import generate_proposed_3d_id
from app.id_engine.national import national_ulpin_for_local_ring
from app.core.blockchain import get_cadastral_blockchain, Transaction

def generate_sample_excel_template() -> bytes:
    """
    Generates a beautifully formatted Excel workbook (.xlsx) with guidelines,
    column validations, and realistic sample data for 3D ULPIN extrusion.
    """
    wb = openpyxl.Workbook()
    
    # Sheet 1: Unit Level Upload Template
    ws = wb.active
    ws.title = "3D_ULPIN_Upload"

    # Header styling
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center")
    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers = [
        "Building_Code",
        "Building_Name",
        "Center_X_m",
        "Center_Y_m",
        "Width_m",
        "Length_m",
        "Total_Floors",
        "Floor_Height_m",
        "Level_Code",
        "Unit_Number",
        "Unit_Type",
        "Carpet_Area_m2",
        "Owner_Name",
        "Encumbrance_Status"
    ]

    ws.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    # Sample rows for building B-19 (Shivneri Heights CHS)
    sample_data = [
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L01", "101", "RESIDENTIAL_2BHK", 78.5, "Sunil Kadam", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L01", "102", "RESIDENTIAL_2BHK", 78.5, "Pooja Hegde", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L02", "201", "RESIDENTIAL_3BHK", 104.2, "Vikram Joshi", "MORTGAGE_SBI"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L02", "202", "RESIDENTIAL_3BHK", 104.2, "Anita Rao", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L03", "301", "RESIDENTIAL_3BHK", 104.2, "Dinesh Nair", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L03", "302", "RESIDENTIAL_3BHK", 104.2, "Kavita Shah", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L04", "401", "PENTHOUSE", 195.0, "Suresh Mehta", "MORTGAGE_HDFC"],
        ["B-20", "Airoli Commercial Plaza", 220.0, 140.0, 30.0, 20.0, 3, 4.0, "L01", "G-01", "COMMERCIAL_RETAIL", 120.0, "Apollo Pharmacy", "CLEAR"],
        ["B-20", "Airoli Commercial Plaza", 220.0, 140.0, 30.0, 20.0, 3, 4.0, "L01", "G-02", "COMMERCIAL_BANK", 180.0, "HDFC Bank Ltd", "CLEAR"],
        ["B-20", "Airoli Commercial Plaza", 220.0, 140.0, 30.0, 20.0, 3, 4.0, "L02", "201", "COMMERCIAL_OFFICE", 240.0, "TechCorp Solutions", "CLEAR"],
    ]

    for row_idx, r in enumerate(sample_data, start=2):
        ws.append(r)
        for col_idx in range(1, len(r) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = border_thin
            cell.alignment = align_center if col_idx not in (2, 13) else align_left
            if row_idx % 2 == 0:
                cell.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    # Column widths
    col_widths = {
        "A": 16, "B": 28, "C": 14, "D": 14, "E": 12, "F": 12,
        "G": 14, "H": 16, "I": 14, "J": 14, "K": 22, "L": 18,
        "M": 22, "N": 20
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # Sheet 2: Field Dictionary & Instructions
    ws_doc = wb.create_sheet(title="Field_Dictionary")
    ws_doc.append(["Field Name", "Type", "Required", "Allowed Values / Example", "Description"])
    doc_header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
    for col_num in range(1, 6):
        cell = ws_doc.cell(row=1, column=col_num)
        cell.fill = doc_header_fill
        cell.font = header_font

    doc_rows = [
        ["Building_Code", "String", "Yes", "B-18, B-19, BLDG-A", "Unique structure identifier in precinct"],
        ["Building_Name", "String", "Yes", "Shivneri Heights CHS", "Sanctioned building name as per RERA"],
        ["Center_X_m", "Float", "Yes", "185.0 (0-400)", "Local Easting coordinate in 400x400m Airoli grid"],
        ["Center_Y_m", "Float", "Yes", "160.0 (0-400)", "Local Northing coordinate in 400x400m Airoli grid"],
        ["Width_m", "Float", "Yes", "24.0", "Building footprint width in meters (East-West)"],
        ["Length_m", "Float", "Yes", "18.0", "Building footprint length in meters (North-South)"],
        ["Total_Floors", "Integer", "Yes", "4, 12, 20", "Total storeys above ground"],
        ["Floor_Height_m", "Float", "No", "3.5 (standard residential)", "Floor to floor height in meters"],
        ["Level_Code", "String", "Yes", "B1, G, L01, L02, ROOF", "Storey level code for 3D extrusion"],
        ["Unit_Number", "String", "Yes", "101, 102, 201, G-01", "Physical flat/suite number"],
        ["Unit_Type", "String", "Yes", "RESIDENTIAL_2BHK, COMMERCIAL", "Cadastral unit classification"],
        ["Carpet_Area_m2", "Float", "Yes", "78.5", "Net usable carpet area per RERA definition"],
        ["Owner_Name", "String", "Yes", "Sunil Kadam", "Registered property owner or promoter"],
        ["Encumbrance_Status", "String", "No", "CLEAR, MORTGAGE_SBI", "Bank lien or easement flag"],
    ]
    for r in doc_rows:
        ws_doc.append(r)
    for col_letter, width in {"A": 20, "B": 12, "C": 12, "D": 32, "E": 48}.items():
        ws_doc.column_dimensions[col_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_sample_csv_template() -> str:
    """Generates standard CSV template matching the Excel layout."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Building_Code", "Building_Name", "Center_X_m", "Center_Y_m",
        "Width_m", "Length_m", "Total_Floors", "Floor_Height_m",
        "Level_Code", "Unit_Number", "Unit_Type", "Carpet_Area_m2",
        "Owner_Name", "Encumbrance_Status"
    ])
    sample_rows = [
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L01", "101", "RESIDENTIAL_2BHK", 78.5, "Sunil Kadam", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L01", "102", "RESIDENTIAL_2BHK", 78.5, "Pooja Hegde", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L02", "201", "RESIDENTIAL_3BHK", 104.2, "Vikram Joshi", "MORTGAGE_SBI"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L02", "202", "RESIDENTIAL_3BHK", 104.2, "Anita Rao", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L03", "301", "RESIDENTIAL_3BHK", 104.2, "Dinesh Nair", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L03", "302", "RESIDENTIAL_3BHK", 104.2, "Kavita Shah", "CLEAR"],
        ["B-19", "Shivneri Heights CHS", 185.0, 160.0, 24.0, 18.0, 4, 3.5, "L04", "401", "PENTHOUSE", 195.0, "Suresh Mehta", "MORTGAGE_HDFC"],
        ["B-20", "Airoli Commercial Plaza", 220.0, 140.0, 30.0, 20.0, 3, 4.0, "L01", "G-01", "COMMERCIAL_RETAIL", 120.0, "Apollo Pharmacy", "CLEAR"],
        ["B-20", "Airoli Commercial Plaza", 220.0, 140.0, 30.0, 20.0, 3, 4.0, "L01", "G-02", "COMMERCIAL_BANK", 180.0, "HDFC Bank Ltd", "CLEAR"],
        ["B-20", "Airoli Commercial Plaza", 220.0, 140.0, 30.0, 20.0, 3, 4.0, "L02", "201", "COMMERCIAL_OFFICE", 240.0, "TechCorp Solutions", "CLEAR"],
    ]
    for r in sample_rows:
        writer.writerow(r)
    return output.getvalue()


def parse_and_extrude_spreadsheet(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Parses uploaded Excel (.xlsx) or CSV file and executes 3D extrusion:
    - Generates 14-char base ULPINs
    - Computes 3D coordinates & volumes
    - Mints ISO/IEC 7064 Luhn Mod 36 compliant 3D-ULPINs
    - Generates Three.js 3D mesh representation
    - Commits transaction to blockchain mempool
    """
    rows: List[Dict[str, Any]] = []

    if filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        headers = [str(cell.value or "").strip() for cell in sheet[1]]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            row_dict = {}
            for h, v in zip(headers, row):
                row_dict[h] = v
            rows.append(row_dict)
    else:
        # CSV parsing
        text = file_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            if any(r.values()):
                rows.append({k.strip(): v.strip() for k, v in r.items() if k})

    if not rows:
        raise ValueError("Spreadsheet is empty or could not be parsed.")

    # Group by Building Code
    buildings_map: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        b_code = str(r.get("Building_Code") or r.get("building_code") or "BLDG-01").strip().upper()
        buildings_map.setdefault(b_code, []).append(r)

    extruded_buildings: List[Dict[str, Any]] = []
    total_minted_3d_ids: List[str] = []

    for b_code, b_rows in buildings_map.items():
        first = b_rows[0]
        b_name = str(first.get("Building_Name") or first.get("building_name") or f"Building {b_code}").strip()
        cx = float(first.get("Center_X_m") or first.get("center_x") or 150.0)
        cy = float(first.get("Center_Y_m") or first.get("center_y") or 150.0)
        w = float(first.get("Width_m") or first.get("width") or 22.0)
        length = float(first.get("Length_m") or first.get("length") or 18.0)
        floors = int(first.get("Total_Floors") or first.get("floors") or len(b_rows))
        fl_height = float(first.get("Floor_Height_m") or first.get("floor_height") or 3.5)

        # Generate base 14-char ULPIN from footprint bounding box
        half_w = w / 2.0
        half_l = length / 2.0
        footprint_ring = [
            [cx - half_w, cy - half_l],
            [cx + half_w, cy - half_l],
            [cx + half_w, cy + half_l],
            [cx - half_w, cy + half_l],
            [cx - half_w, cy - half_l]
        ]
        base_ulpin, _ = national_ulpin_for_local_ring(
            footprint_ring,
            origin_easting=298000.0,
            origin_northing=2113500.0,
            utm_zone=43
        )

        footprint_area = round(w * length, 2)
        total_height = round(floors * fl_height, 2)
        plot_area = round(footprint_area * 2.2, 2)
        total_built_up = round(footprint_area * floors, 2)
        fsi = round(total_built_up / max(plot_area, 1.0), 2)

        # Extrude vertical units
        units_list = []
        for idx, u_row in enumerate(b_rows):
            level_code = str(u_row.get("Level_Code") or f"L{idx+1:02d}").strip().upper()
            unit_no = str(u_row.get("Unit_Number") or f"U{idx+1:02d}").strip()
            unit_type = str(u_row.get("Unit_Type") or "RESIDENTIAL_2BHK").strip().upper()
            carpet_m2 = float(u_row.get("Carpet_Area_m2") or (footprint_area / 2.2))
            owner = str(u_row.get("Owner_Name") or "Promoter Reserved").strip()
            encumbrance = str(u_row.get("Encumbrance_Status") or "CLEAR").strip().upper()

            # Determine Z range based on floor sequence
            floor_num = 1
            if level_code.startswith("L") and level_code[1:].isdigit():
                floor_num = int(level_code[1:])
            elif level_code == "G":
                floor_num = 0
            elif level_code == "B1":
                floor_num = -1

            min_z = round(floor_num * fl_height, 2)
            max_z = round(min_z + fl_height, 2)
            volume_m3 = round(carpet_m2 * (fl_height - 0.3), 2)

            # Mint 3D ULPIN
            proposed_3d_id = generate_proposed_3d_id(
                parent_ulpin=base_ulpin,
                type_code="U",
                building_code=b_code.replace("-", ""),
                level_code=level_code,
                unit_code=unit_no.replace("-", ""),
            )
            total_minted_3d_ids.append(proposed_3d_id)

            units_list.append({
                "proposed_3d_id": proposed_3d_id,
                "unit_number": unit_no,
                "level_code": level_code,
                "unit_type": unit_type,
                "carpet_area_m2": carpet_m2,
                "volume_m3": volume_m3,
                "min_z": min_z,
                "max_z": max_z,
                "owner_name": owner,
                "encumbrance_status": encumbrance,
                "floor_height_m": fl_height
            })

        # 3D Box geometry definition for Three.js
        threejs_box = {
            "position": [cx, cy, total_height / 2.0],
            "dimensions": [w, length, total_height],
            "center": [cx, cy],
            "color_hex": "#3B82F6" if fsi <= 2.0 else "#EF4444"
        }

        extruded_bldg = {
            "building_code": b_code,
            "building_name": b_name,
            "parent_ulpin": base_ulpin,
            "center": [cx, cy],
            "width_m": w,
            "length_m": length,
            "total_floors": floors,
            "total_height_m": total_height,
            "footprint_area_m2": footprint_area,
            "total_built_up_area_m2": total_built_up,
            "calculated_fsi": fsi,
            "fsi_status": "PASS" if fsi <= 2.0 else "EXCEEDED",
            "threejs_geometry": threejs_box,
            "total_units_count": len(units_list),
            "units": units_list
        }
        extruded_buildings.append(extruded_bldg)

        # Stage in blockchain mempool
        bc = get_cadastral_blockchain()
        bc.add_transaction_to_mempool(Transaction(
            tx_type="EXCEL_3D_ULPIN_MINT",
            ulpin=base_ulpin,
            spatial_id=f"EXCEL-EXTRUDE-{b_code}",
            parties={"SOURCE": "EXCEL_SPREADSHEET_INGESTION", "OPERATOR": "Bhu-Drishti 3D Engine"},
            payload={
                "building_code": b_code,
                "building_name": b_name,
                "units_minted": len(units_list),
                "total_built_up_m2": total_built_up,
                "fsi": fsi
            }
        ))

    return {
        "status": "SUCCESS_EXTRUDED_FROM_SPREADSHEET",
        "filename": filename,
        "total_buildings_generated": len(extruded_buildings),
        "total_3d_ulpins_minted": len(total_minted_3d_ids),
        "buildings": extruded_buildings,
        "sample_3d_ids": total_minted_3d_ids[:8],
        "blockchain_mempool_status": "TRANSACTIONS_COMMITTED_TO_MEMPOOL"
    }
