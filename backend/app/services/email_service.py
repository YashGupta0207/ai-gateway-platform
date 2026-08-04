"""
Transactional email hook. Wire this to Brevo's HTTP API (or SES/Postmark) —
kept as a thin async function so it's a one-line swap in auth.py regardless
of provider.
"""
import httpx

from app.core.config import settings


async def send_password_reset_email(to_email: str, reset_token: str) -> None:
    reset_url = f"{settings.cors_origins_list[0]}/reset-password?token={reset_token}"

    # Example Brevo integration — requires BREVO_API_KEY in settings if used.
    # async with httpx.AsyncClient() as client:
    #     await client.post(
    #         "https://api.brevo.com/v3/smtp/email",
    #         headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"},
    #         json={
    #             "sender": {"email": "no-reply@yourdomain.com", "name": settings.APP_NAME},
    #             "to": [{"email": to_email}],
    #             "subject": "Reset your admin password",
    #             "htmlContent": f"<p>Click to reset your password: <a href='{reset_url}'>{reset_url}</a></p>",
    #         },
    #     )

    # Until email is configured, log so the flow is still testable end-to-end.
    import logging
    logging.getLogger("gateway.email").info("Password reset link for %s: %s", to_email, reset_url)
