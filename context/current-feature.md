# Current Feature

Parked follow-ups — rate-limit logging + candidates.py tenant-scoping review

## Status
Completed — awaiting user confirmation

## Goals
1. Rate-limit 429 branches in `signup-firm` and `demo-request` currently log nothing; honeypot trips already log client IP via `logger.warning`. Add the same treatment to both 429 branches.
2. Investigate the two audit REVIEW lines: `candidates.py` `POST /me/photo` and `POST /me/banner` ("authenticated + touches tenant data but no tenant_id filter"). Audit first and report: genuinely unscoped (cross-tenant risk) or false positives (operate on current_user's own candidate row, tenant scoping implicit)? Do NOT change code until findings are reported and confirmed — if false positives, fix may be an audit-script annotation, not an endpoint change.

## Related Files
- `app/api/auth.py` (signup-firm rate limit branch)
- `app/api/demo_request.py` or wherever `create_demo_request` lives (demo-request rate limit branch)
- `app/services/rate_limit.py`
- `app/api/candidates.py` (`/me/photo`, `/me/banner`)
- `audit_tenant_coverage.py`

## Verification
- `python audit_tenant_coverage.py` after any endpoint change, no new REVIEW/HARDCODED lines
- Confirm rate-limit log lines fire on 429 (manual trip or code inspection)

## Notes
- Scope OUT: orphaned `/api/waitlist` endpoint + `Waitlist` model (frontend removed its only caller in the landing revision) — parked deprecation decision for user, do not touch.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-26 — Task loaded from parked follow-ups (rate-limit logging noted in demo-request/signup-firm session; candidates.py REVIEW lines noted across multiple prior sessions).
- 2026-07-26 — Audited both items before writing code. (1) Confirmed exact 429 branches in `auth.py:114-120` (signup_firm) and `demo_request.py:27-31` (create_demo_request) — neither logs, matching honeypot's `logger.warning` precedent one line above each. (2) Traced `candidates.py`'s `/me/photo`/`/me/banner` through `_resolve_candidate_for_user` (line 88): first lookup branch (`Candidate.user_id == current_user.id`, line 91) has no textual tenant_id filter, which is what trips the audit script's per-function regex scan. But grepped the whole codebase for every write of `Candidate.user_id` — the only writer in the entire app is line 105, inside the same helper, gated behind `Candidate.tenant_id == tenant_id`. Confirmed no schema (`CandidateCreate`/`CandidateSelfUpdate`) exposes `user_id`, and no endpoint reassigns `User.tenant_id` post-creation. Reported findings to user as a false positive — audit script doesn't follow cross-function calls — recommending an annotation, not an endpoint change. Awaiting user confirmation before any code change on either item.
- 2026-07-26 — User confirmed both, with amendments: rate-limit logs include email (mirroring honeypot format, rationale: legit retriers can trip 5/hr and email is the only follow-up handle); candidates.py gets the explicit `tenant_id == tenant_id` filter added to branch 1 as defense-in-depth (read-time enforcement of what's currently a write-time-only invariant) plus a comment citing the invariant, and the audit-script carve-out must use a distinct label rather than folding into plain SAFE. Split into 2 commits as directed.
- 2026-07-26 — Commit 1 (`9cbaf51`): added `logger.warning` with IP + email to both 429 branches (`auth.py`, `demo_request.py`). App-import clean, `audit_tenant_coverage.py` unchanged (same 2 pre-existing candidates.py REVIEW lines).
- 2026-07-26 — Commit 2 (`cce6d30`): added `Candidate.tenant_id == tenant_id` filter + invariant comment to `_resolve_candidate_for_user`'s branch 1 (`candidates.py`); added `HELPER_SAFE_FUNCS` set + distinct "Tenant scoping delegated to helper: <name>" SAFE label to `audit_tenant_coverage.py`, wired in ahead of the REVIEW fallback. App-import clean. `audit_tenant_coverage.py` now reports **zero REVIEW lines** (was 2) — `/me/photo` and `/me/banner` both show the new delegated-scoping label instead. Full-run summary: 94 endpoints, 75 SAFE, 19 Public/Skip, 0 Hardcoded, 0 Needs review.
- 2026-07-26 — Both commits done, verified, task complete pending user's explicit confirmation to archive per session workflow.
