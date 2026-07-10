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
        assert person in blob, f"{person} missing from {gt['seen_tenant']} by-date results."


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


def test_employer_side_contact_reachable_by_name(db, gt):
    """
    Walt Kessler has no linked candidate row — get_candidate_calls falls back to
    matching Booking.employer_name. Confirms that fallback path works for the
    owning tenant and stays isolated from the other.
    """
    seen = tool_get_candidate_calls(db, gt["known_employer_contact"], gt["seen_tenant"])
    assert seen["count"] >= 1, (
        f"{gt['known_employer_contact']} should be reachable by name for "
        f"{gt['seen_tenant']} via the employer_name fallback."
    )

    blind = tool_get_candidate_calls(
        db, gt["known_employer_contact"], gt["blind_tenant"]
    )
    assert blind["count"] == 0, (
        f"ISOLATION LEAK: {gt['blind_tenant']} sees calls for "
        f"{gt['known_employer_contact']}."
    )
