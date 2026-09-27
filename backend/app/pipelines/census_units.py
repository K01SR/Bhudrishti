"""Census 2011 administrative-unit counts, from the data.gov.in release.

The counts are official: Office of the Registrar General & Census Commissioner,
published as the "Number of Administrative Units" table (Census 2001 and 2011).
What this module deliberately does *not* carry is any place *name* below state
level, because the published table has none. It is a table of totals, so the
hierarchy exposed here answers "how many" and never pretends to answer "which
ones". For names, the boundary chain and OpenStreetMap supply them, and the
caller is told which source answered.

Source file:
  backend/app/data/census2011_admin_units.csv
  (data.gov.in, Government Open Data License - India)

The counts are 2011 census figures. Administrative units change between
censuses, so any comparison against a current boundary set is a comparison
between a 2011 count and a present-day geometry, and the two disagree for
reasons that have nothing to do with this data being wrong.
"""
from __future__ import annotations

import csv
import functools
import os
from typing import Dict, List, Optional

_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "census2011_admin_units.csv",
)

# Census 2001 and 2011 are both published. The app reports 2011.
_YEAR_COLUMNS = {
    "districts": "Districts",
    "sub_districts": "Sub-Districts",
    "statutory_towns": "No. of Towns - Statutory Towns",
    "census_towns": "No. of Towns - Census Towns",
    "villages": "Villages",
}

# The national row carries no state of its own.
_NATIONAL_ROW = "India"

# Census 2011 used these labels. Several are also common English words, so
# callers matching on a district name would otherwise read "Goa" as a country
# or "Tripura" as a city. The names are kept verbatim from the file and only
# the year is attributed, because a renamed state is a different assertion
# about a jurisdiction than a count of its units.
CENSUS_YEAR = 2011

PROVENANCE = {
    "source": "data.gov.in / Office of the Registrar General & Census Commissioner",
    "dataset": "Number of Administrative Units, Census 2001 and 2011",
    "license": "Government Open Data License - India (GODL)",
    "census_year": CENSUS_YEAR,
    "contains": "counts of administrative units per state",
    "does_not_contain": "place names, boundaries, or coordinates below state level",
}


@functools.lru_cache(maxsize=1)
def _rows() -> List[Dict[str, str]]:
    if not os.path.exists(_DATA_FILE):
        return []
    with open(_DATA_FILE, encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


def _int_or_none(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        value = int(float(text))
    except ValueError:
        return None
    return value if value >= 0 else None


@functools.lru_cache(maxsize=1)
def _by_state() -> Dict[str, Dict[str, object]]:
    """State name -> counts, with the national row kept separately."""
    out: Dict[str, Dict[str, object]] = {}
    for row in _rows():
        name = (row.get("India/State/Union Territory") or "").strip()
        if not name or name == _NATIONAL_ROW:
            continue
        counts: Dict[str, Optional[int]] = {}
        for key, prefix in _YEAR_COLUMNS.items():
            counts[key] = _int_or_none(row.get(f"{prefix} - {CENSUS_YEAR}"))
        out[name] = {"state": name, "census_year": CENSUS_YEAR, "counts": counts}
    return out


@functools.lru_cache(maxsize=1)
def national_counts() -> Dict[str, object]:
    """The published India-wide totals for the 2011 census."""
    for row in _rows():
        if (row.get("India/State/Union Territory") or "").strip() == _NATIONAL_ROW:
            counts = {k: _int_or_none(row.get(f"{p} - {CENSUS_YEAR}")) for k, p in _YEAR_COLUMNS.items()}
            return {
                "scope": "India",
                "census_year": CENSUS_YEAR,
                "counts": counts,
                "provenance": dict(PROVENANCE),
            }
    return {"scope": "India", "census_year": CENSUS_YEAR, "counts": {}, "provenance": dict(PROVENANCE)}


def state_counts(state: str) -> Optional[Dict[str, object]]:
    """Published 2011 counts for one state, matched case-insensitively.

    Returns ``None`` when the state is not in the release rather than guessing
    a number, so a caller can tell "not published" from "zero".
    """
    if not state:
        return None
    rows = _by_state()
    hit = rows.get(state.strip())
    if hit is None:
        lowered = {k.lower(): v for k, v in rows.items()}
        hit = lowered.get(state.strip().lower())
    return dict(hit) if hit else None


def state_names() -> List[str]:
    """Every state/UT name in the release, verbatim, sorted."""
    return sorted(_by_state())


def coverage_note(level: str) -> str:
    """Why a level has no Census count behind it, for API and UI surfaces."""
    return (
        "Census 2011 published counts of these units but no names, and the "
        "boundary chain supplies only what it has geometry for. A missing entry "
        "means no published count for that parent, not zero."
    )
