# Changelog

Completed features/fixes move here from `current-feature.md` once Status = Completed — paste in the final Goals + full History, newest entry at the top. `current-feature.md` then resets to a blank template for the next item.

This file doubles as source material for the Build in Public series — each entry is close to script-ready: what the problem was, what changed, and the dated sequence of how it got fixed.

## Call intelligence on the candidate profile (completed 2026-07-15)
When a Zoom call ends, `_generate_summary_from_transcript` writes `meeting_summary`, `meeting_next_steps`, and `meeting_keywords` to the **booking** record, but the webhook only ever copied `meeting_transcript` onto the **candidate** record. Result: a recruiter looking at `/admin/candidates/:id` saw a raw transcript and no summary — the AI output from the call was invisible anywhere except the Admin Dashboard booking row and the Intelligence chat.

Surfaced the call intelligence on `GET /api/candidates/{candidate_id}` as five derived, read-only fields sourced from the linked booking (`call_summary`, `call_next_steps`, `call_keywords`, `call_date`, `call_booking_id`), resolved via the forward reference `Booking.candidate_id == candidate.id` (tenant-scoped, most recent booking with a non-null `meeting_summary`). No new columns, no migration — computed on read. Deliberately not wired into `GET /api/candidates/me` (recruiter-owned data, same boundary `CandidateSelfUpdate` already draws on write).

History:
- 2026-07-14 — Task created. Origin: recording a demo video for the Renata Voss call and noticed the profile page shows the raw transcript but no AI summary, and the roster's "AI Summary" column reads `ai_summary` (resume-derived, still `NULL`), which makes the call intelligence look like it never ran. It did run — it's just parked on the booking where nobody sees it.
- 2026-07-14 — Implemented. Added 5 `call_*` fields to `CandidateResponse` (`app/schemas/candidate.py`) and a `_attach_call_intelligence()` helper in `app/api/candidates.py`, wired only into `GET /api/candidates/{candidate_id}` (admin). Deliberately NOT wired into `GET /api/candidates/me` — meeting_summary/next_steps/keywords are recruiter-owned, same boundary `CandidateSelfUpdate` already draws on write. No migration, additive only. Flagged in-session (not fixed): `meeting_transcript` is already on `CandidateResponse` and already goes out over `/me` today — pre-existing, undecided whether intentional.
- 2026-07-15 — Verified against all five verification criteria and confirmed complete by user.

## Dead-code inventory & cleanup (completed 2026-07-08)
Ran `vulture` (min-confidence 80) plus a manual grep pass over `app/api/`, `app/services/`, `app/models/`, and the EP15–EP18 comment trail to find genuinely unreferenced code in the backend. Wrote a findings-only audit (`context/dead-code-audit.md`) first, then — after user review and per-step confirmation — deleted the confirmed-dead files and cleaned up flagged unused imports and a stale migration reference, one commit per step with an app-import check as the gate before each commit.

Findings: two duplicate/superseded files (`app/api/job_order_template.py`, an abandoned draft of `job_order_pdf_template.py`; `app/api/ai_parser.py`, a dead duplicate of `app/services/ai_parser.py`), one empty unused model (`app/models/blog.py`, never wired into `alembic/env.py`), two unused imports plus one shadowed import, one stale docstring reference to a migration file that no longer exists, and four unused root-level one-off scripts. The EP15–EP18 comment trail turned up no superseded scaffolding — all four epics are active, cumulative code.

History:
- 2026-07-08 — Ran `vulture app/ --min-confidence 80` (2 minor unused-import hits) and a full grep pass over `app/api/`, `app/services/`, `app/models/`, and the EP15–EP18 comment trail. Wrote `context/dead-code-audit.md`: 3 certain dead files (`app/api/job_order_template.py`, `app/api/ai_parser.py`, `app/models/blog.py`), 2 likely unused imports, 3 items flagged for manual review. No deletions made — findings only.
- 2026-07-08 — Step 1: deleted `app/api/job_order_template.py` (dead duplicate of `job_order_pdf_template.py`, Certain #1 in the audit). App import verified clean; user manually confirmed job-order PDF export still works before this was committed.
- 2026-07-08 — Step 2: deleted `app/api/ai_parser.py` (dead duplicate of `app/services/ai_parser.py`, Certain #2 in the audit). App import verified clean (94 routes, unchanged).
- 2026-07-08 — Step 3: deleted `app/models/blog.py` (empty file, never in `alembic/env.py`'s model imports, Certain #3 in the audit). No Alembic migration needed — nothing was ever backed by this model. App import verified clean (94 routes, unchanged).
- 2026-07-08 — Step 4: removed unused imports flagged by vulture (`OAuthUserComplete` and the shadowed `from time import timezone` in `app/api/auth.py`, `os` in `app/services/scheduler_runner.py` — audit items #4, #5, #8) and fixed the stale `migration_ep16.sql` docstring reference in `test_tenant_isolation.py` to point at the real Alembic migration (audit item #6). App import verified clean (94 routes, unchanged).
- 2026-07-08 — Step 5: deleted 4 unused root-level scripts — `audit_tenant_ep16.py`, `seed_tenant_b.py`, `seed_test_profiles.py`, `verify_test_profiles.py` (audit item #7; kept `seed_full.py`, `run_backfill.py`, `seed_cleanup.py`, `test_tenant_isolation.py`, `audit_tenant_coverage.py`). Known follow-up: `test_tenant_isolation.py` still references `seed_tenant_b.py` in its prerequisites docstring and a runtime guard message — user will fix that separately. App import verified clean (94 routes, unchanged). Ran `audit_tenant_coverage.py`: 88 endpoints, 69 SAFE, 17 PUBLIC/SKIP, 0 HARDCODED, 2 REVIEW (`candidates.py` `/me/photo`, `/me/banner` — pre-existing, unrelated to this cleanup, tracked separately).

<!--
Example entry format:

## Fix false positives in audit_tenant_coverage.py (completed 2026-07-XX)
Fixed the tenant audit script's detection logic so it recognizes aliased auth
dependencies and signature/token-based auth, eliminating 7 false-positive
REVIEW flags with no change to actual endpoint behavior.

History:
- 2026-07-07 — Ran full audit, found 8 REVIEW flags.
- 2026-07-07 — Verified 7 of 8 are false positives.
- 2026-07-08 — Script fixed, re-ran, confirmed 0 REVIEW flags.
-->
