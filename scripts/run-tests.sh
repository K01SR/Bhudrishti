#!/usr/bin/env bash
# Run the backend test suite the way it is meant to be run.
#
# This exists because the suite was never wired to anything. It is 287 tests
# that assert, among other things, that the product does not claim to be a
# government system -- which is not a useful safety net if nobody can execute
# it. Three things have to be true before a run is meaningful:
#
#   * PostGIS, not plain Postgres. ensure_schema() issues CREATE EXTENSION
#     postgis, so a vanilla postgres image fails with "extension must first be
#     installed".
#   * Redis. The vector-tile cache tests talk to a real Redis.
#   * Schema plus one jurisdiction row. See tests/fixtures/ensure_fixtures.py
#     for why the fixture is required rather than optional.
#
# Usage:
#   scripts/run-tests.sh              # full suite
#   scripts/run-tests.sh -k pattern   # extra args are passed through to pytest
#
# Python dependencies are cached in the named volume bhudrishti_testdeps, so
# only the first run pays for pip.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NET="${BHUD_TEST_NET:-bhud_test_net}"
PG="${BHUD_TEST_PG:-bhud_test_pg}"
REDIS="${BHUD_TEST_REDIS:-bhud_test_redis}"
DEPS_VOL="${BHUD_TEST_DEPS_VOL:-bhud_test_deps}"
PG_DB="${POSTGRES_DB:-bhudrishti_3d}"
PG_USER="${POSTGRES_USER:-bhudrishti}"
PG_PASS="${POSTGRES_PASSWORD:-bhudrishti_secure_spatial_2026}"

cleanup() {
  docker rm -f "$PG" "$REDIS" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> starting throwaway PostGIS and Redis"
cleanup
docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" --network-alias postgres \
  -e POSTGRES_USER="$PG_USER" -e POSTGRES_PASSWORD="$PG_PASS" -e POSTGRES_DB="$PG_DB" \
  postgis/postgis:16-3.4 >/dev/null
docker run -d --name "$REDIS" --network "$NET" --network-alias redis \
  redis:7-alpine >/dev/null

echo "==> waiting for PostGIS"
for _ in $(seq 1 60); do
  if docker exec "$PG" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec "$PG" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null

echo "==> installing python dependencies (cached in volume $DEPS_VOL)"
docker volume create "$DEPS_VOL" >/dev/null
docker run --rm -v "$ROOT:/w" -w /w -v "$DEPS_VOL:/deps" \
  -e PYTHONPATH=/deps \
  python:3.11-slim sh -c \
  'pip install -q --target=/deps -r backend/requirements.txt pytest >/dev/null 2>&1 || true'

echo "==> running suite"
# The suite is not clean under a random order: tests/fixtures/ensure_fixtures.py
# makes the database state deterministic so ordering stops mattering.
docker run --rm --network "$NET" \
  -v "$ROOT:/w" -w /w \
  -v "$DEPS_VOL:/deps" \
  -e PYTHONPATH="/deps:/w/backend" \
  -e ENABLE_DEMO_MODE=1 \
  python:3.11-slim sh -c \
  "python tests/fixtures/ensure_fixtures.py && python -m pytest tests -q $*"
