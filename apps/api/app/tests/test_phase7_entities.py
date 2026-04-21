from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.domain import (
    AIRun,
    AuditLog,
    Document,
    DocumentChunk,
    DocumentPage,
    Entity,
    EntityMention,
    Event,
    Matter,
    MatterMember,
    Organization,
    User,
)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def phase7_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 7 Test {suffix}", slug=f"phase-7-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"phase7-{suffix}@trace.local",
        name="Phase Seven Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"phase7-outsider-{suffix}@trace.local",
        name="Phase Seven Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 7 Matter {suffix}",
        matter_code=f"P7-{suffix[:8]}",
        created_by=attorney.id,
    )
    other_matter = Matter(
        organization_id=org.id,
        name=f"Phase 7 Other Matter {suffix}",
        matter_code=f"P7O-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add_all([matter, other_matter])
    db.flush()
    db.add(MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"))

    texts = [
        "2024-03-05 Jane Mercer recorded a Project Falcon concern for Compressor Unit 7A.",
        "2024-03-08 Northshore Supply internal memo said Compressor Unit 7A defect risk was known before shipment.",
        "2024-03-11 Priya Shah wrote that payment approval remained conditional pending notice review.",
        "2024-03-18 Acme Industrial sent written notice to Northshore Supply.",
        "2024-03-25 Jane Mercer said Project Falcon readiness contradicted the defect history.",
    ]
    documents = [
        _add_document_with_chunk(db, matter=matter, user=attorney, name=f"entity-{index}.txt", text=text)
        for index, text in enumerate(texts, start=1)
    ]
    _add_document_with_chunk(
        db,
        matter=other_matter,
        user=attorney,
        name="other-entity.txt",
        text="Jane Mercer in another matter must not leak into this entity set.",
    )
    db.add(
        Event(
            matter_id=matter.id,
            event_date_text="March 5, 2024",
            title="Jane Mercer records Project Falcon concern",
            description="Jane Mercer recorded a Project Falcon concern for Compressor Unit 7A.",
            entities_json=["Jane Mercer", "Project Falcon", "Compressor Unit 7A"],
            confidence="high",
        )
    )
    db.commit()

    yield {
        "org": org,
        "attorney": attorney,
        "outsider": outsider,
        "matter": matter,
        "other_matter": other_matter,
        "documents": documents,
    }

    db.rollback()
    matter_ids = list(db.scalars(select(Matter.id).where(Matter.organization_id == org.id)))
    if matter_ids:
        db.execute(delete(AIRun).where(AIRun.matter_id.in_(matter_ids)))
        db.execute(delete(Document).where(Document.matter_id.in_(matter_ids)))
    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def _add_document_with_chunk(
    db: Session, matter: Matter, user: User, name: str, text: str
) -> Document:
    document = Document(
        matter_id=matter.id,
        uploaded_by=user.id,
        file_name=name,
        display_name=name,
        mime_type="text/plain",
        file_size_bytes=len(text.encode("utf-8")),
        storage_key=f"tests/{matter.id}/{name}",
        sha256=f"phase7-{uuid4()}",
        page_count=1,
        parse_status="completed",
        ocr_status="not_needed",
        ingest_status="completed",
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
            embedding=[0.0] * 384,
        )
    )
    return document


def _login(client: TestClient, email: str, password: str = "correct-password") -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_entity_extraction_creates_required_evidence_backed_pages(
    client: TestClient, db: Session, phase7_records: dict[str, object]
) -> None:
    attorney = phase7_records["attorney"]
    matter = phase7_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    response = client.post(f"/matters/{matter.id}/entities/extract")

    assert response.status_code == 200
    entities = response.json()
    names = {entity["canonical_name"]: entity for entity in entities}
    assert "Jane Mercer" in names
    assert "Priya Shah" in names
    assert "Project Falcon" in names
    assert "Compressor Unit 7A" in names
    assert any(name.startswith("Northshore Supply") for name in names)

    for required_name in ["Jane Mercer", "Priya Shah", "Project Falcon", "Compressor Unit 7A"]:
        assert names[required_name]["mention_count"] >= 1
        assert names[required_name]["key_documents"]
        assert names[required_name]["summary_json"]["workflow"] == "entity_summary_v1"

    jane_id = names["Jane Mercer"]["id"]
    detail_response = client.get(f"/entities/{jane_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["mentions"]
    assert detail["timeline"]
    assert detail["mentions"][0]["viewer_url"].startswith(f"/matters/{matter.id}/documents/")
    assert "Jane Mercer" in detail["summary_json"]["overview"]

    summary_run_count = db.scalar(
        select(func.count())
        .select_from(AIRun)
        .where(AIRun.matter_id == matter.id, AIRun.run_type == "entity_summary")
    )
    assert summary_run_count >= 5


def test_alias_merge_combines_duplicate_entities_without_losing_mentions(
    client: TestClient, db: Session, phase7_records: dict[str, object]
) -> None:
    attorney = phase7_records["attorney"]
    matter = phase7_records["matter"]
    documents = phase7_records["documents"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)
    assert isinstance(documents, list)

    _login(client, attorney.email)
    extract_response = client.post(f"/matters/{matter.id}/entities/extract")
    assert extract_response.status_code == 200
    jane = next(entity for entity in extract_response.json() if entity["canonical_name"] == "Jane Mercer")

    chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == documents[0].id))
    assert chunk is not None
    duplicate = Entity(
        matter_id=matter.id,
        entity_type="person",
        canonical_name="J. Mercer",
        aliases_json=[],
        confidence=0.7,
    )
    db.add(duplicate)
    db.flush()
    duplicate_id = duplicate.id
    db.add(
        EntityMention(
            entity_id=duplicate_id,
            document_id=documents[0].id,
            chunk_id=chunk.id,
            page_number=1,
            mention_text="J. Mercer",
            context_text="J. Mercer is another alias for Jane Mercer in Project Falcon.",
            confidence=0.7,
        )
    )
    db.commit()

    merge_response = client.post(
        f"/entities/{jane['id']}/merge",
        json={"source_entity_id": str(duplicate_id)},
    )
    assert merge_response.status_code == 200
    merged = merge_response.json()
    assert "J. Mercer" in merged["aliases_json"]
    assert merged["mention_count"] >= jane["mention_count"] + 1
    db.expire_all()
    assert db.get(Entity, duplicate_id) is None

    audit_count = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.matter_id == matter.id, AuditLog.action == "merge_entity_alias")
    )
    assert audit_count == 1


def test_entity_routes_enforce_matter_access(
    client: TestClient, phase7_records: dict[str, object]
) -> None:
    attorney = phase7_records["attorney"]
    outsider = phase7_records["outsider"]
    matter = phase7_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(outsider, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    extract_response = client.post(f"/matters/{matter.id}/entities/extract")
    assert extract_response.status_code == 200
    entity_id = extract_response.json()[0]["id"]

    _login(client, outsider.email)
    assert client.get(f"/matters/{matter.id}/entities").status_code == 403
    assert client.post(f"/matters/{matter.id}/entities/extract").status_code == 403
    assert client.get(f"/entities/{entity_id}").status_code == 403
