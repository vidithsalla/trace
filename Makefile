APP_NAME=Trace
COMPOSE_CORE=docker compose --env-file .env -f infra/compose/compose.yaml
COMPOSE_MODEL=docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml
COMPOSE_OCR=docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.ocr.yaml
COMPOSE_FULL=docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml -f infra/compose/compose.ocr.yaml

API_IMAGE=trace-api

.PHONY: test-docker lint-docker up up-model up-ocr up-full down logs api web worker test seed seed-raw eval eval-regression eval-all phase0-verify

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
