"""Give every pre-V3 document a version and extraction. Safe to run repeatedly."""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.domain import Document
from app.services.evidence_versions import backfill_legacy_document


def main() -> None:
    with SessionLocal() as db:
        documents = db.scalars(select(Document).where(Document.current_version_id.is_(None))).all()
        created = 0
        for document in documents:
            if backfill_legacy_document(db, document) is not None:
                created += 1
        db.commit()
        print(f"backfill_versions: {created} document(s) versioned, {len(documents) - created} skipped")


if __name__ == "__main__":
    main()
