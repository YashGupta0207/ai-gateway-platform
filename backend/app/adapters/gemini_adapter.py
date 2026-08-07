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
