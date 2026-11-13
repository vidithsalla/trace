# Trace V3 architecture

Trace V3 is an evidence-review workflow: propose claims from documents, show the passages for
and against each claim, record a human decision against the exact sources seen, and flag that
decision when the sources change.

## Trust layers

Three questions are answered by three different mechanisms and stored in separate columns.
No screen, export or API response merges them into one "validated" flag.

| Layer | Question | Mechanism | Stored in |
| --- | --- | --- | --- |
| Source integrity | Does the quoted passage exist, unchanged, in this document version and matter? | Deterministic (`services/source_gate.py`) | `claim_revisions.source_gate_state`, `claim_evidence.quote_integrity` |
| Support suggestion | Do the passages support, qualify or contradict the claim? | Model candidate (`services/llm/engine.py`) | `claim_revisions.relation_candidate`, `claim_evidence.relation_candidate` |
| Human decision | Has an authorized reviewer accepted this revision with this evidence set? | Append-only review events (`services/change_control.py`) | `review_events`, projected to `claims.review_state` |

Two more states are tracked independently: `claims.basis_state` (`CURRENT` / `STALE_SOURCE`) and
`claims.coverage_state` (`CURRENT` / `POTENTIAL_NEW_EVIDENCE`).

## Request flow

```text
Browser ── same-origin ──> Next.js (Origin check, allowlisted /api/v3 proxy)
                                │
                                ▼
                         FastAPI (session → user; membership → matter role)
             ┌──────────────────┼────────────────────────┐
             ▼                  ▼                        ▼
   Upload / new version   POST /analyses           POST /reviews, /revisions
   (bytes → storage,      (pin snapshot, enqueue)  (row lock + optimistic checks)
    version STAGING)            │
             │                  ▼  Redis / Dramatiq (IDs only)
             ▼            Worker: retrieve in SQL → propose claims (model)
   Worker: parse → spans        → source gate → counterevidence search
   → embeddings → publish       → support assessment (model) → persist
   atomically → drift check
```

Only the web UI port is published, and only on `127.0.0.1`. API, Postgres and Redis are reachable
on the internal Docker network only (`infra/compose/compose.ports.yaml` exposes them for development).

## Source identity

- `documents` is the logical document. `document_versions` holds immutable bytes (SHA-256,
  storage key, revision number). A correction is a new revision; the old one becomes `RETIRED`,
  never deleted or rewritten.
- `extraction_versions` is one parse of one version with one parser profile. `extraction_pages`
  holds the normalized page text it produced.
- `source_spans` are the citation units: zero-based, half-open `[start, end)` offsets over
  NFC-normalized page text, counted in Unicode code points, with the quote's SHA-256.
- Composite foreign keys `(matter_id, id)` make cross-matter references impossible at the
  database level. Triggers reject updates to published text, offsets, embeddings, claim
  revisions, claim evidence, review events and packets.
- Publishing an extraction happens in one transaction with a row lock on the version, so a
  crashed or duplicate worker job can never expose a half-built extraction or create duplicates.

## Corpus snapshots

An analysis pins `corpus_snapshots`: the set of current extraction versions, content-addressed
by a SHA-256 of the sorted manifest. All retrieval for that run joins through the snapshot, so a
document published mid-run cannot leak into it, and the run can be reconstructed later.

## Retrieval

`services/retrieval_v3.py` works on spans, inside one snapshot, with the matter filter in SQL:

| Profile | Definition |
| --- | --- |
| `lexical_v1` | PostgreSQL full-text search (`ts_rank_cd`) on span text |
| `hash_hybrid_baseline` | Lexical + the original deterministic hash vectors (not semantic), RRF k=60 |
| `semantic_exact_v2` | all-MiniLM-L6-v2 via Ollama, exact pgvector `<=>` in SQL |
| `semantic_hybrid_v2` | Lexical + semantic, RRF k=60 (default when Ollama embeddings are configured) |

Exact scan is used on purpose: matters are small, and an ANN index is an optimization to add only
when measured latency calls for it.

**Counterevidence pass.** For each proposed claim, a second search looks for spans that share
the claim's anchors (identifiers, names) *and* contain qualification or reversal language
("subject to", "hold", "not", "correction", ...). PostgreSQL's English text configuration drops
"not", "no" and "but" as stopwords, so this pass matches its challenge terms with a word-boundary
regex on raw text. A semantic neighbour search of the claim is fused in when available.

## Model contract

`services/llm/` is one OpenAI-compatible HTTP client used for both `local` (Ollama, llama.cpp,
vLLM) and `hosted` providers. There is no fallback between providers.

- The model sees passages tagged with server-issued references (`ev_01`). It never sees
  database IDs; references it invents are rejected by the source gate as `UNKNOWN_EVIDENCE_REF`.
- Outputs are parsed into strict Pydantic models (`extra="forbid"`); invalid output is a typed
  `schema_error`, never repaired.
- The overall support label is recomputed deterministically from per-passage relations; the
  model's own overall label is stored only as a disagreement note.
- `hosted` refuses to start unless `TRACE_HOSTED_EGRESS_ACKNOWLEDGED=true` and the endpoint is
  https. `local` refuses a public-internet endpoint.
- Logs contain only call metadata (status, latency, token counts), never prompts or passages.

## Review and drift

- A review POST carries the expected claim revision, evidence-set digest and review sequence.
  The claim row is locked; any mismatch is `409`. Duplicate submissions with the same
  idempotency key return the original event. The actor always comes from the session.
- ACCEPT additionally requires a verified source gate, a current basis and current coverage.
- When a document version is published, `on_version_published` marks every claim whose current
  revision cites an older version of that document `STALE_SOURCE` (deterministic), and raises
  `POTENTIAL_NEW_EVIDENCE` for reviewed claims whose terms overlap the new text (a cautious
  lexical candidate, detector `overlap-v1`).
- Re-check creates a new claim revision against a fresh snapshot; edits create a new revision
  with re-assessed relations. Decisions never carry over to a different revision.

## Evidence packets

`services/packets.py` builds `manifest.json`, `findings.json`, `packet.md` and
`checksums.sha256` from stored records only. The default policy exports only claims accepted
against current sources; `include_all_labeled` exports everything with explicit labels. Files are
integrity-checked against their stored SHA-256 on every download, and membership is re-checked on
every download.
