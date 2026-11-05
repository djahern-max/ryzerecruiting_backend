# Current Feature

Tenant restructure, part 1 of 3 — schema: `tenant_id` NOT NULL everywhere, `tenants.billing_exempt` (first step of removing the house tenant)

## Status
<!-- Not Started | In Progress | Completed -->
In Progress

## Goals
<!-- Goals & requirements -->
**Backend repo only. Schema and models only.** Do not remove `RYZE_TENANT` or
rewrite any `or RYZE_TENANT` call site in this task — that is part 2. Do not
touch the signup resolver (`app/services/tenant_resolution.py`) — that is part 3.
No rebranding.

Context: the platform (Nice ATS, formerly RYZE.ai) currently has a "house tenant"
with slug `ryze` that is simultaneously the first customer and the platform itself.
`RYZE_TENANT` does five jobs: NULL fallback for `tenant_id`, billing/usage
exemption, branding default, signup lost-and-found, and the superuser check in
`db_explorer.py`. The three-part restructure makes all tenants peers and moves
platform behaviour onto explicit columns and user flags. This part lays the
schema groundwork so that part 2 can delete the fallbacks as dead code.

Done means:
1. A new Alembic migration (generated locally, `alembic revision --autogenerate`
   plus hand-written backfill) that, in this order:
   a. Backfills `tenant_id = 'ryze'` where NULL on `candidates`, `bookings`,
      `employer_profiles`, `job_orders`, `job_interests` (zero rows locally; the
      migration must still be correct for a restored prod dump).
   b. Sets `tenant_id` NOT NULL on those five tables.
   c. Adds `tenants.billing_exempt BOOLEAN NOT NULL DEFAULT false`
      (`server_default=sa.text("false")`, matching the `sms_consent` precedent).
   d. Downgrade reverses all three.
   See Decision 1 for `users.tenant_id`.
2. Models updated to match: `nullable=False` on the five columns above; the
   `default="ryze"` / `default=RYZE_TENANT` arguments removed from
   `employer_profile.py`, `job_order.py`, `job_interest.py` (and `user.py` if
   Decision 1 → a). A row with no tenant must now fail at insert, not silently
   land in `ryze`. The module-level `RYZE_TENANT = "ryze"` constants in
   `job_order.py` and `job_interest.py` are deleted (they exist only for the
   defaults); `deps.py` and `branding.py` keep theirs until part 2. The one
   external importer, `seed_landscaping_jobs.py` line 49, is repointed at
   `app.core.deps` in the same commit (one line, no behaviour change).
3. `Tenant` model gains `billing_exempt = Column(Boolean, nullable=False,
   default=False, server_default="false")` — both defaults, like `sms_consent`
   in `booking.py`, so raw-SQL inserts from seed scripts and psql keep working.
4. `alembic upgrade head` from scratch succeeds; `alembic check` reports nothing;
   `alembic downgrade -1` then `upgrade head` round-trips.
5. The existing test suite shows **no new failures versus the saved baseline**
   (`pytest -m "not semantic"`: 3 failed / 11 passed / 3 skipped before any
   change — the 3 failures in `test_tenant_isolation.py` are data-driven, see
   Notes). This task changes no behaviour, only constraints. No test file is
   edited. If a *new* failure appears, it is because a fixture inserts a row
   with no `tenant_id`; fix the fixture, not the constraint.
6. `audit_tenant_coverage.py` output is unchanged from baseline
   (95 endpoints, 0 HARDCODED, 0 REVIEW).

### Decisions to flag in the audit (do not pick — present options and wait)
**Decision 1 — `users.tenant_id`.** Today nullable with `default="ryze"`.
  (a) Make it NOT NULL in this migration like the other five tables.
      Consequence: every user must belong to a tenant at creation, including
      signups the resolver can't place — which forces the part-3 decision
      (reject / pending / create-tenant) to be made now, or the signup-firm
      path breaks in the meantime.
  (b) Leave `users.tenant_id` nullable in this task, drop only its
      `default="ryze"`, and make it NOT NULL in part 3 once the resolver has
      an explicit answer for unplaced users.
  Recommendation to present: (b) — keeps this task purely mechanical.

**Decision 2 — `chat_sessions` / `chat_messages`.** They have no `tenant_id`
  column (scoped indirectly via `chat_sessions.user_id → users.tenant_id`,
  noted 2026-11-03).
  (a) Out of scope here; revisit after part 2 when every other table is strict.
  (b) Add `tenant_id NOT NULL` to `chat_sessions` in this migration, backfilled
      from the owning user.
  Recommendation to present: (a) — one concern per change.

**Decision 3 — backfill value.** The NULL rows (none locally) are historically
  RYZE Recruiting's data, so `'ryze'` is the correct backfill for a prod dump.
  Confirm Dane is happy that any such rows become part of whatever the `ryze`
  tenant row is renamed to in part 2, rather than being deleted.

## Related Files
- `app/models/candidate.py`, `booking.py`, `employer_profile.py`, `job_order.py`,
  `job_interest.py`, `user.py` — nullable `tenant_id` columns and `ryze` defaults
- `app/models/tenant.py` — add `billing_exempt`
- `app/models/usage_event.py` — already NOT NULL; reference for the pattern
- `alembic/env.py` — imports every model; nothing new to add
- `alembic/versions/d68448a26b3b_add_tenants_table.py` — the tenants table this extends
- `tests/conftest.py`, `tests/test_tenant_isolation.py` — fixtures that may insert
  rows without `tenant_id`
- `audit_tenant_coverage.py` — baseline before, re-run after

## Verification
- [x] `python audit_tenant_coverage.py` run BEFORE any change; output saved for comparison
- [x] New migration file exists under `alembic/versions/`, with explicit backfill
      `UPDATE` statements before each `ALTER COLUMN ... SET NOT NULL`
- [x] `psql -d niceats -c "\d candidates"` (and the other four) shows `tenant_id ... not null`
- [x] `psql -d niceats -c "\d tenants"` shows `billing_exempt boolean not null default false`
- [x] `alembic current` shows the new head; `alembic check` is clean
- [x] `alembic downgrade -1` then `alembic upgrade head` both succeed
- [x] Inserting a candidate with no `tenant_id` via SQLAlchemy raises `IntegrityError`
      (one-line check in a python shell, not a committed test)
- [x] `pytest -m "not semantic"` shows the same 3 failed / 11 passed as the baseline,
      with no test-file edits
- [x] `seed_landscaping_jobs.py` still imports (`python -c "import seed_landscaping_jobs"`
      or equivalent) after the model constant is deleted
- [x] `python audit_tenant_coverage.py` after: identical to baseline
- [x] `uvicorn app.main:app --reload --port 8000` starts clean; login still returns a JWT
- [ ] Committed and pushed to `origin/main`; `current-feature.md` History updated

## Notes
- Platform name decided 2026-11-05: **Nice ATS** (niceats.com). Local DB on the
  mini is `niceats`. No code is rebranded yet; that follows the three restructure
  tasks.
- Part 2 (next task): delete `RYZE_TENANT` from `deps.py` and `branding.py`;
  remove every `or RYZE_TENANT` fallback (~40 sites across `candidates.py`,
  `employer_profiles.py`, `search.py`, `chat.py`, `chat_sessions.py`, `billing.py`,
  `bookings.py`, `webhooks.py`, `embedding_service.py`) **plus the three literal
  `or "ryze"` sites in `bookings.py` (lines ~152, ~206, ~641) that a grep for
  `RYZE_TENANT` misses**; `seed_landscaping_jobs.py` now imports the constant
  from `deps.py` and goes with it; replace the slug
  comparison in `_check_tenant_access` and `usage.py` with `tenant.billing_exempt`;
  replace the `db_explorer.py` line-360 tenant check with `user.is_superuser`;
  rewrite `tests/test_tenant_isolation.py`. Audit before/after.
- Part 3: `tenant_resolution.py` — decide reject / pending / create-tenant for
  unplaced signups; `users.tenant_id` NOT NULL if Decision 1 → (b);
  `tests/test_signup_tenant_resolution.py` rewritten (its `*_resolves_to_ryze`
  tests encode the behaviour being removed).
- Test baseline (2026-11-05, decided with Dane): `tests/test_tenant_isolation.py`
  fails 3 tests on this machine before any change. The suite reads the live DB
  and `conftest.GROUND_TRUTH` expects `greenpath_recruiting` bookings on
  2026-07-09; local `niceats` is unseeded, and `seed_greenpath_demo.py` creates
  slug `green_path_recruiting` (underscore) anyway, so seeding would not fix it.
  Fix the slug mismatch in the part-2 rewrite of that file; do not touch it now.
- Open question for Dane, not blocking this task: which tenant his own user
  (id 1, currently `ryze`) should end up in — `green_path_recruiting` (what the
  demo seed does) or a tenant named for his real recruiting business.
- `seed_greenpath_demo.py --wipe-only` restores user 1 to `ryze`; `reset_demo_db.py`,
  `seed_full.py`, `backfill_signup_tenants.py` also assume `ryze`. Those scripts are
  updated in part 2 when the slug goes away, not here.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-11-05 — Task drafted (Claude, chat) from a read-only inspection of the
  models, `deps.py`, `branding.py`, `usage.py`, `tenant_resolution.py`,
  `db_explorer.py` and both tenant test files. No code changed.
- 2026-11-05 — Audit done (Claude Code). Baselines: audit 95 endpoints / 0
  HARDCODED / 0 REVIEW; alembic at 4083c0d3ba12, `check` clean; zero NULL
  `tenant_id` rows locally (DB otherwise empty — 0 tenants, user 1 in `ryze`);
  pytest offline tier 3 failed / 11 passed (data-driven, see Notes). Found:
  every app constructor passes `tenant_id` explicitly, so dropping the model
  defaults changes no behaviour; `seed_landscaping_jobs.py` imports
  `RYZE_TENANT` from `job_order.py`; `bookings.py` has three literal `or "ryze"`.
  Decisions confirmed by Dane: 1 → (b), 2 → (a), 3 → backfill `'ryze'`;
  Criterion 5 reworded to "no new failures vs baseline"; `billing_exempt` gets
  both `default` and `server_default`.
- 2026-11-05 — Implemented (Claude Code), not yet committed. Models: `nullable=False`
  on the five tables, `default="ryze"`/`RYZE_TENANT` defaults and the two
  module-level constants removed, `users.tenant_id` keeps nullable (Decision 1b)
  with its default dropped, `Tenant.billing_exempt` added; `seed_landscaping_jobs.py`
  import repointed at `app.core.deps`. Migration f807a49989a8 (autogenerated,
  then hand-edited: per-table `UPDATE ... WHERE tenant_id IS NULL` before each
  `SET NOT NULL`, `billing_exempt` with `server_default=sa.text("false")`,
  downgrade reverses all). Verified: `alembic upgrade head` → f807a49989a8,
  `alembic check` clean, `downgrade -1` → all five nullable again and column
  gone → `upgrade head` again OK; information_schema shows the five columns
  NOT NULL, `users.tenant_id` nullable, `billing_exempt boolean NOT NULL
  DEFAULT false`; no-tenant `Candidate` insert raises `IntegrityError`
  (not-null violation); pytest offline tier 3 failed / 11 passed — identical to
  baseline; audit output byte-identical to baseline (95 / 0 / 0); uvicorn
  starts clean, `GET /docs` → 200. **Not verified:** login → JWT (no `.token`
  on this machine and no password in session). Awaiting Dane's review of the
  diff before commit.
- 2026-11-05 — Dane reviewed the diff and verified login in the browser against
  the migrated DB (JWT returned). Committed as one change and pushed to
  `origin/main` together with the archive commit d3edd13.
