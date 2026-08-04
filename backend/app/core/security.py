"""
Password hashing, JWT issuing/verification, and developer-token generation.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    PASSWORD_RESET = "password_reset"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(admin_id: str, role: str) -> str:
    return _create_token(
        admin_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra={"role": role},
    )


def create_refresh_token(admin_id: str) -> str:
    return _create_token(admin_id, TokenType.REFRESH, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def create_password_reset_token(admin_id: str) -> str:
    return _create_token(
        admin_id,
        TokenType.PASSWORD_RESET,
        timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )


def decode_token(token: str, expected_type: TokenType) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if payload.get("type") != expected_type.value:
        raise ValueError(f"Expected a {expected_type.value} token")
    return payload


def generate_developer_token() -> str:
    """dev_ + 43 URL-safe random chars — 256 bits of entropy. Only ever shown once."""
    return f"{settings.DEV_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_developer_token(raw_token: str) -> str:
    """
    Developer tokens are stored hashed (SHA-256), never in plaintext, so a DB
    leak doesn't leak usable tokens. Lookup hashes the incoming token and
    queries by hash — deterministic, unlike bcrypt, which we need since we
    look up by token on every gateway request rather than compare-per-row.
    """
    import hashlib
    return hashlib.sha256(raw_token.encode()).hexdigest()
