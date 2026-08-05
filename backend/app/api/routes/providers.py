import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import CredentialField
from app.adapters.registry import registry
from app.api.deps import get_current_admin, require_role
from app.core.database import get_db
from app.core.encryption import cipher
from app.models.models import (
    Admin, AdminRole, ApiRequestLog, DeveloperToken, Provider, ProviderProfile, ProviderProfileCredential, ProviderStatus, TokenProviderAuthorization
)
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
    profiles: list["ProfileIn"] | None = None


class ProviderUpdateRequest(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    description: str | None = None
    profiles: list["ProfileIn"] | None = None


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
    profiles: list["ProfileDetailsOut"]
    total_requests: int
    total_tokens_used: int

class ProfileDetailsOut(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    is_default: bool
    priority: int
    credentials: list[CredentialVariableOut]


class ProfileIn(BaseModel):
    name: str
    priority: int = 0
    is_default: bool = False
    credentials: list[CredentialPairIn] = []


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    is_default: bool
    priority: int


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * max(8, len(value) - 4) + value[-4:]


async def _stats_for_provider(db: AsyncSession, provider_id: uuid.UUID) -> dict:
    token_count = (await db.execute(
        select(func.count(TokenProviderAuthorization.token_id)).where(TokenProviderAuthorization.provider_id == provider_id)
    )).scalar_one()
    last_used_at = (await db.execute(
        select(func.max(DeveloperToken.last_used_at))
        .join(TokenProviderAuthorization, TokenProviderAuthorization.token_id == DeveloperToken.id)
        .where(TokenProviderAuthorization.provider_id == provider_id)
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
        credential_count = 0
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

    if payload.profiles:
        for p in payload.profiles:
            profile = ProviderProfile(provider_id=provider.id, name=p.name.strip(), priority=p.priority, is_default=p.is_default)
            db.add(profile)
            await db.flush()
            for pair in p.credentials:
                db.add(ProviderProfileCredential(profile_id=profile.id, variable_name=pair.variable_name, encrypted_value=cipher.encrypt(pair.value)))
        await db.commit()

    return await _to_out(db, provider, credential_count=0)


@router.get("/{provider_id}", response_model=ProviderDetailsOut)
async def get_provider(provider_id: uuid.UUID, admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    provider = await ProviderRepository(db).get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    profiles = (await db.execute(select(ProviderProfile).where(ProviderProfile.provider_id == provider_id).order_by(ProviderProfile.is_default.desc(), ProviderProfile.priority.desc()))).scalars().all()
    
    profile_details = []
    total_credentials = 0
    for profile in profiles:
        cred_rows = (await db.execute(select(ProviderProfileCredential).where(ProviderProfileCredential.profile_id == profile.id))).scalars().all()
        total_credentials += len(cred_rows)
        decrypted = {row.variable_name: cipher.decrypt(row.encrypted_value) for row in cred_rows}
        profile_details.append(ProfileDetailsOut(
            id=profile.id, name=profile.name, is_active=profile.is_active, is_default=profile.is_default, priority=profile.priority,
            credentials=[CredentialVariableOut(variable_name=name, masked_value=_mask(value)) for name, value in decrypted.items()]
        ))

    stats = await _stats_for_provider(db, provider_id)

    base = await _to_out(db, provider, credential_count=total_credentials)
    return ProviderDetailsOut(
        **base.model_dump(),
        profiles=profile_details,
        total_requests=stats["total_requests"], total_tokens_used=stats["total_tokens_used"],
    )


@router.get("/{provider_id}/profiles", response_model=list[ProfileOut])
async def list_profiles(provider_id: uuid.UUID, admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ProviderProfile).where(ProviderProfile.provider_id == provider_id).order_by(ProviderProfile.is_default.desc(), ProviderProfile.priority.desc()))).scalars().all()
    return [ProfileOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/{provider_id}/profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(provider_id: uuid.UUID, payload: ProfileIn, admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    provider = await ProviderRepository(db).get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    profile = ProviderProfile(provider_id=provider_id, name=payload.name.strip(), priority=payload.priority, is_default=payload.is_default)
    if not profile.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profile name cannot be empty")
    if payload.is_default:
        for row in (await db.execute(select(ProviderProfile).where(ProviderProfile.provider_id == provider_id))).scalars(): row.is_default = False
    db.add(profile)
    await db.flush()
    seen: set[str] = set()
    for pair in payload.credentials:
        key = pair.variable_name.casefold()
        if key in seen: raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Duplicate key '{pair.variable_name}'")
        seen.add(key)
        db.add(ProviderProfileCredential(profile_id=profile.id, variable_name=pair.variable_name, encrypted_value=cipher.encrypt(pair.value)))
    await db.commit()
    await db.refresh(profile)
    return ProfileOut.model_validate(profile, from_attributes=True)


class RevealOut(BaseModel):
    variable_name: str
    value: str


@router.get("/{provider_id}/profiles/{profile_id}/credentials/{variable_name}/reveal", response_model=RevealOut)
async def reveal_credential(
    provider_id: uuid.UUID, profile_id: uuid.UUID, variable_name: str,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Only super_admin/admin can reveal a plaintext credential value — never bundled into list/detail responses by default."""
    row = (await db.execute(select(ProviderProfileCredential).where(ProviderProfileCredential.profile_id == profile_id, ProviderProfileCredential.variable_name == variable_name))).scalar_one_or_none()
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

    if payload.profiles is not None:
        # Delete existing profiles
        await db.execute(sa.delete(ProviderProfile).where(ProviderProfile.provider_id == provider.id))
        
        for p in payload.profiles:
            profile = ProviderProfile(provider_id=provider.id, name=p.name.strip(), priority=p.priority, is_default=p.is_default)
            db.add(profile)
            await db.flush()
            for pair in p.credentials:
                db.add(ProviderProfileCredential(profile_id=profile.id, variable_name=pair.variable_name, encrypted_value=cipher.encrypt(pair.value)))
        await db.commit()

    return await _to_out(db, provider, credential_count=0)


@router.post("/{provider_id}/profiles/{profile_id}/rotate-credentials", response_model=ProfileOut)
async def rotate_credentials(
    provider_id: uuid.UUID,
    profile_id: uuid.UUID,
    payload: list[CredentialPairIn],
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Partial update — only rotates the variables provided, leaves the rest untouched."""
    profile = (await db.execute(select(ProviderProfile).where(ProviderProfile.id == profile_id, ProviderProfile.provider_id == provider_id))).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")

    for pair in payload:
        row = (await db.execute(select(ProviderProfileCredential).where(ProviderProfileCredential.profile_id == profile.id, ProviderProfileCredential.variable_name == pair.variable_name))).scalar_one_or_none()
        if row:
            row.encrypted_value = cipher.encrypt(pair.value)
        else:
            db.add(ProviderProfileCredential(profile_id=profile.id, variable_name=pair.variable_name, encrypted_value=cipher.encrypt(pair.value)))
    
    await db.commit()
    return ProfileOut.model_validate(profile, from_attributes=True)


@router.delete("/{provider_id}/profiles/{profile_id}/credentials/{variable_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential_variable(
    provider_id: uuid.UUID, profile_id: uuid.UUID, variable_name: str,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(ProviderProfileCredential).where(ProviderProfileCredential.profile_id == profile_id, ProviderProfileCredential.variable_name == variable_name))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential variable not found")
    await db.delete(row)
    await db.commit()
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
        select(func.count(TokenProviderAuthorization.token_id)).where(TokenProviderAuthorization.provider_id == provider_id)
    )).scalar_one()
    if token_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete this provider because {token_count} developer token(s) are assigned to it. Delete those tokens first.",
        )
    await repo.delete(provider)
    return None
