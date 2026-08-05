from starlette.requests import Request

from app.adapters.base import BaseProviderAdapter, BuiltRequest, CredentialField

DEFAULT_BASE_URL = "https://api.deepgram.com/v1"


class DeepgramAdapter(BaseProviderAdapter):
    key = "deepgram"
    display_name = "Deepgram"

    @classmethod
    def credential_schema(cls) -> list[CredentialField]:
        return [
            CredentialField(
                name="api_key", label="API Key", field_type="secret",
                required=True, is_mandatory_primary=True,
                placeholder="Deepgram API key",
            ),
        ]

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        # Audio upload / multipart pass-through: content-type (audio/*, multipart/form-data)
        # is forwarded as-is, and the raw body bytes are streamed through unchanged.
        content_type = incoming.headers.get("content-type", "application/octet-stream")
        headers = {
            "Authorization": f"Token {self.credential_value(credentials, 'api_key', 'deepgram_key', 'deepgram_api_key')}",
            "Content-Type": content_type,
        }
        return BuiltRequest(
            method=incoming.method,
            url=f"{DEFAULT_BASE_URL}/{path.lstrip('/')}",
            headers=headers,
            params=dict(incoming.query_params),
            content=body,
            is_streaming=False,
        )

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        import json
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return super().normalize_usage(content)
        duration = payload.get("metadata", {}).get("duration", 0)
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": int(duration), "estimated_cost": 0.0}
