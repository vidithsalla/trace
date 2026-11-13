"""V3 evidence versioning: immutable document/extraction versions, source spans, snapshots.

Matter isolation is enforced with composite (matter_id, id) foreign keys, so a row can never
reference another matter's evidence even if an ID is guessed. Published text and offsets are
made immutable with triggers.
"""

from alembic import op

revision = "0002_evidence_versions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE documents ADD CONSTRAINT uq_documents_matter_id UNIQUE (matter_id, id);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS current_version_id uuid NULL;

CREATE TABLE document_versions (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  document_id uuid NOT NULL,
  revision_no integer NOT NULL CHECK (revision_no > 0),
  source_sha256 text NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
  provenance text NOT NULL DEFAULT 'verified'
    CHECK (provenance IN ('verified', 'unknown_legacy')),
  storage_key text NOT NULL,
  file_name text NOT NULL,
  mime_type text NOT NULL,
  file_size_bytes bigint NULL,
  state text NOT NULL CHECK (state IN ('STAGING', 'READY', 'FAILED', 'RETIRED')),
  error_code text NULL,
  change_note text NULL,
  created_by uuid NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz NULL,
  CHECK (provenance = 'unknown_legacy' OR source_sha256 IS NOT NULL),
  UNIQUE (document_id, revision_no),
  UNIQUE (matter_id, id),
  FOREIGN KEY (matter_id, document_id) REFERENCES documents(matter_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_document_versions_document ON document_versions(document_id, revision_no DESC);

CREATE TABLE extraction_versions (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  document_version_id uuid NOT NULL,
  parser_profile text NOT NULL,
  parser_profile_sha256 text NOT NULL,
  normalization_version text NOT NULL,
  normalized_text_sha256 text NOT NULL,
  page_count integer NOT NULL DEFAULT 0,
  span_count integer NOT NULL DEFAULT 0,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  state text NOT NULL CHECK (state IN ('STAGING', 'READY', 'FAILED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz NULL,
  UNIQUE (document_version_id, parser_profile_sha256),
  UNIQUE (matter_id, id),
  FOREIGN KEY (matter_id, document_version_id)
    REFERENCES document_versions(matter_id, id) ON DELETE CASCADE
);

CREATE TABLE extraction_pages (
  extraction_version_id uuid NOT NULL,
  matter_id uuid NOT NULL,
  page_no integer NOT NULL CHECK (page_no > 0),
  text text NOT NULL,
  text_sha256 text NOT NULL,
  PRIMARY KEY (extraction_version_id, page_no),
  FOREIGN KEY (matter_id, extraction_version_id)
    REFERENCES extraction_versions(matter_id, id) ON DELETE CASCADE
);

CREATE TABLE source_spans (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL,
  extraction_version_id uuid NOT NULL,
  document_id uuid NOT NULL,
  page_no integer NOT NULL CHECK (page_no > 0),
  span_index integer NOT NULL CHECK (span_index >= 0),
  normalized_start integer NOT NULL CHECK (normalized_start >= 0),
  normalized_end integer NOT NULL,
  text text NOT NULL,
  quote_sha256 text NOT NULL,
  offset_encoding text NOT NULL DEFAULT 'unicode_codepoints_nfc',
  raw_anchor_json jsonb NULL,
  search tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  CHECK (normalized_end > normalized_start),
  CHECK (char_length(text) = normalized_end - normalized_start),
  UNIQUE (extraction_version_id, span_index),
  UNIQUE (matter_id, id),
  FOREIGN KEY (matter_id, extraction_version_id)
    REFERENCES extraction_versions(matter_id, id) ON DELETE CASCADE,
  FOREIGN KEY (matter_id, document_id) REFERENCES documents(matter_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_source_spans_search ON source_spans USING gin(search);
CREATE INDEX ix_source_spans_extraction ON source_spans(matter_id, extraction_version_id);

CREATE TABLE embedding_profiles (
  id text PRIMARY KEY,
  model_id text NOT NULL,
  dimension integer NOT NULL,
  normalization text NOT NULL,
  is_semantic boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO embedding_profiles (id, model_id, dimension, normalization, is_semantic) VALUES
  ('hash-v1', 'trace-local-hash', 384, 'l2', false),
  ('minilm-l6-v2', 'sentence-transformers/all-MiniLM-L6-v2', 384, 'l2', true);

CREATE TABLE source_embeddings (
  matter_id uuid NOT NULL,
  source_span_id uuid NOT NULL,
  embedding_profile_id text NOT NULL REFERENCES embedding_profiles(id),
  embedding vector(384) NOT NULL,
  PRIMARY KEY (source_span_id, embedding_profile_id),
  FOREIGN KEY (matter_id, source_span_id) REFERENCES source_spans(matter_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_source_embeddings_matter ON source_embeddings(matter_id, embedding_profile_id);

CREATE TABLE corpus_snapshots (
  id uuid PRIMARY KEY,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  manifest_sha256 text NOT NULL,
  member_count integer NOT NULL,
  created_by uuid NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (matter_id, manifest_sha256),
  UNIQUE (matter_id, id)
);

CREATE TABLE corpus_snapshot_members (
  matter_id uuid NOT NULL,
  snapshot_id uuid NOT NULL,
  extraction_version_id uuid NOT NULL,
  PRIMARY KEY (snapshot_id, extraction_version_id),
  FOREIGN KEY (matter_id, snapshot_id) REFERENCES corpus_snapshots(matter_id, id) ON DELETE CASCADE,
  FOREIGN KEY (matter_id, extraction_version_id)
    REFERENCES extraction_versions(matter_id, id) ON DELETE CASCADE
);

-- Immutability -------------------------------------------------------------------------------
CREATE FUNCTION trace_forbid_update() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'rows in % are immutable', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER source_spans_immutable BEFORE UPDATE ON source_spans
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
CREATE TRIGGER extraction_pages_immutable BEFORE UPDATE ON extraction_pages
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
CREATE TRIGGER source_embeddings_immutable BEFORE UPDATE ON source_embeddings
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();
CREATE TRIGGER corpus_snapshot_members_immutable BEFORE UPDATE ON corpus_snapshot_members
  FOR EACH ROW EXECUTE FUNCTION trace_forbid_update();

CREATE FUNCTION trace_document_version_guard() RETURNS trigger AS $$
BEGIN
  IF NEW.source_sha256 IS DISTINCT FROM OLD.source_sha256
     OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
     OR NEW.revision_no IS DISTINCT FROM OLD.revision_no
     OR NEW.document_id IS DISTINCT FROM OLD.document_id
     OR NEW.matter_id IS DISTINCT FROM OLD.matter_id THEN
    RAISE EXCEPTION 'document version identity is immutable' USING ERRCODE = 'restrict_violation';
  END IF;
  IF OLD.state = 'RETIRED' AND NEW.state <> 'RETIRED' THEN
    RAISE EXCEPTION 'retired versions cannot be reactivated' USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER document_versions_guard BEFORE UPDATE ON document_versions
  FOR EACH ROW EXECUTE FUNCTION trace_document_version_guard();

CREATE FUNCTION trace_extraction_version_guard() RETURNS trigger AS $$
BEGIN
  IF OLD.state = 'READY' THEN
    RAISE EXCEPTION 'published extraction versions are immutable'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER extraction_versions_guard BEFORE UPDATE ON extraction_versions
  FOR EACH ROW EXECUTE FUNCTION trace_extraction_version_guard();
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS corpus_snapshot_members, corpus_snapshots, source_embeddings,
  embedding_profiles, source_spans, extraction_pages, extraction_versions, document_versions CASCADE;
DROP FUNCTION IF EXISTS trace_forbid_update, trace_document_version_guard,
  trace_extraction_version_guard;
ALTER TABLE documents DROP COLUMN IF EXISTS current_version_id;
ALTER TABLE documents DROP CONSTRAINT IF EXISTS uq_documents_matter_id;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
