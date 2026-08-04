import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenType, decode_token, hash_developer_token
from app.models.models import Admin, DeveloperToken, DeveloperTokenStatus, ProviderStatus
from app.repositories.token_repository import TokenRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_token(creds.credentials, TokenType.ACCESS)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    admin = await db.get(Admin, uuid.UUID(payload["sub"]))
    if admin is None or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin not found or inactive")
    return admin


def require_role(*allowed_roles: str):
    async def _checker(admin: Admin = Depends(get_current_admin)) -> Admin:
        if admin.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return admin
    return _checker


async def get_valid_developer_token(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> DeveloperToken:
    """
    Validates the raw `dev_xxx` token presented by an SDK/developer against
    the gateway. This is the ONLY thing a developer ever authenticates with —
    they never see real provider credentials or endpoints.
    """
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing developer token")

    token_hash = hash_developer_token(creds.credentials)
    repo = TokenRepository(db)
    token = await repo.get_by_hash(token_hash)

    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid developer token")
    if token.status != DeveloperTokenStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Developer token is disabled")
    if token.expires_at is not None:
        from datetime import datetime, timezone
        if datetime.now(timezone.utc) > token.expires_at:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Developer token has expired")
    if token.provider is None or token.provider.status != ProviderStatus.ENABLED:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Assigned provider is currently disabled")

    return token
