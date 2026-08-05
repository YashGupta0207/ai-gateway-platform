import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import DeveloperToken


class TokenRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_hash(self, token_hash: str) -> DeveloperToken | None:
        result = await self.db.execute(
            select(DeveloperToken)
            .options(selectinload(DeveloperToken.providers))
            .where(DeveloperToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, token_id: uuid.UUID) -> DeveloperToken | None:
        result = await self.db.execute(
            select(DeveloperToken)
            .options(selectinload(DeveloperToken.providers))
            .where(DeveloperToken.id == token_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[DeveloperToken]:
        result = await self.db.execute(
            select(DeveloperToken)
            .options(selectinload(DeveloperToken.providers))
            .order_by(DeveloperToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, token: DeveloperToken) -> DeveloperToken:
        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)
        return token

    async def update(self, token: DeveloperToken) -> DeveloperToken:
        await self.db.commit()
        await self.db.refresh(token)
        return token

    async def delete(self, token: DeveloperToken) -> None:
        await self.db.delete(token)
        await self.db.commit()
