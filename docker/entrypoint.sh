#!/usr/bin/env bash
# Entrypoint for the single-container image.
#
# Its only real job is the one thing a container-per-service stack gets for
# free: waiting for Postgres to accept connections before uvicorn and celery
# start. In compose that is expressed as depends_on: condition:
# service_healthy. In one container there is no healthcheck to wait on, so
# without this the API boots, fails to connect, and either crashes or -- worse,
# depending on retry settings -- comes up and then 500s on the first request.
set -euo pipefail

PGDATA="${PGDATA:-/var/lib/postgresql/data}"
LOG=/tmp/entrypoint.log

# The Postgres client and server binaries are installed under a versioned
# directory and are NOT on the default PATH. Without this, initdb/pg_ctl/psql
# resolve to nothing and the container exits 127 on the very first boot, right
# after logging "running initdb".
export PATH="/usr/lib/postgresql/16/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

log() { echo "[entrypoint] $*"; }

# Only initialise a brand new volume. Re-running against an existing data
# directory would refuse anyway, but failing with initdb's own error is clearer
# than a partial re-init.
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  log "empty data directory at $PGDATA, running initdb"
  # initdb refuses to run as root, so it runs as the postgres user. The
  # password is set afterwards via ALTER USER rather than here: initdb's
  # --pwfile only sets the superuser password for a fresh cluster, and doing it
  # this way keeps the two paths (fresh volume, existing volume) identical.
  gosu_postgres() { su postgres -c "PATH=/usr/lib/postgresql/16/bin:/usr/bin:/bin $1"; }
  gosu_postgres "initdb -D '$PGDATA' -U '$POSTGRES_USER' --auth-local=trust --auth-host=md5" \
    >>"$LOG" 2>&1

  log "starting postgres temporarily to create the database and extensions"
  gosu_postgres "pg_ctl -D '$PGDATA' -o '-c listen_addresses=127.0.0.1' -w start" >>"$LOG" 2>&1
  gosu_postgres "psql -v ON_ERROR_STOP=1 -U '$POSTGRES_USER' -d postgres" <<SQL >>"$LOG" 2>&1
ALTER USER "$POSTGRES_USER" WITH PASSWORD '$POSTGRES_PASSWORD';
SELECT 'CREATE DATABASE "$POSTGRES_DB" OWNER "$POSTGRES_USER"'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$POSTGRES_DB')\gexec
SQL
  # PostGIS has to be created in the new database, and the tables are created
  # by the API on first boot (cadastre_store calls Base.metadata.create_all).
  gosu_postgres "psql -v ON_ERROR_STOP=1 -U '$POSTGRES_USER' -d '$POSTGRES_DB' -c 'CREATE EXTENSION IF NOT EXISTS postgis;'" >>"$LOG" 2>&1
  gosu_postgres "pg_ctl -D '$PGDATA' -w stop" >>"$LOG" 2>&1
  log "cluster initialised"
else
  log "existing cluster found at $PGDATA, leaving it alone"
fi

# /var/run/postgresql is a tmpfs in some bases and a plain dir in others, and
# postgres refuses to start without the socket directory it expects.
mkdir -p /var/run/postgresql
chown postgres:postgres /var/run/postgresql

# The API and worker run as root (see the Dockerfile) so they can write to
# /app/data, but /app/data is created by the postgres user path above on a
# fresh volume. Make it writable either way.
mkdir -p /app/data
chmod 777 /app/data

# Start the supervisor FIRST, then wait.
#
# This order was backwards. The wait ran before `exec "$@"`, and "$@" is
# supervisord, which is the thing that starts Postgres (see
# [program:postgres] in supervisord.conf). So the container waited for a
# database that nothing had started yet, timed out after 60s, and exited 1 on
# every single boot. Nothing in the image could ever come up.
#
# supervisord therefore goes into the background, this script waits for the
# database it is now actually starting, and then blocks on supervisord so the
# container's lifetime is still tied to it: if supervisord dies the container
# exits and the restart policy takes over, and SIGTERM from `docker stop` is
# forwarded to supervisord rather than being swallowed by this script.
log "starting supervisor: $*"
"$@" &
SUPERVISOR_PID=$!

shutdown() {
  log "forwarding shutdown to supervisord (pid $SUPERVISOR_PID)"
  kill -TERM "$SUPERVISOR_PID" 2>/dev/null || true
}
trap shutdown TERM INT

# Bounded, because an unbounded wait turns a real failure into a container that
# hangs forever instead of exiting and being restarted.
log "waiting for postgres on 127.0.0.1:5432"
READY=0
for i in $(seq 1 90); do
  if su postgres -c "pg_isready -h 127.0.0.1 -p 5432 -q" 2>/dev/null; then
    log "postgres is up after ${i}s"
    READY=1
    break
  fi
  # If supervisord already exited there is nothing left to wait for.
  if ! kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
    log "supervisord exited before postgres became ready; see /tmp/supervisord.log"
    exit 1
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  log "postgres did not become ready in 90s; see /tmp/supervisord.log"
  exit 1
fi

# Block for the container's lifetime.
wait "$SUPERVISOR_PID"
