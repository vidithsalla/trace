from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.domain import Matter, MatterMember
from app.schemas.matter import MatterCreate, MatterDetail, MatterListItem, MatterUpdate
from app.services.audit import record_audit_event
from app.services.matter import WRITE_ROLES, ensure_matter_access, ensure_matter_role

router = APIRouter()


@router.get("/matters", response_model=list[MatterListItem])
def list_matters(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> list[MatterListItem]:
    stmt = (
        select(Matter, MatterMember.role)
        .join(MatterMember, MatterMember.matter_id == Matter.id)
        .where(MatterMember.user_id == current_user.id)
        .where(Matter.organization_id == current_user.organization_id)
        .order_by(Matter.created_at.desc())
    )
    return [
        MatterListItem.model_validate(matter).model_copy(update={"role": role})
        for matter, role in db.execute(stmt).all()
    ]


@router.post("/matters", response_model=MatterDetail, status_code=status.HTTP_201_CREATED)
def create_matter(
    payload: MatterCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Matter:
    matter = Matter(
        organization_id=current_user.organization_id,
        name=payload.name,
        description=payload.description,
        matter_code=payload.matter_code,
        created_by=current_user.id,
    )
    db.add(matter)
    db.flush()
    membership = MatterMember(matter_id=matter.id, user_id=current_user.id, role="admin")
    db.add(membership)
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter.id,
        action="create_matter",
        target_type="matter",
        target_id=matter.id,
        metadata={"name": matter.name},
    )
    db.commit()
    db.refresh(matter)
    return matter


@router.get("/matters/{matter_id}", response_model=MatterDetail)
def get_matter(
    matter_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> Matter:
    return ensure_matter_access(db, matter_id, current_user)


@router.patch("/matters/{matter_id}", response_model=MatterDetail)
def update_matter(
    matter_id: UUID,
    payload: MatterUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Matter:
    matter, _membership = ensure_matter_role(db, matter_id, current_user, WRITE_ROLES)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(matter, key, value)

    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter.id,
        action="update_matter",
        target_type="matter",
        target_id=matter.id,
        metadata=updates,
    )
    db.commit()
    db.refresh(matter)
    return matter
