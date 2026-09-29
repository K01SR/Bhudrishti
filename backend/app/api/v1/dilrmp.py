"""DILRMP programme facts and self-assessed alignment.

Read-only. No route here grants, requests or implies any programme status; the
payload states the opposite, and the ``not_held`` fields are pinned by test.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.compliance.dilrmp import alignment

router = APIRouter(prefix="/dilrmp")


@router.get("/alignment")
async def dilrmp_alignment():
    """Verified programme facts plus a per-capability alignment statement."""
    return alignment()