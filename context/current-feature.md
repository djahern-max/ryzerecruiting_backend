# Current Feature

<!-- Feature/fix name -->
Signup tenant resolution (candidate / employer)

## Status
<!-- Not Started | In Progress | Completed -->
In Progress

## Goals
<!-- Goals & requirements -->
Self-registering candidates and employers are created with `tenant_id = NULL`, which the
whole app treats as `ryze` (every read resolves tenant as `current_user.tenant_id or "ryze"`).
So a candidate who already has a firm-scoped profile — e.g. Renata Voss, whose `candidates`
row was created under `green_path_recruiting` by the booking flow — signs up via `/register`,
lands in `ryze`, and `_resolve_candidate_for_user` can never bridge her login to her profile.
She sees the generic "how the app works" dashboard instead of her own.

**The rule we want: stamp the tenant once, at account creation.**
- A candidate/employer belongs to whichever firm already has a profile for their email. If a
  firm profile exists → inherit that firm's `tenant_id`.
- No prior firm association → default to `ryze` (RYZE's own book; Dane reaches out manually).
  This is intended, not a fallback bug.
- Firms (ADMIN users) stay invite-only via `admin_invite.py` — unchanged.

**Non-goals (do not build these):**
- Not a marketplace. No cross-tenant candidate browsing.
- No auto-migration of a user between firms after signup. If a firm engages a candidate who
  already signed up cold in `ryze`, that reassignment is a future explicit recruiter action,
  not automatic.
- No schema change. `users.tenant_id` already exists. No Alembic migration.

**Root cause (confirmed):** user creation never sets `tenant_id`, in three places:
1. `AuthService.create_user` (password signup) — `app/services/auth.py`
2. `AuthService.get_or_create_oauth_user` (OAuth) — `app/services/auth.py`
3. Inline `User(...)` in the OAuth signup handler — `app/api/auth.py`

Paths 2 and 3 also duplicate OAuth user creation and have already drifted: the inline path
sets `first_login_at`, the service method does not.

## Plan
<!-- Ordered, minimal changes — audit first, do NOT write code until confirmed -->
1. **New helper** — `app/services/tenant_resolution.py`: `resolve_signup_tenant(db, email,
   user_type)`. Candidate → check `candidates.email` (case-insensitive); Employer → check
   `employer_profiles.primary_contact_email`; exactly one non-ryze firm match → that tenant;
   zero or multiple (ambiguous, logged as a warning) → `RYZE_TENANT`. Watch for a circular
   import between `deps.py` and this module — if `RYZE_TENANT` can't be imported cleanly,
   define it once and import in both, never hardcode `"ryze"` a second place.
2. **Password path** — `AuthService.create_user` computes `tenant_id =
   resolve_signup_tenant(...)` and passes it into `User(...)`.
3. **OAuth path** — preferred: consolidate the two OAuth creation sites into one
   (`get_or_create_oauth_user` becomes the single creation point, absorbs `first_login_at`
   and `resolve_signup_tenant(...)`; the inline branch in `app/api/auth.py` calls the service
   method instead of constructing `User(...)` itself). Preserve every field the inline path
   currently sets (`avatar_url`, `oauth_provider`, `oauth_provider_id`, `first_login_at`). If
   consolidation looks too invasive on inspection, fall back to applying
   `resolve_signup_tenant(...)` + `first_login_at` in both sites independently — state which
   route was taken and why.
4. **Backfill** — `backfill_signup_tenants.py` (repo root, pattern-matched on
   `backfill_summaries.py`): dry-run by default, `--commit` to write; explicit model-registration
   imports at top for FK resolution outside app context; own `SessionLocal`. Scope: `user_type
   in (CANDIDATE, EMPLOYER)` and `(tenant_id IS NULL OR tenant_id = 'ryze')` — never ADMIN/
   superusers. Print only rows that would change: `id | email | user_type | ryze/NULL ->
   <new_tenant>`, end with a count. Idempotent.
5. **Deterministic test** — `test_resolve_signup_tenant` in the fast pytest tier (no OpenAI/LLM
   calls, pure DB fixtures): single-firm match, no-match, multi-firm-ambiguous, employer path,
   ADMIN never resolves to a firm. Must run in the tier gated by the pre-push hook.

## Related Files
<!-- Files this touches -->
- `app/services/tenant_resolution.py` — new helper
- `app/services/auth.py` — `AuthService.create_user`, `AuthService.get_or_create_oauth_user`
- `app/api/auth.py` — inline OAuth signup handler
- `backfill_signup_tenants.py` — new backfill script (repo root)
- Test file for `test_resolve_signup_tenant` (deterministic tier — confirm location during audit)
- Read-only reference, do not change:
  - `app/core/deps.py` — `RYZE_TENANT`
  - `app/models/candidate.py`, `app/models/employer_profile.py`, `app/models/user.py`
  - `app/api/admin_invite.py` — firm invite flow, unchanged
  - `backfill_summaries.py` — pattern reference for the new backfill script

## Verification
<!-- How we'll know it worked -->
1. New candidate signs up with `renata.voss.design@gmail.com` on a fresh account →
   `users.tenant_id = green_path_recruiting`, and `/api/candidates/me` resolves her profile
   with no manual DB edit.
2. New candidate with an email that matches no profile → `users.tenant_id = ryze`.
3. Employer equivalent resolves via `employer_profiles`.
4. Firm invite flow (`/api/admin/invite`) still stamps the generated slug on the ADMIN user —
   unchanged.
5. `python backfill_signup_tenants.py` dry-run prints the would-be moves and writes nothing;
   `--commit` applies them; a second run prints zero changes.
6. Deterministic pytest tier passes (pre-push hook green).

## Notes
<!-- Any extra notes -->
- Multi-firm email is the one real edge: a single login can't point at two tenants. Defaulting
  to `ryze` + a warning is deliberate — auto-picking a firm silently is worse than leaving it
  for manual assignment. The tie-break is a product call, not a code default; revisit if it
  actually happens.
- No migration: `users.tenant_id` already exists and is nullable. Leave it nullable — `NULL`
  still means "ryze" for any legacy row.
- This closes the ghost-account gap for the daily cold Google signups too; they correctly stay
  `ryze` because they match no firm profile.
- Do not run migrations, restart services, or deploy — hand any such commands back to the user.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-15 — Task created. Issue found while recording the Renata Voss demo on
  `green_path_recruiting`. Her candidate profile was correctly tenant-scoped (booking flow),
  but her `/register` login landed in `ryze` (`users.id=5, tenant_id=ryze`) so the dashboard
  showed generic copy. Manually moved her user to `green_path_recruiting` → profile resolved
  and the dashboard/My Profile linked correctly, confirming the diagnosis. Root cause: user
  creation never stamps `tenant_id`. This task makes signup resolve the tenant from an existing
  firm profile, defaulting to `ryze`.
- 2026-07-15 — Audited the plan against the actual codebase before writing code. Found:
  `User.tenant_id` already has a column-level `default="ryze"` (not literal `NULL` as the spec's
  Purpose section assumed) — doesn't change the plan, just a factual correction. Confirmed a real
  circular-import risk between `app/core/deps.py` and a top-level `tenant_resolution` import in
  `app/services/auth.py` (`deps.py` imports `AuthService` before defining `RYZE_TENANT`).
  `backfill_summaries.py` (the spec's pattern reference) does not exist anywhere in this repo's
  history — `run_backfill.py` is the real precedent, and it has no dry-run/`--commit` gate to
  copy. Local dev DB has 0 seeded candidate rows, so `test_resolve_signup_tenant` can't be
  written read-only against ground truth the way `test_tenant_isolation.py` is. Presented these
  findings; user made the calls (lazy import over shared-constant, transactional-rollback test
  fixture over ground-truth reuse) in the next message rather than re-opening them.
- 2026-07-15 — Implemented all five pieces per the user's decisions:
  - `app/services/tenant_resolution.py` (new) — `resolve_signup_tenant()`, top-level
    `from app.core.deps import RYZE_TENANT`, no edits to `deps.py`.
  - `app/services/auth.py` — lazy (function-body) imports of `tenant_resolution` in
    `create_user` and `get_or_create_oauth_user` to dodge the deps↔auth cycle; both now stamp
    `tenant_id`; `get_or_create_oauth_user` also gained `first_login_at`.
  - `app/api/auth.py` — consolidated `complete_oauth_signup`'s inline `User(...)` creation
    branch to call `AuthService.get_or_create_oauth_user` instead (took the preferred
    consolidation route, not the inline-patch fallback — the "existing user by email" merge
    branch was untouched and semantically different, so only the new-user branch, which was
    already replicating a subset of the service method, was safe to converge).
  - `backfill_signup_tenants.py` (new, repo root) — dry-run by default, `--commit` to apply,
    modeled on `run_backfill.py`'s explicit-model-import shape with `argparse` added fresh.
  - `tests/test_signup_tenant_resolution.py` (new) — transactional `db` fixture (flush, never
    commit, rollback in teardown) covering all 5 cases from the spec. Had to additionally import
    `Booking` and `User` models (unused directly) so SQLAlchemy could resolve
    `Candidate.booking_id` / `Candidate.user_id` FK targets before insert — first run failed
    with `NoReferencedTableError` until those were added.
  Verified: app imports clean (96 routes), new test file passes 5/5 and leaves the DB exactly as
  found (rollback confirmed via row-count check), full deterministic pytest tier run shows only
  3 pre-existing failures in `test_tenant_isolation.py` unrelated to this change (that suite's
  ground truth depends on seeded data absent from this empty local DB), `audit_tenant_coverage.py`
  shows 0 HARDCODED and the same 2 pre-existing REVIEW items (`candidates.py` photo/banner,
  untouched by this work) as before. `backfill_signup_tenants.py` dry-run against local DB prints
  "0 user(s) would change" cleanly. Not yet committed or deployed — pending user review.
