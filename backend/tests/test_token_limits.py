"""
Tests for editing a developer token's quotas after creation.

Until now the four limit fields could only be set when the token was generated;
PATCH /api/v1/tokens/{id}/limits makes them editable. Enforcement is untouched,
so these tests also pin the developer-facing gateway routes the SDK calls.
"""
import os
import types
import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

pytest.importorskip("aiosqlite", reason="needed only to construct the engine; nothing connects")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())

from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_admin  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import AdminRole, DeveloperToken  # noqa: E402

TOKEN_ID = uuid.uuid4()
LIMIT_FIELDS = ("daily_request_limit", "monthly_request_limit", "daily_token_limit", "monthly_token_limit")


def make_token(**limits):
    token = DeveloperToken(
        id=TOKEN_ID, label="Anvesha", token_hash="h", token_prefix="dev_abc",
        status="active", notes=None, created_by_admin_id=uuid.uuid4(),
        total_requests=6, successful_requests=6, failed_requests=0,
        prompt_tokens=909, completion_tokens=1343, total_tokens=2252,
        total_latency_ms=23000, estimated_cost=0.0,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        **limits,
    )
    token.providers = []
    return token


class _FakeResult:
    def __init__(self, token):
        self._token = token

    def scalar_one_or_none(self):
        return self._token


class _FakeDB:
    def __init__(self, token):
        self.token = token

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self.token)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


def client_for(token, role=AdminRole.SUPER_ADMIN):
    db = _FakeDB(token)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: types.SimpleNamespace(id=uuid.uuid4(), role=role)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def patch_limits(token, payload, role=AdminRole.SUPER_ADMIN):
    return client_for(token, role).patch(f"/api/v1/tokens/{TOKEN_ID}/limits", json=payload)


def test_all_four_limits_can_be_set():
    token = make_token()
    response = patch_limits(token, {
        "daily_request_limit": 100, "monthly_request_limit": 2000,
        "daily_token_limit": 50_000, "monthly_token_limit": 1_000_000,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["daily_request_limit"] == 100
    assert body["monthly_request_limit"] == 2000
    assert body["daily_token_limit"] == 50_000
    assert body["monthly_token_limit"] == 1_000_000
    assert token.daily_request_limit == 100


def test_omitted_fields_are_left_unchanged():
    """PATCH must not silently wipe the quotas the caller didn't mention."""
    token = make_token(daily_request_limit=10, monthly_request_limit=20,
                       daily_token_limit=30, monthly_token_limit=40)
    response = patch_limits(token, {"daily_request_limit": 999})
    assert response.status_code == 200
    assert token.daily_request_limit == 999
    assert (token.monthly_request_limit, token.daily_token_limit, token.monthly_token_limit) == (20, 30, 40)


def test_explicit_null_clears_a_limit():
    token = make_token(daily_request_limit=10, monthly_request_limit=20)
    response = patch_limits(token, {"daily_request_limit": None})
    assert response.status_code == 200
    assert token.daily_request_limit is None, "null means unlimited"
    assert token.monthly_request_limit == 20


def test_empty_body_is_rejected():
    response = patch_limits(make_token(), {})
    assert response.status_code == 400
    assert "daily_request_limit" in response.json()["error"]


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_limits_are_rejected(value):
    """0 would lock the token out entirely — that is what Disable is for."""
    response = patch_limits(make_token(), {"daily_request_limit": value})
    assert response.status_code == 422


def test_unknown_token_is_404():
    response = patch_limits(None, {"daily_request_limit": 5})
    assert response.status_code == 404


def test_viewer_cannot_change_limits():
    response = patch_limits(make_token(), {"daily_request_limit": 5}, role=AdminRole.VIEWER)
    assert response.status_code == 403


def test_usage_counters_are_not_touched_by_a_limit_change():
    """Editing quotas must not disturb the metering columns shown in the table."""
    token = make_token()
    before = (token.total_requests, token.prompt_tokens, token.completion_tokens, token.total_tokens)
    patch_limits(token, {"daily_request_limit": 100})
    assert (token.total_requests, token.prompt_tokens, token.completion_tokens, token.total_tokens) == before


def test_sdk_facing_gateway_routes_are_untouched():
    """
    The SDK talks to unversioned /gateway/* paths. Admin token management lives
    under /api/v1 and must stay there.
    """
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/gateway/chat/completions" in paths
    assert "/gateway/audio/transcriptions" in paths
    assert "/gateway/credentials/{provider_name}" in paths
    assert "/api/v1/tokens/{token_id}/limits" in paths
    assert not any(p.startswith("/api/v1/gateway/chat") for p in paths)
