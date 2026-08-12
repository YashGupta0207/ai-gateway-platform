import json

from starlette.requests import Request

from app.adapters.base import BaseProviderAdapter, BuiltRequest, CredentialField

API_VERSION = "2024-06-01"


class AzureOpenAIAdapter(BaseProviderAdapter):
    key = "azure_openai"
    display_name = "Azure OpenAI"

    @classmethod
    def credential_schema(cls) -> list[CredentialField]:
        return [
            CredentialField(
                name="api_key", label="API Key", field_type="secret",
                required=True, is_mandatory_primary=True,
                placeholder="Azure OpenAI resource key",
            ),
            CredentialField(
                name="endpoint", label="Endpoint", field_type="url",
                required=True, placeholder="https://<resource>.openai.azure.com",
            ),
            CredentialField(
                name="deployment_name", label="Deployment Name", field_type="text",
                required=True, placeholder="gpt-4o-deployment",
            ),
        ]

    def is_streaming_path(self, path: str, body: bytes) -> bool:
        try:
            return bool(json.loads(body or b"{}").get("stream"))
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            return False

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        endpoint = self.credential_value(credentials, "endpoint", "azure_endpoint", "azure_openai_endpoint").rstrip("/")
        deployment = self.credential_value(credentials, "deployment_name", "deployment", "azure_deployment", "azure_openai_deployment")
        api_key = self.credential_value(credentials, "api_key", "azure_openai", "azure_api_key", "azure_openai_key")
        url = f"{endpoint}/openai/deployments/{deployment}/{path.lstrip('/')}"

        headers = {
            "api-key": api_key,
            "Content-Type": incoming.headers.get("content-type", "application/json"),
        }

        return BuiltRequest(
            method=incoming.method,
            url=url,
            headers=headers,
            params={"api-version": API_VERSION},
            content=body,
            is_streaming=self.is_streaming_path(path, body),
        )

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return super().normalize_usage(content)
        usage = payload.get("usage") or {}
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        total = usage.get("total_tokens", prompt + completion)
        return {"prompt_tokens": int(prompt), "completion_tokens": int(completion), "total_tokens": int(total), "estimated_cost": 0.0}

    async def build_chat_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        return await self.build_request(incoming=incoming, path="chat/completions", body=body, credentials=credentials)

    def normalize_chat_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        return content, self.normalize_usage(content)

    async def build_audio_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        return await self.build_request(incoming=incoming, path="audio/transcriptions", body=body, credentials=credentials)

    def normalize_audio_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        return content, self.normalize_usage(content)
