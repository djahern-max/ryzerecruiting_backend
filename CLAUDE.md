# RYZE.ai Backend — CLAUDE.md

## What this is
FastAPI backend for RYZE.ai V2 — a multi-tenant ATS for recruiting firms. RYZE Recruiting (accounting/finance recruiting, New England-based) is the first live tenant and proof-of-concept.

## Stack
- **Framework:** FastAPI, routers included in `app/main.py`
- **DB:** PostgreSQL + pgvector, SQLAlchemy models in `app/models/`, Alembic migrations in `alembic/`
- **Auth:** Bearer token (JWT), `Authorization: Bearer <token>` header — not cookie-based
- **AI:** Anthropic Claude for generation/chat/briefs; OpenAI `text-embedding-3-small` for embeddings only — never use OpenAI for generation or Claude for embeddings
- **Integrations:** Zoom API + webhooks (meeting summaries, transcripts), Google Calendar API, Resend (email), Twilio (SMS, A2P 10DLC in progress), Stripe (billing), DigitalOcean Spaces via boto3 (file storage)
- **Scheduling:** APScheduler as a systemd service

## Repo layout
- `app/api/` — route handlers, one file per resource (`bookings.py`, `candidates.py`, `employer_profiles.py`, `job_orders.py`, `chat.py`, `webhooks.py`, `settings.py`, etc.)
- `app/models/` — SQLAlchemy models
- `app/core/` — `config.py`, `database.py`, auth/tenant dependencies
- `app/services/` — external integrations and shared services (`spaces.py` for DO Spaces, `branding.py` for tenant branding resolution, `notifications.py`, `email.py`)
- `alembic/` — migrations; `env.py` imports every model explicitly — new models must be added there or Alembic won't detect them
- `audit_tenant_coverage.py` — static analysis script that walks `app/api/` and flags endpoints missing tenant scoping (SAFE / HARDCODED / REVIEW / PUBLIC / SKIP). Run this after any change touching auth or queries.

## CRITICAL: multi-tenant isolation
This is the single most important rule in this codebase. RYZE Recruiting is tenant #1, but the platform is being licensed to other firms, so **every query on tenant-owned data must be scoped by `tenant_id`.**

- Use `get_current_tenant` / `get_current_admin_tenant` or `current_user.tenant_id` — never a hardcoded `RYZE_TENANT` constant for anything but genuinely RYZE-specific defaults.
- `chat_sessions` and `chat_messages` were previously found unscoped — treat any table without an obvious `tenant_id` filter as suspect until proven otherwise.
- Run `python audit_tenant_coverage.py` after touching any endpoint and paste me the new `REVIEW`/`HARDCODED` lines rather than assuming a fix worked.

## Tenant branding — resolver EXISTS, use it
The per-tenant branding resolver is **implemented** at `app/services/branding.py` — do not re-implement it or go looking for `app/core/tenant_branding.py` (an older doc referenced that path; it never existed).

- `get_branding(db, tenant_id)` returns a frozen `TenantBranding` dataclass. **Every field falls back individually to RYZE's global defaults** (`app.core.config.settings`), so a tenant with all-NULL override columns behaves exactly like RYZE. It is safe to call with `db=None` or an unknown tenant — you get RYZE defaults.
- Already migrated onto the resolver: `app/services/notifications.py` (all notify functions take `tenant_id` + `db` and resolve branding) and `app/services/email.py` (all senders take a `branding` parameter). Admins can override whitelisted branding fields via `GET/PATCH /api/settings/tenant` in `app/api/settings.py`.
- **Still hardcoded — remaining migration targets:** the PDF templates (`candidate_pdf_template.py`, `employer_pdf_template.py`, `job_order_pdf_template.py`) bake `RYZE.ai` / `RYZE.AI` into their footers. Verify `ai_brief.py` and `calendar.py` before assuming either way.
- **Known risk:** the notify functions default to `tenant_id="ryze"`. A call site that forgets to pass `tenant_id` silently sends RYZE-branded messages for another firm's data. When adding or touching a notify call site, always pass the real `tenant_id` and `db` explicitly. (Making the param required is a queued hardening task for before tenant #2 onboards.)
- **Secret handling:** `tenant.twilio_auth_token` is a credential-column stub for a future per-number model. Do NOT populate it in production until it's encrypted at rest. In the shared-sender model, tenants leave `twilio_*` NULL and ride on RYZE's number.
- **Resend:** `from_email` must be a Resend-verified domain. Until a firm verifies its own domain, leave its `from_email` NULL — mail sends from RYZE's verified address with the firm's display name and the firm's `reply_to`.

## Deploy & migration workflow — do NOT run these yourself
Production is a DigitalOcean droplet (167.71.93.90, user `dane`). The actual deploy always happens manually:

```
# local
git push

# on server
git pull
sudo systemctl stop ryze-api      # required before any Alembic migration
alembic upgrade head              # only run migrations on the server, never generate them there
sudo systemctl start ryze-api     # or restart
```

- **Always generate migrations locally** (`alembic revision --autogenerate`) and commit them — the server only ever runs `alembic upgrade head`.
- **Always stop `ryze-api` before a migration** — gunicorn connections hold locks that block `ALTER TABLE`.
- When giving me instructions that touch the server, give me the exact commands to run — don't execute deploy/migration commands yourself.
- Prefer `DELETE` over `TRUNCATE` on live tables — `TRUNCATE` needs an `ACCESS EXCLUSIVE` lock, `DELETE` only needs `ROW EXCLUSIVE`.

## Conventions
- **Route ordering matters:** static routes like `/me` must be declared before `/{id}` routes in the same router, or FastAPI treats `me` as a path param.
- **Resend** only sends from the verified `ryze.ai` domain — `from_email` stays fixed, vary `reply_to` and display name instead (see Tenant branding above).
- CORS errors in the browser console almost always mean a server-side 500 — check `journalctl -u ryze-api`, not devtools, first.
- `SKIP_FILES` in `audit_tenant_coverage.py` (webhooks, blog, contact, ai_parser) are intentionally public/infrastructure — don't try to tenant-scope them.
- **PDF generation:** Playwright (`sync_playwright`) must run in plain `def` endpoints (not `async def`) so FastAPI executes it in a thread pool; use `wait_until="networkidle"` so Google Fonts load.

## How I want you to work
- **Audit before you refactor.** For anything beyond a one-line fix: read the relevant files, list what you'd change and why, and don't write code until I confirm.
- **One concern per change.** Don't bundle a tenant-scoping fix with a style cleanup with a rename — separate asks, separate diffs.
- I prefer **complete drop-in replacement files** for anything that's gotten complex, rather than partial diffs — I'll say so when I want that.
- Narrow, clearly-scoped surgical edits are fine without asking.
- Don't invent new abstractions or rename public APIs/endpoints unless I asked for that specifically.

## Session workflow — context/current-feature.md
At the start of every session, read `context/current-feature.md` — it holds the active task's Status, Goals, Related Files, and Verification steps. Work from it, don't start unrelated work without checking it first.

- When you finish a meaningful chunk of work, add a dated line to its History section — earliest to latest.
- When a task is fully done and verified, tell me first and wait for my explicit confirmation. **Once I confirm**, archive it yourself: copy its final Goals summary + full History into `context/CHANGELOG.md` as a new entry at the **top**, matching the format of the existing entries, then reset `current-feature.md` — to the blank template, or to the next task's content if I've handed it to you in the same message. **Never archive unprompted or before I confirm.** The confirmation is the gate; nothing moves until I say the word.
- **Blank is a valid resting state.** Resetting `current-feature.md` to the blank template with *no* new task loaded is a normal close-out — Part 1 of a two-part swap (`context/session-opener.md`, Case A-close), not a sign the task was abandoned or that you should infer the next one. The next task may arrive in a later message; when it does, I'll place it in the file and point you at it (Case B). An empty `current-feature.md` is never license to start unrelated work — wait for the next task.
- If I ask you to start something not reflected in `current-feature.md`, ask whether to update the file first before writing code, rather than silently working off-script.
- **Keep this file honest:** when completed work makes any section of this CLAUDE.md inaccurate (a file moved, a "still needs X" item got done, a convention changed), flag it and propose the CLAUDE.md edit in the same session. Stale instructions here mislead every future session.
