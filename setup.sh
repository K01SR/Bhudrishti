#!/usr/bin/env bash
set -euo pipefail

REPO_URL=""
REPO_DIR="BhuDrishti-3D"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

say()  { printf "${GREEN}[setup]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn ]${NC} %s\n" "$*"; }
fail() { printf "${RED}[error]${NC} %s\n" "$*"; exit 1; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v docker >/dev/null 2>&1 || fail "Docker CLI not found.

Install it first:
  Debian/Ubuntu : sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
  Arch/Manjaro  : sudo pacman -S docker docker-compose
  Fedora        : sudo dnf install -y docker docker-compose
  macOS         : brew install --cask docker
Then add your user to the docker group:  sudo usermod -aG docker \$(whoami)  (log out/in after)."

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  fail "Docker Compose not found — install the compose plugin alongside Docker"
fi

if [ ! -f "$ROOT_DIR/docker-compose.yml" ]; then
  if [ -n "$REPO_URL" ]; then
    say "Project files not found — cloning repository..."
    git clone "$REPO_URL" "$ROOT_DIR/$REPO_DIR"
    cd "$ROOT_DIR/$REPO_DIR"
  else
    fail "No docker-compose.yml here and no REPO_URL set.
Set REPO_URL at the top of this script to auto-download the project,
or run this script from inside the project directory."
  fi
fi

if [ ! -f .env ]; then
  cp .env.example .env
  say "Created .env from .env.example"
fi
mkdir -p data

say "Stack: ${DC[*]}"
say "Pulling base images (PostGIS, Redis)..."
"${DC[@]}" pull || warn "pull skipped/failed for some images (offline?) — build will still run"

say "Building backend + frontend images..."
"${DC[@]}" build

say "Done."
printf "${CYAN}Next:${NC}\n"
printf "  Linux/macOS  : ./start.sh\n"
printf "  Windows (cmd): start.bat\n"
printf "  Open         : http://localhost:3000\n"