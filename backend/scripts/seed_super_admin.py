"""
Creates the first super_admin account.
Run once after migrations: python -m scripts.seed_super_admin
Reads SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD / SEED_ADMIN_NAME from env,
never hardcodes credentials.
"""
import asyncio
import os

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.models import Admin, AdminRole


async def main():
    email = os.environ["SEED_ADMIN_EMAIL"]
    password = os.environ["SEED_ADMIN_PASSWORD"]
    full_name = os.environ.get("SEED_ADMIN_NAME", "Super Admin")

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Admin).where(Admin.email == email))).scalar_one_or_none()
        if existing:
            print(f"Admin {email} already exists — skipping.")
            return

        admin = Admin(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=AdminRole.SUPER_ADMIN,
        )
        db.add(admin)
        await db.commit()
        print(f"Created super admin: {email}")


if __name__ == "__main__":
    asyncio.run(main())
