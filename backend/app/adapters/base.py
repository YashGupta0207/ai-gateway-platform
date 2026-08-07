"""
Provider Adapter Pattern.

The Gateway core (app/services/gateway_service.py) never contains
provider-specific logic. It only knows:
    1. Look up the token -> provider -> decrypted credentials
    2. Get the adapter for that provider from the registry
    3. Ask the adapter to build an httpx.Request from the incoming request
    4. Send it, stream the response back

Every adapter implements BaseProviderAdapter. Adding a new provider means
writing one new adapter class and registering it — nothing else in the
Gateway changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from starlette.requests import Request


@dataclass
class CredentialField:
    """Declares one field in a provider's dynamic credential form."""
    name: str                      # internal key, e.g. "api_key", "connection_string", "endpoint"
    label: str                     # shown in UI, e.g. "API Key"
    field_type: str = "text"       # "text" | "secret" | "url"
    required: bool = True
    is_mandatory_primary: bool = False  # True for the ONE large field (API key OR connection string)
    placeholder: str = ""


@dataclass
class BuiltRequest:
    method: str
    url: str
    headers: dict = field(default_factory=dict)
    params: dict | None = None
    json_body: dict | None = None
    content: bytes | None = None
    files: dict | None = None
    is_streaming: bool = False


class BaseProviderAdapter(ABC):
    """One subclass per provider. Stateless — credentials are passed in per-call."""

    key: str = ""              # registry key, matches Provider.adapter_key
    display_name: str = ""

    @classmethod
    @abstractmethod
    def credential_schema(cls) -> list[CredentialField]:
        """Declares what this provider needs. Drives the dynamic frontend form."""
        raise NotImplementedError

    @abstractmethod
    async def build_request(
        self,
        *,
        incoming: Request,
        path: str,
        body: bytes,
        credentials: dict[str, str],
    ) -> BuiltRequest:
        """
        Translate an incoming gateway request into a fully-formed request to
        the real provider, using decrypted credentials. Must never leak the
        credentials back to the caller.
        """
        raise NotImplementedError

    def build_websocket_request(self, *, incoming: Request, path: str, credentials: dict[str, str]) -> tuple[str, dict[str, str]]:
        """
        Return (url, headers) for the upstream WebSocket connection.
        """
        raise NotImplementedError("This provider does not support WebSockets")

    async def handle_live_audio_websocket(self, *, websocket, credentials: dict[str, str], format: str, sample_rate: int) -> None:
        """
        Handle a live audio WebSocket connection for this provider.
        """
        raise NotImplementedError(f"{self.display_name} does not support live audio WebSockets.")

    async def build_chat_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        """
        Translate an OpenAI-style /chat/completions request to the provider's format.
        """
        raise NotImplementedError(f"{self.display_name} does not support chat completions translation.")

    def normalize_chat_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        """
        Translate the provider's chat response back to OpenAI-style format.
        Returns (normalized_content_bytes, usage_dict).
        """
        raise NotImplementedError(f"{self.display_name} does not support chat response normalization.")

    async def build_audio_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        """
        Translate an OpenAI-style /audio/transcriptions request to the provider's format.
        """
        raise NotImplementedError(f"{self.display_name} does not support audio transcriptions translation.")

    def normalize_audio_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        """
        Translate the provider's audio response back to OpenAI-style format.
        Returns (normalized_content_bytes, usage_dict).
        """
        raise NotImplementedError(f"{self.display_name} does not support audio response normalization.")

    def is_streaming_path(self, path: str, body: bytes) -> bool:
        """Override to detect streaming requests (e.g. `"stream": true` in body)."""
        return False

    async def send(self, client: httpx.AsyncClient, built: BuiltRequest) -> httpx.Response:
        request = client.build_request(
            method=built.method,
            url=built.url,
            headers=built.headers,
            params=built.params,
            json=built.json_body,
            content=built.content,
            files=built.files,
        )
        return await client.send(request, stream=built.is_streaming)

    @staticmethod
    def credential_value(credentials: dict[str, str], *names: str, required: bool = True) -> str | None:
        """Resolve readable admin-defined key names without involving the Gateway."""
        normalized = {key.casefold().replace("_", "").replace("-", ""): value for key, value in credentials.items()}
        for name in names:
            value = normalized.get(name.casefold().replace("_", "").replace("-", ""))
            if value is not None:
                return value
        if required:
            raise ValueError(f"Missing credential variable (expected one of: {', '.join(names)})")
        return None

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        """
        Normalize usage from the provider's response body.
        Should return a dict with: prompt_tokens, completion_tokens, total_tokens, estimated_cost.
        """
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost": 0.0}
