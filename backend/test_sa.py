import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Integer

Base = declarative_base()

class TestModel(Base):
    __tablename__ = "test"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    val: Mapped[int] = mapped_column(Integer)

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(engine) as session:
        # Query max val where id = 999 (no rows)
        result = await session.execute(select(func.max(TestModel.val)).where(TestModel.id == 999))
        try:
            val = result.scalar_one()
            print("scalar_one() returned:", val)
        except Exception as e:
            print("scalar_one() raised:", type(e).__name__)

asyncio.run(main())
