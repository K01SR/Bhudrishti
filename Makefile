SHELL := /bin/bash

.PHONY: help up down restart logs build migrate seed test test-container test-isolated test-native smoke \
        verify-docs frontend-install frontend-build reset-db clean \
        dev-up dev-down dev-logs dev-rebuild dev-deps

help:
	@echo "Bhu-Drishti 3D — Management Commands:"
	@echo "  make up              - Start all docker services (postgres, redis, minio, backend, worker, frontend)"
	@echo "  make down            - Stop all docker services"
	@echo "  make build           - Rebuild all containers"
	@echo "  make logs            - Tail container logs"
	@echo "  make dev-up          - Start the DEV stack (uvicorn --reload, celery watchfiles, Vite HMR)"
	@echo "  make dev-down        - Stop the DEV stack (keeps named volumes, incl. postgres_data)"
	@echo "  make dev-logs        - Tail DEV stack logs"
	@echo "  make dev-rebuild     - Rebuild DEV images and restart the DEV stack"
	@echo "  make dev-deps        - Reinstall frontend node_modules in the DEV container after a lockfile change"
	@echo "  make migrate         - Run database migrations"
	@echo "  make seed            - Seed synthetic Airoli demo dataset (Building B-17, parcels, evidence, accounts)"
	@echo "  make test            - Run the self-contained suite via ./scripts/run-tests.sh"
	@echo "  make test-container  - Run test suite in the backend container (needs a live stack; source-gate tests error)"
	@echo "  make test-isolated   - Run the full suite self-contained (PostGIS+Redis+fixtures, no live stack)"
	@echo "  make test-native     - Run test suite against the native (local) backend stack"
	@echo "  make smoke           - Boot native backend and run live API smoke checks"
	@echo "  make verify-docs     - Run the documentation verification engine (docs <-> code drift check)"
	@echo "  make frontend-build  - Typecheck + production-build the frontend bundle"
	@echo "  make reset-db        - Wipe and re-seed database to pristine hero demo state"

# Default native stack (docker compose is NOT used at runtime by default; see ENVIRONMENT=development)
PY ?= ./backend/.venv/bin/python
PIP ?= ./backend/.venv/bin/pip
PYTEST ?= ./backend/.venv/bin/pytest

NATIVE_TEST_ENV = POSTGRES_SERVER=127.0.0.1 POSTGRES_PORT=5432 \
	POSTGRES_USER=bhudrishti POSTGRES_PASSWORD=bhudrishti_secure_spatial_2026 \
	POSTGRES_DB=bhudrishti_3d REDIS_HOST=127.0.0.1 REDIS_PORT=6379

export POSTGRES_SERVER := 127.0.0.1
export POSTGRES_PORT := 5432
export POSTGRES_USER := bhudrishti
export POSTGRES_PASSWORD := bhudrishti_secure_spatial_2026
export POSTGRES_DB := bhudrishti_3d
export REDIS_HOST := 127.0.0.1
export REDIS_PORT := 6379

# Base + dev overlay. Every dev target uses both files in this order.
DEV_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

build:
	docker compose build

dev-up:
	$(DEV_COMPOSE) up -d --build --wait --wait-timeout 180

dev-down:
	$(DEV_COMPOSE) down

dev-logs:
	$(DEV_COMPOSE) logs -f

dev-rebuild:
	$(DEV_COMPOSE) build
	$(DEV_COMPOSE) up -d --wait --wait-timeout 180

# The named frontend_dev_node_modules volume is seeded from the image, so a
# package-lock change needs an explicit reinstall inside the running container.
dev-deps:
	$(DEV_COMPOSE) exec frontend npm ci

migrate:
	docker compose exec backend alembic upgrade head

seed:
	PYTHONPATH=backend $(PY) -m app.cli.seed_demo

seed-docker:
	docker compose exec backend python -m app.cli.seed_demo

# Self-contained: brings up throwaway PostGIS + Redis, creates the schema and
# fixtures, runs the suite, tears everything down. No local venv required.
test:
	./scripts/run-tests.sh

test-isolated:
	./scripts/run-tests.sh

# Needs a running stack. The backend image ships the compiled bundle, not
# frontend/src, so the source-gate tests in tests/ cannot read the files they
# assert on and will error.
test-container:
	docker compose exec backend pytest -v

# Native parity CI: run the exact suite GitHub Actions executes (with services live)
test-native:
	PYTHONPATH=backend $(PYTEST) tests/ -v --tb=short

# Live HTTP smoke: lift the real uvicorn server, probe health + regression endpoints
smoke:
	PYTHONPATH=backend $(PY) -m uvicorn app.main:app \
		--app-dir backend --host 127.0.0.1 --port 8000 & \
	sleep 4; \
	curl -fsS http://127.0.0.1:8000/health && echo "OK: health"; \
	curl -fsS -o /dev/null -w "property-card: %{http_code}\n" \
		http://127.0.0.1:8000/api/v1/exports/pdf/property-card/3D-ULPIN-NZIUOTK4MJZFMT; \
	kill %1 2>/dev/null || true

verify-docs:
	$(PY) scripts/verify-docs.py

frontend-install:
	cd frontend && npm ci

frontend-build:
	cd frontend && npm run build

reset-db:
	docker compose down -v

reset-db-docker:
	docker compose exec backend python -m app.cli.reset_demo

clean:
	docker compose down -v