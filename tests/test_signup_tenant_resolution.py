"""
tests/test_signup_tenant_resolution.py

Deterministic, no-LLM tier — pure DB fixtures, no external API calls.

Tests app.services.tenant_resolution.resolve_signup_tenant in isolation via
a transactional fixture: rows are added + flushed (visible to the resolver's
own query within the same session/transaction) but never committed, and are
always rolled back in teardown — including on assertion failure — so this
file never mutates persistent state.

Note: this file defines its own `db` fixture, intentionally shadowing
conftest.py's read-only `db` fixture for tests in this module only —
resolve_signup_tenant only reads Candidate/EmployerProfile, so no User rows
are needed to exercise it.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.database import SessionLocal
from app.core.deps import RYZE_TENANT

# Booking/User imported (unused directly) so SQLAlchemy can resolve the FK
# targets on Candidate.booking_id / Candidate.user_id before insert.
from app.models.booking import Booking  # noqa: F401
from app.models.user import User, UserType  # noqa: F401
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.services.tenant_resolution import resolve_signup_tenant


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_single_firm_match_resolves_to_that_firm(db):
    email = _email()
    db.add(Candidate(name="Test Candidate", email=email, tenant_id="acme_test_firm"))
    db.flush()

    assert resolve_signup_tenant(db, email, UserType.CANDIDATE) == "acme_test_firm"


def test_no_match_resolves_to_ryze(db):
    email = _email()
    assert resolve_signup_tenant(db, email, UserType.CANDIDATE) == RYZE_TENANT


def test_multi_firm_match_resolves_to_ryze(db, caplog):
    email = _email()
    db.add(Candidate(name="Candidate A", email=email, tenant_id="firm_a"))
    db.add(Candidate(name="Candidate B", email=email, tenant_id="firm_b"))
    db.flush()

    with caplog.at_level("WARNING"):
        result = resolve_signup_tenant(db, email, UserType.CANDIDATE)

    assert result == RYZE_TENANT
    assert "multiple firms" in caplog.text


def test_employer_email_resolves_via_employer_profiles(db):
    email = _email()
    db.add(
        EmployerProfile(
            company_name="Test Co",
            primary_contact_email=email,
            tenant_id="acme_test_firm",
        )
    )
    db.flush()

    assert resolve_signup_tenant(db, email, UserType.EMPLOYER) == "acme_test_firm"


def test_admin_never_resolves_to_a_firm(db):
    email = _email()
    db.add(Candidate(name="Shouldn't Matter", email=email, tenant_id="acme_test_firm"))
    db.flush()

    assert resolve_signup_tenant(db, email, UserType.ADMIN) == RYZE_TENANT
