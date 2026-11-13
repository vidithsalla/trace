# Local Development

## Prerequisites

- Docker Desktop on Apple Silicon
- Node 22+
- Python 3.12+
- `pnpm`
- `uv`

## Recommended Docker Desktop Settings

- CPUs: `2`
- Memory: `4 GB` or as close as possible without hurting the rest of your machine
- Disk image: leave the default unless Docker reports space pressure

This repo assumes an M1 MacBook Pro with 8 GB RAM may be memory-constrained. The default local stack is intentionally lightweight.

## Startup

1. Copy `.env.example` to `.env`.
   If `.env` already exists from an older setup attempt, refresh it from the latest example or add the new `TRACE_MODEL_*` and `TRACE_OCR_*` variables manually.
2. Run `make phase0-verify`.
3. Run `make up` for the lightweight core stack.
4. API docs: `http://localhost:8000/docs`
5. API readiness: `http://localhost:8000/health/ready`
6. Web shell: `http://localhost:3000`

## Optional Add-ons

- Model endpoint add-on:
  - `make up-model`
- OCR add-on:
  - `make up-ocr`
- Full local topology:
  - `make up-full`

The core stack does not require local model serving or local OCR services.

## Optional Semantic Embeddings

Trace defaults to `TRACE_EMBEDDING_PROVIDER=hash`, which uses deterministic 384-dimensional
hash embeddings. This keeps local development, CI, and the default Docker stack lightweight and
does not download model weights.

To enable true semantic embeddings for local or private deployment experiments:

1. Install the semantic extra in the API and worker environments:
   - `cd apps/api && uv sync --extra semantic`
   - `cd apps/worker && uv sync --extra semantic`
2. Set `TRACE_EMBEDDING_PROVIDER=sentence_transformer` in `.env`.
3. Keep `TRACE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` unless you are testing
   another 384-dimensional model.
4. Re-run `make seed-raw` or re-ingest uploaded documents so stored chunk vectors are generated
   by the selected provider.

`all-MiniLM-L6-v2` is a practical CPU-friendly baseline, not a fine-tuned legal embedding model.
The provider boundary is intentionally pluggable so stronger self-hosted embedding models can be
introduced later without changing routes, schemas, or the pgvector column.

The default Compose images intentionally do not install the semantic extra. If semantic mode is
needed inside containers, build a semantic-enabled image or install the extra in the target runtime
before setting `TRACE_EMBEDDING_PROVIDER=sentence_transformer`.

## Useful Commands

- `make api`
- `make web`
- `make worker`
- `make test`
- `make seed`

## Notes

- The repo standardizes on `docker compose`.
- The default local model provider is a retrieval-derived `MockModelClient`.
- `OpenAICompatibleModelClient` is available for later self-hosted integration and optional local add-on use.
- OCR remains part of the product architecture, but it is not in the default startup path.
- The API container runs Alembic migrations at startup.
- Uploaded files and exports are stored on the `object-data` Docker volume (`TRACE_STORAGE_BACKEND=filesystem`).

## Demo Credentials

Seeded by `python -m app.scripts.seed_demo`:

- `admin@trace.local`
- `attorney@trace.local`
- `reviewer@trace.local`

Default password:

- `trace-demo-password`
