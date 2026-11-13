# Known limitations

This file states what Trace does **not** do yet. It is updated as V3 work lands; anything not
listed under "Verified" in the README is planned, not shipped.

## Model and inference

- V3 claim extraction and support assessment call a real model through one OpenAI-compatible
  client: `local` (Ollama/llama.cpp/vLLM, default) or `hosted` (requires explicit egress
  acknowledgement). `mock` is a deterministic rule set used only when configured (tests, CI).
- Real-model tests are opt-in (`make test-real-model`) and are not run in CI.
- V1 workflows (Q&A panel, chronology, entities, contradictions, memos) still run on the
  deterministic legacy engine and are labeled `trace-legacy-deterministic` in AI-run records.
- A 7B local model is noticeably weaker than frontier hosted models at strict JSON and at subtle
  conditional language. Measured failure rates are reported in the eval results, not assumed.

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
