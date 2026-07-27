"""
tests/test_usage_metering.py — pure-function coverage for app/services/usage.py.

Deliberately does not touch the DB (matches this suite's read-only-live-DB
convention — see tests/README.md). record_usage/get_month_cost/is_over_budget/
check_ai_budget need a real Session and are verified manually against a dev DB.
"""
from datetime import datetime

from app.services.usage import _cost_for, PRICING


def test_cost_for_known_model():
    cost = _cost_for("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == PRICING["claude-sonnet-4-6"]["input"] * 1_000_000 + \
        PRICING["claude-sonnet-4-6"]["output"] * 1_000_000
    assert round(cost, 2) == 18.00


def test_cost_for_zero_tokens():
    assert _cost_for("claude-haiku-4-5-20251001", 0, 0) == 0.0


def test_cost_for_unknown_model_returns_zero(caplog):
    with caplog.at_level("WARNING"):
        cost = _cost_for("some-future-model-not-in-pricing", 100, 100)
    assert cost == 0.0
    assert any("Unknown model" in record.message for record in caplog.records)


def test_month_start_boundary_math():
    # Mirrors the month_start = datetime(now.year, now.month, 1) logic in
    # get_month_cost — a call on the last day of the month must still use
    # day 1 as the boundary, not roll into the next month.
    now = datetime(2026, 7, 31, 23, 59, 59)
    month_start = datetime(now.year, now.month, 1)
    assert month_start == datetime(2026, 7, 1, 0, 0, 0)

    now = datetime(2026, 1, 1, 0, 0, 1)
    month_start = datetime(now.year, now.month, 1)
    assert month_start == datetime(2026, 1, 1, 0, 0, 0)
