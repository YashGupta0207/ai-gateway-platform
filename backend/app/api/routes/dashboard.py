from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.models.models import (
    Admin, ApiRequestLog, DeveloperToken, DeveloperTokenStatus, Provider, ProviderStatus,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class ProviderStatusOut(BaseModel):
    id: str
    display_name: str
    status: str


class RecentRequestOut(BaseModel):
    endpoint: str
    method: str
    status_code: int | None
    latency_ms: int | None
    created_at: datetime


class UsageRankOut(BaseModel):
    name: str
    requests: int
    total_tokens: int


class DashboardOut(BaseModel):
    total_providers: int
    total_tokens: int
    active_tokens: int
    disabled_tokens: int
    recent_requests: list[RecentRequestOut]
    provider_status: list[ProviderStatusOut]
    requests_last_24h: int
    expired_tokens: int
    requests_this_month: int
    tokens_today: int
    tokens_this_month: int
    top_developers: list[UsageRankOut]
    top_providers: list[UsageRankOut]


@router.get("/summary", response_model=DashboardOut)
async def dashboard_summary(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    total_providers = (await db.execute(select(func.count(Provider.id)))).scalar_one()
    total_tokens = (await db.execute(select(func.count(DeveloperToken.id)))).scalar_one()
    active_tokens = (await db.execute(
        select(func.count(DeveloperToken.id)).where(DeveloperToken.status == DeveloperTokenStatus.ACTIVE)
    )).scalar_one()
    disabled_tokens = total_tokens - active_tokens

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    requests_24h = (await db.execute(
        select(func.count(ApiRequestLog.id)).where(ApiRequestLog.created_at >= since)
    )).scalar_one()
    requests_month = (await db.execute(select(func.count(ApiRequestLog.id)).where(ApiRequestLog.created_at >= month_start))).scalar_one()
    tokens_today = (await db.execute(select(func.coalesce(func.sum(ApiRequestLog.total_tokens), 0)).where(ApiRequestLog.created_at >= since))).scalar_one()
    tokens_month = (await db.execute(select(func.coalesce(func.sum(ApiRequestLog.total_tokens), 0)).where(ApiRequestLog.created_at >= month_start))).scalar_one()
    expired = (await db.execute(select(func.count(DeveloperToken.id)).where(DeveloperToken.expires_at.is_not(None), DeveloperToken.expires_at < now))).scalar_one()

    recent_logs = (await db.execute(
        select(ApiRequestLog).order_by(ApiRequestLog.created_at.desc()).limit(20)
    )).scalars().all()

    providers = (await db.execute(select(Provider))).scalars().all()
    developer_rows = (await db.execute(select(DeveloperToken.label, func.sum(DeveloperToken.total_requests), func.sum(DeveloperToken.total_tokens)).group_by(DeveloperToken.label).order_by(func.sum(DeveloperToken.total_tokens).desc()).limit(10))).all()
    provider_rows = (await db.execute(select(Provider.display_name, func.count(ApiRequestLog.id), func.coalesce(func.sum(ApiRequestLog.total_tokens), 0)).outerjoin(ApiRequestLog, ApiRequestLog.provider_id == Provider.id).group_by(Provider.id, Provider.display_name).order_by(func.coalesce(func.sum(ApiRequestLog.total_tokens), 0).desc()).limit(10))).all()

    return DashboardOut(
        total_providers=total_providers,
        total_tokens=total_tokens,
        active_tokens=active_tokens,
        disabled_tokens=disabled_tokens,
        requests_last_24h=requests_24h,
        requests_this_month=requests_month,
        tokens_today=int(tokens_today),
        tokens_this_month=int(tokens_month),
        expired_tokens=expired,
        top_developers=[UsageRankOut(name=row[0], requests=int(row[1] or 0), total_tokens=int(row[2] or 0)) for row in developer_rows],
        top_providers=[UsageRankOut(name=row[0], requests=int(row[1] or 0), total_tokens=int(row[2] or 0)) for row in provider_rows],
        recent_requests=[
            RecentRequestOut(endpoint=r.endpoint, method=r.method, status_code=r.status_code,
                              latency_ms=r.latency_ms, created_at=r.created_at)
            for r in recent_logs
        ],
        provider_status=[
            ProviderStatusOut(id=str(p.id), display_name=p.display_name, status=p.status)
            for p in providers
        ],
    )
