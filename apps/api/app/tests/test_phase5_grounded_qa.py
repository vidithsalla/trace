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
    Citation,
    Document,
    DocumentChunk,
    DocumentPage,
    Matter,
    MatterMember,
    Organization,
    User,
)
from app.schemas.workflow import CitationPayload, GroundedQARequest
from app.services.citations import validate_citations
from app.services.mock_model_client import MockModelClient
from app.services.model_client import EvidenceItem, ModelClientError
from app.services.workflows import run_grounded_qa


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
def phase5_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 5 Test {suffix}", slug=f"phase-5-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"phase5-{suffix}@trace.local",
        name="Phase Five Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add(attorney)
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 5 Matter {suffix}",
        matter_code=f"P5-{suffix[:8]}",
        created_by=attorney.id,
    )
    other_matter = Matter(
        organization_id=org.id,
        name=f"Phase 5 Other Matter {suffix}",
        matter_code=f"P5O-{suffix[:8]}",
        created_by=attorney.id,
    )
    empty_matter = Matter(
        organization_id=org.id,
        name=f"Phase 5 Empty Matter {suffix}",
        matter_code=f"P5E-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add_all([matter, other_matter, empty_matter])
    db.flush()
    db.add_all(
        [
            MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"),
            MatterMember(matter_id=other_matter.id, user_id=attorney.id, role="attorney"),
            MatterMember(matter_id=empty_matter.id, user_id=attorney.id, role="attorney"),
        ]
    )

    documents = [
        _add_document_with_chunk(
            db,
            matter=matter,
            user=attorney,
            name="defect-knowledge-1.txt",
            text=(
                "Northshore internal memo says the vibration defect risk on Compressor Unit 7A "
                "was known before shipment and needed follow-up."
            ),
        ),
        _add_document_with_chunk(
            db,
            matter=matter,
            user=attorney,
            name="defect-knowledge-2.txt",
            text=(
                "A shipping review says Northshore discussed the defect before shipment and "
                "flagged Compressor Unit 7A for review."
            ),
        ),
        _add_document_with_chunk(
            db,
            other_matter,
            attorney,
            "other-matter.txt",
            "Northshore defect before shipment belongs to another matter and must not leak.",
        ),
    ]
    db.commit()

    yield {
        "org": org,
        "attorney": attorney,
        "matter": matter,
        "other_matter": other_matter,
        "empty_matter": empty_matter,
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
        sha256=f"phase5-{uuid4()}",
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


def test_grounded_qa_persists_ai_run_and_validated_citations(
    client: TestClient, db: Session, phase5_records: dict[str, object]
) -> None:
    attorney = phase5_records["attorney"]
    matter = phase5_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{matter.id}/ask",
        json={"question": "What evidence suggests Northshore knew of the defect before shipment?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_run_id"] is not None
    assert body["citations"]
    assert all(citation["validation_status"] == "validated" for citation in body["citations"])
    assert all(citation["viewer_url"].startswith(f"/matters/{matter.id}/documents/") for citation in body["citations"])

    run = db.get(AIRun, body["ai_run_id"])
    assert run is not None
    assert run.status == "completed"
    assert run.prompt_template_version == "grounded_qa_v1"
    assert run.output_json["validation"]["workflow"] == "citation_check_v1"

    persisted_count = db.scalar(select(func.count()).select_from(Citation).where(Citation.ai_run_id == run.id))
    assert persisted_count == len(body["citations"])


def test_grounded_qa_returns_insufficient_evidence_for_empty_matter(
    client: TestClient, db: Session, phase5_records: dict[str, object]
) -> None:
    attorney = phase5_records["attorney"]
    empty_matter = phase5_records["empty_matter"]
    assert isinstance(attorney, User)
    assert isinstance(empty_matter, Matter)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{empty_matter.id}/ask",
        json={"question": "What evidence suggests Northshore knew of the defect before shipment?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["short_answer"] == "Insufficient evidence."
    assert body["citations"] == []
    assert body["ai_run_id"] is not None
    run = db.get(AIRun, body["ai_run_id"])
    assert run is not None
    assert run.status == "completed"


def test_single_valid_citation_returns_low_confidence(
    db: Session, phase5_records: dict[str, object]
) -> None:
    attorney = phase5_records["attorney"]
    matter = phase5_records["matter"]
    documents = phase5_records["documents"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)
    assert isinstance(documents, list)

    db.execute(delete(Document).where(Document.id == documents[1].id))
    db.commit()

    response = run_grounded_qa(
        db,
        matter.id,
        attorney.id,
        GroundedQARequest(question="What evidence suggests Northshore knew of the defect before shipment?"),
    )

    assert response.citations
    assert len(response.citations) == 1
    assert response.confidence == "low"


def test_citation_validation_rejects_nonexistent_quote(
    db: Session, phase5_records: dict[str, object]
) -> None:
    matter = phase5_records["matter"]
    documents = phase5_records["documents"]
    assert isinstance(matter, Matter)
    assert isinstance(documents, list)
    chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == documents[0].id))
    assert chunk is not None

    citations = validate_citations(
        db,
        matter.id,
        [
            CitationPayload(
                document_id=documents[0].id,
                document_name=documents[0].file_name,
                page=1,
                chunk_id=chunk.id,
                quote="This quote does not exist in the source material.",
            )
        ],
    )

    assert citations == []


def test_model_provider_error_becomes_safe_failed_run(
    db: Session, phase5_records: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    attorney = phase5_records["attorney"]
    matter = phase5_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    class FailingModelClient(MockModelClient):
        def grounded_qa(self, question: str, evidence: list[EvidenceItem]):
            raise ModelClientError("provider timeout")

    monkeypatch.setattr("app.services.workflows._get_model_client", lambda: FailingModelClient())

    response = run_grounded_qa(
        db,
        matter.id,
        attorney.id,
        GroundedQARequest(question="What evidence suggests Northshore knew of the defect before shipment?"),
    )

    assert response.short_answer == "Model provider failure."
    assert response.unsupported_claims_detected is True
    run = db.get(AIRun, response.ai_run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error_message == "ModelClientError"
