from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.domain import User


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email).order_by(User.created_at.asc()))


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = find_user_by_email(db, email)
    if user is None or user.password_hash is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
