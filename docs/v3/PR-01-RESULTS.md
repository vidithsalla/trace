# PR-01 real model contract: results

- `app/services/llm/`: one OpenAI-compatible client for `local` and `hosted` providers, typed
  Pydantic contracts (`ClaimProposal`, `SupportAssessment`), server-issued evidence refs
  (`ev_01`...), deterministic `MockClaimEngine` used only when configured.
- No fallback: a failing real provider raises a typed error (`provider_timeout`,
  `provider_unavailable`, `provider_rate_limited`, `provider_auth_error`, `schema_error`,
  `provider_content_filtered`, `provider_response_too_large`, `call_budget_exceeded`).
- Retries only for 429/5xx/transport errors, capped (default 2). Redirects refused.
- Data boundary: `hosted` refuses to start without `TRACE_HOSTED_EGRESS_ACKNOWLEDGED=true` and
  https; `local` refuses a public-internet endpoint. Logs carry only sanitized call metadata.
- Removed the fake `OpenAICompatibleModelClient` and the mock vLLM container. `compose.model.yaml`
  now points the stack at the host's Ollama.

## Verified

| Command | Result |
| --- | --- |
| `make test-docker` | `90 passed, 1 skipped` |
| `make lint-docker` | `All checks passed!` |
| `make test-real-model ARGS=app/tests/test_v3_01_model_contract.py` | `1 passed`; `qwen2.5:7b-instruct` via Ollama 0.40.16, prompt_tokens=224, completion_tokens=68, latency 6.5 s (cold) |
