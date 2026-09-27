"""LGD village directory: real administrative places, not real properties.

The Local Government Directory (LGD) is the official register of village and
local-body units maintained by the Ministry of Panchayati Raj. The table built
by ``scripts/build_lgd_villages.py`` holds one row per administrative village
with its official LGD code, its parent district and sub-district, and the
Census 2001/2011 code that ties it to the national census tables.

What that means for the rest of the app
---------------------------------------
An LGD village is a *real administrative unit*, so it is safe to show, search,
filter and navigate by it, and to attribute it to the publisher with a
retrieval date.

It is **not** a cadastre. The directory records no parcel boundaries, no plot
area, no land use, no ownership and no ULPIN. A query here can therefore answer
"which villages are in this district" and must never be used to answer "who owns
this plot" or "how much FSI is left". Anything derived from these rows inherits
that limit, which is why the loader exposes the source and its retrieval date
alongside every result.

Database
--------
``backend/app/data/lgd_villages.sqlite`` is a build artifact, not a committed
file; rebuild it from the LGD exports with::

    python scripts/build_lgd_villages.py '/path/to/downloadDir*.zip'
"""
from __future__ import annotations

import functools
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
_DB_FILE = os.path.join(_DATA_DIR, "lgd_villages.sqlite")
_MANIFEST_FILE = os.path.join(_DATA_DIR, "lgd_villages.manifest.json")

SOURCE = "lgd"
SOURCE_LABEL = "Local Government Directory (MoPR)"

_lock = threading.Lock()


def database_path() -> str:
    return _DB_FILE


def is_available() -> bool:
    return os.path.exists(_DB_FILE)


@functools.lru_cache(maxsize=1)
def manifest() -> Dict[str, Any]:
    """Build provenance: publisher, retrieval date, per-state counts."""
    if not os.path.exists(_MANIFEST_FILE):
        return {}
    with open(_MANIFEST_FILE, encoding="utf-8") as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=1)
def _connect() -> sqlite3.Connection:
    """Read-only, shared connection.

    ``check_same_thread=False`` because FastAPI serves sync helpers from a
    thread pool. Writes are refused at the file level as well as in practice.
    """
    if not os.path.exists(_DB_FILE):
        raise FileNotFoundError(
            f"{_DB_FILE} is missing. Rebuild it with "
            "python scripts/build_lgd_villages.py '<downloadDir*.zip>'"
        )
    conn = sqlite3.connect(f"file:{_DB_FILE}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    try:
        with _lock:
            rows = _connect().execute(sql, params).fetchall()
    except FileNotFoundError:
        return []
    return [dict(row) for row in rows]


def _provenance() -> Dict[str, Any]:
    meta = manifest()
    return {
        "source": SOURCE,
        "source_label": SOURCE_LABEL,
        "publisher": meta.get(
            "publisher", "Ministry of Panchayati Raj, Government of India"
        ),
        "source_url": meta.get(
            "source_url", "https://lgdirectory.gov.in/downloadDirectory.do"
        ),
        "retrieved": meta.get("retrieved_utc"),
        "authoritative": True,
        "note": (
            "Administrative village directory. Official codes and names, but "
            "no parcel boundaries, ownership, plot area or land use."
        ),
    }


def _row_to_village(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "village_code": row["village_code"],
        "village_name": row["village_name_en"] or row["village_name_local"],
        "village_name_local": row["village_name_local"] or None,
        "village_status": row["village_status"] or None,
        "district_code": row["district_code"],
        "district_name": row["district_name"],
        "subdistrict_code": row["subdistrict_code"],
        "subdistrict_name": row["subdistrict_name"],
        "state_code": row["lg_state_code"],
        "state_name": row["lg_state_name"],
        "census_2011_code": row["census_2011_code"] or None,
        "census_2001_code": row["census_2001_code"] or None,
        "geometry_kind": "none",
        "provenance": _provenance(),
    }


def count_villages() -> int:
    rows = _query("SELECT COUNT(*) AS n FROM villages")
    return int(rows[0]["n"]) if rows else 0


def list_states() -> List[Dict[str, Any]]:
    rows = _query(
        """
        SELECT lg_state_code AS state_code, lg_state_name AS state_name,
               COUNT(*) AS village_count
        FROM villages
        GROUP BY lg_state_code, lg_state_name
        ORDER BY lg_state_name
        """
    )
    return [{**row, "provenance": _provenance()} for row in rows]


def list_districts(state_name: str) -> List[Dict[str, Any]]:
    rows = _query(
        """
        SELECT district_code, district_name, COUNT(*) AS village_count
        FROM villages WHERE lg_state_name = ?
        GROUP BY district_code, district_name ORDER BY district_name
        """,
        (state_name,),
    )
    return [{**row, "state_name": state_name, "provenance": _provenance()} for row in rows]


def list_subdistricts(state_name: str, district_name: str) -> List[Dict[str, Any]]:
    rows = _query(
        """
        SELECT subdistrict_code, subdistrict_name, COUNT(*) AS village_count
        FROM villages
        WHERE lg_state_name = ? AND district_name = ?
        GROUP BY subdistrict_code, subdistrict_name ORDER BY subdistrict_name
        """,
        (state_name, district_name),
    )
    return [
        {
            **row,
            "state_name": state_name,
            "district_name": district_name,
            "provenance": _provenance(),
        }
        for row in rows
    ]


def list_villages(
    state_name: Optional[str] = None,
    district_name: Optional[str] = None,
    subdistrict_name: Optional[str] = None,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if state_name:
        clauses.append("lg_state_name = ?")
        params.append(state_name)
    if district_name:
        clauses.append("district_name = ?")
        params.append(district_name)
    if subdistrict_name:
        clauses.append("subdistrict_name = ?")
        params.append(subdistrict_name)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 20000)))
    rows = _query(
        f"""
        SELECT * FROM villages {where}
        ORDER BY lg_state_name, district_name, subdistrict_name, village_name_en
        LIMIT ?
        """,
        tuple(params),
    )
    return [_row_to_village(row) for row in rows]


def get_village(village_code: str) -> Optional[Dict[str, Any]]:
    rows = _query("SELECT * FROM villages WHERE village_code = ?", (str(village_code),))
    return _row_to_village(rows[0]) if rows else None


def search_villages(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Prefix-first village search, ranked so an exact name wins.

    Matching is case-insensitive and prefix-based rather than substring so that
    typing "ner" surfaces Nerul before the many villages that merely contain
    those letters. The village name itself is the only free-text field matched;
    districts and sub-districts are reached through the cascade.

    A bare number is treated as an official LGD village code, because that is
    how a user who already has the code will search, and it is unambiguous.
    """
    term = (query or "").strip()
    if not term:
        return []
    if term.isdigit():
        record = get_village(term)
        return [record] if record else []
    rows = _query(
        """
        SELECT * FROM villages
        WHERE LOWER(village_name_en) LIKE ? OR LOWER(village_name_local) LIKE ?
        ORDER BY
            CASE WHEN LOWER(village_name_en) = ? THEN 0
                 WHEN LOWER(village_name_en) LIKE ? THEN 1
                 ELSE 2 END,
            LENGTH(village_name_en),
            village_name_en
        LIMIT ?
        """,
        (f"{term.lower()}%", f"{term.lower()}%", term.lower(), f"{term.lower()}%", max(1, limit)),
    )
    return [_row_to_village(row) for row in rows]


def villages_in_subdistrict(subdistrict_code: str) -> List[Dict[str, Any]]:
    rows = _query(
        "SELECT * FROM villages WHERE subdistrict_code = ? ORDER BY village_name_en",
        (str(subdistrict_code),),
    )
    return [_row_to_village(row) for row in rows]
