import os
import subprocess

with open(".env", "r") as f:
    lines = f.readlines()

db_url = None
for line in lines:
    if line.startswith("External_Database_URL="):
        db_url = line.split("=", 1)[1].strip()
        break

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    script = f"""
import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.models.models import DeveloperToken, TokenProviderAuthorization
import uuid

async def main():
    engine = create_async_engine("{db_url}")
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
"""
    with open("test_pg.py", "w") as f:
        f.write(script)
        
    cmd = f'docker-compose run --rm -v "%cd%:/app" -e PYTHONPATH=/app api python test_pg.py'
    subprocess.run(cmd, shell=True)
