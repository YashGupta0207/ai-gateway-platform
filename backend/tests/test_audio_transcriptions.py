"""
Regression tests for routing audio transcription through the Gateway proxy.

These encode the contract the ThreadNotes integration depends on: a client
calling the OpenAI SDK's `audio.transcriptions.create(...)` against
POST /gateway/audio/transcriptions reaches the right Azure deployment, gets
the response back unchanged, and has the request metered.

Run with:  cd backend && python -m pytest tests -q
"""
import asyncio
import base64
import json
import os
import types

import httpx
import pytest
from cryptography.fernet import Fernet
from starlette.requests import Request

from app.adapters.azure_openai_adapter import DEFAULT_API_VERSION, AzureOpenAIAdapter
from app.adapters.base import ProviderConfigurationError
from app.adapters.gemini_adapter import GeminiAdapter
from app.adapters.openai_adapter import OpenAIAdapter
from app.adapters.registry import registry

AUDIO = b"RIFF\x00\x00WAVEfmt \x01\x02\x03\r\n--not-a-real-boundary\r\n" * 20

# The profile from the ThreadNotes integration: two deployments on one provider
# and no plain `deployment_name` anywhere.
AZURE_PROFILE = {
    "AZURE_OPENAI_KEY": "secret-key",
    "AZURE_OPENAI_ENDPOINT": "https://res.openai.azure.com/",
    "AZURE_TRANSCRIBE_DEPLOYMENT": "gpt-4o-transcribe",
    "AZURE_DIARIZE_DEPLOYMENT": "gpt-4o-transcribe-diarize",
    "AZURE_OPENAI_API_VERSION": "2025-04-01-preview",
}


def multipart(model="gpt-4o-transcribe", response_format="text", **extra):
    """A multipart body shaped exactly like the OpenAI SDK sends."""
    data = {k: v for k, v in {"model": model, "response_format": response_format, **extra}.items() if v is not None}
    request = httpx.Request("POST", "http://x", files={"file": ("audio.wav", AUDIO, "audio/wav")}, data=data)
    request.read()
    return request.content, request.headers["content-type"]


def incoming(content_type, headers=None, body=None):
    scope_headers = [(b"content-type", content_type.encode()), (b"user-agent", b"threadnotes/1.0")]
    for key, value in (headers or {}).items():
        scope_headers.append((key.lower().encode(), value.encode()))
    request = Request({
        "type": "http", "method": "POST", "path": "/gateway/audio/transcriptions",
        "headers": scope_headers, "query_string": b"", "client": ("10.0.0.5", 1234),
    })
    if body is not None:
        request._body = body
    return request


def build_audio(adapter, credentials, *, model="gpt-4o-transcribe", headers=None):
    body, content_type = multipart(model=model)
    return asyncio.run(adapter.build_audio_request(
        incoming=incoming(content_type, headers, body), body=body, credentials=credentials)), body


# --------------------------------------------------------------------------
# Deployment selection — blocker 1
# --------------------------------------------------------------------------

def test_model_field_selects_the_deployment():
    built, body = build_audio(AzureOpenAIAdapter(), AZURE_PROFILE)
    assert built.url == (
        "https://res.openai.azure.com/openai/deployments/gpt-4o-transcribe/audio/transcriptions"
    )
    assert built.content == body, "the multipart body must be forwarded byte-for-byte"


def test_two_models_hit_different_azure_urls():
    adapter = AzureOpenAIAdapter()
    transcribe, _ = build_audio(adapter, AZURE_PROFILE, model="gpt-4o-transcribe")
    diarize, _ = build_audio(adapter, AZURE_PROFILE, model="gpt-4o-transcribe-diarize")
    assert transcribe.url != diarize.url
    assert diarize.url.endswith("/deployments/gpt-4o-transcribe-diarize/audio/transcriptions")


def test_header_overrides_the_model_field():
    built, _ = build_audio(AzureOpenAIAdapter(), AZURE_PROFILE, headers={"X-Gateway-Deployment": "explicit-dep"})
    assert built.url.endswith("/deployments/explicit-dep/audio/transcriptions")


def test_falls_back_to_the_transcribe_credential_when_no_model_given():
    """AZURE_TRANSCRIBE_DEPLOYMENT used to match no alias and raise."""
    built, _ = build_audio(AzureOpenAIAdapter(), AZURE_PROFILE, model=None)
    assert built.url.endswith("/deployments/gpt-4o-transcribe/audio/transcriptions")


def test_missing_deployment_is_a_4xx_naming_the_accepted_keys():
    bare = {"AZURE_OPENAI_KEY": "k", "AZURE_OPENAI_ENDPOINT": "https://res.openai.azure.com"}
    with pytest.raises(ProviderConfigurationError) as excinfo:
        build_audio(AzureOpenAIAdapter(), bare, model=None)
    assert excinfo.value.status_code == 400
    message = str(excinfo.value)
    assert "azure_transcribe_deployment" in message
    assert "azure_diarize_deployment" in message
    assert "X-Gateway-Deployment" in message


# --------------------------------------------------------------------------
# API version — blocker 2
# --------------------------------------------------------------------------

def test_api_version_comes_from_credentials():
    built, _ = build_audio(AzureOpenAIAdapter(), AZURE_PROFILE)
    assert built.params == {"api-version": "2025-04-01-preview"}


def test_api_version_header_wins():
    built, _ = build_audio(AzureOpenAIAdapter(), AZURE_PROFILE, headers={"X-Gateway-Api-Version": "2099-01-01"})
    assert built.params == {"api-version": "2099-01-01"}


def test_api_version_defaults_to_the_historical_value():
    legacy = {"api_key": "k", "endpoint": "https://res.openai.azure.com", "deployment_name": "d"}
    built, _ = build_audio(AzureOpenAIAdapter(), legacy)
    assert built.params == {"api-version": DEFAULT_API_VERSION}


# --------------------------------------------------------------------------
# Usage normalization — blocker 3
# --------------------------------------------------------------------------

@pytest.mark.parametrize("body", [b"a plain transcript", b"42", b"null", b"", b"\xff\xfe\x00binary"])
def test_usage_without_json_reports_zeros_rather_than_raising(body):
    assert AzureOpenAIAdapter().normalize_usage(body)["total_tokens"] == 0


def test_usage_is_parsed_when_present():
    payload = json.dumps({"usage": {"prompt_tokens": 3, "completion_tokens": 4}}).encode()
    assert AzureOpenAIAdapter().normalize_usage(payload) == {
        "prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7, "estimated_cost": 0.0,
    }


def test_audio_response_is_passthrough():
    """Returning the same object is what tells the Gateway to keep Azure's Content-Type."""
    content = b"a transcript"
    normalized, _ = AzureOpenAIAdapter().normalize_audio_response(content)
    assert normalized is content


# --------------------------------------------------------------------------
# Existing chat traffic must be untouched
# --------------------------------------------------------------------------

def test_json_model_does_not_become_the_deployment():
    """
    Chat callers send a model name that is not necessarily a deployment name.
    Honouring `model` for JSON bodies would silently re-route existing traffic.
    """
    legacy = {"api_key": "k", "endpoint": "https://res.openai.azure.com", "deployment_name": "my-chat-deploy"}
    request = Request({"type": "http", "method": "POST", "path": "/gateway/chat/completions",
                       "headers": [(b"content-type", b"application/json")], "query_string": b""})
    body = json.dumps({"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}).encode()
    built = asyncio.run(AzureOpenAIAdapter().build_chat_request(incoming=request, body=body, credentials=legacy))
    assert built.url == "https://res.openai.azure.com/openai/deployments/my-chat-deploy/chat/completions"


def test_streaming_chat_still_detected():
    legacy = {"api_key": "k", "endpoint": "https://res.openai.azure.com", "deployment_name": "d"}
    request = Request({"type": "http", "method": "POST", "path": "/gateway/chat/completions",
                       "headers": [(b"content-type", b"application/json")], "query_string": b""})
    body = json.dumps({"model": "gpt-4o", "stream": True, "messages": []}).encode()
    built = asyncio.run(AzureOpenAIAdapter().build_chat_request(incoming=request, body=body, credentials=legacy))
    assert built.is_streaming is True


def test_binary_audio_body_does_not_break_stream_detection():
    """json.loads on a binary multipart body raises UnicodeDecodeError, not JSONDecodeError."""
    body, _ = multipart()
    for adapter in (AzureOpenAIAdapter(), OpenAIAdapter()):
        assert adapter.is_streaming_path("audio/transcriptions", body) is False


# --------------------------------------------------------------------------
# Multipart field extraction
# --------------------------------------------------------------------------

def test_multipart_field_extraction():
    body, content_type = multipart(model="gpt-4o-transcribe")
    field = AzureOpenAIAdapter.multipart_field
    assert field(body, content_type, "model") == "gpt-4o-transcribe"
    assert field(body, content_type, "response_format") == "text"
    assert field(body, content_type, "absent") is None
    assert field(body, content_type, "mod") is None, "must not match a name prefix"
    assert field(b'{"model": "x"}', "application/json", "model") is None, "JSON bodies are not multipart"
    assert field(body, content_type, "file") != "gpt-4o-transcribe"


# --------------------------------------------------------------------------
# The other providers
# --------------------------------------------------------------------------

def test_openai_audio_route_unchanged():
    built, body = build_audio(OpenAIAdapter(), {"api_key": "sk-x"})
    assert built.url == "https://api.openai.com/v1/audio/transcriptions"
    assert built.content == body


def test_generic_provider_reaches_audio_transcriptions():
    """An unregistered provider_type used to 501 on this route."""
    adapter = registry.get_or_generic("some-brand-new-provider")
    built, _ = build_audio(adapter, {"base_url": "https://api.example.com", "api_key": "k"})
    assert built.url == "https://api.example.com/audio/transcriptions"


def test_gemini_transcribes_via_generate_content():
    built, _ = build_audio(GeminiAdapter(), {"api_key": "AIza-test"}, model="whisper-1")
    assert built.url.endswith("/models/gemini-1.5-flash:generateContent")
    parts = built.json_body["contents"][0]["parts"]
    assert parts[1]["inline_data"]["data"] == base64.b64encode(AUDIO).decode()
    assert parts[1]["inline_data"]["mime_type"] == "audio/wav"


def test_gemini_honours_a_real_gemini_model_name():
    built, _ = build_audio(GeminiAdapter(), {"api_key": "AIza-test"}, model="gemini-2.0-flash")
    assert "/models/gemini-2.0-flash:generateContent" in built.url


def test_gemini_response_is_reshaped_to_openai_form():
    payload = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "hello "}, {"text": "world"}]}}],
        "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4, "totalTokenCount": 13},
    }).encode()
    content, usage = GeminiAdapter().normalize_audio_response(payload)
    assert json.loads(content) == {"text": "hello world"}
    assert usage["total_tokens"] == 13


def test_gemini_error_body_is_relayed_untouched():
    error = json.dumps({"error": {"code": 400, "message": "bad key"}}).encode()
    content, _ = GeminiAdapter().normalize_audio_response(error)
    assert content == error, "an error must not be flattened into an empty transcript"


def test_deepgram_audio_still_reports_not_implemented():
    with pytest.raises(NotImplementedError):
        build_audio(registry.get("deepgram"), {"api_key": "k"})


# --------------------------------------------------------------------------
# The proxy path: response fidelity and metering
# --------------------------------------------------------------------------

def _gateway_service():
    """Import the service with throwaway settings; it never opens a connection."""
    pytest.importorskip("aiosqlite", reason="needs any async DB driver to construct the engine")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
    os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.services import gateway_service
    return gateway_service


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def one(self):
        return (0, 0)          # _enforce_limits sees no prior usage

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.added = []

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self.rows)

    def add(self, entry):
        self.added.append(entry)

    async def commit(self):
        pass


def _fake_token():
    return types.SimpleNamespace(
        id=1, total_requests=0, successful_requests=0, failed_requests=0,
        first_used_at=None, last_used_at=None, last_client_ip=None, last_user_agent=None,
        prompt_tokens=0, completion_tokens=0, total_tokens=0, total_latency_ms=0, estimated_cost=0.0,
        daily_request_limit=None, monthly_request_limit=None,
        daily_token_limit=None, monthly_token_limit=None,
    )


def run_proxy(*, upstream_status=200, upstream_body=b"", upstream_headers=None, credentials=None, model="gpt-4o-transcribe"):
    service = _gateway_service()
    from app.core.encryption import cipher

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(upstream_status, content=upstream_body, headers=upstream_headers or {})

    original = service._client
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        rows = [types.SimpleNamespace(variable_name=k, encrypted_value=cipher.encrypt(v))
                for k, v in (credentials or AZURE_PROFILE).items()]
        db, token = _FakeDB(rows), _fake_token()
        body, content_type = multipart(model=model)
        response = asyncio.run(service.proxy_audio_request(
            db=db, token=token, provider=types.SimpleNamespace(id=7, adapter_key="azure_openai"),
            profile_id=1, incoming=incoming(content_type, body=body)))
        return response, db, token, captured
    finally:
        service._client = original


def test_plain_text_transcript_survives_the_round_trip():
    """response_format="text" must not come back labelled as JSON."""
    transcript = b"Speaker 1: hello there."
    response, _, _, _ = run_proxy(upstream_body=transcript,
                                  upstream_headers={"content-type": "text/plain; charset=utf-8"})
    assert response.body == transcript
    assert response.media_type == "text/plain; charset=utf-8"


def test_proxied_request_is_metered():
    """The whole point of proxy mode: Requests and Last used stop reading 0/never."""
    response, db, token, _ = run_proxy(upstream_body=b"transcript",
                                       upstream_headers={"content-type": "text/plain"})
    assert response.status_code == 200
    assert len(db.added) == 1
    assert db.added[0].endpoint == "/audio/transcriptions"
    assert db.added[0].status_code == 200
    assert token.total_requests == 1
    assert token.successful_requests == 1
    assert token.last_used_at is not None


def test_tokens_are_recorded_when_azure_reports_usage():
    payload = json.dumps({"text": "hi", "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}}).encode()
    _, _, token, _ = run_proxy(upstream_body=payload, upstream_headers={"content-type": "application/json"})
    assert token.total_tokens == 16
    assert (token.prompt_tokens, token.completion_tokens) == (11, 5)


def test_credentials_never_leak_back_to_the_caller():
    _, _, _, captured = run_proxy(upstream_body=b"ok")
    assert captured["headers"].get("api-key") == "secret-key"
    assert "authorization" not in {k.lower() for k in captured["headers"]}, "the dev_ token must not reach Azure"


def test_upstream_error_is_relayed_not_swallowed():
    error = json.dumps({"error": {"code": "DeploymentNotFound"}}).encode()
    response, _, token, _ = run_proxy(upstream_status=404, upstream_body=error,
                                      upstream_headers={"content-type": "application/json"})
    assert response.status_code == 404
    assert response.body == error
    assert token.failed_requests == 1
