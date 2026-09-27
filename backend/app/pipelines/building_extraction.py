import numpy as np
from typing import Dict, Any, Tuple, List, Optional
from shapely.geometry import Polygon, MultiPoint, mapping
from shapely.ops import unary_union


class BuildingExtractionPipeline:
    """
    Component 1: Automated Building Footprint and Height Extraction from LiDAR.

    What this actually computes: a 5th-percentile ground elevation, a height
    threshold above it, then the 2D convex hull of the surviving XY positions,
    simplified at 0.5 m. No clustering of any kind runs.

    An earlier `method` string advertised "Spatial Point Clustering". There is
    no clustering step, so there is also no separation of adjacent buildings: one
    call returns the hull of everything above the threshold. A hull also fills
    concave courtyards and L-shaped re-entrant corners with solid area, so the
    footprint is an outer envelope and will overstate area for non-convex
    buildings. Callers that need a true outline need a real segmentation step,
    which this is not.
    """

    def __init__(self, ground_threshold_m: float = 0.5):
        self.ground_threshold_m = ground_threshold_m

    def extract_from_points(
        self,
        points: np.ndarray,  # Nx3 array: [x, y, z]
        ground_z: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Extracts 2D footprint polygon, height, and point statistics from point cloud.
        """
        if len(points) == 0:
            raise ValueError("Empty point cloud received for building extraction.")

        z_coords = points[:, 2]
        if ground_z is None:
            # Estimate ground elevation as the 5th percentile of Z
            ground_z = float(np.percentile(z_coords, 5))

        # Filter out ground returns
        non_ground_mask = z_coords > (ground_z + self.ground_threshold_m)
        building_points = points[non_ground_mask]

        if len(building_points) < 10:
            # Fallback if sparse
            building_points = points

        # Calculate building height
        max_z = float(np.percentile(building_points[:, 2], 98))
        extracted_height = round(max_z - ground_z, 2)

        # 2D projection for footprint extraction
        xy_points = building_points[:, :2]
        multi_pt = MultiPoint([tuple(pt) for pt in xy_points])
        
        # Convex hull / simplified bounding polygon
        hull = multi_pt.convex_hull
        if hull.geom_type != "Polygon":
            hull = hull.buffer(1.0).envelope

        # Simplify to clean architectural corners
        simplified_footprint = hull.simplify(tolerance=0.5, preserve_topology=True)
        footprint_geojson = mapping(simplified_footprint)
        footprint_area = round(float(simplified_footprint.area), 2)

        return {
            # Names the two steps that run. Convex hull means an outer envelope,
            # not a traced outline, and no point clustering separates neighbours.
            "method": (
                "Percentile Ground Filter (5th/98th) + Convex Hull "
                "Footprint simplified at 0.5 m"
            ),
            "ground_elevation_z": round(ground_z, 2),
            "max_elevation_z": round(max_z, 2),
            "extracted_height_m": extracted_height,
            "footprint_area_m2": footprint_area,
            "footprint_geojson": footprint_geojson,
            "raw_point_count": len(points),
            "building_point_count": len(building_points),
            "point_density_pts_m2": round(len(building_points) / max(footprint_area, 1.0), 1),
        }

    def evaluate_against_ground_truth(
        self,
        extracted_polygon: Polygon,
        ground_truth_polygon: Polygon,
        extracted_height: float,
        ground_truth_height: float,
    ) -> Dict[str, float]:
        """
        Evaluates extraction quality against known synthetic ground truth.
        Computes IoU (Intersection over Union), Precision, Recall, and Height Error.
        """
        intersection = extracted_polygon.intersection(ground_truth_polygon).area
        union = extracted_polygon.union(ground_truth_polygon).area
        iou = round(float(intersection / union) if union > 0 else 0.0, 4)
        
        precision = round(float(intersection / extracted_polygon.area) if extracted_polygon.area > 0 else 0.0, 4)
        recall = round(float(intersection / ground_truth_polygon.area) if ground_truth_polygon.area > 0 else 0.0, 4)
        height_error_m = round(abs(extracted_height - ground_truth_height), 2)

        return {
            "iou": iou,
            "precision": precision,
            "recall": recall,
            "height_error_m": height_error_m,
        }
