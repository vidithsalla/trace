from argon2 import PasswordHasher
from itsdangerous import BadSignature, URLSafeSerializer

from app.core.config import settings

password_hasher = PasswordHasher()
serializer = URLSafeSerializer(settings.secret_key, salt="trace-session")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except Exception:
        return False


def create_session_token(user_id: str) -> str:
    return serializer.dumps({"user_id": user_id})


def read_session_token(token: str) -> str | None:
    try:
        data = serializer.loads(token)
    except BadSignature:
        return None
    return data.get("user_id")
