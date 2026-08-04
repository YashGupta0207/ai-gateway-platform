import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import CredentialField
from app.adapters.registry import registry
from app.api.deps import get_current_admin, require_role
from app.core.database import get_db
from app.core.encryption import cipher
from app.models.models import (
    Admin, AdminRole, ApiRequestLog, DeveloperToken, Provider, ProviderCredential, ProviderStatus,
)
from app.repositories.provider_credential_repository import DuplicateVariableError, ProviderCredentialRepository
from app.repositories.provider_repository import ProviderRepository

router = APIRouter(prefix="/providers", tags=["Providers"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CredentialPairIn(BaseModel):
    variable_name: str
    value: str

    @field_validator("variable_name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Variable name cannot be empty.")
        return v.strip()

    @field_validator("value")
    @classmethod
    def _value_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Credential value cannot be empty.")
        return v


class AvailableAdapterOut(BaseModel):
    """
    Suggested adapter types + the variable names they typically expect.
    Purely a UI convenience (prefill hints) — the admin can still add,
    rename, or remove any variable freely. Nothing here is enforced.
    """
    adapter_key: str
    display_name: str
    suggested_variables: list[dict]


class ProviderCreateRequest(BaseModel):
    name: str                       # "Provider Name"
    provider_type: str              # free text, e.g. "Azure", "Gemini", "Custom REST API"
    description: str | None = None
    credentials: list[CredentialPairIn]


class ProviderUpdateRequest(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    description: str | None = None
    credentials: list[CredentialPairIn] | None = None   # full replace when provided


class CredentialVariableOut(BaseModel):
    variable_name: str
    masked_value: str


class ProviderOut(BaseModel):
    id: uuid.UUID
    name: str
    provider_type: str
    description: str | None
    status: str
    credential_count: int
    token_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProviderDetailsOut(ProviderOut):
    credentials: list[CredentialVariableOut]
    total_requests: int
    total_tokens_used: int


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * max(8, len(value) - 4) + value[-4:]


async def _stats_for_provider(db: AsyncSession, provider_id: uuid.UUID) -> dict:
    token_count = (await db.execute(
        select(func.count(DeveloperToken.id)).where(DeveloperToken.provider_id == provider_id)
    )).scalar_one()
    last_used_at = (await db.execute(
        select(func.max(DeveloperToken.last_used_at)).where(DeveloperToken.provider_id == provider_id)
    )).scalar_one()
    total_requests = (await db.execute(
        select(func.count(ApiRequestLog.id)).where(ApiRequestLog.provider_id == provider_id)
    )).scalar_one()
    total_tokens_used = (await db.execute(
        select(func.coalesce(func.sum(ApiRequestLog.total_tokens), 0)).where(ApiRequestLog.provider_id == provider_id)
    )).scalar_one()
    return {
        "token_count": token_count, "last_used_at": last_used_at,
        "total_requests": total_requests, "total_tokens_used": int(total_tokens_used),
    }


async def _to_out(db: AsyncSession, provider: Provider, credential_count: int | None = None) -> ProviderOut:
    stats = await _stats_for_provider(db, provider.id)
    if credential_count is None:
        credential_count = len(await ProviderCredentialRepository(db).list_by_provider(provider.id))
    return ProviderOut(
        id=provider.id, name=provider.display_name, provider_type=provider.adapter_key,
        description=provider.description, status=provider.status,
        credential_count=credential_count, token_count=stats["token_count"],
        last_used_at=stats["last_used_at"], created_at=provider.created_at, updated_at=provider.updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/available-adapters", response_model=list[AvailableAdapterOut])
async def list_available_adapters(admin: Admin = Depends(get_current_admin)):
    """
    Drives the 'Provider Type' suggestions in the UI. These are hints only —
    e.g. picking "Azure" can prefill api_key/endpoint/deployment rows — but
    the admin can still type any provider_type and any variable names.
    Providers whose type doesn't match one of these fall back to the
    generic REST adapter at gateway time, so nothing here gates what an
    admin is allowed to create.
    """
    out = []
    for adapter in registry.all().values():
        fields: list[CredentialField] = adapter.credential_schema()
        out.append(AvailableAdapterOut(
            adapter_key=adapter.key,
            display_name=adapter.display_name,
            suggested_variables=[f.__dict__ for f in fields],
        ))
    return out


@router.get("", response_model=list[ProviderOut])
async def list_providers(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    providers = await ProviderRepository(db).list_all()
    return [await _to_out(db, p) for p in providers]


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreateRequest,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    provider = Provider(
        name=payload.name.strip().lower().replace(" ", "-") or str(uuid.uuid4()),
        display_name=payload.name.strip(),
        adapter_key=payload.provider_type.strip(),
        description=payload.description,
    )
    provider = await ProviderRepository(db).create(provider)

    if payload.credentials:
        try:
            await ProviderCredentialRepository(db).replace_all(
                provider.id, [(c.variable_name, c.value) for c in payload.credentials],
            )
        except DuplicateVariableError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return await _to_out(db, provider)


@router.get("/{provider_id}", response_model=ProviderDetailsOut)
async def get_provider(provider_id: uuid.UUID, admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    provider = await ProviderRepository(db).get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    cred_rows = await ProviderCredentialRepository(db).list_by_provider(provider_id)
    decrypted = {row.variable_name: cipher.decrypt(row.encrypted_value) for row in cred_rows}
    stats = await _stats_for_provider(db, provider_id)

    base = await _to_out(db, provider, credential_count=len(cred_rows))
    return ProviderDetailsOut(
        **base.model_dump(),
        credentials=[CredentialVariableOut(variable_name=name, masked_value=_mask(value)) for name, value in decrypted.items()],
        total_requests=stats["total_requests"], total_tokens_used=stats["total_tokens_used"],
    )


class RevealOut(BaseModel):
    variable_name: str
    value: str


@router.get("/{provider_id}/credentials/{variable_name}/reveal", response_model=RevealOut)
async def reveal_credential(
    provider_id: uuid.UUID, variable_name: str,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Only super_admin/admin can reveal a plaintext credential value — never bundled into list/detail responses by default."""
    rows = await ProviderCredentialRepository(db).list_by_provider(provider_id)
    row = next((r for r in rows if r.variable_name == variable_name), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential variable not found")
    return RevealOut(variable_name=row.variable_name, value=cipher.decrypt(row.encrypted_value))


@router.put("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderUpdateRequest,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    repo = ProviderRepository(db)
    provider = await repo.get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    if payload.name is not None:
        provider.display_name = payload.name.strip()
    if payload.provider_type is not None:
        provider.adapter_key = payload.provider_type.strip()
    if payload.description is not None:
        provider.description = payload.description

    provider = await repo.update(provider)

    if payload.credentials is not None:
        try:
            await ProviderCredentialRepository(db).replace_all(
                provider.id, [(c.variable_name, c.value) for c in payload.credentials],
            )
        except DuplicateVariableError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return await _to_out(db, provider)


@router.post("/{provider_id}/rotate-credentials", response_model=ProviderOut)
async def rotate_credentials(
    provider_id: uuid.UUID,
    payload: list[CredentialPairIn],
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Partial update — only rotates the variables provided, leaves the rest untouched."""
    provider = await ProviderRepository(db).get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    try:
        await ProviderCredentialRepository(db).upsert_many(
            provider_id, [(c.variable_name, c.value) for c in payload],
        )
    except DuplicateVariableError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return await _to_out(db, provider)


@router.delete("/{provider_id}/credentials/{variable_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential_variable(
    provider_id: uuid.UUID, variable_name: str,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    provider = await ProviderRepository(db).get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    await ProviderCredentialRepository(db).delete_variable(provider_id, variable_name)
    return None


@router.post("/{provider_id}/enable", response_model=ProviderOut)
async def enable_provider(provider_id: uuid.UUID, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    repo = ProviderRepository(db)
    provider = await repo.get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    provider.status = ProviderStatus.ENABLED
    provider = await repo.update(provider)
    return await _to_out(db, provider)


@router.post("/{provider_id}/disable", response_model=ProviderOut)
async def disable_provider(provider_id: uuid.UUID, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    repo = ProviderRepository(db)
    provider = await repo.get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    provider.status = ProviderStatus.DISABLED
    provider = await repo.update(provider)
    return await _to_out(db, provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: uuid.UUID, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN)), db: AsyncSession = Depends(get_db)):
    repo = ProviderRepository(db)
    provider = await repo.get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    token_count = (await db.execute(
        select(func.count(DeveloperToken.id)).where(DeveloperToken.provider_id == provider_id)
    )).scalar_one()
    if token_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete this provider because {token_count} developer token(s) are assigned to it. Delete those tokens first.",
        )
    await repo.delete(provider)
    return None
