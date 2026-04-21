from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.domain import AuditLog, Matter, MatterMember, Organization, User


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
def phase1_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 1 Test {suffix}", slug=f"phase-1-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"attorney-{suffix}@trace.local",
        name="Phase One Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    reviewer = User(
        organization_id=org.id,
        email=f"reviewer-{suffix}@trace.local",
        name="Phase One Reviewer",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    outsider = User(
        organization_id=org.id,
        email=f"outsider-{suffix}@trace.local",
        name="Phase One Outsider",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add_all([attorney, reviewer, outsider])
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 1 Matter {suffix}",
        description="Matter for auth and RBAC tests.",
        matter_code=f"P1-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add(matter)
    db.flush()
    db.add_all(
        [
            MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"),
            MatterMember(matter_id=matter.id, user_id=reviewer.id, role="reviewer"),
        ]
    )
    db.commit()

    yield {
        "org": org,
        "attorney": attorney,
        "reviewer": reviewer,
        "outsider": outsider,
        "matter": matter,
        "suffix": suffix,
    }

    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def _login(client: TestClient, email: str, password: str = "correct-password") -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_login_me_logout_and_audit(
    client: TestClient, db: Session, phase1_records: dict[str, object]
) -> None:
    attorney = phase1_records["attorney"]
    assert isinstance(attorney, User)

    response = client.post(
        "/auth/login",
        json={"email": attorney.email, "password": "correct-password"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == attorney.email
    assert response.cookies.get("trace_session")

    me = client.get("/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(attorney.id)

    db.refresh(attorney)
    assert attorney.last_login_at is not None

    logout = client.post("/auth/logout")
    assert logout.status_code == 204
    assert client.get("/me").status_code == 401

    actions = list(
        db.scalars(
            select(AuditLog.action)
            .where(AuditLog.user_id == attorney.id)
            .where(AuditLog.action.in_(["login", "logout"]))
        )
    )
    assert "login" in actions
    assert "logout" in actions


def test_login_failure_is_audited_for_known_user(
    client: TestClient, db: Session, phase1_records: dict[str, object]
) -> None:
    attorney = phase1_records["attorney"]
    assert isinstance(attorney, User)

    response = client.post(
        "/auth/login",
        json={"email": attorney.email, "password": "wrong-password"},
    )

    assert response.status_code == 401
    failed = db.scalar(
        select(AuditLog).where(AuditLog.user_id == attorney.id, AuditLog.action == "login_failed")
    )
    assert failed is not None


def test_create_matter_adds_creator_membership_and_audit(
    client: TestClient, db: Session, phase1_records: dict[str, object]
) -> None:
    attorney = phase1_records["attorney"]
    assert isinstance(attorney, User)
    _login(client, attorney.email)

    response = client.post(
        "/matters",
        json={
            "name": "New Phase 1 Matter",
            "description": "Created from test.",
            "matter_code": "NEW-P1",
        },
    )

    assert response.status_code == 201
    matter_id = response.json()["id"]
    membership = db.scalar(
        select(MatterMember).where(
            MatterMember.matter_id == matter_id,
            MatterMember.user_id == attorney.id,
            MatterMember.role == "admin",
        )
    )
    assert membership is not None
    audit = db.scalar(
        select(AuditLog).where(AuditLog.target_id == matter_id, AuditLog.action == "create_matter")
    )
    assert audit is not None


def test_matter_access_is_membership_scoped(client: TestClient, phase1_records: dict[str, object]) -> None:
    matter = phase1_records["matter"]
    attorney = phase1_records["attorney"]
    outsider = phase1_records["outsider"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    assert isinstance(outsider, User)

    _login(client, attorney.email)
    allowed = client.get(f"/matters/{matter.id}")
    assert allowed.status_code == 200
    assert allowed.json()["id"] == str(matter.id)
    client.post("/auth/logout")

    _login(client, outsider.email)
    denied = client.get(f"/matters/{matter.id}")
    assert denied.status_code == 403


def test_reviewer_cannot_update_matter_but_attorney_can(
    client: TestClient, phase1_records: dict[str, object]
) -> None:
    matter = phase1_records["matter"]
    attorney = phase1_records["attorney"]
    reviewer = phase1_records["reviewer"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    assert isinstance(reviewer, User)

    _login(client, reviewer.email)
    denied = client.patch(f"/matters/{matter.id}", json={"status": "archived"})
    assert denied.status_code == 403
    client.post("/auth/logout")

    _login(client, attorney.email)
    allowed = client.patch(f"/matters/{matter.id}", json={"status": "processing"})
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "processing"
