# Trace - Sovereign Discovery Copilot Prompt Contracts

Trace treats prompts as workflow contracts rather than scattered route strings. Each workflow should have typed input, typed output, validation, persistence, audit coverage, and citation checks.

Current workflow contracts:

- `grounded_qa_v1`
- `chronology_builder_v1`
- `entity_summary_v1`
- `contradiction_finder_v1`
- `issue_memo_v1`
- `citation_check_v1`

Local development currently uses `MockModelClient`, which returns deterministic citation-backed outputs from retrieved evidence. `OpenAICompatibleModelClient` is the integration boundary for later self-hosted vLLM or equivalent private model endpoints.

Prompt hardening rules:

- Never produce material factual claims without validated citations.
- Return insufficient evidence when citations cannot be validated.
- Store structured output before rendering prose.
- Persist the prompt template version in `ai_runs.prompt_template_version`.
- Keep matter ID explicit in every workflow request.
