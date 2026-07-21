# Current Feature

Match score calibration & distance-operator unification

## Status
Implemented — awaiting manual verification (dashboard, chat, employer side per Verification steps below)

## Goals
Match *ranking* is correct everywhere, but displayed scores are misleadingly
low on the candidate side (a strong match shows 12%). Root cause: candidate-
side paths compute `score = 1 - L2_distance` (`<->`), and L2 between unit-
norm OpenAI embeddings runs ~0.85-1.0 even for strong matches, crushing all
scores toward 0. The employer-side path uses cosine (`<=>`), so the two
sides also disagree on the same pairing. This task unifies the operator and
calibrates the displayed score. This implements the deferred refactor logged
in CHANGELOG/History (shared helper + `<->`/`<=>` unification).

Requirements:
1. Create ONE shared scoring helper (suggested: `app/services/matching.py`)
   used by all three match paths:
   - `GET /api/candidates/me/job-matches` (`app/api/candidates.py`)
   - `GET /api/job-orders/{id}/candidate-matches` (`app/api/job_orders.py`)
   - `tool_match_jobs_to_candidate` (`app/api/chat.py`)
2. All three use cosine distance (`<=>`) in their raw SQL. ORDER BY stays
   distance ascending — ranking must not change.
3. Score formula, in the shared helper:
   - `cos_sim = 1.0 - cos_distance`
   - Calibrated display score:
     `score = clamp((cos_sim - SIM_FLOOR) / (SIM_CEIL - SIM_FLOOR), 0.0, 1.0)`
   - `SIM_FLOOR = 0.25`, `SIM_CEIL = 0.75` as module-level constants with a
     comment explaining they're empirical calibration bounds for
     text-embedding-3-small profile-vs-job text, tunable in one place.
   - Round to 4 decimals as today. Response field names unchanged
     (`match_score`) — no schema or frontend changes.
4. The transform is monotonic, so ordering is provably identical to today.
   Do not re-rank, re-embed, or touch embeddings.
5. Remove the now-dead `round(max(0.0, 1.0 - distance), 4)` pattern from all
   three call sites in favor of the helper.

Out of scope:
- No frontend changes (UI already renders `match_score` as a percent).
- No migration, no model changes.
- No changes to embedding generation or `_vector_search` in chat.py (query-
  text search is a different concern from stored-embedding matching).

## Related Files
- `app/services/matching.py` — NEW shared helper (constants + score fn)
- `app/api/candidates.py` — `get_my_job_matches`: switch `<->` to `<=>`,
  use helper
- `app/api/job_orders.py` — `get_candidate_matches_for_job`: already `<=>`,
  switch score computation to helper
- `app/api/chat.py` — `tool_match_jobs_to_candidate`: switch `<->` to `<=>`,
  use helper

## Verification
1. `python audit_tenant_coverage.py` — no new REVIEW/HARDCODED lines.
2. Renata's dashboard (tenant `green_path_recruiting`, jobs already seeded):
   - Ordering identical to before: Greenscene Landscape Designer #1,
     Irrigation Technician last.
   - Greenscene shows a plausible strong score (expect roughly 60-85%);
     Garden Center / Irrigation show clearly weak scores; spread is visible.
3. Intelligence chat as dane@greenpathrecruiting.com: "Show me matches for
   Renata Voss" returns the same scores as the dashboard (cross-side
   consistency, which previously did NOT hold).
4. Employer side: Greenscene job's candidate-matches still ranks Renata
   first with a sensible score.
5. Grep check: no remaining `1.0 - distance` score computations against
   `<->` for match display anywhere in app/api/.

## Notes
- Rationale: `1 - L2` mislabels the scale (L2 range 0-2 on unit vectors);
  cosine similarity + empirical floor/ceiling calibration is the honest,
  standard fix. Ranking semantics unchanged.
- If observed scores cluster oddly after the switch, tune SIM_FLOOR/SIM_CEIL
  only — do not reintroduce per-endpoint formulas.
- Demo context: scores appear on camera; verify on production before
  filming.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-21: Created `app/services/matching.py` with `SIM_FLOOR`/`SIM_CEIL`
  constants and `compute_match_score(cos_distance)`. Switched `<->` to `<=>`
  in candidates.py (`get_my_job_matches`) and chat.py
  (`tool_match_jobs_to_candidate`); job_orders.py already used `<=>`. All
  three now call the shared helper instead of the inline
  `round(max(0.0, 1.0 - distance), 4)` pattern. Removed the stale
  "deliberately inline" docstring note on `tool_match_jobs_to_candidate`.
  `audit_tenant_coverage.py` shows the same 2 pre-existing REVIEW lines
  (candidates.py `/me/photo`, `/me/banner` — unrelated, unchanged by this
  work) both before and after the diff; no new REVIEW/HARDCODED lines.
  Deferred: `tool_search_candidates`/`tool_search_employers`/
  `tool_search_job_orders`/`_vector_search` in chat.py still use the old
  uncalibrated `1.0 - distance` formula over `<=>` — left untouched per
  scope, but they'd need their own floor/ceiling constants since
  query-text-vs-profile similarity has a different natural range than
  profile-vs-job similarity. Not yet manually verified against the
  Verification checklist (Renata/Greenscene ordering and scores, chat
  cross-check, employer side).
