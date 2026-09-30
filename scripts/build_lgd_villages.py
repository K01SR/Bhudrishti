#!/usr/bin/env python3
"""Build the LGD village table from Ministry of Panchayati Raj directory dumps.

Source
------
Local Government Directory (LGD), Ministry of Panchayati Raj, Government of
India. Bulk "Download Directory" export, retrieved from

    https://lgdirectory.gov.in/downloadDirectory.do

with the report "All Villages of a State". Each export is a ZIP whose members
are Excel 2003 XML (SpreadsheetML) files that carry an ``.xls`` extension. This
script reads the ``villageofSpecificState*`` member of every ZIP it is pointed
at and folds the rows into one SQLite database.

Column layout of the sheet (verified against the Maharashtra export)::

    0  S. No.                 7  Village Name (English)
    1  District Code          8  Village Name (Local)
    2  District Name          9  Village Status
    3  Sub-District Code     10  Census 2001 Code
    4  Sub-District Name     11  Census 2011 Code
    5  Village Code          12  Remark
    6  Village Version

What this data *is*: an official directory of administrative village units, with
their official LGD codes. What it is *not*: a cadastre. It carries no parcel
boundaries, no ownership, no plot area and no land use, so nothing derived from
it may be presented as a property record. The ``Census 2011 Code`` column is
kept because it is the join key to the Census 2011 administrative table.

Output
------
``backend/app/data/lgd_villages.sqlite`` plus a provenance manifest recording
the retrieval date, per-state row counts and the SHA-256 of every input ZIP, so
the build can be re-run and audited. The database itself is a build artifact and
is not committed.

Usage
-----
    python scripts/build_lgd_villages.py /path/to/downloadDir*.zip \\
        --out backend/app/data/lgd_villages.sqlite
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile

SS = "{urn:schemas-microsoft-com:office:spreadsheet}"
ROW_TAG = SS + "Row"
CELL_TAG = SS + "Cell"
DATA_TAG = SS + "Data"

# "All Villages of Maharashtra(State code : 27) State"
TITLE_RE = re.compile(r"All Villages of (.+?)(?=\(State|<|$)")

# Header rows precede the data: title, blank, column names, "(In English)" units.
MIN_DATA_ROW_INDEX = 5

# The directory's own state/union-territory dropdown lists 36 entries. Recorded
# explicitly rather than inferred from the archives, because the archives cannot
# distinguish "state published with zero villages" (Chandigarh) from "state not
# downloaded", and conflating the two would misreport coverage either way.
STATE_ENTITIES = 36

SCHEMA = """
CREATE TABLE IF NOT EXISTS villages (
    lg_state_code     TEXT NOT NULL,
    lg_state_name     TEXT NOT NULL,
    district_code     TEXT NOT NULL,
    district_name     TEXT NOT NULL,
    subdistrict_code  TEXT NOT NULL,
    subdistrict_name  TEXT NOT NULL,
    village_code      TEXT NOT NULL PRIMARY KEY,
    village_version   TEXT,
    village_name_en   TEXT,
    village_name_local TEXT,
    village_status    TEXT,
    census_2001_code  TEXT,
    census_2011_code  TEXT
);
CREATE INDEX IF NOT EXISTS ix_villages_hierarchy
    ON villages (lg_state_name, district_name, subdistrict_name);
CREATE INDEX IF NOT EXISTS ix_villages_name_en ON villages (village_name_en);
CREATE INDEX IF NOT EXISTS ix_villages_census11 ON villages (census_2011_code);
"""

COLUMNS = [
    "lg_state_code",
    "lg_state_name",
    "district_code",
    "district_name",
    "subdistrict_code",
    "subdistrict_name",
    "village_code",
    "village_version",
    "village_name_en",
    "village_name_local",
    "village_status",
    "census_2001_code",
    "census_2011_code",
]

# Sheet column index -> table column, from the layout documented above.
SHEET_TO_COLUMN = {
    1: "district_code",
    2: "district_name",
    3: "subdistrict_code",
    4: "subdistrict_name",
    5: "village_code",
    6: "village_version",
    7: "village_name_en",
    8: "village_name_local",
    9: "village_status",
    10: "census_2001_code",
    11: "census_2011_code",
}


def cell_text(cell: ET.Element) -> str:
    data = cell.find(DATA_TAG)
    if data is None or data.text is None:
        return ""
    return data.text.strip()


def iter_rows(fh):
    """Yield each Row as a list of strings, clearing elements as we go.

    The sheet is 35-65 MB of XML, so it is parsed incrementally: holding the
    whole tree costs several hundred megabytes per state and buys nothing.
    """
    for _, elem in ET.iterparse(fh, events=("end",)):
        if elem.tag == ROW_TAG:
            yield [cell_text(c) for c in elem.findall(CELL_TAG)]
            elem.clear()


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def parse_zip(path: str, conn: sqlite3.Connection) -> tuple[str, int]:
    """Insert every village row from one export ZIP. Returns (state, rows)."""
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if n.startswith("villageof")]
        if not members:
            return "", 0
        state = ""
        state_code = ""
        inserted = 0
        batch: list[tuple] = []

        with zf.open(members[0]) as fh:
            for index, row in enumerate(iter_rows(fh)):
                if index < MIN_DATA_ROW_INDEX:
                    # Rows 0-3 are the sheet title and the two-row column header
                    # band; the state is named in row 1 as
                    # "All Villages of <State>(State code : NN) State".
                    joined = " ".join(row)
                    if not state:
                        match = TITLE_RE.search(joined)
                        if match:
                            state = clean(match.group(1))
                    if not state_code:
                        code_match = re.search(
                            r"State\s*code\s*:?\s*(\d+)", joined, re.I
                        )
                        if code_match:
                            state_code = code_match.group(1)
                    continue

                if len(row) < 12:
                    continue

                village_code = clean(row[5])
                if not village_code or not village_code.isdigit():
                    # A repeated column-name band or a summary line.
                    continue

                record = {name: "" for name in COLUMNS}
                record["lg_state_code"] = state_code
                record["lg_state_name"] = state
                for sheet_index, column in SHEET_TO_COLUMN.items():
                    if sheet_index < len(row):
                        record[column] = clean(row[sheet_index])

                batch.append(tuple(record[name] for name in COLUMNS))
                if len(batch) >= 5000:
                    conn.executemany(
                        f"INSERT OR REPLACE INTO villages ({','.join(COLUMNS)}) "
                        f"VALUES ({','.join('?' * len(COLUMNS))})",
                        batch,
                    )
                    inserted += len(batch)
                    batch.clear()

        if batch:
            conn.executemany(
                f"INSERT OR REPLACE INTO villages ({','.join(COLUMNS)}) "
                f"VALUES ({','.join('?' * len(COLUMNS))})",
                batch,
            )
            inserted += len(batch)

    return state, inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="export ZIPs, or a glob for them")
    parser.add_argument(
        "--out",
        default="backend/app/data/lgd_villages.sqlite",
        help="output SQLite path",
    )
    parser.add_argument(
        "--manifest",
        default="backend/app/data/lgd_villages.manifest.json",
        help="output provenance manifest path",
    )
    args = parser.parse_args()

    paths: list[str] = []
    for pattern in args.inputs:
        expanded = sorted(glob.glob(pattern))
        if expanded:
            paths.extend(expanded)
        elif os.path.exists(pattern):
            paths.append(pattern)
    # A state can be exported more than once; the newest filename wins.
    paths = sorted(set(paths))

    if not paths:
        print("no input archives matched", file=sys.stderr)
        return 2

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    for stale in (out_path, out_path + "-journal"):
        if os.path.exists(stale):
            os.remove(stale)

    conn = sqlite3.connect(out_path)
    conn.executescript(SCHEMA)

    per_state: dict[str, int] = {}
    sources: list[dict] = []

    for path in paths:
        try:
            state, rows = parse_zip(path, conn)
        except zipfile.BadZipFile:
            print(f"  skip (not a zip): {os.path.basename(path)}")
            continue
        if not rows:
            print(f"  skip (no village rows): {os.path.basename(path)}")
            continue
        conn.commit()
        digest = sha256(path)
        sources.append(
            {
                "archive": os.path.basename(path),
                "state": state,
                "rows_read": rows,
                "bytes": os.path.getsize(path),
                "sha256": digest,
            }
        )
        # Later exports of the same state supersede earlier ones.
        per_state[state] = max(per_state.get(state, 0), rows)
        print(f"  {state:52} {rows:>8,}")

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM villages").fetchone()[0]
    distinct = conn.execute(
        "SELECT COUNT(DISTINCT lg_state_name) FROM villages"
    ).fetchone()[0]
    conn.execute("VACUUM")
    conn.close()

    manifest = {
        "dataset": "Local Government Directory (LGD) villages",
        "publisher": "Ministry of Panchayati Raj, Government of India",
        "source_url": "https://lgdirectory.gov.in/downloadDirectory.do",
        "report": "All Villages of a State (Xls Report)",
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "note": (
            "Administrative village directory. Carries official LGD codes, not "
            "parcel boundaries, ownership, plot area or land use."
        ),
        "state_entities": STATE_ENTITIES,
        "state_entities_note": (
            "The LGD directory publishes 36 state/union-territory entries. Chandigarh "
            "is published with no revenue villages, so 35 appear in the village table."
        ),
        "states_present": distinct,
        "total_villages": total,
        "rows_by_state": dict(sorted(per_state.items())),
        "sources": sources,
    }
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"\n{distinct} states, {total:,} villages")
    print(f"database  {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB)")
    print(f"manifest  {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
