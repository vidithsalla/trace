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
from app.schemas.workflow import (
    CitationPayload,
    ContradictionItem,
    ContradictionRequest,
    ContradictionResponse,
)
from app.services.mock_model_client import MockModelClient
from app.services.model_client import EvidenceItem
from app.services.workflows import run_contradiction_finder


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
def phase8_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 8 Test {suffix}", slug=f"phase-8-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"phase8-{suffix}@trace.local",
        name="Phase Eight Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"phase8-outsider-{suffix}@trace.local",
        name="Phase Eight Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 8 Matter {suffix}",
        matter_code=f"P8-{suffix[:8]}",
        created_by=attorney.id,
    )
    one_sided_matter = Matter(
        organization_id=org.id,
        name=f"Phase 8 One Sided Matter {suffix}",
        matter_code=f"P8S-{suffix[:8]}",
        created_by=attorney.id,
    )
    other_matter = Matter(
        organization_id=org.id,
        name=f"Phase 8 Other Matter {suffix}",
        matter_code=f"P8O-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add_all([matter, one_sided_matter, other_matter])
    db.flush()
    db.add_all(
        [
            MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"),
            MatterMember(matter_id=one_sided_matter.id, user_id=attorney.id, role="attorney"),
        ]
    )

    texts = [
        "2024-03-18 A formal notice letter states Acme provided written notice to Northshore Supply.",
        "2024-03-22 Northshore Supply disputed the notice timing and called the notice late and incomplete.",
        "2024-03-19 Priya Shah approved payment authority for Project Falcon.",
        "2024-03-20 Priya Shah said final authorization remained conditional pending notice review.",
        "2024-03-08 Northshore Supply internal memo said the defect risk was known before shipment.",
        "2024-03-22 Northshore Supply claimed it first learned of the Compressor Unit 7A defect after shipment.",
    ]
    documents = [
        _add_document_with_chunk(db, matter=matter, user=attorney, name=f"contradiction-{index}.txt", text=text)
        for index, text in enumerate(texts, start=1)
    ]
    _add_document_with_chunk(
        db,
        matter=one_sided_matter,
        user=attorney,
        name="one-sided-notice.txt",
        text="2024-03-18 A formal notice letter states Acme provided written notice.",
    )
    _add_document_with_chunk(
        db,
        matter=other_matter,
        user=attorney,
        name="other-matter.txt",
        text="Northshore disputed notice timing in a different matter and must not leak.",
    )
    db.commit()

    yield {
        "org": org,
        "attorney": attorney,
        "outsider": outsider,
        "matter": matter,
        "one_sided_matter": one_sided_matter,
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
        sha256=f"phase8-{uuid4()}",
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


@pytest.mark.parametrize(
    ("topic", "expected_phrase"),
    [
        ("notice timing", "written notice"),
        ("payment approval authority", "conditional"),
        ("defect knowledge", "before shipment"),
    ],
)
def test_seeded_contradiction_topics_surface_with_validated_citations(
    client: TestClient,
    db: Session,
    phase8_records: dict[str, object],
    topic: str,
    expected_phrase: str,
) -> None:
    attorney = phase8_records["attorney"]
    matter = phase8_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    response = client.post(f"/matters/{matter.id}/contradictions", json={"topic": topic})

    assert response.status_code == 200
    body = response.json()
    assert body["ai_run_id"] is not None
    assert body["contradictions"]
    contradiction = body["contradictions"][0]
    assert contradiction["severity"] in {"low", "medium", "high"}
    assert contradiction["citations_a"]
    assert contradiction["citations_b"]
    assert all(citation["validation_status"] == "validated" for citation in contradiction["citations_a"])
    assert all(citation["validation_status"] == "validated" for citation in contradiction["citations_b"])
    assert any(expected_phrase in citation["quote"].lower() for citation in [*contradiction["citations_a"], *contradiction["citations_b"]])

    run = db.get(AIRun, body["ai_run_id"])
    assert run is not None
    assert run.status == "completed"
    assert run.prompt_template_version == "contradiction_finder_v1"
    assert run.output_json["validation"]["persisted_contradiction_count"] == 1
    persisted_citation_count = db.scalar(
        select(func.count()).select_from(Citation).where(Citation.ai_run_id == run.id)
    )
    assert persisted_citation_count >= 2


def test_one_sided_topic_returns_ambiguity_not_contradiction(
    client: TestClient, phase8_records: dict[str, object]
) -> None:
    attorney = phase8_records["attorney"]
    one_sided_matter = phase8_records["one_sided_matter"]
    assert isinstance(attorney, User)
    assert isinstance(one_sided_matter, Matter)

    _login(client, attorney.email)
    response = client.post(
        f"/matters/{one_sided_matter.id}/contradictions",
        json={"topic": "notice timing"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["contradictions"] == []
    assert body["ambiguities"]


def test_contradiction_validation_rejects_bad_citation_quotes(
    db: Session, phase8_records: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    attorney = phase8_records["attorney"]
    matter = phase8_records["matter"]
    documents = phase8_records["documents"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)
    assert isinstance(documents, list)
    chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == documents[0].id))
    assert chunk is not None

    class BadCitationContradictionClient(MockModelClient):
        def contradictions(self, request: ContradictionRequest, evidence: list[EvidenceItem]) -> ContradictionResponse:
            bad_citation = CitationPayload(
                document_id=documents[0].id,
                document_name=documents[0].file_name,
                page=1,
                chunk_id=chunk.id,
                quote="This quote does not exist in the source material.",
            )
            return ContradictionResponse(
                topic=request.topic,
                contradictions=[
                    ContradictionItem(
                        claim_a="Bad claim A",
                        claim_b="Bad claim B",
                        why_conflict="Bad citations should be rejected.",
                        severity="medium",
                        citations_a=[bad_citation],
                        citations_b=[bad_citation],
                    )
                ],
                ambiguities=[],
            )

    monkeypatch.setattr("app.services.workflows._get_model_client", lambda: BadCitationContradictionClient())

    response = run_contradiction_finder(
        db,
        matter.id,
        attorney.id,
        ContradictionRequest(topic="notice timing"),
    )

    assert response.contradictions == []
    assert response.ambiguities
    run = db.get(AIRun, response.ai_run_id)
    assert run is not None
    assert run.output_json["validation"]["rejected_contradiction_count"] == 1


def test_contradiction_routes_enforce_matter_access(
    client: TestClient, phase8_records: dict[str, object]
) -> None:
    outsider = phase8_records["outsider"]
    matter = phase8_records["matter"]
    assert isinstance(outsider, User)
    assert isinstance(matter, Matter)

    _login(client, outsider.email)
    response = client.post(f"/matters/{matter.id}/contradictions", json={"topic": "notice timing"})

    assert response.status_code == 403
