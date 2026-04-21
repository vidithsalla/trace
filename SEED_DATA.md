# Trace - Sovereign Discovery Copilot Seed Data

The canonical MVP seed matter is `Acme Industrial v. Northshore Supply`.

Seed modes:

- Mode A raw ingestion: `make seed-raw` uploads files from `seed_data/raw/acme_matter` and runs ingestion synchronously.
- Mode B fast bootstrap: `make seed` inserts processed pages/chunks directly for quick local demos.

The raw seed folder includes synthetic source files covering defect knowledge, shipment readiness, notice timing, payment approval authority, and records requests. The truth map lives at `seed_truth/acme_truth.json`.

Phase 11 adds broader lightweight regression truth packs:

- `seed_truth/employment_dispute_truth.json`
- `seed_truth/internal_investigation_truth.json`
- `seed_truth/invoice_payment_dispute_truth.json`

These files embed compact synthetic document text directly in the truth maps. They are not full demo matters by default; they are CI-friendly regression corpora for broader PRD coverage.

Expected demo flow:

- Sign in as `attorney@trace.local`.
- Open the Acme matter.
- Search for defect knowledge, notice timing, or payment approval.
- Ask the defect-knowledge question.
- Generate a chronology and export CSV/DOCX.
- Open Jane Mercer or Priya Shah entity pages.
- Run contradiction finder for notice timing, payment approval authority, and defect knowledge.
- Generate a notice-timeliness memo and export Markdown/DOCX.
- Inspect the audit trail from matter settings and export audit CSV.
