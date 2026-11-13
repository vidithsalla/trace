# Trace - Sovereign Discovery Copilot Architecture

Trace is a private, matter-scoped legal workflow system. The local monorepo contains `apps/web` for the Next.js 15 App Router UI, `apps/api` for the FastAPI domain/API layer, `apps/worker` for Dramatiq jobs, shared `packages/*`, service contract folders, Docker Compose infrastructure, raw seed data, and seed truth maps.

The core runtime is intentionally lightweight by default: web, API, worker, Postgres with pgvector and Redis, plus a filesystem object-storage volume. Model serving and OCR remain product-critical, but local vLLM/OCR containers are optional add-ons so Apple Silicon 8 GB machines can run the app comfortably.

Core invariants:

- Every matter-scoped record, retrieval result, AI run, citation, memo, event, export, and audit row must stay isolated to one matter.
- Evidence is stored before prose: structured JSON persists first, then markdown, DOCX, CSV, and UI views are rendered.
- AI workflows persist `ai_runs`, validated citations, conservative confidence metadata, and audit events.
- Exports are represented by `export_jobs`, stored in object storage, and downloadable only after matter access checks.
- Seed and eval tooling must keep the Acme demo reproducible without requiring a local model server.

Phase 10 adds operational hardening:

- Export job lifecycle for memo Markdown/DOCX and chronology CSV/DOCX.
- Object-storage-backed export artifacts.
- `/exports/{export_id}` status metadata and `/exports/{export_id}/download`.
- Audit filtering, audit CSV export, and a matter settings audit trail.
- Structured request logs and Prometheus-style `/metrics`.
- Fast and raw seed modes plus an Acme eval runner.
