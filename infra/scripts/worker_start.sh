#!/bin/sh
set -eu

cd /app
export PYTHONPATH=/app

uv run dramatiq worker.tasks --processes 1 --threads 2
