from typing import Dict, Any, List, Tuple
from shapely.geometry import Polygon, mapping


class VerticalDelineationPipeline:
    """
    Component 3: Vertical Parcel Delineation.
    Converts 2D Unit Footprint Polygon + Vertical Height Interval [Z_min, Z_max]
    into a mathematically valid 3D Cadastral Solid with area, volume, and Three.js 3D mesh.
    """

    def extrude_unit_volume(
        self,
        polygon_coords: List[List[float]],  # [[x1, y1], [x2, y2], ...]
        min_z: float,
        max_z: float,
    ) -> Dict[str, Any]:
        """
        Extrudes 2D polygon between min_z and max_z to form a 3D polyhedral prism.
        Returns footprint area, 3D volume, and Three.js triangular mesh geometry.
        """
        if max_z <= min_z:
            raise ValueError(f"Invalid vertical interval: max_z ({max_z}) must be greater than min_z ({min_z}).")

        poly = Polygon(polygon_coords)
        if not poly.is_valid:
            poly = poly.buffer(0)

        area_m2 = round(float(poly.area), 2)
        height_m = round(max_z - min_z, 2)
        volume_m3 = round(area_m2 * height_m, 2)

        # Generate 3D Mesh (Vertices & Triangles) for Three.js rendering
        # Bottom ring at min_z, top ring at max_z
        ring = list(poly.exterior.coords)[:-1]  # Exclude closing duplicate
        n = len(ring)

        vertices: List[float] = []
        # Add bottom vertices (index 0 to n-1)
        for x, y in ring:
            vertices.extend([float(x), float(y), float(min_z)])
        # Add top vertices (index n to 2n-1)
        for x, y in ring:
            vertices.extend([float(x), float(y), float(max_z)])

        indices: List[int] = []

        # Side quad faces (split into 2 triangles each)
        for i in range(n):
            next_i = (i + 1) % n
            b1 = i
            b2 = next_i
            t1 = i + n
            t2 = next_i + n
            # Triangle 1
            indices.extend([b1, b2, t2])
            # Triangle 2
            indices.extend([b1, t2, t1])

        # Bottom and top face fan triangulation
        for i in range(1, n - 1):
            # Bottom face (clockwise / normal down)
            indices.extend([0, i + 1, i])
            # Top face (counter-clockwise / normal up)
            indices.extend([n, n + i, n + i + 1])

        centroid = poly.centroid
        center_x = float(centroid.x)
        center_y = float(centroid.y)
        center_z = float((min_z + max_z) / 2.0)

        return {
            "min_z": min_z,
            "max_z": max_z,
            "height_m": height_m,
            "carpet_area_m2": round(area_m2 * 0.82, 2),  # Estimated ~82% carpet
            "built_up_area_m2": area_m2,
            "volume_m3": volume_m3,
            "center": [center_x, center_y, center_z],
            "mesh_3d": {
                "vertices": vertices,
                "indices": indices,
                "vertex_count": len(vertices) // 3,
                "triangle_count": len(indices) // 3,
            },
            "footprint_geojson": mapping(poly),
        }
