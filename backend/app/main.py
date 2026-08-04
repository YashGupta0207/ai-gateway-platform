import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, dashboard, gateway, providers, tokens
from app.core.config import settings
from app.middleware.error_handling import RequestLoggingMiddleware, register_exception_handlers

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)

@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    email = os.environ.get("SEED_ADMIN_EMAIL")
    password = os.environ.get("SEED_ADMIN_PASSWORD")
    if email and password:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.models import Admin, AdminRole
        from app.core.security import hash_password
        
        async with AsyncSessionLocal() as db:
            existing = (await db.execute(select(Admin).where(Admin.email == email))).scalar_one_or_none()
            if not existing:
                admin = Admin(
                    email=email,
                    hashed_password=hash_password(password),
                    full_name=os.environ.get("SEED_ADMIN_NAME", "Super Admin"),
                    role=AdminRole.SUPER_ADMIN,
                )
                db.add(admin)
                await db.commit()
                logging.info(f"Created super admin from environment variables: {email}")
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="Admin Portal + API Gateway that proxies developer requests to AI providers "
                "without ever exposing real provider credentials.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(providers.router, prefix=settings.API_V1_PREFIX)
app.include_router(tokens.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
# Gateway routes are NOT versioned under /api/v1 — this is the stable
# developer-facing surface the SDK talks to.
app.include_router(gateway.router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": settings.APP_NAME}
