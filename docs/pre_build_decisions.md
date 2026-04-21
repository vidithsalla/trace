# PRE_BUILD_DECISIONS.md

## Purpose

This document locks the key implementation decisions for the **Sovereign Discovery Copilot** MVP before coding begins.

The goal is to reduce ambiguity for the build agent, prevent premature architecture drift, and keep the first version focused on a single strong vertical slice.

This file is binding unless a later explicit change is made.

---

## 1. Product Boundary

### 1.1 What we are building
We are building a **private, matter-scoped legal discovery assistant** that helps litigation and investigations teams:
- upload and ingest matter documents
- search and inspect the corpus
- ask grounded questions with citations
- generate chronologies
- generate witness/entity summaries
- detect contradictions
- draft first-pass issue memos

### 1.2 What we are not building
We are **not** building:
- a generic chatbot
- a legal advice engine
- a broad e-discovery replacement
- a motion drafting platform
- a review queue / reviewer management system
- a multi-matter intelligence system
- a cross-tenant knowledge graph
- a consumer document summarizer

### 1.3 Product wedge
The wedge is:
- **private deployment**
- **citation-grounded answers**
- **first-pass review artifacts**
- **matter-scoped workflows**

Not:
- flashy general chat
- maximum model cleverness
- replacing lawyer judgment

---

## 2. MVP Success Definition

The MVP is successful only if a user can:
1. sign in
2. create a matter
3. upload a batch of mixed legal documents
4. wait for them to ingest successfully
5. search the matter corpus
6. ask a grounded question and inspect citations
7. generate a chronology
8. open an entity/witness summary
9. run contradiction detection
10. generate a first-pass issue memo
11. export a usable artifact
12. audit what happened

If a feature does not help this flow, it should be deprioritized.

---

## 3. Deployment Philosophy

### 3.1 Sovereign-first deployment
This product is being built as a **private AI system**.

That means:
- no required external LLM API dependency in production mode
- inference must be able to run against a self-hosted model endpoint
- customer data must remain scoped to the deployment boundary
- architecture must support single-tenant deployment from day one

### 3.2 Local-first developer experience
The system must be runnable locally via Docker Compose with a realistic end-to-end workflow.

Local dev should include:
- web app
- API
- worker
- Postgres
- Redis
- object storage
- model serving endpoint
- optional OCR service

### 3.3 Single-tenant before multi-tenant complexity
We will design the data model so organizations and matters exist from day one, but we will **not** optimize for complex pooled multi-tenant SaaS infra in the MVP.

We are building for:
- local dev
- demo deployment
- single-tenant hosted deployment
- customer VPC/on-prem path later

---

## 4. Core Architecture Decisions

## 4.1 Frontend
**Decision:** Use **Next.js 15 + TypeScript + Tailwind + shadcn/ui**.

### Why
- fast build speed
- good enterprise UI ergonomics
- easy routing and layout management
- straightforward integration with API backend
- good component reuse

### Non-goals
- do not over-customize design system early
- do not spend time on pixel-perfect brand polish before workflows work

---

## 4.2 Backend API
**Decision:** Use **FastAPI** as the main application API.

### Why
- strong Python ecosystem fit for document/AI workflows
- easy schema validation with Pydantic
- simple async support
- fast to build and iterate
- easy for background jobs and internal service integration

### Constraint
The backend is the source of truth for:
- authorization
- matter boundaries
- ingestion job orchestration
- search workflows
- AI workflow execution
- audit logging

The frontend must not bypass backend security assumptions.

---

## 4.3 Background Jobs
**Decision:** Use a queue-backed worker model with **Redis** and one worker framework.

Preferred choice:
- Dramatiq or Celery

### Why
We need async jobs for:
- ingestion
- OCR
- chunking
- embeddings
- entity extraction
- chronology generation
- contradiction workflows
- export generation

### Build rule
Choose one queue library and stick to it. Do not build ad hoc async orchestration.

---

## 4.4 Database
**Decision:** Use **PostgreSQL** for primary application state.

### Why
- stable and boring
- relational model is a strong fit for matters/documents/entities/events/logs
- supports JSON fields where needed
- pgvector available for MVP vector search

### Rule
Postgres is the system of record for:
- organizations
- users
- matters
- documents metadata
- entities
- events
- memos
- AI run logs
- audit logs

Do not invent a separate state store for core product records.

---

## 4.5 Vector Search
**Decision:** Use **pgvector** inside Postgres for MVP.

### Why
- operational simplicity
- good enough for MVP corpus sizes
- easier local dev
- fewer moving parts than a dedicated vector DB

### Tradeoff accepted
This is not the most scalable option long term, but it is the right MVP trade.

### Rule
Do not add Pinecone/Weaviate/Qdrant/etc. in MVP unless a hard blocker emerges.

---

## 4.6 Object Storage
**Decision:** Use **S3-compatible object storage**.

Local:
- MinIO

Hosted:
- S3-compatible provider

### Why
We need storage for:
- raw uploads
- extracted text artifacts
- page images
- thumbnails/previews
- export files

### Rule
Never store large original binary files directly in Postgres.

---

## 4.7 Model Serving
**Decision:** Use **self-hosted vLLM** behind an internal OpenAI-compatible interface.

### Primary model target
- Gemma 4 26B instruction model for main reasoning workflows

### Optional secondary model
- smaller model for lightweight extraction/classification

### Why
- vLLM supports Gemma 4
- OpenAI-compatible API shape reduces coupling
- efficient serving and batching
- easier future provider abstraction

### Rule
The app must speak to an internal model client abstraction, not directly to vendor-specific code scattered throughout the system.

---

## 4.8 OCR and Parsing
**Decision:** Build a parser abstraction and OCR fallback path.

### Initial parser support
- PDF text extraction
- OCR PDFs
- DOCX
- TXT
- CSV/XLSX
- JPG/PNG OCR

### Why
Legal corpora are messy and multimodal enough that OCR failure is a product failure.

### Rule
Treat OCR and parse quality as first-class observable states, not hidden implementation details.

---

## 4.9 Retrieval Strategy
**Decision:** Use **hybrid retrieval** from day one.

Components:
- lexical search
- vector search
- metadata filters
- reranking
- evidence assembly

### Why
Pure semantic retrieval is too brittle for legal workflows.
Pure keyword retrieval misses conceptual matches.
Hybrid retrieval is the minimum credible baseline.

### Rule
Every major AI workflow must pass through a retrieval/evidence assembly layer.
No workflow should generate matter-level conclusions from raw model memory alone.

---

## 4.10 Structured Outputs
**Decision:** Use structured JSON outputs for all AI workflows before rendering prose.

### Why
- better validation
- better auditability
- easier UI rendering
- less brittle than freeform output
- easier downstream export generation

### Rule
The model should output schema-shaped data first, then the app renders user-facing text.

Do not let the model directly author uncontrolled long-form UI content where structure matters.

---

## 5. Grounding and Safety Decisions

## 5.1 Evidence-first answering
**Decision:** No answer should be presented as grounded unless citations were validated.

### Rule
A grounded response must:
- cite actual chunks from the current matter
- link to source docs/pages
- avoid unsupported factual claims

If evidence is weak, the system must say so.

---

## 5.2 No legal advice posture
**Decision:** The product is a review acceleration tool, not a legal advice engine.

### Must do
- summarize evidence
- organize facts
- flag ambiguity/conflict
- accelerate first-pass review

### Must not do
- claim legal conclusions as authoritative
- invent law or standards
- advise on litigation strategy as product behavior
- imply attorney replacement

### Rule
Prompt templates and UI copy must reinforce this boundary.

---

## 5.3 Matter isolation
**Decision:** Every workflow is matter-scoped.

### Rule
- no cross-matter retrieval in MVP
- no cross-matter entity linking in MVP
- every AI request must include matter context
- returned citations must belong to the same matter

This is not optional.

---

## 5.4 Conservative contradiction handling
**Decision:** Contradiction detection should err on the side of caution.

### Rule
The system should distinguish:
- clear conflict
- possible ambiguity
- insufficient evidence

Do not overclaim contradiction where there is only paraphrase drift or partial overlap.

---

## 6. Product Surface Decisions

## 6.1 Main screens to build
We are committing to these core screens:
1. Matter Dashboard
2. Documents Screen
3. Ask Screen
4. Chronology Screen
5. Entity/Witness Screen
6. Issue Memo Screen
7. Admin/Settings Screen

### Rule
Do not build extra navigation surfaces until these are functional.

---

## 6.2 Documents viewer
**Decision:** The viewer is core product infrastructure, not a nice-to-have.

### Must support
- PDF/image viewing
- page navigation
- citation-driven jumps
- extracted text side-by-side when useful

### Why
If users cannot quickly verify cited evidence, trust collapses.

---

## 6.3 Exports
**Decision:** Exports are in MVP.

Initial export formats:
- Markdown
- DOCX
- CSV for chronology

PDF export can wait if needed.

### Why
Legal users need artifacts they can move into existing workflows.

---

## 7. Workflow Prioritization Decisions

## 7.1 Priority order
The build order is locked as:
1. auth + matters
2. upload + storage
3. ingestion + parsing + OCR
4. search + viewer
5. grounded Q&A
6. chronology builder
7. entity extraction/summaries
8. contradiction finder
9. issue memo generator
10. exports + hardening

### Rule
Do not jump ahead to fancy workflows before upload, ingestion, search, viewer, and grounded QA work reliably.

---

## 7.2 Vertical slice requirement
We would rather have:
- one polished demo matter
- one clean grounded QA path
- one useful chronology flow

than:
- many half-implemented AI features

### Rule
Depth over breadth.

---

## 8. Data Modeling Decisions

## 8.1 UUIDs everywhere
**Decision:** All primary records use UUIDs.

### Why
- safer merging across services
- easier future deployment flexibility
- no brittle integer assumptions

---

## 8.2 Core domain entities
We are explicitly modeling:
- organization
- user
- matter
- matter membership
- document
- page
- chunk
- entity
- entity mention
- event
- memo
- AI run
- citation
- audit log

### Rule
Do not invent major additional domain objects unless necessary for MVP flow.

---

## 8.3 Keep source traceability
**Decision:** Every extracted artifact must preserve traceability back to source.

### Applies to
- entity mentions
- chronology events
- contradiction outputs
- memo claims
- search hits
- answer citations

### Rule
No “smart summary” object should exist without evidence references.

---

## 9. UX and Design Decisions

## 9.1 Design tone
**Decision:** Use a sober, enterprise, trust-building design tone.

### Desired qualities
- evidence-forward
- low-noise
- calm
- readable
- professional

### Avoid
- playful chatbot vibes
- flashy gradients as a core identity
- consumer-AI aesthetic
- anthropomorphic assistant styling

---

## 9.2 Citations are product UI, not footnotes
**Decision:** Citations should be visible and easy to inspect.

### Rule
Every important factual answer should make evidence inspection easy within 1–2 clicks.

---

## 9.3 Confidence display
**Decision:** Show confidence / ambiguity states where appropriate.

### Why
This helps set user expectations and reduces false certainty.

### Rule
Low-evidence answers must look meaningfully different from high-confidence grounded answers.

---

## 10. Build Quality Decisions

## 10.1 Observability from day one
**Decision:** Add structured logs and basic metrics early.

### Track
- ingestion duration
- OCR failures
- indexing failures
- retrieval latency
- generation latency
- citation validation failures
- job failures by type

### Why
Document/AI systems fail in messy ways. We need visibility early.

---

## 10.2 Seeded demo matter is mandatory
**Decision:** The repo must include a realistic synthetic seeded matter.

### Required contents
- 15–25 mixed documents
- at least 3–5 entities
- at least one contradiction
- at least one timeline dispute
- at least one scanned exhibit
- at least one transcript excerpt
- at least one spreadsheet

### Why
The product must be demoable immediately and testable without external data.

---

## 10.3 Tests
**Decision:** Implement a minimum but meaningful test baseline.

### Must include
- auth / matter authorization tests
- citation resolution tests
- schema validation tests for major AI outputs
- at least one end-to-end integration test for upload → ingest → ask

### Rule
Do not ship a completely untested ingestion/retrieval path.

---

## 10.4 Prefer boring infrastructure
**Decision:** Prefer boring, explicit, inspectable systems over clever abstractions.

### Means
- explicit schemas
- explicit queues
- explicit ingestion states
- explicit AI run logs
- explicit citations

Not:
- hidden orchestration magic
- deeply nested abstractions early
- overdesigned microservices

---

## 11. Hard Constraints

These are hard constraints for the build agent.

### 11.1 Must include
- Docker Compose local environment
- `.env.example`
- migrations
- seed scripts
- README
- architecture docs
- prompt docs
- evaluation docs

### 11.2 Must not include
- dependency on external closed-model APIs for core workflows
- cross-tenant data mixing
- chain-of-thought storage/display
- feature creep into billing, legal hold, or enterprise admin bloat
- multi-region infra work

---

## 12. Open Decisions Already Deferred

The following are explicitly deferred and should not block MVP:
- SSO/SAML
- production-grade privilege review
- redaction workflows
- PST/OST advanced email ingestion
- collaborative annotation systems
- complex review queues
- full multi-tenant pooled SaaS architecture
- PDF export polish
- fine-tuning infrastructure
- per-customer policy engines

If one of these becomes necessary, flag it as a post-MVP decision.

---

## 13. Codex Operating Instructions

When in doubt, optimize for:
1. matter isolation
2. citation integrity
3. grounded outputs
4. demoability
5. boring reliability
6. speed to a working vertical slice

If forced to choose between:
- better architecture purity
- or a clearer, testable, matter-scoped workflow

choose the clearer workflow.

If forced to choose between:
- fancy AI behavior
- or trustworthy evidence presentation

choose trustworthy evidence presentation.

If forced to choose between:
- more features
- or making grounded QA + chronology actually work

choose grounded QA + chronology.

---

## 14. Final Locked Decisions Summary

### Build stack
- Next.js 15 + TypeScript frontend
- FastAPI backend
- Redis-backed worker
- PostgreSQL + pgvector
- MinIO/S3-compatible storage
- self-hosted vLLM for Gemma 4

### Product stack
- matter-scoped workspaces
- ingestion pipeline
- hybrid retrieval
- grounded Q&A
- chronology builder
- entity summaries
- contradiction finder
- issue memos
- exports
- audit logs

### Product philosophy
- private by default
- evidence-first
- workflow over generic chat
- review acceleration, not legal advice
- boring, inspectable systems over clever magic

---

## 15. Hand-off Note

This file should be read before:
- schema design
- seed design
- prompt design
- architecture implementation
- UI implementation

The next required companion document is:
- `SCHEMA_AND_SEEDS.md`

After that:
- `CODEX_BUILD_GUIDE.md`
