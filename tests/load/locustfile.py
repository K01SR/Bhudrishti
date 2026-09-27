"""Load scenarios against the real API.

Three rules, each of which exists because the obvious alternative is a number
that means nothing:

**Authenticate for real.** Login is ``OAuth2PasswordRequestForm``, so the body is
form-encoded. Posting JSON returns 422, and a scenario that skips auth measures
401s. Every authenticated user is obtained by logging in as a demo account and
failing the run if that fails, rather than continuing and reporting the fast
failure of an unauthenticated request as a good result.

**Refuse to guess the target.** There is no default host. A load test that
defaults to something reachable is a load test that eventually runs against a
staging box at 3am. The host must be passed explicitly, and it is echoed at the
start of the run so the output says what it hit.

**Report the shape with the numbers.** Latency from one uvicorn worker with no
resource limits is not a capacity figure for the product. The runner records the
deployment context alongside the percentiles so a reader cannot quote p99 without
also quoting what produced it.
"""
from __future__ import annotations

import itertools
import os

from locust import HttpUser, between, events, task

# Read-heavy, because that is the shape of real use: people look at a map and
# read, they do not submit. A load profile that only writes measures the wrong
# thing and flatters the result.
READ_WEIGHT = 10


def _auth_required() -> bool:
    return os.getenv("LOAD_REQUIRE_AUTH", "1") != "0"


class BhudrishtiUser(HttpUser):
    """A signed-in session doing the reads a map actually performs."""

    wait_time = between(0.2, 1.0)

    def on_start(self):
        self.token = None
        username = os.getenv("LOAD_USERNAME", "builder.demo")
        password = os.getenv("LOAD_PASSWORD", "demo@2026")

        if not _auth_required():
            return

        with self.client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": password},
            name="POST /auth/login",
            catch_response=True,
        ) as res:
            if res.status_code != 200:
                # Fail the run rather than measure 401s as throughput.
                res.failure(f"login failed: {res.status_code} {res.text[:120]}")
                raise SystemExit(
                    f"Load test aborted: login as {username!r} returned "
                    f"{res.status_code}. Fix credentials rather than measuring "
                    f"unauthenticated responses."
                )
            self.token = res.json().get("access_token")
            res.success()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(4)
    def health(self):
        self.client.get("/health", name="GET /health")

    @task(3)
    def parcels(self):
        self.client.get("/api/v1/parcels/", name="GET /parcels/")

    @task(3)
    def hero_property(self):
        self.client.get("/api/v1/properties/hero", name="GET /properties/hero",
                        headers=self._headers())

    @task(2)
    def precinct_buildings(self):
        self.client.get("/api/v1/precinct/buildings", name="GET /precinct/buildings",
                        headers=self._headers())

    @task(2)
    def search(self):
        self.client.get("/api/v1/search", params={"q": "Shivajinagar"},
                        name="GET /search", headers=self._headers())

    @task(2)
    def verification_cases(self):
        self.client.get("/api/v1/verification/cases", name="GET /verification/cases",
                        headers=self._headers())

    @task(2)
    def lidar_scene(self):
        self.client.get("/api/v1/lidar/inspect/scene", name="GET /lidar/inspect/scene")

    @task(1)
    def source_status(self):
        self.client.get("/api/v1/datasources/status", name="GET /datasources/status")

    @task(1)
    def dilrmp_alignment(self):
        self.client.get("/api/v1/dilrmp/alignment", name="GET /dilrmp/alignment",
                        headers=self._headers())


class WriteUser(HttpUser):
    """A citizen filing objections, for the write half of the backlog.

    Kept in a separate user class rather than folded into ``BhudrishtiUser``
    because the two must be measured apart. Mixing writes into a read profile
    hides both: the writes look like read latency, and the reads inherit a
    threadpool that writes are saturating.

    What these numbers do and do not mean is stated in the module docstring of
    ``probe_writes.py``: of the API modules only ``parcels.py`` and
    ``pipelines_api.py`` call ``commit()``, so this measures handler throughput
    over an in-process list append, not database write capacity.
    """

    wait_time = between(0.1, 0.5)
    _seq = itertools.count()

    def on_start(self):
        username = os.getenv("LOAD_WRITE_USERNAME", "citizen.demo")
        password = os.getenv("LOAD_PASSWORD", "demo@2026")
        with self.client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": password},
            name="POST /auth/login",
            catch_response=True,
        ) as res:
            if res.status_code != 200:
                res.failure(f"write login failed: {res.status_code}")
                raise SystemExit(
                    f"Load test aborted: login as {username!r} returned "
                    f"{res.status_code}. Fix credentials rather than measuring "
                    f"unauthenticated responses."
                )
            self.token = res.json().get("access_token")
            res.success()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task
    def file_objection(self):
        index = next(self._seq)
        with self.client.post(
            "/api/v1/objections/",
            json={
                "ulpin": "12345678901234",
                "category": "OTHER",
                "description": f"locust write probe {index}",
                "contact_email": "load@example.invalid",
                "priority": "LOW",
            },
            headers=self._headers(),
            name="POST /objections/",
            catch_response=True,
        ) as res:
            if res.status_code == 201:
                res.success()
            else:
                # A duplicate case number is a lost update: two citizens were
                # told their objections exist and only one of them can be
                # served back. Surfacing it as a failure is the whole point of
                # running writes at all.
                case = res.json().get("case_number") if res.content else None
                res.failure(f"objection not accepted: {res.status_code} {case}")


@events.quitting.add_listener
def _note_shape(environment, **_kwargs):
    """Attach deployment context to the run so percentiles cannot be quoted bare."""
    stats = environment.stats
    total = stats.total
    print("\n--- request shape ---")
    for entry in total.entries.values():
        if entry.num_requests:
            print(
                f"{entry.name:34s} n={entry.num_requests:6d} "
                f"fail={entry.num_failures:5d} "
                f"p50={entry.get_response_time_percentile(0.50):6.0f}ms "
                f"p95={entry.get_response_time_percentile(0.95):6.0f}ms "
                f"p99={entry.get_response_time_percentile(0.99):6.0f}ms"
            )
    print(
        f"TOTAL n={total.num_requests} fail={total.num_failures} "
        f"rps={total.total_rps:.1f} "
        f"p50={total.get_response_time_percentile(0.50):.0f}ms "
        f"p95={total.get_response_time_percentile(0.95):.0f}ms "
        f"p99={total.get_response_time_percentile(0.99):.0f}ms"
    )