"""Survey-triage queue: where a floor survey is worth doing first.

Read-only. It ranks buildings; it does not create cadastral records, and it
cannot. The response carries the estimator's own fitness verdict next to the
queue so a reader cannot act on the ranking without also seeing that the
underlying model is not fit to delineate parcels.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query

from app.ml.floor_triage import get_triage_queue

router = APIRouter(prefix="/floor-triage", tags=["ML Evidence"])


@router.get("/queue")
async def triage_queue(
    limit: int = Query(50, ge=1, le=500, description="Max buildings to rank"),
) -> Dict[str, Any]:
    """Buildings ranked by expected value of a floor survey.

    Serves the problem statement's "vertical parcel delineation" requirement at
    the only fidelity the current model supports: deciding where to send a
    surveyor, not deciding where a boundary lies.
    """
    return get_triage_queue(limit=limit)
