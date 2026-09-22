import numpy as np
from typing import Dict, Any, List, Tuple
from scipy.signal import find_peaks


class FloorSegmentationPipeline:
    """
    Component 2: Automated Floor Level Segmentation via Point Cloud Height Distribution.

    What this actually computes: the storey count is
    ``round(total_height / expected_floor_height_m)`` and the levels are uniform
    bands of that count spanning ground_z to max_z. The Z-density histogram and
    its peaks are computed but do not influence the result.

    An earlier `method` string advertised "Z-Density Peak Detection & Structural
    Slab Clustering". Neither clustering nor peak-based assignment happened: the
    detected `peak_elevations` were assigned and then dropped on the floor, so
    every reported level came from the uniform height rule. The string now
    describes the rule that runs.
    """

    def __init__(self, expected_floor_height_m: float = 3.6):
        self.expected_floor_height_m = expected_floor_height_m

    def segment_floors(
        self,
        points: np.ndarray,
        ground_z: float = 0.0,
        has_basement: bool = True,
        basement_depth_m: float = 3.5,
    ) -> Dict[str, Any]:
        """
        Segments the cloud into discrete storey bands from its total height.

        Uniform height-based bands only; see the class docstring. A density peak
        is not evidence of a slab in this implementation, so none is claimed.
        """
        z_coords = points[:, 2]
        above_ground_z = z_coords[z_coords >= ground_z]
        
        if len(above_ground_z) == 0:
            above_ground_z = z_coords

        max_z = float(np.max(above_ground_z))
        total_height = max_z - ground_z

        # Compute vertical elevation histogram (bin size = 0.2m)
        bin_width = 0.2
        bins = np.arange(ground_z, max_z + bin_width, bin_width)
        hist, bin_edges = np.histogram(above_ground_z, bins=bins)

        # Density peaks are computed for reference but do NOT set the levels.
        # `peak_elevations` used to be assigned from these peaks and then never
        # read, so the returned bands always came from the uniform height rule
        # further down despite what the `method` string claimed. Nothing
        # downstream uses the peaks now, and the method string says so.
        min_peak_distance = int(2.4 / bin_width)
        peaks, properties = find_peaks(hist, distance=min_peak_distance, prominence=np.max(hist) * 0.15)

        floor_levels: List[Dict[str, Any]] = []

        # 1. Add Basement if present
        if has_basement:
            floor_levels.append({
                "level_code": "B1",
                "floor_number": -1,
                "name": "Basement Parking & Utility Level",
                "level_type": "BASEMENT",
                "min_z": round(ground_z - basement_depth_m, 2),
                "max_z": round(ground_z, 2),
                "height_m": round(basement_depth_m, 2),
            })

        # 2. Add Above-Ground Floors
        # `above_count` was computed here from the discarded peak elevations and
        # never read; the uniform height rule below is the only thing that sets
        # the storey count.
        num_floors = max(1, int(round(total_height / self.expected_floor_height_m)))
        step = total_height / num_floors

        for i in range(num_floors):
            f_num = i + 1
            l_code = "G" if f_num == 1 else f"L{f_num - 1:02d}"
            f_name = "Ground Floor" if f_num == 1 else f"Floor {f_num - 1}"
            z_start = round(ground_z + i * step, 2)
            z_end = round(ground_z + (i + 1) * step, 2)
            floor_levels.append({
                "level_code": l_code,
                "floor_number": f_num,
                "name": f_name,
                "level_type": "GROUND" if f_num == 1 else "HABITABLE",
                "min_z": z_start,
                "max_z": z_end,
                "height_m": round(z_end - z_start, 2),
            })

        return {
            # Uniform height-derived bands. Peak detection runs above but does not
            # assign levels, so it is not named as the method.
            "method": (
                f"Uniform storey bands from total height / "
                f"{self.expected_floor_height_m} m expected storey height"
            ),
            "detected_floor_count": num_floors,
            "has_basement": has_basement,
            "total_levels_count": len(floor_levels),
            "floor_levels": floor_levels,
        }

    def evaluate_floor_accuracy(
        self,
        detected_floors: int,
        ground_truth_floors: int,
    ) -> Dict[str, float]:
        """Calculates Floor-Count Accuracy and Absolute Error."""
        error = abs(detected_floors - ground_truth_floors)
        accuracy = 1.0 if error == 0 else max(0.0, 1.0 - (error / ground_truth_floors))
        return {
            "floor_count_accuracy": round(accuracy, 4),
            "mean_absolute_error": float(error),
        }
