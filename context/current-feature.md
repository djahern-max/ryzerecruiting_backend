# Current Feature

Local dev environment — backend running on this machine (first step of the greenscene.io revival)

## Status
<!-- Not Started | In Progress | Completed -->
Completed

## Goals
<!-- Goals & requirements -->
**Backend repo only.** Do not touch `ryzerecruiting_frontend` in this task.

Get the FastAPI backend running locally from a fresh clone, with a working
database and a superadmin login, so that feature work for the greenscene.io
revival can start. No rebranding, no tenant changes, no deploy — those are
separate tasks that follow this one.

Done means:
1. `uvicorn app.main:app --reload --port 8000` starts clean and `GET /docs` loads.
2. `alembic upgrade head` has run against a fresh local Postgres with the
   `vector` extension enabled, and `alembic current` shows head.
3. A superadmin user exists (via `scripts/create_superadmin.py`) and
   `POST /api/auth/login` returns a JWT for it.
4. The demo seed (`seed_greenpath_demo.py`) has been run on the local DB and
   `GET /api/candidates` (authenticated) returns rows.
5. A `requirements.txt` exists that reproduces the environment — see Decision 1.

Known facts from the inspection on 2026-11-02 (see project doc `LOCAL_SETUP.md`):
- `requirements.txt` is in `.gitignore`, so the dependency list is not in the repo.
  A reconstructed, unpinned list was drafted from the imports in `app/`.
- Only `DATABASE_URL` and `SECRET_KEY` are required by `app/core/config.py`;
  every other setting defaults to empty.
- Redis is created lazily in `app/api/auth.py` and `app/services/rate_limit.py`
  (`localhost:6379`), so the API starts without it; OAuth login and the public
  signup-firm / demo-request endpoints need it.
- `SessionMiddleware` in `app/main.py` is `https_only=True`, so the OAuth flow
  cannot complete over `http://localhost`. Email/password (JWT) login is unaffected.

### Decisions to flag in the audit (do not pick — present options and wait)
**Decision 1 — `requirements.txt`.** It is gitignored today.
  (a) Keep it ignored and maintain it only locally, as now.
  (b) Remove it from `.gitignore` and commit a pinned list (`pip freeze`) so a
      fresh clone — and Claude Code — can rebuild the environment.
  Consequence of (a): every fresh machine repeats today's reconstruction.
  Consequence of (b): the server's `pip install` becomes reproducible, but the
  droplet's installed versions should be captured first so the pins match prod.

**Decision 2 — local OAuth.** `https_only=True` blocks Google/LinkedIn login
locally. Options: (a) leave it — use email/password locally, OAuth is tested on
the server only; (b) make `https_only` follow `settings.DEBUG` so local dev can
exercise OAuth. Out of scope for this task either way; just record the choice.

## Related Files
- `app/core/config.py` — required settings
- `app/core/database.py` — engine / `DATABASE_URL`
- `app/main.py` — app entry, middleware
- `alembic/env.py`, `alembic/versions/3b1bb86413d5_initial_migration.py` — pgvector dependency
- `scripts/create_superadmin.py` — first login
- `seed_greenpath_demo.py` — demo data (wipes all but user id 1)
- `.env.example`, `.gitignore`
- `app/api/auth.py`, `app/services/rate_limit.py` — Redis usage

## Verification
- [x] `source venv/bin/activate && pip install -r requirements.txt` completes with no errors
- [x] `psql -d ryzerecruiting -c "\dx"` lists `vector`
- [x] `alembic upgrade head` then `alembic current` shows the head revision
- [x] `python scripts/create_superadmin.py --email <me>` creates user id 1
- [x] `uvicorn app.main:app --reload --port 8000` starts; `curl http://localhost:8000/docs` returns 200
- [x] `curl -X POST http://localhost:8000/api/auth/login ...` returns a token
- [x] `python seed_greenpath_demo.py` completes; authenticated `GET /api/candidates` returns 22 rows
- [x] `python audit_tenant_coverage.py` runs clean (baseline — no code changes expected in this task)

## Notes
- Machine OS: macOS (Darwin 25.6), Homebrew. PostgreSQL 16.9 + pgvector 0.8.0
  via brew (service running, `pg_hba` = trust on loopback). Redis not installed
  (not needed for the done criteria). Python 3.13.5 default, 3.12 via brew.
- Decisions taken 2026-11-02: **1 → (b)** commit a pinned `requirements.txt`
  built from the droplet's `pip freeze` and drop it from `.gitignore` (same
  commit). **2 → (a)** leave `https_only=True`; email/password locally, OAuth
  tested on the server only — no code change. **3 → (a)** the pre-existing
  local `ryzerecruiting` DB (empty, at head, `users_id_seq` at 6) was dropped
  and recreated so migrations run from scratch and the superadmin gets id 1.
- venv uses `python3.12`: the pre-Feb-2026 pins (pydantic-core 2.14.x,
  SQLAlchemy 2.0.25) have no 3.13 wheels, and `bcrypt` must stay <5 for passlib.
- No `LOCAL_SETUP.md` and no older working copy exist on this machine; nothing
  overrides the reconstructed `.env`/`requirements.txt`.
- Follow-up (not this task): `scripts/` is gitignored; `create_superadmin.py`
  is tracked only because it predates the rule. New helper scripts would be
  silently uncommitted.
- Follow-up (not this task): squash the migration chain into a single initial
  migration once the Greenscene tenant/branding work has settled the schema.
  Whoever squashes should know: `alembic check` / autogenerate emits
  `SAWarning: Cannot correctly sort tables; there are unresolvable cycles
  between tables "bookings, candidates"` — `bookings.candidate_id` and
  `candidates.booking_id` (8bad52f7eb0f) reference each other. Harmless today;
  SQLAlchemy says it may become an error in a future release.
- Follow-up (tenant isolation, decide before the Greenscene tenant work):
  `chat_sessions` / `chat_messages` have **no `tenant_id` column** — the models
  never had one, and the migration added 2026-11-03 (4083c0d3ba12) mirrors the
  models as-is. Scoping today is indirect via `chat_sessions.user_id → users.tenant_id`.
- If the original working copy of this repo still exists on this machine, its
  `requirements.txt` and `.env` take precedence over the reconstructed ones.
- Next tasks after this one, in order (each its own current-feature.md):
  1. Frontend running locally against this backend.
  2. Create the Greenscene tenant / decide whether Rye Beach Landscaping runs as
     a tenant or replaces the `ryze` defaults (branding resolver, PDF footers).
  3. Rebrand hardcoded RYZE references; domain config for greenscene.io.
  4. Deploy plan for greenscene.io.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-11-02 — Task drafted from a read-only inspection of both repos (Claude, chat). No code changed.
- 2026-11-02 — Audit done (Claude Code). Found: machine already had Postgres 16 +
  pgvector and an empty `ryzerecruiting` DB at head; `requirements.txt` was
  tracked until 3b28e0f (2026-02-16) and the pinned list is recoverable from git;
  startup is import-safe with empty settings. Tenant audit baseline: 95 endpoints,
  0 HARDCODED, 0 REVIEW. Decisions 1(b)/2(a)/3(a) confirmed by Dane.
- 2026-11-02 — Created `.env` from `.env.example` (fresh `SECRET_KEY`, `DEBUG=True`);
  dropped and recreated `ryzerecruiting` (Decision 3a). Waiting on the droplet
  `pip freeze` before building the venv.
- 2026-11-02 — `requirements.txt` written (Feb-2026 pins from 3b28e0f + 14 added
  packages, fully pinned from `pip freeze`, 96 lines); removed from `.gitignore`.
  venv built with python3.12.12; `pip install` clean — **zero bumps** to the
  February pins were needed. `import app.main` OK (101 routes). No droplet
  exists, so no prod freeze to match (Dane, 2026-11-02).
- 2026-11-02 — **BLOCKER found:** `alembic upgrade head` on the fresh DB fails at
  d68448a26b3b (`DROP CONSTRAINT bookings_candidate_id_fkey` — does not exist).
  46a2f9a418dc already dropped `bookings.candidate_id`; d68448a26b3b drops it
  again and 31bc4d401f23 indexes/FKs it without re-adding it. Prod had drifted
  from the chain (column re-added by hand). The previous local DB was at head
  only because it was restored, not migrated. Chain is at 11ae0fa76851 locally;
  awaiting decision on the fix.
- 2026-11-02 — Commit f77b8c5: pinned `requirements.txt` restored, un-ignored.
  Commit 0bd9fde: migration chain fix (Option A — d68448a26b3b spurious drops
  removed; 31bc4d401f23 re-adds `bookings.candidate_id` before its index/FK).
  `alembic upgrade head` now succeeds from scratch; `alembic current` =
  990ba786ad38 (head); `vector 0.8.0` installed; `users_id_seq` fresh at 1.
  **`alembic check` still FAILS:** `chat_sessions` / `chat_messages` (models
  added 2026-03-16, commit 8132911) were never given a migration and nothing
  calls `create_all`, so prod created them out-of-band. Awaiting decision on a
  new autogenerated migration.
- 2026-11-03 — Commit for 4083c0d3ba12: autogenerated migration creating
  `chat_sessions` + `chat_messages` (two tables, four indexes, nothing else; no
  `tenant_id` — models never had one, recorded in Notes). `alembic upgrade head`
  → `alembic current` = 4083c0d3ba12 (head); `alembic check` reports no new
  upgrade operations. FK-cycle SAWarning and squash recorded as Notes follow-ups.
- 2026-11-03 — Criterion 1 verified: `uvicorn app.main:app --reload --port 8000`
  starts clean (startup complete, no tracebacks); `GET /docs` → 200, `GET /` →
  `It Works!`. Server left running in the background for the login/seed checks.
  Verification boxes ticked: pip install, `\dx` vector, alembic head, uvicorn/docs.
- 2026-11-03 — Criteria 3 + 4 verified. Dane ran `create_superadmin.py` →
  `id=1 danielaherniv@gmail.com` (tenant `ryze`, superuser) and confirmed
  `POST /api/auth/login` returns a JWT; the JWT lives in `.token` (now
  gitignored) and `GET /api/auth/me` with it → 200, id 1. `seed_greenpath_demo.py
  --yes` completed: 22 candidates, 12 employers, 18 job orders, 31 bookings,
  tenant `green_path_recruiting` created, user 1 moved into it. Authenticated
  `GET /api/candidates` → 200, 22 rows. `audit_tenant_coverage.py`: 95 endpoints,
  0 HARDCODED, 0 REVIEW (unchanged from baseline). All 8 Verification boxes
  checked; Status → Completed. Awaiting Dane's confirmation before archive.
  `run_backfill.py` (embeddings) not run — needs an OpenAI key, not a criterion.
