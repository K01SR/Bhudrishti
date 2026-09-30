#!/usr/bin/env python3
"""Generates small glTF 2.0 (GLB) building templates for the builder portal.

Pure-python, dependency-free: boxes are composed into stylised volumes, packed
into a single binary buffer and embedded as a base64 data-URI inside a GLB.
Run: python scripts/gen_templates.py  (idempotent, overwrites in-place).
"""
import base64
import json
import math
import os
import struct

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "templates")

# face index -> the 4 corners of each face (positions) and the face normal
# corner order for a box spanning (x0,y0,z0)-(x1,y1,z1)
def box_geometry(x0, y0, z0, x1, y1, z1):
    corners = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    faces = [
        ((0, 1, 2, 3), (0, 0, -1)),   # front (z0)
        ((5, 4, 7, 6), (0, 0, 1)),    # back (z1)
        ((4, 0, 3, 7), (-1, 0, 0)),   # left (x0)
        ((1, 5, 6, 2), (1, 0, 0)),    # right (x1)
        ((3, 2, 6, 7), (0, 1, 0)),    # top (y1)
        ((4, 5, 1, 0), (0, -1, 0)),   # bottom (y0)
    ]
    verts = []
    norms = []
    idx = []
    base = 0
    for quad, n in faces:
        for ci in quad:
            verts.extend(corners[ci])
            norms.extend(n)
        idx.extend([base, base + 1, base + 2, base, base + 2, base + 3])
        base += 4
    return verts, norms, idx


def compose(parts):
    """parts: list of (x0,y0,z0,x1,y1,z1) boxes → (positions, normals, indices)."""
    positions, normals, indices = [], [], []
    for box in parts:
        p, n, i = box_geometry(*box)
        shift = len(positions) // 3
        positions.extend(p)
        normals.extend(n)
        indices.extend([x + shift for x in i])
    return positions, normals, indices


def scale_center(parts, target_width=22.0, target_depth=22.0):
    xs = [c for box in parts for c in (box[0], box[3])]
    zs = [c for box in parts for c in (box[2], box[5])]
    x0, x1 = min(xs), max(xs)
    z0, z1 = min(zs), max(zs)
    w = max(x1 - x0, 1e-6)
    d = max(z1 - z0, 1e-6)
    s = min(target_width / w, target_depth / d) / 1.0
    cx = (x0 + x1) / 2.0
    cz = (z0 + z1) / 2.0
    scaled = [( (x - cx) * s, y * s, (z - cz) * s, (x2 - cx) * s, y2 * s, (z2 - cz) * s) for (x, y, z, x2, y2, z2) in parts]
    return scaled


TEMPLATES = [
    {
        "id": "TPL-RES-TOWER",
        "name": "Residential Tower",
        "kind": "residential",
        "description": "Slender high-rise with rooftop terrace massing.",
        "parts": [
            (0, 0, 0, 20, 6, 20),
            (2, 6, 2, 18, 12, 18),
            (4, 12, 4, 16, 18, 16),
        ],
    },
    {
        "id": "TPL-OFF-BLOCK",
        "name": "Office Block",
        "kind": "office",
        "description": "Mid-rise office slab with a recessed crown.",
        "parts": [
            (0, 0, 0, 26, 8, 18),
            (3, 8, 3, 23, 14, 15),
        ],
    },
    {
        "id": "TPL-MALL",
        "name": "Commercial Mall",
        "kind": "commercial",
        "description": "Low, wide retail podium with lighter roof level.",
        "parts": [
            (0, 0, 0, 32, 5, 26),
            (4, 5, 4, 28, 8, 22),
        ],
    },
    {
        "id": "TPL-TWIN",
        "name": "Twin Towers",
        "kind": "residential",
        "description": "Two linked towers sharing a podium.",
        "parts": [
            (0, 0, 0, 30, 5, 16),
            (1, 5, 1, 12, 16, 15),
            (18, 5, 1, 29, 16, 15),
        ],
    },
    {
        "id": "TPL-VILLA",
        "name": "Villa / Row House",
        "kind": "residential",
        "description": "Low-rise pitched-mass villa footprint.",
        "parts": [
            (0, 0, 0, 18, 4, 14),
            (2, 4, 2, 16, 6, 12),
            (6, 6, 6, 12, 9, 8),
        ],
    },
]


def build_glb(positions, normals, indices, name, color):
    pos = struct.pack(f"{len(positions)}f", *positions)
    nor = struct.pack(f"{len(normals)}f", *normals)
    ind = struct.pack(f"{len(indices)}I", *indices)
    blob = pos + nor + ind

    nv = len(positions) // 3
    pos_view = {"buffer": 0, "byteOffset": 0, "byteLength": len(pos), "target": 34962}
    nor_view = {"buffer": 0, "byteOffset": len(pos), "byteLength": len(nor), "target": 34962}
    ind_view = {"buffer": 0, "byteOffset": len(pos) + len(nor), "byteLength": len(ind), "target": 34963}

    minp = [min(positions[i::3]) for i in range(3)]
    maxp = [max(positions[i::3]) for i in range(3)]

    gltf = {
        "asset": {"version": "2.0", "generator": "bhu-drishti-template-gen"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [
            {
                "name": name,
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": color,
                    "metallicFactor": 0.05,
                    "roughnessFactor": 0.9,
                },
            }
        ],
        "buffers": [
            {
                "byteLength": len(blob),
                "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode(),
            }
        ],
        "bufferViews": [pos_view, nor_view, ind_view],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": nv, "type": "VEC3", "min": minp, "max": maxp},
            {"bufferView": 1, "componentType": 5126, "count": nv, "type": "VEC3", "min": [-1, -1, -1], "max": [1, 1, 1]},
            {"bufferView": 2, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ],
    }

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode()
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(blob) + ((4 - len(blob) % 4) % 4)
    header = b"glTF" + struct.pack("<II", 2, total)
    jchunk = struct.pack("<I", len(json_bytes)) + b"JSON" + json_bytes
    blob_pad = blob + b"\x00" * ((4 - len(blob) % 4) % 4)
    bchunk = struct.pack("<I", len(blob_pad)) + b"BIN\x00" + blob_pad
    return header + jchunk + bchunk


COLORS = {
    "residential": [0.83, 0.69, 0.88, 1.0],
    "office": [0.55, 0.69, 0.9, 1.0],
    "commercial": [0.94, 0.75, 0.45, 1.0],
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for t in TEMPLATES:
        positions, normals, indices = compose(scale_center(t["parts"]))
        glb = build_glb(positions, normals, indices, t["name"], COLORS.get(t["kind"], [0.7, 0.7, 0.7, 1.0]))
        fn = os.path.join(OUT_DIR, f"{t['id']}.glb")
        with open(fn, "wb") as f:
            f.write(glb)
        print(f"wrote {fn} ({len(glb)} bytes)")

    blob = open(os.path.join(OUT_DIR, f"{TEMPLATES[0]['id']}.glb"), "rb").read()
    assert blob[:4] == b"glTF", "bad magic"
    assert struct.unpack("<I", blob[4:8])[0] == 2, "bad version"
    print("Generated", len(TEMPLATES), "templates. OK.")


if __name__ == "__main__":
    main()