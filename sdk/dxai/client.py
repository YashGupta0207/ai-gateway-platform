from __future__ import annotations

from dxai._client import DXAIError, _BaseGatewayClient
from dxai.resources.chat import Chat


class DXAI(_BaseGatewayClient):
    """
    Usage, identical in spirit to the official OpenAI SDK:

        from dxai import DXAI

        client = DXAI(api_key="dev_xxxxxxxxx")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

    The developer token is bound to exactly one provider on the admin side —
    this SDK never sees, stores, or accepts a real provider API key.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 120.0):
        super().__init__(api_key=api_key, base_url=base_url, timeout=timeout)
        self.chat = Chat(self)


__all__ = ["DXAI", "DXAIError"]
