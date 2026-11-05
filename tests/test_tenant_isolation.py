"""
tests/test_tenant_isolation.py
==============================

Tenant isolation and tenant-access invariants. Self-contained: every test
builds its own tenants, users and rows inside one transaction that is rolled
back at teardown (including on assertion failure), so this file never reads
seed data and never mutates persistent state. It needs a reachable DB and
nothing else — no OpenAI, no Anthropic, no running server.

Two layers:

  1. Isolation through the chat tool functions (pure SQL). Every test asserts
     BOTH directions — the owning tenant CAN see its data, the other tenant
     CANNOT — so a leak and a hidden record both fail loudly.

  2. Tenant access after restructure part 2 (no house tenant):
       - billing/usage exemption comes from tenants.billing_exempt
       - no tenants row                 -> 403
       - NULL users.tenant_id           -> 403
       - platform owner is is_superuser, not tenant membership

HTTP-level checks drive the ASGI app through httpx with get_db and
get_current_user overridden, so the real dependency chain
(get_current_admin_user -> require_tenant -> _check_tenant_access) is what
produces the status codes. (starlette's TestClient is not used: the pinned
starlette 0.35 passes `app=` to httpx, which httpx 0.28 no longer accepts.)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.deps import _check_tenant_access, get_current_user, require_tenant
from app.api.chat import tool_get_candidate_calls, tool_get_meetings_by_date
from app.api.db_explorer import _is_platform_owner
from app.main import app
from app.models.booking import Booking
from app.models.candidate import Candidate
from app.models.tenant import Tenant
from app.models.usage_event import UsageEvent
from app.models.user import User, UserType
from app.services.usage import is_over_budget
from conftest import names_in_meetings

CALL_DATE = date(2026, 7, 9)
CALL_DATE_ISO = CALL_DATE.isoformat()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture()
def db():
    """Transactional session — shadows conftest's read-only `db` for this
    module only. Rows are flushed (visible to queries in this session) but
    never committed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class _Client:
    """Minimal sync HTTP client over the in-process ASGI app."""

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        async def _go():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as ac:
                return await ac.get(path, params=params)

        return asyncio.run(_go())


@pytest.fixture()
def client(db):
    """HTTP client whose endpoints run against the test transaction. Tests
    pick the acting user with `_login(user)`."""

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        yield _Client()
    finally:
        app.dependency_overrides.clear()


def _login(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


# --------------------------------------------------------------------------
# Row builders — unique slugs/emails so tests never collide with live rows
# --------------------------------------------------------------------------
def _slug(tag: str) -> str:
    return f"test_{tag}_{uuid.uuid4().hex[:12]}"


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def make_tenant(db, tag: str = "firm", **overrides) -> Tenant:
    tenant = Tenant(
        slug=_slug(tag),
        company_name=f"Test {tag}",
        status="active",
        billing_exempt=False,
    )
    for key, value in overrides.items():
        setattr(tenant, key, value)
    db.add(tenant)
    db.flush()
    return tenant


def make_user(
    db,
    tenant_id: str,
    *,
    user_type: UserType = UserType.ADMIN,
    is_superuser: bool = False,
) -> User:
    user = User(
        email=_email(),
        full_name="Test User",
        user_type=user_type,
        is_active=True,
        is_superuser=is_superuser,
        tenant_id=tenant_id,
    )
    db.add(user)
    db.flush()
    return user


def transient_user(*, is_superuser: bool = False) -> User:
    """A User with no tenant that is never written: users.tenant_id is NOT
    NULL since restructure part 3, so the NULL-tenant cases below exercise
    require_tenant / is_superuser on an object the dependency override hands
    straight to the endpoint."""
    return User(
        email=_email(),
        full_name="Transient User",
        user_type=UserType.ADMIN,
        is_active=True,
        is_superuser=is_superuser,
        tenant_id=None,
    )


def make_candidate(db, tenant_id: str, name: str) -> Candidate:
    candidate = Candidate(tenant_id=tenant_id, name=name, email=_email())
    db.add(candidate)
    db.flush()
    return candidate


def make_booking(
    db,
    tenant_id: str,
    contact_name: str,
    *,
    candidate_id: int | None = None,
    booking_type: str = "inbound",
) -> Booking:
    booking = Booking(
        tenant_id=tenant_id,
        booking_type=booking_type,
        employer_name=contact_name,
        employer_email=_email(),
        company_name=f"{contact_name} Co",
        date=CALL_DATE,
        time_slot="10:00 AM",
        status="confirmed",
        candidate_id=candidate_id,
    )
    db.add(booking)
    db.flush()
    return booking


@pytest.fixture()
def firms(db):
    """Two peer tenants with data on the same date.

    seen:  Renata Voss (candidate row + linked outbound_candidate booking) and
           Walt Kessler (employer-side contact, booking only, no candidate row)
    blind: one booking of its own, so the blind tenant still sees *its* data.
    """
    seen = make_tenant(db, "seen")
    blind = make_tenant(db, "blind")

    renata = make_candidate(db, seen.slug, "Renata Voss")
    make_booking(
        db, seen.slug, "Renata Voss",
        candidate_id=renata.id, booking_type="outbound_candidate",
    )
    make_booking(db, seen.slug, "Walt Kessler")
    make_booking(db, blind.slug, "Blind Side Contact")

    return {
        "seen": seen.slug,
        "blind": blind.slug,
        "known_people": ["Renata Voss", "Walt Kessler"],
        "known_candidate": "Renata Voss",
        "known_employer_contact": "Walt Kessler",
        "blind_contact": "Blind Side Contact",
    }


# ==========================================================================
# 1. Isolation through the chat tool functions
# ==========================================================================
def test_owning_tenant_sees_its_calls_by_date(db, firms):
    res = tool_get_meetings_by_date(db, firms["seen"], CALL_DATE_ISO, CALL_DATE_ISO)
    assert res["count"] == len(firms["known_people"])
    blob = names_in_meetings(res)
    for person in firms["known_people"]:
        assert person in blob, f"{person} missing from owning-tenant by-date results."
    assert firms["blind_contact"] not in blob, (
        "ISOLATION LEAK: the blind tenant's contact is visible to the owning tenant."
    )


def test_other_tenant_cannot_see_those_calls_by_date(db, firms):
    res = tool_get_meetings_by_date(db, firms["blind"], CALL_DATE_ISO, CALL_DATE_ISO)
    blob = names_in_meetings(res)
    for person in firms["known_people"]:
        assert person not in blob, (
            f"ISOLATION LEAK: {person} (an owning-tenant contact) is visible to "
            f"the other tenant via get_meetings_by_date."
        )
    # Reachability in the other direction: the blind tenant sees its own call.
    assert res["count"] == 1
    assert firms["blind_contact"] in blob


def test_owning_tenant_finds_candidate_calls(db, firms):
    res = tool_get_candidate_calls(db, firms["seen"], firms["known_candidate"])
    assert res["count"] == 1
    assert res["meetings"][0]["candidate_name"] == firms["known_candidate"]


def test_other_tenant_finds_no_candidate_calls(db, firms):
    res = tool_get_candidate_calls(db, firms["blind"], firms["known_candidate"])
    assert res["count"] == 0, (
        f"ISOLATION LEAK: the other tenant sees {res['count']} call(s) for "
        f"{firms['known_candidate']}."
    )


def test_candidate_tool_boundary_excludes_employer_contacts(db, firms):
    """
    Documents the real boundary of get_candidate_calls.

    The tool resolves a *candidate* by name first and returns early if none
    matches — so it reaches its employer_name fallback ONLY for a name that
    already matched a candidate row. Walt Kessler is a pure employer-side
    contact (booking only, candidate_id NULL, no candidate row), so the
    candidate tool does NOT surface him. That is current, intended behavior
    for a tool named/scoped to candidates.

    PRODUCT DECISION (tracked, not asserted here): if recruiters should later
    be able to ask "what did I discuss with <employer contact>?", that is a
    deliberate change to get_candidate_calls (move the employer_name match
    ahead of the early return) or to chat-layer routing — not something to
    bake in silently through this test.
    """
    via_candidate_tool = tool_get_candidate_calls(
        db, firms["seen"], firms["known_employer_contact"]
    )
    assert via_candidate_tool["count"] == 0, (
        f"Expected the candidate tool to NOT return the employer-only contact "
        f"{firms['known_employer_contact']}, but it returned "
        f"{via_candidate_tool['count']} call(s). If you intended to make employer "
        f"contacts recallable, that's a code change, not a test change."
    )


# ==========================================================================
# 2. Behaviour 1 — billing / usage exemption comes from tenants.billing_exempt
# ==========================================================================
def test_billing_exempt_tenant_bypasses_402(db, client):
    tenant = make_tenant(db, "exempt", status="expired", billing_exempt=True)
    user = make_user(db, tenant.slug)

    assert _check_tenant_access(tenant.slug, db) == tenant.slug

    _login(user)
    assert client.get("/api/job-orders/open").status_code == 200


def test_non_exempt_expired_tenant_gets_402(db, client):
    tenant = make_tenant(db, "expired", status="expired", billing_exempt=False)
    user = make_user(db, tenant.slug)

    with pytest.raises(HTTPException) as exc:
        _check_tenant_access(tenant.slug, db)
    assert exc.value.status_code == 402

    _login(user)
    assert client.get("/api/job-orders/open").status_code == 402


def test_trial_window_is_enforced_unless_exempt(db):
    now = datetime.now(timezone.utc)
    live = make_tenant(db, "trial_live", status="trial", trial_ends_at=now + timedelta(days=7))
    lapsed = make_tenant(db, "trial_lapsed", status="trial", trial_ends_at=now - timedelta(days=1))
    lapsed_exempt = make_tenant(
        db, "trial_lapsed_exempt", status="trial",
        trial_ends_at=now - timedelta(days=1), billing_exempt=True,
    )

    assert _check_tenant_access(live.slug, db) == live.slug
    assert _check_tenant_access(lapsed_exempt.slug, db) == lapsed_exempt.slug
    with pytest.raises(HTTPException) as exc:
        _check_tenant_access(lapsed.slug, db)
    assert exc.value.status_code == 402


def test_billing_exempt_tenant_is_never_over_ai_budget(db):
    exempt = make_tenant(db, "exempt", billing_exempt=True)
    metered = make_tenant(db, "metered", billing_exempt=False)
    over = Decimal(str(settings.AI_MONTHLY_BUDGET_USD)) + Decimal("1")
    for slug in (exempt.slug, metered.slug):
        db.add(
            UsageEvent(
                tenant_id=slug,
                provider="anthropic",
                model="claude-sonnet-4-6",
                source="test",
                input_tokens=1,
                output_tokens=1,
                cost_usd=over,
                # naive UTC, matching usage.get_month_cost's month-boundary math
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    db.flush()

    assert is_over_budget(db, metered.slug) is True, "metering sanity check"
    assert is_over_budget(db, exempt.slug) is False


# ==========================================================================
# 3. Behaviour 2 — no tenants row = no access (403)
# ==========================================================================
def test_missing_tenant_row_is_403(db, client):
    orphan_slug = _slug("no_row")
    user = make_user(db, orphan_slug)

    with pytest.raises(HTTPException) as exc:
        _check_tenant_access(orphan_slug, db)
    assert exc.value.status_code == 403

    _login(user)
    resp = client.get("/api/job-orders/open")
    assert resp.status_code == 403, resp.text


# ==========================================================================
# 4. Behaviour 3 — NULL users.tenant_id = no access to tenant data (403)
#    (the column is NOT NULL since part 3; these guard the defensive branch)
# ==========================================================================
def test_null_user_tenant_is_403(db, client):
    user = transient_user()

    with pytest.raises(HTTPException) as exc:
        require_tenant(user)
    assert exc.value.status_code == 403

    _login(user)
    # get_current_tenant path (billing-enforcing dependency)
    assert client.get("/api/job-orders/open").status_code == 403
    # require_tenant path (admin list endpoint)
    assert client.get("/api/candidates").status_code == 403


def test_null_tenant_superuser_still_has_no_tenant_data_access(db, client):
    """is_superuser grants platform-level views, not a tenant's data."""
    user = transient_user(is_superuser=True)
    _login(user)
    assert client.get("/api/job-orders/open").status_code == 403
    assert client.get("/api/candidates").status_code == 403


# ==========================================================================
# 5. Behaviour 4 — platform owner = is_superuser, not tenant membership
# ==========================================================================
def test_platform_owner_is_the_superuser_flag(db):
    tenant = make_tenant(db)
    tenant_admin = make_user(db, tenant.slug, is_superuser=False)
    superuser_in_tenant = make_user(db, tenant.slug, is_superuser=True)
    superuser_no_tenant = transient_user(is_superuser=True)

    assert _is_platform_owner(tenant_admin) is False
    assert _is_platform_owner(superuser_in_tenant) is True
    assert _is_platform_owner(superuser_no_tenant) is True


def test_non_superuser_cannot_reach_unscoped_db_explorer(db, client, firms):
    tenant_admin = make_user(db, firms["seen"], is_superuser=False)
    _login(tenant_admin)
    assert client.get("/admin/db/counts").status_code == 403
    assert client.get("/admin/db/explorer", params={"table": "candidates"}).status_code == 403


def test_superuser_without_tenant_reaches_unscoped_db_explorer(db, client, firms):
    """The platform view does not need tenant membership, and it is unscoped:
    the counts include rows from every tenant created by this test."""
    owner = transient_user(is_superuser=True)
    _login(owner)

    resp = client.get("/admin/db/counts")
    assert resp.status_code == 200, resp.text
    counts = resp.json()
    # firms seeded 3 bookings across two tenants; an unscoped count sees all.
    assert counts["bookings"] >= 3
    assert counts["candidates"] >= 1
