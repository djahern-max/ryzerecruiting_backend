# current-feature.md

# DB Explorer — platform-owner global visibility (unscope superadmin queries)

**Status:** Not started
**Repo:** ryzerecruiting_backend (primary), ryzerecruiting_frontend (minor)
**File:** `app/api/db_explorer.py`, `src/pages/admin/DBExplorer.jsx`

## Problem

The DB Explorer is the superadmin's window into the entire database, but it is
currently showing only rows whose `tenant_id` matches the superadmin's own
tenant. Live symptom (2026-07-22): the database contains **6 `job_orders` and
2 `bookings`** (verified via psql `SELECT COUNT(*)`), but the explorer shows
**zero** for both.

### Root cause (confirmed by repo audit)

Every endpoint in `app/api/db_explorer.py` applies a tenant filter to tables in
`TENANT_SCOPED_TABLES` using `_tenant(current_user)` — i.e. the superadmin's
own tenant — with exactly one ad-hoc bypass, for the `users` table:

```python
if table in TENANT_SCOPED_TABLES:
    if not (table == "users" and current_user.is_superuser):
        conditions.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
```

Any row in `job_orders`, `bookings`, `candidates`, `employer_profiles`, or
`job_interests` whose `tenant_id` differs from the superadmin's resolved tenant
(`user.tenant_id or "ryze"`) is invisible — including rows with a different
tenant slug AND rows with a mismatched/legacy value.

**Critically:** the file already contains the intended fix as dead code. The
helper `_is_platform_owner()` exists with a docstring describing exactly the
desired behavior, but it is never called by any endpoint:

```python
def _is_platform_owner(user) -> bool:
    """RYZE's own superadmin (tenant_id == 'ryze') gets a global, unscoped view
    across every table. Any other user — including a firm-level superuser, should
    one ever exist — stays scoped to their own tenant, preserving isolation."""
    return (user.tenant_id or RYZE_TENANT) == RYZE_TENANT
```

## Goals

1. **Platform owner sees everything.** When the requesting user passes
   `get_current_superuser` AND `_is_platform_owner(user)` is true, drop the
   `tenant_id` filter on every tenant-scoped table in every DB Explorer
   endpoint: counts, browse, export, PATCH, DELETE.
2. **Everyone else stays strictly scoped.** A hypothetical firm-level superuser
   (is_superuser but tenant != "ryze") keeps the existing tenant-filtered
   behavior on every endpoint. No behavior change anywhere else in the app —
   all REST/data endpoints continue to use `get_current_tenant` /
   `get_current_admin_tenant` scoping untouched.
3. **Tenant attribution is visible.** The platform owner must be able to see
   *which* tenant each row belongs to, so surface `tenant_id` in the frontend
   summary columns for tenant-scoped tables.

## Non-goals

- Do NOT touch tenant scoping anywhere outside `app/api/db_explorer.py`.
- Do NOT change `get_current_tenant`, `get_current_admin_tenant`, or
  `_check_tenant_access` in `app/core/deps.py`.
- Do NOT add a tenant-picker UI (a later enhancement; global view is enough).

---

## Backend changes — `app/api/db_explorer.py`

### 1. Introduce a single unscoped-decision point

At the top of each endpoint that queries data, compute once:

```python
unscoped = _is_platform_owner(current_user)
```

(`get_current_superuser` is already the route dependency, so `is_superuser` is
guaranteed; `_is_platform_owner` adds the tenant check. Both conditions are
required — keep it that way.)

### 2. `/db/counts`

Replace the `users`-only special case with the general rule:

```python
for table in TABLE_COLS:
    try:
        if table in TENANT_SCOPED_TABLES and not unscoped:
            counts[table] = db.execute(
                text(f'SELECT COUNT(*) FROM "{table}" WHERE tenant_id = :tid'),
                {"tid": tenant_id},
            ).scalar() or 0
        else:
            counts[table] = db.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar() or 0
    except Exception:
        counts[table] = 0
```

Note: the old special case (`table == "users" and current_user.is_superuser`)
is now subsumed and should be deleted — a firm-level superuser will correctly
see only their own users, which is stricter (and correct) compared to today.

### 3. `/db/explorer` (browse) and `/db/export`

Both build the same conditions list. Change the tenant filter in each to:

```python
if table in TENANT_SCOPED_TABLES and not unscoped:
    conditions.append("tenant_id = :tenant_id")
    params["tenant_id"] = tenant_id
```

Delete the `users` special case in both places.

### 4. PATCH `/db/records/{table}/{record_id}` and DELETE

Same rule: the platform owner edits/deletes globally (`WHERE id = :id` only);
anyone else keeps `AND tenant_id = :tenant_id`:

```python
if table in TENANT_SCOPED_TABLES and not _is_platform_owner(current_user):
    # existing tenant-scoped UPDATE/DELETE
else:
    # unscoped UPDATE/DELETE (existing non-scoped branch)
```

### 5. Update stale comments

- The module-level comment above `TENANT_SCOPED_TABLES` and the endpoint
  docstrings say queries are "scoped to the authenticated admin's tenant" —
  amend to note the platform-owner exception.
- The docstring on `_is_platform_owner` is already correct; it becomes live
  code, not dead code.

### 6. Audit `bookings` for a `tenant_id` column (verify, then act)

`bookings` is in `TENANT_SCOPED_TABLES`, but `TABLE_COLS["bookings"]` does NOT
list `tenant_id`, unlike every other scoped table. Check the model
(`app/models/booking.py`) and/or run `\d bookings`:

- If the column exists: add `"tenant_id"` to `TABLE_COLS["bookings"]` (after
  `"id"`) so the platform owner can see attribution.
- If the column does NOT exist: `bookings` must be REMOVED from
  `TENANT_SCOPED_TABLES` (the current filter would be erroring and the counts
  endpoint's bare `except` silently reports 0 — which may be a second,
  masked contributor to the empty view). Document whichever is found in the
  History section below.

### 7. Optional but recommended — diagnose the mismatch

The fix makes visibility unconditional for the platform owner, but it's worth
one query to understand why the scoping failed in the first place:

```sql
SELECT tenant_id, COUNT(*) FROM job_orders GROUP BY tenant_id;
SELECT id, email, tenant_id, is_superuser FROM users WHERE is_superuser = true;
```

If the superadmin's `users.tenant_id` is NULL or a value other than the slug
on the job_orders rows, that's the mismatch. Record the finding in History —
if superadmin rows should canonically carry `tenant_id = 'ryze'`, fix the data
too (`UPDATE users SET tenant_id = 'ryze' WHERE is_superuser = true;`), since
`_is_platform_owner` treats NULL as "ryze" already but explicit is better.

---

## Frontend changes — `src/pages/admin/DBExplorer.jsx`

Minimal. The API response shape is unchanged; the frontend just renders more
rows. One improvement:

### `SUMMARY_COLS` — surface `tenant_id` on scoped tables

Add `"tenant_id"` (right after `"id"`) to the summary columns for:
`candidates`, `employer_profiles`, `job_orders`, `job_interests`, and
`bookings` (only if step 6 confirms the column exists). `users` already shows
it. This lets the global view answer "whose row is this?" at a glance.

No changes to `TABLES`, `EDITABLE_COLS`, or `FK_MAP`.

---

## Security invariants (do not violate)

1. Unscoped access requires BOTH `is_superuser` (route dependency) AND
   `tenant_id == 'ryze'` (`_is_platform_owner`). Never relax to is_superuser
   alone.
2. All table and column names remain whitelist-validated against the config
   dicts (`TABLE_COLS`, `SEARCHABLE_COLS`, `EDITABLE_COLS`) — no change to
   the injection-safety posture.
3. `hashed_password`, `embedding`, and `twilio_auth_token` stay excluded from
   `TABLE_COLS` regardless of who is asking.
4. Zero changes outside `db_explorer.py` / `DBExplorer.jsx`. Run
   `audit_tenant_coverage.py` after the change and confirm no new
   REVIEW/HARDCODED lines.

---

## Verification checklist

Run as the RYZE superadmin (tenant "ryze" or NULL):

- [ ] Sidebar counts match psql exactly: bookings 2, candidates 1,
      chat_messages 2, chat_sessions 1, employer_profiles 2, job_interests 1,
      job_orders 6, tenants 1, users 7, webhook_logs 13, waitlist 0,
      contacts 0.
- [ ] Browsing `job_orders` lists all 6 rows with their `tenant_id` visible.
- [ ] Browsing `bookings` lists both rows.
- [ ] Search, date filters, sort, and CSV export on `job_orders` operate over
      all 6 rows (export file contains 6 data rows).
- [ ] PATCH an editable field on a job_order belonging to a non-ryze tenant →
      succeeds (200), persists.
- [ ] DELETE works globally (test on a disposable row only).

Regression (simulate a firm-scoped superuser, e.g. temporarily set a test
user's `is_superuser = true` with `tenant_id = 'sometenant'`):

- [ ] That user's counts/browse/export on scoped tables show ONLY
      `tenant_id = 'sometenant'` rows.
- [ ] That user's PATCH/DELETE against a ryze-tenant row → 404.
- [ ] Non-superuser admin still gets 403 on every `/admin/db/*` route.
- [ ] All non-explorer endpoints unchanged (spot-check `/api/search/*` and one
      REST list endpoint — still tenant-filtered).
- [ ] `audit_tenant_coverage.py` output identical to before the change.

## History

- 2026-07-22: Spec written. Root cause confirmed by repo audit: every
  db_explorer endpoint tenant-filters via `_tenant(current_user)` with only a
  `users` special case; the purpose-built `_is_platform_owner()` helper exists
  but was never wired into any endpoint (dead code). Live DB shows 6
  job_orders / 2 bookings invisible in the explorer. Also flagged:
  `bookings` is in `TENANT_SCOPED_TABLES` but `TABLE_COLS["bookings"]` lacks
  `tenant_id` — must verify the column exists (step 6) since the counts
  endpoint's bare `except → 0` could be silently masking an error there.
- 2026-07-22: Audit-first step done before writing code — confirmed
  `RYZE_TENANT` is exported from `app/core/deps.py` (module-level constant,
  already imported into `db_explorer.py`), no import changes needed.
  Confirmed `app/models/booking.py` has `tenant_id = Column(String(100),
  nullable=True, index=True)` — **Path A** taken for step 6: added
  `"tenant_id"` to `TABLE_COLS["bookings"]` (after `"id"`) rather than
  removing `bookings` from `TENANT_SCOPED_TABLES`. Captured baseline
  `audit_tenant_coverage.py` output before any edits: `db_explorer.py` 6/6
  SAFE, 0 hardcoded (all detected via the literal `_tenant(current_user)`
  string in each function body, which every endpoint retains post-change);
  the only REVIEW lines anywhere are the 2 pre-existing, unrelated
  `candidates.py` (`/me/photo`, `/me/banner`) findings. Plan confirmed by
  user with two additions: also amend the `/db/counts` and `/db/export`
  docstrings (not just PATCH/DELETE/module comment) with the platform-owner
  exception, and record here that dropping the `users` special case
  intentionally tightens a hypothetical firm-level superuser's behavior
  (they now see only their own tenant's `users` rows, stricter than today's
  blanket unscoped-users bypass — correct per Goal 2).
- 2026-07-22: Backend implemented — introduced `unscoped =
  _is_platform_owner(current_user)` in `/db/counts`, `/db/explorer` (browse),
  and `/db/export`; PATCH/DELETE use `_is_platform_owner(current_user)`
  inline in the branch condition per the spec's literal per-site wording.
  Deleted the `users`-only special case in all three GET-family endpoints —
  subsumed by the general rule, and intentionally stricter for any future
  firm-level superuser (is_superuser but tenant != "ryze"): they now see only
  their own tenant's `users` rows instead of every tenant's. Updated the
  `TENANT_SCOPED_TABLES` module comment and all five endpoint
  docstrings/inline comments (counts, browse, export, PATCH, DELETE) to note
  the platform-owner exception. Added `"tenant_id"` to
  `TABLE_COLS["bookings"]` after `"id"` (Path A, confirmed above). App-import
  check clean (98 routes, unchanged). `audit_tenant_coverage.py`: identical
  to the pre-change baseline — `db_explorer.py` still 6/6 SAFE, 0 hardcoded;
  same 2 pre-existing unrelated REVIEW lines in `candidates.py`, no new
  REVIEW/HARDCODED anywhere.
- 2026-07-22: Backend committed as `a0bc938`.
- 2026-07-22: Frontend implemented (sibling `frontend` repo) — added
  `"tenant_id"` right after `"id"` in `SUMMARY_COLS` for `bookings`,
  `candidates`, `employer_profiles`, `job_orders`, and `job_interests`.
  `tenants` untouched (not tenant-scoped, no `tenant_id` column). No changes
  to `TABLES`, `EDITABLE_COLS`, or `FK_MAP`. Committed separately as
  `c19bf57` in the frontend repo, per "one concern per change" /
  separate-repo convention.
- Remaining: user runs the item-7 diagnostic SQL (`job_orders` tenant_id
  distribution, superuser `users` rows) and pastes results back; full manual
  verification checklist (sidebar counts, browse/search/export/PATCH/DELETE
  as platform owner, regression as a simulated firm-scoped superuser,
  non-superuser 403, non-explorer endpoints unchanged, final
  `audit_tenant_coverage.py` re-check).
