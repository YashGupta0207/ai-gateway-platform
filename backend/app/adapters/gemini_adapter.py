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

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        import json
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return super().normalize_usage(content)
        usage = payload.get("usageMetadata") or {}
        prompt = usage.get("promptTokenCount", 0)
        completion = usage.get("candidatesTokenCount", 0)
        total = usage.get("totalTokenCount", prompt + completion)
        return {"prompt_tokens": int(prompt), "completion_tokens": int(completion), "total_tokens": int(total), "estimated_cost": 0.0}
