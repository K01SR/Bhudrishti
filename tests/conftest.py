import os
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

# Most suites exercise the generated Airoli showcase. Open the demo gate before
# app.core.demo_gate-backed modules are imported, since several cache the dataset
# at module scope. Production keeps this shut; see app/core/demo_gate.py.
os.environ.setdefault("ENABLE_DEMO_MODE", "1")

from app.main import app  # noqa: E402  (must follow the gate above)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def anon_client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, username: str, password: str = "demo@2026") -> Dict[str, Any]:
    res = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def authed_builder(client: TestClient):
    """TestClient authenticated as builder.demo (BUILDER)."""
    data = _login(client, "builder.demo")
    client.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return client


@pytest.fixture()
def authed_verify(client: TestClient):
    """TestClient authenticated as district.admin (DISTRICT_VERIFIER / STATE admin)."""
    data = _login(client, "district.admin")
    client.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return client


@pytest.fixture()
def authed_state(client: TestClient):
    """TestClient authenticated as state.admin (STATE_ADMIN)."""
    data = _login(client, "state.admin")
    client.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return client


@pytest.fixture()
def builder_token(client: TestClient) -> str:
    return _login(client, "builder.demo")["access_token"]


@pytest.fixture()
def verifier_token(client: TestClient) -> str:
    return _login(client, "district.admin")["access_token"]


@pytest.fixture()
def state_token(client: TestClient) -> str:
    return _login(client, "state.admin")["access_token"]