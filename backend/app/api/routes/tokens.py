import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, require_role
from app.core.database import get_db
from app.core.security import generate_developer_token, hash_developer_token
from app.core.encryption import cipher
from app.models.models import Admin, AdminRole, ApiRequestLog, DeveloperToken, DeveloperTokenStatus, TokenProviderAuthorization
from app.repositories.provider_repository import ProviderRepository
from app.repositories.token_repository import TokenRepository

router = APIRouter(prefix="/tokens", tags=["Developer Tokens"])


class TokenCreateRequest(BaseModel):
    label: str
    notes: str | None = None
    expires_at: datetime | None = None
    daily_request_limit: int | None = None
    monthly_request_limit: int | None = None
    daily_token_limit: int | None = None
    monthly_token_limit: int | None = None
    provider_ids: list[uuid.UUID]


class TokenCreatedOut(BaseModel):
    id: uuid.UUID
    label: str
    raw_token: str   # shown ONCE, at creation time only
    provider_ids: list[uuid.UUID]
    status: str
    expires_at: datetime | None
    created_at: datetime


class TokenOut(BaseModel):
    id: uuid.UUID
    label: str
    token_prefix: str
    temporary_api_key: str | None = None
    provider_ids: list[uuid.UUID]
    provider_names: list[str]
    status: str
    notes: str | None
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    created_by: str | None = None
    last_client_ip: str | None = None
    last_user_agent: str | None = None
    daily_request_limit: int | None = None
    monthly_request_limit: int | None = None
    daily_token_limit: int | None = None
    monthly_token_limit: int | None = None
    total_requests: int
    successful_requests: int
    failed_requests: int
    first_used_at: datetime | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    average_latency_ms: float
    estimated_cost: float


def _to_out(token: DeveloperToken, reveal: bool = False) -> TokenOut:
    return TokenOut(
        id=token.id, label=token.label, token_prefix=token.token_prefix,
        temporary_api_key=cipher.decrypt(token.encrypted_token) if reveal and token.encrypted_token else None,
        provider_ids=[p.id for p in token.providers], provider_names=[p.display_name for p in token.providers],
        status=token.status, notes=token.notes, expires_at=token.expires_at,
        last_used_at=token.last_used_at, created_at=token.created_at,
        created_by=None, last_client_ip=token.last_client_ip, last_user_agent=token.last_user_agent,
        daily_request_limit=token.daily_request_limit, monthly_request_limit=token.monthly_request_limit,
        daily_token_limit=token.daily_token_limit, monthly_token_limit=token.monthly_token_limit,
        total_requests=token.total_requests, prompt_tokens=token.prompt_tokens,
        successful_requests=token.successful_requests, failed_requests=token.failed_requests,
        first_used_at=token.first_used_at,
        completion_tokens=token.completion_tokens, total_tokens=token.total_tokens,
        average_latency_ms=(token.total_latency_ms / token.total_requests) if token.total_requests else 0,
        estimated_cost=token.estimated_cost,
    )


@router.post("", response_model=TokenCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_token(
    payload: TokenCreateRequest,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    if not payload.provider_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one provider must be specified")
    
    providers = []
    for pid in payload.provider_ids:
        provider = await ProviderRepository(db).get_by_id(pid)
        if provider is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Provider {pid} not found")
        providers.append(provider)

    raw_token = generate_developer_token()
    token = DeveloperToken(
        label=payload.label,
        token_hash=hash_developer_token(raw_token),
        token_prefix=raw_token[:12],
        encrypted_token=cipher.encrypt(raw_token),

        notes=payload.notes,
        expires_at=payload.expires_at,
        created_by_admin_id=admin.id,
        daily_request_limit=payload.daily_request_limit,
        monthly_request_limit=payload.monthly_request_limit,
        daily_token_limit=payload.daily_token_limit,
        monthly_token_limit=payload.monthly_token_limit,
    )
    token = await TokenRepository(db).create(token)
    for authorized_provider_id in set(payload.provider_ids):
        db.add(TokenProviderAuthorization(developer_token_id=token.id, provider_id=authorized_provider_id))
    await db.commit()

    return TokenCreatedOut(
        id=token.id, label=token.label, raw_token=raw_token,
        provider_ids=payload.provider_ids, status=token.status, expires_at=token.expires_at, created_at=token.created_at,
    )


@router.get("", response_model=list[TokenOut])
async def list_tokens(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    tokens = await TokenRepository(db).list_all()
    return [_to_out(t) for t in tokens]


@router.get("/{token_id}", response_model=TokenOut)
async def get_token(token_id: uuid.UUID, reveal: bool = Query(False), admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    token = await TokenRepository(db).get_by_id(token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    return _to_out(token, reveal=reveal)


class ProviderAuthorizationIn(BaseModel):
    provider_ids: list[uuid.UUID]


@router.put("/{token_id}/providers", status_code=status.HTTP_204_NO_CONTENT)
async def set_token_provider_authorizations(token_id: uuid.UUID, payload: ProviderAuthorizationIn, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    token = await TokenRepository(db).get_by_id(token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    await db.execute(TokenProviderAuthorization.__table__.delete().where(TokenProviderAuthorization.developer_token_id == token_id))
    for provider_id in set(payload.provider_ids):
        db.add(TokenProviderAuthorization(developer_token_id=token_id, provider_id=provider_id))
    await db.commit()


class RequestLogOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    endpoint: str
    method: str
    status_code: int | None
    latency_ms: int | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    ip_address: str | None
    user_agent: str | None
    is_streaming: bool


class PeriodUsageOut(BaseModel):
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TokenUsageOut(BaseModel):
    today: PeriodUsageOut
    month: PeriodUsageOut


@router.get("/{token_id}/requests", response_model=list[RequestLogOut])
async def token_requests(token_id: uuid.UUID, limit: int = Query(50, ge=1, le=200), admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ApiRequestLog).where(ApiRequestLog.developer_token_id == token_id).order_by(ApiRequestLog.created_at.desc()).limit(limit))).scalars().all()
    return [RequestLogOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{token_id}/usage", response_model=TokenUsageOut)
async def token_usage(token_id: uuid.UUID, admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    starts = (now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    async def aggregate(since: datetime) -> PeriodUsageOut:
        row = (await db.execute(select(func.count(ApiRequestLog.id), func.coalesce(func.sum(ApiRequestLog.prompt_tokens), 0), func.coalesce(func.sum(ApiRequestLog.completion_tokens), 0), func.coalesce(func.sum(ApiRequestLog.total_tokens), 0)).where(ApiRequestLog.developer_token_id == token_id, ApiRequestLog.created_at >= since))).one()
        return PeriodUsageOut(requests=int(row[0]), prompt_tokens=int(row[1]), completion_tokens=int(row[2]), total_tokens=int(row[3]))
    return TokenUsageOut(today=await aggregate(starts[0]), month=await aggregate(starts[1]))


class TokenLimitsUpdate(BaseModel):
    """
    PATCH semantics: an omitted field is left alone, an explicit null clears the
    limit (back to unlimited). That distinction is what lets a caller drop one
    quota without having to restate the other three.
    """
    daily_request_limit: int | None = Field(default=None, ge=1)
    monthly_request_limit: int | None = Field(default=None, ge=1)
    daily_token_limit: int | None = Field(default=None, ge=1)
    monthly_token_limit: int | None = Field(default=None, ge=1)


@router.patch("/{token_id}/limits", response_model=TokenOut)
async def update_token_limits(
    token_id: uuid.UUID,
    payload: TokenLimitsUpdate,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """
    Adjust a token's quotas after creation — until now they were fixed at
    creation time and there was no way to change them.

    Enforcement itself is untouched: the Gateway still compares these against
    the token's ApiRequestLog totals, so a new limit takes effect on the very
    next request and nothing about the developer-facing SDK contract changes.
    A limit set below current usage starts returning 429 immediately.
    """
    repo = TokenRepository(db)
    token = await repo.get_by_id(token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Supply at least one of: daily_request_limit, monthly_request_limit, "
            "daily_token_limit, monthly_token_limit. Send null to clear a limit.",
        )
    for field_name, value in changes.items():
        setattr(token, field_name, value)
    return _to_out(await repo.update(token))


@router.post("/{token_id}/disable", response_model=TokenOut)
async def disable_token(token_id: uuid.UUID, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    repo = TokenRepository(db)
    token = await repo.get_by_id(token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    token.status = DeveloperTokenStatus.DISABLED
    return _to_out(await repo.update(token))


@router.post("/{token_id}/enable", response_model=TokenOut)
async def enable_token(token_id: uuid.UUID, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    repo = TokenRepository(db)
    token = await repo.get_by_id(token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    token.status = DeveloperTokenStatus.ACTIVE
    return _to_out(await repo.update(token))


@router.post("/{token_id}/regenerate", response_model=TokenCreatedOut)
async def regenerate_token(token_id: uuid.UUID, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    repo = TokenRepository(db)
    token = await repo.get_by_id(token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")

    raw_token = generate_developer_token()
    token.token_hash = hash_developer_token(raw_token)
    token.token_prefix = raw_token[:12]
    token.encrypted_token = cipher.encrypt(raw_token)
    token = await repo.update(token)

    return TokenCreatedOut(
        id=token.id, label=token.label, raw_token=raw_token,
        provider_ids=[p.id for p in token.providers], status=token.status, expires_at=token.expires_at, created_at=token.created_at,
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(token_id: uuid.UUID, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN)), db: AsyncSession = Depends(get_db)):
    repo = TokenRepository(db)
    token = await repo.get_by_id(token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    await repo.delete(token)
    return None
