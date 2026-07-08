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
