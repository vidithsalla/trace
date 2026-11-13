# Security

Trace is an open-source portfolio project designed to run on your own machine with synthetic or
non-sensitive data. It has not had an external security audit or penetration test.

## Reporting a problem

Please open a GitHub issue for anything that is not exploitable, or use GitHub's private
vulnerability reporting ("Report a vulnerability" on the Security tab) for anything that is.
Issues of particular interest:

- reading or citing another matter's documents, runs, claims, spans or packets
- a review decision recorded for the wrong actor, revision or evidence set
- a superseded source passing as current, or a packet changing after creation
- uploaded document text influencing anything other than being displayed as evidence
- secrets, prompts or document text appearing in logs

## What the code enforces (and tests)

| Boundary | Enforcement | Tests |
| --- | --- | --- |
| Matter isolation | Membership check on every route; `matter_id` filter in SQL before text is read; composite `(matter_id, id)` foreign keys | `test_v3_02_review_pipeline.py::test_matter_isolation_through_model_input_and_api`, `test_v3_04_versions.py::test_cross_matter_span_reference_rejected_by_foreign_key` |
| Model output | Strict schema, server-issued evidence refs only, no tools, cannot write review state | `test_v3_01_model_contract.py`, `test_unknown_evidence_ref_is_invalid_and_blocks_acceptance`, `test_prompt_injection_text_never_changes_review_state` |
| Review integrity | Row lock, expected revision + evidence digest + review sequence, idempotency keys, session actor | `test_review_concurrency_idempotency_and_forged_actor`, `test_concurrent_opposite_reviews_exactly_one_wins` |
| Immutability | Database triggers on published spans, versions, claim revisions, evidence, review events, packets | `test_published_spans_and_version_identity_are_immutable`, `test_claim_revisions_and_evidence_are_append_only` |
| CSRF | SameSite=Lax session cookie; Origin check on `/api` mutations; custom `X-Trace-Request` header required on V3 mutations | `test_analysis_idempotency_and_csrf` |
| Data egress | Hosted model needs explicit acknowledgement + https; local model may not point at a public host | `test_hosted_requires_egress_acknowledgement_and_https`, `test_local_provider_cannot_point_at_public_internet` |
| Storage | Keys validated against traversal; files written atomically; packet files hash-checked on download | `test_filesystem_storage_rejects_unsafe_keys`, `test_packet_export_is_immutable_and_rechecks_membership` |
| Configuration | API refuses to start outside development/test with the placeholder secret or demo login | `test_unsafe_config_blocked_outside_development` |

## Known gaps

- Demo accounts with a shared password exist in development mode. Do not expose a Trace instance
  beyond `127.0.0.1` without replacing them and setting `TRACE_ENV=production`.
- No rate limiting, account lockout, or multi-factor authentication.
- Session tokens are signed but not server-side revocable before expiry.
- OCR and layout-aware parsing are not enabled; malicious PDFs are parsed by PyMuPDF.
- A hosted model provider applies its own retention policy, outside Trace's control.
