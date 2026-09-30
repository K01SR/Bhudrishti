"""Gate for generated demonstration data.

The Airoli precinct in :mod:`app.pipelines.synthetic_generator` is invented
geometry: made-up ULPINs, footprints, and a permitted-FSI figure no authority
published. It exists so the project can be demonstrated without waiting for
government data access, and it is never presented as a real record.

It is disabled by default. Nothing synthetic is served, counted, or rendered
unless ``ENABLE_DEMO_MODE`` is explicitly set, which keeps every response
traceable to a real dataset.

Set ``ENABLE_DEMO_MODE=1`` only for a demonstration run, and label the
deployment as demo data when you do.
"""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}

DEMO_DISABLED_MESSAGE = (
    "Demonstration data is disabled. This deployment serves only records "
    "ingested from a real dataset, and none have been ingested yet. "
    "Set ENABLE_DEMO_MODE=1 to load the generated Airoli showcase."
)


class DemoDataDisabled(RuntimeError):
    """Raised when generated data is requested while the demo gate is shut.

    ``note`` carries a fact about the *data* rather than about this deployment,
    so a caller can tell "turn the gate on" apart from "no such dataset is
    published for this place". Without it, every refusal reads like an outage
    that an environment variable would fix.
    """

    def __init__(self, message: str, note: str | None = None) -> None:
        super().__init__(message)
        self.note = note


def demo_mode_enabled() -> bool:
    # Read the environment on each call so tests and CLI runs can toggle the
    # gate without reimporting the modules that cache the dataset.
    return os.getenv("ENABLE_DEMO_MODE", "").strip().lower() in _TRUTHY


def require_demo_mode(feature: str, note: str | None = None) -> None:
    if not demo_mode_enabled():
        raise DemoDataDisabled(f"{feature}: {DEMO_DISABLED_MESSAGE}", note=note)


def demo_mode_dependency() -> None:
    """Router dependency: refuse the whole route group while the gate is shut.

    Used by routers that would otherwise rebuild a plausible-looking record out
    of an empty cache instead of calling the generator.
    """
    if not demo_mode_enabled():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail=DEMO_DISABLED_MESSAGE,
            headers={"X-Demo-Mode": "disabled"},
        )


def load_demo_dataset() -> dict:
    """Import-time safe dataset access for modules that cache at module scope.

    Returns an empty dataset while the gate is shut so the application still
    starts; request handlers that then try to read generated content raise.
    """
    if not demo_mode_enabled():
        dataset = empty_dataset()
        dataset["demo_disabled"] = True
        return dataset

    from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset

    return generate_synthetic_airoli_dataset()


def empty_dataset() -> dict:
    """Structurally valid, empty stand-in used when the demo gate is shut.

    Keeps downstream ``.get`` access safe without inventing any value.
    """
    return {
        "precinct": {},
        "hero_parcel": {},
        "surrounding_parcels": [],
        "extra_parcels": [],
        "parcel_locations": {},
        "hero_structure": {},
        "levels": [],
        "units": [],
        "subsurface_objects": [],
        "elevated_objects": [],
        "epoch2_change": {},
        "architectural_elements": [],
        "synthetic_lidar_points": [],
        "synthetic_lidar_points_classified": [],
        "synthetic_lidar_points_by_ulpin": {},
        "precinct_buildings": [],
        "all_precinct_units": [],
        "precinct_units_by_ulpin": {},
    }
