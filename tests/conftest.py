"""
tests/conftest.py — shared fixtures + ground-truth config for the
RYZE Intelligence regression suite.

WHAT THIS SUITE DOES
--------------------
It locks in the behavior your webhook diagnostic just proved correct:
  1. Tenant isolation — a tenant can see its calls; another firm cannot — plus
     the tenant-access rules (billing_exempt, missing tenant row, NULL
     users.tenant_id, is_superuser as platform owner).
  2. Retrieval reachability — the seeded calls are findable by date, by name,
     and by semantic (vector) search.
  3. (opt-in) End-to-end Intelligence answers reference the right people.

HOW IT'S LAYERED (by cost / determinism)
----------------------------------------
  test_tenant_isolation.py     -> self-contained: builds its own tenants/rows in
                                  a rolled-back transaction. No external APIs,
                                  no seed data. Always runs. Fast.
  test_signup_tenant_resolution -> same transactional pattern, no external APIs;
                                  drives /oauth/complete-signup with a fake
                                  redis_client, so no Redis needed either.
  test_retrieval_reachability  -> needs OpenAI (query embedding). Cheap. Auto-skips
                                  if the embedding service is unreachable.
  test_intelligence_e2e.py     -> needs OpenAI + Anthropic. Opt-in only:
                                  RUN_LLM_TESTS=1 pytest

IMPORTANT
---------
Nothing in this suite commits to your database. The transactional tiers flush
rows inside a transaction that is always rolled back; the semantic / LLM tiers
read live seed data read-only. The ground truth below matches the two seeded
actor-demo calls under green_path_recruiting and is used ONLY by those two
tiers. Edit GROUND_TRUTH when your seed data changes.

RUN FROM the backend project root (folder containing `app/`), venv active:
    pytest -v
    RUN_LLM_TESTS=1 pytest -v          # include the LLM end-to-end tier
    pytest -v -m "not semantic"        # skip embedding-dependent tests (offline)
"""

from __future__ import annotations

import os
import sys

import pytest

# Make the app package importable when pytest is run from the project root.
sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal  # noqa: E402


# --------------------------------------------------------------------------
# Ground truth — the facts your webhook diagnostic established.
# Update these if you re-seed. Names live in Booking.employer_name.
# --------------------------------------------------------------------------
GROUND_TRUTH = {
    # The firm whose data actually exists in the DB right now.
    "seen_tenant": "green_path_recruiting",
    # A different firm that must NOT be able to see the above.
    "blind_tenant": "other_firm_recruiting",
    # Date the actor-demo calls were booked on (ISO).
    "call_date": "2026-07-09",
    # People who appear on greenpath's calls (in Booking.employer_name).
    "known_people": ["Renata Voss", "Walt Kessler"],
    # A candidate with a linked booking (candidate_id FK set).
    "known_candidate": "Renata Voss",
    # An employer-side contact with NO linked candidate.
    "known_employer_contact": "Walt Kessler",
}


@pytest.fixture()
def gt():
    """Ground-truth config, injected into tests."""
    return GROUND_TRUTH


@pytest.fixture()
def db():
    """A read-only DB session, closed after each test (semantic / LLM tiers).
    The transactional test modules shadow this with their own rollback fixture."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def embeddings_available():
    """
    True if the embedding service answers. Semantic tests skip cleanly when
    it doesn't (e.g. no network / missing OPENAI_API_KEY), instead of erroring.
    """
    try:
        from app.services.embedding_service import generate_embedding

        vec = generate_embedding("healthcheck")
        return bool(vec)
    except Exception:
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "semantic: requires the OpenAI embedding service")
    config.addinivalue_line("markers", "llm: requires Anthropic (opt-in via RUN_LLM_TESTS=1)")


# Reusable skip guard for the LLM tier.
RUN_LLM = os.getenv("RUN_LLM_TESTS") == "1"
requires_llm = pytest.mark.skipif(
    not RUN_LLM,
    reason="LLM end-to-end tier is opt-in; set RUN_LLM_TESTS=1 to run it.",
)


# --------------------------------------------------------------------------
# Small helpers shared across test modules
# --------------------------------------------------------------------------
def names_in_meetings(result: dict) -> str:
    """Flatten employer/company names from a tool result into one searchable blob."""
    blob = []
    for m in result.get("meetings", []) or []:
        blob.append(str(m.get("employer_name") or ""))
        blob.append(str(m.get("company_name") or ""))
        blob.append(str(m.get("candidate_name") or ""))
    return " ".join(blob)


def ids_in(result: dict, key: str = "meetings") -> set[int]:
    return {m.get("id") for m in (result.get(key) or []) if m.get("id") is not None}
