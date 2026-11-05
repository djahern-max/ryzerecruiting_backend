"""
tests/test_signup_tenant_resolution.py

Deterministic, no-LLM tier — transactional DB fixture, no external API calls.

Covers the rule from tenant restructure part 3: there are no unplaced users.
A self-registering Candidate / Employer gets the one firm that already has
their email on file, or is refused (403 no firm, 409 several firms) with no
`users` row written.

Three layers:
  1. resolve_signup_tenant in isolation.
  2. AuthService.create_user — the /register path — refusal leaves no row,
     success stamps the firm's slug.
  3. POST /api/auth/oauth/complete-signup through the ASGI app, with
     app.api.auth.redis_client replaced by a dict-backed fake: a refusal
     reaches the client as 403 with its detail and deletes the temp token.

The `db` fixture shadows conftest's read-only one. Rows are flushed, never
committed: the session's commit() is redirected to flush() so the service's
own commit calls stay inside the transaction, which is rolled back at
teardown — including on assertion failure.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from fastapi import HTTPException

import app.api.auth as auth_api
from app.core.database import SessionLocal, get_db
from app.main import app
from app.models.booking import Booking  # noqa: F401  (FK target for Candidate)
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.user import User, UserType
from app.schemas.user import PublicUserType, UserCreate
from app.services.auth import AuthService
from app.services.tenant_resolution import (
    MULTI_FIRM_DETAIL,
    NO_FIRM_DETAIL,
    resolve_signup_tenant,
)


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def _slug(tag: str) -> str:
    return f"test_{tag}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture()
def db(monkeypatch):
    session = SessionLocal()
    monkeypatch.setattr(session, "commit", session.flush)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class _FakeRedis:
    """Just enough of redis.Redis for app.api.auth's temp-token helpers."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(auth_api, "redis_client", fake)
    return fake


@pytest.fixture()
def client(db):
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        yield _Client()
    finally:
        app.dependency_overrides.clear()


class _Client:
    """Minimal sync HTTP client over the in-process ASGI app (starlette 0.35's
    TestClient is incompatible with the pinned httpx 0.28)."""

    def post(self, path: str, params: dict | None = None) -> httpx.Response:
        async def _go():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as ac:
                return await ac.post(path, params=params)

        return asyncio.run(_go())


def _user_count(db, email: str) -> int:
    return db.query(User).filter(User.email == email).count()


def add_candidate(db, email: str, tenant_id: str) -> None:
    db.add(Candidate(name="Test Candidate", email=email, tenant_id=tenant_id))
    db.flush()


# ==========================================================================
# 1. resolve_signup_tenant
# ==========================================================================
def test_single_firm_match_resolves_to_that_firm(db):
    email, firm = _email(), _slug("firm")
    add_candidate(db, email, firm)

    assert resolve_signup_tenant(db, email, UserType.CANDIDATE) == firm


def test_match_is_case_insensitive(db):
    email, firm = _email(), _slug("firm")
    add_candidate(db, email, firm)

    assert resolve_signup_tenant(db, email.upper(), UserType.CANDIDATE) == firm


def test_employer_email_resolves_via_employer_profiles(db):
    email, firm = _email(), _slug("firm")
    db.add(
        EmployerProfile(
            company_name="Test Co", primary_contact_email=email, tenant_id=firm
        )
    )
    db.flush()

    assert resolve_signup_tenant(db, email, UserType.EMPLOYER) == firm


def test_no_match_is_403(db):
    with pytest.raises(HTTPException) as exc:
        resolve_signup_tenant(db, _email(), UserType.CANDIDATE)
    assert exc.value.status_code == 403
    assert exc.value.detail == NO_FIRM_DETAIL


def test_empty_email_is_403(db):
    with pytest.raises(HTTPException) as exc:
        resolve_signup_tenant(db, "   ", UserType.CANDIDATE)
    assert exc.value.status_code == 403
    assert exc.value.detail == NO_FIRM_DETAIL


def test_multi_firm_match_is_409(db, caplog):
    email = _email()
    add_candidate(db, email, _slug("firm_a"))
    add_candidate(db, email, _slug("firm_b"))

    with caplog.at_level("WARNING"):
        with pytest.raises(HTTPException) as exc:
            resolve_signup_tenant(db, email, UserType.CANDIDATE)

    assert exc.value.status_code == 409
    assert exc.value.detail == MULTI_FIRM_DETAIL
    assert "multiple firms" in caplog.text


def test_same_firm_twice_is_one_match(db):
    """Two candidate rows in the same firm are not a multi-firm conflict."""
    email, firm = _email(), _slug("firm")
    add_candidate(db, email, firm)
    add_candidate(db, email, firm)

    assert resolve_signup_tenant(db, email, UserType.CANDIDATE) == firm


def test_admin_never_resolves_to_a_firm(db):
    email = _email()
    add_candidate(db, email, _slug("firm"))

    with pytest.raises(HTTPException) as exc:
        resolve_signup_tenant(db, email, UserType.ADMIN)
    assert exc.value.status_code == 403
    assert exc.value.detail == NO_FIRM_DETAIL


# ==========================================================================
# 2. AuthService.create_user (the /register path)
# ==========================================================================
def _payload(email: str, user_type=PublicUserType.CANDIDATE) -> UserCreate:
    return UserCreate(
        email=email, password="correct-horse-battery", full_name="Test Person",
        user_type=user_type,
    )


def test_register_refused_leaves_no_user_row(db):
    email = _email()

    with pytest.raises(HTTPException) as exc:
        AuthService.create_user(db, _payload(email))
    assert exc.value.status_code == 403
    assert _user_count(db, email) == 0


def test_register_multi_firm_refused_leaves_no_user_row(db):
    email = _email()
    add_candidate(db, email, _slug("firm_a"))
    add_candidate(db, email, _slug("firm_b"))

    with pytest.raises(HTTPException) as exc:
        AuthService.create_user(db, _payload(email))
    assert exc.value.status_code == 409
    assert _user_count(db, email) == 0


def test_register_single_match_stamps_that_firm(db):
    email, firm = _email(), _slug("firm")
    add_candidate(db, email, firm)

    user = AuthService.create_user(db, _payload(email))

    assert user.tenant_id == firm
    assert user.user_type == UserType.CANDIDATE
    assert _user_count(db, email) == 1


# ==========================================================================
# 3. POST /api/auth/oauth/complete-signup
# ==========================================================================
def _seed_temp_token(fake_redis: _FakeRedis, email: str) -> str:
    token = f"tok_{uuid.uuid4().hex}"
    auth_api.store_oauth_temp_data(
        token,
        {
            "email": email,
            "oauth_provider": "google",
            "oauth_provider_id": uuid.uuid4().hex,
            "full_name": "OAuth Person",
            "avatar_url": None,
        },
    )
    assert f"oauth_temp:{token}" in fake_redis.store
    return token


def test_oauth_no_match_is_403_and_clears_temp_token(db, client, fake_redis):
    email = _email()
    token = _seed_temp_token(fake_redis, email)

    resp = client.post(
        "/api/auth/oauth/complete-signup",
        params={"temp_token": token, "user_type": "CANDIDATE"},
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == NO_FIRM_DETAIL
    assert f"oauth_temp:{token}" not in fake_redis.store, "temp token must be deleted"
    assert _user_count(db, email) == 0

    # The flow cannot be replayed: the token is now unknown.
    replay = client.post(
        "/api/auth/oauth/complete-signup",
        params={"temp_token": token, "user_type": "CANDIDATE"},
    )
    assert replay.status_code == 400


def test_oauth_multi_firm_is_409_and_clears_temp_token(db, client, fake_redis):
    email = _email()
    add_candidate(db, email, _slug("firm_a"))
    add_candidate(db, email, _slug("firm_b"))
    token = _seed_temp_token(fake_redis, email)

    resp = client.post(
        "/api/auth/oauth/complete-signup",
        params={"temp_token": token, "user_type": "CANDIDATE"},
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == MULTI_FIRM_DETAIL
    assert f"oauth_temp:{token}" not in fake_redis.store
    assert _user_count(db, email) == 0


def test_oauth_single_match_creates_user_in_that_firm(db, client, fake_redis):
    email, firm = _email(), _slug("firm")
    add_candidate(db, email, firm)
    token = _seed_temp_token(fake_redis, email)

    resp = client.post(
        "/api/auth/oauth/complete-signup",
        params={"temp_token": token, "user_type": "CANDIDATE"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["tenant_id"] == firm
    assert body["access_token"]
    assert f"oauth_temp:{token}" not in fake_redis.store
    assert db.query(User).filter(User.email == email).one().tenant_id == firm
