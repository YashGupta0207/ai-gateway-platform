import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenType, decode_token, hash_developer_token
from app.models.models import Admin, DeveloperToken, DeveloperTokenStatus, Provider, ProviderProfile, ProviderStatus, TokenProviderAuthorization
from sqlalchemy import select
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
    return token


async def resolve_authorized_provider(db: AsyncSession, token: DeveloperToken, requested_name: str | None, requested_profile_name: str | None = None) -> tuple[Provider, ProviderProfile]:
    """Resolve the SDK-selected provider before credentials are loaded or decrypted."""
    if not requested_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing X-Gateway-Provider header")
        
    result = await db.execute(select(Provider).where((Provider.name == requested_name) | (Provider.display_name == requested_name)))
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Provider '{requested_name}' does not exist")
        
    if provider.status != ProviderStatus.ENABLED:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Requested provider is currently disabled")
        
    authorized = (await db.execute(select(TokenProviderAuthorization.id).where(TokenProviderAuthorization.developer_token_id == token.id, TokenProviderAuthorization.provider_id == provider.id))).scalar_one_or_none()
    if authorized is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Developer is not authorized to access provider '{provider.display_name}'.")
        
    if requested_profile_name:
        profile = (await db.execute(
            select(ProviderProfile)
            .where(
                ProviderProfile.provider_id == provider.id, 
                ProviderProfile.is_active.is_(True),
                ProviderProfile.name == requested_profile_name
            )
        )).scalars().first()
        if profile is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Requested profile '{requested_profile_name}' does not exist or is inactive for this provider")
    else:
        profile = (await db.execute(
            select(ProviderProfile)
            .where(ProviderProfile.provider_id == provider.id, ProviderProfile.is_active.is_(True))
            .order_by(ProviderProfile.is_default.desc(), ProviderProfile.priority.desc())
        )).scalars().first()
        
    if profile is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Requested provider has no active profile")
    return provider, profile
