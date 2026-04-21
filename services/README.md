# Trace Services Contracts

This directory captures subsystem boundaries shared across the Trace build:

- `ingestion`: parser, OCR, chunking, metadata, entities, events
- `retrieval`: search, rerank, evidence assembly
- `ai`: model client, prompt catalog, schemas, workflow orchestration
- `exports`: artifact builders and export pipelines

These folders are intentionally implementation-light today; the concrete FastAPI service code lives under `apps/api/app/services` while the contracts here preserve the target architecture from the PRD.
