#!/usr/bin/env bash
# First-time setup for Trace on macOS or Linux.
#
#   ./install.sh            local model via Ollama if available (recommended)
#   ./install.sh --mock     deterministic mock model, no model download (for a quick look)
#
# What this does: checks Docker, writes a .env with freshly generated secrets, optionally pulls
# two Ollama models, builds and starts the containers, and loads synthetic demo data.
# It does not install system packages, change shell profiles, or register background services.
set -euo pipefail

cd "$(dirname "$0")"
MODEL_MODE="auto"
for arg in "$@"; do
  case "$arg" in
    --mock) MODEL_MODE="mock" ;;
    --local) MODEL_MODE="local" ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

info() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

LLM_MODEL="qwen2.5:7b-instruct"
EMBED_MODEL="all-minilm:l6-v2"

# --- 1. Docker ---------------------------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "Docker is required. Install Docker Desktop: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop, then rerun ./install.sh"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (included with Docker Desktop)."

# --- 2. Configuration --------------------------------------------------------------------------
random_hex() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$1"; else head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; fi
}
set_env() { # set_env KEY VALUE (replace or append, no other edits)
  if grep -qE "^$1=" .env; then
    local tmp; tmp="$(mktemp)"; awk -v k="$1" -v v="$2" -F= 'BEGIN{OFS="="} $1==k{$0=k"="v} {print}' .env > "$tmp" && mv "$tmp" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

if [ ! -f .env ]; then
  cp .env.example .env
  set_env TRACE_SECRET_KEY "$(random_hex 32)"
  set_env TRACE_POSTGRES_PASSWORD "$(random_hex 16)"
  chmod 600 .env
  info "Created .env with generated secrets (kept local; never committed)."
else
  info "Using existing .env."
fi

# Pick a free port for the web UI if 3000 is taken.
port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
WEB_PORT="$(grep -E '^TRACE_WEB_PORT=' .env | cut -d= -f2)"; WEB_PORT="${WEB_PORT:-3000}"
# The port is fine if it is held by this install's own web container (re-running the installer).
own_web="$(docker ps -q --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME:-trace}" \
  --filter "label=com.docker.compose.service=web")"
if [ -z "$own_web" ] && ! port_free "$WEB_PORT"; then
  for candidate in 3300 3333 3456 3999; do
    if port_free "$candidate"; then WEB_PORT="$candidate"; break; fi
  done
  set_env TRACE_WEB_PORT "$WEB_PORT"
  set_env TRACE_CORS_ORIGINS "http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}"
  info "Port 3000 is busy; using ${WEB_PORT}."
fi

# --- 3. Model ----------------------------------------------------------------------------------
ollama_up() { curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; }
if [ "$MODEL_MODE" = "auto" ]; then
  if command -v ollama >/dev/null 2>&1 || ollama_up; then MODEL_MODE="local"; else MODEL_MODE="mock"; fi
fi

if [ "$MODEL_MODE" = "local" ]; then
  command -v ollama >/dev/null 2>&1 || die "Ollama not found. Install it from https://ollama.com/download (or 'brew install ollama'), or rerun with --mock."
  if ! ollama_up; then
    die "Ollama is installed but not running. Start it in another terminal with 'ollama serve', then rerun ./install.sh"
  fi
  info "Pulling local models (about 4.8 GB the first time) ..."
  ollama pull "$LLM_MODEL"
  ollama pull "$EMBED_MODEL"
  set_env TRACE_MODEL_PROVIDER local
  set_env TRACE_MODEL_NAME "$LLM_MODEL"
  info "Using local model ${LLM_MODEL}. Documents never leave this machine."
else
  set_env TRACE_MODEL_PROVIDER mock
  warn "Using the deterministic mock model (labeled as such in the UI). Install Ollama and rerun ./install.sh for real local inference."
fi

# --- 4. Start and seed -------------------------------------------------------------------------
./trace.sh start
./trace.sh demo
info "Done. Open http://127.0.0.1:${WEB_PORT}  ·  Stop with ./trace.sh stop  ·  Logs with ./trace.sh logs"
