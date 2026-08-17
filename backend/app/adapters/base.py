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
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from starlette.requests import Request

_BOUNDARY_RE = re.compile(r'boundary="?([^";,]+)"?', re.IGNORECASE)


class ProviderConfigurationError(ValueError):
    """
    Raised when an adapter cannot build an upstream request from the incoming
    request plus the stored credentials — a missing deployment name, say.

    Distinct from a bare ValueError (which the Gateway reports as a 500,
    "provider misconfigured") because the caller can usually fix this one
    themselves by naming a model or deployment on the request, so it surfaces
    as a 4xx with the accepted keys spelled out.
    """
    status_code = 400


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

    async def handle_live_audio_websocket(self, *, websocket, credentials: dict[str, str], format: str, sample_rate: int) -> dict[str, int | float]:
        """
        Handle a live audio WebSocket connection for this provider.
        Returns a usage dictionary.
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

        Defaults to forwarding the multipart body untouched to the provider's
        own `audio/transcriptions` route, which is what any OpenAI-compatible
        REST provider expects. Adapters whose provider speaks a different
        shape (Gemini, Azure Speech) override this.
        """
        return await self.build_request(
            incoming=incoming, path="audio/transcriptions", body=body, credentials=credentials
        )

    def normalize_audio_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        """
        Translate the provider's audio response back to OpenAI-style format.
        Returns (normalized_content_bytes, usage_dict).

        Returning `content` itself (not a copy) marks this as a passthrough, so
        the Gateway knows it can keep the provider's own Content-Type — that is
        what lets `response_format="text"` survive the round trip.
        """
        return content, self.normalize_usage(content)

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

    @staticmethod
    def multipart_field(body: bytes, content_type: str | None, name: str) -> str | None:
        """
        Pull one small text field out of a multipart body.

        Deliberately not `await request.form()`: that parses and buffers every
        part, including the audio file, when all we want is a short string like
        `model`. This scans for the one field and copies only its value.
        Returns None if the body isn't multipart or the field isn't there.
        """
        if not body or not content_type or "multipart/form-data" not in content_type.lower():
            return None
        boundary_match = _BOUNDARY_RE.search(content_type)
        if not boundary_match:
            return None
        boundary = boundary_match.group(1).strip().encode()

        # Content-Disposition ... name="<name>" [; more] CRLF [more headers] CRLF CRLF <value> CRLF --boundary
        pattern = (
            rb'name="' + re.escape(name.encode()) + rb'"'
            rb'(?:;[^\r\n]*)?\r\n'
            rb'(?:[^\r\n]+\r\n)*'
            rb'\r\n'
            rb'(.*?)'
            rb'\r\n--' + re.escape(boundary)
        )
        found = re.search(pattern, body, re.DOTALL)
        if not found:
            return None
        try:
            return found.group(1).decode("utf-8").strip() or None
        except UnicodeDecodeError:
            return None

    @staticmethod
    def usage_from_payload(payload: object, *, prompt_key: str = "prompt_tokens",
                           completion_key: str = "completion_tokens",
                           total_key: str = "total_tokens") -> dict[str, int | float] | None:
        """
        Read token counts out of an already-decoded provider response.
        Returns None when the payload carries no usage block — a plain-text
        transcription, for instance — so callers can fall back to zeros
        without treating it as an error.
        """
        if not isinstance(payload, dict):
            return None
        usage = payload.get("usage") or payload.get("usageMetadata") or {}
        if not isinstance(usage, dict):
            return None
        prompt = usage.get(prompt_key) or 0
        completion = usage.get(completion_key) or 0
        total = usage.get(total_key)
        if total is None:
            total = prompt + completion
        try:
            return {"prompt_tokens": int(prompt), "completion_tokens": int(completion),
                    "total_tokens": int(total), "estimated_cost": 0.0}
        except (TypeError, ValueError):
            return None

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        """
        Normalize usage from the provider's response body.
        Should return a dict with: prompt_tokens, completion_tokens, total_tokens, estimated_cost.
        """
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost": 0.0}
