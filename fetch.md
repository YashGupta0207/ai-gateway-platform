# Fetching Credentials from AI Gateway

The AI Gateway provides a secure way for trusted backends (like ThreadNotes) to fetch decrypted credentials for a specific provider. This is useful when your backend needs to connect to services directly (e.g., Cosmos DB) instead of routing requests through the proxy.

> **Prefer proxy mode where it's available.** Credential fetch hands your backend the real key and the Gateway never sees the call, so `Requests`, `Tokens` and `Last used` stay empty for that token. Anything that speaks HTTP — chat completions, audio transcription — should go through the proxy instead so it gets metered. See [Proxy mode for audio transcription](#proxy-mode-for-audio-transcription) below. Credential fetch remains the right answer for SDKs that can't be proxied, such as Cosmos DB.

## Endpoint

**`GET /gateway/credentials/{provider_name}`**

### Headers Required

- `Authorization`: `Bearer dev_...` (Your Developer Token)
- `X-Gateway-Profile`: (Optional) The name of the specific profile to fetch credentials from.
- `X-Gateway-Tags`: (Optional) JSON string of tags to filter profiles by.

### Example Request (Python)

```python
import requests

GATEWAY_URL = "http://localhost:8000"
DEVELOPER_TOKEN = "dev_your_token_here"
PROVIDER_NAME = "cosmos-db"

headers = {
    "Authorization": f"Bearer {DEVELOPER_TOKEN}"
}

response = requests.get(
    f"{GATEWAY_URL}/gateway/credentials/{PROVIDER_NAME}",
    headers=headers
)

if response.status_code == 200:
    data = response.json()
    credentials = data.get("credentials", {})
    print("Fetched Credentials:", credentials)
else:
    print(f"Error: {response.status_code} - {response.text}")
```

### Example Request (cURL)

```bash
curl -X GET "http://localhost:8000/gateway/credentials/cosmos-db" \
     -H "Authorization: Bearer dev_your_token_here"
```

## Changes Required in Your Code

To use this new endpoint, developers should update their code to fetch credentials dynamically instead of relying on hardcoded environment variables.

1. **Remove Hardcoded Credentials**: Remove sensitive credentials (like `COSMOS_DB_KEY`, `COSMOS_DB_ENDPOINT`) from your `.env` file.
2. **Fetch at Startup or Runtime**: Add logic to fetch the credentials from the Gateway API using the developer token.
3. **Initialize Services**: Use the fetched credentials to initialize your services (e.g., Cosmos DB client).

### Example Integration

```python
# Before:
# cosmos_endpoint = os.getenv("COSMOS_DB_ENDPOINT")
# cosmos_key = os.getenv("COSMOS_DB_KEY")

# After:
import requests
import os

def get_cosmos_credentials():
    gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000")
    developer_token = os.getenv("GATEWAY_DEVELOPER_TOKEN")
    
    response = requests.get(
        f"{gateway_url}/gateway/credentials/cosmos-db",
        headers={"Authorization": f"Bearer {developer_token}"}
    )
    response.raise_for_status()
    return response.json()["credentials"]

# Use the credentials
creds = get_cosmos_credentials()
cosmos_endpoint = creds["endpoint"]
cosmos_key = creds["key"]
```

## Proxy mode for audio transcription

**`POST /gateway/audio/transcriptions`**

Point the OpenAI SDK at the Gateway and every call is metered — it shows up in
`ApiRequestLog` and increments the token's `Requests` and `Last used`. Your
backend never holds a provider key.

```python
from openai import OpenAI

client = OpenAI(
    api_key="dev_your_token_here",                 # Gateway developer token, not a provider key
    base_url="https://ai-gateway-platform-cex4.onrender.com/gateway",
    default_headers={"X-Gateway-Provider": "AzureOpenAI"},
)

transcript = client.audio.transcriptions.create(
    model="gpt-4o-transcribe",                     # selects the Azure deployment
    file=(filename, audio_bytes, mimetype),
    response_format="text",
)
```

### Choosing the Azure deployment

One provider can host several deployments, so the deployment is resolved per
request, in this order:

1. **`X-Gateway-Deployment` header** — an explicit override.
2. **The `model` field in the multipart body** — what the SDK already sends, so
   `model="gpt-4o-transcribe"` and `model="gpt-4o-transcribe-diarize"` reach
   different Azure deployments with no extra configuration.
3. **The provider profile's credentials** — any of `deployment_name`,
   `deployment`, `azure_deployment`, `azure_openai_deployment`,
   `azure_transcribe_deployment`, `azure_diarize_deployment`.

If none of those resolve, the Gateway returns **400** naming the accepted keys
rather than failing as a server error.

> `model` is read from multipart bodies only. Chat completions send a model name
> that is not necessarily an Azure deployment name, so JSON requests keep using
> the deployment from the profile — existing chat traffic is unaffected.

### API version

`gpt-4o-transcribe` is not served on the old default `2024-06-01`. Set the
version per profile with an `api_version` (or `azure_openai_api_version`)
credential variable, or per request with the `X-Gateway-Api-Version` header.
Profiles that set neither keep the `2024-06-01` default.

### Response format

The provider's response and `Content-Type` are passed through untouched, so
`response_format="text"` returns plain text and `response_format="json"` returns
JSON. Token counts are recorded when the provider reports a `usage` block; a
plain-text transcript carries none, so those requests are counted with zero
tokens rather than failing.

### Other providers

The same route works for OpenAI (`X-Gateway-Provider: OpenAI`), Gemini — where
transcription is translated to a `generateContent` call and the reply is
reshaped to OpenAI's `{"text": ...}` — Azure Speech, and any generic REST
provider that exposes an OpenAI-compatible `audio/transcriptions` endpoint.
