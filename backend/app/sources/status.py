"""What each configured source can actually answer, and what it cannot.

The provider chain in :mod:`app.sources.registry` says which sources are live.
It does not say what any of them are evidence *of*, and that gap is where an
overclaim hides: a reachable endpoint returning footprints is easy to present
as a cadastral record, because the payload does not contradict itself.

So this module states, per source, the capabilities it can serve and the ones
it cannot, and derives availability from the live provider instances rather than
from a hand-maintained list. A capability is only ``available`` when a provider
in this deployment can actually serve it now.

Two distinctions are load-bearing and are encoded rather than left to prose:

* **Cadastral** means parcel boundaries and the legal facts attached to them:
  title, ownership, area, use rights. A building footprint is not cadastre, and
  no source in this project supplies one.
* **Authoritative** means an official publication *of the thing itself*. Bhuvan
  publishing building footprints is authoritative for footprints; it does not
  thereby become authoritative for who owns the parcel they sit on.

Capability names are deliberately specific. ``building_footprints`` is available
today. ``property_title_ownership`` is not, and no configured source can make it
so. Both facts belong in the same response, so a consumer cannot read the first
without the second.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.pipelines import lgd_villages


@dataclass(frozen=True)
class SourceSpec:
    """Static description of a provider; live state is read at call time."""

    id: str
    label: str
    publisher: str
    kind: str
    license: str
    reference_url: str
    #: Env vars that must all be present for this provider to be usable.
    required_env: tuple = ()
    #: Capabilities this provider can serve when configured.
    provides: tuple = ()
    #: What it structurally cannot serve, whatever the credentials.
    cannot_provide: tuple = ()
    #: True only for an official publication of the capability itself.
    authoritative_for: tuple = ()


@dataclass(frozen=True)
class Capability:
    """One answerable question, and this deployment's real answer to it."""

    key: str
    label: str
    question: str
    available: bool
    basis: str
    source_id: Optional[str] = None
    authoritative: bool = False


@dataclass
class SourceStatus:
    spec: SourceSpec
    configured: bool
    missing_env: List[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.spec.id,
            "label": self.spec.label,
            "publisher": self.spec.publisher,
            "kind": self.spec.kind,
            "license": self.spec.license,
            "reference_url": self.spec.reference_url,
            "configured": self.configured,
            # Names only. A status endpoint is the wrong place to echo the
            # values, and echoing them would put live credentials in a GET.
            "missing_configuration": self.missing_env,
            "provides": list(self.spec.provides),
            "cannot_provide": list(self.spec.cannot_provide),
            "authoritative_for": list(self.spec.authoritative_for),
            "detail": self.detail,
        }


# Footprint geometry with no height, floor count or legal attribute attached:
# satellite or cadastral-vector detection is a statement about a roof.
_FOOTPRINT_NOT_CADASTRAL = (
    "building footprints only; no parcel boundary, title, ownership or area record"
)

_SOURCES: tuple = (
    SourceSpec(
        id="lgd",
        label="Local Government Directory (LGD)",
        publisher="Government of India, Ministry of Panchayati Raj",
        kind="government",
        license="Official publication of the Government of India; terms of use apply",
        reference_url="https://lgdirectory.gov.in/",
        provides=("village_admin_boundaries",),
        cannot_provide=(
            "parcel or survey boundaries: the directory publishes codes and "
            "hierarchy for revenue villages and carries no geometry",
            "title, ownership or area",
        ),
        authoritative_for=("village_admin_boundaries",),
    ),
    SourceSpec(
        id="bhuvan",
        label="Bhuvan vector layer (WFS)",
        publisher="NRSC / ISRO, Department of Space",
        kind="government",
        license="Bhuvan (NRSC/ISRO) — terms of use apply",
        reference_url="https://bhuvan.nrsc.gov.in/",
        required_env=("BHUVAN_WFS_URL", "BHUVAN_WFS_LAYER"),
        provides=("building_footprints",),
        cannot_provide=(
            _FOOTPRINT_NOT_CADASTRAL,
            "building height or floor count unless the configured layer carries it",
        ),
        authoritative_for=("building_footprints",),
    ),
    SourceSpec(
        id="data.gov.in",
        label="data.gov.in open data resource",
        publisher="Government of India (portal); dataset authors vary",
        kind="government_portal",
        license="Open Government Data Licence (OGDL), India",
        reference_url="https://www.data.gov.in/",
        required_env=("OGD_API_KEY", "OGD_RESOURCE_ID"),
        provides=(),
        cannot_provide=(
            "anything, until a specific resource id is configured: the portal is "
            "a catalogue of contributed datasets, not a cadastral service",
            "a guarantee that a listed dataset is current or officially endorsed",
        ),
        # Deliberately empty. A government portal hosting a dataset does not
        # make the dataset authoritative, and the portal is not itself a
        # registry of property. Nothing here may be marked authoritative on the
        # strength of the .gov.in domain.
        authoritative_for=(),
    ),
    SourceSpec(
        id="globalml",
        label="Microsoft GlobalML building footprints",
        publisher="Microsoft (Bing Maps ML detection from satellite imagery)",
        kind="derived",
        license="CDLA Permissive 2.0",
        reference_url="https://github.com/microsoft/GlobalMLBuildingFootprints",
        provides=("building_footprints",),
        cannot_provide=(
            _FOOTPRINT_NOT_CADASTRAL,
            "building height, floor count or usage class: detection is 2D roof "
            "outlines from imagery",
            "named places",
        ),
        authoritative_for=(),
    ),
    SourceSpec(
        id="openstreetmap",
        label="OpenStreetMap (Overpass)",
        publisher="OpenStreetMap community",
        kind="community",
        license="ODbL 1.0, (c) OpenStreetMap contributors",
        reference_url="https://www.openstreetmap.org/",
        provides=("building_footprints", "place_names"),
        cannot_provide=(
            _FOOTPRINT_NOT_CADASTRAL,
            "legal or cadastral status: ODbL data is community-contributed and "
            "carries no authority over property records",
        ),
        authoritative_for=(),
    ),
)


def _source_states() -> Dict[str, SourceStatus]:
    """Read live configuration for every spec, without echoing any secret."""
    from app.sources.registry import _PROVIDERS

    states: Dict[str, SourceStatus] = {}

    for spec in _SOURCES:
        missing = [name for name in spec.required_env if not os.getenv(name, "").strip()]

        if spec.id == "lgd":
            available = lgd_villages.is_available()
            meta = lgd_villages.manifest() if available else {}
            detail = (
                f"{lgd_villages.count_villages()} villages, retrieved "
                f"{meta.get('retrieved_utc')}"
                if available
                else "LGD sqlite build absent"
            )
            states[spec.id] = SourceStatus(spec, available, missing, detail)
            continue

        provider_cls = _PROVIDERS.get(spec.id)
        if provider_cls is None:
            # A spec with no provider is a description of nothing.
            states[spec.id] = SourceStatus(
                spec, False, list(spec.required_env), "no provider implements this source"
            )
            continue

        provider = provider_cls()
        configured = bool(provider.is_configured)
        if configured:
            detail = "configured and in the provider chain"
        elif missing:
            # Name the variables, never their values.
            detail = f"dormant: set {', '.join(missing)}"
        else:
            detail = "dormant: provider reports itself unconfigured"
        states[spec.id] = SourceStatus(spec, configured, missing, detail)

    return states


def _capability(
    key: str,
    label: str,
    question: str,
    states: Dict[str, SourceStatus],
    candidates: tuple,
    unavailable_basis: str,
) -> Capability:
    """First configured candidate that provides ``key`` wins the capability."""
    for source_id in candidates:
        status = states.get(source_id)
        if status and status.configured and key in status.spec.provides:
            return Capability(
                key=key,
                label=label,
                question=question,
                available=True,
                basis=f"{status.spec.label} is configured",
                source_id=source_id,
                authoritative=key in status.spec.authoritative_for,
            )
    return Capability(
        key=key,
        label=label,
        question=question,
        available=False,
        basis=unavailable_basis,
    )


# Capabilities in display order. The unavailable legal ones are interleaved with
# the available ones rather than grouped at the end, so a consumer reading top
# to bottom sees the real picture instead of an available-list and a footnote.
_CAPABILITY_SPECS: tuple = (
    (
        "building_footprints",
        "Building footprints",
        "Can the platform show a real building outline for an area?",
        ("bhuvan", "globalml", "openstreetmap"),
        "no footprint provider is configured",
    ),
    (
        "building_height",
        "Building height / floors",
        "Is a height or floor count measured rather than assumed?",
        (),
        "no configured source publishes height; GlobalML is 2D roof outlines "
        "and the demo heights are generated",
    ),
    (
        "place_names",
        "Named places",
        "Can an area be searched by place name?",
        ("openstreetmap",),
        "no named-place provider is configured",
    ),
    (
        "village_admin_boundaries",
        "Village administrative boundaries",
        "Can official revenue-village codes and hierarchy be served?",
        ("lgd",),
        "the LGD build is absent",
    ),
    (
        "cadastral_parcel_boundaries",
        "Cadastral parcel boundaries",
        "Can surveyed parcel boundaries be served from an official source?",
        (),
        "no cadastral or survey boundary source is connected; parcels in this "
        "deployment come from the generated demo dataset",
    ),
    (
        "property_title_ownership",
        "Property title and ownership",
        "Can who owns a property be answered from an official record?",
        (),
        "no title or ownership source is connected; this is not available in "
        "India from any open dataset, by law of the registration acts",
    ),
    (
        "building_approvals",
        "Building approvals and permits",
        "Can a sanctioned building plan be served?",
        (),
        "approvals are held by local authorities and are not published as an "
        "open dataset",
    ),
    (
        "zoning_regulations",
        "Zoning / FSI regulations",
        "Can applicable zoning and floor-area rules be served per parcel?",
        (),
        "zoning is published as notifications and local bye-laws, not as "
        "machine-readable per-parcel data",
    ),
    (
        "enforcement_violations",
        "Enforcement actions and violations",
        "Can recorded violations be served?",
        (),
        "enforcement is a local authority function; no open dataset records it",
    ),
    (
        "point_cloud_lidar",
        "Airborne LiDAR point clouds",
        "Can real airborne LiDAR be served for an area?",
        (),
        "no open Indian airborne LiDAR distribution exists; the shipped "
        "point-cloud file is a deterministic synthetic demo capture",
    ),
)


def build_status() -> Dict[str, Any]:
    """The full source picture: per-source config, and per-question answers."""
    states = _source_states()
    capabilities = [
        _capability(key, label, question, states, candidates, basis)
        for key, label, question, candidates, basis in _CAPABILITY_SPECS
    ]

    available = [c.key for c in capabilities if c.available]
    unavailable = [c.key for c in capabilities if not c.available]

    return {
        "sources": [states[s.id].as_dict() for s in _SOURCES],
        "capabilities": [
            {
                "key": c.key,
                "label": c.label,
                "question": c.question,
                "available": c.available,
                "basis": c.basis,
                "source_id": c.source_id,
                "authoritative": c.authoritative,
            }
            for c in capabilities
        ],
        "summary": {
            "configured_sources": sorted(s.spec.id for s in states.values() if s.configured),
            "available_capabilities": available,
            "unavailable_capabilities": unavailable,
            # Stated as a null with a reason, not omitted. A consumer checking
            # this key must be forced to notice that nothing fills it.
            "authoritative_cadastral_source": None,
            "authoritative_cadastral_note": (
                "No connected source publishes cadastral boundaries, title or "
                "ownership. data.gov.in is a catalogue of contributed datasets, "
                "so a government-hosted resource is not by itself authoritative "
                "for property records. Anything cadastre-related in this "
                "deployment is generated demo data and is labelled as such."
            ),
            "generated_data_policy": (
                "Generated demo data is never presented as a source result. "
                "Gates refuse to serve it when ENABLE_DEMO_MODE=0."
            ),
        },
    }