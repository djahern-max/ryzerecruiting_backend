# RYZE Intelligence regression suite

Locks in the retrieval + tenant-isolation behavior your webhook diagnostic
proved correct, plus the tenant-access rules from the tenant restructure.
Tests bind directly to the tool functions in `app/api/chat.py` (service
layer) or drive the FastAPI app in-process with the auth dependency
overridden, so no running server or auth token is needed.

## Layout

| File | Tier | External APIs | Runs by default |
|------|------|---------------|-----------------|
| `test_tenant_isolation.py` | Deterministic, self-contained (rolled-back transaction) | none | yes |
| `test_signup_tenant_resolution.py` | Deterministic, self-contained (rolled-back transaction) | none | yes |
| `test_usage_metering.py` | Pure functions, no DB | none | yes |
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

The semantic and LLM tiers read live seed data. Their expected facts live in
`GROUND_TRUTH` at the top of `conftest.py` (tenants, call date, known people).
When you re-seed or add real tenants, update that one block and those tiers
follow.

Current seed under test (semantic / LLM tiers only):
- `green_path_recruiting` — Booking #1 Renata Voss (candidate), Booking #2 Walt
  Kessler (employer contact), both on 2026-07-09, both embedded.
- `other_firm_recruiting` — must not see either.

`test_tenant_isolation.py` does not use `GROUND_TRUTH`: each test creates its
own tenants, users, candidates and bookings (unique `test_*` slugs and
`@example.com` emails) inside a transaction that is rolled back at teardown.

## Notes

- Nothing in the suite commits to your database: the transactional tiers
  always roll back, the semantic / LLM tiers read live data read-only. If
  you'd rather isolate it, point `DATABASE_URL` at a copy before running.
- Names are matched in `Booking.employer_name` (that's where the instant-meeting
  flow stores the contact name).
- The isolation tests assert both directions — owning tenant sees its data,
  other tenant does not — so a leak or a hidden record both fail loudly.
