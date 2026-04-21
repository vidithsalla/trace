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
    Event,
    EventCitation,
    ExportJob,
    Matter,
    MatterMember,
    Organization,
    User,
)
from app.schemas.workflow import ChronologyEvent, ChronologyRequest, ChronologyResponse, CitationPayload
from app.services.mock_model_client import MockModelClient
from app.services.model_client import EvidenceItem
from app.services.workflows import run_chronology_builder


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
def phase6_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 6 Test {suffix}", slug=f"phase-6-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"phase6-{suffix}@trace.local",
        name="Phase Six Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"phase6-outsider-{suffix}@trace.local",
        name="Phase Six Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 6 Matter {suffix}",
        matter_code=f"P6-{suffix[:8]}",
        created_by=attorney.id,
    )
    other_matter = Matter(
        organization_id=org.id,
        name=f"Phase 6 Other Matter {suffix}",
        matter_code=f"P6O-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add_all([matter, other_matter])
    db.flush()
    db.add(MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"))

    texts = [
        "2024-03-05 Jane Mercer recorded a Project Falcon defect concern for Compressor Unit 7A.",
        "2024-03-08 Northshore Supply internal memo said vibration defect risk was known before shipment.",
        "2024-03-11 Priya Shah wrote that payment approval remained conditional pending notice review.",
        "2024-03-12 Shipping checklist marked Compressor Unit 7A ready despite unresolved vibration notes.",
        "2024-03-15 Acme Industrial received Compressor Unit 7A and documented startup instability.",
        "2024-03-18 Acme Industrial sent written notice of the delivery problem to Northshore Supply.",
        "2024-03-20 Priya Shah discussed payment approval and repeated the notice condition.",
        "2024-03-22 Northshore Supply disputed notice timing and defect knowledge before shipment.",
        "2024-03-25 Jane Mercer noted the Project Falcon readiness message contradicted the defect history.",
        "2024-03-28 Acme Industrial withheld payment approval and requested Project Falcon inspection records.",
    ]
    documents = [
        _add_document_with_chunk(db, matter=matter, user=attorney, name=f"event-{index}.txt", text=text)
        for index, text in enumerate(texts, start=1)
    ]
    _add_document_with_chunk(
        db,
        matter=other_matter,
        user=attorney,
        name="other-matter-event.txt",
        text="2024-03-08 Other matter Northshore event must not appear in the chronology.",
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
        db.execute(delete(ExportJob).where(ExportJob.matter_id.in_(matter_ids)))
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
        sha256=f"phase6-{uuid4()}",
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


def test_chronology_generation_persists_events_and_event_citations(
    client: TestClient, db: Session, phase6_records: dict[str, object]
) -> None:
    attorney = phase6_records["attorney"]
    matter = phase6_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{matter.id}/chronology",
        json={"topic": "notice payment approval defect knowledge", "limit": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_run_id"] is not None
    assert len(body["events"]) >= 10
    assert all(event["id"] for event in body["events"])
    assert all(event["citations"] for event in body["events"])
    assert all(
        citation["validation_status"] == "validated"
        for event in body["events"]
        for citation in event["citations"]
    )
    assert any(event["conflict_flag"] for event in body["events"])

    run = db.get(AIRun, body["ai_run_id"])
    assert run is not None
    assert run.status == "completed"
    assert run.prompt_template_version == "chronology_builder_v1"
    assert run.output_json["validation"]["persisted_event_count"] == len(body["events"])

    event_count = db.scalar(select(func.count()).select_from(Event).where(Event.matter_id == matter.id))
    citation_count = db.scalar(
        select(func.count())
        .select_from(EventCitation)
        .join(Event, Event.id == EventCitation.event_id)
        .where(Event.matter_id == matter.id)
    )
    assert event_count == len(body["events"])
    assert citation_count >= len(body["events"])


def test_chronology_rejects_unvalidated_event_citations(
    db: Session, phase6_records: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    attorney = phase6_records["attorney"]
    matter = phase6_records["matter"]
    documents = phase6_records["documents"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)
    assert isinstance(documents, list)
    chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == documents[0].id))
    assert chunk is not None

    class BadCitationChronologyClient(MockModelClient):
        def chronology(self, request: ChronologyRequest, evidence: list[EvidenceItem]) -> ChronologyResponse:
            return ChronologyResponse(
                events=[
                    ChronologyEvent(
                        date_text="March 5, 2024",
                        title="Badly cited event",
                        description="This should not persist.",
                        citations=[
                            CitationPayload(
                                document_id=documents[0].id,
                                document_name=documents[0].file_name,
                                page=1,
                                chunk_id=chunk.id,
                                quote="This quote does not exist in the source material.",
                            )
                        ],
                    )
                ],
                unresolved_ambiguities=[],
            )

    monkeypatch.setattr("app.services.workflows._get_model_client", lambda: BadCitationChronologyClient())

    response = run_chronology_builder(
        db,
        matter.id,
        attorney.id,
        ChronologyRequest(topic="defect knowledge", limit=5),
    )

    assert response.events == []
    assert "excluded" in response.unresolved_ambiguities[0]
    persisted_count = db.scalar(select(func.count()).select_from(Event).where(Event.matter_id == matter.id))
    assert persisted_count == 0


def test_chronology_listing_edit_and_csv_export(
    client: TestClient, db: Session, phase6_records: dict[str, object]
) -> None:
    attorney = phase6_records["attorney"]
    matter = phase6_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    generate = client.post(
        f"/matters/{matter.id}/chronology",
        json={"topic": "Project Falcon payment notice", "entity_name": "Jane Mercer", "limit": 20},
    )
    assert generate.status_code == 200
    first_event = generate.json()["events"][0]

    list_response = client.get(f"/matters/{matter.id}/chronology/events?entity_name=Jane")
    assert list_response.status_code == 200
    assert list_response.json()

    patch_response = client.patch(
        f"/events/{first_event['id']}",
        json={"title": "Edited chronology event", "conflict_flag": True, "date_confidence": "high"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Edited chronology event"
    assert patch_response.json()["source_type"] == "user_edited"

    audit_count = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.matter_id == matter.id, AuditLog.action == "update_chronology_event")
    )
    assert audit_count == 1

    csv_response = client.get(f"/matters/{matter.id}/chronology/export.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "Edited chronology event" in csv_response.text
    assert "citations" in csv_response.text


def test_chronology_routes_enforce_matter_access(
    client: TestClient, phase6_records: dict[str, object]
) -> None:
    outsider = phase6_records["outsider"]
    matter = phase6_records["matter"]
    assert isinstance(outsider, User)
    assert isinstance(matter, Matter)

    _login(client, outsider.email)

    assert client.post(f"/matters/{matter.id}/chronology", json={"topic": "defect"}).status_code == 403
    assert client.get(f"/matters/{matter.id}/chronology/events").status_code == 403
    assert client.get(f"/matters/{matter.id}/chronology/export.csv").status_code == 403
