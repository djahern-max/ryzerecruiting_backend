# RYZE Intelligence regression suite

Locks in the retrieval + tenant-isolation behavior your webhook diagnostic
proved correct. Tests bind directly to the tool functions in `app/api/chat.py`
(service layer), so no running server or auth token is needed.

## Layout

| File | Tier | External APIs | Runs by default |
|------|------|---------------|-----------------|
| `test_tenant_isolation.py` | Deterministic SQL | none | yes |
| `test_retrieval_reachability.py` | Semantic / vector | OpenAI (embeddings) | yes (auto-skips offline) |
| `test_intelligence_e2e.py` | Full LLM loop | OpenAI + Anthropic | no (opt-in) |

## Running

From the backend project root (the folder containing `app/`), venv active:

```bash
pytest -v                       # deterministic + semantic tiers
RUN_LLM_TESTS=1 pytest -v       # add the end-to-end LLM tier
pytest -v -m "not semantic"     # fully offline (SQL only)
pytest -v tests/test_tenant_isolation.py   # just the isolation invariants
```

## Ground truth

All expected facts live in `GROUND_TRUTH` at the top of `conftest.py`
(tenants, call date, known people). When you re-seed or add real tenants,
update that one block and the whole suite follows.

Current seed under test:
- `greenpath_recruiting` — Booking #1 Renata Voss (candidate), Booking #2 Walt
  Kessler (employer contact), both on 2026-07-09, both embedded.
- `ryze` — must not see either.

## Notes

- The suite reads your **live** database read-only; it never writes. If you'd
  rather isolate it, point `DATABASE_URL` at a copy before running.
- Names are matched in `Booking.employer_name` (that's where the instant-meeting
  flow stores the contact name).
- The isolation tests assert both directions — owning tenant sees its data,
  other tenant does not — so a leak or a hidden record both fail loudly.
