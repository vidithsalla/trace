import json
from collections.abc import Generator
from pathlib import Path
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.domain import (
    AIRun,
    Document,
    DocumentChunk,
    DocumentPage,
    Entity,
    Event,
    ExportJob,
    Matter,
    MatterMember,
    Memo,
    Organization,
    User,
)
from app.scripts.seed_demo import SEED_TEXTS
from app.services.evals import EvalRunner
from app.services.storage import storage_service


@pytest.fixture(autouse=True)
def _reset_storage_client():
    storage_service.client = None
    yield
    storage_service.client = None


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
def phase10_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 10 Test {suffix}", slug=f"phase-10-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"phase10-{suffix}@trace.local",
        name="Phase Ten Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"phase10-outsider-{suffix}@trace.local",
        name="Phase Ten Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 10 Matter {suffix}",
        matter_code=f"P10-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add(matter)
    db.flush()
    db.add(MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"))

    for index, text in enumerate(SEED_TEXTS, start=1):
        document = Document(
            matter_id=matter.id,
            uploaded_by=attorney.id,
            file_name=f"phase10-document-{index}.txt",
            display_name=f"Phase 10 Document {index}",
            mime_type="text/plain",
            file_size_bytes=len(text.encode("utf-8")),
            storage_key=f"tests/phase10/{matter.id}/{index}.txt",
            sha256=f"phase10-{uuid4()}",
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

    for name in ["Jane Mercer", "Priya Shah", "Northshore Supply LLC", "Project Falcon"]:
        db.add(Entity(matter_id=matter.id, entity_type="seed", canonical_name=name, aliases_json=[]))

    db.commit()
    yield {"org": org, "attorney": attorney, "outsider": outsider, "matter": matter}

    db.rollback()
    matter_ids = list(db.scalars(select(Matter.id).where(Matter.organization_id == org.id)))
    if matter_ids:
        db.execute(delete(ExportJob).where(ExportJob.matter_id.in_(matter_ids)))
        db.execute(delete(Memo).where(Memo.matter_id.in_(matter_ids)))
        db.execute(delete(AIRun).where(AIRun.matter_id.in_(matter_ids)))
        db.execute(delete(Event).where(Event.matter_id.in_(matter_ids)))
        db.execute(delete(Document).where(Document.matter_id.in_(matter_ids)))
    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def _login(client: TestClient, email: str, password: str = "correct-password") -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_chronology_exports_create_jobs_storage_downloads_and_audit(
    client: TestClient, db: Session, phase10_records: dict[str, object]
) -> None:
    attorney = phase10_records["attorney"]
    matter = phase10_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    chronology_response = client.post(
        f"/matters/{matter.id}/chronology",
        json={"topic": "notice payment defect Project Falcon", "limit": 20},
    )
    assert chronology_response.status_code == 200
    assert len(chronology_response.json()["events"]) >= 10

    csv_response = client.get(f"/matters/{matter.id}/chronology/export.csv")
    assert csv_response.status_code == 200
    assert "x-trace-export-id" in csv_response.headers
    csv_export_id = csv_response.headers["x-trace-export-id"]
    csv_job = db.get(ExportJob, UUID(csv_export_id))
    assert csv_job is not None
    assert csv_job.status == "completed"
    assert csv_job.storage_key
    assert storage_service.object_exists(csv_job.storage_key)

    docx_response = client.get(f"/matters/{matter.id}/chronology/export.docx")
    assert docx_response.status_code == 200
    assert docx_response.content.startswith(b"PK")
    docx_export_id = docx_response.headers["x-trace-export-id"]

    export_status = client.get(f"/exports/{docx_export_id}")
    assert export_status.status_code == 200
    assert export_status.json()["download_url"] == f"/exports/{docx_export_id}/download"

    download_response = client.get(f"/exports/{docx_export_id}/download")
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"PK")

    audit_response = client.get(f"/audit?matter_id={matter.id}&limit=200")
    assert audit_response.status_code == 200
    actions = {row["action"] for row in audit_response.json()}
    assert {"export_job_completed", "export_chronology_csv", "export_chronology_docx", "export_download"} <= actions

    audit_csv = client.get(f"/audit/export.csv?matter_id={matter.id}")
    assert audit_csv.status_code == 200
    assert "export_job_completed" in audit_csv.text


def test_memo_exports_are_backed_by_export_jobs(
    client: TestClient, db: Session, phase10_records: dict[str, object]
) -> None:
    attorney = phase10_records["attorney"]
    matter = phase10_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    memo_response = client.post(
        f"/matters/{matter.id}/memos",
        json={"issue": "Whether Acme gave timely notice of the delivery problem", "limit": 12},
    )
    assert memo_response.status_code == 201
    memo_id = memo_response.json()["id"]

    markdown_response = client.get(f"/memos/{memo_id}/export.md")
    assert markdown_response.status_code == 200
    markdown_job = db.get(ExportJob, UUID(markdown_response.headers["x-trace-export-id"]))
    assert markdown_job is not None
    assert markdown_job.export_type == "memo_markdown"
    assert markdown_job.status == "completed"

    docx_response = client.get(f"/memos/{memo_id}/export.docx")
    assert docx_response.status_code == 200
    assert docx_response.content.startswith(b"PK")
    docx_job = db.get(ExportJob, UUID(docx_response.headers["x-trace-export-id"]))
    assert docx_job is not None
    assert docx_job.export_type == "memo_docx"
    assert storage_service.object_exists(docx_job.storage_key)


def test_export_download_enforces_matter_access(
    client: TestClient, phase10_records: dict[str, object]
) -> None:
    attorney = phase10_records["attorney"]
    outsider = phase10_records["outsider"]
    matter = phase10_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(outsider, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    client.post(
        f"/matters/{matter.id}/chronology",
        json={"topic": "notice payment defect Project Falcon", "limit": 20},
    )
    csv_response = client.get(f"/matters/{matter.id}/chronology/export.csv")
    export_id = csv_response.headers["x-trace-export-id"]

    _login(client, outsider.email)
    assert client.get(f"/exports/{export_id}").status_code == 403
    assert client.get(f"/exports/{export_id}/download").status_code == 403
    assert client.get(f"/matters/{matter.id}/chronology/export.docx").status_code == 403


def test_eval_runner_checks_seeded_matter_and_exports(
    db: Session, tmp_path: Path, phase10_records: dict[str, object]
) -> None:
    matter = phase10_records["matter"]
    assert isinstance(matter, Matter)
    truth_path = tmp_path / "truth.json"
    truth_path.write_text(
        json.dumps(
            {
                "product_name": "Trace",
                "product_full_name": "Trace - Sovereign Discovery Copilot",
                "matter_name": matter.name,
                "entities": [{"canonical_name": "Jane Mercer", "aliases": []}],
                "known_contradictions": [{"topic": "notice timing"}],
                "golden_questions": [
                    {
                        "question": "What evidence suggests Northshore knew of the defect before shipment?",
                        "must_include": ["defect", "shipment"],
                    }
                ],
            }
        )
    )

    report = EvalRunner(db, truth_path).run()
    assert report["passed"] is True
    check_names = {check["name"] for check in report["checks"]}
    assert {"golden_questions", "known_contradictions", "chronology_exports", "memo_exports", "branding"} <= check_names
