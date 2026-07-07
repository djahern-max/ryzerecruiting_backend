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
- `app/api/` — route handlers, one file per resource (`bookings.py`, `candidates.py`, `employer_profiles.py`, `job_orders.py`, `chat.py`, `webhooks.py`, etc.)
- `app/models/` — SQLAlchemy models
- `app/core/` — `config.py`, `database.py`, auth/tenant dependencies
- `app/services/` — external integrations (e.g. `spaces.py` for DO Spaces)
- `alembic/` — migrations; `env.py` imports every model explicitly — new models must be added there or Alembic won't detect them
- `audit_tenant_coverage.py` — static analysis script that walks `app/api/` and flags endpoints missing tenant scoping (SAFE / HARDCODED / REVIEW / PUBLIC / SKIP). Run this after any change touching auth or queries.

## CRITICAL: multi-tenant isolation
This is the single most important rule in this codebase. RYZE Recruiting is tenant #1, but the platform is being licensed to other firms, so **every query on tenant-owned data must be scoped by `tenant_id`.**

- Use `get_current_tenant` / `get_current_admin_tenant` or `current_user.tenant_id` — never a hardcoded `RYZE_TENANT` constant for anything but genuinely RYZE-specific defaults.
- `chat_sessions` and `chat_messages` were previously found unscoped — treat any table without an obvious `tenant_id` filter as suspect until proven otherwise.
- Known hardcoded-branding files that still need consolidation onto a per-tenant resolver: `notifications.py`, `ai_brief.py`, `calendar.py`, and the PDF footer templates. A `TenantBranding` dataclass / `get_branding(tenant_id, db)` resolver in `app/core/tenant_branding.py` is the intended fix — check its current state before assuming it's done.
- Run `python audit_tenant_coverage.py` after touching any endpoint and paste me the new `REVIEW`/`HARDCODED` lines rather than assuming a fix worked.

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
- **Resend** only sends from the verified `ryze.ai` domain — `from_email` stays fixed, vary `reply_to` and display name instead.
- CORS errors in the browser console almost always mean a server-side 500 — check `journalctl -u ryze-api`, not devtools, first.
- `SKIP_FILES` in `audit_tenant_coverage.py` (webhooks, blog, contact, ai_parser) are intentionally public/infrastructure — don't try to tenant-scope them.

## How I want you to work
- **Audit before you refactor.** For anything beyond a one-line fix: read the relevant files, list what you'd change and why, and don't write code until I confirm.
- **One concern per change.** Don't bundle a tenant-scoping fix with a style cleanup with a rename — separate asks, separate diffs.
- I prefer **complete drop-in replacement files** for anything that's gotten complex, rather than partial diffs — I'll say so when I want that.
- Narrow, clearly-scoped surgical edits are fine without asking.
- Don't invent new abstractions or rename public APIs/endpoints unless I asked for that specifically.

## Session workflow — context/current-feature.md
At the start of every session, read `context/current-feature.md` — it holds the active task's Status, Goals, Related Files, and Verification steps. Work from it, don't start unrelated work without checking it first.

- When you finish a meaningful chunk of work, add a dated line to its History section — earliest to latest.
- When a task is fully done and verified, tell me — I'll move it to `context/CHANGELOG.md` and reset `current-feature.md` for the next task. Don't do that move yourself; flag it and wait for confirmation.
- If I ask you to start something not reflected in `current-feature.md`, ask whether to update the file first before writing code, rather than silently working off-script.
