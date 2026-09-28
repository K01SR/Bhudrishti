# Phase 1c — Real LiDAR streaming: closed as externally constrained

**Status:** closed, not delivered. The blocker is the availability of the data,
not the implementation.

## What the roadmap item asked for

Stream genuinely measured point returns into the LiDAR view, replacing the
generated Airoli point cloud so the product never renders invented points as
though a survey had flown.

## Why it cannot be delivered for this product

Audited 2026-09 against the public, credential-free sources:

| Source | Coverage | Credentials | Point format |
|---|---|---|---|
| `open-lidar-data` (public S3) | BE CH DE DK EE ES FI FR IE LU LV NL PL SE SI UK US | none | COPC (range-readable) |
| `s3://usgs-lidar-public` (USGS 3DEP) | United States | none | EPT / LAZ (range-readable) |
| `s3://usgs-lidar-requester-pays` | United States | AWS account | raw LAZ 1.4 |
| `tnmaccess.nationalmap.gov` | United States | none | product index |
| ISRO/NRSC Bhuvan | India | login for the archive | imagery, ortho, DEM — **no LiDAR** |

**India has no open airborne LiDAR.** None of the areas this product serves —
Airoli Sector 8, Bandra West, Delhi, Mumbai Fort, Bengaluru — is covered by any
of them.

LAZ decoding is *not* the obstacle, which was worth checking rather than
assuming: `laspy>=2.5.4` is already a dependency, and the `lazrs` backend
installs cleanly from a wheel. Coverage is the whole obstacle.

A pipeline that streams real LAZ would therefore work for Belgium and
Washington and for none of the app's actual precincts — a large, slow, hard-to-
maintain code path that would never render a real Indian point. That is not a
trade worth making, and building it would add a dependency and a download path
without adding a single authentic point to the product.

## What was done instead

The refusal now states the true reason, and the true reason is enforced by tests
rather than left in a comment.

1. **`app/core/lidar_coverage.py`** records the audit: the verified coverage
   table, the per-country source, and the message. It is a small module with a
   lookup rather than a note in a document, so the fact is available to code.
2. **The point-cloud routes pass that fact as a `data_note`** on the 503 they
   already returned. A caller can now tell "this deployment is refusing
   generated data" (fixable by configuration) from "no such dataset is
   published for this place" (not fixable by any configuration).
3. **`DemoDataDisabled` carries an optional `note`**, and the handler returns it
   as `data_note` alongside `demo_mode`.
4. **The client stops dropping it.** `extractError` in `lidarApi.ts` read
   `detail` only, so the reason never reached the screen.
5. **`tests/test_lidar_coverage.py`** asserts that all five precincts are outside
   coverage, that the countries the table *does* claim resolve, and that the
   refusal says so. If a source starts publishing India, these fail loudly
   rather than the message quietly going stale.

## What the product serves instead, and what it must not call LiDAR

- Building footprints — Microsoft GlobalML (published, non-authoritative) or
  OpenStreetMap.
- Ground and surface elevation — AWS Terrain Tiles, a real global elevation
  raster. Already wired via `app/sources/terrain.py`.
- A modelled point field in `opendata.service.area_lidar_points`, labelled
  `MODELLED`. It is not LiDAR and is not presented as such.

None of these is a substitute for measured returns, and the API does not imply
that it is: the LiDAR view returns an honest 503 and explains that the data does
not exist publicly.

## If this ever becomes deliverable

It needs a source with Indian coverage, licensed for redistribution — most
plausibly a direct NRSC/Bhuvan agreement, or a commercial provider. Nothing in
the codebase blocks that: `lazrs` plus `laspy` reads LAZ, and a COPC or EPT
source is range-readable and therefore streamable without downloading a national
archive. The work would be a source module, a coverage entry, and a stream
decoder. The refusal message is written to be revised at exactly that point.
