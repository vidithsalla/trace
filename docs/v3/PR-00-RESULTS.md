# PR-00 baseline and CI: results

Recorded 2026-11-13 on macOS (Apple Silicon), Docker Desktop, from a fresh clone of `81ce7cc`.

## Observed on the unmodified baseline

| Check | Result |
| --- | --- |
| `docker compose up` | **Failed.** `minio/mc` and `minio/minio` no longer exist on Docker Hub or quay.io. |
| Host ports | Postgres/Redis/MinIO/API/web published on `0.0.0.0` (reachable from the LAN). |
| Lockfiles | None. Docker builds fell back to unpinned `uv sync` / `pnpm install --no-frozen-lockfile`. |
| Web dependencies | `next@15.2.0`, `react@19.0.0`: versions with published critical advisories. |
| `ruff check` | 116 findings under ruff 0.17's default rules (previous runs used an older default set). |

## Changes

- Object storage: MinIO replaced by a filesystem backend on a shared Docker volume (atomic writes,
  storage-key validation against path traversal). S3-compatible backend kept as opt-in.
- All published ports bound to `127.0.0.1`; host ports configurable (`TRACE_POSTGRES_HOST_PORT` etc.).
- Lockfiles added (`apps/api/uv.lock`, `apps/worker/uv.lock`, `pnpm-lock.yaml`); Docker builds use
  `--frozen` / `--frozen-lockfile`; `uv` pinned.
- `next@15.5.29`, `react@19.1.10`, `react-dom@19.1.10`; `typedRoutes` moved out of `experimental`.
- Startup guard: API refuses to run outside `development`/`test` with the placeholder secret key or
  demo login enabled.
- Explicit ruff rule set; import order fixed; three `zip()` calls made strict.
- GitHub Actions CI: API lint + migrations + pytest against Postgres/pgvector and Redis; web
  typecheck + production build. No model credentials required.
- `docs/KNOWN_LIMITATIONS.md`, `evals/` layout and the `conditional-payment-v1` fixture.

## Verified after changes (local, Docker)

| Command | Result |
| --- | --- |
| `make up` (core stack) | api, worker, web, postgres, redis healthy; `/health/ready` all `ok` |
| `make test-docker` | `66 passed` (56 existing + 10 new) |
| `make lint-docker` | `All checks passed!` |
| `pnpm typecheck` (web container) | passed |
| `next build` (throwaway web container) | passed |
| `GET /`, `GET /matters` | 200 |

CI result on GitHub: see the Actions run for this commit.

## Next boundary

PR-01: real OpenAI-compatible model client (local Ollama by default, hosted optional), no mock
fallback, typed claim schema, evidence-reference allowlist.
