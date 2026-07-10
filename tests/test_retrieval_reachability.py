"""
tests/test_retrieval_reachability.py
====================================

Proves the semantic (pgvector) path — the one that was silently returning
nothing whenever a booking wasn't embedded, and the one your "what did we
discuss" questions route to.

These need a query embedding from OpenAI, so they're marked `semantic` and
auto-skip if the embedding service is unreachable (offline / no key). They are
cheap (one short embedding per test), but if you want to run fully offline:

    pytest -m "not semantic"

Both directions are asserted here too: the owning tenant's embedded calls are
retrievable, and the vector search cannot return them to another tenant (the
WHERE tenant_id filter lives inside _vector_search, so this locks that in).
"""

from __future__ import annotations

import pytest

from app.api.chat import tool_search_meeting_notes, tool_search_candidates
from conftest import ids_in


pytestmark = pytest.mark.semantic


@pytest.fixture(autouse=True)
def _skip_without_embeddings(embeddings_available):
    if not embeddings_available:
        pytest.skip("Embedding service unavailable — skipping semantic retrieval tests.")


def _owning_tenant_booking_ids(db, gt):
    """Discover the owning tenant's booking ids straight from the DB (no hardcoding)."""
    from app.models.booking import Booking

    rows = (
        db.query(Booking.id)
        .filter(Booking.tenant_id == gt["seen_tenant"])
        .all()
    )
    return {r[0] for r in rows}


def test_meeting_notes_semantic_search_finds_seeded_calls(db, gt):
    res = tool_search_meeting_notes(
        db, "recruiting screening call transcript", limit=10, tenant_id=gt["seen_tenant"]
    )
    assert res["count"] >= 1, (
        "Semantic search over meeting notes returned nothing for the owning tenant. "
        "If the diagnostic showed embedded=yes, check that _vector_search's tenant "
        "filter matches the tenant string exactly."
    )
    found = ids_in(res, "meetings")
    owned = _owning_tenant_booking_ids(db, gt)
    assert found & owned, (
        f"Semantic results {found} don't overlap the owning tenant's bookings {owned}."
    )


def test_meeting_notes_semantic_search_is_tenant_scoped(db, gt):
    """The other tenant must never get the owning tenant's bookings back."""
    owned = _owning_tenant_booking_ids(db, gt)
    res = tool_search_meeting_notes(
        db, "recruiting screening call transcript", limit=10, tenant_id=gt["blind_tenant"]
    )
    leaked = ids_in(res, "meetings") & owned
    assert not leaked, (
        f"ISOLATION LEAK: vector search returned {gt['seen_tenant']} bookings "
        f"{leaked} to {gt['blind_tenant']}."
    )


def test_candidate_semantic_search_scoped(db, gt):
    """
    Candidate vector search must also respect tenant. We assert isolation
    (the strong invariant); reachability depends on the query matching the
    candidate's embedded resume/transcript, which is looser to assert on.
    """
    from app.models.candidate import Candidate

    owned_candidate_ids = {
        r[0]
        for r in db.query(Candidate.id)
        .filter(Candidate.tenant_id == gt["seen_tenant"])
        .all()
    }
    res = tool_search_candidates(
        db, "accounting finance candidate", limit=10, tenant_id=gt["blind_tenant"]
    )
    leaked = {c.get("id") for c in res.get("candidates", [])} & owned_candidate_ids
    assert not leaked, (
        f"ISOLATION LEAK: candidate vector search returned {gt['seen_tenant']} "
        f"candidates {leaked} to {gt['blind_tenant']}."
    )
