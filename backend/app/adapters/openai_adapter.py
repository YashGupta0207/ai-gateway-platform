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
        try:
            return bool(json.loads(body or b"{}").get("stream"))
        except (json.JSONDecodeError, AttributeError):
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
