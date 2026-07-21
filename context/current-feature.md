# Current Feature

Intelligence chat tool: `match_jobs_to_candidate` (candidate → jobs matching)

## Status
Not Started

## Goals
Add a new tool to RYZE Intelligence (`app/api/chat.py`) so a recruiter can ask
"Show me matches for Renata Voss" and get open job orders ranked by the
candidate's **stored profile embedding** — the same pgvector math as
`GET /api/candidates/me/job-matches` — not a text-query search.

Requirements:
1. New tool schema `match_jobs_to_candidate` in the `TOOLS` list.
   - Inputs: `name` (required, candidate name or partial name), `limit`
     (optional, default 5).
   - Description should tell Claude to use it for queries like "show me
     matches for <name>", "what roles fit <name>", "which open jobs should
     we pitch to <name>".
2. New tool function `tool_match_jobs_to_candidate(db, name, limit, tenant_id)`:
   - Look up candidate via `Candidate.name.ilike(f"%{name}%")` scoped to
     `tenant_id` (mirror `tool_get_candidate_by_name`).
   - If no candidate: return `{"error": "No candidate found matching '<name>'."}`.
   - If `candidate.embedding is None`: return an error saying the candidate
     has no embedding yet.
   - Otherwise run the same raw SQL pattern as `get_my_job_matches` in
     `app/api/candidates.py`: `embedding <-> '<vector>'::vector` distance
     against `job_orders` WHERE `tenant_id = :tenant AND status = 'open'
     AND embedding IS NOT NULL`, ordered by distance, limited.
   - Return a dict with key **`"job_orders"`** (list of dicts: id, title,
     location, salary_min, salary_max, requirements, status, match_score
     where match_score = `round(max(0.0, 1.0 - distance), 4)`), plus
     `"count"` and `"candidate_name"`.
   - The `"job_orders"` key is required so the existing streaming loop
     collects it and ChatPage.jsx renders inline job order cards — do NOT
     invent a new key.
3. Register the tool in `make_tool_dispatch()`, threading the `tenant_id`
   param exactly like the existing entries — no hardcoded `RYZE_TENANT`.
4. If `TOOL_STATUS_MESSAGES` exists, add:
   `"match_jobs_to_candidate": "Matching open roles to candidate..."`.

Out of scope (do NOT bundle):
- Do not modify `tool_match_candidates_to_job` (known to be a text-search
  alias — separate task later if wanted).
- No frontend changes — ChatPage.jsx already renders `job_orders`.
- No schema/model changes, no Alembic migration needed.

## Related Files
- `app/api/chat.py` — all changes live here (TOOLS list, new tool function,
  `make_tool_dispatch`, optionally TOOL_STATUS_MESSAGES)
- `app/api/candidates.py` — reference only: `get_my_job_matches` is the SQL
  pattern to mirror
- `app/models/candidate.py`, `app/models/job_order.py` — reference only
- `src/pages/ChatPage.jsx` (frontend repo) — reference only: confirms
  `job_orders` key renders inline cards

## Verification
1. `python audit_tenant_coverage.py` — no new REVIEW/HARDCODED lines from
   this change.
2. Restart API locally, log in as admin, open `/admin/chat`.
3. Ask: "Show me matches for Renata Voss."
   - Claude calls `match_jobs_to_candidate` (visible in server logs:
     `Chat tool call: match_jobs_to_candidate(...)`).
   - Response includes ranked landscaping job orders with match scores and
     inline job order cards render under the answer.
4. Cross-check: scores/ordering agree with Renata's candidate dashboard
   ("Open Opportunities" section), since both use her embedding with the
   `<->` operator against the same open job orders.
5. Negative test: "Show me matches for Bob Fakename" returns a clean
   "no candidate found" style answer, no traceback.

## Notes
- Purpose: demo video shot — recruiter asks Intelligence for a candidate's
  matches and gets visual ranked job cards.
- Depends on seeded data: run `seed_landscaping_jobs.py` first so open,
  embedded landscaping job orders exist (script inserts + embeds them).
- Renata's candidate record must have a non-NULL embedding or the tool will
  return the "no embedding" error — re-save her profile if needed.
- `get_my_job_matches` uses `<->` (L2) while the employer-side
  candidate-matches endpoint uses `<=>` (cosine). Mirror `<->` here so chat
  scores match the candidate dashboard exactly.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-21 — Audit confirmed: `app/api/chat.py` tool conventions and
  `get_my_job_matches` (`app/api/candidates.py`) SQL pattern both match the
  spec exactly. Two calls made and confirmed before implementation: (1)
  multi-match tie-break for `match_jobs_to_candidate` is
  `.order_by(Candidate.id.desc()).first()`, with a `"note"` field on the
  result dict disclosing which candidate was picked when the name matched
  more than one; (2) the raw-SQL block is copied inline into `chat.py` rather
  than extracted to a shared helper — `candidates.py` is untouched.
  Implemented: `TOOL_STATUS_MESSAGES` entry, `match_jobs_to_candidate` tool
  schema in `TOOLS`, `tool_match_jobs_to_candidate()` function, and its
  registration in `make_tool_dispatch()`. `python audit_tenant_coverage.py`
  shows no new REVIEW/HARDCODED lines (same 2 pre-existing, unrelated
  `candidates.py` findings as before).
  **Deferred refactor (not done here):** `tool_match_jobs_to_candidate`
  duplicates `get_my_job_matches`'s raw-SQL job-ranking block verbatim, and
  the codebase now has two different vector operators for conceptually
  similar matches — `get_my_job_matches`/this new tool use `<->` (L2) while
  the employer-side candidate-matches endpoint and `chat.py`'s
  `_vector_search` helper use `<=>` (cosine). A future pass could extract
  the L2 ranking-by-stored-embedding logic into one shared helper and decide
  whether L2 vs. cosine should be unified platform-wide, or is intentionally
  different per use case — worth deciding deliberately rather than by
  accretion.
- 2026-07-21 — Verification (steps 2–5). Reviewed `seed_landscaping_jobs.py`
  against models/embedding service before running it: found a real bug —
  missing `from app.models.user import User` import, so `EmployerProfile.user_id`'s
  FK to `users` failed to resolve at flush time (same class of issue as the
  `test_signup_tenant_resolution.py` FK note in `CHANGELOG.md`). Fixed with a
  one-line import (unrelated to this feature, but blocking). Ran the script
  locally: created Greenscene employer profile #4, 6 open job orders (ids
  1–6), all embedded. Confirmed local dev DB has 0 real candidates and 0
  users (no Renata locally) — used the fallback the user authorized: created
  a throwaway synthetic candidate with a landscape-designer profile, embedded
  it, and called `tool_match_jobs_to_candidate()` directly. Its `job_orders`
  order and `match_score` values were byte-for-byte identical to an
  independently run copy of `get_my_job_matches`'s raw SQL against the same
  embedding — confirms the two are mathematically equivalent, which is the
  actual property step 4 cared about (Renata's real dashboard couldn't be
  used directly since she doesn't exist in the local DB). Also exercised the
  multi-match tie-break with two synthetic same-prefix candidates — picked
  the higher id and returned the `"note"` field as designed. Went further
  than the direct-call fallback: started the local API (`uvicorn`), created a
  throwaway admin user + JWT, and hit the live streaming `/api/chat` endpoint
  for real. Server log confirms `Chat tool call: match_jobs_to_candidate(...)
  tenant=ryze`, response included the `"Matching open roles to
  candidate..."` status line, and the trailing `__DATA__` chunk carried
  ranked `job_orders` ids. Negative test ("Show me matches for Bob
  Fakename") returned a clean "no record" prose answer, `job_orders: null`,
  HTTP 200, no traceback. All scratch rows (admin user, synthetic
  candidates) deleted after; the 6 seeded landscaping job orders and the
  Greenscene employer profile were left in place as the intended persistent
  demo data. Local verification passes — not deployed.
