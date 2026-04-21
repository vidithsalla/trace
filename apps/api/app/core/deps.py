from collections.abc import Generator
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import read_session_token
from app.db.session import SessionLocal
from app.models.domain import User


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db),
    trace_session: str | None = Cookie(default=None, alias=settings.session_cookie),
) -> User:
    if trace_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session")
    user_id = read_session_token(trace_session)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user = db.get(User, UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


def get_optional_current_user(
    db: Session = Depends(get_db),
    trace_session: str | None = Cookie(default=None, alias=settings.session_cookie),
) -> User | None:
    if trace_session is None:
        return None
    user_id = read_session_token(trace_session)
    if user_id is None:
        return None
    user = db.get(User, UUID(user_id))
    if user is None or not user.is_active:
        return None
    return user
