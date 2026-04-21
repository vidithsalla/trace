# Trace - Sovereign Discovery Copilot Roadmap

## Product Identity and Naming Rules

Trace is the product name used in product-facing UI, short references, and day-to-day implementation language.

Trace - Sovereign Discovery Copilot is the formal product name used in primary documentation headings, deployment materials, login/header surfaces, and formal architecture references.

Do not introduce a competing product name. If older documents use the bare name Sovereign Discovery Copilot, future product-facing implementation should prefer Trace, while formal docs may use Trace - Sovereign Discovery Copilot.

## Source-of-Truth Precedence

This roadmap is the reconciled public execution layer for the MVP and follow-on implementation path. It reflects the latest 0-13 execution plan layered on top of the public schema, architecture, local development, and pre-build decision documents. Local/internal PRD and build-guide references may exist outside the public repo, but they are not required to understand or run this repository.

When implementation details conflict, use this precedence:

1. `docs/pre_build_decisions.md`
2. `docs/schema_and_seeds.md`
3. `ROADMAP.md` as the current phase-by-phase execution layer
4. `docs/architecture.md`
5. `docs/local_dev.md`

If a future implementation discovers a contradiction between this roadmap and the higher-precedence docs, update the roadmap explicitly instead of silently drifting.

## Local Development Topology

The default local path is intentionally lightweight for a MacBook Pro M1 with 8 GB RAM and Docker Desktop memory constraints.

Default `make up` core stack:

- `web`
- `api`
- `worker`
- `postgres`
- `redis`
- `minio`

Optional local add-ons:

- `make up-model` starts the model overlay using `infra/compose/compose.model.yaml`.
- `make up-ocr` starts the OCR overlay using `infra/compose/compose.ocr.yaml`.
- `make up-full` starts core plus both optional overlays.

Model and OCR services are product-critical, but they must not be required for day-one local development. Local workflows default to `MockModelClient`. Production and private deployment remain aligned with a self-hosted OpenAI-compatible model endpoint, expected to be vLLM-backed. OCR must be implemented behind an `OCRService` abstraction before any heavy OCR container becomes required.

## Global Engineering Invariants

- Matter isolation is mandatory in API routes, worker jobs, retrieval, AI workflows, citations, exports, and audit logs.
- Every AI request must require an explicit `matter_id`.
- Every retrievable chunk, entity, event, memo, citation, export, and AI run must belong to exactly one matter.
- Evidence comes before prose: store structured workflow output first, then render markdown, tables, summaries, or exports.
- Citations must resolve to matter-scoped source material and should include document, page, chunk, and quote context whenever available.
- Grounded factual answers must be conservative. If evidence is weak or citations fail validation, return low confidence or insufficient evidence.
- Do not add external SaaS model dependencies to the production target. Production inference must remain private and self-hostable.
- Do not add a separate vector database for MVP unless pgvector becomes a documented blocker.
- Do not implement cross-matter search, cross-matter entity linking, chain-of-thought storage, full enterprise antivirus, SSO/SAML, PST/OST ingestion, redaction, or collaborative annotation in MVP.
- The canonical MVP truth source is the Acme Industrial v. Northshore Supply seeded matter.

## Phase Status Legend

- Verified: implemented and smoke-checked in the current repo.
- Planned: not yet complete; implement in the listed order.
- Deferred: explicitly out of MVP or post-MVP unless elevated by a later decision.

## Public APIs to Preserve

The roadmap assumes this external API surface. Do not rename or remove these routes without updating all docs, UI clients, and tests.

- `POST /auth/login`
- `POST /auth/logout`
- `GET /me`
- `GET /matters`
- `POST /matters`
- `PATCH /matters/{matter_id}`
- `POST /matters/{matter_id}/documents/upload`
- `GET /matters/{matter_id}/documents`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/pages/{page_number}`
- `POST /matters/{matter_id}/search`
- `POST /matters/{matter_id}/ask`
- `POST /matters/{matter_id}/chronology`
- `POST /matters/{matter_id}/entities/extract`
- `GET /matters/{matter_id}/entities`
- `GET /entities/{entity_id}`
- `POST /matters/{matter_id}/contradictions`
- `POST /matters/{matter_id}/memos`
- `GET /memos/{memo_id}`
- `GET /audit`
- `GET /ai-runs/{run_id}`
- `GET /exports/{export_id}`

## Internal Contracts to Preserve

Define or harden these contracts before adding business logic that depends on them:

- `DocumentParser`
- `OCRService`
- `EmbeddingClient`
- `Retriever`
- `Reranker`
- `ModelClient`
- `CitationValidator`
- `WorkflowRunner`
- `Exporter`
- `SeedLoader`
- `EvalRunner`

AI workflow contracts must have typed input schemas, typed output schemas, prompt templates, validation, persistence, and audit coverage:

- `grounded_qa_v1`
- `chronology_builder_v1`
- `entity_summary_v1`
- `contradiction_finder_v1`
- `issue_memo_v1`
- `citation_check_v1`

## Phase 0 - Repo and Local Platform

Status: Verified

Last tracked: 2026-04-17

### Completion Tracker

#### Feature Completion

- [x] Monorepo structure exists with `apps/web`, `apps/api`, `apps/worker`, `packages/ui`, `packages/types`, `services`, `infra`, `docs`, and `seed_truth`.
- [x] Lightweight default Docker Compose core stack exists in `infra/compose/compose.yaml`.
- [x] Core stack is limited to `web`, `api`, `worker`, `postgres`, `redis`, `minio`, and `minio-init`.
- [x] Optional model overlay exists in `infra/compose/compose.model.yaml`.
- [x] Optional OCR overlay exists in `infra/compose/compose.ocr.yaml`.
- [x] Root `Makefile` exposes `up`, `up-model`, `up-ocr`, `up-full`, `down`, `logs`, `test`, `seed`, and `phase0-verify`.
- [x] `.env.example` exists with Trace, database, Redis, MinIO, model, and OCR defaults.
- [x] Local `.env` exists for current development.
- [x] FastAPI app exposes health and readiness behavior.
- [x] Next.js app renders Trace-branded shell text.
- [x] Dramatiq worker service exists and starts through `infra/scripts/worker_start.sh`.
- [x] Postgres uses `pgvector/pgvector:pg16`.
- [x] Redis uses `redis:7-alpine`.
- [x] MinIO object storage exists with `minio-init` bucket initialization.
- [x] Alembic migration foundation exists.
- [x] Initial migration creates the `vector` extension before vector columns.
- [x] `ModelClient` abstraction exists.
- [x] `MockModelClient` exists and remains the local default provider.
- [x] `OpenAICompatibleModelClient` exists for future self-hosted vLLM integration.

#### Implementation Step Tracking

- [x] Step 0.1: Default compose file is limited to core services only.
- [x] Step 0.2: `compose.model.yaml` is an explicit optional model overlay.
- [x] Step 0.3: `compose.ocr.yaml` is an explicit optional OCR overlay.
- [x] Step 0.4: `make up` does not start `vllm`, OCR, or other heavy services.
- [x] Step 0.5: `make up-model`, `make up-ocr`, and `make up-full` are explicit opt-in paths.
- [x] Step 0.6: API startup runs migrations before serving through `infra/scripts/api_start.sh`.
- [x] Step 0.7: Worker startup uses `uv` and `PYTHONPATH=/app` through `infra/scripts/worker_start.sh`.
- [x] Step 0.8: Migration is pgvector-safe through `CREATE EXTENSION IF NOT EXISTS vector`.
- [x] Step 0.9: App metadata and visible shell text use Trace and Trace - Sovereign Discovery Copilot.
- [x] Step 0.10: Local docs explain that model serving and OCR are optional locally but required architecture targets.

#### Test and Verification Tracking

- [x] `docker compose -f infra/compose/compose.yaml config --quiet` passed.
- [x] `docker compose -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml config --quiet` passed.
- [x] `docker compose -f infra/compose/compose.yaml -f infra/compose/compose.ocr.yaml config --quiet` passed.
- [x] `python3 infra/scripts/phase0_verify.py` passed.
- [x] `python3 -m compileall apps/api/app apps/worker/worker infra/scripts` passed.
- [x] Live core stack status checked with `docker compose -f infra/compose/compose.yaml ps`.
- [x] Live status on 2026-04-17: `api`, `postgres`, `redis`, `web`, and `worker` are healthy; `minio` is up.
- [x] API readiness returned `database`, `redis`, and `object_storage` as `ok`.
- [x] Web internal health probe returned `web-ok`.
- [x] Worker internal import probe returned `worker-ok`.

#### Checkpoint Tracking

- [x] Checkpoint 0.1: Repo shape exists.
- [x] Checkpoint 0.2: Core compose stack builds.
- [x] Checkpoint 0.3: Core compose stack starts.
- [x] Checkpoint 0.4: API readiness is green.
- [x] Checkpoint 0.5: Web and worker are healthy.
- [x] Checkpoint 0.6: Optional model and OCR overlays validate.

#### Phase 0 Exit Gate Tracking

- [x] Exit gate met: `make up` boots the lightweight core stack and the app can be accessed without local model serving or OCR containers.

#### Evidence Paths

- `infra/compose/compose.yaml`
- `infra/compose/compose.model.yaml`
- `infra/compose/compose.ocr.yaml`
- `infra/scripts/phase0_verify.py`
- `infra/scripts/api_start.sh`
- `infra/scripts/worker_start.sh`
- `apps/api/alembic/versions/0001_initial.py`
- `apps/api/app/services/model_client.py`
- `apps/api/app/services/mock_model_client.py`
- `apps/api/app/services/openai_compatible_model_client.py`
- `README.md`
- `docs/local_dev.md`
- `docs/architecture.md`

### Goal

Provide a stable, lightweight monorepo foundation that boots locally without requiring local vLLM, Gemma, OCR workers, or other memory-heavy services.

### Feature List

- Monorepo structure with `apps/web`, `apps/api`, `apps/worker`, `packages/ui`, `packages/types`, `services`, `infra`, `docs`, and `seed_truth`.
- Lightweight default Docker Compose core stack.
- Optional split compose overlays for model and OCR add-ons.
- Root `Makefile` for common development commands.
- `.env.example` and local `.env` support.
- FastAPI health and readiness endpoints.
- Next.js Trace-branded shell.
- Dramatiq worker service.
- Postgres 16 with pgvector.
- Redis 7.
- MinIO object storage with bucket initialization.
- Alembic migration foundation.
- Model abstraction with mock local provider and OpenAI-compatible adapter.

### Implementation Steps

1. Keep the default compose file limited to `web`, `api`, `worker`, `postgres`, `redis`, `minio`, and `minio-init`.
2. Keep `infra/compose/compose.model.yaml` as an explicit optional model overlay.
3. Keep `infra/compose/compose.ocr.yaml` as an explicit optional OCR overlay.
4. Ensure `make up` never starts `vllm`, OCR, or other heavy services.
5. Ensure `make up-model`, `make up-ocr`, and `make up-full` remain explicit opt-in paths.
6. Keep API startup responsible for running migrations before serving.
7. Keep worker startup simple and import-safe through the `uv` environment.
8. Keep the initial migration compatible with pgvector by creating the `vector` extension before vector columns.
9. Keep app metadata and visible shell text branded as Trace and Trace - Sovereign Discovery Copilot.
10. Keep local docs clear that model serving and OCR are optional locally but required architecture targets.

### Expected Behavior When Complete

- A developer can run the core stack on Docker Desktop without running local model serving or heavy OCR.
- API health reports app identity and readiness for database, Redis, and object storage.
- Web renders the Trace shell.
- Worker starts and can import its task module.
- MinIO bucket initialization succeeds.
- Optional compose overlays validate but are not used by default.

### Test Criteria

- `docker compose -f infra/compose/compose.yaml config --quiet` passes.
- `docker compose -f infra/compose/compose.yaml -f infra/compose/compose.model.yaml config --quiet` passes.
- `docker compose -f infra/compose/compose.yaml -f infra/compose/compose.ocr.yaml config --quiet` passes.
- `python3 infra/scripts/phase0_verify.py` passes.
- `python3 -m compileall apps/api/app apps/worker/worker infra/scripts` passes.
- API readiness returns `database`, `redis`, and `object_storage` checks as `ok`.
- Web internal health probe succeeds.
- Worker internal import probe succeeds.

### Checkpoints

- Checkpoint 0.1: Repo shape exists.
- Checkpoint 0.2: Core compose stack builds.
- Checkpoint 0.3: Core compose stack starts.
- Checkpoint 0.4: API readiness is green.
- Checkpoint 0.5: Web and worker are healthy.
- Checkpoint 0.6: Optional model and OCR overlays validate.

### Exit Gate

Phase 0 is complete when `make up` boots the lightweight core stack and the app can be accessed without local model serving or OCR containers.

### Known Dependencies

- Docker Desktop on Apple Silicon.
- `pnpm` for JavaScript workspace tooling.
- `uv` for Python dependency management.
- Postgres image with pgvector support.

## Phase 1 - Auth, Organizations, Matters, and RBAC

Status: Verified

Last tracked: 2026-04-17

### Completion Tracker

#### Feature Completion

- [x] Organizations, users, matters, matter members, and audit logs are represented in the domain model.
- [x] Password authentication uses Argon2 hashing and verification.
- [x] API-owned session cookie flow exists for login, logout, and `/me`.
- [x] Next.js `/api` proxy routes exist for auth and matter flows.
- [x] `POST /auth/login` validates credentials, creates a session cookie, updates `last_login_at`, and audits success.
- [x] `POST /auth/login` audits failed attempts for known users.
- [x] `POST /auth/logout` clears the session cookie and audits logout for valid sessions.
- [x] `GET /me` returns the authenticated user.
- [x] `GET /matters` returns only matters where the current user has membership.
- [x] `POST /matters` creates a matter and adds the creator as `admin`.
- [x] `GET /matters/{matter_id}` requires matter membership.
- [x] `PATCH /matters/{matter_id}` requires an allowed write role.
- [x] Matter access helpers enforce organization boundary plus membership.
- [x] Seed script creates demo org, admin, attorney, reviewer, Acme matter, and memberships.
- [x] Sign-in UI posts to the real auth proxy.
- [x] Matter list UI loads real matter data from the API proxy.
- [x] Create matter UI posts to the real matter proxy.
- [x] Existing matter workspace routes provide the Phase 1 dashboard shell for opened matters.

#### Implementation Step Tracking

- [x] Step 1.1: Models and migration foundation cover Phase 1 tables.
- [x] Step 1.2: Argon2 password hashing and verification are active.
- [x] Step 1.3: Login creates session, updates `last_login_at`, and audits success/failure.
- [x] Step 1.4: Logout clears session and audits valid-session logout.
- [x] Step 1.5: `/me` returns authenticated user context.
- [x] Step 1.6: Matter list is membership-scoped.
- [x] Step 1.7: Matter creation adds creator as `admin`.
- [x] Step 1.8: Matter patch supports allowed metadata updates.
- [x] Step 1.9: Reusable matter access and role helpers exist.
- [x] Step 1.10: Service-layer guards protect implemented matter-dependent routes.
- [x] Step 1.11: Seed org and users exist through `app.scripts.seed_demo`.
- [x] Step 1.12: Sign-in, matter list, create matter, and matter workspace shell are wired.
- [x] Step 1.13: UI keeps Trace and Trace - Sovereign Discovery Copilot branding.
- [x] Step 1.14: Audit records cover login, login failure, logout, matter create, and matter update.

#### Test and Verification Tracking

- [x] `python3 -m compileall apps/api/app apps/worker/worker infra/scripts` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with 5 tests.
- [x] `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.seed_demo` passed.
- [x] Seeded attorney live smoke: `POST /auth/login` returned 200.
- [x] Seeded attorney live smoke: `GET /me` returned `attorney@trace.local`.
- [x] Seeded attorney live smoke: `GET /matters` returned an authorized matter list.
- [x] Seeded attorney live smoke: `POST /matters` created a matter.
- [x] Seeded attorney live smoke: `GET /matters/{matter_id}` opened the created matter.
- [x] Temporary live-smoke matter was removed after verification.
- [x] Live core stack status checked after Phase 1 changes.
- [x] Live status on 2026-04-17: `api`, `postgres`, `redis`, `web`, and `worker` are healthy; `minio` is up.

#### Checkpoint Tracking

- [x] Checkpoint 1.1: Auth data model and migration foundation verified.
- [x] Checkpoint 1.2: Session cookie lifecycle works through API and web proxy.
- [x] Checkpoint 1.3: Seed users can authenticate.
- [x] Checkpoint 1.4: Matter membership guard is reusable and covered by tests.
- [x] Checkpoint 1.5: Matter UI works end to end for list and creation.
- [x] Checkpoint 1.6: Audit logs capture Phase 1 security actions.

#### Phase 1 Exit Gate Tracking

- [x] Exit gate met: a seeded attorney can sign in, create or open a matter, and server-side RBAC blocks unauthorized access consistently across implemented routes.

#### Evidence Paths

- `apps/api/app/api/routes/auth.py`
- `apps/api/app/api/routes/matters.py`
- `apps/api/app/core/deps.py`
- `apps/api/app/services/auth.py`
- `apps/api/app/services/matter.py`
- `apps/api/app/schemas/auth.py`
- `apps/api/app/schemas/matter.py`
- `apps/api/app/scripts/seed_demo.py`
- `apps/api/app/tests/test_phase1_auth_matters.py`
- `apps/web/app/api/auth/login/route.ts`
- `apps/web/app/api/auth/logout/route.ts`
- `apps/web/app/api/me/route.ts`
- `apps/web/app/api/matters/route.ts`
- `apps/web/app/api/matters/[matterId]/route.ts`
- `apps/web/components/sign-in-form.tsx`
- `apps/web/components/matter-list.tsx`
- `apps/web/components/matter-create-form.tsx`
- `apps/web/app/(auth)/sign-in/page.tsx`
- `apps/web/app/matters/page.tsx`
- `apps/web/app/matters/new/page.tsx`
- `apps/api/pyproject.toml`

### Goal

Implement secure organization and matter-scoped access so every later workflow has a reliable authorization boundary.

### Feature List

- Organizations.
- Users.
- Password authentication with Argon2 hashing.
- API-owned session cookies behind the Next.js `/api` proxy path.
- Login, logout, and current-user flows.
- Matters.
- Matter membership.
- Matter-scoped roles: `admin`, `attorney`, `reviewer`, `read_only`.
- Authorization helpers for route handlers and services.
- Audit logs for security-relevant actions.
- Seed organization and users.
- Sign-in UI.
- Matter list UI.
- Create matter UI.
- Matter dashboard shell.

### Implementation Steps

1. Confirm models and migrations cover `organizations`, `users`, `matters`, `matter_members`, and `audit_logs`.
2. Harden password hashing with Argon2 and constant-time verification behavior.
3. Implement `POST /auth/login` to validate credentials, create a secure session, update `last_login_at`, and audit success or failure.
4. Implement `POST /auth/logout` to clear the active session cookie and audit logout.
5. Implement `GET /me` to return the current user, organization, and accessible role context.
6. Implement `GET /matters` to return only matters where the user has membership.
7. Implement `POST /matters` to create a matter and automatically add the creator as a matter admin or attorney.
8. Implement `PATCH /matters/{matter_id}` for allowed matter metadata updates.
9. Add reusable API dependencies for current user, current organization, and matter membership.
10. Add service-layer guards so route handlers are not the only authorization boundary.
11. Seed one organization plus admin, attorney, and reviewer users.
12. Build sign-in, matter list, create matter, and matter dashboard shell screens.
13. Ensure UI displays Trace in the app shell and Trace - Sovereign Discovery Copilot on primary formal headings.
14. Add audit records for login, logout, matter creation, matter update, and membership changes.

### Expected Behavior When Complete

- A seeded attorney can sign in.
- A signed-in user can view only authorized matters.
- A signed-in user can create a new matter.
- Opening a matter requires membership.
- Unauthorized matter access returns a consistent forbidden or not-found response without leaking matter metadata.
- Audit logs show who accessed or modified security-relevant resources.

### Test Criteria

- Login succeeds with valid seeded credentials.
- Login fails with invalid password.
- Logout clears the session.
- `/me` returns the current user when authenticated.
- `/me` fails when unauthenticated.
- Matter list excludes unauthorized matters.
- Matter create adds creator membership.
- Unauthorized `GET`, `POST`, and `PATCH` attempts are blocked.
- Role enforcement blocks `read_only` users from write actions.
- Audit rows are created for login, logout, matter create, and denied access where appropriate.

### Checkpoints

- Checkpoint 1.1: Auth data model and migration verified.
- Checkpoint 1.2: Session cookie lifecycle works through API and web.
- Checkpoint 1.3: Seed users can authenticate.
- Checkpoint 1.4: Matter membership guard is reusable and covered by tests.
- Checkpoint 1.5: Matter UI works end to end.
- Checkpoint 1.6: Audit logs capture security actions.

### Exit Gate

Phase 1 is complete when a seeded attorney can sign in, create or open a matter, and server-side RBAC blocks unauthorized access consistently across all implemented routes.

### Known Dependencies

- Phase 0 core stack.
- Initial database migration tooling.
- Stable session secret configuration.

## Phase 2 - Upload and Ingestion Skeleton

Status: Verified

Last tracked: 2026-04-17

### Completion Tracker

#### Feature Completion

- [x] `documents` table exists in the initial schema.
- [x] `ingest_jobs` table exists in the initial schema.
- [x] Matter-scoped multipart upload endpoint exists at `POST /matters/{matter_id}/documents/upload`.
- [x] Upload endpoint enforces Phase 1 matter membership before storage writes.
- [x] Upload endpoint accepts MVP file families: PDF, DOCX, TXT, CSV, XLSX, JPG, and PNG.
- [x] Upload endpoint validates file name, MIME type, extension, selected file signatures, non-empty payloads, and configurable size limits.
- [x] Upload endpoint streams incoming files in bounded chunks and uses a spooled temporary file before object storage write.
- [x] SHA-256 is computed during upload preparation and persisted on the document row.
- [x] Duplicate SHA-256 policy is documented for Phase 2: duplicate files are allowed as separate documents, while the persisted hash gives later phases a deterministic dedupe/review hook.
- [x] Storage keys are matter-scoped and stable for later ingestion phases.
- [x] Uploaded files persist in MinIO through the shared storage service.
- [x] Document rows persist file metadata, storage key, SHA-256, parse status, OCR status, and ingest status.
- [x] Ingest job rows are created with queued status and document/matter linkage.
- [x] Dramatiq enqueue passes only the document ID, not raw file content.
- [x] Worker skeleton transitions ingest jobs and documents through queued, running, and completed states.
- [x] Worker failure path marks jobs/documents failed with safe error text and records an `ingest_job_failed` audit row.
- [x] Upload start, success, validation failure, and enqueue failure paths create audit records.
- [x] Matter-scoped document listing exists at `GET /matters/{matter_id}/documents`.
- [x] Matter-aware document detail route exists at `GET /documents/{document_id}`.
- [x] Matter-aware page lookup route exists at `GET /documents/{document_id}/pages/{page_number}` for later parsing/viewer phases.
- [x] Next.js proxy supports multipart upload bodies.
- [x] Documents page includes upload UI, document table, status badges, and polling.

#### Implementation Step Tracking

- [x] Step 2.1: Document and ingest job schema fields are present from the initial migration.
- [x] Step 2.2: `POST /matters/{matter_id}/documents/upload` is implemented with matter membership enforcement.
- [x] Step 2.3: Upload preparation reads in bounded chunks and avoids holding the full upload in normal request memory.
- [x] Step 2.4: SHA-256 is computed before object storage persistence.
- [x] Step 2.5: Allowed file types are enforced for PDF, DOCX, TXT, CSV, XLSX, JPG, and PNG.
- [x] Step 2.6: `TRACE_MAX_UPLOAD_BYTES` controls the local/demo file size limit.
- [x] Step 2.7: Object storage keys include the matter ID and generated document object name.
- [x] Step 2.8: Document rows are created with `parse_status`, `ocr_status`, and `ingest_status`.
- [x] Step 2.9: Ingest job rows are created with queued status and matter/document linkage.
- [x] Step 2.10: API enqueue sends only `document_id` to the `ingestion` queue.
- [x] Step 2.11: Worker skeleton handles queued, running, completed, and failed status transitions.
- [x] Step 2.12: Failed jobs store safe class-name error messages instead of raw internals.
- [x] Step 2.13: `GET /matters/{matter_id}/documents` returns matter-scoped document lists.
- [x] Step 2.14: `GET /documents/{document_id}` enforces matter-aware access control.
- [x] Step 2.15: Upload UI exposes success and failure states and refreshes after upload.
- [x] Step 2.16: Document list UI shows file metadata and ingest status badges.
- [x] Step 2.17: Upload and ingest failure audit coverage exists for implemented Phase 2 paths.

#### Test and Verification Tracking

- [x] `python3 -m compileall apps/api/app apps/worker/worker` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with 11 tests.
- [x] `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck` passed.
- [x] Authorized upload test creates a MinIO object, document row, ingest job row, and audit row.
- [x] Unauthorized upload test rejects an outsider before storage write.
- [x] Unsupported file type test rejects the upload and records upload failure audit.
- [x] Oversized file test rejects the upload and records upload failure audit.
- [x] Signature mismatch test rejects incorrectly declared binary content.
- [x] Matter-scoped document list test returns only authorized matter documents.
- [x] Duplicate SHA-256 handling is deterministic by policy: duplicates are not collapsed in Phase 2, and each document retains its own row, storage key, and hash.
- [x] Live web-proxy smoke: seeded attorney login returned 200.
- [x] Live web-proxy smoke: matter list returned one authorized seeded matter.
- [x] Live web-proxy smoke: upload returned queued document status.
- [x] Live web-proxy smoke: worker polling moved the uploaded document from queued to completed.
- [x] Temporary live-smoke document and MinIO object were removed after verification.

#### Checkpoint Tracking

- [x] Checkpoint 2.1: Upload endpoint stores files in MinIO.
- [x] Checkpoint 2.2: Document metadata persists correctly.
- [x] Checkpoint 2.3: Worker receives ingest jobs through Dramatiq/Redis.
- [x] Checkpoint 2.4: Ingest status lifecycle is visible in API responses.
- [x] Checkpoint 2.5: Documents page and upload UI are usable.
- [x] Checkpoint 2.6: Upload audit coverage exists.

#### Phase 2 Exit Gate Tracking

- [x] Exit gate met: mixed files can be uploaded into a matter, persist in object storage, and move through stable queued, running, completed, or failed states.

#### Evidence Paths

- `apps/api/app/api/routes/documents.py`
- `apps/api/app/services/document.py`
- `apps/api/app/services/storage.py`
- `apps/api/app/schemas/document.py`
- `apps/api/app/tests/test_phase2_documents.py`
- `apps/worker/worker/tasks.py`
- `apps/worker/worker/settings.py`
- `apps/worker/pyproject.toml`
- `apps/web/lib/api-proxy.ts`
- `apps/web/app/api/matters/[matterId]/documents/route.ts`
- `apps/web/app/api/matters/[matterId]/documents/upload/route.ts`
- `apps/web/app/matters/[matterId]/documents/page.tsx`
- `apps/web/components/document-upload-panel.tsx`

### Goal

Allow authorized users to upload matter documents into object storage and see those documents move through a visible ingestion job lifecycle.

### Feature List

- `documents` table.
- `ingest_jobs` table.
- Matter-scoped multipart upload endpoint.
- Streaming write to MinIO.
- File signature, MIME, extension, size, and safety validation.
- SHA-256 hashing.
- Storage key generation.
- Ingest job enqueue.
- Upload audit logs.
- Documents table UI.
- Upload UI.
- Status badges.
- Job polling.

### Implementation Steps

1. Confirm or add document and ingest job schema fields from `docs/schema_and_seeds.md`.
2. Implement `POST /matters/{matter_id}/documents/upload` with matter membership enforcement.
3. Stream uploaded bytes to object storage without loading large files entirely into memory.
4. Compute SHA-256 during upload.
5. Validate allowed file types for MVP: PDF, DOCX, TXT, CSV, XLSX, JPG, PNG.
6. Enforce configurable file size limits suitable for local development and demo data.
7. Generate object storage keys scoped by organization, matter, and document ID.
8. Create a `documents` row with `parse_status`, `ocr_status`, and `ingest_status`.
9. Create an `ingest_jobs` row with `queued` status and matter/document linkage.
10. Enqueue a Dramatiq job with only IDs, not raw file content.
11. Implement worker skeleton that transitions jobs through `queued`, `running`, `completed`, and `failed`.
12. Ensure failed jobs store a safe error message.
13. Implement `GET /matters/{matter_id}/documents`.
14. Implement `GET /documents/{document_id}` with matter-aware access control.
15. Build upload UI with visible progress and failure states.
16. Build document list UI with file metadata and ingest status.
17. Add audit logs for upload start, upload success, upload failure, and job failure.

### Expected Behavior When Complete

- Authorized users can upload mixed files into a matter.
- Uploaded files persist in MinIO.
- Document rows are created with stable metadata.
- Ingest jobs are visible and transition through deterministic states.
- Unauthorized users cannot upload into or list documents for a matter.
- UI clearly shows upload and ingestion status.

### Test Criteria

- Authorized upload creates object storage object, document row, ingest job row, and audit row.
- Unauthorized upload is rejected before storage write.
- Unsupported MIME type is rejected.
- Oversized file is rejected.
- Duplicate SHA-256 handling is deterministic and documented.
- Ingest job skeleton can mark success.
- Ingest job skeleton can mark failure with safe error text.
- Document list returns only matter-scoped documents.
- UI polling reflects status changes.

### Checkpoints

- Checkpoint 2.1: Upload endpoint stores files in MinIO.
- Checkpoint 2.2: Document metadata persists correctly.
- Checkpoint 2.3: Worker receives ingest job.
- Checkpoint 2.4: Ingest status lifecycle is visible in API.
- Checkpoint 2.5: Documents page and upload UI are usable.
- Checkpoint 2.6: Upload audit coverage exists.

### Exit Gate

Phase 2 is complete when mixed files can be uploaded into a matter, persist in object storage, and move through stable queued, running, completed, or failed states.

### Known Dependencies

- Phase 1 matter membership enforcement.
- MinIO storage service.
- Dramatiq worker.
- Audit service.

## Phase 3 - Parsing, OCR, Chunks, Embeddings, and Search Corpus

Status: Verified

Last tracked: 2026-04-17

### Completion Tracker

#### Local OCR Note

- [x] Phase 3 is verified for the lightweight local core stack without starting the optional OCR add-on.
- [x] OCR hooks are implemented and observable, and OCR-disabled mode marks image/scanned content as `unavailable` instead of silently pretending extraction succeeded.
- [x] Full OCR text extraction/searchability for the seeded OCR challenge remains gated behind enabling an OCR provider or optional OCR add-on. This preserves the Apple Silicon 8 GB default path while keeping the production OCR architecture intact.

#### Feature Completion

- [x] `DocumentParser` contract exists with parse input, page output, metadata, status, and quality score shapes.
- [x] Parser registry resolves parsers by MIME type and extension.
- [x] PDF text parsing uses PyMuPDF.
- [x] Poor PDF text extraction is detected and routed through the OCR abstraction.
- [x] Image parsing uses the same OCR abstraction and marks disabled OCR clearly.
- [x] DOCX parsing uses `python-docx`.
- [x] CSV parsing uses Python `csv`.
- [x] XLSX parsing uses `openpyxl`.
- [x] TXT parsing is implemented.
- [x] `document_pages` persist page number, raw text, normalized text, text-layer flag, OCR confidence, and metadata.
- [x] Normalized text cleanup removes null bytes, repeated whitespace, and excessive blank lines.
- [x] Chunking preserves page boundaries.
- [x] Chunking defaults to roughly 800 tokens with 150-token overlap.
- [x] `document_chunks` persist matter ID, document ID, page span, chunk index, text, token count, metadata, and pgvector-compatible embeddings.
- [x] `EmbeddingClient` abstraction exists through a deterministic lightweight local hash embedding client.
- [x] Embeddings persist into the existing pgvector column.
- [x] Lexical search uses Postgres full-text search.
- [x] Vector ranking uses persisted embeddings and local cosine scoring.
- [x] Hybrid retrieval uses reciprocal-rank fusion over lexical and vector ranks.
- [x] Search enforces matter scope before ranking.
- [x] Search supports document ID, file type, document type, date range, entity-name, and source-name filters.
- [x] `POST /matters/{matter_id}/search` returns snippets, document names, page references, chunk IDs, scores, and metadata.
- [x] Worker ingestion now parses, persists pages, chunks, embeddings, and status updates.
- [x] Worker failure path persists safe failed statuses through the shared ingestion service.
- [x] Web search proxy route exists.
- [x] Search UI exists with query box, result count, snippets, document/page context, and score display.
- [x] Worker healthcheck timeout accounts for parser import cost without adding heavy runtime services.

#### Implementation Step Tracking

- [x] Step 3.1: `DocumentParser` interface and typed parse result shapes are defined.
- [x] Step 3.2: `OCRService` interface and disabled provider are defined.
- [x] Step 3.3: Parser registry by MIME type and extension is implemented.
- [x] Step 3.4: PDF text parser is implemented with PyMuPDF.
- [x] Step 3.5: Poor PDF text extraction marks OCR as needed/unavailable.
- [x] Step 3.6: OCR fallback hooks do not require a heavy OCR container in the default stack.
- [x] Step 3.7: Image OCR hook uses the same OCR abstraction.
- [x] Step 3.8: DOCX, TXT, CSV, and XLSX parsers are implemented.
- [x] Step 3.9: `document_pages` persistence is implemented.
- [x] Step 3.10: Page preview/image generation is deferred to Phase 4 viewer work; page/image reference columns are preserved.
- [x] Step 3.11: Normalized text cleanup is implemented.
- [x] Step 3.12: Page-boundary-preserving chunking is implemented.
- [x] Step 3.13: Approximate 800-token chunks with 150-token overlap are the default.
- [x] Step 3.14: `document_chunks` persistence includes matter scope, page span, metadata, and embeddings.
- [x] Step 3.15: `EmbeddingClient` abstraction and lightweight local embedding path are implemented.
- [x] Step 3.16: Embeddings store in pgvector.
- [x] Step 3.17: Lexical search uses Postgres FTS.
- [x] Step 3.18: Vector ranking uses stored embeddings.
- [x] Step 3.19: Reciprocal-rank fusion merges lexical and vector ranks.
- [x] Step 3.20: Matter scope is enforced on every search query.
- [x] Step 3.21: Metadata filters are implemented for document IDs, file types, document types, date range, entity names, and source names.
- [x] Step 3.22: `POST /matters/{matter_id}/search` is implemented.
- [x] Step 3.23: Ingest statuses update through running, completed, unavailable-OCR, and failed paths.
- [x] Step 3.24: UI search box and result rendering are implemented.

#### Test and Verification Tracking

- [x] `python3 -m compileall apps/api/app apps/worker/worker` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with 16 tests.
- [x] `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck` passed.
- [x] Parser tests cover TXT, CSV, DOCX, XLSX, PDF, and image/OCR-disabled paths.
- [x] OCR-disabled mode test verifies image content is marked `unavailable` with provider metadata.
- [x] Chunking test verifies page-boundary preservation and overlap behavior.
- [x] Ingestion test verifies page persistence, chunk persistence, embedding persistence, and searchability.
- [x] Search filter test verifies file-type filtering.
- [x] Matter isolation test verifies search does not return another matter's chunks.
- [x] Live web-proxy smoke: seeded attorney login returned 200.
- [x] Live web-proxy smoke: text upload returned queued document status.
- [x] Live web-proxy smoke: worker moved document to completed with parse status completed and OCR status not needed.
- [x] Live web-proxy smoke: search returned the uploaded document by unique phrase.
- [x] Temporary live-smoke document and MinIO object were removed after verification.
- [x] Final stack status checked with `docker compose -f infra/compose/compose.yaml ps`; `api`, `web`, `worker`, `postgres`, and `redis` are healthy, and `minio` is up.

#### Checkpoint Tracking

- [x] Checkpoint 3.1: Parser registry and first text parser work.
- [x] Checkpoint 3.2: Pages persist with normalized text.
- [x] Checkpoint 3.3: Chunking creates matter-scoped chunks.
- [x] Checkpoint 3.4: Embeddings persist in pgvector.
- [x] Checkpoint 3.5: Lexical search works.
- [x] Checkpoint 3.6: Hybrid search works.
- [x] Checkpoint 3.7: OCR hook status is visible.
- [x] Checkpoint 3.8: Mixed parser paths are covered; OCR-dependent seed search waits for optional OCR provider enablement.

#### Phase 3 Exit Gate Tracking

- [x] Local core exit gate met: uploaded text documents are parsed, page-aware, chunked, embedded, indexed, searchable, inspectable through API data, and matter-scoped.
- [x] OCR architecture exit gate met: scanned/image content enters the OCR abstraction and records visible unavailable/needed status in the default local stack.
- [ ] OCR extraction exit gate not exercised in default local mode: the seeded OCR inspection report cannot become text-searchable until an OCR provider/add-on is enabled.

#### Evidence Paths

- `apps/api/app/services/parsers.py`
- `apps/api/app/services/ocr.py`
- `apps/api/app/services/embeddings.py`
- `apps/api/app/services/ingestion.py`
- `apps/api/app/services/search.py`
- `apps/api/app/services/storage.py`
- `apps/api/app/schemas/search.py`
- `apps/api/app/tests/test_phase3_ingestion_search.py`
- `apps/worker/worker/tasks.py`
- `apps/worker/pyproject.toml`
- `infra/docker/worker.Dockerfile`
- `infra/compose/compose.yaml`
- `apps/web/app/api/matters/[matterId]/search/route.ts`
- `apps/web/app/matters/[matterId]/search/page.tsx`
- `apps/web/components/matter-search-panel.tsx`

### Goal

Convert uploaded files into searchable, page-aware, citation-ready text artifacts with OCR hooks and hybrid retrieval.

### Feature List

- Parser registry.
- PDF text parsing with PyMuPDF.
- OCR fallback path for scanned PDFs.
- Image OCR hook.
- DOCX parsing with `python-docx`.
- CSV parsing with Python `csv`.
- XLSX parsing with `openpyxl`.
- TXT parsing.
- `document_pages`.
- `document_chunks`.
- Page-level raw text and normalized text.
- Page preview or image references where useful.
- OCR confidence and text-layer flags.
- Extraction quality scoring.
- Chunking at about 800 tokens with 150-token overlap.
- Local embedding client abstraction.
- pgvector storage.
- Postgres full-text search.
- Vector search.
- Reciprocal-rank fusion.
- Matter-scoped snippets.
- Search filters.

### Implementation Steps

1. Define `DocumentParser` interface with parse input, parse output, page output, metadata, and error shape.
2. Define `OCRService` interface with disabled, local library, and future HTTP/provider modes.
3. Implement parser registry by MIME type and file extension.
4. Implement PDF text parser using PyMuPDF.
5. Detect poor PDF text extraction and mark OCR as needed.
6. Implement OCR fallback hooks without requiring a heavy OCR container in default local setup.
7. Implement image OCR hook using the same OCR abstraction.
8. Implement DOCX, TXT, CSV, and XLSX parsers.
9. Persist `document_pages` with page number, raw text, normalized text, text-layer flag, OCR confidence, and metadata.
10. Generate page previews or page image references for PDFs/images where useful for the viewer.
11. Implement normalized text cleanup for whitespace, page artifacts, and encoding oddities.
12. Implement page-boundary-preserving chunking.
13. Use approximate 800-token chunks with 150-token overlap.
14. Store `document_chunks` with `matter_id`, `document_id`, page span, chunk index, text, token count, metadata, and embedding.
15. Implement `EmbeddingClient` abstraction and a local lightweight embedding path.
16. Store embeddings in pgvector.
17. Implement lexical search using Postgres full-text search.
18. Implement vector search using pgvector.
19. Implement hybrid retrieval with reciprocal-rank fusion.
20. Enforce matter scope in every search query.
21. Implement metadata filters for document type, date, entity where available, and source.
22. Implement `POST /matters/{matter_id}/search`.
23. Update ingest statuses through parsing, OCR, chunking, embedding, indexing, ready, and failed.
24. Add UI search box, search results, snippets, document/page context, and parse/OCR status details.

### Expected Behavior When Complete

- Uploaded documents become searchable after ingestion.
- OCR-needed content can enter the corpus through the OCR abstraction.
- Search results include snippets, document names, page references, chunk references, and score metadata.
- Search is always matter-scoped.
- Users can inspect extraction quality, OCR status, and parse failures.
- The seeded OCR inspection report becomes searchable and visible.

### Test Criteria

- Parser unit tests cover PDF, DOCX, TXT, CSV, XLSX, JPG, and PNG paths.
- OCR fallback triggers when PDF text extraction quality is poor.
- OCR disabled mode fails gracefully and marks OCR status clearly.
- Chunking preserves page boundaries and target overlap.
- Embedding persistence works for chunks.
- Lexical search returns expected seeded snippets.
- Vector search returns expected seeded concepts.
- Hybrid retrieval merges and ranks results deterministically.
- Search never returns chunks from another matter.
- Ingest failures persist safe error messages.
- Seeded OCR challenge is searchable once OCR is enabled.

### Checkpoints

- Checkpoint 3.1: Parser registry and first text parser work.
- Checkpoint 3.2: Pages persist with normalized text.
- Checkpoint 3.3: Chunking creates matter-scoped chunks.
- Checkpoint 3.4: Embeddings persist in pgvector.
- Checkpoint 3.5: Lexical search works.
- Checkpoint 3.6: Hybrid search works.
- Checkpoint 3.7: OCR hook status is visible.
- Checkpoint 3.8: Mixed seeded documents are searchable.

### Exit Gate

Phase 3 is complete when the seeded OCR inspection report and other mixed documents are searchable, inspectable, and represented as page-aware chunks with matter-scoped retrieval.

### Known Dependencies

- Phase 2 upload and ingest job lifecycle.
- pgvector extension.
- Object storage access.
- OCR add-on remains optional locally until specifically testing OCR.

## Phase 4 - Viewer and Citation Trust Loop

Status: Verified

Last tracked: 2026-04-17

### Completion Tracker

#### Preview Implementation Note

- [x] Phase 4 uses a lightweight source-preview path: browser-native PDF iframe preview, direct image rendering, text iframe preview, and extracted-text fallback.
- [x] `react-pdf`/PDF.js canvas rendering is not added yet to avoid pulling new frontend dependencies into the constrained local stack. The viewer route and source-file API are compatible with adding it later.

#### Feature Completion

- [x] Matter-aware document detail endpoint exists at `GET /documents/{document_id}`.
- [x] Matter-aware page endpoint exists at `GET /documents/{document_id}/pages/{page_number}`.
- [x] Matter-aware source-file endpoint exists at `GET /documents/{document_id}/file`.
- [x] Source-file endpoint streams original source bytes from MinIO with inline content disposition.
- [x] Source-file endpoint returns a clear 404 if a source object is missing.
- [x] Page view and source-file view audit rows are recorded.
- [x] Existing seed script backfills source text objects for seeded demo documents.
- [x] Web API proxies exist for document detail, page data, and source-file bytes.
- [x] Web viewer route exists at `/matters/{matter_id}/documents/{document_id}`.
- [x] Viewer supports direct deep links with `page`, `quote`, and `chunk` query parameters.
- [x] Viewer renders original source preview and extracted text side by side.
- [x] Viewer renders PDF sources through browser-native PDF preview.
- [x] Viewer renders images directly with safe sizing.
- [x] Viewer renders text sources through a source iframe.
- [x] Viewer falls back to extracted text when source preview is unavailable.
- [x] Viewer has previous, next, and direct page-jump controls.
- [x] Viewer renders citation context and highlights matching terms in extracted text.
- [x] Search result cards include an “Open source page” link to the exact document/page with snippet context.
- [x] Document list cards include an “Open viewer” link.
- [x] Unauthorized document, page, and file requests are blocked server-side.

#### Implementation Step Tracking

- [x] Step 4.1: `GET /documents/{document_id}` is matter-aware.
- [x] Step 4.2: `GET /documents/{document_id}/pages/{page_number}` returns page text and metadata.
- [x] Step 4.3: Web viewer route is implemented for document/page inspection.
- [x] Step 4.4: PDF preview uses browser-native PDF rendering through the source-file route; dedicated `react-pdf` canvas integration remains an optional enhancement.
- [x] Step 4.5: Image preview renders directly with bounded sizing.
- [x] Step 4.6: Extracted text renders side-by-side with original preview.
- [x] Step 4.7: Page navigation and direct page jump are implemented.
- [x] Step 4.8: Quote snippet context and local highlighting are implemented.
- [x] Step 4.9: Citation deep-link parameters are defined as `page`, `quote`, and `chunk`.
- [x] Step 4.10: Search result links open exact document pages.
- [x] Step 4.11: Unauthorized viewer resources return forbidden responses without returning document payloads.
- [x] Step 4.12: Missing preview/source cases degrade to extracted text or clear 404 behavior.

#### Test and Verification Tracking

- [x] `python3 -m compileall apps/api/app apps/worker/worker` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with 20 tests.
- [x] `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck` passed.
- [x] Authorized viewer test verifies document detail, page data, source-file bytes, and view audit rows.
- [x] Unauthorized viewer test verifies document, page, and file requests are blocked.
- [x] Missing page test verifies clear 404 behavior.
- [x] Search identifier test verifies search results include document ID, page number, chunk ID, and snippet.
- [x] Live web-proxy smoke: seeded attorney login returned 200.
- [x] Live web-proxy smoke: text upload completed ingestion.
- [x] Live web-proxy smoke: search returned the uploaded document and page.
- [x] Live web-proxy smoke: viewer route returned 200 for the search hit deep link.
- [x] Live web-proxy smoke: page API returned extracted text containing the searched phrase.
- [x] Live web-proxy smoke: source-file proxy returned original text bytes containing the searched phrase.
- [x] Temporary live-smoke document and MinIO object were removed after verification.

#### Checkpoint Tracking

- [x] Checkpoint 4.1: Document detail endpoint is matter-aware.
- [x] Checkpoint 4.2: Page endpoint returns usable page data.
- [x] Checkpoint 4.3: Web viewer opens documents.
- [x] Checkpoint 4.4: Search hits deep-link to pages.
- [x] Checkpoint 4.5: Quote snippets render with context.
- [x] Checkpoint 4.6: Viewer trust loop works within one to two clicks.

#### Phase 4 Exit Gate Tracking

- [x] Exit gate met: search hits can open the exact source page with source preview, extracted text, quote context, and matter-aware authorization.

#### Evidence Paths

- `apps/api/app/api/routes/documents.py`
- `apps/api/app/scripts/seed_demo.py`
- `apps/api/app/tests/test_phase4_viewer.py`
- `apps/web/lib/api-proxy.ts`
- `apps/web/app/api/documents/[documentId]/route.ts`
- `apps/web/app/api/documents/[documentId]/file/route.ts`
- `apps/web/app/api/documents/[documentId]/pages/[pageNumber]/route.ts`
- `apps/web/app/matters/[matterId]/documents/[documentId]/page.tsx`
- `apps/web/components/document-viewer.tsx`
- `apps/web/components/document-upload-panel.tsx`
- `apps/web/components/matter-search-panel.tsx`

### Goal

Make source verification fast enough that legal users can trust search hits and later AI citations in one to two clicks.

### Feature List

- Document viewer route.
- PDF support.
- Image support.
- Page navigation.
- Extracted text side-by-side panel.
- Deep links by `document_id`, `page_number`, and optional citation context.
- Quote snippet rendering.
- Local context around matched quotes.
- Matter-aware viewer authorization.
- Page preview rendering.
- Search result to viewer navigation.

### Implementation Steps

1. Implement `GET /documents/{document_id}` with matter-aware authorization.
2. Implement `GET /documents/{document_id}/pages/{page_number}` with page text, metadata, and preview references.
3. Add viewer route in the web app for document and page inspection.
4. Integrate `react-pdf`/PDF.js for PDFs.
5. Render images directly with safe sizing.
6. Render extracted text side-by-side with the original preview where useful.
7. Add page navigation controls and direct page jump.
8. Add quote snippet highlighting or local context rendering.
9. Define citation deep-link parameters that later workflow outputs can reuse.
10. Add search result links that open exact document pages.
11. Ensure unauthorized viewer requests do not leak document names or page counts.
12. Ensure viewer handles missing previews by falling back to extracted text.

### Expected Behavior When Complete

- Users can open a search hit and land on the exact page.
- Users can see enough local evidence to verify why the result matched.
- Viewer access respects matter membership.
- Later citations can reuse the same deep-link mechanism.
- Missing previews or extraction artifacts degrade gracefully.

### Test Criteria

- Authorized users can open a document page.
- Unauthorized users cannot open another matter's document page.
- Search result links include document and page identifiers.
- Page endpoint returns extracted text and metadata.
- Citation link builder resolves to the correct route.
- Viewer handles PDF, image, and text-only documents.
- Missing page returns a clear not-found response.

### Checkpoints

- Checkpoint 4.1: Document detail endpoint is matter-aware.
- Checkpoint 4.2: Page endpoint returns usable page data.
- Checkpoint 4.3: Web viewer opens documents.
- Checkpoint 4.4: Search hits deep-link to pages.
- Checkpoint 4.5: Quote snippets render with context.
- Checkpoint 4.6: Viewer trust loop works within one to two clicks.

### Exit Gate

Phase 4 is complete when any search hit can open the exact source page with enough local context for a legal user to verify the evidence quickly.

### Known Dependencies

- Phase 3 pages, chunks, and search results.
- Page preview artifacts when available.
- Matter membership enforcement.

## Phase 5 - Grounded Q&A

Status: Verified

Last tracked: 2026-04-17

### Completion Tracker

#### Feature Completion

- [x] `ai_runs` persistence is active for grounded Q&A.
- [x] `citations` persistence is active for validated answer citations.
- [x] `ModelClient` abstraction includes a safe provider error type.
- [x] `MockModelClient` remains the local default.
- [x] `OpenAICompatibleModelClient` remains configured for later self-hosted vLLM-compatible integration.
- [x] Evidence assembly uses question-driven matter-scoped retrieval with a matter-scoped fallback when lexical/vector search returns no ranked results.
- [x] `GroundedQAResponse` includes answer, short answer, confidence, citations, open questions, unsupported-claims flag, and AI run ID.
- [x] Citation payloads include viewer URLs and validation status.
- [x] `grounded_qa_v1` is the persisted prompt template version for Q&A runs.
- [x] `citation_check_v1` is represented in AI run output validation metadata.
- [x] Citation validation requires document/chunk/page records to exist in the same matter.
- [x] Citation validation rejects quotes that do not appear in source chunk or page text.
- [x] Zero validated citations return insufficient evidence.
- [x] Single validated citation answers are downgraded to low confidence.
- [x] AI run input, output, status, provider/model metadata, and validation metadata persist.
- [x] Citation rows persist after validation and link to source documents/chunks/pages.
- [x] AI run lifecycle audit rows cover start, completion, validation failure, and provider failure paths.
- [x] Ask UI renders question input, answer, confidence badge, evidence-only mode, validated citations, citation links, and AI run link.
- [x] Web proxy route exists for `POST /matters/{matter_id}/ask`.
- [x] Web proxy route exists for `GET /ai-runs/{run_id}`.

#### Implementation Step Tracking

- [x] Step 5.1: `ai_runs` and `citations` schema fields are used for Q&A.
- [x] Step 5.2: `ModelClientError` gives provider failures safe semantics.
- [x] Step 5.3: `MockModelClient` works locally without model-serving containers.
- [x] Step 5.4: OpenAI-compatible adapter remains wired through configuration for future vLLM use.
- [x] Step 5.5: Evidence assembly uses hybrid retrieval output and enforces matter scope.
- [x] Step 5.6: `GroundedQAResponse` schema is hardened with citation viewer and validation metadata.
- [x] Step 5.7: `grounded_qa_v1` is persisted on Q&A AI runs.
- [x] Step 5.8: Deterministic `citation_check_v1` validation is implemented.
- [x] Step 5.9: Citations must resolve to same-matter chunks, documents, and pages.
- [x] Step 5.10: Quoted text is matched against source text.
- [x] Step 5.11: Zero validated citations returns insufficient evidence.
- [x] Step 5.12: One validated citation returns low confidence.
- [x] Step 5.13: High confidence is not granted without at least two validated citations.
- [x] Step 5.14: AI run persistence includes input, output, status, model/provider metadata, and validation metadata.
- [x] Step 5.15: Citation rows persist after validation.
- [x] Step 5.16: Q&A run lifecycle audit coverage exists.
- [x] Step 5.17: Ask UI renders answers, evidence-only mode, confidence, and clickable citations.

#### Test and Verification Tracking

- [x] `python3 -m compileall apps/api/app apps/worker/worker` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app` passed.
- [x] `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with 25 tests.
- [x] `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck` passed.
- [x] Q&A persistence test verifies `ai_runs`, validated citations, persisted citation rows, and validation metadata.
- [x] Insufficient evidence test verifies empty matters return no citations and a safe answer.
- [x] Weak evidence test verifies one validated citation returns low confidence.
- [x] Citation validator test rejects nonexistent quotes.
- [x] Provider failure test verifies safe failed run behavior.
- [x] Live seeded Acme smoke: seeded attorney login returned 200.
- [x] Live seeded Acme smoke: defect-knowledge question returned 200.
- [x] Live seeded Acme smoke: response included validated citations and AI run ID.
- [x] Live seeded Acme smoke: first citation viewer URL opened with 200.
- [x] Live seeded Acme smoke: `GET /api/ai-runs/{run_id}` returned the completed `grounded_qa` run.
- [x] Final stack status checked; `api`, `web`, `worker`, `postgres`, and `redis` are healthy, and `minio` is up.

#### Checkpoint Tracking

- [x] Checkpoint 5.1: AI run schema and persistence work.
- [x] Checkpoint 5.2: Evidence assembly produces source packs.
- [x] Checkpoint 5.3: Mock model Q&A works locally.
- [x] Checkpoint 5.4: Citation validation rejects bad citations.
- [x] Checkpoint 5.5: Ask UI renders answer and evidence.
- [x] Checkpoint 5.6: Seeded defect-knowledge question works.

#### Phase 5 Exit Gate Tracking

- [x] Exit gate met: the defect-knowledge seeded question returns a matter-scoped grounded answer with validated citations that open real source pages.

#### Evidence Paths

- `apps/api/app/services/workflows.py`
- `apps/api/app/services/citations.py`
- `apps/api/app/services/model_client.py`
- `apps/api/app/services/mock_model_client.py`
- `apps/api/app/services/openai_compatible_model_client.py`
- `apps/api/app/schemas/workflow.py`
- `apps/api/app/api/routes/workflows.py`
- `apps/api/app/tests/test_phase5_grounded_qa.py`
- `apps/web/app/api/matters/[matterId]/ask/route.ts`
- `apps/web/app/api/ai-runs/[runId]/route.ts`
- `apps/web/app/matters/[matterId]/ask/page.tsx`
- `apps/web/components/ask-panel.tsx`

### Goal

Ship the first AI workflow: matter-scoped grounded Q&A with validated citations, conservative confidence, persisted AI runs, and clickable evidence.

### Feature List

- `ai_runs`.
- `citations`.
- `ModelClient` abstraction.
- `MockModelClient` local default.
- `OpenAICompatibleModelClient` for self-hosted vLLM or equivalent endpoint.
- Evidence assembly.
- `grounded_qa_v1`.
- `citation_check_v1`.
- Citation validation.
- Quote matching.
- Confidence state.
- Insufficient evidence handling.
- Ask screen.
- Evidence-only view.
- Clickable citations.
- AI run audit logs.

### Implementation Steps

1. Confirm `ai_runs` and `citations` schema fields align with `docs/schema_and_seeds.md`.
2. Harden `ModelClient` with request, response, timeout, retry, and error semantics.
3. Keep `MockModelClient` as default local provider.
4. Wire `OpenAICompatibleModelClient` through configuration for future self-hosted vLLM use.
5. Implement evidence assembly using hybrid retrieval, reranking, and matter-scoped filters.
6. Define `GroundedQAResponse` schema with answer, short answer, confidence, citations, open questions, unsupported claims flag, and AI run ID.
7. Create prompt template `grounded_qa_v1`.
8. Create prompt/template or deterministic validator for `citation_check_v1`.
9. Require citations to point to existing chunks, documents, pages, and matter IDs.
10. Match quoted text against source text where feasible.
11. If zero validated citations remain, return insufficient evidence.
12. If only one weak citation remains, return low confidence.
13. Prefer at least two corroborating citations for high-confidence factual answers when available.
14. Persist AI run input, output, status, model/provider metadata, latency, and validation metadata.
15. Persist citation rows linked to AI runs and source evidence.
16. Audit Q&A run creation, completion, validation failure, and user access.
17. Build Ask UI with answer rendering, confidence badge, evidence-only mode, and clickable citations.

### Expected Behavior When Complete

- Users can ask a matter-scoped question.
- The answer is grounded in retrieved evidence.
- Citations validate against real source material.
- Unsupported or weakly supported answers are conservative.
- AI runs are inspectable after completion.
- Citations open real source pages in the viewer.

### Test Criteria

- Q&A run persists an `ai_runs` row.
- Citations persist and link to source records.
- Retrieval is matter-scoped.
- Zero-citation answer returns insufficient evidence.
- Weak evidence returns low confidence.
- Citation quote validation rejects nonexistent quotes.
- The seeded question "What evidence suggests Northshore knew of the defect before shipment?" returns validated citations.
- Clicked citations open real source pages.
- Model timeout or provider error becomes a safe user-visible failure.

### Checkpoints

- Checkpoint 5.1: AI run schema and persistence work.
- Checkpoint 5.2: Evidence assembly produces source packs.
- Checkpoint 5.3: Mock model Q&A works locally.
- Checkpoint 5.4: Citation validation rejects bad citations.
- Checkpoint 5.5: Ask UI renders answer and evidence.
- Checkpoint 5.6: Seeded defect-knowledge question works.

### Exit Gate

Phase 5 is complete when the defect-knowledge seeded question returns a matter-scoped grounded answer with validated citations that open real source pages.

### Known Dependencies

- Phase 3 retrieval.
- Phase 4 viewer and citation deep links.
- Model provider abstraction.
- Seeded Acme matter content.

## Phase 6 - Chronology Builder

Status: Verified

Last tracked: 2026-04-19

### Goal

Generate a citation-backed chronology that turns matter evidence into a structured, sortable, editable legal artifact.

### Feature List

- `events`.
- `event_citations`.
- Chronology retrieval mode.
- `chronology_builder_v1`.
- Structured chronology JSON.
- Date normalization.
- Date confidence.
- Disputed or ambiguous date handling.
- Near-duplicate event collapsing.
- Manual event edits.
- Chronology table UI.
- Filters by entity, topic, source, and date.
- CSV export.

### Implementation Steps

1. Confirm `events` and `event_citations` schema fields.
2. Implement chronology-specific retrieval mode optimized for dated facts, correspondence, notices, invoices, inspections, and testimony.
3. Define `ChronologyRunOutput` schema with events and unresolved ambiguities.
4. Create prompt template `chronology_builder_v1`.
5. Generate structured events before prose.
6. Normalize dates to ISO dates when possible.
7. Preserve original date text and date confidence.
8. Mark disputed dates or ambiguous records with conflict flags.
9. Collapse near-duplicate events while preserving all useful citations.
10. Persist events and event citations.
11. Support manual edit of event title, description, date, confidence, and visibility.
12. Keep original AI output available through `ai_runs`.
13. Build chronology UI with sortable table, filters, citation links, and event detail drawer.
14. Add chronology CSV export in this phase.
15. Audit chronology generation, manual edits, and export creation.

### Completion Tracker

- [x] Step 6.1: `events` and `event_citations` are present in the core schema.
- [x] Step 6.2: Chronology-specific retrieval uses topic/entity/date filters plus a matter-scoped fallback evidence pack.
- [x] Step 6.3: `ChronologyResponse` carries structured events, unresolved ambiguities, event IDs, citation payloads, confidence, and source type.
- [x] Step 6.4: `chronology_builder_v1` is persisted through `ai_runs` with validation metadata.
- [x] Step 6.5: Structured events are generated and persisted before any UI rendering.
- [x] Step 6.6: Mock local chronology provider extracts dates when possible and marks inferred dates as low confidence.
- [x] Step 6.7: Original date text and date confidence are preserved on every event.
- [x] Step 6.8: Disputed events can be marked with `conflict_flag`.
- [x] Step 6.9: Near-duplicate event collapse preserves distinct citations.
- [x] Step 6.10: Persisted `events` and `event_citations` require validated matter-scoped citations.
- [x] Step 6.11: Manual edits support title, description, date, date confidence, entities, confidence, and dispute flag.
- [x] Step 6.12: Original workflow input/output remains inspectable through `ai_runs`.
- [x] Step 6.13: Web chronology UI supports generation, saved-event loading, sort, entity/text filter, disputed-only filter, citation links, and event editing.
- [x] Step 6.14: CSV export works through `/matters/{matter_id}/chronology/export.csv`.
- [x] Step 6.15: Audit logs cover generation, manual edits, and CSV export.

### Expected Behavior When Complete

- Users can generate a chronology from matter evidence.
- Events are structured and citation-backed.
- Ambiguous or disputed dates are visible rather than hidden.
- Users can sort, filter, inspect, and edit events.
- CSV export produces a usable chronology artifact.
- Re-running chronology generation replaces prior AI-extracted chronology rows while preserving user-edited events.

### Test Criteria

- Acme matter produces at least 10 useful events.
- Each persisted event has matter scope.
- Event citations link to source evidence.
- Date confidence is stored and rendered.
- Duplicate event collapse preserves supporting citations.
- Manual edits persist and are audited.
- Chronology table sorts by date.
- Filters work by entity/topic/source where data exists.
- CSV export succeeds.
- `POST /matters/{matter_id}/chronology` rejects events with invalid citations.
- `GET /matters/{matter_id}/chronology/events` and `PATCH /events/{event_id}` enforce matter membership.
- The web proxy path can generate a seeded chronology, open a citation, edit an event, and export CSV.

### Checkpoints

- [x] Checkpoint 6.1: Events schema and citations work.
- [x] Checkpoint 6.2: Chronology retrieval mode returns useful evidence.
- [x] Checkpoint 6.3: Structured chronology output validates.
- [x] Checkpoint 6.4: Events persist with citations.
- [x] Checkpoint 6.5: Chronology UI supports inspect/sort/filter.
- [x] Checkpoint 6.6: CSV export works.

### Verification Evidence

- `python3 -m compileall apps/api/app apps/worker/worker`
- `docker compose -f infra/compose/compose.yaml build api web worker`
- `docker compose -f infra/compose/compose.yaml up -d api web worker`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app`
- `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with `29 passed`.
- Live seeded smoke through the web proxy: login `200`, chronology generation `200`, `10` events, validated citation viewer `200`, saved event list `200`, event edit `200`, CSV export `200`.

### Implementation Evidence

- `apps/api/app/schemas/workflow.py`
- `apps/api/app/services/chronology.py`
- `apps/api/app/services/workflows.py`
- `apps/api/app/services/mock_model_client.py`
- `apps/api/app/api/routes/workflows.py`
- `apps/api/app/scripts/seed_demo.py`
- `apps/api/app/tests/test_phase6_chronology.py`
- `apps/web/components/chronology-panel.tsx`
- `apps/web/app/matters/[matterId]/chronology/page.tsx`
- `apps/web/app/api/matters/[matterId]/chronology/route.ts`
- `apps/web/app/api/matters/[matterId]/chronology/events/route.ts`
- `apps/web/app/api/matters/[matterId]/chronology/export.csv/route.ts`
- `apps/web/app/api/events/[eventId]/route.ts`

### Exit Gate

Phase 6 is complete when the Acme matter produces at least 10 useful citation-backed events with disputed dates, filters, sortable output, and CSV export.

### Known Dependencies

- Phase 3 retrieval.
- Phase 4 viewer.
- Phase 5 AI run and citation infrastructure.
- Export foundation for CSV.

## Phase 7 - Entity and Witness Layer

Status: Verified

Last tracked: 2026-04-20

### Goal

Build evidence-backed entity and witness pages that summarize people, organizations, projects, and products using traceable mentions.

### Feature List

- `entities`.
- `entity_mentions`.
- Deterministic entity candidate harvesting.
- Canonical entity normalization.
- Alias handling.
- Manual alias merge.
- `entity_summary_v1`.
- Entity list UI.
- Entity detail UI.
- Mentions list.
- Key documents.
- Entity timeline.
- Evidence-backed summaries.

### Implementation Steps

1. Confirm `entities` and `entity_mentions` schema fields.
2. Implement deterministic candidate harvesting from parsed text using capitalization, known seed aliases, document metadata, and simple heuristics.
3. Normalize candidates into canonical records.
4. Store mentions with document, page, chunk, quote, and matter context.
5. Use LLM only for summary/profile synthesis over retrieved mentions, not for the first canonical source of truth.
6. Implement alias creation and manual alias merge.
7. Define `EntitySummary.summary_json`.
8. Create prompt template `entity_summary_v1`.
9. Persist entity summary output and link it to an AI run when model-generated.
10. Build entity list page with type, mention count, key documents, and last-seen metadata.
11. Build entity detail page with summary, aliases, mentions, citations, key documents, and timeline.
12. Add matter-aware access checks for `GET /matters/{matter_id}/entities` and `GET /entities/{entity_id}`.
13. Add `POST /matters/{matter_id}/entities/extract`.
14. Audit entity extraction and alias merge.

### Completion Tracker

- [x] Step 7.1: `entities` and `entity_mentions` schema fields are present and exercised by tests.
- [x] Step 7.2: Deterministic candidate harvesting uses seed aliases, known canonical entities, document/chunk text, and capitalization heuristics.
- [x] Step 7.3: Candidate normalization resolves aliases into canonical matter-scoped entity records.
- [x] Step 7.4: Mentions store document, page, chunk, quote/context, and viewer link context.
- [x] Step 7.5: LLM/model synthesis is used only for summary/profile generation over extracted mentions.
- [x] Step 7.6: Alias creation and manual entity merge are implemented.
- [x] Step 7.7: `EntitySummary.summary_json` stores overview, role, key actions, key documents, key dates, open questions, workflow, AI run ID, and mention count.
- [x] Step 7.8: `entity_summary_v1` is represented by persisted `ai_runs`.
- [x] Step 7.9: Entity summary output is persisted and linked to an AI run.
- [x] Step 7.10: Entity list UI shows type, mention count, key documents, aliases, and summary preview.
- [x] Step 7.11: Entity detail UI shows summary, aliases, mentions, source links, key documents, and timeline.
- [x] Step 7.12: Entity routes enforce matter-aware access checks.
- [x] Step 7.13: `POST /matters/{matter_id}/entities/extract` extracts and summarizes matter entities.
- [x] Step 7.14: Audit logs cover entity extraction, alias creation, and alias merge.

### Expected Behavior When Complete

- Users can browse known entities in a matter.
- Entity pages explain who or what the entity is, with citations.
- Mentions are traceable to source documents and pages.
- Alias merge can clean up duplicate seeded names.
- LLM summaries do not create unsupported entity facts.
- Entity extraction also runs during document ingestion as a lightweight deterministic hook.

### Test Criteria

- Jane Mercer has an evidence-backed page.
- Northshore Supply has an evidence-backed page.
- Priya Shah has an evidence-backed page.
- Project Falcon has an evidence-backed page.
- Compressor Unit 7A has an evidence-backed page.
- Entity mentions include document, page, chunk, and quote context.
- Alias merge combines duplicate entities without losing mentions.
- Entity access is matter-scoped.
- Entity summary output validates against schema.
- Entity extraction is idempotent enough for repeated local demo runs and does not duplicate mentions.
- Entity mention viewer URLs open source pages.
- Entity summary runs are persisted as `ai_runs` using `entity_summary_v1`.

### Checkpoints

- [x] Checkpoint 7.1: Entity schema and mention schema work.
- [x] Checkpoint 7.2: Candidate harvesting creates seeded canonical entities.
- [x] Checkpoint 7.3: Mentions are traceable.
- [x] Checkpoint 7.4: Alias merge works.
- [x] Checkpoint 7.5: Entity summary workflow works.
- [x] Checkpoint 7.6: Entity pages are useful for Acme.

### Verification Evidence

- `python3 -m compileall apps/api/app apps/worker/worker`
- `docker compose -f infra/compose/compose.yaml build api web worker`
- `docker compose -f infra/compose/compose.yaml up -d api web worker`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app`
- `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with `32 passed`.
- Live seeded smoke through the web proxy: login `200`, entity extraction `200`, required entities present, Jane Mercer detail `200`, mention source viewer `200`, alias creation `200`.

### Implementation Evidence

- `apps/api/app/schemas/entity.py`
- `apps/api/app/services/entities.py`
- `apps/api/app/services/ingestion.py`
- `apps/api/app/services/mock_model_client.py`
- `apps/api/app/api/routes/workflows.py`
- `apps/api/app/scripts/seed_demo.py`
- `apps/api/app/tests/test_phase7_entities.py`
- `apps/web/components/entities-panel.tsx`
- `apps/web/components/entity-detail-panel.tsx`
- `apps/web/app/matters/[matterId]/entities/page.tsx`
- `apps/web/app/matters/[matterId]/entities/[entityId]/page.tsx`
- `apps/web/app/api/matters/[matterId]/entities/route.ts`
- `apps/web/app/api/matters/[matterId]/entities/extract/route.ts`
- `apps/web/app/api/entities/[entityId]/route.ts`
- `apps/web/app/api/entities/[entityId]/aliases/route.ts`
- `apps/web/app/api/entities/[entityId]/merge/route.ts`

### Exit Gate

Phase 7 is complete when Jane Mercer, Northshore Supply, Priya Shah, Project Falcon, and Compressor Unit 7A have evidence-backed pages with mentions, key documents, and timelines.

### Known Dependencies

- Phase 3 parsed chunks.
- Phase 4 viewer.
- Phase 5 AI run/citation infrastructure for summaries.
- Seed truth aliases.

## Phase 8 - Contradiction Finder

Status: Verified

Last tracked: 2026-04-20

### Goal

Surface conflicting claims conservatively and transparently, separating true contradictions from ambiguities.

### Feature List

- Contradiction retrieval mode.
- `contradiction_finder_v1`.
- Proposition clustering.
- Side-by-side evidence.
- Severity labeling.
- Contradiction versus ambiguity separation.
- Persisted AI run output.
- Citation rows for both sides.
- Contradiction report UI.
- Optional contradiction markers on entity or chronology pages.

### Implementation Steps

1. Define `ContradictionRunOutput` schema with topic, contradictions, ambiguities, severity, citations for side A, and citations for side B.
2. Create prompt template `contradiction_finder_v1`.
3. Implement topic-specific retrieval with entity, date, and issue hints.
4. Cluster evidence into propositions before asking for contradiction synthesis where practical.
5. Require both sides of a contradiction to have citations.
6. Separate contradiction from ambiguity in the output.
7. Label severity conservatively.
8. Persist contradiction output through `ai_runs`.
9. Persist citations for each side.
10. Build contradiction request UI.
11. Build contradiction report UI with side-by-side claims, evidence, severity, and ambiguity notes.
12. Use seed truth topics as regression targets.
13. Audit contradiction run creation, completion, and failures.

### Completion Tracker

- [x] Step 8.1: `ContradictionResponse` includes topic, contradictions, ambiguities, severity, side labels, confidence, evidence count, and citations for both sides.
- [x] Step 8.2: `contradiction_finder_v1` is persisted through `ai_runs`.
- [x] Step 8.3: Topic-specific retrieval supports `notice timing`, `payment approval authority`, and `defect knowledge`.
- [x] Step 8.4: Evidence is clustered into side A and side B propositions before synthesis.
- [x] Step 8.5: Contradictions require validated citations on both sides.
- [x] Step 8.6: One-sided evidence returns ambiguity instead of a contradiction.
- [x] Step 8.7: Severity labels are conservative and schema-validated.
- [x] Step 8.8: Contradiction output persists through `ai_runs` with validation metadata.
- [x] Step 8.9: Citation rows persist for both sides after validation.
- [x] Step 8.10: Contradiction request UI is implemented.
- [x] Step 8.11: Contradiction report UI renders side-by-side claims, evidence, severity, and ambiguity notes.
- [x] Step 8.12: Seed truth topics are covered by regression tests and live smoke.
- [x] Step 8.13: Audit logs cover contradiction run start, completion, and failure paths.

### Expected Behavior When Complete

- Users can request contradiction analysis for a topic.
- Results show conflicting claims side by side.
- Each side links to source evidence.
- Ambiguities are not overstated as contradictions.
- Known seeded contradiction themes are detectable.
- Citation links open the underlying document page for each side.

### Test Criteria

- Notice timing contradiction theme is surfaced.
- Payment approval authority contradiction theme is surfaced.
- Defect knowledge contradiction theme is surfaced.
- Contradiction output validates against schema.
- Each contradiction has citations on both sides.
- Ambiguities can appear separately.
- Matter isolation prevents cross-matter evidence.
- Side-by-side evidence links open viewer pages.
- Bad citation quotes are rejected and recorded as validation failures.
- Persisted `ai_runs` include contradiction validation metadata.
- Live web proxy flow succeeds for all seeded contradiction topics.

### Checkpoints

- [x] Checkpoint 8.1: Contradiction schema is defined and validated.
- [x] Checkpoint 8.2: Retrieval mode returns opposing evidence candidates.
- [x] Checkpoint 8.3: Output separates contradictions and ambiguities.
- [x] Checkpoint 8.4: Report UI renders side-by-side evidence.
- [x] Checkpoint 8.5: All three seeded themes pass regression checks.

### Verification Evidence

- `python3 -m compileall apps/api/app apps/worker/worker`
- `docker compose -f infra/compose/compose.yaml build api web worker`
- `docker compose -f infra/compose/compose.yaml up -d api web worker`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app`
- `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with `38 passed`.
- Live seeded smoke through the web proxy: login `200`, matters `200`, and contradiction runs for `notice timing`, `payment approval authority`, and `defect knowledge` each returned one citation-backed contradiction with both viewer links opening `200`.

### Implementation Evidence

- `apps/api/app/schemas/workflow.py`
- `apps/api/app/services/contradictions.py`
- `apps/api/app/services/workflows.py`
- `apps/api/app/services/mock_model_client.py`
- `apps/api/app/scripts/seed_demo.py`
- `apps/api/app/tests/test_phase8_contradictions.py`
- `apps/web/components/contradictions-panel.tsx`
- `apps/web/app/matters/[matterId]/contradictions/page.tsx`
- `apps/web/app/api/matters/[matterId]/contradictions/route.ts`

### Exit Gate

Phase 8 is complete when Trace can surface notice timing, payment approval authority, and defect knowledge contradiction themes conservatively with citation-backed evidence.

### Known Dependencies

- Phase 3 retrieval.
- Phase 4 viewer.
- Phase 5 AI runs and citations.
- Phase 7 entities improve topic targeting but must not be the only path.

## Phase 9 - Issue Memo Generator

Status: Verified

Last tracked: 2026-04-20

### Goal

Generate first-pass issue memos that synthesize supporting facts, contrary facts, gaps, and next-review recommendations with citations.

### Feature List

- `memos`.
- Issue-focused retrieval mode.
- `issue_memo_v1`.
- Structured memo JSON.
- Rendered markdown.
- Editable memo detail screen.
- Citation-linked memo sections.
- Memo export integration.
- Required memo sections: `issue`, `answer_in_brief`, `supporting_facts`, `contrary_facts`, `gaps`, `next_documents_to_review`.

### Implementation Steps

1. Confirm `memos` schema fields.
2. Define `Memo.content_json` schema with the required memo sections.
3. Create prompt template `issue_memo_v1`.
4. Implement issue-focused retrieval using issue terms, entities, chronology events, contradiction candidates, and top-ranked chunks.
5. Generate structured memo JSON first.
6. Validate every required memo section exists.
7. Render markdown from structured JSON second.
8. Persist memo JSON, markdown, source run ID, status, title, and matter ID.
9. Link material memo claims to citations.
10. Build memo generation form.
11. Build editable memo detail screen.
12. Add citation navigation from memo sections to source pages.
13. Add export integration for markdown and DOCX.
14. Audit memo generation, edits, and exports.

### Completion Tracker

- [x] Step 9.1: Existing `memos` schema is used for matter-scoped issue memo persistence.
- [x] Step 9.2: `Memo.content_json` is validated against required sections: `issue`, `answer_in_brief`, `supporting_facts`, `contrary_facts`, `gaps`, and `next_documents_to_review`.
- [x] Step 9.3: `issue_memo_v1` is represented in persisted `ai_runs` and workflow metadata.
- [x] Step 9.4: Issue-focused evidence assembly combines contradiction-oriented evidence, search results, and top matter chunks.
- [x] Step 9.5: Structured memo JSON is produced before markdown rendering.
- [x] Step 9.6: Required memo sections are validated before persistence and edit saves.
- [x] Step 9.7: Markdown is rendered from structured JSON.
- [x] Step 9.8: Memo JSON, markdown, source run ID, status, title, and matter ID persist.
- [x] Step 9.9: Supporting and contrary facts include validated citation payloads.
- [x] Step 9.10: Memo generation form is available in the matter memo screen.
- [x] Step 9.11: Editable memo detail UI supports updating title and structured content.
- [x] Step 9.12: Memo citations deep-link to source document pages.
- [x] Step 9.13: Markdown and DOCX export routes work through the API and web proxy.
- [x] Step 9.14: Audit logs cover memo AI run start/completion, edits, and exports.

### Expected Behavior When Complete

- Users can generate a first-pass memo for a targeted issue.
- The memo has all required sections.
- Supporting and contrary facts are citation-backed.
- Gaps and next-review recommendations are explicit.
- Users can edit the memo without losing source traceability.
- Memo can be exported.
- The source `ai_run` records `issue_memo_v1` and `citation_check_v1` validation metadata.

### Test Criteria

- [x] Notice timeliness memo generates successfully.
- [x] Payment approval authority memo generates successfully.
- [x] Memo JSON validates required sections.
- [x] Material supporting facts have citations.
- [x] Material contrary facts have citations.
- [x] Gaps can be present without citations if they are framed as gaps.
- [x] Memo markdown renders cleanly.
- [x] Memo edit persists.
- [x] Memo Markdown export succeeds.
- [x] Memo DOCX export succeeds.
- [x] Unauthorized users cannot create, read, edit, or export memos for matters they do not belong to.
- [x] AI run validation metadata and citation rows persist.

### Checkpoints

- [x] Checkpoint 9.1: Memo schema and persistence work.
- [x] Checkpoint 9.2: Issue retrieval mode returns useful evidence.
- [x] Checkpoint 9.3: Structured memo output validates.
- [x] Checkpoint 9.4: Memo detail UI renders citations.
- [x] Checkpoint 9.5: Editing works.
- [x] Checkpoint 9.6: Export integration works.

### Verification Evidence

- `python3 -m compileall apps/api/app apps/worker/worker`
- `docker compose -f infra/compose/compose.yaml build api worker`
- `docker compose -f infra/compose/compose.yaml up -d api worker`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app`
- `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with `42 passed`.
- Live seeded smoke through the web proxy: login `200`, Acme matter lookup `200`, notice-timeliness memo creation `201`, AI run lookup `200`, citation viewer URL `200`, memo patch `200`, Markdown export `200`, and DOCX export `200`.
- Live smoke returned two supporting facts, two contrary facts, validated citations, `issue_memo` source run metadata, `citation_check_v1` validation metadata, `994` Markdown bytes, and `37072` DOCX bytes.

### Implementation Evidence

- `apps/api/app/schemas/workflow.py`
- `apps/api/app/services/memos.py`
- `apps/api/app/services/workflows.py`
- `apps/api/app/services/mock_model_client.py`
- `apps/api/app/api/routes/workflows.py`
- `apps/api/app/tests/test_phase9_memos.py`
- `apps/web/components/memo-panel.tsx`
- `apps/web/app/matters/[matterId]/memo/page.tsx`
- `apps/web/app/api/matters/[matterId]/memos/route.ts`
- `apps/web/app/api/memos/[memoId]/route.ts`
- `apps/web/app/api/memos/[memoId]/export.md/route.ts`
- `apps/web/app/api/memos/[memoId]/export.docx/route.ts`

### Exit Gate

Phase 9 is complete when a user can generate a first-pass memo on notice timeliness or payment approval authority and verify every material section against citations.

### Known Dependencies

- Phase 3 retrieval.
- Phase 4 viewer.
- Phase 5 AI runs and citations.
- Phase 6 chronology is useful context.
- Phase 8 contradictions are useful context.

## Phase 10 - Exports, Audit Hardening, Seed Modes, Docs, and Evals

Status: Verified

Last tracked: 2026-04-20

### Goal

Harden the MVP into a reproducible demo and early-pilot system with export jobs, audit coverage, seed data modes, observability hooks, documentation, and an eval harness.

### Feature List

- `export_jobs`.
- Optional `saved_searches`.
- Memo Markdown export.
- Memo DOCX export.
- Chronology CSV export.
- Chronology DOCX export.
- Audit coverage for uploads, document views, AI runs, exports, auth, and matter changes.
- Structured logs.
- Request IDs.
- Job IDs.
- Latency metrics hooks.
- Retryable failure surfacing.
- Seed Mode A: raw-ingestion seed as source of truth.
- Seed Mode B: fast bootstrap from processed artifacts.
- README, architecture, local dev, prompts, evals, and seed data docs.
- Eval runner.
- AI run and audit trail screens.

### Implementation Steps

1. Confirm `export_jobs` schema fields.
2. Add optional `saved_searches` only if needed for demo or workflow continuity.
3. Implement `Exporter` contract.
4. Implement export job lifecycle: queued, running, completed, failed.
5. Implement memo markdown export.
6. Implement memo DOCX export.
7. Implement chronology CSV export.
8. Implement chronology DOCX export.
9. Store export artifacts in object storage.
10. Implement `GET /exports/{export_id}` for status and download metadata.
11. Add audit logs for upload, document view, search, AI run, memo generation, chronology generation, contradiction generation, export creation, and export download.
12. Add request IDs to API logs and responses.
13. Add job IDs to worker logs.
14. Add structured logs with `structlog`.
15. Add Prometheus-style metrics hooks for request latency, job duration, OCR duration, retrieval latency, model latency, and export duration.
16. Surface retryable failures in UI.
17. Build seed Mode A that ingests raw files through the real pipeline.
18. Build seed Mode B that loads processed artifacts for fast local bootstrap.
19. Expand `seed_truth/acme_truth.json` with canonical entities, aliases, events, contradictions, golden questions, expected concepts, and expected source documents.
20. Implement `EvalRunner` against the seed truth map.
21. Add docs or update docs for README, architecture, local dev, prompts, evals, and seed data.
22. Add AI run detail page.
23. Add audit trail page.

### Completion Tracker

- [x] Step 10.1: `export_jobs` schema fields are represented in the domain model and API schema.
- [x] Step 10.2: `saved_searches` remains optional and was not required for MVP demo continuity.
- [x] Step 10.3: Exporter behavior is centralized in `app.services.exports`.
- [x] Step 10.4: Export jobs move through queued, running, completed, and failed states with safe errors.
- [x] Step 10.5: Memo Markdown export creates an export job, stores an artifact, and returns the file.
- [x] Step 10.6: Memo DOCX export creates an export job, stores an artifact, and returns the file.
- [x] Step 10.7: Chronology CSV export creates an export job, stores an artifact, and returns the file.
- [x] Step 10.8: Chronology DOCX export creates an export job, stores an artifact, and returns the file.
- [x] Step 10.9: Export artifacts are stored in MinIO/object storage under `exports/{matter_id}/{export_id}`.
- [x] Step 10.10: `GET /exports/{export_id}` returns status and download metadata.
- [x] Step 10.11: Export downloads are supported through `/exports/{export_id}/download`.
- [x] Step 10.12: Audit logs cover search, uploads, document views, AI runs, workflow outputs, export creation, export completion, export download, edits, and auth paths.
- [x] Step 10.13: Request IDs and structured request logs are emitted by API middleware.
- [x] Step 10.14: Worker export job IDs are handled by the export actor path.
- [x] Step 10.15: `structlog` JSON request logs are configured.
- [x] Step 10.16: `/metrics` exposes Prometheus-style request counters and latency gauges.
- [x] Step 10.17: Export failure states persist safe error classes.
- [x] Step 10.18: Seed Mode A raw ingestion works through `python -m app.scripts.seed_demo --mode raw`.
- [x] Step 10.19: Seed Mode B fast bootstrap works through `python -m app.scripts.seed_demo --mode fast`.
- [x] Step 10.20: `seed_truth/acme_truth.json` includes canonical entities, aliases, contradictions, golden questions, expected concepts, and expected documents.
- [x] Step 10.21: `EvalRunner` checks Acme entities, golden questions, contradictions, exports, and branding.
- [x] Step 10.22: README, architecture, local dev, prompts, evals, and seed data docs exist at repo root.
- [x] Step 10.23: AI run detail UI is available from workflow run links.
- [x] Step 10.24: Audit trail UI and audit CSV export are available from matter settings.

### Expected Behavior When Complete

- Users can export chronology and memo artifacts.
- Export jobs have visible status and safe failure states.
- Major workflows create audit logs.
- Logs contain enough context to debug requests and jobs.
- A fresh developer can run the stack and load the Acme matter.
- The demo flow works without tribal knowledge.
- Eval runner checks the seeded matter for key regressions.
- Matter settings shows a recent audit trail and audit CSV export.
- AI run IDs link to an inspectable workflow detail page.

### Test Criteria

- [x] Memo markdown export succeeds.
- [x] Memo DOCX export succeeds.
- [x] Chronology CSV export succeeds.
- [x] Chronology DOCX export succeeds.
- [x] Export failure stores safe error details.
- [x] Export download is matter-authorized.
- [x] Audit logs exist for all major workflows.
- [x] Request IDs appear in API logs.
- [x] Job IDs are part of export worker processing.
- [x] Seed Mode A ingests raw demo data.
- [x] Seed Mode B bootstraps quickly from processed artifacts.
- [x] Eval runner checks concept coverage, citation existence, contradiction handling, exports, and branded smoke coverage.
- [x] Fresh local setup documentation is accurate enough for the current stack.

### Checkpoints

- [x] Checkpoint 10.1: Export job lifecycle works.
- [x] Checkpoint 10.2: Required export formats work.
- [x] Checkpoint 10.3: Audit coverage is broad enough for demo.
- [x] Checkpoint 10.4: Structured logs and request/job IDs exist.
- [x] Checkpoint 10.5: Seed Mode A works.
- [x] Checkpoint 10.6: Seed Mode B works.
- [x] Checkpoint 10.7: Eval runner works.
- [x] Checkpoint 10.8: Docs support a fresh developer.
- [x] Checkpoint 10.9: Audit and AI run inspection screens exist.

### Verification Evidence

- `python3 -m compileall apps/api/app apps/worker/worker`
- `docker compose -f infra/compose/compose.yaml build api web worker`
- `docker compose -f infra/compose/compose.yaml up -d api web worker`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app`
- `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with `46 passed`.
- `curl -s -D - http://localhost:8000/health` returned `x-request-id`.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.seed_demo --mode fast` passed.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.seed_demo --mode raw` passed.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.eval_seed` passed all Acme MVP checks.
- Live Phase 10 web-proxy smoke: login `200`, Acme matter lookup `200`, chronology generation `200`, CSV export `200`, DOCX export `200`, export status `200`, export download `200`, audit list `200`, audit CSV `200`, and API metrics `200`.
- Live smoke returned `10` chronology events, completed CSV export `2342ee51-4bc5-4b30-920d-bab418f682db`, completed DOCX export `d7d19d6a-4255-4a0c-9844-797e79af9feb`, `113` audit rows, and matching DOCX download size `37667` bytes.
- Live AI run detail smoke opened `/matters/{matter_id}/ai-runs/20f07d56-d644-40aa-9786-6adfdfe039bd` with `200`.

### Implementation Evidence

- `apps/api/app/services/exports.py`
- `apps/api/app/services/evals.py`
- `apps/api/app/services/chronology.py`
- `apps/api/app/api/routes/exports.py`
- `apps/api/app/api/routes/audit.py`
- `apps/api/app/api/routes/workflows.py`
- `apps/api/app/core/metrics.py`
- `apps/api/app/main.py`
- `apps/api/app/scripts/seed_demo.py`
- `apps/api/app/scripts/eval_seed.py`
- `apps/api/app/tests/test_phase10_exports_audit_evals.py`
- `apps/worker/worker/tasks.py`
- `apps/web/components/audit-trail.tsx`
- `apps/web/components/ai-run-detail.tsx`
- `apps/web/components/chronology-panel.tsx`
- `apps/web/components/memo-panel.tsx`
- `apps/web/app/matters/[matterId]/settings/page.tsx`
- `apps/web/app/matters/[matterId]/ai-runs/[runId]/page.tsx`
- `apps/web/app/api/audit/route.ts`
- `apps/web/app/api/audit/export.csv/route.ts`
- `apps/web/app/api/exports/[exportId]/route.ts`
- `apps/web/app/api/exports/[exportId]/download/route.ts`
- `seed_data/raw/acme_matter`
- `seed_truth/acme_truth.json`
- `README.md`
- `ARCHITECTURE.md`
- `LOCAL_DEV.md`
- `PROMPTS.md`
- `EVALS.md`
- `SEED_DATA.md`

### Exit Gate

Phase 10 is complete when a fresh developer can run the stack, load the Acme matter, execute the demo flow, inspect the audit trail, and export a chronology and memo without tribal knowledge.

### Known Dependencies

- Phases 1-9.
- Object storage for export artifacts.
- Seed truth map.
- Worker job infrastructure.

## Phase 11 - PRD Eval Breadth After MVP Gates

Status: Verified

Last tracked: 2026-04-20

### Goal

Expand regression coverage beyond the canonical Acme matter after MVP gates pass, without delaying the core vertical slice.

### Feature List

- Employment dispute truth pack.
- Internal investigation truth pack.
- Invoice/payment dispute truth pack.
- Lightweight raw or processed corpora for each truth pack.
- Eval harness support for multiple corpora.
- Regression reporting by corpus and workflow.
- Branded smoke coverage for Trace shells and docs.

### Implementation Steps

1. Confirm all MVP gates are green for Acme before starting Phase 11.
2. Define compact truth map schema reuse for non-Acme corpora.
3. Create an employment dispute corpus with key entities, timeline events, golden questions, and at least one ambiguity or contradiction.
4. Create an internal investigation corpus with witness/entity emphasis, chronology events, and contradiction or inconsistency cases.
5. Create an invoice/payment dispute corpus with payment authority, invoice timing, approval conditions, and exportable memo topics.
6. Add these truth packs to seed/eval docs.
7. Extend `EvalRunner` to run selected corpora individually or as a suite.
8. Track concept coverage, citation existence, retrieval isolation, ambiguity handling, contradiction precision, chronology completeness, and memo section coverage.
9. Keep corpora lightweight so local evals remain feasible on constrained hardware.
10. Add CI-friendly smoke mode if CI exists later.

### Completion Tracker

- [x] Step 11.1: Acme MVP gates were re-verified before Phase 11 implementation.
- [x] Step 11.2: Non-Acme truth packs reuse the same product/corpus/golden-question structure with `corpus_type: static_regression`.
- [x] Step 11.3: Employment dispute truth pack exists with entities, documents, events, golden questions, contradiction, ambiguity, and memo topic.
- [x] Step 11.4: Internal investigation truth pack exists with witness/entity emphasis, chronology events, inconsistency, ambiguity, and memo topic.
- [x] Step 11.5: Invoice/payment dispute truth pack exists with payment authority, invoice timing, conditional approval, ambiguity, and memo topic.
- [x] Step 11.6: Seed/eval docs document Phase 11 regression packs and commands.
- [x] Step 11.7: `EvalSuiteRunner` supports Acme, a selected regression corpus, regression-only, and all-corpus modes.
- [x] Step 11.8: Static regression checks cover concept coverage, source-document/citation existence, contradiction evidence, chronology coverage, ambiguity coverage, memo section coverage, and branding.
- [x] Step 11.9: Regression corpora are embedded lightweight JSON packs and do not require model or OCR add-ons.
- [x] Step 11.10: CLI smoke commands are suitable for future CI: `make eval-regression` and `make eval-all`.

### Expected Behavior When Complete

- The eval harness reflects the PRD's broader test-matter intent.
- Acme remains the canonical MVP demo matter.
- Additional corpora catch regressions in retrieval, citation validation, chronology, contradiction detection, and memo generation.
- Local developers can choose lightweight eval runs without starting model or OCR add-ons by default.
- Eval reports separate `acme_mvp` from `employment_dispute`, `internal_investigation`, and `invoice_payment_dispute`.

### Test Criteria

- [x] Employment corpus eval can run.
- [x] Internal investigation corpus eval can run.
- [x] Invoice/payment corpus eval can run.
- [x] Each corpus has golden questions.
- [x] Each corpus checks citation/source-document existence.
- [x] Each corpus checks expected concepts.
- [x] Ambiguity handling is tested in each regression corpus.
- [x] Branded smoke checks confirm Trace naming in truth packs.
- [x] Eval report separates Acme MVP gates from broader regression gates.

### Checkpoints

- [x] Checkpoint 11.1: Acme MVP gates are complete.
- [x] Checkpoint 11.2: Truth map schema supports multiple corpora.
- [x] Checkpoint 11.3: Employment corpus exists.
- [x] Checkpoint 11.4: Internal investigation corpus exists.
- [x] Checkpoint 11.5: Invoice/payment corpus exists.
- [x] Checkpoint 11.6: Multi-corpus eval runner works.
- [x] Checkpoint 11.7: Reports distinguish MVP and regression breadth.

### Verification Evidence

- `python3 -m compileall apps/api/app apps/worker/worker`
- `python3 -m json.tool` passed for all three Phase 11 truth packs.
- `docker compose -f infra/compose/compose.yaml build api worker`
- `docker compose -f infra/compose/compose.yaml up -d api worker`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app`
- `docker compose -f infra/compose/compose.yaml exec -T web pnpm typecheck`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with `50 passed`.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.seed_demo --mode fast` passed before the full suite.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.eval_seed --suite regression --corpus invoice_payment_dispute` passed.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.eval_seed --suite regression` passed with all three regression corpora green.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run python -m app.scripts.eval_seed --suite all` passed with `4` total reports, `4` passed, `0` failed.

### Implementation Evidence

- `seed_truth/employment_dispute_truth.json`
- `seed_truth/internal_investigation_truth.json`
- `seed_truth/invoice_payment_dispute_truth.json`
- `apps/api/app/services/evals.py`
- `apps/api/app/scripts/eval_seed.py`
- `apps/api/app/tests/test_phase11_eval_breadth.py`
- `README.md`
- `EVALS.md`
- `SEED_DATA.md`
- `Makefile`

### Exit Gate

Phase 11 is complete when the eval harness can run Acme plus three lightweight regression corpora and report workflow-specific pass/fail coverage without blocking the default local development stack.

### Known Dependencies

- Phase 10 eval harness.
- Stable seed/truth map format.
- MVP workflows passing on Acme.

## Phase 12 - Semantic Retrieval Upgrade

Status: Verified

Last tracked: 2026-04-21

### Goal

Add a real semantic embedding provider for Trace while preserving the lightweight default local development path.

### Feature List

- `TRACE_EMBEDDING_PROVIDER` configuration with `hash` and `sentence_transformer` providers.
- `LocalHashEmbeddingClient` remains the deterministic default for CI, constrained laptops, and default Docker use.
- `SentenceTransformerEmbeddingClient` provides true semantic embeddings with `sentence-transformers/all-MiniLM-L6-v2`.
- Lazy optional dependency loading so semantic mode is only required when explicitly enabled.
- 384-dimensional vector validation to preserve the existing pgvector schema.
- Vector normalization before persistence or ranking.
- Clear runtime errors for missing semantic dependencies, unknown providers, and wrong-dimension models.
- Local development docs explain semantic setup, re-ingestion requirements, and quality caveats.
- Test coverage for provider selection, semantic vector normalization, and RRF/search compatibility.

### Implementation Steps

1. Add `embedding_provider` to API settings with default value `hash`.
2. Add `TRACE_EMBEDDING_PROVIDER=hash` to `.env.example`.
3. Keep `TRACE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` as the default semantic model.
4. Keep `LocalHashEmbeddingClient` unchanged as the default lightweight provider.
5. Add `SentenceTransformerEmbeddingClient` behind the existing `EmbeddingClient` interface.
6. Import `sentence_transformers` lazily only when semantic mode is used.
7. Normalize semantic vectors to unit length.
8. Validate semantic vector count and dimension before returning embeddings.
9. Make `get_embedding_client()` dispatch by provider name.
10. Add optional `semantic` dependencies to API and worker package metadata.
11. Update local development docs with semantic install and `.env` instructions.
12. Document that documents must be re-ingested or re-embedded after changing embedding providers.
13. Add unit tests for hash default behavior, unknown provider errors, semantic fake-model behavior, missing dependency errors, and wrong dimensions.
14. Extend search verification so RRF metadata remains visible with lexical and vector ranks.
15. Move and revise the internal recruiter-facing cleanup prompt so future README work can honestly describe semantic mode.

### Completion Tracker

- [x] Step 12.1: `embedding_provider` setting exists and defaults to `hash`.
- [x] Step 12.2: `.env.example` includes `TRACE_EMBEDDING_PROVIDER=hash`.
- [x] Step 12.3: `TRACE_EMBEDDING_MODEL` still defaults to `sentence-transformers/all-MiniLM-L6-v2`.
- [x] Step 12.4: Hash embeddings remain deterministic, 384-dimensional, and default.
- [x] Step 12.5: `SentenceTransformerEmbeddingClient` exists behind `EmbeddingClient`.
- [x] Step 12.6: Semantic dependency/model loading is lazy.
- [x] Step 12.7: Semantic vectors are normalized.
- [x] Step 12.8: Semantic vector count and dimension are validated.
- [x] Step 12.9: Provider dispatch supports `hash` and `sentence_transformer`.
- [x] Step 12.10: API and worker package metadata define optional `semantic` extras.
- [x] Step 12.11: Local docs explain default hash mode and opt-in semantic mode.
- [x] Step 12.12: Docs explain re-ingestion is required after switching providers.
- [x] Step 12.13: Tests cover provider selection and semantic error paths.
- [x] Step 12.14: Phase 3 search tests verify RRF rank metadata remains exposed.
- [x] Step 12.15: Local internal agent prompt was revised for accurate semantic claims and kept out of the public repo.

### Expected Behavior When Complete

- Default local development still requires no model download, no GPU, and no semantic dependency install.
- Search and ingestion continue to work with deterministic hash embeddings by default.
- Enabling `TRACE_EMBEDDING_PROVIDER=sentence_transformer` uses a real sentence-transformer model for semantic embeddings.
- Semantic mode stores vectors in the existing pgvector column without a schema migration.
- If semantic dependencies are missing, Trace fails clearly instead of silently falling back.
- After semantic mode is enabled and documents are re-ingested, paraphrase-style queries can benefit from true semantic vector recall.

### Test Criteria

- [x] Hash embeddings are deterministic and 384-dimensional.
- [x] Default provider selection returns `LocalHashEmbeddingClient`.
- [x] Unknown providers raise a safe configuration error.
- [x] Semantic provider can be exercised with a fake sentence-transformer model.
- [x] Semantic provider normalizes vectors.
- [x] Semantic provider reports missing optional dependency clearly.
- [x] Semantic provider rejects non-384-dimensional model output.
- [x] Existing ingestion persists embeddings as before.
- [x] Search remains matter-scoped.
- [x] RRF metadata still reports lexical and vector rank evidence.
- [x] Existing Phase 1-11 behavior remains covered by the full test suite.

### Checkpoints

- [x] Checkpoint 12.1: Provider config exists.
- [x] Checkpoint 12.2: Hash remains default.
- [x] Checkpoint 12.3: Semantic client exists and is lazy-loaded.
- [x] Checkpoint 12.4: Optional semantic dependency metadata exists.
- [x] Checkpoint 12.5: Semantic setup docs exist.
- [x] Checkpoint 12.6: Unit tests cover semantic provider behavior.
- [x] Checkpoint 12.7: Existing retrieval tests remain green.

### Verification Evidence

- `python3 -m compileall apps/api/app apps/worker/worker`
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest app/tests/test_phase12_semantic_embeddings.py app/tests/test_phase3_ingestion_search.py` passed with `11 passed`.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run ruff check app` passed.
- `docker compose -f infra/compose/compose.yaml exec -T api uv run pytest` passed with `56 passed`.

### Exit Gate

Phase 12 is complete when Trace can run unchanged in lightweight hash mode by default, and can opt into a real 384-dimensional sentence-transformer embedding provider without API or database schema changes.

### Known Dependencies

- Phase 3 ingestion and search corpus.
- Existing pgvector-compatible 384-dimensional embedding column.
- Optional `sentence-transformers` dependency for semantic mode.
- Re-ingestion or re-embedding after switching providers.

## Phase 13 - Product Launch Path

Status: Designed - Future Product Phase

Last tracked: 2026-04-21

This phase is documented as the productization path for Trace. It is not part of the MVP or the RAG research core. Implementation is planned for a future cycle.

### Goal

Create a public-facing product surface and deployment path for Trace while keeping the authenticated legal workspace private and invite-only.

### Feature List

- Public landing page at `/`.
- Existing-user sign-in at `/sign-in`.
- Authenticated redirect to `/matters`.
- Private matter workspace routes behind auth.
- Request access, book demo, and security posture CTAs.
- Demo access guidance for local and private demo deployments.
- VPS/private demo deployment documentation.
- Invite-only access flow.
- SEO and OpenGraph metadata for public discovery.

### Implementation Steps

1. Audit the current root page and identify internal shell copy to preserve or replace.
2. Build the public landing page at `/` with hero, problem, product, trust loop, privacy, and CTA sections.
3. Design a responsive landing page with premium typography, gradients, and restrained motion.
4. Add `Request Access`, `Book a Demo`, and `View Security Posture` CTAs.
5. Ensure the landing page does not expose authenticated routes, document data, matter names, or matter content.
6. Separate public routes from authenticated routes in Next.js middleware or route guards.
7. Keep `/sign-in` available for existing users.
8. Redirect authenticated users from `/sign-in` to `/matters`.
9. Redirect unauthenticated access to `/matters/*` to `/sign-in`.
10. Add a demo access section for local and private-demo use.
11. Add environment-based deployment target configuration for local, VPS, and cloud/private hosting.
12. Document VPS deployment with web, API, worker, Postgres, Redis, and MinIO.
13. Add remote-friendly health/readiness checks and monitoring notes.
14. Add invite-only access through allow-list or admin provisioning.
15. Add SEO title, description, and OpenGraph metadata.
16. Audit remaining internal-facing UI copy and convert it to user-facing language.
17. Test the full public landing to sign-in to workspace to sign-out to landing flow.

### Expected Behavior When Complete

- Visitors can understand Trace without signing in.
- Existing users can sign in and land directly in matter workspaces.
- Private matter data never appears on public pages.
- Demo and pilot operators have clear deployment/access options.
- Public copy positions Trace as private, matter-scoped, citation-grounded legal discovery software.

### Test Criteria

- Landing page renders without authentication.
- Landing page CTAs work or point to intentional placeholders.
- Authenticated users can reach `/matters`.
- Unauthenticated users cannot reach `/matters/*`.
- `/sign-in` redirects authenticated users to `/matters`.
- Public pages do not fetch matter, document, AI run, or audit data.
- SEO/OpenGraph metadata renders.
- Local demo instructions still work.
- Private demo deployment docs are complete enough for a fresh operator.

### Checkpoints

- Checkpoint 13.1: Public landing page exists.
- Checkpoint 13.2: Authenticated app routes are separated.
- Checkpoint 13.3: CTA path exists.
- Checkpoint 13.4: Demo access guidance exists.
- Checkpoint 13.5: VPS/private deployment docs exist.
- Checkpoint 13.6: Invite-only access path exists.
- Checkpoint 13.7: Public-to-private flow is tested.

### Exit Gate

Phase 13 is complete when Trace has a public landing page, a protected authenticated workspace, and documented local/private-demo deployment paths without exposing legal matter data publicly.

### Known Dependencies

- Stable authenticated app shell.
- Phase 1 auth and RBAC.
- Deployment target decision.
- Product/security copy review before public launch.

## MVP Acceptance Checklist

The MVP is complete only when all of these are true:

- A user can sign in.
- A user can create or open a matter.
- A user can upload mixed documents.
- Ingestion parses, OCRs when needed, chunks, embeds, and indexes documents.
- Search returns matter-scoped results.
- Viewer opens source pages from search results and citations.
- Grounded Q&A returns validated citations or insufficient evidence.
- Chronology generation produces citation-backed events.
- Entity pages show evidence-backed mentions and summaries.
- Contradiction finder surfaces known seeded contradiction themes conservatively.
- Issue memo generation produces required sections with citation-backed material claims.
- At least one chronology export succeeds.
- At least one memo export succeeds.
- Major workflows create `ai_runs` where relevant.
- Major workflows create `audit_logs`.
- The seeded Acme truth map supports evals.
- Fresh local setup is reproducible from docs.
- Default local development does not require local vLLM or heavy OCR services.

## End-to-End Demo Flow

Use this as the canonical demo script once MVP gates are implemented:

1. Start the lightweight core stack.
2. Load or seed `Acme Industrial v. Northshore Supply`.
3. Sign in as a seeded attorney.
4. Open the Acme matter.
5. Upload or verify seeded mixed documents.
6. Confirm the scanned inspection report OCR status and searchability.
7. Search the corpus for defect knowledge.
8. Ask: "What evidence suggests Northshore knew of the defect before shipment?"
9. Inspect citations in the viewer.
10. Generate a chronology.
11. Sort and filter chronology events.
12. Open Jane Mercer's entity page.
13. Run contradiction finder for payment approval authority.
14. Generate a notice-timeliness memo.
15. Export a memo or chronology artifact.
16. View the AI run record.
17. View the audit trail.

## Seed and Eval Expectations

The Acme seed truth map must remain the canonical MVP truth source.

Required seed truth coverage:

- Product name: Trace.
- Formal product name: Trace - Sovereign Discovery Copilot.
- Matter: Acme Industrial v. Northshore Supply.
- Canonical entities and aliases.
- Key chronology events.
- Known contradiction topics.
- Golden demo questions.
- Expected concepts.
- Expected source documents.
- OCR challenge document.

Required contradiction topics:

- Notice timing.
- Payment approval authority.
- Defect knowledge.

Required golden demo question coverage:

- Northshore defect knowledge before shipment.
- Invoice approval authority.
- Notice timing conflict.
- Chronology of notice and payment events.
- First-pass memo on notice timeliness.

Eval checks should cover:

- Matter-scoped retrieval.
- Concept coverage.
- Citation existence.
- Citation source validity.
- Ambiguity handling.
- Chronology event quality.
- Contradiction precision.
- Memo section completeness.
- Export availability.
- Trace branding smoke checks.

## Deferred Non-MVP Items

Do not allow these items to block MVP completion:

- SSO/SAML.
- Enterprise antivirus integration.
- Advanced PST/OST ingestion.
- Cross-matter search.
- Cross-matter entity linking.
- Collaborative annotation.
- Redaction workflows.
- Chain-of-thought storage.
- Full privilege review automation.
- PDF export polish if Markdown, DOCX, and CSV are solid.
- Kubernetes production hardening beyond keeping the architecture deployment-ready.
- Large local vLLM as a default developer dependency.
- Heavy local OCR as a default developer dependency.
