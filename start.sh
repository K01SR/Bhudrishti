#!/usr/bin/env bash
# ==============================================================================
# Bhu-Drishti 3D: Main Application Runner
# Starts FastAPI backend and Vite frontend natively on host OS
# ==============================================================================
set -eo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

say()  { printf "${GREEN}[start]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn ]${NC} %s\n" "$*"; }
fail() { printf "${RED}[error]${NC} %s\n" "$*"; exit 1; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p logs

DAEMON_MODE=0
START_DB=1

for arg in "$@"; do
  case "$arg" in
    -d|--daemon)
      DAEMON_MODE=1
      ;;
    --no-db)
      START_DB=0
      ;;
    --docker)
      say "Launching full stack via Docker Compose..."
      exec docker compose up -d
      ;;
    -h|--help)
      echo -e "${BOLD}Usage:${NC} ./start.sh [OPTIONS]"
      echo ""
      echo "Starts Bhu-Drishti 3D (FastAPI Backend + Vite Frontend) natively on host OS."
      echo ""
      echo -e "${BOLD}Options:${NC}"
      echo "  -d, --daemon   Run services in background (logs stored in logs/)"
      echo "  --no-db        Skip starting backing PostGIS/Redis data store"
      echo "  --docker       Start full containerized stack via Docker Compose"
      echo "  -h, --help     Show this help message"
      echo ""
      echo -e "${BOLD}To stop:${NC} ./stop.sh"
      exit 0
      ;;
  esac
done

say "Checking host environment..."

# 1. Detect Python 3.10+
PYTHON_BIN=""
for py in python3.11 python3.12 python3.13 python3.14 python3; do
  if command -v "$py" >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v "$py")"
    break
  fi
done
[ -n "$PYTHON_BIN" ] || fail "Python 3.10+ not found on host. Please install Python."

# 2. Detect Node.js & npm
command -v node >/dev/null 2>&1 || fail "Node.js not found on host. Please install Node.js."
command -v npm >/dev/null 2>&1 || fail "npm not found on host. Please install npm."

say "Python : $($PYTHON_BIN --version) ($PYTHON_BIN)"
say "Node   : $(node --version) ($(command -v node))"

# 3. Setup Python Virtual Environment
VENV_DIR="$ROOT_DIR/backend/.venv"
if [ ! -d "$VENV_DIR" ]; then
  say "Creating Python virtualenv at backend/.venv..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
  say "Installing backend dependencies from backend/requirements.txt..."
  "$VENV_DIR/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"
fi

# Ensure async DB drivers
if ! "$VENV_DIR/bin/python" -c "import greenlet, psycopg" >/dev/null 2>&1; then
  say "Ensuring async database drivers in virtualenv..."
  "$VENV_DIR/bin/pip" install greenlet "psycopg[binary]>=3.1.0" >/dev/null 2>&1 || true
fi

# 4. Setup Frontend npm dependencies
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  say "Installing frontend npm packages..."
  (cd "$ROOT_DIR/frontend" && npm install)
fi

# 5. Check/Start PostGIS and Redis
POSTGRES_READY=0
if nc -z -w 1 127.0.0.1 5432 2>/dev/null || (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null; then
  POSTGRES_READY=1
  say "PostgreSQL/PostGIS is running on 127.0.0.1:5432"
fi

REDIS_READY=0
if nc -z -w 1 127.0.0.1 6379 2>/dev/null || (exec 3<>/dev/tcp/127.0.0.1/6379) 2>/dev/null; then
  REDIS_READY=1
  say "Redis is running on 127.0.0.1:6379"
fi

if [ $POSTGRES_READY -eq 0 ] && [ $START_DB -eq 1 ]; then
  if command -v docker >/dev/null 2>&1; then
    say "Starting backing database services (PostGIS + Redis) via Docker..."
    docker compose up -d postgres redis >/dev/null 2>&1 || warn "Could not start docker postgres/redis containers"
    sleep 3
    if nc -z -w 2 127.0.0.1 5432 2>/dev/null || (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null; then
      POSTGRES_READY=1
      say "PostGIS container ready on port 5432."
    fi
  else
    warn "PostgreSQL is not listening on 5432 and Docker is unavailable."
    warn "Backend will start in standalone/synthetic mode (hero cadastre & 3D units available)."
  fi
fi

# 6. Configure Environment
export POSTGRES_SERVER="${POSTGRES_SERVER:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export POSTGRES_USER="${POSTGRES_USER:-bhudrishti}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-bhudrishti_secure_spatial_2026}"
export POSTGRES_DB="${POSTGRES_DB:-bhudrishti_3d}"
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export LOCAL_STORAGE_PATH="${LOCAL_STORAGE_PATH:-/tmp/bhudrishti_storage}"
export VITE_PROXY_TARGET="http://127.0.0.1:8000"
export PYTHONPATH="$ROOT_DIR/backend"

mkdir -p "$LOCAL_STORAGE_PATH"

# Ensure ports 8000 and 3000 are free from stale processes
for port in 8000 3000; do
  stale_pids=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$stale_pids" ]; then
    say "Clearing stale process on port $port (PID: $stale_pids)..."
    kill -9 $stale_pids 2>/dev/null || true
  fi
done

# Cleanup handler on exit or Ctrl+C
cleanup() {
  printf "\n${YELLOW}[start] Stopping native services...${NC}\n"
  if [ -f "$ROOT_DIR/.backend.pid" ]; then
    BPID=$(cat "$ROOT_DIR/.backend.pid")
    pkill -P "$BPID" 2>/dev/null || true
    kill -9 "$BPID" 2>/dev/null || true
    rm -f "$ROOT_DIR/.backend.pid"
  fi
  if [ -f "$ROOT_DIR/.frontend.pid" ]; then
    FPID=$(cat "$ROOT_DIR/.frontend.pid")
    pkill -P "$FPID" 2>/dev/null || true
    kill -9 "$FPID" 2>/dev/null || true
    rm -f "$ROOT_DIR/.frontend.pid"
  fi
  for port in 8000 3000; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  done
  say "All native services stopped cleanly."
  exit 0
}

# 7. Start Backend
say "Starting FastAPI backend on http://127.0.0.1:8000..."
setsid "$VENV_DIR/bin/python" -m uvicorn app.main:app \
  --app-dir "$ROOT_DIR/backend" \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  </dev/null > "$ROOT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$ROOT_DIR/.backend.pid"

# 8. Start Frontend
say "Starting Vite frontend dev server on http://localhost:3000..."
setsid bash -c "cd '$ROOT_DIR/frontend' && VITE_PROXY_TARGET='http://127.0.0.1:8000' npm run dev -- --host 0.0.0.0 --port 3000" \
  </dev/null > "$ROOT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$ROOT_DIR/.frontend.pid"

say "Waiting for services to become available..."
BACKEND_OK=0
FRONTEND_OK=0
for i in $(seq 1 30); do
  if [ $BACKEND_OK -eq 0 ] && curl -sf -o /dev/null http://127.0.0.1:8000/health 2>/dev/null; then
    BACKEND_OK=1
    say "Backend is UP  -> http://localhost:8000 (API docs: http://localhost:8000/docs)"
  fi
  if [ $FRONTEND_OK -eq 0 ] && curl -sf -o /dev/null http://127.0.0.1:3000/ 2>/dev/null; then
    FRONTEND_OK=1
    say "Frontend is UP -> http://localhost:3000"
  fi
  [ $BACKEND_OK -eq 1 ] && [ $FRONTEND_OK -eq 1 ] && break
  sleep 1
done

printf "\n${GREEN}${BOLD}Bhu-Drishti 3D is running!${NC}\n\n"
printf "  ${CYAN}Frontend UI :${NC} http://localhost:3000\n"
printf "  ${CYAN}Backend API :${NC} http://localhost:8000\n"
printf "  ${CYAN}API Docs    :${NC} http://localhost:8000/docs\n"
printf "  ${CYAN}Logs        :${NC} tail -f logs/backend.log logs/frontend.log\n"
printf "  ${CYAN}Stop        :${NC} ./stop.sh\n\n"

if [ $DAEMON_MODE -eq 1 ]; then
  say "Running in daemon mode. PIDs saved to .backend.pid and .frontend.pid."
  exit 0
else
  say "Streaming live logs (Press Ctrl+C to stop)..."
  trap cleanup SIGINT SIGTERM
  tail -f "$ROOT_DIR/logs/backend.log" "$ROOT_DIR/logs/frontend.log" &
  wait
fi