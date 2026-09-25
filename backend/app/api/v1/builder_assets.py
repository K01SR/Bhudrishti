"""Builder 3D asset library.

Serves the bundled GLB building templates and accepts custom 3D model uploads
(GLB, glTF, OBJ, STL) so a builder can stage a proposed structure and attach it
to a submission. Uploaded files land on the /app/data volume (persistent) and
are tracked in-memory, matching the demo lifecycle used by builder submissions.
"""
import os
import shutil
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import FileResponse

from app.core.security import require_roles, TokenPayload, RoleEnum

router = APIRouter(prefix="/builder/assets", tags=["builder-assets"])

BUILDER_ONLY = require_roles([RoleEnum.BUILDER, RoleEnum.STATE_ADMIN])

TEMPLATES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "templates"))
UPLOAD_ROOT = "/app/data/model_assets"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

ALLOWED_EXTS = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".obj": "text/plain",
    ".stl": "model/stl",
}

TEMPLATE_META = {
    "TPL-RES-TOWER": ("Residential Tower", "residential", "Slender high-rise with rooftop terrace massing."),
    "TPL-OFF-BLOCK": ("Office Block", "office", "Mid-rise office slab with a recessed crown."),
    "TPL-MALL": ("Commercial Mall", "commercial", "Low, wide retail podium with lighter roof level."),
    "TPL-TWIN": ("Twin Towers", "residential", "Two linked towers sharing a podium."),
    "TPL-VILLA": ("Villa / Row House", "residential", "Low-rise pitched-mass villa footprint."),
}

_ASSETS = []


def template_files():
    out = []
    try:
        for fn in sorted(os.listdir(TEMPLATES_DIR)):
            if not fn.endswith(".glb"):
                continue
            full = os.path.join(TEMPLATES_DIR, fn)
            tpl_id = fn[:-4]
            name, kind, desc = TEMPLATE_META.get(tpl_id, (tpl_id, "generic", "Bundled template."))
            out.append({
                "id": tpl_id,
                "name": name,
                "kind": kind,
                "description": desc,
                "format": "model/gltf-binary",
                "file_name": fn,
                "size_bytes": os.path.getsize(full),
                "url": f"/api/v1/assets/templates/{fn}",
            })
    except FileNotFoundError:
        pass
    return out


@router.get("/templates")
def list_templates():
    """Lists the bundled GLB building templates a builder can pick from."""
    return template_files()


@router.get("/")
def list_uploaded():
    """Lists assets uploaded by builders in this process lifetime."""
    return list(_ASSETS)


def _validate_head(ext: str, head: bytes) -> str:
    """Lightweight magic checks per upload format."""
    if ext == ".glb":
        if not head.startswith(b"glTF"):
            return "File is not a valid glTF binary (missing glTF magic header)."
    elif ext == ".gltf":
        stripped = head.lstrip(b" \t\r\n")
        if not stripped.startswith(b"{"):
            return "File is not a valid glTF JSON (must start with '{')."
    elif ext in (".obj", ".stl"):
        if b"\x00" in head or not head.strip():
            return "File is not valid ASCII mesh data."
    return ""


@router.post("/upload")
async def upload_model(file: UploadFile = File(...), _auth: TokenPayload = Depends(BUILDER_ONLY)):
    """Accepts a GLB, glTF, OBJ or STL model and stores it under /app/data/model_assets."""
    if not file.filename:
        raise HTTPException(status_code=422, detail="Filename required.")
    ext = os.path.splitext(os.path.basename(file.filename))[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=422,
            detail=f"Only {', '.join(sorted(ALLOWED_EXTS))} files are accepted.",
        )

    head = await file.read(4)
    await file.seek(0)
    err = _validate_head(ext, head)
    if err:
        raise HTTPException(status_code=422, detail=err)

    asset_id = "AST-" + uuid.uuid4().hex[:12].upper()
    target_dir = os.path.join(UPLOAD_ROOT, asset_id)
    os.makedirs(target_dir, exist_ok=True)
    model_name = f"model{ext}"
    target = os.path.join(target_dir, model_name)

    size = 0
    with open(target, "wb") as out:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                shutil.rmtree(target_dir, ignore_errors=True)
                raise HTTPException(status_code=413, detail="Model exceeds the 20 MB upload limit.")
            out.write(chunk)

    asset = {
        "id": asset_id,
        "original_name": os.path.basename(file.filename),
        "name": os.path.splitext(os.path.basename(file.filename))[0],
        "format": ALLOWED_EXTS[ext],
        "size_bytes": size,
        "status": "UPLOADED",
        "uploaded_on": "2026-09-25",
        "url": f"/api/v1/assets/{asset_id}/model{ext}",
    }
    _ASSETS.insert(0, asset)
    return asset


@router.get("/{asset_id}")
def get_asset(asset_id: str):
    asset = next((a for a in _ASSETS if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return asset


files_router = APIRouter(prefix="/assets", tags=["assets-files"])


@files_router.get("/templates/{file_name}")
def serve_template(file_name: str):
    if not file_name.endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only .glb template files can be served.")
    path = os.path.join(TEMPLATES_DIR, os.path.basename(file_name))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Template not found.")
    return FileResponse(path, media_type="model/gltf-binary")


@files_router.get("/{asset_id}/model{ext}")
def serve_asset_model(asset_id: str, ext: str):
    asset = next((a for a in _ASSETS if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found (uploaded assets live for the process lifetime).")
    full_ext = ext.lower() if ext.startswith(".") else f".{ext}"
    if full_ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported model extension.")
    path = os.path.join(UPLOAD_ROOT, asset_id, f"model{full_ext}")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Model file missing.")
    return FileResponse(path, media_type=ALLOWED_EXTS[full_ext])