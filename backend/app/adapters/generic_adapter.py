"""
Generic REST passthrough adapter.

Used whenever Provider.adapter_key doesn't match one of the specialized,
hand-written adapters (OpenAI, Azure OpenAI, Gemini, Deepgram). This is what
lets an admin onboard a brand-new REST-style provider — Pinecone,
OpenRouter, ElevenLabs, Azure Speech, a bespoke internal API, anything that
speaks HTTP with a base URL and a bearer/API-key style credential — purely
through the admin UI, with zero backend code changes.

Convention over configuration: it looks for a small set of well-known
variable names among whatever the admin typed into the dynamic
variable/value rows. Everything else is passed straight through.

Recognized variables (all optional except base_url):
    base_url         REQUIRED. e.g. "https://api.pinecone.io"
    api_key           sent as a bearer token unless auth_header_name is set
    auth_header_name   e.g. "Api-Key" — overrides the default Authorization header
    auth_scheme        e.g. "Bearer " (default) or "" for a raw key with a custom header

Providers that aren't HTTP/REST at all (a raw Postgres/Redis/Cosmos
connection, for example) cannot be proxied generically — those still need
a purpose-built adapter, same as any of the four above, following this same
pattern.
"""
from starlette.requests import Request

from app.adapters.base import BaseProviderAdapter, BuiltRequest, CredentialField


class GenericAdapter(BaseProviderAdapter):
    key = "generic"
    display_name = "Custom / Generic REST API"

    @classmethod
    def credential_schema(cls) -> list[CredentialField]:
        return [
            CredentialField(
                name="base_url", label="Base URL", field_type="url",
                required=True, is_mandatory_primary=True,
                placeholder="https://api.example.com",
            ),
            CredentialField(name="api_key", label="API Key (optional)", field_type="secret", required=False),
            CredentialField(name="auth_header_name", label="Auth header name (optional)", field_type="text", required=False,
                             placeholder="Authorization"),
            CredentialField(name="auth_scheme", label="Auth scheme prefix (optional)", field_type="text", required=False,
                             placeholder="Bearer "),
        ]

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        base_url = credentials.get("base_url")
        if not base_url:
            raise ValueError(
                "This provider has no 'base_url' credential variable set — the generic "
                "adapter needs one to know where to forward requests."
            )

        headers = {"Content-Type": incoming.headers.get("content-type", "application/json")}
        api_key = credentials.get("api_key")
        if api_key:
            header_name = credentials.get("auth_header_name") or "Authorization"
            scheme = credentials.get("auth_scheme", "Bearer ")
            headers[header_name] = f"{scheme}{api_key}"

        return BuiltRequest(
            method=incoming.method,
            url=f"{base_url.rstrip('/')}/{path.lstrip('/')}",
            headers=headers,
            params=dict(incoming.query_params),
            content=body,
            is_streaming=False,
        )
