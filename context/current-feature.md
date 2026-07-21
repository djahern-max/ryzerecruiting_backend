# current-feature.md

## Feature: Candidate "I'm Interested" — quick email note to recruiter (backend)

**Status:** Not Started
**Repo:** ryzerecruiting_backend
**Depends on:** Nothing new. Uses existing Resend + `get_branding()` (app/services/branding.py) and the `_resolve_candidate_for_user` pattern in app/api/candidates.py.

### Goal
Let an authenticated candidate express interest in an open job order with one
click plus an optional short note. The firm's recruiter (branding.admin_email
for the candidate's tenant) receives a branded Resend email with reply_to set
to the candidate's own email so they can reply directly. Email only — NO SMS
(Twilio A2P still pending approval; do not touch notifications SMS paths).

Three concerns, three commits. Audited 2026-07-21 — plan confirmed with
adjustments (see History). Email fires SYNCHRONOUSLY in the request (not
BackgroundTasks) — matches every existing `notify_*` call in this codebase
(bookings.py); only slow AI calls (embeddings, briefs) use BackgroundTasks
here. Commit order is model→email→endpoints so every commit is runnable
standalone.

### Concern 1 — model + migration → commit 1
New `app/models/job_interest.py`:
- `JobInterest`: id, tenant_id (String(100), default RYZE_TENANT, indexed),
  job_order_id FK → job_orders, candidate_id FK → candidates,
  note (Text, nullable), created_at (default=datetime.utcnow, matching
  job_order.py's style, not server_default=func.now()).
- `UniqueConstraint("job_order_id", "candidate_id")` — one interest per
  candidate per role, dedupe at the DB level.
- Add the model import to `alembic/env.py` or autogenerate won't see it.
- Migration commands come to me — remember to stop `ryze-api` first.

### Concern 2 — email → commit 2
New function in `app/services/email.py` following the
`send_admin_notification` pattern:
- `send_candidate_interest_notification(candidate_name, candidate_email,
  candidate_title, job_title, job_location, note, branding)`.
- `to: [branding.admin_email]`, `reply_to: candidate_email` (so the recruiter
  hits reply and talks to the candidate directly).
- Subject: `Candidate Interest — {candidate_name} → {job_title}`.
- HTML-escape the candidate note before interpolating into the email body.
- Wrapper `notify_candidate_interest(...)` in `app/services/notifications.py`
  (email-only, no `_send_sms` call) that resolves `get_branding(db,
  tenant_id)`. Inert but importable — nothing calls it yet in this commit.

### Concern 3 — endpoints → commit 3
In `app/api/job_orders.py`:
- `POST /api/job-orders/{job_order_id}/express-interest` —
  auth via `get_any_authenticated_user`, imported with the EXACT line
  candidates.py uses (`from app.api.auth import get_current_user as
  get_any_authenticated_user`) — confirmed this is a distinct function
  object from the `app.core.deps.get_current_user` job_orders.py already
  imports for `/open` and `/candidate-matches`; add the new import
  alongside, don't touch the existing one.
  Resolve candidate via `_resolve_candidate_for_user`, imported from
  `app.api.candidates` (confirmed no circular import: candidates.py only
  imports the JobOrder model/schema, never the job_orders router module).
  404 if no candidate profile.
  Job lookup MUST filter `tenant_id == current_user.tenant_id or "ryze"`
  AND `status == "open"` — the tenant filter is the isolation guarantee.
  Pre-check 409 if a JobInterest already exists for (job, candidate), AND
  wrap the create+commit in try/except IntegrityError → rollback → 409, so
  a double-click race on the unique constraint still returns 409, not 500.
  Payload: `{ note: Optional[str] }`, max_length=500 via Pydantic
  (`app/schemas/job_interest.py`: JobInterestCreate, JobInterestResponse).
  On success: persist JobInterest, call `notify_candidate_interest(...)`
  synchronously (request's db session), return 201.
In `app/api/candidates.py`:
- `GET /api/candidates/me/interests` → list of `{ job_order_id, created_at }`
  for the resolved candidate (frontend uses this to render "Interest sent"
  state on load). Declare in the /me block, before `/{id}` routes per the
  route-ordering rule.
Run `python audit_tenant_coverage.py` after — paste me any new
REVIEW/HARDCODED lines.

### Explicitly OUT of scope
- SMS (Twilio pending).
- Any admin UI for viewing interests — the email + DB rows are enough for now.
- Employer-facing anything. Candidate contact info must not leak toward
  employers; this email goes to the firm's admin_email only.
- Rate limiting beyond the unique constraint.

## Verification
1. `python audit_tenant_coverage.py` — no new REVIEW/HARDCODED lines.
2. As Renata (tenant green_path_recruiting): POST express-interest on the
   Greenscene job → 201, JobInterest row has tenant_id
   'green_path_recruiting', email arrives at Green Path's admin_email
   (NOT RYZE's) with reply_to = Renata's email.
3. Second POST on the same job → 409.
4. POST against a job order belonging to a different tenant → 404.
5. GET /api/candidates/me/interests returns the Greenscene job_order_id.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-21: Audited plan against the actual codebase before writing code.
  Confirmed `_resolve_candidate_for_user` is safely importable from
  `app.api.candidates` into `app.api.job_orders` (no circular import —
  candidates.py never imports the job_orders router module). Confirmed
  candidates.py's `get_any_authenticated_user` is `app.api.auth.get_current_user`
  under an alias, a distinct function object from the
  `app.core.deps.get_current_user` job_orders.py already imports — the new
  endpoint needs its own mirrored import, not reuse of the existing one.
  Found the codebase's actual email-dispatch convention diverges from the
  original spec: every existing `notify_*` call (bookings.py) fires
  synchronously in-request; only slow AI calls (embeddings, AI briefs) use
  BackgroundTasks. User confirmed: go synchronous, not BackgroundTasks.
  User also reordered commits (model → email → endpoints, so each commit is
  independently runnable), fixed `created_at` to `default=datetime.utcnow`
  (matching job_order.py's style instead of `server_default=func.now()`),
  and added an IntegrityError→409 fallback around the create/commit for the
  double-click race, on top of the pre-check.
