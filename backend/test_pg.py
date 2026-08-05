
import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.models.models import DeveloperToken, TokenProviderAuthorization
import uuid

async def main():
    engine = create_async_engine("postgresql+asyncpg://ai_gateway_db_463u_user:rLF0iCK2EgXCu32W57gUOJnzM7gncKJT@dpg-d9onjhid0e5s73c04bdg-a.oregon-postgres.render.com/ai_gateway_db_463u")
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(func.max(DeveloperToken.last_used_at))
            .join(TokenProviderAuthorization, TokenProviderAuthorization.token_id == DeveloperToken.id)
            .where(TokenProviderAuthorization.provider_id == uuid.uuid4())
        )
        try:
            val = result.scalar_one()
            print("scalar_one() returned:", val)
        except Exception as e:
            print("scalar_one() raised:", type(e).__name__)

asyncio.run(main())
