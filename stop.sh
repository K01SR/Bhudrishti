#!/usr/bin/env bash
# ==============================================================================
# Bhu-Drishti 3D: Stop Script
# Shuts down native backend and frontend processes cleanly
# ==============================================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

say()  { printf "${GREEN}[stop]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

STOPPED=0

# 1. Stop backend via PID
if [ -f "$ROOT_DIR/.backend.pid" ]; then
  BPID=$(cat "$ROOT_DIR/.backend.pid")
  if kill -0 "$BPID" 2>/dev/null; then
    say "Stopping backend (PID $BPID)..."
    kill "$BPID" 2>/dev/null || true
    sleep 1
    kill -9 "$BPID" 2>/dev/null || true
    STOPPED=1
  fi
  rm -f "$ROOT_DIR/.backend.pid"
fi

# 2. Stop frontend via PID
if [ -f "$ROOT_DIR/.frontend.pid" ]; then
  FPID=$(cat "$ROOT_DIR/.frontend.pid")
  if kill -0 "$FPID" 2>/dev/null; then
    say "Stopping frontend (PID $FPID)..."
    kill "$FPID" 2>/dev/null || true
    sleep 1
    kill -9 "$FPID" 2>/dev/null || true
    STOPPED=1
  fi
  rm -f "$ROOT_DIR/.frontend.pid"
fi

# 3. Fallback: kill any leftover processes on port 8000 or 3000
for port in 8000 3000; do
  pids=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pids" ]; then
    warn "Freeing leftover process on port $port (PIDs: $pids)..."
    kill -9 $pids 2>/dev/null || true
    STOPPED=1
  fi
done

# 4. Optional: stop backing db services if requested
if [ "${1:-}" = "--docker" ] || [ "${1:-}" = "--all" ] || [ "${1:-}" = "-a" ]; then
  if command -v docker >/dev/null 2>&1; then
    say "Stopping backing database containers..."
    docker compose stop postgres redis >/dev/null 2>&1 || true
  fi
fi

if [ $STOPPED -eq 1 ]; then
  say "Bhu-Drishti 3D services stopped successfully."
else
  say "No active processes found."
fi
