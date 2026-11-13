import argparse
import hashlib
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.domain import (
    Document,
    DocumentChunk,
    DocumentPage,
    Entity,
    Matter,
    MatterMember,
    Organization,
    User,
)
from app.services.entities import extract_entities_for_matter
from app.services.evidence_versions import backfill_legacy_document
from app.services.ingestion import process_document
from app.services.storage import storage_service

SEED_TEXTS = [
    (
        "2024-03-05 Jane Mercer logged a Project Falcon quality note stating Compressor Unit 7A "
        "showed abnormal vibration during bench testing."
    ),
    (
        "2024-03-08 Northshore Supply's internal memo references a vibration defect risk before "
        "shipment and suggests the team knew the issue needed follow-up."
    ),
    (
        "2024-03-11 Priya Shah emailed Jane Mercer that payment approval remained conditional "
        "until the notice review and defect questions were resolved."
    ),
    (
        "2024-03-12 The shipping checklist for Compressor Unit 7A marked Project Falcon as ready "
        "despite an unresolved vibration comment."
    ),
    (
        "2024-03-15 Acme Industrial received Compressor Unit 7A and immediately recorded a delivery "
        "problem tied to vibration and startup instability."
    ),
    (
        "2024-03-18 A formal notice letter states Acme Industrial provided written notice of the "
        "delivery problem to Northshore Supply."
    ),
    (
        "2024-03-20 Priya Shah discussed payment approval but noted final authorization remained "
        "conditional pending notice review."
    ),
    (
        "2024-03-22 Northshore Supply disputed the notice timing and claimed it first learned of the "
        "Compressor Unit 7A defect after shipment."
    ),
    (
        "2024-03-25 Jane Mercer summarized that the defect knowledge issue contradicted the shipping "
        "team's earlier Project Falcon readiness message."
    ),
    (
        "2024-03-28 Acme Industrial reserved rights, withheld payment approval, and requested all "
        "Project Falcon inspection records from Northshore Supply."
    ),
    (
        "2024-03-19 An invoice approval log states Priya Shah approved payment authority for "
        "Project Falcon before later conditions were applied."
    ),
]

SEED_ENTITIES = [
    ("person", "Jane Mercer", ["J. Mercer"]),
    ("person", "Priya Shah", []),
    ("organization", "Northshore Supply LLC", ["Northshore", "NS Supply"]),
    ("organization", "Acme Industrial Systems", ["Acme", "Acme Industrial"]),
    ("project", "Project Falcon", ["Project Falcon Upgrade"]),
    ("equipment", "Compressor Unit 7A", ["Unit 7A", "7A"]),
]

def default_raw_seed_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "seed_data" / "raw" / "acme_matter"
        if candidate.exists():
            return candidate
    return Path("/app/seed_data/raw/acme_matter")


RAW_SEED_DIR = default_raw_seed_dir()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Trace demo data.")
    parser.add_argument(
        "--mode",
        choices=["fast", "raw"],
        default="fast",
        help="fast loads processed artifacts; raw uploads files and runs ingestion synchronously.",
    )
    args = parser.parse_args()

    # Schema comes from Alembic migrations (run at API start), never create_all.
    engine = create_engine(settings.database_url, future=True)
    with Session(engine) as db:
        _, seeded_users, matter = ensure_seed_shell(db)
        if args.mode == "raw":
            seed_raw_ingestion(db, matter, seeded_users["attorney@trace.local"])
        else:
            seed_fast_bootstrap(db, matter, seeded_users["attorney@trace.local"])
            db.flush()
            for document in db.scalars(select(Document).where(Document.matter_id == matter.id)):
                backfill_legacy_document(db, document)
        seed_entities(db, matter)
        db.flush()
        extract_entities_for_matter(db, matter.id, seeded_users["attorney@trace.local"].id)
        db.commit()
        print(f"Seeded Trace demo organization, users, matter, chunks, and entities via {args.mode} mode.")


def ensure_seed_shell(db: Session) -> tuple[Organization, dict[str, User], Matter]:
    org = db.scalar(select(Organization).where(Organization.slug == "trace-demo"))
    if org is None:
        org = Organization(name="Trace Demo Org", slug="trace-demo")
        db.add(org)
        db.flush()

    users = {
        "admin@trace.local": ("Trace Admin", "admin"),
        "attorney@trace.local": ("Avery Counsel", "member"),
        "reviewer@trace.local": ("Robin Reviewer", "member"),
    }
    seeded_users: dict[str, User] = {}
    for email, (name, role) in users.items():
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                organization_id=org.id,
                email=email,
                name=name,
                global_role=role,
                password_hash=hash_password("trace-demo-password"),
            )
            db.add(user)
            db.flush()
        seeded_users[email] = user

    matter = db.scalar(select(Matter).where(Matter.name == "Acme Industrial v. Northshore Supply"))
    if matter is None:
        matter = Matter(
            organization_id=org.id,
            name="Acme Industrial v. Northshore Supply",
            description="Synthetic seeded matter for Trace demos.",
            matter_code="TRACE-DEMO-001",
            created_by=seeded_users["attorney@trace.local"].id,
        )
        db.add(matter)
        db.flush()

    for email, user in seeded_users.items():
        membership = db.scalar(
            select(MatterMember).where(
                MatterMember.matter_id == matter.id, MatterMember.user_id == user.id
            )
        )
        if membership is None:
            role = "admin" if "admin" in email else ("attorney" if "attorney" in email else "reviewer")
            db.add(MatterMember(matter_id=matter.id, user_id=user.id, role=role))

    return org, seeded_users, matter


def seed_fast_bootstrap(db: Session, matter: Matter, attorney: User) -> None:
    for index, text in enumerate(SEED_TEXTS, start=1):
        storage_key = f"seed/{index}.txt"
        if not storage_service.object_exists(storage_key):
            storage_service.upload_fileobj(storage_key, BytesIO(text.encode("utf-8")), "text/plain")

    for index, text in enumerate(SEED_TEXTS, start=1):
        file_name = f"seed-document-{index}.txt"
        existing_document = db.scalar(
            select(Document).where(Document.matter_id == matter.id, Document.file_name == file_name)
        )
        if existing_document is None:
            document = Document(
                matter_id=matter.id,
                uploaded_by=attorney.id,
                file_name=file_name,
                display_name=f"Seed Document {index}",
                mime_type="text/plain",
                file_size_bytes=len(text.encode("utf-8")),
                storage_key=f"seed/{index}.txt",
                sha256=f"seed-{index}",
                page_count=1,
                parse_status="parsed",
                ocr_status="not_needed",
                ingest_status="ready",
            )
            db.add(document)
            db.flush()

            db.add(
                DocumentPage(
                    document_id=document.id,
                    page_number=1,
                    raw_text=text,
                    normalized_text=text,
                    has_text_layer=True,
                )
            )
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    matter_id=matter.id,
                    page_start=1,
                    page_end=1,
                    chunk_index=0,
                    text=text,
                    token_count=len(text.split()),
                )
            )
            continue

        existing_chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == existing_document.id))
        if existing_chunk is None:
            db.add(
                DocumentChunk(
                    document_id=existing_document.id,
                    matter_id=matter.id,
                    page_start=1,
                    page_end=1,
                    chunk_index=0,
                    text=text,
                    token_count=len(text.split()),
                )
            )


def seed_raw_ingestion(db: Session, matter: Matter, attorney: User) -> None:
    raw_files = sorted(RAW_SEED_DIR.glob("seed-document-*.txt"))
    if not raw_files:
        raise RuntimeError(f"No raw seed files found in {RAW_SEED_DIR}")

    for raw_file in raw_files:
        content = raw_file.read_bytes()
        storage_key = f"seed/raw/{raw_file.name}"
        if not storage_service.object_exists(storage_key):
            storage_service.upload_fileobj(storage_key, BytesIO(content), "text/plain")
        existing_document = db.scalar(
            select(Document).where(Document.matter_id == matter.id, Document.file_name == raw_file.name)
        )
        if existing_document is None:
            existing_document = Document(
                matter_id=matter.id,
                uploaded_by=attorney.id,
                file_name=raw_file.name,
                display_name=raw_file.stem.replace("-", " ").title(),
                mime_type="text/plain",
                file_size_bytes=len(content),
                storage_key=storage_key,
                sha256=hashlib.sha256(content).hexdigest(),
                parse_status="uploaded",
                ocr_status="not_needed",
                ingest_status="queued",
                metadata_json={"seed_mode": "raw"},
            )
            db.add(existing_document)
            db.flush()
        if existing_document.ingest_status != "completed":
            process_document(db, existing_document.id)


def seed_entities(db: Session, matter: Matter) -> None:
    for entity_type, canonical_name, aliases in SEED_ENTITIES:
        existing_entity = db.scalar(
            select(Entity).where(Entity.matter_id == matter.id, Entity.canonical_name == canonical_name)
        )
        if existing_entity is None:
            db.add(
                Entity(
                    matter_id=matter.id,
                    entity_type=entity_type,
                    canonical_name=canonical_name,
                    aliases_json=aliases,
                )
            )


if __name__ == "__main__":
    main()
