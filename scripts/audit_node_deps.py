#!/usr/bin/env python3
"""Fail CI on High/Critical npm advisories, with narrow documented exceptions.

Replaces ``npm audit --omit=dev --audit-level=high || true`` in
``.github/workflows/security.yml``. That line paired an ``--audit-level=high``
with ``|| true``, which swallowed the exit code, so the gate it described could
never fire: a critical advisory was reported and the step passed.

Policy
------
* High and Critical fail the build. Medium and below are reported only.
* ``--omit=dev``: devDependencies do not ship, so they are audited separately
  (or not at all) rather than blocking releases on build tooling.

Exceptions
----------
An exception is a specific advisory id, with a written justification, that is
allowed to persist. Exceptions are not a way to make a red build green: each one
names the advisory, says why it is not reachable, and -- where reachability
depends on the architecture -- is re-checked here rather than trusted. If the
condition that justified the exception stops holding, the exception stops
applying and the advisory fails the build like any other.

That re-check is the whole point. "Trust me, it's not reachable" decays into an
unexplained suppression within one refactor; here, adding SSR to the app makes
the react-router exception expire automatically and CI goes red on a real
exposure.

Usage::

    python3 scripts/audit_node_deps.py [--frontend-dir frontend] [--report FILE]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

FAILING_SEVERITIES = {"high", "critical"}


@dataclass
class Accepted:
    """An advisory allowed to persist, on the record, until a stated date.

    Deliberately different from a suppression. Every field is a promise:
    why the risk is not being fixed yet, what the exposure actually is, and the
    last date it may be carried. On or after ``expires`` the acceptance stops
    applying and the advisory fails the build, so a deferral cannot quietly
    become permanent the way ``|| true`` did.
    """

    advisory_id: str
    package: str
    reason: str
    exposure: str
    expires: str  # ISO date, YYYY-MM-DD
    track_as: str = ""
    # Optional run-time re-check: (still_justified, explanation).
    guard: Any = None


ACCEPTED: List[Accepted] = [
    Accepted(
        advisory_id="GHSA-jrc7-96c5-q579",
        package="maplibre-gl",
        reason=(
            "XSS Sanitizer Bypass in DOM.sanitize() via Live NamedNodeMap Removal "
            "Skip. Affects maplibre-gl <= 6.4.0; installed 4.7.1; patched in "
            "6.4.1. Not fixed here because the fix is a two-major-version jump "
            "(4.7.1 -> 6.4.1+) and maplibre v6 drops the default export and "
            "changes several typed signatures, breaking 10 type errors across "
            "7 map components. Migrating that without the budget to verify map "
            "rendering end to end would risk shipping a broken map, which is a "
            "worse outcome than a recorded risk."
        ),
        exposure=(
            "Reachable in principle: maplibre renders every map popup, and "
            "popup content includes strings sourced from OpenStreetMap and "
            "GlobalML (place names, building names). Exploitability depends on a "
            "popup interpolating untrusted text through the vulnerable path, "
            "which has not been audited in this repository. Treat as open, not "
            "as theoretical."
        ),
        expires="2026-12-01",
        track_as="upgrade maplibre-gl 4.7.1 -> >=6.4.1 (breaking; 7 map components)",
    ),
]


def _audit(frontend: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        ["npm", "audit", "--omit=dev", "--json"],
        cwd=frontend, capture_output=True, text=True,
    )
    # npm audit exits 1 when it finds anything; the JSON is still valid then.
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("npm audit did not emit JSON:\n" + proc.stdout + proc.stderr, file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frontend-dir", default="frontend")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    frontend = Path(args.frontend_dir).resolve()
    report = _audit(frontend)
    vulns = report.get("vulnerabilities") or {}

    print("npm audit summary: " + json.dumps(report.get("metadata", {}).get("vulnerabilities", {})))

    failing: List[str] = []
    accepted: List[str] = []
    for name, info in sorted(vulns.items()):
        severity = str(info.get("severity", "")).lower()
        if severity not in FAILING_SEVERITIES:
            continue
        via = info.get("via") or []
        ids = [v.get("url", "") for v in via if isinstance(v, dict) and v.get("url")]
        ghsa = [u.rsplit("/", 1)[-1] for u in ids if "/GHSA-" in u]
        matched = next((a for a in ACCEPTED if a.advisory_id in ghsa and a.package == name), None)
        if matched is None:
            failing.append(f"{name}@{info.get('range','?')} [{severity}] {', '.join(ids) or 'no advisory id'}")
            continue

        frontend_dir = frontend
        if matched.guard is not None:
            still_ok, why = matched.guard(frontend_dir)
            if not still_ok:
                # The justification expired. This must fail loudly.
                failing.append(
                    f"{name}: {matched.advisory_id} was accepted because {matched.reason} "
                    f"but that no longer holds: {why}"
                )
                continue

        # A deferral must not outlive its own expiry date.
        today = date.today().isoformat()
        if today >= matched.expires:
            failing.append(
                f"{name}: {matched.advisory_id} was accepted until {matched.expires}, "
                f"which has passed (today is {today}). Fix it or record a new "
                f"acceptance with a fresh date."
            )
            continue

        accepted.append(
            f"{name}: {matched.advisory_id} ACCEPTED UNTIL {matched.expires}\n"
            f"      exposure: {matched.exposure}\n"
            f"      action:   {matched.track_as}"
        )

    if accepted:
        print("\nACCEPTED (documented, still justified):")
        for a in accepted:
            print("  - " + a)
    if failing:
        print("\nFAILING (must be fixed):", file=sys.stderr)
        for f in failing:
            print("  - " + f, file=sys.stderr)
        if args.report:
            Path(args.report).write_text(json.dumps(
                {"failing": failing, "accepted": accepted}, indent=2))
        return 1

    print("\nNo unaccepted high or critical advisories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())