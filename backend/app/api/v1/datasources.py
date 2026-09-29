"""Source configuration and capability status.

Reports what this deployment can actually answer, so the frontend never has to
infer it from a badge. Separate from the provider chain: that decides which
source serves an area, this decides what any of them are evidence of.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.sources.status import build_status

router = APIRouter(prefix="/datasources")


@router.get("/status")
async def datasource_status():
    """Per-source configuration and per-capability availability.

    Secret values are never returned, only the names of missing variables.
    """
    return build_status()