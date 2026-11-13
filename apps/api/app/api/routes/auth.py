from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db, get_optional_current_user
from app.core.security import create_session_token
from app.models.domain import utcnow
from app.schemas.auth import LoginRequest, SessionUser
from app.services.audit import record_audit_event
from app.services.auth import authenticate_user, find_user_by_email

router = APIRouter()


@router.post("/auth/login", response_model=SessionUser)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> SessionUser:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        attempted_user = find_user_by_email(db, payload.email)
        if attempted_user is not None:
            record_audit_event(
                db,
                organization_id=attempted_user.organization_id,
                user_id=attempted_user.id,
                action="login_failed",
                target_type="user",
                target_id=attempted_user.id,
                metadata={"email": payload.email},
            )
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.last_login_at = utcnow()
    response.set_cookie(
        key=settings.session_cookie,
        value=create_session_token(str(user.id)),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="login",
        target_type="user",
        target_id=user.id,
        metadata={"email": user.email},
    )
    db.commit()
    db.refresh(user)
    return SessionUser.model_validate(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_current_user),
) -> Response:
    if current_user is not None:
        record_audit_event(
            db,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="logout",
            target_type="user",
            target_id=current_user.id,
            metadata={"email": current_user.email},
        )
        db.commit()
    response.delete_cookie(settings.session_cookie, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=SessionUser)
def me(current_user=Depends(get_current_user)) -> SessionUser:
    return SessionUser.model_validate(current_user)
