# Current Feature

Tenant restructure, part 3 of 3 — no unplaced users: registration is refused unless a firm already has the person; `users.tenant_id` NOT NULL

## Status
<!-- Not Started | In Progress | Completed -->
Not Started

## Goals
<!-- Goals & requirements -->
**Backend repo only.** No rebranding of display strings. No new invite feature
(see Notes). The frontend copy change that goes with this is listed under
"Frontend follow-up" and is done in the other repo afterwards.

Context: parts 1 and 2 (archived in CHANGELOG.md) removed the house tenant.
The last fallback is `app/services/tenant_resolution.py`: a self-registering
Employer or Candidate whose email matches no firm's `candidates` /
`employer_profiles` rows is stamped `_LEGACY_UNPLACED = "ryze"`, a slug with no
`tenants` row, and gets 403 everywhere. Decision (Dane, 2026-11-05): firms sign
up at `/signup` with a firm name; everyone else joins only through a firm that
already has them. There are no unplaced users.

How a user can be created after this task, and where their tenant comes from:
1. `POST /api/auth/signup-firm` — creates the tenant, user is its ADMIN. Already correct.
2. `POST /api/admin/invite-firm` (superuser) — same. Already correct.
3. `POST /api/auth/register` and `POST /api/auth/oauth/complete-signup`
   (Employer / Candidate self-registration) — **changed**: the resolver must
   return exactly one firm or the request is refused and no `users` row is
   written.
4. `scripts/create_superadmin.py` — `--tenant` required to exist (part 2). Correct.

Done means:
1. `resolve_signup_tenant(db, email, user_type)` returns a slug or raises
   `HTTPException`. No-match → **403** `detail="No recruiting firm has you on
   file yet. Ask your recruiter to add you, then register with the same
   email."` (exact text is Decision 2). Multi-match → see Decision 1. The
   `_LEGACY_UNPLACED` constant and every `"ryze"` literal are gone from the
   file. `grep -rn "RYZE_TENANT\|_LEGACY_UNPLACED\|\"ryze\"\|'ryze'" app/`
   returns nothing (Decision 4 — the remaining plain `ryze` hits in `app/`
   are URLs, `FROM_EMAIL`, email templates and CORS origins: rebrand task).
   ADMIN or an empty email reaching the resolver raise the same 403.
2. `AuthService.create_user` and `get_or_create_oauth_user`
   (`app/services/auth.py`) already call the resolver **before** constructing
   the `User` (audit 2026-11-05: nothing moves); once it raises, a refusal
   leaves no row behind by construction. For OAuth, the refusal must also
   clear the Redis temp token so the half-finished flow cannot be replayed —
   the service never sees the token, so the `/oauth/complete-signup` handler
   does the clearing.
3. `/register` already passes `HTTPException` through (`api/auth.py:79`).
   The handler that wraps everything in a 500 is `/oauth/complete-signup`
   (`api/auth.py:510`) — fix that one: catch `HTTPException` first, roll
   back, delete the temp token, re-raise, so the 403/409 and its detail reach
   the client.
4. New Alembic migration: `users.tenant_id` **NOT NULL**. Backfill first:
   `UPDATE users SET tenant_id = 'green_path_recruiting' WHERE tenant_id IS NULL`
   (zero rows locally; required for a restored dump). Downgrade relaxes the
   constraint. Model: `nullable=False`.
5. `require_tenant` in `deps.py` keeps its NULL branch (defensive; the column
   is NOT NULL but the helper is cheap) — add a comment saying so.
6. `tests/test_signup_tenant_resolution.py` rewritten: single-firm match →
   that slug; employer-profile match; admin never matched to a firm (existing
   cases, keep); **new**: no match → 403 and no `users` row; multi-match →
   Decision 1 behaviour; OAuth no-match → 403 and temp token deleted. Delete
   the `*_resolves_to_ryze` tests.
7. `backfill_signup_tenants.py` — its purpose was to move users out of `ryze`;
   after this task there is nothing to move. Delete it, or keep with a header
   saying it is a one-time historical script (Decision 3).
8. `pytest -m "not semantic"` → 0 failed. `audit_tenant_coverage.py` unchanged
   from the part-2 end state (0 HARDCODED, 0 REVIEW).

### Decisions to flag in the audit (do not pick — present options and wait)
**Decision 1 — email matches more than one firm.** Today: logged, dumped in
  `ryze`. Options:
  (a) Refuse with 409 `detail="More than one firm has this email on file.
      Contact your recruiter."` No account created. Simplest; a firm can fix
      its data and the person retries.
  (b) Create the account in the firm whose row is most recent.
      Guessing; wrong guess leaks a candidate into the wrong firm's book.
  (c) Return the list and let the user pick — needs a new endpoint and UI.
  Recommend (a). Record (c) as a possible later feature.

**Decision 2 — refusal detail strings.** Confirm the two messages above
  (no-match 403, multi-match 409) or supply wording. The frontend shows
  `detail` verbatim.

**Decision 3 — `backfill_signup_tenants.py`.** (a) delete; (b) keep with a
  historical header. Recommend (a): it references a slug that no longer exists
  and `CHANGELOG.md` records what it did.

## Related Files
- `app/services/tenant_resolution.py` — the rewrite
- `app/services/auth.py` — `create_user`, `get_or_create_oauth_user` (resolver
  call moves before `User(...)`; OAuth refusal clears temp token)
- `app/api/auth.py` — `/register` error handling; `/oauth/complete-signup`;
  `delete_oauth_temp_data`
- `app/models/user.py` — `tenant_id` nullable → False
- `alembic/versions/` — new migration
- `app/core/deps.py` — comment on `require_tenant`
- `tests/test_signup_tenant_resolution.py`, `tests/conftest.py`
- `backfill_signup_tenants.py`
- `CLAUDE.md` — "CRITICAL: multi-tenant isolation" section: after this task
  the rule can state "every user has a tenant; there is no fallback"; propose
  the edit (honesty rule)

## Verification
- [x] `python audit_tenant_coverage.py` BEFORE; output saved (`context/audit_baseline_part3.txt`: 95 endpoints, 76 Safe, 19 Public/Skip, 0 Hardcoded, 0 Review)
- [x] Decisions 1–4 presented with recommendations; answers recorded in Notes
- [ ] `grep -rn "RYZE_TENANT\|_LEGACY_UNPLACED\|\"ryze\"\|'ryze'" app/` → no output (Decision 4)
- [ ] Migration applied; `psql -d niceats -c "\d users"` shows `tenant_id ... not null`
- [ ] `alembic downgrade -1` then `upgrade head` round-trips
- [ ] `curl -X POST localhost:8000/api/auth/register` with an unknown email →
      403 with the agreed detail; `SELECT count(*) FROM users` unchanged
- [ ] Same email added as a candidate in green_path_recruiting via psql →
      register again → 201, user's `tenant_id = green_path_recruiting`
- [ ] Two firms with the same candidate email (psql) → register → 409 (if
      Decision 1a); no row written
- [ ] `pytest -m "not semantic"` → 0 failed
- [ ] `audit_tenant_coverage.py` AFTER: 0 HARDCODED, 0 REVIEW, Safe ≥ before
- [ ] `signup-firm` still creates a tenant and logs its ADMIN in (browser: /signup)
- [ ] Dane's login still works (browser)
- [ ] `CLAUDE.md` edit proposed and, on confirmation, committed separately
- [ ] Committed and pushed to `origin/main`; History updated

## Notes
- Platform: Nice ATS (niceats.com). Local DB `niceats`. No production server.
- **Decisions (2026-11-05):** 1 → (a) multi-match refused with 409, no row.
  2 → both strings as written; ADMIN and empty email reaching the resolver
  raise the same 403, no third message. 3 → (a) delete
  `backfill_signup_tenants.py`. 4 (new) → grep criterion amended to
  `grep -rn "RYZE_TENANT\|_LEGACY_UNPLACED\|\"ryze\"\|'ryze'" app/`; the
  stale `config.py:56` comment ("the `ryze` tenant is exempt") is fixed in
  commit 1. OAuth no-match test drives `/oauth/complete-signup` through the
  ASGI app with `app.api.auth.redis_client` replaced by a dict-backed fake.
- **Possible later feature (Decision 1c):** when one email matches several
  firms, return the list and let the person pick — needs a new endpoint and
  UI. Not built here.
- **No invite feature in this task.** A firm-level "invite a candidate / employer
  by link" flow (token carries the tenant; registration consumes it) is the
  natural next feature if firms find "add them to your pipeline first" too
  indirect. Record it as a candidate task; do not build it here.
- `users.invited_at` / `invited_by` columns exist (migration e00a9314318b) and
  would support that feature.
- **Frontend follow-up (other repo, after this lands):** `Auth.jsx` and
  `CompleteOAuthSignup.jsx` must render the 403/409 `detail` string from
  `/register` and `/oauth/complete-signup` in the existing error area, and
  the Employer/Candidate chooser should carry one line of copy: "Registration
  is for people a recruiting firm has already added. Running a firm? Start at
  /signup." Confirm the existing `error` state in `Auth.jsx` shows
  `detail` rather than a generic message.
- `chat_sessions` / `chat_messages` still have no `tenant_id` (scoped via the
  owning user, which now always has one). Decide after the restructure whether
  to add the column; not blocking.
- After this task the restructure is complete. Next: codebase audit brief
  (report only), then the rebrand tasks.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-11-05 — Task drafted (Claude, chat) from a read-only inspection of
  `tenant_resolution.py`, `services/auth.py`, `api/auth.py`, `admin_invite.py`
  and the frontend routes. No code changed.
- 2026-11-05 — Pre-change audit (Claude Code): baseline saved
  (95 / 76 Safe / 0 / 0, identical to part-2 end state). Confirmed: resolver
  already runs before `User(...)` in both service methods; `/register`
  passes `HTTPException` through, `/oauth/complete-signup` is the handler
  that swallows into a 500 and leaves the Redis temp token behind;
  `grep -rn "ryze" app/` can't reach zero inside scope (17 URL/template/
  config hits — rebrand task); every `User(...)` constructor in the repo
  passes `tenant_id`; zero NULL `users.tenant_id` locally. Decisions 1–4
  answered by Dane (see Notes). No code changed.
