"""Scene Architect: builds the per-property 3D scene specification from the
persisted PostGIS cadastral store. Every coordinate, z-bound, solid and clash
point is DERIVED from the database (parcels, structure, levels, units, run
provenance) rather than hardcoded — the frontend viewer renders purely from
this payload."""

from .scene_architect import build_scene3d

__all__ = ["build_scene3d"]