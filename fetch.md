# Fetching Credentials from AI Gateway

The AI Gateway provides a secure way for trusted backends (like ThreadNotes) to fetch decrypted credentials for a specific provider. This is useful when your backend needs to connect to services directly (e.g., Cosmos DB) instead of routing requests through the proxy.

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
