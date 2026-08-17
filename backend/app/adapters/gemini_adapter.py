from starlette.requests import Request

from app.adapters.base import (
    BaseProviderAdapter,
    BuiltRequest,
    CredentialField,
    ProviderConfigurationError,
)

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_AUDIO_MODEL = "gemini-1.5-flash"


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
        usage = self.usage_from_payload(
            payload,
            prompt_key="promptTokenCount",
            completion_key="candidatesTokenCount",
            total_key="totalTokenCount",
        )
        return usage or super().normalize_usage(content)

    async def build_chat_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        import json
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON body")
            
        model = payload.get("model") or self.credential_value(credentials, "model_name", required=False) or "gemini-1.5-pro"
        
        contents = []
        for msg in payload.get("messages", []):
            role = msg.get("role")
            if role == "assistant":
                role = "model"
            elif role == "system":
                role = "user" 
                
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })
            
        gemini_payload = {"contents": contents}
        
        is_streaming = payload.get("stream", False)
        path = f"models/{model}:streamGenerateContent?alt=sse" if is_streaming else f"models/{model}:generateContent"
        
        url = f"{DEFAULT_BASE_URL}/{path}"
        headers = {"Content-Type": "application/json"}
        
        return BuiltRequest(
            method="POST",
            url=url,
            headers=headers,
            params={"key": self.credential_value(credentials, "api_key", "gemini_key", "gemini_api_key")},
            json_body=gemini_payload,
            is_streaming=is_streaming,
        )

    async def build_audio_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        """
        Gemini has no /audio/transcriptions route — transcription is an ordinary
        generateContent call with the audio attached inline — so unlike the
        OpenAI-compatible adapters this one has to unpack the multipart body.
        """
        import base64
        import json

        form = await incoming.form()
        file_field = form.get("file")
        if not file_field or not hasattr(file_field, "read"):
            raise ProviderConfigurationError("Missing 'file' part in the multipart form data.")

        audio_bytes = await file_field.read()
        mime_type = getattr(file_field, "content_type", None) or "audio/wav"

        # Callers driving this through the OpenAI SDK send OpenAI model names
        # ("whisper-1", "gpt-4o-transcribe"), which Gemini would reject. Honour
        # the field only when it actually names a Gemini model.
        requested = form.get("model")
        model = requested if isinstance(requested, str) and requested.startswith("gemini") else None
        model = model or self.credential_value(credentials, "model_name", required=False) or DEFAULT_AUDIO_MODEL

        prompt = form.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            prompt = "Transcribe this audio. Return only the transcript text, with no commentary."

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(audio_bytes).decode("ascii")}},
                ],
            }]
        }

        return BuiltRequest(
            method="POST",
            url=f"{DEFAULT_BASE_URL}/models/{model}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": self.credential_value(credentials, "api_key", "gemini_key", "gemini_api_key")},
            json_body=payload,
            is_streaming=False,
        )

    def normalize_audio_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        """Reshape Gemini's generateContent reply into OpenAI's {"text": ...}."""
        import json
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return content, self.normalize_usage(content)
        if not isinstance(payload, dict) or "candidates" not in payload:
            # An upstream error body — hand it back untouched rather than
            # flattening it into an empty transcript.
            return content, self.normalize_usage(content)

        usage = self.normalize_usage(content)
        text = ""
        candidates = payload.get("candidates") or []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))

        return json.dumps({"text": text}).encode("utf-8"), usage

    def normalize_chat_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        import json
        import time
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return content, self.normalize_usage(content)
            
        usage = self.normalize_usage(content)
        
        text = ""
        candidates = payload.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                text = parts[0].get("text", "")
                
        openai_response = {
            "id": "chatcmpl-gemini",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "gemini",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text
                },
                "finish_reason": "stop"
            }],
            "usage": usage
        }
        
        return json.dumps(openai_response).encode("utf-8"), usage
