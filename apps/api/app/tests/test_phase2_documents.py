from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.domain import AuditLog, Document, IngestJob, Matter, MatterMember, Organization, User
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
def phase2_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 2 Test {suffix}", slug=f"phase-2-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"attorney-{suffix}@trace.local",
        name="Phase Two Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"outsider-{suffix}@trace.local",
        name="Phase Two Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 2 Matter {suffix}",
        description="Matter for document upload tests.",
        matter_code=f"P2-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add(matter)
    db.flush()
    db.add(MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"))
    db.commit()

    yield {"org": org, "attorney": attorney, "outsider": outsider, "matter": matter}

    matter_ids = list(db.scalars(select(Matter.id).where(Matter.organization_id == org.id)))
    if matter_ids:
        db.execute(delete(Document).where(Document.matter_id.in_(matter_ids)))
    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def _login(client: TestClient, email: str, password: str = "correct-password") -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_upload_persists_document_storage_job_and_audit(
    client: TestClient,
    db: Session,
    phase2_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matter = phase2_records["matter"]
    attorney = phase2_records["attorney"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda document_id: None)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{matter.id}/documents/upload",
        files={"file": ("phase2.txt", b"Phase 2 upload text", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "phase2.txt"
    assert body["mime_type"] == "text/plain"
    assert body["file_size_bytes"] == len(b"Phase 2 upload text")
    assert body["ingest_status"] == "queued"
    assert body["ocr_status"] == "not_needed"

    document = db.get(Document, body["id"])
    assert document is not None
    assert storage_service.object_exists(document.storage_key)

    ingest_job = db.scalar(select(IngestJob).where(IngestJob.document_id == document.id))
    assert ingest_job is not None
    assert ingest_job.status == "queued"

    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "upload_document",
            AuditLog.target_id == document.id,
            AuditLog.matter_id == matter.id,
        )
    )
    assert audit is not None

    storage_service.delete_object(document.storage_key)


def test_unauthorized_user_cannot_upload_to_matter(
    client: TestClient,
    phase2_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matter = phase2_records["matter"]
    outsider = phase2_records["outsider"]
    assert isinstance(matter, Matter)
    assert isinstance(outsider, User)
    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda document_id: None)

    _login(client, outsider.email)
    response = client.post(
        f"/matters/{matter.id}/documents/upload",
        files={"file": ("blocked.txt", b"blocked", "text/plain")},
    )

    assert response.status_code == 403


def test_upload_rejects_unsupported_file_type(
    client: TestClient,
    db: Session,
    phase2_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matter = phase2_records["matter"]
    attorney = phase2_records["attorney"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda document_id: None)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{matter.id}/documents/upload",
        files={"file": ("script.exe", b"not allowed", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type"
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "upload_document_failed",
            AuditLog.matter_id == matter.id,
        )
    )
    assert audit is not None
    assert audit.metadata_json["detail"] == "Unsupported file type"


def test_upload_rejects_oversized_file(
    client: TestClient,
    db: Session,
    phase2_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matter = phase2_records["matter"]
    attorney = phase2_records["attorney"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda document_id: None)
    monkeypatch.setattr(settings, "max_upload_bytes", 4)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{matter.id}/documents/upload",
        files={"file": ("too-large.txt", b"larger than four bytes", "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "File too large"
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "upload_document_failed",
            AuditLog.matter_id == matter.id,
        )
    )
    assert audit is not None
    assert audit.metadata_json["status_code"] == 413


def test_upload_rejects_signature_mismatch(
    client: TestClient,
    phase2_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matter = phase2_records["matter"]
    attorney = phase2_records["attorney"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda document_id: None)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{matter.id}/documents/upload",
        files={"file": ("fake.pdf", b"not actually a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File signature does not match declared type"


def test_list_documents_is_matter_scoped(
    client: TestClient,
    phase2_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matter = phase2_records["matter"]
    attorney = phase2_records["attorney"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda document_id: None)

    _login(client, attorney.email)
    upload = client.post(
        f"/matters/{matter.id}/documents/upload",
        files={"file": ("listed.csv", b"col\nvalue\n", "text/csv")},
    )
    assert upload.status_code == 200

    response = client.get(f"/matters/{matter.id}/documents")
    assert response.status_code == 200
    names = {document["file_name"] for document in response.json()}
    assert "listed.csv" in names

    document_id = UUID(upload.json()["id"])
    with SessionLocal() as cleanup_db:
        stored = cleanup_db.get(Document, document_id)
        assert stored is not None
        storage_service.delete_object(stored.storage_key)
