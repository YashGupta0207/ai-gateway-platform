# AI Gateway — Admin Portal + API Gateway + Developer SDK

A proxy layer between developers and AI providers. Developers authenticate
with temporary tokens (`dev_xxxxx`); they never see real provider API keys,
endpoints, or connection strings. Admins configure providers through a
dynamic form driven entirely by each provider's adapter — adding a new
provider never requires a schema migration or a UI redesign.

```
Developer → dev_ token → Gateway → validate token → decrypt credentials → call provider → return response
```

## Project layout

```
backend/        FastAPI gateway + admin API (auth, providers, tokens, proxy, dashboard)
admin-portal/   React + TS + Vite + Tailwind admin UI
sdk/            Python developer SDK (dxai, dxdeepgram)
nginx/          Root reverse proxy routing /api and /gateway to the backend, everything else to the UI
docker-compose.yml
```

## Supported providers (Phase 1)

OpenAI, Azure OpenAI, Gemini, Deepgram — each as an isolated adapter under
`backend/app/adapters/`. Adding provider #5 means writing one adapter class
and registering it in `backend/app/adapters/registry.py`; nothing else in
the gateway changes.

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env
# edit backend/.env:
#   - generate JWT_SECRET_KEY:            python -c "import secrets; print(secrets.token_urlsafe(64))"
#   - generate CREDENTIAL_ENCRYPTION_KEY:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up --build -d

# run migrations (compose already does this on api startup, but if you need it standalone):
docker compose exec api alembic upgrade head

# create the first admin account
docker compose exec -e SEED_ADMIN_EMAIL=you@example.com -e SEED_ADMIN_PASSWORD=change-me-now api \
  python -m scripts.seed_super_admin
```

- Admin UI: http://localhost/ (or http://localhost:5173 directly)
- API docs (Swagger): http://localhost/docs
- Gateway proxy base (what the SDK talks to): http://localhost/gateway

## Local development (without Docker)

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # point DATABASE_URL/REDIS_URL at local instances
alembic upgrade head
python -m scripts.seed_super_admin   # requires SEED_ADMIN_EMAIL/PASSWORD env vars
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd admin-portal
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev
```

**SDK**
```bash
cd sdk
pip install -e .
python -c "
from dxai import DXAI
client = DXAI(api_key='dev_xxx')   # defaults to the hosted gateway; pass base_url= or set DXAI_BASE_URL for local
print(client.chat.completions.create(model='gpt-4o', messages=[{'role':'user','content':'hi'}]))
"
```

## How a new provider gets added

1. Write `backend/app/adapters/<name>_adapter.py` subclassing `BaseProviderAdapter`,
   declaring `credential_schema()` and `build_request(...)`.
2. Register it in `backend/app/adapters/registry.py`.
3. Restart the API. The admin UI's "Add provider" dropdown and dynamic
   credential form pick it up automatically via `GET /api/v1/providers/available-adapters`
   — no frontend changes needed.

## Security notes

- All provider credentials are encrypted individually (Fernet/AES) before
  being written to `providers.encrypted_credentials`; nothing is ever
  stored in plaintext.
- Developer tokens are stored as SHA-256 hashes, never in plaintext; the raw
  token is shown exactly once, at creation/regeneration time.
- Admin auth uses short-lived JWT access tokens + longer-lived refresh
  tokens; passwords are bcrypt-hashed.
- Role-based access control: `super_admin` / `admin` / `viewer`, enforced
  per-route via `require_role(...)`.

## Explicitly out of scope for Phase 1

Rate limiting, cost tracking, usage limits, billing, and usage analytics —
per the spec, these were deliberately deferred. The architecture supports
adding them later: `ApiRequestLog` already captures per-request latency,
size, and status, which is what a rate limiter or billing engine would
read from; a rate-limit check would slot into `gateway_service.proxy_request`
as a single new step before `adapter.send(...)`.

## What's stubbed vs. wired

- Password-reset email sending is wired as a hook (`backend/app/services/email_service.py`)
  with a commented Brevo HTTP API example — plug in real credentials to activate; until then it logs the reset link server-side so the flow is still testable end-to-end.
- Redis is provisioned in Docker Compose and `REDIS_URL` is available in
  config, but nothing consumes it yet in Phase 1 (no caching/rate-limiting
  work is in scope). It's there so Phase 2 additions don't need new infra.
