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
    Citation,
    Document,
    DocumentChunk,
    DocumentPage,
    ExportJob,
    Matter,
    MatterMember,
    Memo,
    Organization,
    User,
)
from app.services.memos import REQUIRED_MEMO_SECTIONS


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
def phase9_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 9 Test {suffix}", slug=f"phase-9-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"phase9-{suffix}@trace.local",
        name="Phase Nine Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"phase9-outsider-{suffix}@trace.local",
        name="Phase Nine Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 9 Matter {suffix}",
        matter_code=f"P9-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add(matter)
    db.flush()
    db.add(MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"))

    texts = [
        "2024-03-18 A formal notice letter states Acme provided written notice to Northshore Supply.",
        "2024-03-22 Northshore Supply disputed the notice timing and called the notice late and incomplete.",
        "2024-03-19 Priya Shah approved payment authority for Project Falcon.",
        "2024-03-20 Priya Shah said final authorization remained conditional pending notice review.",
        "2024-03-28 Acme Industrial withheld payment approval and requested Project Falcon inspection records.",
    ]
    documents = [
        _add_document_with_chunk(db, matter=matter, user=attorney, name=f"memo-{index}.txt", text=text)
        for index, text in enumerate(texts, start=1)
    ]
    db.commit()

    yield {
        "org": org,
        "attorney": attorney,
        "outsider": outsider,
        "matter": matter,
        "documents": documents,
    }

    db.rollback()
    matter_ids = list(db.scalars(select(Matter.id).where(Matter.organization_id == org.id)))
    if matter_ids:
        db.execute(delete(ExportJob).where(ExportJob.matter_id.in_(matter_ids)))
        db.execute(delete(Memo).where(Memo.matter_id.in_(matter_ids)))
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
        sha256=f"phase9-{uuid4()}",
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
    "issue",
    [
        "Whether Acme gave timely notice of the delivery problem",
        "Whether payment approval authority was final or conditional",
    ],
)
def test_issue_memo_generation_persists_required_sections_and_citations(
    client: TestClient, db: Session, phase9_records: dict[str, object], issue: str
) -> None:
    attorney = phase9_records["attorney"]
    matter = phase9_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    response = client.post(f"/matters/{matter.id}/memos", json={"issue": issue, "limit": 12})

    assert response.status_code == 201
    body = response.json()
    content = body["content_json"]
    assert set(REQUIRED_MEMO_SECTIONS) <= set(content)
    assert content["supporting_facts"]
    assert content["contrary_facts"]
    assert content["gaps"]
    assert content["next_documents_to_review"]
    assert body["content_markdown"].startswith(f"# {issue}")
    assert "## Supporting Facts" in body["content_markdown"]

    for fact in [*content["supporting_facts"], *content["contrary_facts"]]:
        assert fact["statement"]
        assert fact["citations"]
        assert all(citation["validation_status"] == "validated" for citation in fact["citations"])
        assert all(citation["viewer_url"].startswith(f"/matters/{matter.id}/documents/") for citation in fact["citations"])

    run = db.get(AIRun, body["source_run_id"])
    assert run is not None
    assert run.status == "completed"
    assert run.prompt_template_version == "issue_memo_v1"
    assert run.output_json["validation"]["workflow"] == "citation_check_v1"
    assert run.output_json["validation"]["supporting_fact_count"] >= 1
    assert run.output_json["validation"]["contrary_fact_count"] >= 1

    citation_count = db.scalar(select(func.count()).select_from(Citation).where(Citation.ai_run_id == run.id))
    assert citation_count >= 2


def test_memo_edit_and_exports_succeed(
    client: TestClient, db: Session, phase9_records: dict[str, object]
) -> None:
    attorney = phase9_records["attorney"]
    matter = phase9_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    create_response = client.post(
        f"/matters/{matter.id}/memos",
        json={"issue": "Whether payment approval authority was final or conditional", "limit": 12},
    )
    assert create_response.status_code == 201
    memo = create_response.json()
    content = memo["content_json"]
    content["answer_in_brief"] = "Edited answer in brief for Phase 9."

    patch_response = client.patch(
        f"/memos/{memo['id']}",
        json={"title": "Edited payment authority memo", "content_json": content},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["title"] == "Edited payment authority memo"
    assert patched["content_json"]["answer_in_brief"] == "Edited answer in brief for Phase 9."
    assert "Edited answer in brief for Phase 9." in patched["content_markdown"]

    markdown_response = client.get(f"/memos/{memo['id']}/export.md")
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "Edited answer in brief for Phase 9." in markdown_response.text

    docx_response = client.get(f"/memos/{memo['id']}/export.docx")
    assert docx_response.status_code == 200
    assert docx_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert docx_response.content.startswith(b"PK")

    audit_actions = set(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.matter_id == matter.id,
                AuditLog.action.in_(["update_memo", "export_memo_markdown", "export_memo_docx"]),
            )
        )
    )
    assert {"update_memo", "export_memo_markdown", "export_memo_docx"} <= audit_actions


def test_memo_routes_enforce_matter_access(
    client: TestClient, phase9_records: dict[str, object]
) -> None:
    attorney = phase9_records["attorney"]
    outsider = phase9_records["outsider"]
    matter = phase9_records["matter"]
    assert isinstance(attorney, User)
    assert isinstance(outsider, User)
    assert isinstance(matter, Matter)

    _login(client, attorney.email)
    create_response = client.post(
        f"/matters/{matter.id}/memos",
        json={"issue": "Whether Acme gave timely notice of the delivery problem", "limit": 12},
    )
    assert create_response.status_code == 201
    memo_id = create_response.json()["id"]

    _login(client, outsider.email)
    assert client.post(f"/matters/{matter.id}/memos", json={"issue": "notice"}).status_code == 403
    assert client.get(f"/memos/{memo_id}").status_code == 403
    assert client.patch(f"/memos/{memo_id}", json={"title": "Nope"}).status_code == 403
    assert client.get(f"/memos/{memo_id}/export.md").status_code == 403
