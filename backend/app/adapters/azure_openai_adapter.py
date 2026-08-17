import json

from starlette.requests import Request

from app.adapters.base import (
    BaseProviderAdapter,
    BuiltRequest,
    CredentialField,
    ProviderConfigurationError,
)

DEFAULT_API_VERSION = "2024-06-01"

# Every credential variable name an admin might have used for the deployment.
# `credential_value` casefolds and strips _/- before matching, so
# AZURE_TRANSCRIBE_DEPLOYMENT lines up with azure_transcribe_deployment here.
DEPLOYMENT_KEYS = (
    "deployment_name", "deployment", "azure_deployment", "azure_openai_deployment",
    "azure_transcribe_deployment", "azure_diarize_deployment",
)
API_VERSION_KEYS = ("api_version", "azure_api_version", "azure_openai_api_version")

# Chat reports prompt_tokens/completion_tokens; audio/transcriptions reports
# input_tokens/output_tokens. Chat spellings first, so chat metering is decided
# before the audio aliases are ever consulted.
PROMPT_TOKEN_KEYS = ("prompt_tokens", "input_tokens")
COMPLETION_TOKEN_KEYS = ("completion_tokens", "output_tokens")

DEPLOYMENT_HEADER = "X-Gateway-Deployment"
API_VERSION_HEADER = "X-Gateway-Api-Version"


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
            CredentialField(
                name="api_version", label="API Version (optional)", field_type="text",
                required=False, placeholder=DEFAULT_API_VERSION,
            ),
        ]

    def is_streaming_path(self, path: str, body: bytes) -> bool:
        try:
            return bool(json.loads(body or b"{}").get("stream"))
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError, TypeError):
            return False

    def _resolve_deployment(self, incoming: Request, body: bytes, credentials: dict[str, str]) -> str:
        """
        One Azure provider can host several deployments — gpt-4o-transcribe for
        transcription and gpt-4o-transcribe-diarize for diarization, say — so
        the deployment has to be selectable per request, not just per profile.

        Precedence: explicit header, then the `model` field the OpenAI SDK
        already puts in the multipart body, then whatever the profile stores.

        `model` is read only from multipart bodies. JSON callers (chat
        completions) send a model name that is not necessarily a deployment
        name, and honouring it there would silently re-route existing traffic.
        """
        header_value = incoming.headers.get(DEPLOYMENT_HEADER)
        if header_value and header_value.strip():
            return header_value.strip()

        model_field = self.multipart_field(body, incoming.headers.get("content-type"), "model")
        if model_field:
            return model_field

        credential_value = self.credential_value(credentials, *DEPLOYMENT_KEYS, required=False)
        if credential_value and credential_value.strip():
            return credential_value.strip()

        raise ProviderConfigurationError(
            "No Azure OpenAI deployment resolved for this request. Send a "
            f"'{DEPLOYMENT_HEADER}' header or a 'model' field in the multipart body, "
            "or set one of these credential variables on the provider profile: "
            + ", ".join(DEPLOYMENT_KEYS)
        )

    def _resolve_api_version(self, incoming: Request, credentials: dict[str, str]) -> str:
        """
        Newer models are only served on newer API versions — gpt-4o-transcribe
        needs 2025-04-01-preview and is absent from the old default — so this is
        configurable, defaulting to the historical value so existing providers
        keep behaving exactly as before.
        """
        header_value = incoming.headers.get(API_VERSION_HEADER)
        if header_value and header_value.strip():
            return header_value.strip()
        credential_value = self.credential_value(credentials, *API_VERSION_KEYS, required=False)
        if credential_value and credential_value.strip():
            return credential_value.strip()
        return DEFAULT_API_VERSION

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        endpoint = self.credential_value(credentials, "endpoint", "azure_endpoint", "azure_openai_endpoint").rstrip("/")
        api_key = self.credential_value(credentials, "api_key", "azure_openai", "azure_api_key", "azure_openai_key")
        deployment = self._resolve_deployment(incoming, body, credentials)
        url = f"{endpoint}/openai/deployments/{deployment}/{path.lstrip('/')}"

        headers = {
            "api-key": api_key,
            "Content-Type": incoming.headers.get("content-type", "application/json"),
        }

        return BuiltRequest(
            method=incoming.method,
            url=url,
            headers=headers,
            params={"api-version": self._resolve_api_version(incoming, credentials)},
            content=body,
            is_streaming=self.is_streaming_path(path, body),
        )

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        """
        Azure returns JSON for chat and for `response_format=json`, but plain
        text for `response_format=text`. Absent usage is normal here, not an
        error: the request still gets counted, only the token totals stay 0.

        Chat and transcription spell usage differently on the same provider, so
        both spellings are accepted with the chat keys first. A chat response
        always carries prompt_tokens/completion_tokens and so never reaches the
        audio aliases; a transcription carries only input_tokens/output_tokens,
        which used to leave prompt and completion recorded as 0.
        """
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return super().normalize_usage(content)
        usage = self.usage_from_payload(
            payload,
            prompt_keys=PROMPT_TOKEN_KEYS,
            completion_keys=COMPLETION_TOKEN_KEYS,
        )
        if usage is None:
            return super().normalize_usage(content)
        return usage | self._token_breakdown(payload)

    @staticmethod
    def _token_breakdown(payload: dict) -> dict[str, int]:
        """
        Split the input tokens into audio vs text where Azure reports it.

        Transcription bills audio and text input at different rates, so the two
        are worth keeping apart. Only emitted when the provider actually sends
        `input_token_details`, which keeps chat usage dicts byte-identical to
        what they were before.

        Note: ApiRequestLog has no column for these yet, so they are available
        to callers of normalize_usage but are not persisted — adding them to the
        log needs a migration.
        """
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return {}
        details = usage.get("input_token_details")
        if not isinstance(details, dict):
            return {}
        breakdown = {}
        for source_key, out_key in (("audio_tokens", "audio_tokens"), ("text_tokens", "text_tokens")):
            value = details.get(source_key)
            if value is not None:
                try:
                    breakdown[out_key] = int(value)
                except (TypeError, ValueError):
                    continue
        return breakdown

    async def build_chat_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        return await self.build_request(incoming=incoming, path="chat/completions", body=body, credentials=credentials)

    def normalize_chat_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        return content, self.normalize_usage(content)
