# SCHEMA_AND_SEEDS.md

## Purpose

This document defines the canonical MVP schema and seeded demo/test data strategy for **Sovereign Discovery Copilot**.

Its job is to remove ambiguity for the build agent in four places:
- what tables and relationships must exist
- what fields are required vs optional
- how source traceability must work
- what demo/test matter data must be generated to prove the product works

This file should be treated as the schema truth for MVP unless an explicit later migration changes it.

---

## 1. Schema Principles

### 1.1 Matter-scoped by default
All user-facing product data must be scoped to an organization and, where applicable, a specific matter.

### 1.2 Traceability is mandatory
Any extracted artifact that influences user-visible output must be traceable back to source evidence.

This applies to:
- citations
- chronology events
- entity summaries
- contradiction outputs
- issue memos
- search hits
- AI-generated answers

### 1.3 Structured first, rendered second
The database should store structured representations of major AI workflows first. Rendered prose and exports can be derived from that.

### 1.4 UUIDs everywhere
Use UUID primary keys for all core records.

### 1.5 Flexible where it helps, relational where it matters
Use relational fields for core product invariants and JSON fields where extraction results may vary.

### 1.6 Do not optimize for future fantasy complexity
This schema is for MVP. It should be clean, explicit, and extensible, but not prematurely generalized.

---

## 2. Naming Conventions

### 2.1 IDs
- all primary keys: `id UUID PRIMARY KEY`
- all foreign keys use `<object>_id`

### 2.2 Timestamps
All core tables should include:
- `created_at`
- `updated_at`

Use timezone-aware timestamps.

### 2.3 Status enums
Use enums or constrained string values for fields like:
- parse status
- OCR status
- job status
- confidence
- run type
- severity

Prefer explicit enum types in Postgres where practical.

---

## 3. MVP Domain Model Overview

Core objects:
- organization
- user
- matter
- matter_member
- document
- document_page
- document_chunk
- entity
- entity_mention
- event
- event_citation
- ai_run
- citation
- memo
- audit_log
- ingest_job
- export_job
- saved_search (optional but useful)

The schema is intentionally centered on:
- matter isolation
- evidence traceability
- reproducible AI workflows

---

## 4. Canonical Tables

## 4.1 organizations
Represents a customer org or single-tenant workspace boundary.

### Fields
- `id UUID PRIMARY KEY`
- `name TEXT NOT NULL`
- `slug TEXT UNIQUE NOT NULL`
- `settings_json JSONB DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Notes
`settings_json` can hold org-level config such as retention settings or feature flags.

---

## 4.2 users
Represents a user in an organization.

### Fields
- `id UUID PRIMARY KEY`
- `organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE`
- `email TEXT NOT NULL`
- `name TEXT NOT NULL`
- `password_hash TEXT NULL`
- `global_role TEXT NOT NULL DEFAULT 'member'`
- `is_active BOOLEAN NOT NULL DEFAULT true`
- `last_login_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Constraints
- unique index on `(organization_id, email)`

### Notes
For MVP, email/password is fine. SSO-ready abstraction can come later.

---

## 4.3 matters
Represents a litigation or investigation matter.

### Fields
- `id UUID PRIMARY KEY`
- `organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE`
- `name TEXT NOT NULL`
- `description TEXT NULL`
- `matter_code TEXT NULL`
- `status TEXT NOT NULL DEFAULT 'active'`
- `created_by UUID NOT NULL REFERENCES users(id)`
- `archived_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested statuses
- `active`
- `archived`
- `processing`

---

## 4.4 matter_members
Maps users to matters with a matter-scoped role.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
- `role TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Constraints
- unique index on `(matter_id, user_id)`

### Allowed roles
- `admin`
- `attorney`
- `reviewer`
- `read_only`

---

## 4.5 documents
Represents an uploaded source file.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `uploaded_by UUID NOT NULL REFERENCES users(id)`
- `file_name TEXT NOT NULL`
- `display_name TEXT NULL`
- `mime_type TEXT NOT NULL`
- `file_size_bytes BIGINT NOT NULL`
- `storage_key TEXT NOT NULL`
- `sha256 TEXT NOT NULL`
- `page_count INTEGER NULL`
- `document_date DATE NULL`
- `document_type TEXT NULL`
- `language TEXT NULL`
- `parse_status TEXT NOT NULL DEFAULT 'uploaded'`
- `ocr_status TEXT NOT NULL DEFAULT 'not_needed'`
- `ingest_status TEXT NOT NULL DEFAULT 'queued'`
- `extraction_quality_score NUMERIC(5,2) NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `error_message TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested document types
- `email`
- `contract`
- `letter`
- `memo`
- `transcript`
- `invoice`
- `spreadsheet`
- `image_evidence`
- `exhibit`
- `other`

### Suggested parse statuses
- `uploaded`
- `parsing`
- `parsed`
- `failed`

### Suggested OCR statuses
- `not_needed`
- `queued`
- `running`
- `completed`
- `failed`

### Suggested ingest statuses
- `queued`
- `processing`
- `ready`
- `failed`

### Notes
- `sha256` supports dedupe detection and auditability
- `metadata_json` can store parser-specific outputs

---

## 4.6 document_pages
Represents per-page extracted content.

### Fields
- `id UUID PRIMARY KEY`
- `document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE`
- `page_number INTEGER NOT NULL`
- `raw_text TEXT NULL`
- `normalized_text TEXT NULL`
- `image_storage_key TEXT NULL`
- `ocr_confidence NUMERIC(5,2) NULL`
- `has_text_layer BOOLEAN NOT NULL DEFAULT false`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Constraints
- unique index on `(document_id, page_number)`

### Notes
Store both raw and normalized text so debugging and citation alignment remain possible.

---

## 4.7 document_chunks
Represents retrievable text chunks derived from pages.

### Fields
- `id UUID PRIMARY KEY`
- `document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `page_start INTEGER NOT NULL`
- `page_end INTEGER NOT NULL`
- `chunk_index INTEGER NOT NULL`
- `heading TEXT NULL`
- `text TEXT NOT NULL`
- `token_count INTEGER NULL`
- `embedding VECTOR NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Constraints
- unique index on `(document_id, chunk_index)`
- index on `matter_id`

### Notes
- Keep `matter_id` denormalized here for faster matter-scoped retrieval
- `metadata_json` may include section labels, parser hints, chunk quality, etc.

---

## 4.8 entities
Represents canonical entities extracted for a matter.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `entity_type TEXT NOT NULL`
- `canonical_name TEXT NOT NULL`
- `aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `summary_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `confidence NUMERIC(5,2) NULL`
- `is_user_curated BOOLEAN NOT NULL DEFAULT false`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested entity types
- `person`
- `organization`
- `location`
- `project`
- `product`
- `date_group`
- `financial_amount`
- `other`

### Notes
Use `summary_json` to store structured entity profile material rather than plain prose only.

---

## 4.9 entity_mentions
Represents where an entity appeared in source content.

### Fields
- `id UUID PRIMARY KEY`
- `entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE`
- `document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE`
- `chunk_id UUID NULL REFERENCES document_chunks(id) ON DELETE SET NULL`
- `page_number INTEGER NULL`
- `mention_text TEXT NOT NULL`
- `context_text TEXT NULL`
- `confidence NUMERIC(5,2) NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Notes
This is critical for traceability and for building entity pages and mention timelines.

---

## 4.10 events
Represents normalized timeline events for a matter.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `event_date DATE NULL`
- `event_date_text TEXT NULL`
- `event_date_confidence TEXT NOT NULL DEFAULT 'medium'`
- `title TEXT NOT NULL`
- `description TEXT NOT NULL`
- `entities_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `source_type TEXT NOT NULL DEFAULT 'ai_extracted'`
- `confidence TEXT NOT NULL DEFAULT 'medium'`
- `conflict_flag BOOLEAN NOT NULL DEFAULT false`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_by_run_id UUID NULL REFERENCES ai_runs(id) ON DELETE SET NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested confidence values
- `low`
- `medium`
- `high`

### Notes
`entities_json` can hold lightweight entity references or names for quick render; source of truth still comes from citations and entity tables.

---

## 4.11 event_citations
Maps events to the supporting evidence.

### Fields
- `id UUID PRIMARY KEY`
- `event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE`
- `document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE`
- `chunk_id UUID NULL REFERENCES document_chunks(id) ON DELETE SET NULL`
- `page_number INTEGER NULL`
- `quote TEXT NOT NULL`
- `span_start INTEGER NULL`
- `span_end INTEGER NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Notes
This table makes chronology exports and event inspection defensible.

---

## 4.12 ai_runs
Represents every major AI workflow execution.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `user_id UUID NOT NULL REFERENCES users(id)`
- `run_type TEXT NOT NULL`
- `model_name TEXT NOT NULL`
- `prompt_template_version TEXT NOT NULL`
- `status TEXT NOT NULL DEFAULT 'completed'`
- `input_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `output_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `latency_ms INTEGER NULL`
- `token_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `error_message TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested run types
- `grounded_qa`
- `chronology_builder`
- `entity_summary`
- `contradiction_finder`
- `issue_memo`
- `citation_check`
- `entity_extraction`
- `event_extraction`

### Suggested statuses
- `queued`
- `running`
- `completed`
- `failed`

### Notes
Do not store hidden chain of thought. Store structured inputs/outputs only.

---

## 4.13 citations
Represents citations used in AI outputs.

### Fields
- `id UUID PRIMARY KEY`
- `ai_run_id UUID NOT NULL REFERENCES ai_runs(id) ON DELETE CASCADE`
- `document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE`
- `chunk_id UUID NULL REFERENCES document_chunks(id) ON DELETE SET NULL`
- `page_number INTEGER NULL`
- `quote TEXT NOT NULL`
- `span_start INTEGER NULL`
- `span_end INTEGER NULL`
- `label TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Notes
This table powers UI citation rendering and auditability.

---

## 4.14 memos
Represents saved first-pass issue memos.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `created_by UUID NOT NULL REFERENCES users(id)`
- `title TEXT NOT NULL`
- `memo_type TEXT NOT NULL DEFAULT 'issue_memo'`
- `status TEXT NOT NULL DEFAULT 'draft'`
- `source_run_id UUID NULL REFERENCES ai_runs(id) ON DELETE SET NULL`
- `content_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `content_markdown TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested statuses
- `draft`
- `finalized`
- `archived`

### Notes
`content_json` should hold structured sections and citations. `content_markdown` is a render convenience.

---

## 4.15 audit_logs
Represents user-visible or security-significant actions.

### Fields
- `id UUID PRIMARY KEY`
- `organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE`
- `user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL`
- `matter_id UUID NULL REFERENCES matters(id) ON DELETE SET NULL`
- `action TEXT NOT NULL`
- `target_type TEXT NULL`
- `target_id UUID NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Example actions
- `login`
- `create_matter`
- `upload_document`
- `start_ai_run`
- `export_memo`
- `view_document`

---

## 4.16 ingest_jobs
Tracks document ingestion pipeline jobs.

### Fields
- `id UUID PRIMARY KEY`
- `document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `status TEXT NOT NULL DEFAULT 'queued'`
- `job_type TEXT NOT NULL DEFAULT 'document_ingestion'`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `started_at TIMESTAMPTZ NULL`
- `finished_at TIMESTAMPTZ NULL`
- `error_message TEXT NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested statuses
- `queued`
- `running`
- `completed`
- `failed`

---

## 4.17 export_jobs
Tracks export generation jobs.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `requested_by UUID NOT NULL REFERENCES users(id)`
- `export_type TEXT NOT NULL`
- `status TEXT NOT NULL DEFAULT 'queued'`
- `source_object_type TEXT NOT NULL`
- `source_object_id UUID NOT NULL`
- `storage_key TEXT NULL`
- `error_message TEXT NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Suggested export types
- `memo_markdown`
- `memo_docx`
- `chronology_csv`
- `chronology_docx`

---

## 4.18 saved_searches (optional but recommended)
Stores useful search presets.

### Fields
- `id UUID PRIMARY KEY`
- `matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE`
- `created_by UUID NOT NULL REFERENCES users(id)`
- `name TEXT NOT NULL`
- `query_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

---

## 5. Relationship Summary

### Organization
- has many users
- has many matters
- has many audit logs

### Matter
- belongs to organization
- has many matter members
- has many documents
- has many entities
- has many events
- has many AI runs
- has many memos
- has many export jobs

### Document
- belongs to matter
- has many pages
- has many chunks
- has many ingest jobs
- is cited by many citations/event citations

### Entity
- belongs to matter
- has many mentions

### Event
- belongs to matter
- has many event citations

### AI Run
- belongs to matter
- belongs to user
- has many citations
- may create events or memos

---

## 6. Required Indexes

At minimum, add indexes for:
- `users(organization_id, email)` unique
- `matter_members(matter_id, user_id)` unique
- `documents(matter_id)`
- `documents(ingest_status)`
- `document_pages(document_id, page_number)` unique
- `document_chunks(matter_id)`
- `document_chunks(document_id, chunk_index)` unique
- vector index on `document_chunks.embedding`
- `entities(matter_id, canonical_name)`
- `entity_mentions(entity_id)`
- `events(matter_id, event_date)`
- `ai_runs(matter_id, run_type)`
- `citations(ai_run_id)`
- `audit_logs(organization_id, created_at)`
- `ingest_jobs(document_id, status)`
- `export_jobs(matter_id, status)`

---

## 7. Schema-Level Invariants

These are non-negotiable product invariants.

### 7.1 Matter isolation invariant
Every retrievable chunk, event, entity, memo, citation, and AI run must be attributable to exactly one matter.

### 7.2 Source traceability invariant
Every user-visible factual artifact must be backed by citation rows or source references.

### 7.3 Audit invariant
Every major workflow must create an `ai_runs` row and an `audit_logs` row.

### 7.4 Soft render invariant
Generated prose can be changed without losing the underlying structured data.

### 7.5 No orphan artifacts
Deleting a matter should cascade-delete related matter-scoped records unless explicitly preserved for audit reasons.

---

## 8. JSON Shapes to Standardize Early

These JSON structures should be explicitly standardized in code schemas.

## 8.1 `summary_json` for entities
Suggested shape:

```json
{
  "overview": "string",
  "role_in_matter": "string",
  "key_actions": ["string"],
  "key_dates": [
    {
      "date": "2024-03-12",
      "description": "string"
    }
  ],
  "open_questions": ["string"]
}
```

## 8.2 `content_json` for memos
Suggested shape:

```json
{
  "issue": "string",
  "answer_in_brief": "string",
  "supporting_facts": [
    {
      "statement": "string",
      "citation_ids": ["uuid"]
    }
  ],
  "contrary_facts": [
    {
      "statement": "string",
      "citation_ids": ["uuid"]
    }
  ],
  "gaps": ["string"],
  "next_documents_to_review": ["string"]
}
```

## 8.3 `output_json` for contradiction runs
Suggested shape:

```json
{
  "topic": "string",
  "contradictions": [
    {
      "claim_a": "string",
      "claim_b": "string",
      "why_conflict": "string",
      "severity": "low",
      "citation_ids_a": ["uuid"],
      "citation_ids_b": ["uuid"]
    }
  ],
  "ambiguities": [
    {
      "description": "string",
      "citation_ids": ["uuid"]
    }
  ]
}
```

## 8.4 `output_json` for chronology runs
Suggested shape:

```json
{
  "events": [
    {
      "date": "2024-03-12",
      "date_text": "March 12, 2024",
      "date_confidence": "high",
      "title": "Payment approved",
      "description": "string",
      "entity_names": ["Jane Doe", "Acme Corp"],
      "citations": [
        {
          "document_id": "uuid",
          "page_number": 4,
          "quote": "string"
        }
      ]
    }
  ],
  "unresolved_ambiguities": ["string"]
}
```

---

## 9. Seed Data Philosophy

The seeded corpus must do four jobs at once:
1. make the app demoable immediately
2. exercise the ingestion pipeline
3. exercise retrieval and citation rendering
4. provide known truth cases for evaluation

The seed data should be **synthetic but realistic**.

Do not use real confidential legal data.

---

## 10. Required Seeded Demo Matter

Create one default seeded matter called something like:
- `Acme Industrial v. Northshore Supply`

This matter should include a realistic commercial dispute around delayed deliveries, payment approvals, and notice obligations.

### Why this scenario
It naturally supports:
- contracts
- invoices
- emails
- timeline disputes
- witness conflicts
- document-to-document contradictions
- money issues
- issue memo generation

---

## 11. Seeded Matter Structure

### Matter Summary
A dispute between a buyer and supplier over delayed equipment delivery, whether notice was timely given, whether payment approval was authorized, and whether a defect was known before shipment.

### Core themes
- delivery delay
- notice timing
- payment approval authority
- defect knowledge
- contradictory witness statements

### Required seeded users
At least:
- one admin user
- one attorney user
- one reviewer user

These can all belong to one demo organization.

---

## 12. Seeded Documents (Minimum Set)

Create 15–25 mixed documents.

### Required document categories
1. Master supply agreement PDF
2. Amendment / addendum PDF
3. Email thread PDF or text export about delivery delay
4. Email thread about payment approval
5. Invoice PDF
6. Internal memo discussing defect concern
7. Shipping notice letter
8. Deposition transcript excerpt for Witness A
9. Deposition transcript excerpt for Witness B
10. Meeting notes DOCX
11. Spreadsheet with delivery/payment milestones
12. Scanned inspection report PDF requiring OCR
13. Photograph/image evidence with caption text
14. Internal project update memo
15. Formal notice letter

### Optional extra docs
- text messages export
- purchase order
- handwritten note scan
- revised shipment schedule
- customer complaint summary

---

## 13. Required Seeded Entities

Create at least 5 core entities with aliases and repeated mentions.

### Suggested entities
1. `Jane Mercer` — Operations Director at Acme Industrial
2. `David Lin` — Account Manager at Northshore Supply
3. `Priya Shah` — CFO or finance approver at Acme
4. `Northshore Supply LLC` — supplier org
5. `Acme Industrial Systems` — buyer org
6. `Project Falcon` — project name
7. `Compressor Unit 7A` — product/equipment entity

### Alias examples
- `Acme`
- `Acme Industrial`
- `Northshore`
- `NS Supply`
- `Project Falcon Upgrade`

### Requirement
At least one entity should require alias merging logic to look correct.

---

## 14. Required Seeded Timeline

Build a timeline with at least 10 significant events.

### Suggested example events
1. Contract executed
2. Delivery schedule confirmed
3. Internal defect concern raised
4. Shipment delayed
5. Notice email sent
6. Payment approval discussed
7. Invoice submitted
8. Formal notice letter sent
9. Deposition statement by Witness A
10. Conflicting deposition statement by Witness B
11. Inspection report created
12. Revised schedule circulated

### Requirement
At least 2 events must have ambiguous or disputed dates.

---

## 15. Required Contradictions in Seed Data

Seed at least 3 known contradictions.

### Contradiction 1: Notice timing
- one document suggests notice was sent on time
- another suggests it was late or incomplete

### Contradiction 2: Payment approval authority
- one witness says Priya approved payment
- another document suggests approval was conditional or never finalized

### Contradiction 3: Defect knowledge
- internal memo suggests supplier knew of defect risk before shipment
- witness testimony denies prior knowledge

### Rule
These contradictions must be clear enough that the contradiction finder can surface them, but subtle enough that the product still feels realistic.

---

## 16. Required OCR Challenge

At least one PDF should be an image-based scanned document that:
- requires OCR to become searchable
- contains a material fact needed for chronology or contradiction detection
- contains at least one citation-worthy quote

### Suggested example
Inspection report noting possible vibration defect before shipment.

---

## 17. Required Spreadsheet Seed

Create one spreadsheet that includes:
- milestone dates
- payment status
- delivery dates
- approver names

### Why
This tests:
- tabular extraction
- timeline generation
- entity recognition
- contradiction detection against emails/transcripts

---

## 18. Seed Truth Map

The repo must include a machine-readable truth file for the seeded matter.

Suggested file:
- `seed_truth/acme_truth.json`

This file should define:
- expected core entities
- expected aliases
- expected key events
- expected known contradictions
- expected answer snippets for key demo questions
- expected cited documents/pages for those answers

### Why
Without a truth map, seeded data is only for demos, not evals.

---

## 19. Example Truth File Shape

```json
{
  "matter_name": "Acme Industrial v. Northshore Supply",
  "entities": [
    {
      "canonical_name": "Jane Mercer",
      "aliases": ["J. Mercer"]
    }
  ],
  "key_events": [
    {
      "title": "Formal notice letter sent",
      "date": "2024-03-18"
    }
  ],
  "known_contradictions": [
    {
      "topic": "payment approval authority",
      "claim_a": "Priya Shah approved the invoice on March 20.",
      "claim_b": "Approval was only provisional and not finalized."
    }
  ],
  "golden_questions": [
    {
      "question": "Who approved the payment?",
      "must_include": ["Priya Shah", "conditional", "invoice"],
      "expected_document_names": ["payment-approval-email-thread.pdf", "invoice-1187.pdf"]
    }
  ]
}
```

---

## 20. Golden Demo Questions

Seed at least 8 golden questions for demos and regression checks.

### Suggested questions
1. What is the timeline of the delivery delay?
2. What evidence suggests Northshore knew of the defect before shipment?
3. What documents mention payment approval?
4. Who appears to have authority over invoice approval?
5. What conflicts exist regarding when notice was sent?
6. Summarize what Jane Mercer says about the delay.
7. Build a chronology of notice and payment events.
8. Generate a first-pass memo on whether notice was timely.

### Rule
For each golden question, the truth file should indicate:
- key concepts that must appear
- likely citation-bearing documents
- whether ambiguity should be called out

---

## 21. Seeding Output Requirements

The seed script should create:
- one demo organization
- three demo users with different roles
- one seeded matter
- all seeded documents
- pages/chunks if precomputed in seed flow, or the files necessary for ingestion if not
- a truth file accessible to eval tooling

### Recommendation
Prefer shipping raw source files plus an ingest step so the product proves ingestion works.

However, for local demo convenience, a fast bootstrap mode that seeds already-ingested outputs is also acceptable if clearly documented.

---

## 22. Two Seed Modes

Implement two possible seed modes if feasible.

### Mode A: Raw ingestion demo
- upload-like seeding of source files
- full parser/OCR/chunk/embed pipeline runs

### Mode B: Fast dev bootstrap
- inserts preprocessed pages/chunks/entities/events for faster local demo iteration

### Rule
Mode A is preferred for product truth. Mode B is allowed for developer speed.

---

## 23. Minimal Example SQL-Like Sketch

This is not the final migration code, but it shows intended shape.

```sql
CREATE TABLE organizations (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE matters (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  matter_code TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_by UUID NOT NULL REFERENCES users(id),
  archived_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id UUID PRIMARY KEY,
  matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  uploaded_by UUID NOT NULL REFERENCES users(id),
  file_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL,
  storage_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  parse_status TEXT NOT NULL DEFAULT 'uploaded',
  ocr_status TEXT NOT NULL DEFAULT 'not_needed',
  ingest_status TEXT NOT NULL DEFAULT 'queued',
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 24. Required Build Outputs From This Spec

The build agent should produce:
- DB migration files
- ORM models/schema files
- seed scripts
- synthetic source files for the seeded matter
- truth map JSON
- small eval harness that can reference the truth map

---

## 25. Validation Checklist for Schema Completion

The schema work is only complete if all answers below are “yes.”

### Isolation
- Can every document be traced to exactly one matter?
- Can every AI run be traced to one matter and one user?
- Can every citation be traced to real source content?

### Traceability
- Can a chronology event point back to source quotes?
- Can an entity mention point back to chunk/page/doc context?
- Can a memo section be backed by citations?

### Demoability
- Does the seeded matter include mixed document types?
- Does it include OCR-needed content?
- Does it include at least 3 contradictions?
- Does it support all main workflows?

### Extensibility
- Can we later add SSO without schema trauma?
- Can we later add richer reviewer workflows without rewriting the world?
- Can we later move vector retrieval out of Postgres if needed?

---

## 26. Hard Rules for Codex

### Must do
- keep schema explicit and understandable
- preserve matter isolation everywhere
- preserve source traceability everywhere
- include realistic demo data and truth map
- document all seed generation steps

### Must not do
- invent cross-matter features
- hide core product state only in JSON when relational fields are clearer
- skip citations for seeded artifacts
- build demo data too small or too clean to stress the product
- use real confidential legal data

---

## 27. Final Hand-off Note

This document exists to make the build deterministic.

If there is tension between:
- a simpler schema
- and stronger source traceability

choose stronger source traceability.

If there is tension between:
- a faster fake demo
- and a seeded corpus that genuinely exercises ingestion and retrieval

choose the corpus that genuinely exercises ingestion and retrieval.

The next companion document should be:
- `CODEX_BUILD_GUIDE.md`

That document should translate the PRD and schema into an ordered execution plan for the build agent.
