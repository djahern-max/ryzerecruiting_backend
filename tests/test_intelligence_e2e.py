"""
tests/test_intelligence_e2e.py
==============================

The full path: runs stream_chat_response end-to-end (agentic tool loop +
streamed answer) and asserts the answer references the right people for the
owning tenant, and does NOT for the other tenant.

This tier costs real Anthropic + OpenAI tokens and is non-deterministic (it's
an LLM), so it's OPT-IN:

    RUN_LLM_TESTS=1 pytest -v tests/test_intelligence_e2e.py

Assertions are deliberately loose — entity presence/absence, not exact wording —
so a phrasing change doesn't fail the test but a retrieval/isolation regression
does. This is your "is the whole thing actually wired together" smoke test;
the deterministic tiers are what you rely on for precise regressions.
"""

from __future__ import annotations

import json

import pytest

from app.api.chat import ChatRequest, stream_chat_response
from conftest import requires_llm


def _collect(payload, db, tenant_id) -> str:
    """
    Drain the generator and return just the human-facing answer text:
    strip __STATUS__ progress lines and the trailing __DATA__ JSON blob.
    """
    chunks = list(stream_chat_response(payload, db, tenant_id))
    raw = "".join(chunks)
    # Everything after the __DATA__ sentinel is structured card data, not prose.
    answer = raw.split("__DATA__")[0]
    # Drop the progress lines.
    lines = [ln for ln in answer.splitlines() if not ln.startswith("__STATUS__")]
    return "\n".join(lines).strip()


@requires_llm
def test_e2e_owning_tenant_recalls_the_call(db, gt):
    payload = ChatRequest(
        message=f"What calls did I have on {gt['call_date']}? Who did I speak with?",
        history=[],
    )
    answer = _collect(payload, db, gt["seen_tenant"])
    assert answer, "Empty answer from stream_chat_response."
    # At least one known person should surface (match on last name to be lenient).
    last_names = [p.split()[-1] for p in gt["known_people"]]
    assert any(ln.lower() in answer.lower() for ln in last_names), (
        f"Expected one of {last_names} in the answer, got:\n{answer}"
    )


@requires_llm
def test_e2e_other_tenant_does_not_leak(db, gt):
    payload = ChatRequest(
        message=f"What calls did I have on {gt['call_date']}? Who did I speak with?",
        history=[],
    )
    answer = _collect(payload, db, gt["blind_tenant"])
    last_names = [p.split()[-1] for p in gt["known_people"]]
    for ln in last_names:
        assert ln.lower() not in answer.lower(), (
            f"ISOLATION LEAK in the generated answer: '{ln}' appeared for "
            f"{gt['blind_tenant']}.\n{answer}"
        )


@requires_llm
def test_e2e_semantic_question_recalls_discussion(db, gt):
    """
    The 'what did we discuss' style question that routes to the embedding-backed
    tool — the exact phrasing that used to whiff. Confirms the answer isn't a
    blank 'no record found' for the owning tenant.
    """
    payload = ChatRequest(
        message=f"What did I discuss with {gt['known_candidate']}?",
        history=[],
    )
    answer = _collect(payload, db, gt["seen_tenant"])
    assert answer, "Empty answer."
    no_record_signals = ["no record", "no calls", "couldn't find", "no meetings", "don't have"]
    assert not any(sig in answer.lower() for sig in no_record_signals), (
        f"Intelligence claims no record of {gt['known_candidate']} despite an "
        f"embedded call on file:\n{answer}"
    )
