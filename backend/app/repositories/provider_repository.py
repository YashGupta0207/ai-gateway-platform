import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Provider


class ProviderRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, provider_id: uuid.UUID) -> Provider | None:
        return await self.db.get(Provider, provider_id)

    async def get_by_name(self, name: str) -> Provider | None:
        result = await self.db.execute(select(Provider).where(Provider.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Provider]:
        result = await self.db.execute(select(Provider).order_by(Provider.created_at.desc()))
        return list(result.scalars().all())

    async def create(self, provider: Provider) -> Provider:
        self.db.add(provider)
        await self.db.commit()
        await self.db.refresh(provider)
        return provider

    async def update(self, provider: Provider) -> Provider:
        await self.db.commit()
        await self.db.refresh(provider)
        return provider

    async def delete(self, provider: Provider) -> None:
        await self.db.delete(provider)
        await self.db.commit()
