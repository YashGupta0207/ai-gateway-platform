from fastapi import APIRouter, Depends, WebSocket, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.deps import get_valid_developer_token, get_valid_developer_token_ws, resolve_authorized_provider
from app.core.database import get_db
from app.models.models import DeveloperToken
from app.services.gateway_service import proxy_request, proxy_websocket

router = APIRouter(prefix="/gateway", tags=["Gateway (Developer-facing)"])
ws_router = APIRouter(tags=["Gateway WebSockets"])


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


@ws_router.websocket("/api/v1/gateway/ws/listen")
async def gateway_websocket_proxy(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    await websocket.accept()
    token = await get_valid_developer_token_ws(websocket, db)
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or missing token")
        return

    tags_header = websocket.headers.get("X-Gateway-Tags")
    tags = None
    if tags_header:
        import json
        try:
            tags = json.loads(tags_header)
        except json.JSONDecodeError:
            pass

    requested_name = websocket.headers.get("X-Gateway-Provider") or websocket.query_params.get("provider")
    requested_profile_name = websocket.headers.get("X-Gateway-Profile") or websocket.query_params.get("profile")

    try:
        provider, profile = await resolve_authorized_provider(
            db, 
            token, 
            requested_name,
            requested_profile_name,
            tags
        )
    except Exception as e:
        # resolve_authorized_provider raises HTTPException which we can't let propagate in WS
        error_msg = str(e.detail) if hasattr(e, 'detail') else str(e)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=error_msg)
        return

    await proxy_websocket(
        db=db, token=token, provider=provider, profile_id=profile.id, websocket=websocket, path="listen"
    )
