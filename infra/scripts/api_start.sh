#!/bin/sh
set -eu

cd /app

export PYTHONPATH=/app

uv run alembic upgrade head
uv run python -m app.scripts.backfill_versions
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
