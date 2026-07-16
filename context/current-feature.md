# current-feature.md

## Feature: Tenant brand name in auth responses (candidate portal white-labeling — Phase 1 of 2, BACKEND)

**Status:** Code written, pending manual deploy + verification
**Repo:** ryzerecruiting_backend
**Depends on:** nothing
**Blocks:** frontend Header brand swap (Phase 2). Do NOT start the frontend
task until this is deployed and `tenant_brand_name` is confirmed present in the
live `GET /api/auth/me` response.

### Goal
Expose the resolved tenant brand name on the authenticated user object so the
frontend can display the recruiting firm's name (e.g. "Green Path Recruiting")
instead of the hardcoded "RYZE.ai". This is the keystone change: the frontend
currently has no way to know which firm a user belongs to — `/auth/me` and the
login response return `id`, `email`, `full_name`, `user_type`, `is_superuser`
only, with no tenant or brand information.

Add `tenant_brand_name` (string) — and optionally `tenant_id` (string) — to
every place the API returns the authenticated user object:
- login (`AuthService.authenticate_user`)
- `GET /api/auth/me`
- the OAuth signup completion response

The value is `get_branding(db, user.tenant_id).brand_name`, which already
returns "Green Path Recruiting" for that tenant and falls back to "RYZE.ai" for
the `ryze` tenant (and for any tenant with a NULL company_name). Reuse the
existing resolver — do not add new branding logic.

### Non-goals (keep scope tight)
- No URL / route changes.
- No visual theming (logo, brand colors) — sender-identity brand *name* only.
- No new email templates — branded welcome email is a separate, later task.
- **No DB migration** — this reads existing `tenant.company_name` through the
  resolver; there is no schema change. If a plan proposes a migration, it has
  misunderstood the task.

### Kickoff prompt for Claude Code (audit-first)

Workspace is rooted at this backend repo. Before writing any code:

**1. Audit — read and list, do not edit yet:**
- The `GET /api/auth/me` handler (likely `app/api/auth.py`): how it builds its
  response, and whether it already has a `db` session and access to
  `current_user.tenant_id`.
- `AuthService.authenticate_user` and the OAuth signup response builder — the
  exact dicts returned under the `user` key.
- The Pydantic response schema for the user object, if these responses are
  typed rather than raw dicts (`app/schemas/user.py` or similar).
- `app/services/branding.py`: confirm the `get_branding(db, tenant_id)`
  signature, that `.brand_name` is the correct field, and that it
  short-circuits to RYZE defaults with **no DB query** when
  `tenant_id == "ryze"` or `db is None` (so calling it on every `/auth/me` is
  cheap).
- List every distinct site that returns the authenticated user object, so the
  new field is added to all of them consistently. Missing one means the field
  is present on some logins and absent on others — call this out explicitly.

**2. Propose a plan and wait for confirmation.** Cover:
- Whether to add just `tenant_brand_name` or also `tenant_id`.
- Whether to add a small shared helper (e.g. `_auth_user_payload(db, user)`) so
  the 3 response sites can't drift, vs. inlining the resolver call in each.
  Recommend the helper if it reads cleanly.
- Whether the responses are schema-typed (add the field to the schema) or raw
  dicts (add the key).
- Confirm no migration is needed.

**3. After confirmation, write.** Per repo conventions: targeted edits where the
change is a narrow field addition; a complete replacement file only for any file
that needs broader restructuring. One concern per change; propose a commit point.

**4. Verify:**
- Run `python audit_tenant_coverage.py` and paste any new REVIEW / HARDCODED
  lines. Expected: none — this touches auth response construction, not
  tenant-owned data queries.
- Manually confirm the field resolves correctly:
  - a `ryze` user → `"RYZE.ai"`
  - a `green_path_recruiting` user → `"Green Path Recruiting"`
    (Renata Voss is the green_path test account).

**5. Deploy is manual.** Hand me the exact commands; do not run them. No
migration, so this is a plain code deploy:
```
# on server
git pull
sudo systemctl restart ryze-api
```

### History
- 2026-07-16 — Task created. Phase 1 of candidate portal white-labeling: surface
  the tenant brand name on the authenticated user object so the frontend Header
  (Phase 2) can render the firm's name instead of a hardcoded "RYZE.ai".
  Confirmed during brainstorming that the job-matches path is already
  tenant-scoped (`/api/candidates/me/job-matches` filters
  `WHERE tenant_id = :tenant` in both the pgvector and fallback paths;
  `/api/job-orders/open` likewise), so no work is needed there. Signup tenant
  resolution was already fixed (2026-07-15), so Renata resolves to
  `green_path_recruiting` and is a valid non-RYZE test case.
- 2026-07-16 — Audit + plan confirmed. Implemented: `UserResponse` gains
  `tenant_id` / `tenant_brand_name` (schema-typed, `app/schemas/user.py`);
  `AuthService._auth_user_payload(db, user)` helper added and used by
  `authenticate_user` (`/login`, `/login/form`) and `/oauth/complete-signup`;
  `/me` and `/register` build their response via
  `UserResponse.model_validate(user).model_copy(update={...})` — ORM instances
  are never mutated. `python audit_tenant_coverage.py` shows no new
  REVIEW/HARDCODED lines (the 2 existing REVIEW lines are pre-existing,
  unrelated `candidates.py` findings). Committed as a single commit, no
  migration required. Awaiting manual deploy + confirmation that brand name
  resolves correctly for a `ryze` user and for Renata (`green_path_recruiting`).
