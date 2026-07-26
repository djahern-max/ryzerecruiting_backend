# Feature 1 of 3 — Self-Serve Recruiter Signup + Demo Requests

**Date:** 2026-07-26 · **Go-live day, feature 1 of 3** (then: 2-demo-video, 3-usage-billing)
**To activate:** copy this file to `current-feature.md` in the repo root.
**Working style:** commit-sized steps, test + commit between each, update CHANGELOG.md, run `python audit_tenant_coverage.py` after any backend endpoint change.

## Objective
A recruiter landing on ryze.ai can, without any action from Dane: (a) sign up and get a working trial account immediately, or (b) request a demo, which notifies Dane by email. The existing superadmin invite flow stays intact as a third path.

## Current state (verified in repo)
- Onboarding is invite-only: `POST /api/admin/invite` (superadmin-gated, `app/api/admin_invite.py`) creates Tenant (status=trial, 30 days) + ADMIN User + fires a Resend welcome email containing a temp password.
- Public `/auth` only registers EMPLOYER/CANDIDATE users into the ryze tenant. There is no public path that creates a recruiting-firm tenant.
- Downstream trial machinery (402 in `deps.py`, AuthContext interceptor, UpgradePage, trial badge) is fully built and requires **zero changes** — self-serve users must simply come out shaped like invited users.

## Scope — IN

### Backend
1. **`POST /api/auth/signup-firm` (public).** Reuse the logic of `admin_invite.py` (slug generation, Tenant row status=trial 30 days, ADMIN user, `is_superuser=False`, `tenant_id=<new slug>`) with these differences:
   - Request body: company_name, full_name, email, password (user chooses; no temp password).
   - Response mirrors `/api/auth/login`: `access_token` + user, so the frontend logs them straight in.
   - Welcome email via Resend — new template variant of `send_welcome_invite_email` with **no password in it** ("your trial ends {date}, log in here").
   - Abuse guards: duplicate-email rejection (exists), per-IP rate limit (slowapi or a simple in-memory counter), hidden honeypot field rejected server-side.
2. **`POST /api/demo-request` (public).** Fields: name, company, email, phone (optional), message (optional).
   - New `demo_requests` table (model + Alembic migration — register the model in `alembic/env.py` or autogenerate won't see it). Store first, then email — the DB row is the lead record; email failure must not lose the lead.
   - Notification email to Dane via Resend.
   - Same rate-limit + honeypot guards.

### Frontend
3. **Recruiter signup page** (e.g. `/signup`): company name, full name, email, password + confirm → calls signup-firm → stores token → straight into `/admin` with trial badge showing. CSS Modules, controlled inputs with explicit handlers per project convention (no `<form>` submit pattern).
4. **Demo request form** — modal or small page reachable at `/demo`. Success state: "Thanks — we'll be in touch shortly."
5. **Minimal landing hookup:** two working links/buttons on the existing landing page to `/signup` and `/demo`. (The full hero redesign with the video and final CTA layout is Feature 2 — do not restyle the landing here, just make the routes reachable.)
6. **PostHog events:** `signup_started` (signup page submit), `signup_completed` (successful account creation), `demo_requested`.

## Scope — OUT
- Email verification links (fast follow — log as known gap in CHANGELOG).
- OAuth signup for firms (Google/LinkedIn stay employer/candidate-only).
- CAPTCHA (only if abuse appears).
- Any change to the superadmin invite flow.
- Landing page visual redesign (Feature 2).

## Decisions made
- Self-serve trial: **30 days, no card required** — same policy and code path as invited firms. Revisit if junk signups appear.

## Open questions for Dane (answer before starting)
- Demo-request notification address — dane@ryze.ai?
- Any extra signup fields (firm size, niche)? Recommendation: no — every field costs conversions; ask on the demo call instead.

## Acceptance criteria
- Incognito → ryze.ai → signup → lands in `/admin` with trial badge → PostHog shows `signup_completed` carrying the new tenant_id.
- Demo form → row in `demo_requests` → Dane receives the email.
- Existing invite flow still works (send one test invite).
- Duplicate email and honeypot submissions are rejected cleanly.
- `audit_tenant_coverage.py` shows no new REVIEW/HARDCODED lines.

## Session log
- 2026-07-26 — Backend-only session (items 1-2). Audit-first step done before writing code: read `admin_invite.py`, `auth.py`, `email.py`'s `send_welcome_invite_email`, `AuthService._auth_user_payload`, Tenant/User models. Confirmed `slowapi` isn't installed but `redis` already is (used for OAuth temp storage in `auth.py`) — proposed and confirmed a small Redis-backed fixed-window counter instead of either named option, since a bare in-memory counter resets per gunicorn worker process. Confirmed production sits behind nginx, so the rate limiter reads `X-Forwarded-For`'s first hop. Confirmed slug-generation + trial-window logic gets **duplicated** into the new endpoint rather than extracted into a shared helper, so `admin_invite.py` stays completely untouched per the Scope-OUT boundary. Confirmed split honeypot behavior: `/signup-firm` returns an explicit 400 (its real response is a token used to log the user in, which can't be faked, and autofill can trip it for real humans); `/demo-request` returns a silent fake-success (its response is just an ack). Confirmed `send_welcome_invite_email`'s hardcoded RYZE branding is correct as-is for this flow (RYZE onboarding a firm onto RYZE.ai, not a tenant emailing its own contacts) — the no-password variant follows the same pattern. Rate limits confirmed: 5/hour/IP signup, 10/hour/IP demo-request.
- 2026-07-26 — Commit 1 (`3f270dd`) — `POST /api/auth/signup-firm`: new `app/services/rate_limit.py` (Redis `INCR`+`EXPIRE` counter + `get_client_ip`), `SignupFirmRequest` schema added to `app/schemas/user.py`, endpoint + duplicated `_generate_firm_slug` helper added to `app/api/auth.py`, `send_self_serve_welcome_email` added to `app/services/email.py`, `"signup_firm"` added to `audit_tenant_coverage.py`'s `PUBLIC_PATTERNS`. App-import clean (99 routes, up from 98). `audit_tenant_coverage.py`: same 2 pre-existing unrelated `candidates.py` REVIEW lines, no new REVIEW/HARDCODED — `signup_firm` correctly classified PUBLIC.
- 2026-07-26 — Commit 2 (`2c63386`) — `POST /api/demo-request`: new `app/models/demo_request.py` (`DemoRequest`, no `tenant_id` — matches the `Waitlist` precedent, no tenant exists yet), `app/schemas/demo_request.py`, `app/api/demo_request.py` router (store-then-notify, notify via `get_branding(db, "ryze").admin_email` rather than a hardcoded address), `send_demo_request_notification` added to `email.py`, registered in `alembic/env.py`, migration `0224c07abf32` generated locally and round-tripped (upgrade → `\d demo_requests` confirmed schema → `downgrade -1` cleanly dropped → re-`upgrade head` cleanly restored) — chains off head `039ab00599f3`, not yet run anywhere else. Router wired into `main.py` alongside `waitlist_router`. `"create_demo_request"` added to `PUBLIC_PATTERNS`. App-import clean (100 routes). `audit_tenant_coverage.py`: same 2 pre-existing unrelated REVIEW lines, no new REVIEW/HARDCODED.

  Both commits pushed locally, not deployed. Frontend items 3-6 (signup page, demo form, landing hookup, PostHog events) explicitly out of scope for this session — belong to a separate frontend-repo session per the user's instruction. Deploy commands (stop `ryze-api`, `alembic upgrade head`, restart) to be handed over, not run here. Acceptance-criteria checklist (incognito walkthrough, PostHog events, invite-flow regression check, duplicate/honeypot rejection) can't be verified until the frontend session ships items 3-6.
