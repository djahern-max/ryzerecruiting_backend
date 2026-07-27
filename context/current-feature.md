# Current Feature — AI Usage Metering, Internal Budget Cap, $20 Plan, Stripe Go-Live

**Date:** 2026-07-27 · Supersedes the earlier draft "feature-3-usage-billing.md"
**Repo:** ryzerecruiting_backend — BACKEND ONLY (frontend has its own companion file)
**To activate:** copy this file to `current-feature.md` in the repo root.
**Working style:** commit-sized steps, test + commit between each, update CHANGELOG.md, run `python audit_tenant_coverage.py` after any endpoint change.

## Objective
Every AI call is metered with real token counts and cost. The subscription price becomes
$20/month. Separately from the price, each tenant gets an **internal AI cost budget**
(env-configurable, default $8.00/month of real API spend) — the price is revenue, the
budget is COGS; they are intentionally not the same number. When a tenant exceeds the
budget, **AI endpoints only** return a friendly limit message; the rest of the app keeps
working. Usage in dollars is visible to the superadmin only — tenants see nothing in v1.
Stripe goes from test to live mode with the new $20 price.

## Design decisions (locked — do not relitigate mid-build)
- **Budget ≠ price.** `AI_MONTHLY_BUDGET_USD` env var, default `8.00`. The $20 price is
  just a new Stripe Price ID. If real data says the budget is wrong, we change the env var.
- **Cap blocks AI only, never data.** Do NOT reuse the 402 machinery in `deps.py` — the
  frontend's global axios interceptor redirects every 402 to `/upgrade`, which would
  bounce a *paying* customer to the upgrade wall. The cap returns **429** with
  `detail={"code": "ai_usage_limit", "message": "..."}` so the frontend can distinguish it.
- **The `ryze` tenant is exempt from the cap** (mirrors its existing billing bypass) but
  its usage IS still recorded — Dane needs to see his own burn.
- **Metering must never break a user request.** All recording wrapped in try/except.
- **Month boundary = calendar month UTC** for v1. Subscription-anchor months are Phase 2.
- **Tenant-facing meters, $5 top-ups, and overage billing are explicit fast follows** —
  see Scope OUT.

## Current state (verified in repo)
- Stripe subscription flow end-to-end in `app/api/billing.py`: Checkout on
  `STRIPE_PRICE_ID`, webhook activates tenant, 402 enforcement in `deps.py`. Still in
  test mode. No paying customers → price change is just a new Price ID, no migration.
- **No usage tracking exists anywhere.** AI call sites to instrument:
  - `app/api/chat.py` — tool-loop `client.messages.create` calls AND the final
    `client.messages.stream` answer
  - `app/api/chat_sessions.py` — generate-title
  - `app/api/webhooks.py` — `_generate_summary_from_transcript` (Anthropic call in a
    background task with its own `SessionLocal`)
  - brief / profile AI generation services
  - `app/services/embedding_service.py` — OpenAI embeddings
- **Live data now.** Two real tenants: `ryze` and `egyptian_global` (self-serve signup
  works). No destructive testing against `egyptian_global`.

## Scope — IN

### Step 1 — `usage_events` table
Model + Alembic migration; register in `alembic/env.py`.
Columns: id, tenant_id, user_id (nullable — some calls are system/background),
ts (UTC), provider (`anthropic`|`openai`), model, input_tokens, output_tokens,
cost_usd (Numeric(10,6), computed at write time), source
(`chat`|`chat_final`|`title`|`summary`|`brief`|`profile_ai`|`embedding`|…).
Index on (tenant_id, ts).

### Step 2 — `app/services/usage.py`
- `PRICING` dict — per-MTok input/output rates for `claude-sonnet-4-6` and
  `text-embedding-3-small`. **Verify current rates from the providers' pricing pages at
  implementation time; do not trust memorized numbers.** Unknown model → log warning,
  record tokens with cost 0 (never crash the calling request).
- `record_usage(db, tenant_id, user_id, provider, model, input_tokens, output_tokens, source)`
  — the single choke point; call sites never compute cost inline. Wrapped in try/except.
- `get_month_cost(db, tenant_id) -> Decimal` — indexed sum of cost_usd for the current
  UTC calendar month. This backs both the cap check and the usage endpoint.
- `check_ai_budget(db, tenant_id) -> None` — raises
  `HTTPException(429, detail={"code": "ai_usage_limit", "message": "You've reached this
  month's AI usage limit. It resets on the 1st."})` when
  `get_month_cost >= AI_MONTHLY_BUDGET_USD`. `ryze` tenant returns immediately.

### Step 3 — Instrument every call site
- Anthropic non-streaming: `response.usage.input_tokens / output_tokens` (available on
  every tool-loop iteration — record each one, source=`chat`).
- Anthropic streaming final answer: after the text loop, read
  `stream.get_final_message().usage` inside the `with` block, source=`chat_final`.
- OpenAI embeddings: `response.usage.total_tokens` → record as input_tokens, output 0.
- Background summary task in webhooks.py uses its own db session — pass it through.

### Step 4 — Enforce the cap on AI endpoints only
- `POST /api/chat` — call `check_ai_budget` **in the endpoint, before returning the
  StreamingResponse** (a 429 cannot be raised mid-stream).
- generate-title, brief/profile generation endpoints — same check at the top.
- Do NOT gate embeddings triggered by data writes (e.g. candidate re-embeds) — blocking
  those would silently corrupt search. They're small; they stay unmetered-but-recorded.
- Do NOT touch `deps.py` / `get_current_tenant`.

### Step 5 — Usage endpoints
- `GET /api/billing/usage` (superuser only): per-tenant breakdown for the current month —
  tenant slug, summed cost_usd, budget, percent, event count — plus a grand total. This
  is Dane's cost dashboard feed. Cross-tenant by design; guard with
  `get_current_superuser`, and document the exemption for `audit_tenant_coverage.py`.
- No tenant-facing usage endpoint in v1.

### Step 6 — Stripe test → live
1. Create the $20/mo Price in the dashboard — **test mode AND live mode separately**
   (test prices don't carry over).
2. Verify in test mode first: checkout on the new test $20 price → webhook → tenant
   activated. Use a throwaway tenant with `trial_ends_at` set into the past via SQL —
   never `egyptian_global`.
3. Flip env to live: live secret key, live publishable key (frontend env), live
   `STRIPE_PRICE_ID`, and a **newly registered live-mode webhook endpoint with its own
   `STRIPE_WEBHOOK_SECRET`** — the classic go-live failure is a completed live checkout
   whose webhook never activates the tenant because the live signing secret wasn't set.
4. Make one real $20 purchase yourself, confirm activation end-to-end, then refund it
   in the Stripe dashboard.
5. Set spend alerts/limits in the Anthropic and OpenAI consoles as the backstop of last
   resort.

## Scope — OUT (explicit fast follows, do NOT build today)
- Tenant-facing usage meter (if ever shown, it will be a percentage or "credits" — never
  raw dollar COGS, which leaks margin and implies they bought $20 of AI).
- $5 top-ups: Stripe Checkout `mode="payment"`, webhook credits a credit ledger table,
  effective limit = budget + credits, credits roll over. Build only if real users
  actually hit the cap.
- Automated overage billing / metered Stripe prices.
- Per-user usage breakdown UI; model toggle (Sonnet ↔ Haiku).
- Subscription-anchor billing months.

## Acceptance criteria
- 3 chat messages → ≥ 3 `usage_events` rows (tool-loop rows + chat_final rows) with
  plausible token counts, nonzero cost_usd, correct tenant_id.
- Title generation, a transcript summary, and an embedding call also produce rows.
- `GET /api/billing/usage` as superuser: sums hand-check against raw rows; a non-superuser
  gets 403.
- Temporarily set `AI_MONTHLY_BUDGET_USD=0.01` for a test tenant's session → chat returns
  429 with code `ai_usage_limit`; candidate/employer/job-order endpoints still return 200.
  The `ryze` tenant is never capped.
- A deliberately broken PRICING entry does not break chat (row logged at cost 0, warning
  in logs).
- Live-mode: real $20 checkout activates the tenant via webhook; charge refunded.
- `audit_tenant_coverage.py` clean (with the documented superuser exemption).

## Session log
- 2026-07-27: Implemented Steps 1-5 (backend usage metering + budget cap), commit-sized,
  tested manually between each:
  - `usage_events` table (model + migration, registered in `alembic/env.py`).
  - `app/services/usage.py`: `record_usage` (never raises), `get_month_cost`,
    `is_over_budget` (ryze always exempt), `check_ai_budget` (raises 429
    `{"code": "ai_usage_limit", ...}`). Unknown-model pricing logs a warning and
    records cost 0 without crashing. Pricing verified at implementation time:
    Sonnet 4.6 $3/$15 per MTok, Haiku 4.5 $1/$5 per MTok, text-embedding-3-small
    $0.02/MTok.
  - `generate_embedding` extended with optional `db`/`tenant_id`/`source` kwargs;
    wired into all ~9 embedding call sites (chat RAG, search, candidate embed,
    5 background helpers + batch sync) — record-only, never budget-gated per design
    (embeddings tied to data writes must never be blocked).
  - All Anthropic call sites instrumented: `chat.py` (tool-loop + final streamed
    answer, budget-gated pre-stream in the endpoint), `chat_sessions.py`
    generate-title, `webhooks.py` transcript summary (BackgroundTask — soft-skip via
    `is_over_budget` since a raise has no HTTP caller to catch it), `ai_brief.py` +
    `bookings.py::_generate_brief_background` (same soft-skip pattern), `ai_parser.py`
    + its 4 endpoint callers in candidates.py/job_orders.py/employer_profiles.py
    (budget-gated, `db`/tenant added to 2 endpoints that previously had neither).
  - `GET /api/billing/usage` (superuser-only, cross-tenant cost breakdown for the
    current UTC month) — follows the `db_explorer.py` precedent (`_tenant()` helper
    call + prose comment) so `audit_tenant_coverage.py` reports it SAFE rather than
    REVIEW.
  - Every call site verified manually against the local dev DB (not just unit
    tests): usage rows recorded with correct tenant/model/cost, 429 fires for an
    over-budget non-`ryze` tenant while `ryze` stays exempt, soft-skip paths skip
    the Claude call entirely with no usage row and no side effects.
  - `python audit_tenant_coverage.py`: 95 endpoints scanned, 0 hardcoded, 0 review —
    clean, including the new `/usage` endpoint and the 4 newly-`db`-wired parse
    endpoints.
  - Pre-existing test failures confirmed unrelated (seed-data drift in the local
    dev DB — `bookings`/`candidates` tables are empty locally — identical failures
    before and after this branch's changes): `test_meeting_notes_semantic_search_finds_seeded_calls`,
    `test_owning_tenant_sees_its_calls_by_date`, `test_owning_tenant_finds_candidate_calls`,
    `test_candidate_tool_boundary_excludes_employer_contacts`.
  - Not started: Step 6 (Stripe test → live) is ops/account configuration per
    CLAUDE.md's deploy workflow — instructions handed to Dane rather than executed.
