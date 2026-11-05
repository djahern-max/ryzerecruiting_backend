# Current Feature

Tenant restructure, part 2 of 3 — remove the house tenant: delete `RYZE_TENANT`, every `or "ryze"` fallback, and the no-tenant-row allowance; platform behaviour moves to `tenants.billing_exempt` and `users.is_superuser`

## Status
<!-- Not Started | In Progress | Completed -->
In Progress

## Goals
<!-- Goals & requirements -->
**Backend repo only.** Do not touch `app/services/tenant_resolution.py` or
`tests/test_signup_tenant_resolution.py` — that is part 3. No rebranding of
display strings (`APP_NAME`, `FROM_EMAIL`, PDF footers, CORS origins) — that is
the rebrand task after part 3.

Part 1 (f807a49989a8, archived in CHANGELOG.md) made `tenant_id` NOT NULL on
`candidates`, `bookings`, `employer_profiles`, `job_orders`, `job_interests` and
added `tenants.billing_exempt`. `users.tenant_id` is still nullable (Decision 1b).

After this task there is no house tenant. All tenants are peers. The platform
(Nice ATS) is not a tenant. Four things change behaviour:

1. **Billing/usage exemption** comes from `tenants.billing_exempt`, not a slug
   compare. `_check_tenant_access` (`app/core/deps.py`) and `is_over_budget`
   (`app/services/usage.py`) read the column.
2. **No tenant row = no access.** The "legacy or pre-EP17 account — allow
   through" branch in `_check_tenant_access` is deleted. A slug with no
   `tenants` row raises 403 (see Decision 2 for the status code).
3. **NULL `users.tenant_id` = no access to tenant data.** Every
   `current_user.tenant_id or <fallback>` becomes a dependency that raises when
   the user has no tenant. Centralise this: `get_current_tenant` /
   `get_current_admin_tenant` already exist in `deps.py`; call sites that
   currently inline the fallback switch to the dependency (or to a small
   `require_tenant(user)` helper for non-endpoint code such as
   `embedding_service.py`). Do not re-implement the check in each file.
4. **Platform owner = `is_superuser`**, not tenant membership.
   `db_explorer._is_platform_owner` and `_tenant` (`app/api/db_explorer.py`
   ~lines 352–360) use `user.is_superuser`.

Done means:
- `grep -rn "RYZE_TENANT\|\"ryze\"\|'ryze'" app/` returns nothing except the
  `_LEGACY_UNPLACED = "ryze"` line in `tenant_resolution.py` (Decision 4a; part 3).
- `app/core/deps.py` and `app/services/branding.py` no longer define the constant.
  `get_branding()` drops the `tid == RYZE_TENANT` shortcut; the `_ryze_defaults`
  function is renamed `_platform_defaults` (contents unchanged — the strings
  inside are rebranded later).
- The data migration in "Data" below is applied and Dane's user can log in and
  reach `/api/candidates`.
- `tests/test_tenant_isolation.py` rewritten so it is self-contained (creates its
  own tenants and rows in a transaction, does not read live demo data), fixes
  the `greenpath_recruiting` vs `green_path_recruiting` slug mismatch, and adds
  tests for behaviours 1–4 above: exempt tenant bypasses 402, missing tenant row
  → 403, NULL `users.tenant_id` → 403, non-superuser cannot reach the unscoped
  db_explorer view. `pytest -m "not semantic"` → 0 failed.
- `audit_tenant_coverage.py` after ≥ baseline: 0 HARDCODED, 0 REVIEW, and the
  Safe count does not go down. (The script's own `ryze` references in its
  pattern list are updated in the same commit so it does not flag the new
  helper as a pattern it doesn't recognise.)

### Data (one migration, hand-written)
Your user (id 1) is in slug `ryze` and the `tenants` table is empty, so today
you only have access via the allow-through branch this task deletes. The
migration must, in order:
1. Insert a `tenants` row for Dane's firm — slug and `company_name` per
   Decision 1 — with `status='active'`, `billing_exempt=true`.
2. `UPDATE users SET tenant_id = '<slug>' WHERE tenant_id = 'ryze' OR tenant_id IS NULL AND is_superuser`.
   (Any prod-dump rows backfilled to `'ryze'` in part 1 follow the same UPDATE
   on the five data tables.)
3. Downgrade: reverse the UPDATEs to `'ryze'`; leave the tenant row (deleting a
   tenant is never a migration's job).

### Call-site inventory (from grep, 2026-11-05 — verify before editing)
- `app/core/deps.py`: constant, `_check_tenant_access`, `get_current_tenant`,
  `get_current_admin_tenant` (lines ~23, 79, 84–86, 130, 142)
- `app/services/usage.py:29,101–102`; `app/services/branding.py:34,86–89`
- `app/services/embedding_service.py:19,481,548,603,625,647`
- `app/services/auth.py:35–36` (comment only — update the comment)
- `app/api/db_explorer.py:12,352–360`
- `app/api/search.py:15,95,131,178,223`
- `app/api/chat.py:14,337,363,404,445,483,514,547,580,631,637,668,746,771`
  (tool functions default `tenant_id=RYZE_TENANT` — make the parameter required)
- `app/api/chat_sessions.py:20,250`; `app/api/billing.py:14,62,67,142`
- `app/api/employer_profiles.py:14,56,329,349,375,409,460,508,638`
- `app/api/candidates.py:25,73,90,145,233`; `app/api/webhooks.py:23,137`
- `app/api/bookings.py` — **eleven** literal `or "ryze"`:
  152,178,206,379,395,424,468,641,738,755,931
- `app/services/notifications.py` — notify functions default `tenant_id="ryze"`
  (CLAUDE.md "Known risk"): make `tenant_id` required, no default.
- Scripts that assume `ryze`: `seed_greenpath_demo.py` (`--wipe-only` restores
  user 1 to `ryze`), `reset_demo_db.py`, `seed_full.py`, `seed_cleanup.py`,
  `backfill_signup_tenants.py`, `seed_landscaping_jobs.py`,
  `manual_test_tenant_isolation.py`, `scripts/create_superadmin.py` (stamps
  tenant `ryze` — give it a required `--tenant` argument). Update them to the
  Decision 1 slug; delete any that are dead (check `context/dead-code-audit.md`).
- `tests/conftest.py` (3 refs).

### Decisions to flag in the audit (do not pick — present options and wait)
**Decision 1 — Dane's own tenant.** The slug and company name for the row the
  migration creates.
  (a) `green_path_recruiting` / "Green Path Recruiting" — matches what
      `seed_greenpath_demo.py` already creates; one tenant locally, the seed
      becomes idempotent with it.
  (b) A slug for Dane's real recruiting business (name to be supplied).
      Green Path Recruiting then stays a demo tenant created by the seed only.
  Consequence of (a): demo data and Dane's working data share a tenant.
  Consequence of (b): clean separation; seed script needs a second superadmin
  or a `--tenant` flag.

**Decision 2 — status code for "no tenant" cases** (missing row, NULL
  `users.tenant_id`). (a) 403 with a clear detail string; (b) 401. 403 is
  recommended: the user is authenticated, just not entitled. The frontend
  shows the detail string either way.

**Decision 3 — `chat.py` tool functions.** They take `tenant_id` with a
  default. (a) Make it a required positional parameter — any caller that forgot
  it fails loudly at import/call time. (b) Keep the parameter, drop the default.
  Same effect; (a) is the stricter signature. Recommend (a).

## Related Files
- `app/core/deps.py`, `app/services/usage.py`, `app/services/branding.py`,
  `app/services/notifications.py`, `app/services/embedding_service.py`
- `app/api/db_explorer.py`, `bookings.py`, `candidates.py`, `employer_profiles.py`,
  `search.py`, `chat.py`, `chat_sessions.py`, `billing.py`, `webhooks.py`
- `app/models/tenant.py` (`billing_exempt`, from part 1)
- `alembic/versions/` — new data migration
- `tests/test_tenant_isolation.py`, `tests/conftest.py`
- `audit_tenant_coverage.py`, the seed/maintenance scripts listed above
- `CLAUDE.md` — "CRITICAL: multi-tenant isolation" and "Tenant branding" sections
  reference `RYZE_TENANT` and `tenant_id="ryze"` defaults; propose the edit in
  the same session (honesty rule)

## Verification
- [x] `python audit_tenant_coverage.py` run BEFORE any change; output saved (`context/audit_baseline_part2.txt`: 95 endpoints, 76 Safe, 19 Public/Skip, 0 Hardcoded, 0 Review)
- [x] Decisions 1–3 (+4) presented with recommendations; answers recorded in Notes
- [x] `grep -rn "RYZE_TENANT\|\"ryze\"\|'ryze'" app/` → only `_LEGACY_UNPLACED = "ryze"` in `tenant_resolution.py` (Decision 4a)
- [x] Data migration applied; `psql -d niceats -c "SELECT slug, status, billing_exempt FROM tenants;"` shows Dane's firm, active, `t` (green_path_recruiting | active | t)
- [x] `psql -d niceats -c "SELECT id, email, tenant_id, is_superuser FROM users;"` shows user 1 in the new slug (1 | green_path_recruiting | t)
- [x] `alembic downgrade -1` then `upgrade head` round-trips (a1b2c3d4e5f6; `alembic check` clean)
- [ ] Login returns a JWT; authenticated `GET /api/candidates` → 200 (Dane, in the browser)
- [ ] Manually: set `billing_exempt=false` and `status='expired'` on the tenant via psql → `GET /api/candidates` → 402; restore → 200
- [ ] Manually: `UPDATE users SET tenant_id = NULL WHERE id = 1` → 403; restore
- [x] `pytest -m "not semantic"` → 0 failed (24 passed, 3 skipped, 3 deselected; commit 5)
- [x] `python audit_tenant_coverage.py` after: 95 endpoints, 76 Safe, 0 HARDCODED, 0 REVIEW — unchanged from baseline
- [ ] `python seed_greenpath_demo.py --yes` then `--wipe-only --yes` both run clean against the new slug (Dane: Claude's auto-mode permission refused to run the wipe; every table it clears is currently empty, so the pair is a no-op on data)
- [x] `CLAUDE.md` edit committed separately (dd46661, commit 6)
- [x] Commit 6 also: un-ignore `scripts/` in `.gitignore` (one line) so `create_superadmin.py` and future helpers are tracked normally (dd46661)
- [x] Committed and pushed to `origin/main` (commits 1–6: e8471f5, 7342ea5, c76d157, af88f5e, 0fef322, dd46661); History updated

## Notes
- Platform name: Nice ATS (niceats.com). Local DB `niceats`. No production server.
- **Decisions (2026-11-05):** 1 → (a): slug `green_path_recruiting`,
  company_name "Green Path Recruiting". Migration upserts that row (active,
  billing_exempt=true) and moves user 1 into it; `ensure_tenant` in the seed
  is idempotent against it; `--wipe-only` keeps user 1 there; no `--tenant`
  flag on the seed; `create_superadmin.py --tenant` defaults to it. 2 → (a) 403. 3 → (a) required positional. 4 → (a): local
  `_LEGACY_UNPLACED = "ryze"` inside `tenant_resolution.py` and the signup
  test, so part 3 still owns the rewrite. **Consequence of 4:** unplaced
  signups now resolve to a slug with no `tenants` row and therefore get 403 on
  data endpoints until part 3 — intended.
- Inventory additions accepted: `job_orders.py` (10 sites), `admin_invite.py:97`
  → `is_superuser`, `email.py` `get_branding(None, "ryze")` →
  `get_branding(None, None)` at all 17 sites, the eight notify calls that pass
  no tenant (`bookings.py` ×7, `scheduler.py:75`) must pass the booking's
  `tenant_id`, `reseed_demo.py`, `analyze_webhook_logs.py` CLI default, and
  the audit script hint text. No root script is deleted; references updated only.
- `RYZE_TENANT` stays defined in `deps.py` (marked deprecated) through commits
  1–2 so every commit imports cleanly; it is deleted in commit 3 with the last
  importers.
- "One concern per change" applies within this task too: suggested commit order
  is (1) deps/usage/branding/db_explorer + helper, (2) API call sites, (3)
  services + scripts, (4) data migration, (5) tests, (6) CLAUDE.md. Audit after
  each of (1)–(3).
- Part 3 (next): `tenant_resolution.py` — unplaced signups (reject / pending /
  create-tenant); `users.tenant_id` NOT NULL once that is settled;
  `tests/test_signup_tenant_resolution.py` rewritten (`*_resolves_to_ryze`
  tests encode the behaviour being removed). The `/auth` page's platform-level
  Employer/Candidate self-registration depends on this decision.
- `chat_sessions` / `chat_messages` still have no `tenant_id` (scoped via the
  owning user). Still out of scope; revisit after part 3.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-11-05 — Task drafted (Claude, chat) from a read-only inspection after
  part 1 landed (00d3712). No code changed.
- 2026-11-05 — Pre-change audit (Claude): baseline saved to
  `context/audit_baseline_part2.txt` (95 / 76 Safe / 0 HARDCODED / 0 REVIEW).
  Inventory verified; bookings.py has exactly 11 literal `or "ryze"` plus a
  12th via `RYZE_TENANT` at line 73. Found sites missing from the inventory:
  job_orders.py (10 literal `or "ryze"`), admin_invite.py:97, email.py
  (17 `get_branding(None, "ryze")`), settings.py:120 comment, and
  tenant_resolution.py importing `RYZE_TENANT` from deps (part-3 file).
  Decisions 1–3 (+ a new Decision 4) presented; waiting on answers. No code changed.
- 2026-11-05 — Commits 1–4 landed locally (e8471f5, 7342ea5, c76d157,
  a1b2c3d4e5f6 migration). Audit unchanged after each of 1–3 (95 / 76 Safe /
  0 / 0). Migration round-tripped on `niceats`; user 1 now in
  `green_path_recruiting`, row active + billing_exempt. Awaiting Dane's browser
  check (login + /api/bookings) before commit 5 (tests). Not yet pushed.
- 2026-11-05 — Commits 1–4 pushed. Commit 5 (0fef322): `test_tenant_isolation.py`
  rewritten self-contained (own tenants/rows in a rolled-back transaction),
  15 tests covering chat-tool isolation both ways plus behaviours 1–4 at the
  dependency and HTTP level (httpx ASGITransport — starlette 0.35's TestClient
  is incompatible with the pinned httpx 0.28). conftest/README updated, stale
  `greenpath_recruiting` slug fixed. Full offline suite 24 passed / 0 failed.
  Commit 6 (dd46661): CLAUDE.md isolation + branding sections rewritten for
  the no-house-tenant rules; `.gitignore` no longer ignores `scripts/`. Both
  pushed. Open: Dane's browser login check, the two manual psql checks, and
  the seed/wipe run (permission-blocked). Finding: `GET /api/candidates` uses
  `require_tenant` only, so it returns 200, not 402, for an expired
  non-exempt tenant — same as before part 2. The 402 path is on endpoints
  that depend on `get_current_tenant` (e.g. `GET /api/bookings`,
  `GET /api/job-orders/open`); the manual 402 check should use one of those.
