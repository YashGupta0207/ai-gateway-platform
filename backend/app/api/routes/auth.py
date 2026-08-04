from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.core.security import (
    TokenType, create_access_token, create_password_reset_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from app.models.models import Admin

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(select(Admin).where(Admin.email == payload.email))
    admin = result.scalar_one_or_none()

    if admin is None or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not admin.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    return TokenPair(
        access_token=create_access_token(str(admin.id), admin.role),
        refresh_token=create_refresh_token(str(admin.id)),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token, TokenType.REFRESH)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    import uuid
    admin = await db.get(Admin, uuid.UUID(data["sub"]))
    if admin is None or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin not found or inactive")

    return TokenPair(
        access_token=create_access_token(str(admin.id), admin.role),
        refresh_token=create_refresh_token(str(admin.id)),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(admin: Admin = Depends(get_current_admin)):
    # Stateless JWTs: logout is enforced client-side by discarding tokens.
    # For server-side revocation, add the jti to a Redis denylist here.
    return None


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(select(Admin).where(Admin.email == payload.email))
    admin = result.scalar_one_or_none()

    # Always return 202 regardless of whether the email exists, to avoid
    # leaking which emails are registered admins.
    if admin is not None:
        reset_token = create_password_reset_token(str(admin.id))
        # In production: send this via the transactional email service (e.g. Brevo/SES)
        # instead of returning it. Wired here as a hook point.
        from app.services.email_service import send_password_reset_email
        await send_password_reset_email(admin.email, reset_token)

    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = decode_token(payload.reset_token, TokenType.PASSWORD_RESET)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    import uuid
    admin = await db.get(Admin, uuid.UUID(data["sub"]))
    if admin is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reset token")

    admin.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password has been reset successfully."}
