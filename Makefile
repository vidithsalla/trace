APP_NAME=Trace
COMPOSE_CORE=docker compose --env-file .env -f infra/compose/compose.yaml
COMPOSE_MODEL=docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml
COMPOSE_OCR=docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.ocr.yaml
COMPOSE_FULL=docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml -f infra/compose/compose.ocr.yaml

.DEFAULT_GOAL := up
API_IMAGE=trace-api
GIT_SHA:=$(shell git describe --always --dirty 2>/dev/null || echo unknown)

# Typecheck/build the web app from the working tree with the image's locked node_modules.
WEB_SRC=-v "$(CURDIR)/apps/web/app:/app/apps/web/app" -v "$(CURDIR)/apps/web/components:/app/apps/web/components" \
  -v "$(CURDIR)/apps/web/lib:/app/apps/web/lib" -v "$(CURDIR)/apps/web/next.config.ts:/app/apps/web/next.config.ts:ro"
web-check:
	docker run --rm --user root $(WEB_SRC) -e NEXT_TELEMETRY_DISABLED=1 trace-web sh -c "pnpm typecheck && pnpm build"

# V3 evals. Example: make eval-v3 ARGS="--engines mock,local --profiles all"
eval-v3:
	docker run --rm --network trace_default --env-file .env -e PYTHONPATH=/app \
	  -e TRACE_CODE_COMMIT=$(GIT_SHA) --add-host host.docker.internal:host-gateway \
	  -v "$(CURDIR)/apps/api/app:/app/app" -v "$(CURDIR)/evals:/app/evals" \
	  -v trace_object-data:/data/objects $(API_IMAGE) uv run python -m app.scripts.eval_v3 $(ARGS)

.PHONY: eval-v3 test-docker lint-docker test-real-model up up-model up-ocr up-full down logs api web worker test seed seed-raw eval eval-regression eval-all phase0-verify

up:
	$(COMPOSE_CORE) up --build

up-model:
	$(COMPOSE_MODEL) up --build

up-ocr:
	$(COMPOSE_OCR) up --build

up-full:
	$(COMPOSE_FULL) up --build

down:
	$(COMPOSE_FULL) down --remove-orphans

logs:
	$(COMPOSE_CORE) logs -f

api:
	cd apps/api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd apps/web && pnpm dev

worker:
	cd apps/worker && python -m worker.main

test:
	cd apps/api && pytest

seed:
	cd apps/api && python -m app.scripts.seed_demo --mode fast

seed-raw:
	cd apps/api && python -m app.scripts.seed_demo --mode raw

eval:
	cd apps/api && python -m app.scripts.eval_seed

eval-regression:
	cd apps/api && python -m app.scripts.eval_seed --suite regression

eval-all:
	cd apps/api && python -m app.scripts.eval_seed --suite all

phase0-verify:
	python3 infra/scripts/phase0_verify.py

# Run API tests/lint against the working tree inside the API image (stack must be up).
test-docker:
	docker run --rm --network trace_default --env-file .env -e PYTHONPATH=/app \
	  -v "$(CURDIR)/apps/api/app:/app/app" -v "$(CURDIR)/apps/api/alembic:/app/alembic" \
	  -v "$(CURDIR)/apps/api/pyproject.toml:/app/pyproject.toml:ro" \
	  -v trace_object-data:/data/objects $(API_IMAGE) \
	  sh -c "uv run alembic upgrade head >/dev/null && uv run pytest -q -p no:warnings $(ARGS)"

lint-docker:
	docker run --rm -v "$(CURDIR)/apps/api:/w" -w /w $(API_IMAGE) /app/.venv/bin/ruff check app

# Opt-in: run real-model tests against a local Ollama (`ollama serve` on the host).
test-real-model:
	docker run --rm --network trace_default --env-file .env -e PYTHONPATH=/app \
	  -e TRACE_REAL_MODEL_TESTS=1 -e TRACE_MODEL_PROVIDER=local --add-host host.docker.internal:host-gateway \
	  -v "$(CURDIR)/apps/api/app:/app/app" -v "$(CURDIR)/apps/api/pyproject.toml:/app/pyproject.toml:ro" \
	  $(API_IMAGE) sh -c "uv run pytest -q -p no:warnings -m real_model -s $(ARGS)"
