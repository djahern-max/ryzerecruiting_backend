# Current Feature

<!-- Feature/fix name -->
Free trial: 30 days -> 60 days

## Status
<!-- Not Started | In Progress | Completed -->
Completed

## Goals
<!-- Goals & requirements -->
- Change the free trial length from 30 to 60 days everywhere it's set or described.
- Backend: `timedelta(days=30)` in both trial-creation paths, plus docstrings/comments mentioning "30-day".
- Backend: welcome email copy (both invite + self-serve variants) — subject lines and body text.
- Frontend (separate repo, `../frontend`): InviteForm admin description text, UpgradePage expired-trial message, SignupFirm page subhead (make "60-day free trial" an explicit selling point there).
- Audit for other literal `30`s tied to trials before changing (done — see Notes).

## Related Files
- `app/api/auth.py` (signup-firm trial creation + docstring)
- `app/api/admin_invite.py` (admin invite trial creation + docstring)
- `app/services/email.py` (invite welcome email + self-serve welcome email, both subject + body)
- `../frontend/src/pages/admin/InviteForm.jsx` (two "30-day" mentions)
- `../frontend/src/pages/UpgradePage.jsx` ("your 30-day free trial has expired")
- `../frontend/src/pages/SignupFirm.jsx` (subhead — add 60-day trial as a selling point)

## Verification
- `grep -rn "30.day\|days=30" app/` (backend) and frontend `src/pages` returns no remaining trial-related hits.
- Manually sanity-check both welcome email templates render with "60-day" copy.

## Notes
- `context/CHANGELOG.md` and `../frontend/src/pages/SaasLanding.jsx` (EP16/EP17 dev-log entries) also mention "30-day trial" — these are historical/dated records of what was true when that work shipped, not living product copy. Left unchanged, same treatment as CHANGELOG.md entries generally.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-26: Task started — audited for all trial-related "30" literals across backend + frontend, updated this file before coding.
- 2026-07-26: Changed both `timedelta(days=30)` calls (auth.py, admin_invite.py) and their docstrings to 60. Updated both welcome email variants in email.py (subject + body, 4 spots). Updated InviteForm.jsx (2 spots), UpgradePage.jsx, and SignupFirm.jsx subhead (added "60-day free trial" as a selling point). Ran audit_tenant_coverage.py — no new REVIEW/HARDCODED findings on auth.py/admin_invite.py. Backend committed (`1d47499`), frontend committed separately (`78d9716`, different repo).
