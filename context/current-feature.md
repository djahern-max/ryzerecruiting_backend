# Current Feature

<!-- Feature/fix name -->
Fix false positives in audit_tenant_coverage.py

## Status
<!-- Not Started | In Progress | Completed -->
Not Started

## Goals
<!-- Goals & requirements -->
The tenant audit script currently flags 8 endpoints as REVIEW, but 7 are false positives caused by the script's own detection limitations — not real tenant-isolation gaps. Fix the detection logic so future runs only flag genuine issues, without changing any endpoint behavior.

Known gaps in the script:
- Doesn't recognize `get_any_authenticated_user` (an aliased import of `get_current_user` from `app.api.auth`) as an auth dependency.
- Doesn't recognize `get_current_superuser` as an auth dependency.
- Has no concept of signature-based auth (Stripe webhook) or token-based auth (magic-link endpoints) as valid non-`Depends()` protection.

## Related Files
<!-- Files this touches -->
- `audit_tenant_coverage.py` — the only file this task should change
- Reference examples (don't modify, just use as ground truth):
  - `app/api/billing.py` — `POST /webhook`, protected by Stripe signature verification
  - `app/api/bookings.py` — `POST /respond/confirm`, protected by single-use `response_token`
  - `app/api/db_explorer.py` — all endpoints protected by `get_current_superuser`
  - `app/api/candidates.py` — `/me`, `/me/job-matches` protected by `get_any_authenticated_user`

## Verification
<!-- How we'll know it worked -->
Re-run `python audit_tenant_coverage.py` after the fix. Expect 0 REVIEW flags (down from 8), same 54 SAFE / 26 PUBLIC-SKIP counts, 0 HARDCODED. No endpoint behavior should change — this is a detection-script-only fix.

## Notes
<!-- Any extra notes -->
Don't touch any actual API endpoint logic for this task — scope is the audit script only.

This History section doubles as raw material for the Build in Public series — when this moves to `CHANGELOG.md`, it's ready to turn into a video script without reconstructing the timeline from memory.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-07 — Ran full audit: 54 SAFE, 26 PUBLIC/SKIP, 0 HARDCODED, 8 REVIEW flagged.
- 2026-07-07 — Manually verified all 8 REVIEW flags against source — confirmed 7 are false positives (see Related Files above), 0 are real tenant-isolation gaps.
