"""Credentials a deployment reads must actually reach the processes that use them.

An ``OGD_API_KEY`` sat in ``.env`` for some time while ``docker-compose.yml``
passed no ``OGD_*`` variable into either the backend or the worker container.
The key was therefore dead configuration: written to disk, never delivered to
the process, and invisible to ``app.sources.ogd``, which could consequently only
ever raise ``NoAuthenticSourceError`` regardless of what an operator configured.
The ``/api/v1/datasources/status`` endpoint reported ``data.gov.in`` as
unconfigured throughout, which is what finally surfaced it.

Nothing about the status endpoint was wrong. The defect was that a credential
an operator believed they had configured was silently discarded. These tests
bind every provider credential the code reads to the compose service that runs
it, so the same class of gap fails loudly.

Scope note: this checks wiring, not validity. No key here is verified to work,
and setting one does not enable the provider -- ``OGD_RESOURCE_ID`` is required
too, and no catalog resource has been verified as authoritative.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.yml").read_text()
ENV_EXAMPLE = (ROOT / ".env.example").read_text()


def _service_block(name: str) -> str:
    """Slice one service out of the compose file.

    Indentation-delimited rather than parsed with a YAML library: PyYAML is not
    a backend dependency, and the anchor is structural (two-space service keys
    under ``services:``) and stable.
    """
    lines = COMPOSE.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line == f"  {name}:":
            start = i
            break
    assert start is not None, f"service {name!r} not found in docker-compose.yml"
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("  ") and not lines[j].startswith("   ") and lines[j].strip():
            return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


@pytest.mark.parametrize("service", ["backend", "worker"])
def test_ogd_credentials_reach_every_service_that_ingests(service):
    block = _service_block(service)
    for var in ("OGD_API_KEY", "OGD_RESOURCE_ID", "OGD_BASE_URL"):
        assert var in block, (
            f"{service} does not receive {var}. A credential in .env that never "
            f"reaches the process is dead configuration: the provider can then "
            f"never authenticate and will report itself unconfigured forever."
        )


@pytest.mark.parametrize("service", ["backend", "worker"])
def test_ogd_credentials_default_to_empty_rather_than_a_literal(service):
    """Empty default, so an absent key stays absent instead of becoming a value.

    A literal fallback would be worse than dead configuration: the deployment
    would appear configured and would attempt authenticated calls with a key
    nobody chose, and the resulting 401s would look like a provider outage.
    """
    block = _service_block(service)
    assert "OGD_API_KEY=${OGD_API_KEY:-}" in block, (
        f"{service}: OGD_API_KEY must default to empty, not to a literal"
    )
    assert "OGD_RESOURCE_ID=${OGD_RESOURCE_ID:-}" in block, (
        f"{service}: OGD_RESOURCE_ID must default to empty; a key alone does not "
        f"enable the provider"
    )


def test_env_example_does_not_ship_a_credential():
    """The tracked template must stay safe to publish."""
    for line in ENV_EXAMPLE.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for var in ("OGD_API_KEY", "OGD_RESOURCE_ID", "SECRET_KEY"):
            if stripped.startswith(f"{var}="):
                assert stripped == f"{var}=", (
                    f".env.example assigns a value to {var}; the tracked template "
                    f"must leave it empty so nobody inherits a working credential"
                )


def test_compose_still_refuses_demo_data_by_default():
    """Guard the neighbouring default while this file is being asserted on."""
    assert "ENABLE_DEMO_MODE=${ENABLE_DEMO_MODE:-0}" in COMPOSE, (
        "docker-compose must keep defaulting ENABLE_DEMO_MODE to 0"
    )


def test_status_endpoint_still_requires_a_resource_id():
    """A key without a resource id must not read as configured.

    Guards the reason OGD_RESOURCE_ID is wired alongside the key: satisfying one
    half of the credential must never flip the provider to "available". The
    provider is deliberately marked as providing nothing, since data.gov.in is a
    catalogue of contributed datasets and not a cadastral service.
    """
    from app.sources.status import _SOURCES

    ogd = next(s for s in _SOURCES if s.id == "data.gov.in")
    assert "OGD_API_KEY" in ogd.required_env
    assert "OGD_RESOURCE_ID" in ogd.required_env
    assert ogd.provides == (), (
        "data.gov.in must not be credited with providing anything until a "
        "specific verified resource id is configured"
    )


def test_dev_default_secrets_fail_closed_in_production():
    """The known defaults must refuse to boot rather than run insecurely.

    This is the control that makes the empty SECRET_KEY in .env.example a
    hygiene matter rather than a live vulnerability: config.py raises
    RuntimeError in production mode for any recognised development default, so
    a deployment that copied one fails to start instead of issuing tokens
    anyone could forge from the public repository.
    """
    from app.core.config import Settings

    prod = Settings(ENVIRONMENT="production", SECRET_KEY="bhu_drishti_3d_super_secret_jwt_key_airoli_2026_cadastre")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        prod._validate_prd()