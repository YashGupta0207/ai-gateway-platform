from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.deps import get_valid_developer_token, resolve_authorized_provider
from app.core.database import get_db
from app.models.models import DeveloperToken
from app.services.gateway_service import proxy_request

router = APIRouter(prefix="/gateway", tags=["Gateway (Developer-facing)"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def gateway_proxy(
    path: str,
    request: Request,
    token: DeveloperToken = Depends(get_valid_developer_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Single catch-all entrypoint every developer/SDK request goes through.
    Handles JSON, streaming, multipart, and raw audio uploads transparently —
    the adapter decides how to interpret the body, not this route.
    """
    tags_header = request.headers.get("X-Gateway-Tags")
    tags = None
    if tags_header:
        import json
        try:
            tags = json.loads(tags_header)
        except json.JSONDecodeError:
            pass
            
    provider, profile = await resolve_authorized_provider(
        db, 
        token, 
        request.headers.get("X-Gateway-Provider"),
        request.headers.get("X-Gateway-Profile"),
        tags
    )
    return await proxy_request(db=db, token=token, provider=provider, profile_id=profile.id, incoming=request, path=path)
