"""Record EXPLAIN (ANALYZE, BUFFERS) for the production retrieval queries on one matter.

    python -m app.scripts.explain_retrieval --matter <uuid> [--copies N]

``--copies N`` builds a throwaway matter with N copies of the target matter's text (so plans can be
seen at a larger size), runs the plans there, and deletes it afterwards. Output goes to stdout;
`make explain-retrieval` saves it under evals/reports/.
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import delete, select, text

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.domain import Document, Matter, User
from app.models.evidence import ExtractionPage, ExtractionVersion
from app.services import retrieval_v3
from app.services.embeddings import LocalHashEmbeddingClient
from app.services.evidence_versions import create_snapshot
from app.services.text_ingest import ingest_text_document

QUESTION = "Was invoice 7A approved unconditionally on March 18?"
CLAIM = "Invoice 7A was approved for payment without conditions."


def explain(db, built) -> str:
    statement, params = built
    rows = db.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + statement.text), params).all()
    return "\n".join(r[0] for r in rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matter", required=True)
    parser.add_argument("--copies", type=int, default=0)
    args = parser.parse_args()
    with SessionLocal() as db:
        matter = db.get(Matter, uuid.UUID(args.matter))
        target, scratch = matter, None
        if args.copies:
            user = db.get(User, matter.created_by)
            scratch = Matter(organization_id=matter.organization_id, name=f"explain {uuid.uuid4().hex[:6]}",
                             matter_code=uuid.uuid4().hex[:10], created_by=user.id)
            db.add(scratch)
            db.flush()
            texts = db.execute(select(ExtractionPage.text).join(
                ExtractionVersion, ExtractionVersion.id == ExtractionPage.extraction_version_id).join(
                Document, Document.current_version_id == ExtractionVersion.document_version_id).where(
                Document.matter_id == matter.id)).scalars().all()
            for i in range(args.copies):
                for j, body in enumerate(texts):
                    ingest_text_document(db, scratch, user, f"copy-{i}-{j}.txt", f"{body}\n\nCopy {i}.")
            db.commit()
            target = scratch
        try:
            snapshot = create_snapshot(db, target.id, None)
            db.commit()
            spans = db.execute(text("SELECT count(*) FROM corpus_snapshot_members m JOIN source_spans s "
                                    "ON s.extraction_version_id = m.extraction_version_id "
                                    "WHERE m.snapshot_id = :s"), {"s": snapshot.id}).scalar_one()
            print(f"# Retrieval query plans · spans in snapshot: {spans} · "
                  f"postgres {db.execute(text('SHOW server_version')).scalar_one()} · code {settings.code_commit}\n")
            vector = LocalHashEmbeddingClient().embed_texts([QUESTION])[0]
            for name, built in [
                ("lexical", retrieval_v3.lexical_sql(matter_id=target.id, snapshot_id=snapshot.id, query=QUESTION, k=24)),
                ("semantic (hash-v1 vectors, exact <=>)", retrieval_v3.semantic_sql(
                    matter_id=target.id, snapshot_id=snapshot.id, vector=vector, k=24, profile_id="hash-v1")),
                ("counterevidence challenge", retrieval_v3.challenge_sql(
                    matter_id=target.id, snapshot_id=snapshot.id, claim=CLAIM, k=12)),
            ]:
                print(f"## {name}\n\n```\n{explain(db, built)}\n```\n")
        finally:
            if scratch is not None:
                db.rollback()
                db.execute(delete(Matter).where(Matter.id == scratch.id))
                db.commit()


if __name__ == "__main__":
    main()
