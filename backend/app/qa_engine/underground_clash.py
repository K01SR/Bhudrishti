from typing import Dict, Any, List, Optional
from shapely.geometry import Polygon, LineString, box


class UndergroundClashDetector:
    """
    Subsurface Clash Detection Engine (Rule R009).
    Detects physical 3D volumetric and linear intersections between:
      - Building Basement Foundations
      - Stormwater / Sewage / Gas Utility Pipes
      - Deep Underground Metro Transit Corridors
    """

    def check_basement_utility_clash(
        self,
        basement_polygon_coords: List[List[float]],
        basement_min_z: float,
        basement_max_z: float,
        utility_start_xyz: List[float],
        utility_end_xyz: List[float],
        utility_radius_m: float = 0.4,
        utility_code: str = "PIPE-DRAIN-01",
    ) -> Dict[str, Any]:
        """
        Calculates 3D intersection between basement envelope and underground utility line.
        """
        # 1. Check vertical elevation overlap
        util_min_z = min(utility_start_xyz[2], utility_end_xyz[2]) - utility_radius_m
        util_max_z = max(utility_start_xyz[2], utility_end_xyz[2]) + utility_radius_m

        vertical_overlap = (util_max_z >= basement_min_z) and (util_min_z <= basement_max_z)
        if not vertical_overlap:
            return {
                "has_clash": False,
                "message": f"No vertical overlap between basement [{basement_min_z}, {basement_max_z}] and utility [{util_min_z}, {util_max_z}].",
            }

        # 2. Check 2D horizontal plane intersection
        basement_poly = Polygon(basement_polygon_coords)
        pipe_line_2d = LineString([utility_start_xyz[:2], utility_end_xyz[:2]])

        if not basement_poly.intersects(pipe_line_2d):
            return {
                "has_clash": False,
                "message": "Utility line does not intersect basement horizontal polygon footprint.",
            }

        # 3. Clash detected! Compute clash intersection segment
        intersection_geom = basement_poly.intersection(pipe_line_2d)
        clash_depth = round((utility_start_xyz[2] + utility_end_xyz[2]) / 2.0, 2)
        
        # Intersection coordinates
        clash_coords = list(intersection_geom.coords) if hasattr(intersection_geom, "coords") else []

        return {
            "has_clash": True,
            "severity": "CRITICAL",
            "rule_id": "R009",
            "utility_code": utility_code,
            "clash_depth_z": clash_depth,
            "penetration_length_m": round(float(intersection_geom.length), 2),
            "clash_intersection_coords": clash_coords,
            "message": (
                f"CRITICAL 3D SUBSURFACE CLASH: Utility {utility_code} penetrates basement foundation perimeter "
                f"at elevation Z={clash_depth}m with {round(float(intersection_geom.length), 2)}m internal penetration."
            ),
            "recommended_action": (
                "Reject basement design or issue mandatory municipal diversion notice for stormwater main PIPE-DRAIN-01 "
                "prior to cadastral approval."
            ),
        }
