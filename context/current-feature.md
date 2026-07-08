# Current Feature

<!-- Feature/fix name -->
Dead-code inventory

## Status
<!-- Not Started | In Progress | Completed -->
In Progress

## Goals
<!-- Goals & requirements -->
Produce `context/dead-code-audit.md`, a findings-only inventory of dead-code candidates in `app/`. **No deletions this session** — the goal is a documented, evidence-backed list the user can act on later.

Scope:
- Run `vulture` (min-confidence 80) against `app/`.
- Grep for `app/api/*.py` files not registered via `include_router` in `main.py`, and `app/services/`/`app/models/` files with zero import references anywhere in `app/` or `alembic/`.
- Resolve the `job_order_template.py` vs `job_order_pdf_template.py` duplicate suspicion.
- Filter false positives: Pydantic fields, SQLAlchemy columns, `Depends()` params, `alembic/env.py` model imports, standalone scripts, and the scheduler service entry point are NOT dead code.
- Follow the EP15–EP18 comment trail for superseded scaffolding.

## Related Files
<!-- Files this touches -->
- `context/dead-code-audit.md` — the output of this task (new file)
- `app/api/`, `app/services/`, `app/models/` — read-only investigation targets
- `audit_tenant_coverage.py` — reference only, not modified (that's the separate, prior in-progress task below)

## Verification
<!-- How we'll know it worked -->
`git status`/`git diff` after this session shows changes only in `context/current-feature.md` and `context/dead-code-audit.md` — zero changes under `app/`, `alembic/`, or any other source directory. Every candidate in the audit doc has cited evidence (grep output, vulture line, or git log) and an explicit confidence tag, not a bare assertion.

## Notes
<!-- Any extra notes -->
This replaces the prior in-progress task tracked here ("Fix false positives in audit_tenant_coverage.py", Status: Not Started, 2 History entries from 2026-07-07). That work was not completed/confirmed, so it never moved to CHANGELOG.md — its content is preserved in git history (commit `b61acc0`) and can be restored from there when that task resumes.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-08 — Ran `vulture app/ --min-confidence 80` (2 minor unused-import hits) and a full grep pass over `app/api/`, `app/services/`, `app/models/`, and the EP15–EP18 comment trail. Wrote `context/dead-code-audit.md`: 3 certain dead files (`app/api/job_order_template.py`, `app/api/ai_parser.py`, `app/models/blog.py`), 2 likely unused imports, 3 items flagged for manual review. No deletions made — findings only.
- 2026-07-08 — Step 1: deleted `app/api/job_order_template.py` (dead duplicate of `job_order_pdf_template.py`, Certain #1 in the audit). App import verified clean; user manually confirmed job-order PDF export still works before this was committed.
- 2026-07-08 — Step 2: deleted `app/api/ai_parser.py` (dead duplicate of `app/services/ai_parser.py`, Certain #2 in the audit). App import verified clean (94 routes, unchanged).
- 2026-07-08 — Step 3: deleted `app/models/blog.py` (empty file, never in `alembic/env.py`'s model imports, Certain #3 in the audit). No Alembic migration needed — nothing was ever backed by this model. App import verified clean (94 routes, unchanged).
- 2026-07-08 — Step 4: removed unused imports flagged by vulture (`OAuthUserComplete` and the shadowed `from time import timezone` in `app/api/auth.py`, `os` in `app/services/scheduler_runner.py` — audit items #4, #5, #8) and fixed the stale `migration_ep16.sql` docstring reference in `test_tenant_isolation.py` to point at the real Alembic migration (audit item #6). App import verified clean (94 routes, unchanged).
- 2026-07-08 — Step 5: deleted 4 unused root-level scripts — `audit_tenant_ep16.py`, `seed_tenant_b.py`, `seed_test_profiles.py`, `verify_test_profiles.py` (audit item #7; kept `seed_full.py`, `run_backfill.py`, `seed_cleanup.py`, `test_tenant_isolation.py`, `audit_tenant_coverage.py`). Known follow-up: `test_tenant_isolation.py` still references `seed_tenant_b.py` in its prerequisites docstring and a runtime guard message — user will fix that separately. App import verified clean (94 routes, unchanged). Ran `audit_tenant_coverage.py`: 88 endpoints, 69 SAFE, 17 PUBLIC/SKIP, 0 HARDCODED, 2 REVIEW (`candidates.py` `/me/photo`, `/me/banner` — pre-existing, unrelated to this cleanup, tracked separately).
