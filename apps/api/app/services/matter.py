from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Matter, MatterMember, User

WRITE_ROLES = {"admin", "attorney"}


def get_matter_membership(db: Session, matter_id: UUID, user_id: UUID) -> MatterMember | None:
    return db.scalar(
        select(MatterMember).where(MatterMember.matter_id == matter_id, MatterMember.user_id == user_id)
    )


def ensure_matter_access(db: Session, matter_id: UUID, user: User) -> Matter:
    matter = db.get(Matter, matter_id)
    if matter is None or matter.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    membership = get_matter_membership(db, matter_id, user.id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Matter access denied")
    return matter


def ensure_matter_role(
    db: Session, matter_id: UUID, user: User, allowed_roles: set[str] | frozenset[str]
) -> tuple[Matter, MatterMember]:
    matter = ensure_matter_access(db, matter_id, user)
    membership = get_matter_membership(db, matter_id, user.id)
    if membership is None or membership.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return matter, membership
