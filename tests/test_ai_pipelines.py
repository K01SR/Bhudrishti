import pytest
import numpy as np
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset
from app.pipelines.building_extraction import BuildingExtractionPipeline
from app.pipelines.floor_segmentation import FloorSegmentationPipeline
from app.pipelines.vertical_delineation import VerticalDelineationPipeline
from app.pipelines.change_detection import ChangeDetectionPipeline


def test_building_extraction_pipeline():
    dataset = generate_synthetic_airoli_dataset()
    pts = dataset["synthetic_lidar_points"]
    extractor = BuildingExtractionPipeline()

    res = extractor.extract_from_points(pts)
    assert res["extracted_height_m"] == pytest.approx(18.0, rel=0.1)
    assert res["footprint_area_m2"] > 400.0


def test_floor_segmentation_pipeline():
    dataset = generate_synthetic_airoli_dataset()
    pts = dataset["synthetic_lidar_points"]
    segmenter = FloorSegmentationPipeline()

    res = segmenter.segment_floors(pts, ground_z=0.0, has_basement=True)
    assert res["detected_floor_count"] == 5
    assert res["has_basement"] is True
    assert res["total_levels_count"] == 6  # 1 basement + 5 floors


def test_vertical_delineation_3d_mesh():
    delineator = VerticalDelineationPipeline()
    poly_coords = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
    vol_res = delineator.extrude_unit_volume(poly_coords, min_z=0.0, max_z=3.5)

    assert vol_res["built_up_area_m2"] == 100.0
    assert vol_res["volume_m3"] == 350.0
    assert vol_res["mesh_3d"]["vertex_count"] == 8
    assert vol_res["mesh_3d"]["triangle_count"] == 12


def test_multi_epoch_change_detection():
    detector = ChangeDetectionPipeline()
    res = detector.detect_changes(
        epoch1_height=18.0,
        epoch2_height=21.5,
        epoch1_floors=5,
        epoch2_floors=6,
        footprint_area_m2=510.0,
    )
    assert res["change_detected"] is True
    # Was asserted as "Suspected Unauthorized Change". The pipeline compares two
    # supplied numbers and has no sanction record, no survey and no officer
    # review, so it cannot characterise a difference as unauthorised. The
    # arithmetic below is unchanged and still verified here.
    assert res["status"] == "Suspected change (unverified)"
    assert res["evidence_basis"] == "SYNTHETIC"
    assert "unauthorized" not in res["status"].lower()
    assert res["delta_height_m"] == 3.5
    assert res["delta_floors"] == 1
