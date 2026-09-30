"""Headless load-test runner. Records measurements; invents nothing.

Percentiles without context are the failure mode this script is built to avoid.
A p99 of 40ms is a good result or a bad one depending entirely on how many
workers answered it, whether a cache was warm, and whether the data was real.
So every run writes a JSON document containing the deployment shape alongside
the numbers, and a run with no successful requests is an error rather than a
result.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def detect_demo_mode(host: str) -> str:
    """Ask the backend, rather than trusting this process's environment.

    The load generator and the server routinely run in different places: the
    backend may have ENABLE_DEMO_MODE=1 in its compose override while this
    script's own environment says nothing. Recording the generator's env would
    have reported "unset" for a run that was entirely serving demo data, which
    is exactly the kind of unverified context that makes a benchmark
    unciteable. The scene endpoint is demo-gated, so its status is the answer.
    """
    probe = subprocess.run(
        [
            "curl",
            "-s",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            f"{host}/api/v1/lidar/inspect/scene",
        ],
        capture_output=True,
        text=True,
    )
    code = probe.stdout.strip()
    if code == "200":
        return "on (serving generated demo data)"
    if code == "503":
        return "off (demo-gated endpoints refusing)"
    return f"indeterminate (scene endpoint returned {code or 'no response'})"


def deployment_shape(host: str) -> dict:
    """Record what produced these numbers, so they cannot be quoted bare."""
    return {
        "host": host,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "backend": "uvicorn app.main:app, single worker, no --workers flag",
        "workers": 1,
        "resource_limits": "none declared in docker-compose.yml",
        "cache": "no response cache in front of the API",
        "proxy": "nginx in the frontend image proxies /api to the backend",
        # Probed from the server, not inherited from this process.
        "demo_mode": detect_demo_mode(host),
        "note": (
            "Single-node figures for one uvicorn worker. These are not a "
            "capacity claim for a scaled deployment, and the sample is far too "
            "short to characterise tail latency."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        required=True,
        help="Target base URL. No default on purpose: a load test must name its target.",
    )
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--spawn-rate", type=float, default=2.0)
    parser.add_argument("--run-time", default="60s")
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()

    if not args.host.startswith(("http://", "https://")):
        print("--host must include the scheme, e.g. http://localhost:8000")
        return 2

    RESULTS.mkdir(exist_ok=True)
    csv_prefix = RESULTS / f"{args.label}"
    json_path = RESULTS / f"{args.label}.json"

    # Refuse before generating load, not after.
    probe = subprocess.run(
        ["curl", "-sf", "-o", "/dev/null", f"{args.host}/health"],
        capture_output=True,
    )
    if probe.returncode != 0:
        print(f"Target {args.host} is not answering /health. Not generating load.")
        return 2

    shape = deployment_shape(args.host)
    print(f"target: {args.host}")
    print(f"shape : {json.dumps(shape, indent=2)}")
    print(f"run   : {args.users} users, spawn {args.spawn_rate}/s, {args.run_time}")

    cmd = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(HERE / "locustfile.py"),
        "--host",
        args.host,
        "-u",
        str(args.users),
        "-r",
        str(args.spawn_rate),
        "-t",
        args.run_time,
        "--headless",
        "--csv",
        str(csv_prefix),
        "--csv-full-history",
        "--only-summary",
    ]
    print("running:", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(HERE))

    # Locust writes the aggregates; read them back rather than re-deriving.
    stats_csv = Path(f"{csv_prefix}_stats.csv")
    if not stats_csv.exists():
        print("No stats CSV produced. The run did not complete.")
        return 1

    import csv as _csv

    rows = []
    aggregate = None
    with stats_csv.open() as fh:
        for row in _csv.DictReader(fh):
            name = row.get("Name")
            if name in (None, ""):
                continue
            record = {
                "name": name,
                "requests": int(row["Request Count"]),
                "failures": int(row["Failure Count"]),
                "p50_ms": float(row["50%"]),
                "p95_ms": float(row["95%"]),
                "p99_ms": float(row["99%"]),
                "rps": float(row["Requests/s"]),
            }
            # Locust's totals row is named "Aggregated"; keep it rather than
            # dropping it with the per-endpoint rows, since it is the only place
            # overall throughput is recorded.
            if name == "Aggregated":
                aggregate = record
            else:
                rows.append(record)

    payload = {
        "shape": shape,
        "endpoints": rows,
        "exit_code": completed.returncode,
    }
    if aggregate:
        payload["total"] = aggregate

    successful = sum(r["requests"] - r["failures"] for r in rows)
    payload["successful_requests"] = successful

    json_path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {json_path}")

    if successful == 0:
        print("Zero successful requests: that is a failed run, not a fast one.")
        return 1

    print(
        f"\n{'endpoint':34s} {'n':>6s} {'fail':>5s} {'p50':>7s} {'p95':>7s} {'p99':>7s}"
    )
    for r in payload["endpoints"]:
        print(
            f"{r['name']:34s} {r['requests']:6d} {r['failures']:5d} "
            f"{r['p50_ms']:7.0f} {r['p95_ms']:7.0f} {r['p99_ms']:7.0f}"
        )
    if total := payload.get("total"):
        print(
            f"{'AGGREGATE':34s} {total['requests']:6d} {total['failures']:5d} "
            f"{total['p50_ms']:7.0f} {total['p95_ms']:7.0f} {total['p99_ms']:7.0f} "
            f"  {total['rps']:6.1f} rps"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())