# Dead-Code Audit

Findings-only inventory. **No files were deleted or modified as part of this audit** — every item below is a candidate for the user to review and act on separately.

Method: `vulture app/ --min-confidence 80`, plus a manual grep pass checking every `app/api/` file against `include_router` calls in `main.py`, and every `app/services/`/`app/models/` file for import references anywhere in `app/` or `alembic/`. False positives (Pydantic fields, SQLAlchemy columns, `Depends()` params, `alembic/env.py` model imports, standalone scripts, the scheduler entry point) were filtered out before anything below was listed as a candidate.

## Summary

| Confidence | Count |
|---|---|
| Certain | 3 |
| Likely | 2 |
| Needs my review | 3 |

---

## Certain

### 1. `app/api/job_order_template.py`
Dead duplicate of `app/api/job_order_pdf_template.py`.

**Evidence:**
- Its own header comment reads `# app/api/job_order_pdf_template.py` — the wrong filename, a copy-paste leftover from the file it duplicates.
- Zero import references anywhere: `grep -rn "job_order_template" app/ alembic/` matches nothing outside the file's own header.
- The live version is `app/api/job_order_pdf_template.py`, imported at `app/api/job_orders.py:27` (`from app.api.job_order_pdf_template import PDF_STYLE, PDF_HTML, render_pdf, ...`), which is wired into `main.py` via `job_orders_router`.
- Single orphaned commit (`2ac69ff working on fixing up job order PDF export`), never touched again while `job_order_pdf_template.py` has ongoing commits (`369a50c`, `4b602fa`, `5bcfc8c`). Diff shows `job_order_template.py` is an earlier/divergent draft missing later refinements (two-column flex layout, `break-inside: avoid`).

**Recommendation:** safe to delete once reviewed — nothing imports it.

### 2. `app/api/ai_parser.py`
Dead duplicate of `app/services/ai_parser.py`.

**Evidence:**
- Its own header comment reads `# app/services/ai_parser.py` — again, the wrong path, copy-paste leftover.
- Defines no `APIRouter` / route decorators, and isn't registered in `main.py`.
- Zero import references anywhere: `grep -rn "api.ai_parser\|from app.api.ai_parser"` matches nothing.
- The live version is `app/services/ai_parser.py`, imported by `app/api/employer_profiles.py`, `app/api/job_orders.py`, and `app/api/candidates.py`.
- Side note: `audit_tenant_coverage.py`'s `SKIP_FILES = {"webhooks.py", "blog.py", "contact.py", "ai_parser.py"}` includes `"ai_parser.py"`, but since that script only scans `app/api/`, this entry is effectively inert — it "skips" a file that defines zero routes to begin with, not a real endpoint. Not actionable here (`audit_tenant_coverage.py` is out of scope for this task), just noted for whoever next touches that script.

**Recommendation:** safe to delete once reviewed — nothing imports it.

### 3. `app/models/blog.py`
Empty file (0 bytes).

**Evidence:**
- `wc -l app/models/blog.py` → 0 lines.
- Not imported anywhere in `app/` or `alembic/` — and unlike every other model, it's **not** in `alembic/env.py`'s explicit model-import list (`Contact`, `User`, `EmployerProfile`, `Booking`, `Waitlist`, `JobOrder`, `Candidate`, `WebhookLog`, `Tenant`, `ChatSession`, `ChatMessage` are all there; no `Blog`).
- `app/api/blog.py` (the router that *is* registered in `main.py`, prefix `/blog`) doesn't touch this model at all — it's a 9-line stub with a single placeholder endpoint (`GET /` → `{"message": "Blog API Root"}`), no DB access.
- Only one commit ever touched it: the initial commit (`4537f70`).

**Recommendation:** safe to delete — it has no content and no references. Separately worth knowing (not a deletion candidate, just context): `app/api/blog.py` itself is a live but non-functional stub — it's registered and reachable, just doesn't do anything yet.

---

## Likely

### 4. `app/api/auth.py:17` — unused import `OAuthUserComplete`
**Evidence:** `vulture` flagged at 90% confidence. `grep -n "OAuthUserComplete" app/api/auth.py` matches only the import line itself — never referenced in the rest of the file.

**Recommendation:** likely safe to remove the import line. Low risk, single-line change.

### 5. `app/services/scheduler_runner.py:12` — unused import `os`
**Evidence:** `vulture` flagged at 90% confidence. `grep -n "\bos\." app/services/scheduler_runner.py` returns nothing — `os` is imported but never referenced.

**Recommendation:** likely safe to remove the import line. Note: this is a narrower finding than the file itself — `scheduler_runner.py` as a whole is **not** dead code (see Filtered False Positives below), only this one import inside it.

---

## Needs my review

### 6. `test_tenant_isolation.py:21` — stale reference to `migration_ep16.sql`
**Evidence:** the file's "Prerequisites" docstring says `migration_ep16.sql must have been run`, but no file named `migration_ep16.sql` exists anywhere in the repo. The real EP16 schema change lives in the Alembic migration `alembic/versions/11ae0fa76851_ep16_add_tenant_id_to_bookings_backfill_.py`. This looks like the script's docstring was never updated after the raw-SQL migration was replaced by the proper Alembic one.

**Not dead code** — just a stale comment in a still-relevant prerequisites list. Flagged so whoever next runs this script isn't sent looking for a file that doesn't exist.

### 7. Root-level one-off scripts: `test_tenant_isolation.py`, `audit_tenant_ep16.py`, `seed_tenant_b.py`
**Evidence:** all three sit outside `app/`, so they were outside this audit's explicit `vulture`/grep scope (which targeted `app/` and `alembic/`). None are imported anywhere (`grep -rln "test_tenant_isolation\|audit_tenant_ep16\|seed_tenant_b" app/ alembic/` → no hits), which is expected for standalone scripts run directly (`python script.py`) — that alone doesn't make them dead.

**Not verified either way** — whether these are still actively run (e.g. as regression checks after tenant-isolation changes) wasn't checked as part of this audit. Flagged because one-off root-level scripts are the kind of thing that tends to accumulate as genuine dead code over time without ever being explicitly deprecated. Recommend the user confirm whether these are still part of the workflow before deciding.

### 8. `app/api/auth.py:2` — `from time import timezone` immediately shadowed by `from datetime import datetime, timezone` on line 3
**Evidence:** not flagged by vulture (it's a valid, used name — `timezone` — just bound twice in a row), found incidentally while inspecting the `OAuthUserComplete` finding above. `time.timezone` is an integer constant, not the `datetime.timezone` class actually used later in the file; the second import silently overrides the first, so the first import is functionally inert.

**Not asserted as a bug** — behavior is correct today because the second binding wins, but the first import line does nothing and reads as either a leftover or a mistake. Flagged for the user's judgment, not included in the Certain/Likely counts since it's not "dead code" in the file/import sense the rest of this audit covers.

---

## EP15–EP18 comment trail

Searched all patterns (`EP15`, `EP-15`, `EP15:`, `[EP15]`, `(EP15)`, `# EP15`, plus git log `--grep`) across `app/`, `alembic/`, `context/`, and git history. **No superseded scaffolding found.** EP15 (candidate matching), EP16 (multi-tenant isolation), EP17 (billing/onboarding/candidate flow), EP18 (candidate stub/profile/user-linking) are sequential, cumulative, currently-live features — each later epic builds directly on the previous one's code rather than replacing it. Zero instances of "deprecated," "superseded," "no longer used," "TODO: remove," or equivalent language attached to any EP-tagged comment. The only near-legacy phrase found (`app/core/deps.py:84`, "legacy or pre-EP17 account") refers to old *data* (accounts created before EP17 existed), not old *code* — it's a live backward-compatibility branch, not dead code.

---

## Filtered false positives (checked, confirmed NOT dead)

- **`app/services/scheduler_runner.py`** (the file, not the one bad import above) — zero import references anywhere, but this is expected: it's the APScheduler systemd entry point (`ryze-scheduler.service`), started directly by systemd rather than imported by any other module. Per CLAUDE.md, this is explicitly not dead code.
- **`app/api/candidate_pdf_template.py`, `app/api/employer_pdf_template.py`, `app/api/job_order_pdf_template.py`** — not registered via `include_router` (they define no router), but all three are live via direct import from their sibling router files (`candidates.py`, `employer_profiles.py`, `job_orders.py` respectively).
- All other `app/services/*.py` and `app/models/*.py` files have at least one import reference in `app/` or `alembic/` (checked individually — see table below).

| services file | referencing files | models file | referencing files |
|---|---|---|---|
| ai_brief | 1 | booking | 5 |
| ai_parser | 3 | candidate | 8 |
| auth | 2 | chat_message | 2 |
| branding | 2 | chat_session | 2 |
| calendar | 1 | contact | 2 |
| candidate_stub | 1 | employer_profile | 7 |
| email | 2 | job_order | 6 |
| embedding_service | 7 | tenant | 6 |
| notifications | 2 | user | 15 |
| scheduler | 1 | waitlist | 2 |
| spaces | 2 | webhook_log | 2 |
| zoom | 2 | *(blog → 0, see Certain #3)* | |
| *(scheduler_runner → 0, false positive above)* | | | |

## Raw vulture output

```
$ vulture app/ --min-confidence 80
app/api/auth.py:17: unused import 'OAuthUserComplete' (90% confidence)
app/services/scheduler_runner.py:12: unused import 'os' (90% confidence)
```
