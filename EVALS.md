# Trace - Sovereign Discovery Copilot Evals

The MVP eval harness centers on `Acme Industrial v. Northshore Supply` and `seed_truth/acme_truth.json`.

Run locally:

```bash
make seed
make eval
```

The eval runner checks:

- Canonical entity coverage.
- Golden question concept coverage and citation existence.
- Known contradiction detection.
- Chronology generation and CSV/DOCX exports.
- Issue memo generation and Markdown/DOCX exports.
- Trace branding smoke coverage.

The runner defaults to rollback mode so eval-generated artifacts do not have to persist. Use the API script directly with `--commit` if you intentionally want to retain eval-generated memos, events, AI runs, and exports:

```bash
cd apps/api
python -m app.scripts.eval_seed --commit
```

Phase 11 regression breadth is represented by three lightweight static truth packs:

- `seed_truth/employment_dispute_truth.json`
- `seed_truth/internal_investigation_truth.json`
- `seed_truth/invoice_payment_dispute_truth.json`

Run Acme plus all regression checks:

```bash
cd apps/api
python -m app.scripts.eval_seed --suite all
```

Run only regression breadth checks:

```bash
cd apps/api
python -m app.scripts.eval_seed --suite regression
```

Run one regression corpus:

```bash
cd apps/api
python -m app.scripts.eval_seed --suite regression --corpus invoice_payment_dispute
```

The regression packs validate truth-map schema, entity mentions, golden-question concept coverage, source-document existence, contradiction evidence, chronology event coverage, ambiguity coverage, memo section coverage, and Trace branding without requiring local model serving.
