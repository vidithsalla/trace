APP_NAME=Trace - Sovereign Discovery Copilot
COMPOSE_CORE=docker compose -f infra/compose/compose.yaml
COMPOSE_MODEL=docker compose -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml
COMPOSE_OCR=docker compose -f infra/compose/compose.yaml -f infra/compose/compose.ocr.yaml
COMPOSE_FULL=docker compose -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml -f infra/compose/compose.ocr.yaml

.PHONY: up up-model up-ocr up-full down logs api web worker test seed seed-raw eval eval-regression eval-all phase0-verify

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
