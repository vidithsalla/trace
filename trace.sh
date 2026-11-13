#!/usr/bin/env bash
# Trace control script: start | stop | status | logs | demo | uninstall
# Runs everything in Docker; only the web UI is published, on 127.0.0.1.
set -euo pipefail

cd "$(dirname "$0")"
ENV_FILE=".env"
BASE=(docker compose --env-file "$ENV_FILE" -f infra/compose/compose.yaml)

info() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-; }

compose() {
  local files=("${BASE[@]}")
  if [ "$(env_value TRACE_MODEL_PROVIDER)" = "local" ]; then
    files+=(-f infra/compose/compose.model.yaml)
  fi
  "${files[@]}" "$@"
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install Docker Desktop: https://docs.docker.com/get-docker/"
  docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop and try again."
}

wait_healthy() {
  local port; port="$(env_value TRACE_WEB_PORT)"; port="${port:-3000}"
  info "Waiting for Trace to become ready on http://127.0.0.1:${port} ..."
  for _ in $(seq 1 90); do
    if curl -fsS "http://127.0.0.1:${port}/sign-in" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  die "Trace did not become ready. Check: ./trace.sh logs"
}

check_model() {
  if [ "$(env_value TRACE_MODEL_PROVIDER)" != "local" ]; then
    return 0
  fi
  if ! curl -fsS "http://127.0.0.1:11434/api/version" >/dev/null 2>&1; then
    warn "Local model server not reachable on 127.0.0.1:11434."
    warn "Start it in another terminal with:  ollama serve"
    warn "Trace will start, but investigations will fail with 'model server not reachable' until then."
  fi
}

cmd_start() {
  require_docker
  [ -f "$ENV_FILE" ] || die "No .env found. Run ./install.sh first."
  check_model
  info "Starting Trace (first start builds images; this can take a few minutes) ..."
  compose up -d --build
  wait_healthy
  local port; port="$(env_value TRACE_WEB_PORT)"; port="${port:-3000}"
  info "Trace is running: http://127.0.0.1:${port}"
  echo "Sign in with attorney@trace.local / trace-demo-password (or reviewer@trace.local)."
}

cmd_demo() {
  require_docker
  compose exec -T api uv run python -m app.scripts.seed_demo --mode fast
  compose exec -T api uv run python -m app.scripts.seed_v3_demo
  info "Demo matters ready: 'Halden Freight invoice dispute' (V3 review) and 'Acme Industrial v. Northshore Supply'."
}

case "${1:-}" in
  start) cmd_start ;;
  stop) require_docker; compose stop; info "Trace stopped. Your data is kept." ;;
  status) require_docker; compose ps ;;
  logs) require_docker; compose logs --tail=200 -f ;;
  demo) cmd_demo ;;
  uninstall)
    require_docker
    read -r -p "This deletes Trace's containers AND its data volumes (documents, database). Type 'delete' to confirm: " answer
    [ "$answer" = "delete" ] || die "Cancelled."
    compose down --volumes --remove-orphans
    info "Removed containers and data volumes. The project folder and .env are untouched."
    ;;
  *)
    echo "Usage: ./trace.sh {start|stop|status|logs|demo|uninstall}"
    exit 1
    ;;
esac
