# Known limitations

This file states what Trace does **not** do yet. It is updated as V3 work lands; anything not
listed under "Verified" in the README is planned, not shipped.

## Model and inference

- `OpenAICompatibleModelClient` currently delegates every call to `MockModelClient`. No real
  model request is made by any workflow. (Being replaced in V3 PR-01.)
- The optional `vllm` Compose service is itself a mock server (`infra/docker/mock-vllm.Dockerfile`).
- Mock output is deterministic and keyword-driven. It is suitable for tests, not for judging quality.

## Retrieval

- Vector similarity is computed in Python over candidate chunks loaded from PostgreSQL, not by
  pgvector in SQL.
- The default embedding provider is a deterministic local hash, which is not semantic. The
  optional `sentence_transformer` provider has only been tested against a fake model.
- Chunk "token" counts are whitespace word counts.

## Citations and evidence

- Citation validation checks that cited chunks belong to the matter and that the quoted string
  appears in stored text. A real quote can still be incomplete, outdated, out of context, or
  contrary to the claim. Quote presence is not entailment.
- Documents are not versioned. Re-uploading creates a new document; there is no record of which
  version of a source a decision relied on.

## Documents

- OCR is disabled by default; scanned PDFs without a text layer produce no searchable text.
- No layout-aware parsing: tables and multi-column PDFs are flattened.

## Security and operations

- Local portfolio application. It has not been deployed for external users, audited, or
  penetration tested.
- Development defaults include a placeholder secret key and an insecure demo login. The API now
  refuses to start with these when `TRACE_ENV` is not `development` or `test`.
- The test suite runs against the same database as the local dev stack.

## Evaluation

- Current evals use synthetic seed data and static truth packs authored alongside the system.
  They are regression checks, not a held-out measurement of accuracy.
- No lawyer or qualified reviewer has validated any output.
