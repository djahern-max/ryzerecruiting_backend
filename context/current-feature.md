# current-feature.md

# DB Explorer — surface all current tables (`job_interests`, `tenants`)

**Status:** In Progress

## Context
The DB Explorer was built when the schema was smaller and hardcodes its table
list in two places (backend `TABLE_COLS`/config dicts and a frontend `TABLES`
constant). The live DB now has 13 tables (`\dt`), but the explorer surfaces only
10. Two real tables are missing from the UI:

- **`job_interests`** — added 2026-07-21 (candidate "I'm Interested" feature).
- **`tenants`** — added 2026-04-01 (migration `d68448a26b3b`), never wired into
  the explorer.

`alembic_version` is intentionally **excluded** and stays that way: its only
column is `version_num` (a string PK); it has no `id` column, so it is
incompatible with the explorer's `ORDER BY id DESC` browse fallback and its
`WHERE id = :id` edit/delete logic. It's a migration marker, not application
data.

No DB migration is required — both tables already exist in the database. This is
purely surfacing existing tables in the admin UI.

## Goals
1. Add `job_interests` to the DB Explorer (browse, count, search, CSV export,
   edit the `note` field, delete). Tenant-scoped (it has a `tenant_id` column).
2. Add `tenants` to the DB Explorer as a **read-only, superuser-global** view
   (the `tenants` table has no `tenant_id` column — its `slug` *is* the tenant
   identity — so it must NOT be tenant-scoped). Exclude the `twilio_auth_token`
   secret column, following the same principle already used to exclude
   `hashed_password` and `embedding`.
3. Keep `alembic_version` excluded (documented above).

---

## Backend — `app/api/db_explorer.py`

### 1. `TENANT_SCOPED_TABLES` — add `job_interests` only
`job_interests` has a `tenant_id` column and must be tenant-filtered.
`tenants` must NOT be added here (no `tenant_id` column).

```python
TENANT_SCOPED_TABLES = {
    "candidates",
    "employer_profiles",
    "job_orders",
    "bookings",
    "users",
    "job_interests",
}
```

### 2. `TABLE_COLS` — add two entries
Column order matches each model's logical display order. For `tenants`,
`twilio_auth_token` is deliberately omitted (secret stub).

```python
    "job_interests": [
        "id",
        "tenant_id",
        "job_order_id",
        "candidate_id",
        "note",
        "created_at",
    ],
    "tenants": [
        "id",
        "slug",
        "company_name",
        "status",
        "trial_starts_at",
        "trial_ends_at",
        "stripe_customer_id",
        "stripe_subscription_id",
        "from_email",
        "reply_to_email",
        "support_email",
        "admin_email",
        "signature_name",
        "twilio_account_sid",
        "twilio_from_number",
        "created_at",
        "updated_at",
    ],
```

### 3. `SEARCHABLE_COLS` — add two entries

```python
    "job_interests": ["note"],
    "tenants": ["slug", "company_name", "status", "admin_email"],
```

### 4. `EDITABLE_COLS` — add two entries
`note` is the only sensibly-editable field on a `job_interests` row. `tenants`
is read-only in the explorer (branding/billing edits go through the dedicated
`/api/settings/tenant` endpoint, not here) — use an empty list, matching the
existing read-only tables (`chat_sessions`, `contacts`, `webhook_logs`, ...).

```python
    "job_interests": ["note"],
    "tenants": [],
```

### 5. `TABLES_WITH_UPDATED_AT` — add `tenants` only
`tenants` has an `updated_at` column; `job_interests` does **not** (it has only
`created_at`), so do NOT add `job_interests` here.

```python
TABLES_WITH_UPDATED_AT = {
    "bookings",
    "candidates",
    "employer_profiles",
    "job_orders",
    "users",
    "chat_sessions",
    "tenants",
}
```

**No endpoint code changes.** Every endpoint (`/db/counts`, `/db/explorer`,
`/db/export`, PATCH, DELETE, `/db/explorer/tables`) iterates these config dicts
generically, so the four dict additions above are sufficient on the backend.
`/db/explorer/tables` returns `list(TABLE_COLS.keys())`, so it picks up both new
tables automatically.

---

## Frontend — `src/pages/admin/DBExplorer.jsx`
The frontend does not read the backend's `/db/explorer/tables` list — it uses
its own hardcoded `TABLES` constant, so it must be updated in parallel.

### 1. `TABLES` — add both tables

```js
const TABLES = [
    "bookings", "candidates", "employer_profiles",
    "job_orders", "job_interests", "chat_sessions", "chat_messages",
    "users", "waitlist", "contacts", "tenants", "webhook_logs",
];
```

### 2. `SUMMARY_COLS` — add two entries

```js
    job_interests: ["id", "job_order_id", "candidate_id", "note", "created_at"],
    tenants: ["id", "slug", "company_name", "status", "admin_email", "created_at"],
```

### 3. `EDITABLE_COLS` (frontend copy) — add two entries
Keep in lockstep with the backend `EDITABLE_COLS`.

```js
    job_interests: ["note"],
    tenants: [],
```

### 4. `FK_MAP` — add `job_order_id`
Makes the `job_order_id` foreign key clickable (jumps to the `job_orders`
table), matching how `candidate_id`, `user_id`, etc. already behave. This is a
global column→table map, so it also benefits any other view showing
`job_order_id`.

```js
const FK_MAP = {
    employer_profile_id: "employer_profiles",
    candidate_id: "candidates",
    job_order_id: "job_orders",
    user_id: "users",
    session_id: "chat_sessions",
    employer_id: "users",
};
```

---

## Verification checklist
- [ ] Backend restarts cleanly; `GET /admin/db/explorer/tables` now lists
      `job_interests` and `tenants` (and still omits `alembic_version`).
- [ ] `GET /admin/db/counts` returns counts for both new tables; `job_interests`
      count is tenant-scoped, `tenants` count is the raw total.
- [ ] Sidebar in the DB Explorer shows both new tables with correct row counts.
- [ ] `job_interests`: browse, search on `note`, date filter on `created_at`,
      CSV export, edit `note` (persists), and delete all work. Editing is
      tenant-scoped (cross-tenant edit/delete → 404).
- [ ] `tenants`: browse + CSV export work; `twilio_auth_token` is absent from
      the column set; no edit affordance (read-only).
- [ ] `job_order_id` renders as a clickable FK that navigates to `job_orders`.

## History
- 2026-07-21: Spec written. Confirmed via repo audit that the explorer hardcodes
  its table list in `app/api/db_explorer.py` (four config dicts) and
  `src/pages/admin/DBExplorer.jsx` (`TABLES` + `SUMMARY_COLS` +
  `EDITABLE_COLS` + `FK_MAP`); both were 10 tables. `job_interests` and
  `tenants` were both absent. `alembic_version` deliberately kept out (no `id`
  PK). No migration needed — both tables already live in the DB.
- 2026-07-21: Audit-first step done before writing code — read
  `app/api/db_explorer.py`, `frontend/src/pages/admin/DBExplorer.jsx`,
  `app/models/job_interest.py`, and `app/models/tenant.py`. Confirmed every
  db_explorer endpoint is generic over the config dicts (no per-table branches
  needed) and already gated by `get_current_superuser`, so the `tenants`
  global view needs no extra plumbing. Confirmed column lists against the
  actual models: `JobInterest` has no `updated_at` (matches spec excluding it
  from `TABLES_WITH_UPDATED_AT`); `Tenant` has 18 columns, 17 after excluding
  `twilio_auth_token`, matching the spec's `TABLE_COLS["tenants"]` exactly.
  Plan confirmed by user with three guards: (1) `tenants` `EDITABLE_COLS` must
  exclude `slug` (identity key, no FK — editing it would orphan a firm's
  data) and keep `status`/`trial_*`/`stripe_*` read-only too — already true,
  spec had `tenants: []`; (2) `job_interests` editable = `note` only, FKs and
  `tenant_id` read-only — already true; (3) document that DELETE on a
  `tenants` row does not cascade (plain-string `tenant_id` references, no FK
  constraint) — orphaned rows silently fall back to RYZE branding via
  `get_branding()`.
- 2026-07-21: Backend implemented — 5 dict edits in `app/api/db_explorer.py`
  (`TENANT_SCOPED_TABLES` +`job_interests`; `TABLE_COLS`, `SEARCHABLE_COLS`,
  `EDITABLE_COLS` +both tables; `TABLES_WITH_UPDATED_AT` +`tenants`), plus the
  no-cascade-DELETE warning as a comment above `TABLE_COLS["tenants"]` and the
  read-only rationale as a comment above `EDITABLE_COLS["tenants"]`. No
  endpoint code changes. App-import check clean (98 routes).
  `audit_tenant_coverage.py`: same 2 pre-existing REVIEW lines
  (`candidates.py` `/me/photo`, `/me/banner`, unrelated), no new
  REVIEW/HARDCODED. Committed as `4b60776`.
- 2026-07-21: Frontend implemented (sibling `frontend` repo) — 4 edits to
  `src/pages/admin/DBExplorer.jsx` mirroring the backend: `TABLES`,
  `SUMMARY_COLS`, `EDITABLE_COLS` (`job_interests: ["note"]`,
  `tenants: []`), and `FK_MAP` (+`job_order_id` → `job_orders`, the first
  table to expose that column). Committed separately as `0a510a0` in the
  frontend repo, per "one concern per change" / separate-repo convention.
- Remaining: manual verification against the checklist above (browse/search/
  export/edit/delete for `job_interests`, browse/export/no-edit for
  `tenants`, FK click-through, sidebar counts) — not yet run.
