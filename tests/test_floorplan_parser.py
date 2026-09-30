import io
import pytest
import ezdxf
from app.pipelines.floorplan_parser import floorplan_parser


def test_floorplan_manual_trace_ingestion():
    """Verify manual trace polygon ingestion and 3D strata extrusion."""
    # 2 unit polygons on Level 1 (3.6m to 7.2m)
    unit1_ring = [[0.0, 0.0], [10.0, 0.0], [10.0, 8.0], [0.0, 8.0], [0.0, 0.0]]  # 80 m2
    unit2_ring = [[10.0, 0.0], [20.0, 0.0], [20.0, 8.0], [10.0, 8.0], [10.0, 0.0]] # 80 m2

    result = floorplan_parser.parse_manual_trace(
        unit_polygons=[unit1_ring, unit2_ring],
        parent_ulpin="12345678901234",
        building_code="B17",
        level_code="L01",
        base_elevation_m=3.6,
        floor_height_m=3.6
    )

    assert result["source_type"] == "FLOOR_PLAN_MANUAL_TRACE"
    assert result["units_count"] == 2
    assert result["total_level_carpet_area_m2"] == 131.2
    assert result["total_level_volume_m3"] == 576.0  # 160 * 3.6

    u1 = result["units"][0]
    assert u1["unit_code"] == "101"
    assert u1["built_up_area_m2"] == 80.0
    assert u1["carpet_area_m2"] == 65.6
    assert u1["volume_m3"] == 288.0
    assert u1["min_z"] == 3.6
    assert u1["max_z"] == 7.2
    assert "mesh3d" in u1
    assert len(u1["mesh3d"]["vertices"]) > 0
    assert len(u1["mesh3d"]["indices"]) > 0
    assert u1["source"] == "manual_trace_over_floor_plan"


def test_floorplan_dxf_ingestion_with_real_ezdxf():
    """Verify real AutoCAD DXF polyline extraction and 3D extrusion via ezdxf."""
    # Create an in-memory DXF document with 2 closed LWPOLYLINE units
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Unit 101: 12m x 10m = 120 m2
    msp.add_lwpolyline(
        [(0, 0), (12, 0), (12, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "UNITS"}
    )

    # Unit 102: 14m x 10m = 140 m2
    msp.add_lwpolyline(
        [(12, 0), (26, 0), (26, 10), (12, 10)],
        close=True,
        dxfattribs={"layer": "UNITS"}
    )

    stream = io.StringIO()
    doc.write(stream)
    dxf_bytes = stream.getvalue().encode("utf-8")

    result = floorplan_parser.parse_dxf_bytes(
        dxf_bytes=dxf_bytes,
        parent_ulpin="12345678901234",
        building_code="B17",
        level_code="L02",
        base_elevation_m=7.2,
        floor_height_m=3.6
    )

    assert result["source_type"] == "FLOOR_PLAN_DXF"
    assert result["units_count"] == 2
    assert result["total_level_carpet_area_m2"] == 213.2
    assert result["total_level_volume_m3"] == 936.0  # 260 * 3.6

    for unit in result["units"]:
        assert unit["min_z"] == 7.2
        assert unit["max_z"] == 10.8
        assert unit["source"] == "autocad_dxf_vector_parser"
        assert "mesh3d" in unit
        assert len(unit["mesh3d"]["vertices"]) > 0
