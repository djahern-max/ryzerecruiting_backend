"""
tests/test_tenant_isolation.py
==============================

The most valuable tests in the suite. You just shipped tenant isolation and
proved by hand that greenpath's calls are invisible to ryze. These tests turn
that one-time manual check into a permanent, enforced invariant — and they run
with zero external API calls, so they're fast and never flaky.

Every test asserts BOTH directions:
  - the owning tenant CAN see its data (reachability), and
  - the other tenant CANNOT (isolation).

A regression that leaks data across tenants, or hides a tenant's own data,
fails here loudly.
"""

from __future__ import annotations

from app.api.chat import (
    tool_get_meetings_by_date,
    tool_get_candidate_calls,
)
from conftest import names_in_meetings


# --------------------------------------------------------------------------
# By-date reachability + isolation  (pure SQL, no embeddings)
# --------------------------------------------------------------------------
def test_owning_tenant_sees_its_calls_by_date(db, gt):
    res = tool_get_meetings_by_date(
        db, gt["call_date"], gt["call_date"], gt["seen_tenant"]
    )
    assert res["count"] >= len(gt["known_people"]), (
        f"Expected at least {len(gt['known_people'])} calls for "
        f"{gt['seen_tenant']} on {gt['call_date']}, got {res['count']}."
    )
    blob = names_in_meetings(res)
    for person in gt["known_people"]:
        assert (
            person in blob
        ), f"{person} missing from {gt['seen_tenant']} by-date results."


def test_other_tenant_cannot_see_those_calls_by_date(db, gt):
    res = tool_get_meetings_by_date(
        db, gt["call_date"], gt["call_date"], gt["blind_tenant"]
    )
    blob = names_in_meetings(res)
    for person in gt["known_people"]:
        assert person not in blob, (
            f"ISOLATION LEAK: {person} (a {gt['seen_tenant']} contact) is visible "
            f"to {gt['blind_tenant']} via get_meetings_by_date."
        )


# --------------------------------------------------------------------------
# Candidate call-history reachability + isolation  (pure SQL, no embeddings)
# --------------------------------------------------------------------------
def test_owning_tenant_finds_candidate_calls(db, gt):
    res = tool_get_candidate_calls(db, gt["known_candidate"], gt["seen_tenant"])
    assert res["count"] >= 1, (
        f"Expected at least one call on record for {gt['known_candidate']} "
        f"under {gt['seen_tenant']}, got {res['count']}."
    )


def test_other_tenant_finds_no_candidate_calls(db, gt):
    res = tool_get_candidate_calls(db, gt["known_candidate"], gt["blind_tenant"])
    assert res["count"] == 0, (
        f"ISOLATION LEAK: {gt['blind_tenant']} sees "
        f"{res['count']} call(s) for {gt['known_candidate']}."
    )


def test_candidate_tool_boundary_excludes_employer_contacts(db, gt):
    """
    Documents the real boundary of get_candidate_calls.

    The tool resolves a *candidate* by name first and returns early if none
    matches — so it reaches its employer_name fallback ONLY for a name that
    already matched a candidate row. Walt Kessler is a pure employer-side
    contact (Booking #2, candidate_id is null, no candidate row), so the
    candidate tool does NOT surface him. That is current, intended behavior
    for a tool named/scoped to candidates.

    This test asserts that boundary in both directions:
      - a candidate WITH a linked call (Renata) is reachable, and
      - an employer-only contact (Walt) is not returned by the candidate tool.

    PRODUCT DECISION (tracked, not asserted here): if you later want recruiters
    to ask "what did I discuss with <employer contact>?" and get their call
    back, that's a deliberate change to get_candidate_calls (move the
    employer_name match ahead of the early return) or to chat-layer routing —
    not something to bake in silently through this test.
    """
    # Candidate side: reachable for the owning tenant.
    seen_candidate = tool_get_candidate_calls(
        db, gt["known_candidate"], gt["seen_tenant"]
    )
    assert seen_candidate["count"] >= 1, (
        f"{gt['known_candidate']} (a candidate with a linked call) should be "
        f"reachable for {gt['seen_tenant']}."
    )

    # Employer-only contact: correctly NOT surfaced by the candidate tool.
    employer_via_candidate_tool = tool_get_candidate_calls(
        db, gt["known_employer_contact"], gt["seen_tenant"]
    )
    assert employer_via_candidate_tool["count"] == 0, (
        f"Expected the candidate tool to NOT return the employer-only contact "
        f"{gt['known_employer_contact']}, but it returned "
        f"{employer_via_candidate_tool['count']} call(s). If you intended to make "
        f"employer contacts recallable, that's a code change, not a test change."
    )

    # And the candidate path stays tenant-isolated.
    blind_candidate = tool_get_candidate_calls(
        db, gt["known_candidate"], gt["blind_tenant"]
    )
    assert (
        blind_candidate["count"] == 0
    ), f"ISOLATION LEAK: {gt['blind_tenant']} sees calls for {gt['known_candidate']}."
