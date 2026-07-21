# current-feature.md

## Feature: notifications@ sender + lock down from_email (backend)

**Status:** Not Started
**Repo:** ryzerecruiting_backend
**Depends on:** notifications@ryze.ai exists as a forwarding alias in the
ryze.ai mail setup (I'm creating it). ryze.ai is already Resend-verified, so
any local-part sends without re-verification.

### Goal
Outbound mail should come from a neutral infrastructure address
(notifications@ryze.ai) instead of dane@ryze.ai, WITHOUT moving ryze-tenant
reply-to/support routing away from my real inbox — and tenant admins should
no longer be able to set from_email at all (an unverified domain there kills
all their outbound mail; we just hit this live with Green Path).

Two concerns, two commits:

### Concern 1 — split sender config from reply config → commit 1
- `app/core/config.py`: add `REPLY_TO_EMAIL` setting. Default it to
  FROM_EMAIL's current value pattern so a missing env var changes nothing.
- `app/services/branding.py` `_ryze_defaults`: `from_email` stays
  `settings.FROM_EMAIL`; `reply_to_email` and `support_email` become
  `settings.REPLY_TO_EMAIL`. `admin_email` stays `settings.ADMIN_EMAIL`.
- No change to per-tenant override resolution (`pick(...)`) — tenant
  overrides still win field-by-field.
- Env change is mine to run: give me the exact lines for the server env file
  (`FROM_EMAIL=notifications@ryze.ai`, `REPLY_TO_EMAIL=dane@ryze.ai`) and
  the restart command. Do not run them.

### Concern 2 — remove from_email from tenant settings → commit 2
- `app/api/settings.py`: remove `from_email` from `TenantBrandingUpdate`.
  IMPORTANT deploy-safety: the deployed frontend sends all fields including
  from_email, and the model has extra="forbid" — a hard removal 422s every
  branding save until the frontend ships. So: accept-and-ignore it during
  transition (keep the field on the update model but skip it in the
  setattr loop, with a comment saying it's removable after the frontend
  deploy), OR flip extra to "ignore" for this model. Propose which in the
  audit; either is fine, silent-drop is not allowed to persist the value.
- Remove `from_email` from `TenantBrandingResponse` and
  `_build_tenant_branding_response`.
- Data cleanup command for me to run: `UPDATE tenants SET from_email = NULL;`
  (Green Path's is already cleared; this catches future rows seeded before
  the frontend ships).
- `get_branding` keeps reading `tenant.from_email` — harmless with the
  column NULL everywhere, and preserves the future verified-domain model.
  Do NOT drop the column or write a migration.

### Explicitly OUT of scope
- No migration, no model changes.
- No changes to email.py senders or notifications.py.
- The from_email column stays in the DB for the future per-domain model.

## Verification
1. `python audit_tenant_coverage.py` — no new lines.
2. After env change + restart: trigger a candidate-interest email as Renata
   (clear her job_interests row first) → arrives at
   dane@greenpathrecruiting.com FROM "Green Path Recruiting
   <notifications@ryze.ai>", reply-to renata.voss.design@gmail.com.
3. PATCH /api/settings/tenant with a from_email in the payload → succeeds
   (transition tolerance) but the DB value stays NULL.
4. A ryze-tenant booking email's reply-to still resolves to dane@ryze.ai
   (REPLY_TO_EMAIL), not notifications@.

## History
<!-- Keep this updated. Earliest to latest -->
