import json

from starlette.requests import Request

from app.adapters.base import BaseProviderAdapter, BuiltRequest, CredentialField

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIAdapter(BaseProviderAdapter):
    key = "openai"
    display_name = "OpenAI"

    @classmethod
    def credential_schema(cls) -> list[CredentialField]:
        return [
            CredentialField(
                name="api_key", label="API Key", field_type="secret",
                required=True, is_mandatory_primary=True,
                placeholder="sk-...",
            ),
            CredentialField(
                name="organization_id", label="Organization ID (optional)",
                field_type="text", required=False,
            ),
        ]

    def is_streaming_path(self, path: str, body: bytes) -> bool:
        # UnicodeDecodeError matters here: an audio upload is a binary multipart
        # body, and json.loads chokes on it before it ever reaches JSONDecodeError.
        try:
            return bool(json.loads(body or b"{}").get("stream"))
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError, TypeError):
            return False

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        api_key = self.credential_value(credentials, "api_key", "openai_key", "openai_api_key")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": incoming.headers.get("content-type", "application/json"),
        }
        organization_id = self.credential_value(credentials, "organization_id", "openai_organization_id", required=False)
        if organization_id:
            headers["OpenAI-Organization"] = organization_id

        return BuiltRequest(
            method=incoming.method,
            url=f"{DEFAULT_BASE_URL}/{path.lstrip('/')}",
            headers=headers,
            content=body,
            is_streaming=self.is_streaming_path(path, body),
        )

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        # `response_format="text"` yields a bare transcript, not JSON — and a
        # transcript that happens to parse as JSON ("null", "42") is not a dict.
        # Neither is an error; usage just stays 0.
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return super().normalize_usage(content)
        return self.usage_from_payload(payload) or super().normalize_usage(content)

    async def build_chat_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        return await self.build_request(incoming=incoming, path="chat/completions", body=body, credentials=credentials)

    def normalize_chat_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        return content, self.normalize_usage(content)
