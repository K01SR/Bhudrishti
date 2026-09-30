"""Write-path concurrency probe against a running API.

Every number in ``tests/load/README.md`` until now came from the read path,
because that is the path a map exercises. This probes the writes instead, and
exists because the write path is shaped differently in three ways that a read
benchmark cannot reveal.

**Most user-facing writes never reach Postgres.** Measured 2026-10-04: of the
API modules, only ``parcels.py`` and ``pipelines_api.py`` call ``commit()``, and
``parcels.py`` only via ``POST /ingest-area``, which fetches from
OpenStreetMap. So ``POST /builder/submissions/detailed`` returns
``persistence.persisted: false`` with the reason "the submitter is not a
database account yet". The obvious thing to load-test is therefore not a
database write at all, and a harness that reported "write throughput" from these
endpoints would be reporting the throughput of a list append.

**Those writes are served from worker threads.** The handlers are sync ``def``,
so FastAPI runs them in the threadpool, where they genuinely run concurrently
and are not serialised by the event loop. Any counter-then-append in them is a
lost-update race by construction.

**Nothing rolls back.** A failed write leaves whatever the handler had already
mutated in the module-level dict, and there is no transaction to undo it, so a
partial write survives into the next request.

Usage:
    python3 tests/load/probe_writes.py --host http://127.0.0.1:8000 \\
        --concurrency 40 --rounds 3

Refuses to guess the host, for the reason given in ``locustfile.py``.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

DEFAULT_WRITE_PATH = "/api/v1/objections/"


class Probe:
    def __init__(self, host: str, verify_tls: bool = True):
        self.host = host.rstrip("/")
        self.token: str | None = None
        context = None
        if not verify_tls:
            import ssl

            context = ssl._create_unverified_context()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context)
        )

    def _request(self, method: str, path: str, body=None, form=None, headers=None):
        url = f"{self.host}{path}"
        data = None
        hdrs = dict(headers or {})
        if form is not None:
            data = "&".join(f"{k}={v}" for k, v in form.items()).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        if self.token:
            hdrs["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with self._opener.open(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, None

    def login(self, username: str, password: str) -> None:
        status, payload = self._request(
            "POST", "/api/v1/auth/login", form={"username": username, "password": password}
        )
        if status != 200 or not isinstance(payload, dict) or "access_token" not in payload:
            # Measuring 401s as throughput is the failure this guards against.
            print(f"login failed: {status} {payload}", file=sys.stderr)
            sys.exit(2)
        self.token = payload["access_token"]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def run_round(probe: Probe, path: str, concurrency: int, index: int) -> dict:
    def one(i: int):
        started = time.perf_counter()
        status, payload = probe._request(
            "POST",
            path,
            body={
                "ulpin": f"12345679{index:02d}{i:05d}",
                "category": "OTHER",
                "description": f"write probe round={index} seq={i}",
                "contact_email": f"probe{index}-{i}@example.invalid",
                "priority": "LOW",
            },
        )
        return (time.perf_counter() - started) * 1000.0, status, payload

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, range(concurrency)))

    latencies = [r[0] for r in results]
    statuses = Counter(r[1] for r in results)
    case_numbers = [r[2].get("case_number") for r in results if isinstance(r[2], dict)]
    duplicates = {k: v for k, v in Counter(case_numbers).items() if v > 1}

    return {
        "round": index,
        "requests": len(results),
        "statuses": dict(statuses),
        "p50_ms": round(percentile(latencies, 50), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "p99_ms": round(percentile(latencies, 99), 1),
        "max_ms": round(max(latencies), 1),
        "mean_ms": round(statistics.fmean(latencies), 1),
        "distinct_case_numbers": len(set(case_numbers)),
        "duplicate_case_numbers": duplicates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True, help="Base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--path", default=DEFAULT_WRITE_PATH, help="Write endpoint to probe")
    parser.add_argument("--concurrency", type=int, default=40)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--username", default="citizen.demo")
    parser.add_argument("--password", default="demo@2026")
    parser.add_argument("--label", default="write-path")
    args = parser.parse_args()

    probe = Probe(args.host)
    probe.login(args.username, args.password)
    print(f"target: {args.host}{args.path}")
    print(f"user:   {args.username}   concurrency: {args.concurrency}   rounds: {args.rounds}")

    rounds = []
    for i in range(1, args.rounds + 1):
        result = run_round(probe, args.path, args.concurrency, i)
        rounds.append(result)
        print(
            f"round {result['round']}: {result['requests']} writes  "
            f"p50={result['p50_ms']}ms p95={result['p95_ms']}ms p99={result['p99_ms']}ms  "
            f"statuses={result['statuses']}  distinct_case_numbers={result['distinct_case_numbers']}"
        )
        if result["duplicate_case_numbers"]:
            print(f"  LOST UPDATE: duplicate case numbers {result['duplicate_case_numbers']}", file=sys.stderr)

    all_statuses = Counter()
    for r in rounds:
        all_statuses.update(r["statuses"])
    total = sum(r["requests"] for r in rounds)
    errors = {k: v for k, v in all_statuses.items() if k >= 400}
    duplicates = {r["round"]: r["duplicate_case_numbers"] for r in rounds if r["duplicate_case_numbers"]}

    print()
    print(f"total writes: {total}")
    print(f"statuses:     {dict(all_statuses)}")
    print(f"p50 across rounds: {round(statistics.fmean([r['p50_ms'] for r in rounds]), 1)}ms")
    print(f"p95 across rounds: {round(max(r['p95_ms'] for r in rounds), 1)}ms")

    print(json.dumps({
        "label": args.label,
        "path": args.path,
        "concurrency": args.concurrency,
        "rounds": rounds,
        "errors": errors,
        "duplicate_case_numbers": duplicates,
    }, indent=2))

    # Exit non-zero on a lost update or a server error. A write path that loses
    # writes has not passed, whatever the latency says.
    if duplicates or any(s >= 500 for s in all_statuses):
        print("\nFAILED: lost writes or server errors", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())