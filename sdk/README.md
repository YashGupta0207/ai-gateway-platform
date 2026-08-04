# DXAI SDK

Developer SDKs for the AI Gateway. You authenticate with a `dev_xxxxx` token
issued from the admin portal — you never see or handle a real provider API
key, endpoint, or secret. Every call is routed through the Gateway, which
resolves your token to whichever provider the admin assigned it to.

## Install

```bash
pip install -e .
```

(Once published: `pip install dxai-sdk`.)

## Chat completions (OpenAI / Azure OpenAI style)

```python
from dxai import DXAI

client = DXAI(api_key="dev_xxxxxxxxx", base_url="https://your-gateway.example.com")

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response)

# Streaming
for chunk in client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Stream this"}],
    stream=True,
):
    print(chunk)
```

## Transcription (Deepgram style)

```python
from dxdeepgram import DeepgramClient

client = DeepgramClient(api_key="dev_xxxxxxxxx", base_url="https://your-gateway.example.com")
result = client.transcribe_file("audio.wav", mimetype="audio/wav")
print(result)
```

## Configuration

Instead of passing `api_key`/`base_url` explicitly, you can set:

```bash
export DXAI_API_KEY=dev_xxxxxxxxx
export DXAI_BASE_URL=https://your-gateway.example.com
```

## Error handling

```python
from dxai import DXAI, DXAIError

try:
    client.chat.completions.create(model="gpt-4o", messages=[...])
except DXAIError as e:
    print(e.status_code, e.response_body)
```
