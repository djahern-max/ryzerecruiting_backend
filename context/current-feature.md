# Current Feature

<!-- Feature/fix name -->
Call intelligence on the candidate profile — expose booking `meeting_*` fields via the candidate API

## Status
<!-- Not Started | In Progress | Completed -->
In Progress

## Goals
<!-- Goals & requirements -->
When a Zoom call ends, `_generate_summary_from_transcript` writes `meeting_summary`,
`meeting_next_steps`, and `meeting_keywords` to the **booking** record. The webhook copies
only `meeting_transcript` onto the **candidate** record (`_copy_transcript_to_candidate`).

Result: a recruiter looking at `/admin/candidates/:id` sees a 2,000-character raw transcript
and no summary. The AI output from the call is invisible anywhere except the Admin Dashboard
booking row and the Intelligence chat. That's backwards — the summary is the thing a recruiter
actually wants; the transcript is the receipt.

**Goal:** surface the call intelligence on the candidate read endpoints as *derived, read-only*
fields sourced from the linked booking.

**Naming — this matters.** The candidate model already has `ai_summary` (from resume/LinkedIn
parsing), and the UI already labels a column "AI Summary". Do **not** reuse that name. New fields
are prefixed `call_`:

- `call_summary`      ← `booking.meeting_summary`
- `call_next_steps`   ← `booking.meeting_next_steps`
- `call_keywords`     ← `booking.meeting_keywords`
- `call_date`         ← `booking.date` (so the UI can say "from your call on Jul 12")
- `call_booking_id`   ← `booking.id` (lets the frontend link back to the booking)

**Constraints:**
- **No new columns. No Alembic migration.** These are computed on read from the existing
  `bookings` row. Nothing to `ALTER TABLE`, so `ryze-api` does not need to be stopped.
- Tenant-scoped like everything else — the booking lookup filters on
  `Booking.tenant_id == current_user.tenant_id` (superuser → `"ryze"`).

**Which booking?** Use the forward reference, not the back-reference:

- `booking.candidate_id` is set on **every** link (new stub *and* matched-existing-candidate).
- `candidate.booking_id` is set **only when the stub is newly created** — see
  `find_or_create_candidate_stub()`. If the candidate already existed and a booking was linked
  to them, `candidate.booking_id` stays `NULL`.

So query `Booking.candidate_id == candidate.id`, tenant-scoped. A candidate can have multiple
bookings (rescheduled calls — scenario C in the stub service docstring). Take the **most recent
booking that has a non-null `meeting_summary`**, ordered by `date DESC, id DESC`. If none has a
summary, all `call_*` fields come back `None` and the frontend simply doesn't render the card.

## Related Files
<!-- Files this touches -->
- `app/schemas/candidate.py` — add the five optional `call_*` fields to `CandidateOut`
  (or whichever response model `GET /api/candidates/{id}` returns)
- `app/api/candidates.py` — `GET /api/candidates/{id}` and `GET /api/candidates/me`:
  resolve the linked booking and populate the derived fields
- Read-only reference, do not change:
  - `app/services/candidate_stub.py` — confirms the forward/back-reference asymmetry above
  - `app/api/webhooks.py` — `_generate_summary_from_transcript`, `_copy_transcript_to_candidate`
  - `app/models/booking.py` — `meeting_summary` / `meeting_next_steps` / `meeting_keywords`

**Explicitly out of scope for this task:**
- The candidate PDF export (`pdf_card` sections in `app/api/candidates.py`) — adding a call
  summary section there is a separate change. One concern per commit.
- `GET /api/candidates/` (list/roster endpoint) — the roster's "AI Summary" column stays bound
  to `ai_summary`. Do not touch it here.
- The `candidate_name` column debt on `bookings` — unrelated, still open.

## Verification
<!-- How we'll know it worked -->
1. Renata Voss on the `green_path_recruiting` tenant already has a confirmed booking with a
   transcript and a generated summary. `curl` `GET /api/candidates/{her_id}` as a
   `green_path_recruiting` admin and confirm `call_summary`, `call_next_steps`, `call_keywords`,
   `call_date`, and `call_booking_id` all come back populated.
2. Hit the same endpoint as the `ryze` superuser — should return **nothing** for her (correct
   tenant isolation, this is the known gotcha, not a bug).
3. Create/inspect a candidate with **no** booking → all five `call_*` fields are `None`, endpoint
   still returns 200 (no crash on the `None` booking).
4. Confirm a candidate whose booking exists but has **no** summary yet (transcript pending) also
   returns `None` across the board rather than partial garbage.
5. `ai_summary` is still `None` for Renata (her resume isn't parsed) and is **unchanged** — this
   task must not touch the resume-parse path.

## Notes
<!-- Any extra notes -->
- This is a read-model change only. If it starts wanting a migration, stop and re-scope — the
  point of `call_*` being derived is that there's exactly one source of truth for call data
  (the booking) and we don't duplicate it onto candidates the way `meeting_transcript` already is.
- Worth noting for later: `meeting_transcript` **is** duplicated onto the candidate row today
  (EP17). That's arguably the same mistake in the other direction, but it's load-bearing for
  `build_candidate_text()` / embeddings. Leave it alone for now; flag it if we ever consolidate.
- Frontend companion task lives in the frontend repo's `context/current-feature.md`. Ship the
  backend first — the frontend card is gated on these fields existing.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-14 — Task created. Origin: recording a demo video for the Renata Voss call and noticed
  the profile page shows the raw transcript but no AI summary, and the roster's "AI Summary"
  column reads `ai_summary` (resume-derived, still `NULL`), which makes the call intelligence look
  like it never ran. It did run — it's just parked on the booking where nobody sees it.
- 2026-07-14 — Implemented. Added 5 `call_*` fields to `CandidateResponse`
  (`app/schemas/candidate.py`) and a `_attach_call_intelligence()` helper in
  `app/api/candidates.py`, wired only into `GET /api/candidates/{candidate_id}` (admin). Deliberately
  NOT wired into `GET /api/candidates/me` — meeting_summary/next_steps/keywords are
  recruiter-owned, same boundary `CandidateSelfUpdate` already draws on write. No migration,
  additive only. Flagged in-session (not fixed): `meeting_transcript` is already on
  `CandidateResponse` and already goes out over `/me` today — pre-existing, undecided whether
  intentional. Status still Not Started → ready to flip to Completed pending verification.
