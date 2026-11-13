"""V3 claims, evidence relations, append-only review ledger, change alerts, evidence packets.

Three trust layers are stored separately and never collapsed:
- source integrity  -> claim_revisions.source_gate_state / claim_evidence.quote_integrity
- support candidate -> claim_revisions.relation_candidate / claim_evidence.relation_candidate
- human decision    -> review_events (append-only) projected onto claims.review_state
"""

from alembic import op

revision = "0003_claims_reviews"
down_revision = "0002_evidence_versions"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO embedding_profiles (id, model_id, dimension, normalization, is_semantic) VALUES
  ('minilm-l6-v2-ollama', 'all-minilm:l6-v2 (Ollama)', 384, 'l2', true)
  ON CONFLICT (id) DO NOTHING;

CREATE TABLE analysis_runs (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  corpus_snapshot_id uuid NOT NULL,
  requested_by uuid NOT NULL REFERENCES users(id),
  question text NOT NULL CHECK (char_length(question) BETWEEN 3 AND 1000),
  retrieval_profile text NOT NULL,
  retrieval_config_sha256 text NOT NULL,
  model_config jsonb NOT NULL,
  model_config_sha256 text NOT NULL,
  prompt_version text NOT NULL,
  code_commit text NOT NULL,
  status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','COMPLETED','ABSTAINED','FAILED')),
  error_code text NULL,
  call_records jsonb NOT NULL DEFAULT '[]'::jsonb,
  coverage jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz NULL,
  completed_at timestamptz NULL,
  UNIQUE (matter_id, requested_by, idempotency_key),
  UNIQUE (matter_id, id),
  FOREIGN KEY (matter_id, corpus_snapshot_id) REFERENCES corpus_snapshots(matter_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_analysis_runs_matter ON analysis_runs(matter_id, created_at DESC);

CREATE TABLE retrieval_candidates (
  run_id uuid NOT NULL,
  matter_id uuid NOT NULL,
  source_span_id uuid NOT NULL,
  evidence_ref text NOT NULL CHECK (evidence_ref ~ '^ev_[0-9]{2,3}$'),
  retrieval_role text NOT NULL CHECK (retrieval_role IN ('primary','counterevidence')),
  retriever text NOT NULL,
  rank integer NOT NULL,
  score double precision NULL,
  for_claim_id uuid NULL,
  PRIMARY KEY (run_id, evidence_ref),
  FOREIGN KEY (matter_id, run_id) REFERENCES analysis_runs(matter_id, id) ON DELETE CASCADE,
  FOREIGN KEY (matter_id, source_span_id) REFERENCES source_spans(matter_id, id) ON DELETE CASCADE
);

CREATE TABLE claims (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  run_id uuid NOT NULL,
  current_revision integer NOT NULL DEFAULT 1,
  review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK (review_state IN ('UNREVIEWED','ACCEPTED','REJECTED','UNRESOLVED')),
  basis_state text NOT NULL DEFAULT 'CURRENT' CHECK (basis_state IN ('CURRENT','STALE_SOURCE')),
  coverage_state text NOT NULL DEFAULT 'CURRENT'
    CHECK (coverage_state IN ('CURRENT','POTENTIAL_NEW_EVIDENCE')),
  review_seq integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (matter_id, id),
  FOREIGN KEY (matter_id, run_id) REFERENCES analysis_runs(matter_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_claims_matter ON claims(matter_id, created_at DESC);

CREATE TABLE claim_revisions (
  claim_id uuid NOT NULL,
  matter_id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  text text NOT NULL CHECK (char_length(text) BETWEEN 3 AND 600),
  evidence_set_sha256 text NOT NULL,
  corpus_snapshot_id uuid NOT NULL,
  source_gate_state text NOT NULL CHECK (source_gate_state IN ('VERIFIED','INVALID','UNAVAILABLE')),
  source_gate_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  relation_candidate text NOT NULL CHECK (relation_candidate IN
    ('SUPPORT_CANDIDATE','CONTRADICTION_CANDIDATE','MIXED','NOT_ESTABLISHED','UNCERTAIN','UNASSESSED')),
  coverage jsonb NOT NULL DEFAULT '{}'::jsonb,
  open_questions jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by_actor_type text NOT NULL CHECK (created_by_actor_type IN ('model','human','system')),
  created_by_user_id uuid NULL REFERENCES users(id),
  change_reason text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (claim_id, revision),
  UNIQUE (matter_id, claim_id, revision),
  FOREIGN KEY (matter_id, claim_id) REFERENCES claims(matter_id, id) ON DELETE CASCADE,
  FOREIGN KEY (matter_id, corpus_snapshot_id) REFERENCES corpus_snapshots(matter_id, id) ON DELETE CASCADE
);

CREATE TABLE claim_evidence (
  claim_id uuid NOT NULL,
  claim_revision integer NOT NULL,
  matter_id uuid NOT NULL,
  source_span_id uuid NOT NULL,
  evidence_ref text NOT NULL,
  cited_by_model boolean NOT NULL,
  evidence_role text NOT NULL CHECK (evidence_role IN ('supporting','opposing','qualifying','other')),
  quote_integrity text NOT NULL CHECK (quote_integrity IN ('VERIFIED','INVALID','UNAVAILABLE')),
  integrity_reason text NULL,
  relation_candidate text NOT NULL CHECK (relation_candidate IN
    ('supports','qualifies','contradicts','irrelevant','uncertain','unassessed')),
  reason_code text NULL,
  retrieval_role text NOT NULL CHECK (retrieval_role IN ('primary','counterevidence')),
  PRIMARY KEY (claim_id, claim_revision, source_span_id),
  FOREIGN KEY (matter_id, claim_id, claim_revision)
    REFERENCES claim_revisions(matter_id, claim_id, revision) ON DELETE CASCADE,
  FOREIGN KEY (matter_id, source_span_id) REFERENCES source_spans(matter_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_claim_evidence_span ON claim_evidence(matter_id, source_span_id);

CREATE TABLE review_events (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL,
  claim_id uuid NOT NULL,
  claim_revision integer NOT NULL,
  evidence_set_sha256 text NOT NULL,
  actor_user_id uuid NOT NULL REFERENCES users(id),
  action text NOT NULL CHECK (action IN ('ACCEPT','REJECT','UNRESOLVED','EDIT','RECHECK')),
  reason_code text NULL,
  note text NULL CHECK (note IS NULL OR char_length(note) <= 2000),
  event_seq integer NOT NULL,
  idempotency_key text NOT NULL,
  request_sha256 text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (claim_id, event_seq),
  UNIQUE (matter_id, actor_user_id, idempotency_key),
  FOREIGN KEY (matter_id, claim_id, claim_revision)
    REFERENCES claim_revisions(matter_id, claim_id, revision) ON DELETE CASCADE
);

CREATE TABLE coverage_alerts (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL,
  claim_id uuid NOT NULL,
  claim_revision integer NOT NULL,
  kind text NOT NULL CHECK (kind IN ('STALE_SOURCE','STALE_CLAIM','POTENTIAL_NEW_EVIDENCE')),
  triggering_document_version_id uuid NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','DISMISSED')),
  detector_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz NULL,
  resolved_by uuid NULL REFERENCES users(id),
  FOREIGN KEY (matter_id, claim_id) REFERENCES claims(matter_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_coverage_alerts_open ON coverage_alerts(matter_id, status, created_at DESC);
CREATE UNIQUE INDEX uq_coverage_alerts_open ON coverage_alerts(claim_id, kind, triggering_document_version_id)
  WHERE status = 'OPEN';

CREATE TABLE packet_exports (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  requested_by uuid NOT NULL REFERENCES users(id),
  inclusion_policy text NOT NULL CHECK (inclusion_policy IN ('accepted_current_only','include_all_labeled')),
  claim_count integer NOT NULL,
  manifest_sha256 text NOT NULL,
  storage_prefix text NOT NULL,
  files jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (matter_id, id)
);

CREATE TRIGGER review_events_immutable BEFORE UPDATE ON review_events
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
CREATE TRIGGER claim_revisions_immutable BEFORE UPDATE ON claim_revisions
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
CREATE TRIGGER claim_evidence_immutable BEFORE UPDATE ON claim_evidence
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
CREATE TRIGGER retrieval_candidates_immutable BEFORE UPDATE ON retrieval_candidates
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
CREATE TRIGGER packet_exports_immutable BEFORE UPDATE ON packet_exports
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS packet_exports, coverage_alerts, review_events, claim_evidence,
  claim_revisions, claims, retrieval_candidates, analysis_runs CASCADE;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
