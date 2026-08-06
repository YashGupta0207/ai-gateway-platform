"""
Database models.

Key design decision (per the dynamic-credential requirement):
Providers do NOT have fixed credential columns like `api_key`, `endpoint`,
`secret`, and no longer even have a JSONB blob of them. Instead, each
credential is its own row in `provider_credentials`:
    Provider (1) -> (many) ProviderCredential { variable_name, encrypted_value }
An admin can attach any number of arbitrarily-named variables to any
provider — 1, 5, or 100 — with zero schema changes. Only `encrypted_value`
is encrypted; `variable_name` stays in plaintext so it's readable in the UI
and can be matched against what a Provider Adapter expects at gateway time.
`Provider.adapter_key` (exposed to the API/UI as "provider_type") still
identifies which BaseProviderAdapter interprets those variables; if it
doesn't match a registered adapter, the Gateway falls back to a generic
passthrough adapter (see app/adapters/generic_adapter.py), so truly novel
REST-style providers work without writing a line of backend code.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid_col():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class AdminRole:
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    VIEWER = "viewer"


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[uuid.UUID] = _uuid_col()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=AdminRole.ADMIN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="admin")


class ProviderStatus:
    ENABLED = "enabled"
    DISABLED = "disabled"


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = _uuid_col()
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)  # internal slug, e.g. "openai-prod"
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)  # "Provider Name" shown in the UI
    # "Provider Type" in the UI. Free text — NOT restricted to a fixed enum.
    # Matched against app/adapters/registry.py at gateway time; unmatched
    # values transparently fall back to the generic REST adapter.
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ProviderStatus.ENABLED)

    base_url_override: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tokens: Mapped[list["DeveloperToken"]] = relationship(secondary="token_provider_authorizations", back_populates="providers")





class ProviderProfile(Base):
    __tablename__ = "provider_profiles"

    id: Mapped[uuid.UUID] = _uuid_col()
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    credentials: Mapped[list["ProviderProfileCredential"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class ProviderProfileCredential(Base):
    __tablename__ = "provider_profile_credentials"
    __table_args__ = (UniqueConstraint("profile_id", "variable_name", name="uq_profile_credential_variable"),)

    id: Mapped[uuid.UUID] = _uuid_col()
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    variable_name: Mapped[str] = mapped_column(String(150), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    profile: Mapped["ProviderProfile"] = relationship(back_populates="credentials")


class DeveloperTokenStatus:
    ACTIVE = "active"
    DISABLED = "disabled"


class DeveloperToken(Base):
    __tablename__ = "developer_tokens"

    id: Mapped[uuid.UUID] = _uuid_col()
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)  # first chars shown in UI, e.g. dev_ab12
    # Retained encrypted solely for privileged admin management. The hash remains
    # the value used for developer authentication.
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DeveloperTokenStatus.ACTIVE)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_user_agent: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    daily_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[float] = mapped_column(nullable=False, default=0)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admins.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    providers: Mapped[list["Provider"]] = relationship(secondary="token_provider_authorizations", back_populates="tokens")
    provider_authorizations: Mapped[list["TokenProviderAuthorization"]] = relationship(cascade="all, delete-orphan")


class TokenProviderAuthorization(Base):
    __tablename__ = "token_provider_authorizations"
    __table_args__ = (UniqueConstraint("developer_token_id", "provider_id", name="uq_token_provider_authorization"),)

    id: Mapped[uuid.UUID] = _uuid_col()
    developer_token_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("developer_tokens.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"

    id: Mapped[uuid.UUID] = _uuid_col()
    developer_token_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developer_tokens.id", ondelete="SET NULL"), nullable=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[float] = mapped_column(nullable=False, default=0)
    user_agent: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_col()
    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(150), nullable=False)  # e.g. "provider.create", "token.disable"
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    admin: Mapped["Admin"] = relationship(back_populates="audit_logs")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(150), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
