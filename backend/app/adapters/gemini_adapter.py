from starlette.requests import Request

from app.adapters.base import BaseProviderAdapter, BuiltRequest, CredentialField

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiAdapter(BaseProviderAdapter):
    key = "gemini"
    display_name = "Google Gemini"

    @classmethod
    def credential_schema(cls) -> list[CredentialField]:
        return [
            CredentialField(
                name="api_key", label="API Key", field_type="secret",
                required=True, is_mandatory_primary=True,
                placeholder="AIza...",
            ),
            CredentialField(
                name="model_name", label="Model Name (optional default)", field_type="text",
                required=False, placeholder="gemini-1.5-pro",
            ),
        ]

    def is_streaming_path(self, path: str, body: bytes) -> bool:
        return "streamGenerateContent" in path

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        url = f"{DEFAULT_BASE_URL}/{path.lstrip('/')}"
        headers = {"Content-Type": incoming.headers.get("content-type", "application/json")}

        return BuiltRequest(
            method=incoming.method,
            url=url,
            headers=headers,
            params={"key": self.credential_value(credentials, "api_key", "gemini_key", "gemini_api_key")},
            content=body,
            is_streaming=self.is_streaming_path(path, body),
        )
