from collections.abc import Generator
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.domain import (
    AuditLog,
    Document,
    DocumentChunk,
    DocumentPage,
    Matter,
    MatterMember,
    Organization,
    User,
)
from app.services.storage import storage_service


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
def phase4_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 4 Test {suffix}", slug=f"phase-4-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"viewer-attorney-{suffix}@trace.local",
        name="Phase Four Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"viewer-outsider-{suffix}@trace.local",
        name="Phase Four Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 4 Matter {suffix}",
        matter_code=f"P4-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add(matter)
    db.flush()
    db.add(MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"))

    source_text = "Northshore source evidence appears on page one for Compressor Unit 7A."
    storage_key = f"tests/{matter.id}/{uuid4()}-viewer.txt"
    storage_service.upload_fileobj(storage_key, BytesIO(source_text.encode("utf-8")), "text/plain")

    document = Document(
        matter_id=matter.id,
        uploaded_by=attorney.id,
        file_name="viewer.txt",
        display_name="Viewer Source",
        mime_type="text/plain",
        file_size_bytes=len(source_text.encode("utf-8")),
        storage_key=storage_key,
        sha256="phase4",
        page_count=1,
        parse_status="completed",
        ocr_status="not_needed",
        ingest_status="completed",
        extraction_quality_score=0.95,
    )
    db.add(document)
    db.flush()
    page = DocumentPage(
        document_id=document.id,
        page_number=1,
        raw_text=source_text,
        normalized_text=source_text,
        has_text_layer=True,
        metadata_json={"parser": "txt"},
    )
    db.add(page)
    db.add(
        DocumentChunk(
            document_id=document.id,
            matter_id=matter.id,
            page_start=1,
            page_end=1,
            chunk_index=0,
            text=source_text,
            token_count=len(source_text.split()),
            embedding=[0.0] * 384,
        )
    )
    db.commit()

    yield {
        "org": org,
        "attorney": attorney,
        "outsider": outsider,
        "matter": matter,
        "document": document,
        "page": page,
        "source_text": source_text,
        "storage_key": storage_key,
    }

    storage_service.delete_object(storage_key)
    db.execute(delete(Document).where(Document.id == document.id))
    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def _login(client: TestClient, email: str, password: str = "correct-password") -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_authorized_user_can_open_document_page_and_source_file(
    client: TestClient, db: Session, phase4_records: dict[str, object]
) -> None:
    attorney = phase4_records["attorney"]
    document = phase4_records["document"]
    source_text = phase4_records["source_text"]
    assert isinstance(attorney, User)
    assert isinstance(document, Document)
    assert isinstance(source_text, str)

    _login(client, attorney.email)
    detail_response = client.get(f"/documents/{document.id}")
    page_response = client.get(f"/documents/{document.id}/pages/1")
    file_response = client.get(f"/documents/{document.id}/file")

    assert detail_response.status_code == 200
    assert detail_response.json()["file_name"] == "viewer.txt"
    assert page_response.status_code == 200
    assert page_response.json()["normalized_text"] == source_text
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("text/plain")
    assert file_response.content == source_text.encode("utf-8")

    audit_actions = set(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.matter_id == document.matter_id,
                AuditLog.action.in_(["view_document_page", "view_document_file"]),
            )
        )
    )
    assert {"view_document_page", "view_document_file"} <= audit_actions


def test_unauthorized_user_cannot_open_viewer_resources(
    client: TestClient, phase4_records: dict[str, object]
) -> None:
    outsider = phase4_records["outsider"]
    document = phase4_records["document"]
    assert isinstance(outsider, User)
    assert isinstance(document, Document)

    _login(client, outsider.email)

    assert client.get(f"/documents/{document.id}").status_code == 403
    assert client.get(f"/documents/{document.id}/pages/1").status_code == 403
    assert client.get(f"/documents/{document.id}/file").status_code == 403


def test_missing_page_returns_not_found(client: TestClient, phase4_records: dict[str, object]) -> None:
    attorney = phase4_records["attorney"]
    document = phase4_records["document"]
    assert isinstance(attorney, User)
    assert isinstance(document, Document)

    _login(client, attorney.email)
    response = client.get(f"/documents/{document.id}/pages/99")

    assert response.status_code == 404
    assert response.json()["detail"] == "Page not found"


def test_search_result_contains_exact_viewer_identifiers(
    client: TestClient, phase4_records: dict[str, object]
) -> None:
    attorney = phase4_records["attorney"]
    matter = phase4_records["matter"]
    document = phase4_records["document"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)
    assert isinstance(document, Document)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{matter.id}/search",
        json={"query": "Northshore source evidence", "limit": 5},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["document_id"] == str(document.id)
    assert result["page_number"] == 1
    assert result["chunk_id"] is not None
    assert "Northshore source evidence" in result["snippet"]
