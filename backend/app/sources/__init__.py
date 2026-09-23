"""Authentic data sources for the platform.

Import from here rather than from provider modules:

    from app.sources import fetch_area, NoAuthenticSourceError
"""
from app.sources.base import AreaData, AreaSource, NoAuthenticSourceError, Provenance
from app.sources.registry import fetch_area, get_providers, provider_order, unconfigured_providers

__all__ = [
    "AreaData",
    "AreaSource",
    "NoAuthenticSourceError",
    "Provenance",
    "fetch_area",
    "get_providers",
    "provider_order",
    "unconfigured_providers",
]
