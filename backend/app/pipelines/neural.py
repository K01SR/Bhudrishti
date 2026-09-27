"""
Neural backend hooks for the ML pipelines.

The platform is deterministic-first: all cadastral extraction works today on
pure geometry/point-cloud algorithms. When a trained model is available it can
be dropped into ``app/pipelines/neural/`` and registered below; the pipeline
automatically prefers it and records ``engine.neural = True`` in provenance.
No GPU or heavy framework is required for the demo path — the hooks degrade to
the deterministic implementation gracefully.

There is no trained model in this repository. Nothing under ``backend/`` has
weights, a checkpoint, a training set or an evaluation result, so nothing here
may report a model as having run. The registry below therefore carries two
kinds of entry and they are kept apart on purpose:

* :class:`TorchBuildingSegmenter` — a hook for a real model. It reports itself
  available only when ``NEURAL_MODEL_PATH`` points at a checkpoint *and* torch
  imports, because until then it has nothing to run.
* :class:`GlobalMLFootprintBackend` — a source adapter. It retrieves footprints
  that Microsoft already published as the GlobalML Building Footprints release.
  Those footprints were detected by the publisher, upstream of us, and the
  upstream method is not distributed with the data. So this backend is a lookup,
  not an inference: it reports the dataset's own provenance for the geometry and
  states plainly that the geometry is not an output of any model in this code.

Both kinds return footprints, so both are registered in ``_BACKENDS``, but
``get_neural_backend()`` only ever hands back the first kind and
``get_footprint_source()`` the second, so a retrieval adapter can never be
reported as a model that ran.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional


class NeuralBackendUnavailable(Exception):
    """Raised when a requested neural component is not installed/configured."""


class NeuralBackend:
    """Base interface. Subclasses may load torch/onnx models lazily."""

    name = "base"
    # A backend is only a *neural* backend if it runs learned parameters.
    # Retrieval adapters set this False and stay out of get_neural_backend().
    is_neural_model = False
    # ...and only a footprint *source* if it can actually return footprints.
    supplies_footprints = False

    def available(self) -> bool:
        return False

    def extract_footprints(
        self, points: Any, ground_z: float = 0.0, **kwargs
    ) -> Optional[Dict[str, Any]]:
        raise NeuralBackendUnavailable(f"Neural backend '{self.name}' not available.")

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name, "available": self.available()}


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except Exception:
        return False


class TorchBuildingSegmenter(NeuralBackend):
    """Optional PyTorch semantic-segmentation footprint extractor (UNet-like).

    Expects a checkpoint at ``NEURAL_MODEL_PATH`` (env var). When absent the
    deterministic LiDAR pipeline remains the active engine. No checkpoint ships
    with this repository, so in a default deployment this reports unavailable.
    """

    name = "torch-unet-footprint"
    is_neural_model = True
    supplies_footprints = True

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or os.environ.get("NEURAL_MODEL_PATH")
        self._model: Any = None

    def available(self) -> bool:
        return bool(self.model_path) and _torch_available()

    def _load(self) -> Any:
        if self._model is None:
            import torch  # pragma: no cover

            self._model = torch.jit.load(self.model_path, map_location="cpu")
        return self._model

    def extract_footprints(self, points: Any, ground_z: float = 0.0, **kwargs):
        if not self.available():
            raise NeuralBackendUnavailable(
                "Torch UNet backend configured but unavailable (set NEURAL_MODEL_PATH or install torch)."
            )
        return None  # pragma: no cover — placeholder for a trained-model deployment


# Height is not published for the GlobalML India partitions (``height`` is -1 in
# the source, see app/sources/globalml.py), so anything that extrudes a volume
# has to assume one. The assumption below is the same deterministic estimator the
# point-cloud sampler already uses (app/opendata/service.py::_generate_for_footprint:
# floor count x 3.0 m, else footprint extent x 0.9 m clamped to 3-60 m) so the two
# surfaces cannot disagree with each other. It is arithmetic on the outline we
# already have — not a measurement, not a photo interpretation, not a survey — so
# every number it produces leaves this module tagged "derived" with this basis
# attached.
MODELLED_FLOOR_HEIGHT_M = 3.0
MODELLED_EXTENT_TO_HEIGHT = 0.9
MODELLED_MIN_HEIGHT_M = 3.0
MODELLED_MAX_HEIGHT_M = 60.0
MODELLED_HEIGHT_BASIS = (
    "derived: floor count x 3.0 m where the source publishes a floor count, else "
    "footprint extent x 0.9 m clamped to 3-60 m; arithmetic on the published "
    "outline, not a measured height"
)


def _derive_height_m(building: Dict[str, Any]) -> Optional[float]:
    """Estimate a height for a footprint that has none. Never a measurement."""
    floors = building.get("floors")
    if isinstance(floors, (int, float)) and not isinstance(floors, bool) and floors > 0:
        return round(float(floors) * MODELLED_FLOOR_HEIGHT_M, 2)

    ring = building.get("ring_geo") or []
    if len(ring) < 2:
        return None
    lons = [float(p[0]) for p in ring]
    lats = [float(p[1]) for p in ring]
    lat_ref = sum(lats) / len(lats)
    # Same equirectangular constants as app.sources.base.ring_area_m2, so the
    # extent measured here matches the area the source reports for this ring.
    kx = 111320.0 * math.cos(math.radians(lat_ref))
    extent_m = max((max(lons) - min(lons)) * kx, (max(lats) - min(lats)) * 110540.0, 1.0)
    height = max(MODELLED_MIN_HEIGHT_M, min(MODELLED_MAX_HEIGHT_M, extent_m * MODELLED_EXTENT_TO_HEIGHT))
    return round(height, 2)


class GlobalMLFootprintBackend(NeuralBackend):
    """Real building footprints retrieved from the published GlobalML release.

    What this is: an adapter over :func:`app.sources.registry.fetch_area`, so a
    caller that asks the backend registry for footprints gets genuine published
    geometry with the dataset's own provenance (provider, dataset, licence, tile
    URL, ``authoritative=False``) attached, instead of generated geometry.

    What this is not: a model. It loads no weights, runs no inference and
    compares no imagery, so it cannot and does not report a detection quality,
    an accuracy figure or a confidence score — nothing in this repository would
    support one. Microsoft produced the footprints with its own published method
    upstream of us; that method, its training data and its quality figures are
    not distributed with the footprints, so this backend treats the upstream
    model as an unattributed property of the dataset rather than as an engine it
    operates. The upstream production is recorded as a dataset attribute, kept
    clearly apart from the method provenance below, so the two cannot be read as
    a single claim about this system.

    Heights and floor counts: the India partitions publish neither (``height`` is
    -1, ``floors`` is absent). Where the source supplies a height it is passed
    through tagged ``height_basis="source"``. Where it does not, one is derived
    by :func:`_derive_height_m` and tagged ``"derived"`` with
    :data:`MODELLED_HEIGHT_BASIS` as its stated basis. The backend never returns
    an estimate without that tag, because an untagged height on a 3D scene reads
    as surveyed.

    Unavailability and outages are separate: if GlobalML is not in the configured
    ``OPENDATA_SOURCES`` chain this reports unavailable, and if the chain is
    configured but nothing answers, the :class:`NoAuthenticSourceError` from the
    source layer propagates. Neither path substitutes generated geometry.
    """

    name = "globalml-published-footprints"
    is_neural_model = False
    supplies_footprints = True

    def _chain(self) -> List[str]:
        try:
            from app.sources.registry import provider_order

            return provider_order()
        except Exception:  # noqa: BLE001 - a malformed chain is unavailable, not fatal
            return []

    def available(self) -> bool:
        return "globalml" in self._chain()

    def extract_footprints(
        self,
        points: Any = None,
        ground_z: float = 0.0,
        *,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_m: int = 500,
        max_buildings: int = 220,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Fetch published footprints for a coordinate.

        ``points`` accepts a ``(lat, lon)`` pair so the base-class call signature
        still works; ``lat=``/``lon=`` are the explicit form.
        """
        if not self.available():
            raise NeuralBackendUnavailable(
                "GlobalML is not in the configured OPENDATA_SOURCES chain "
                "(currently: " + (", ".join(self._chain()) or "none") + ")."
            )

        if lat is None or lon is None:
            if isinstance(points, (tuple, list)) and len(points) >= 2:
                lat, lon = float(points[0]), float(points[1])
        if lat is None or lon is None:
            raise NeuralBackendUnavailable(
                f"Backend '{self.name}' needs a coordinate: pass points=(lat, lon) or lat=/lon=."
            )

        from app.sources.registry import fetch_area

        area = fetch_area(lat, lon, int(radius_m), max_buildings=int(max_buildings))

        footprints: List[Dict[str, Any]] = []
        derived_count = 0
        source_count = 0
        for b in area.buildings:
            height_m = b.get("height_m")
            published_basis = str(b.get("height_basis") or "")
            if isinstance(height_m, (int, float)) and height_m > 0 and published_basis != "modelled":
                basis, basis_detail = "source", f"published by {area.provenance.provider}"
                source_count += 1
            else:
                height_m = _derive_height_m(b)
                basis, basis_detail = "derived", MODELLED_HEIGHT_BASIS
                derived_count += 1
            floors = None
            if height_m is not None:
                floors = max(1, int(round(float(height_m) / MODELLED_FLOOR_HEIGHT_M)))
            footprints.append(
                {
                    "id": b.get("id"),
                    "name": b.get("name"),
                    "type": b.get("type"),
                    "height_m": height_m,
                    "floors": floors,
                    "floors_basis": basis,
                    "height_basis": basis,
                    "height_basis_detail": basis_detail,
                    "footprint_area_m2": b.get("footprint_area_m2"),
                    "ring_geo": b.get("ring_geo"),
                    "center_geo": b.get("center_geo"),
                    "footprint_provenance": area.provenance.as_dict(),
                }
            )

        return {
            "engine": self.name,
            "method": "retrieval_of_published_footprint_dataset",
            "footprints_count": len(footprints),
            "footprints": footprints,
            # Provenance of the geometry: the dataset's, and only the dataset's.
            "provenance": area.provenance.as_dict(),
            "label_provenance": area.label_provenance,
            "warnings": list(area.warnings),
            # Provenance of the method, reported separately from the data so the
            # two are never merged into one claim.
            "model": {
                "trained_here": False,
                "weights_loaded": False,
                "inference_performed": False,
                "artifact_path": None,
                "authority": "NONE",
                "note": (
                    "Footprints come from Microsoft's published GlobalML Building "
                    "Footprints release. This repository trains no model, loads no "
                    "weights and runs no inference: it retrieves the dataset. The "
                    "publisher's upstream detection method, its training data and "
                    "its quality figures do not ship with the footprints, so no "
                    "figure here describes our own output, and none describes the "
                    "quality of the upstream one either."
                ),
            },
            "upstream_dataset_note": (
                "The publisher states the footprints were machine-detected from "
                "satellite imagery. That is a property of the published dataset, "
                "not an engine this platform operates or has measured."
            ),
            "height_basis": {
                "source": source_count,
                "derived": derived_count,
                "derived_basis": MODELLED_HEIGHT_BASIS,
                "note": (
                    "The GlobalML India partitions publish no height and no floor "
                    "count, so a derived value is not a defect of this adapter."
                ),
            },
        }

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available(),
            "kind": "source-adapter",
            "is_neural_model": self.is_neural_model,
            "trained_here": False,
            "weights": None,
            "inference_performed": False,
            "authority": "NOT_AUTHORITATIVE",
            "produces": "building footprints retrieved from the published GlobalML release",
            "does_not_produce": [
                "learned parameters of any kind",
                "heights or floor counts read off imagery",
                "ownership, title or party information",
                "any measure of how good the footprints are",
            ],
            "configured_sources": self._chain(),
            "height_estimator": MODELLED_HEIGHT_BASIS,
        }


_BACKENDS: List[NeuralBackend] = [TorchBuildingSegmenter(), GlobalMLFootprintBackend()]


def get_neural_backend(name: Optional[str] = None) -> Optional[NeuralBackend]:
    """Returns the first available registered neural backend (or None).

    Only backends that run learned parameters qualify. A retrieval adapter such
    as :class:`GlobalMLFootprintBackend` is registered too, so it can be selected
    and described, but handing one back from here would report a model that
    never ran; :func:`get_footprint_source` is its accessor instead.
    """
    for b in _BACKENDS:
        if b.is_neural_model and b.available() and (name is None or b.name == name):
            return b
    return None


def get_footprint_source(name: Optional[str] = None) -> Optional[NeuralBackend]:
    """First available backend that can actually supply footprints, model or not."""
    for b in _BACKENDS:
        if b.supplies_footprints and b.available() and (name is None or b.name == name):
            return b
    return None


def describe_backends() -> List[Dict[str, Any]]:
    return [b.describe() for b in _BACKENDS]


def get_active_engine() -> Dict[str, Any]:
    """Reports which engine is active for each neural-capable stage."""
    neural = get_neural_backend()
    source = get_footprint_source()
    return {
        "building_extraction": "deterministic-lidar",
        "floor_segmentation": "deterministic-zkd",
        # Named after whichever backend is really serving footprints, so a
        # retrieval adapter is never reported here as a model that ran.
        "footprint_refinement": (
            neural.name if neural else (source.name if source else "deterministic-lidar")
        ),
        "cuda_available": _torch_available(),
        "trained_model_in_repo": False,
        "backends": describe_backends(),
    }