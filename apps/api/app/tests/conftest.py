"""Shared fixtures for V3 tests. Older phase test modules define their own fixtures."""

from __future__ import annotations

import hashlib
from collections.abc import Generator
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.domain import Document, Matter, MatterMember, Organization, User
from app.services.evidence_versions import (
    PageText,
    create_document_version,
    parser_profile,
    publish_extraction,
)
from app.services.parsers import normalize_text
from app.services.storage import storage_service

PASSWORD = "correct-password"


@dataclass
class World:
    org: Organization
    attorney: User
    reviewer: User
    viewer: User
    outsider: User
    matter: Matter
    other_matter: Matter


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
def world(db: Session) -> Generator[World, None, None]:
    suffix = uuid4().hex[:10]
    org = Organization(name=f"V3 Test {suffix}", slug=f"v3-{suffix}")
    db.add(org)
    db.flush()

    def user(role: str) -> User:
        u = User(organization_id=org.id, email=f"{role}-{suffix}@trace.local", name=role.title(),
                 global_role="member", password_hash=hash_password(PASSWORD))
        db.add(u)
        return u

    attorney, reviewer, viewer, outsider = user("attorney"), user("reviewer"), user("viewer"), user("outsider")
    db.flush()
    matter = Matter(organization_id=org.id, name=f"Matter A {suffix}", matter_code=f"A-{suffix}",
                    created_by=attorney.id)
    other = Matter(organization_id=org.id, name=f"Matter B {suffix}", matter_code=f"B-{suffix}",
                   created_by=outsider.id)
    db.add_all([matter, other])
    db.flush()
    db.add_all([
        MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"),
        MatterMember(matter_id=matter.id, user_id=reviewer.id, role="reviewer"),
        MatterMember(matter_id=matter.id, user_id=viewer.id, role="viewer"),
        MatterMember(matter_id=other.id, user_id=outsider.id, role="attorney"),
    ])
    db.commit()
    yield World(org, attorney, reviewer, viewer, outsider, matter, other)

    db.rollback()
    db.execute(delete(Matter).where(Matter.organization_id == org.id))
    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def login(client: TestClient, user: User) -> TestClient:
    response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def ingest_text(db: Session, matter: Matter, user: User, name: str, text: str,
                document: Document | None = None) -> Document:
    """Store bytes and publish a versioned extraction, exactly as the worker would."""
    raw = text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    key = f"tests/{matter.id}/{uuid4().hex}.txt"
    storage_service.upload_fileobj(key, BytesIO(raw), "text/plain")
    if document is None:
        document = Document(matter_id=matter.id, uploaded_by=user.id, file_name=name,
                            display_name=name, mime_type="text/plain", file_size_bytes=len(raw),
                            storage_key=key, sha256=digest, ingest_status="completed",
                            parse_status="completed")
        db.add(document)
        db.flush()
    version = create_document_version(db, document, storage_key=key, source_sha256=digest,
                                      file_name=name, mime_type="text/plain",
                                      file_size_bytes=len(raw), created_by=user.id)
    publish_extraction(db, version, [PageText(1, normalize_text(text))],
                       profile=parser_profile("TextParser"))
    db.commit()
    return document


def current_spans(db: Session, document: Document):
    from app.models.evidence import ExtractionVersion, SourceSpan

    db.refresh(document)
    return db.scalars(
        select(SourceSpan)
        .join(ExtractionVersion, ExtractionVersion.id == SourceSpan.extraction_version_id)
        .where(ExtractionVersion.document_version_id == document.current_version_id)
        .order_by(SourceSpan.span_index)
    ).all()
