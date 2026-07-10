"""
analyze_webhook_logs.py — RYZE Intelligence recollection diagnostic
====================================================================

Purpose
-------
Your 13 webhook logs are the ground truth of what Zoom actually delivered.
This script reconciles them against the rest of the pipeline so you can see,
per meeting, *exactly* why RYZE Intelligence would or would not "remember"
a given call.

It answers, for each meeting:
  1. Which Zoom events arrived, in what order, and with what timing gaps.
  2. Whether a Booking was matched (meeting_url.contains(meeting_id)).
  3. Whether the transcript / summary landed on the booking.
  4. Whether the booking was EMBEDDED (this is what search_meeting_notes needs).
  5. Whether a linked Candidate exists, got the transcript copied, and got embedded.
  6. Whether tenant_id is consistent (a mismatch makes the call invisible to the
     querying recruiter even when everything else is fine).

Then it prints a verdict per meeting:
  - "get_meetings_by_date / get_todays_meetings" reachability  (date-based, no embedding needed)
  - "search_meeting_notes"                       reachability  (vector, embedding REQUIRED)

Why two verdicts? Because the AI's answer quality depends on WHICH tool Claude
picks. "What did I discuss with X?" tends to route to the embedding-dependent
tool; "what calls did I have today?" routes to the date tool. A call can be
reachable by one and invisible to the other.

How to run
----------
From your backend project root (the dir that contains the `app/` package),
with your normal venv activated and .env / DATABASE_URL available:

    python analyze_webhook_logs.py

Optional flags:
    python analyze_webhook_logs.py --tenant ryze      # assume this tenant when judging visibility
    python analyze_webhook_logs.py --dump-payloads     # print the raw JSON payload per log
    python analyze_webhook_logs.py --hours 72          # only logs from the last N hours

It is READ-ONLY. It never writes to the database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------
# Bootstrap: make the app package importable when run from the project root.
# --------------------------------------------------------------------------
sys.path.insert(0, os.getcwd())

try:
    from app.core.database import SessionLocal
    from app.models.webhook_log import WebhookLog
    from app.models.booking import Booking
    from app.models.candidate import Candidate
except Exception as e:  # pragma: no cover
    print(
        "\nCould not import your app models. Run this from the backend project root\n"
        "(the folder containing the `app/` package), with your venv active.\n"
        f"Import error: {e}\n"
    )
    sys.exit(1)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def g(obj, attr, default=None):
    """Safe getattr — tolerates schema drift across episodes."""
    return getattr(obj, attr, default)


def has_value(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    return True


def is_embedded(row) -> bool:
    """
    A row counts as embedded if either embedded_at is set OR the embedding
    vector column is populated. search_meeting_notes filters on the vector
    being non-null, so that is the authoritative check; embedded_at is a
    cheaper proxy we also honor.
    """
    if has_value(g(row, "embedded_at")):
        return True
    emb = g(row, "embedding")
    try:
        return emb is not None
    except Exception:
        return False


def fmt_ts(ts) -> str:
    if not ts:
        return "—"
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    return str(ts)


def parse_payload(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def extract_ids(log) -> tuple[str, str]:
    """Prefer stored columns, fall back to digging into the raw payload."""
    meeting_id = (g(log, "meeting_id") or "").strip()
    meeting_uuid = (g(log, "meeting_uuid") or "").strip()
    if meeting_id and meeting_uuid:
        return meeting_id, meeting_uuid
    obj = (
        parse_payload(g(log, "raw_payload") or "").get("payload", {}).get("object", {})
    )
    meeting_id = meeting_id or str(obj.get("id", "") or "")
    meeting_uuid = meeting_uuid or str(obj.get("uuid", "") or "")
    return meeting_id, meeting_uuid


# --------------------------------------------------------------------------
# Booking matching — mirror the webhook handler's own logic exactly:
#   db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
# --------------------------------------------------------------------------
def find_booking(db, meeting_id: str):
    if not meeting_id:
        return None
    return (
        db.query(Booking)
        .filter(Booking.meeting_url.contains(meeting_id))
        .order_by(Booking.id.desc())
        .first()
    )


def find_candidate(db, booking):
    cid = g(booking, "candidate_id")
    if not cid:
        return None
    return db.query(Candidate).filter(Candidate.id == cid).first()


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
BAR = "=" * 78
SUB = "-" * 78

# Events we care about, in the order Zoom is supposed to fire them.
EVENT_ORDER = [
    "meeting.started",
    "meeting.ended",
    "recording.completed",
    "recording.transcript_completed",
    "meeting.summary_updated",
]


def event_rank(ev: str) -> int:
    return EVENT_ORDER.index(ev) if ev in EVENT_ORDER else len(EVENT_ORDER)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tenant",
        default="ryze",
        help="Tenant to assume for the querying recruiter (default: ryze)",
    )
    ap.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Only consider webhook logs from the last N hours",
    )
    ap.add_argument(
        "--dump-payloads", action="store_true", help="Print each raw JSON payload"
    )
    args = ap.parse_args()

    db = SessionLocal()
    try:
        q = db.query(WebhookLog)
        if args.hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
            q = q.filter(WebhookLog.received_at >= cutoff)
        logs = q.order_by(WebhookLog.received_at.asc()).all()

        print(BAR)
        print(f"RYZE Intelligence recollection diagnostic")
        print(f"assumed querying tenant : {args.tenant}")
        print(f"webhook logs found      : {len(logs)}")
        print(BAR)

        if not logs:
            print("No webhook logs to analyze.")
            return

        # ---- Group logs by meeting_id (fall back to uuid, then to 'no-id') ----
        groups: dict[str, list] = defaultdict(list)
        noise = []  # url_validation and other id-less events
        for log in logs:
            mid, uuid = extract_ids(log)
            key = mid or uuid
            if not key or g(log, "event") == "endpoint.url_validation":
                noise.append(log)
                continue
            groups[key].append(log)

        # ---- Raw event-type tally (quick health read) ----
        tally = defaultdict(int)
        for log in logs:
            tally[g(log, "event") or "unknown"] += 1
        print("\nEvent tally across all logs:")
        for ev, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3}  {ev}")
        if noise:
            print(
                f"\n({len(noise)} id-less/validation logs excluded from per-meeting analysis)"
            )

        # ---- Per-meeting reconciliation ----
        summary_rows = []
        for key in sorted(groups.keys()):
            mlogs = sorted(
                groups[key],
                key=lambda l: (
                    g(l, "received_at") or datetime.min,
                    event_rank(g(l, "event") or ""),
                ),
            )
            meeting_id, meeting_uuid = extract_ids(mlogs[0])

            print("\n" + BAR)
            print(
                f"MEETING  meeting_id={meeting_id or '?'}  uuid={(meeting_uuid or '?')[:24]}"
            )
            print(SUB)

            # Timeline
            first_ts = g(mlogs[0], "received_at")
            print("Event timeline:")
            for l in mlogs:
                ts = g(l, "received_at")
                gap = ""
                if isinstance(ts, datetime) and isinstance(first_ts, datetime):
                    delta = (ts - first_ts).total_seconds()
                    gap = f"  (+{int(delta)//60}m{int(delta)%60:02d}s)"
                print(
                    f"  {fmt_ts(ts)}{gap:<12}  {g(l,'event'):<34}  "
                    f"booking_found={g(l,'booking_found')!s:<4}  result={g(l,'result')}"
                )
                if args.dump_payloads:
                    print(
                        "    payload:",
                        json.dumps(parse_payload(g(l, "raw_payload")), indent=2)[:1500],
                    )

            got_transcript_event = any(
                g(l, "event") == "recording.transcript_completed" for l in mlogs
            )
            got_summary_event = any(
                g(l, "event") == "meeting.summary_updated" for l in mlogs
            )

            # Reconcile with the DB
            booking = find_booking(db, meeting_id)
            if not booking:
                print(
                    "\n  DB match : NO booking matched meeting_url.contains(meeting_id)."
                )
                print(
                    "             -> This call is INVISIBLE to Intelligence. Likely the meeting"
                )
                print(
                    "                was not created via the booking/instant-meeting flow, or the"
                )
                print("                meeting_id isn't inside the stored join URL.")
                summary_rows.append((meeting_id, "no booking", "—", "MISS", "MISS"))
                continue

            b_tenant = g(booking, "tenant_id")
            b_embedded = is_embedded(booking)
            has_tx = has_value(g(booking, "meeting_transcript"))
            has_sum = has_value(g(booking, "meeting_summary"))
            tenant_ok = str(b_tenant) == str(args.tenant)

            print(
                f"\n  Booking  #{g(booking,'id')}  status={g(booking,'status')}  "
                f"type={g(booking,'booking_type')}  tenant={b_tenant}"
                + (
                    ""
                    if tenant_ok
                    else f"  <-- NOT '{args.tenant}': invisible to that recruiter"
                )
            )
            print(
                f"           who={g(booking,'employer_name') or g(booking,'company_name') or '—'}  "
                f"date={g(booking,'date')} {g(booking,'time_slot') or ''}"
            )
            print(
                f"  Data     transcript={'yes' if has_tx else 'NO'}  "
                f"summary={'yes' if has_sum else 'NO'}  "
                f"embedded={'yes' if b_embedded else 'NO'}  "
                f"embedded_at={fmt_ts(g(booking,'embedded_at'))}"
            )

            # Linked candidate
            cand = find_candidate(db, booking)
            if cand:
                c_tx = has_value(g(cand, "meeting_transcript"))
                c_emb = is_embedded(cand)
                print(
                    f"  Candidate #{g(cand,'id')} {g(cand,'name')}  "
                    f"transcript_copied={'yes' if c_tx else 'NO'}  "
                    f"embedded={'yes' if c_emb else 'NO'}  tenant={g(cand,'tenant_id')}"
                )
            else:
                print(
                    "  Candidate: none linked (booking.candidate_id is null) — "
                    "get_candidate_calls / candidate vector search won't surface this call."
                )

            # ---- Verdicts ----
            # Date-based tools (get_todays_meetings / get_meetings_by_date) only need
            # the booking row + tenant match. No embedding required.
            date_reach = "OK" if tenant_ok else "MISS(tenant)"
            # search_meeting_notes needs embedding + tenant match.
            if not b_embedded:
                notes_reach = "MISS(no embedding)"
            elif not tenant_ok:
                notes_reach = "MISS(tenant)"
            else:
                notes_reach = "OK"

            print(f"\n  VERDICT  date tools (by date)      : {date_reach}")
            print(f"           search_meeting_notes (vec) : {notes_reach}")

            # Nudges
            if got_transcript_event and not has_tx:
                print(
                    "  NOTE     transcript event arrived but booking has no transcript "
                    "-> download/parse step likely failed (check download_token handling)."
                )
            if (has_tx or has_sum) and not b_embedded:
                print(
                    "  NOTE     content present but NOT embedded -> embed_booking_background "
                    "likely failed (OpenAI key? exception?). This is the #1 cause of 'no recollection'."
                )
            if not got_transcript_event and not got_summary_event:
                print(
                    "  NOTE     no transcript/summary event yet -> if the call was recent, Zoom may"
                )
                print(
                    "           still be processing (transcripts can lag 15-30+ min). Ask again later."
                )

            summary_rows.append(
                (
                    meeting_id,
                    f"#{g(booking,'id')}",
                    str(b_tenant),
                    date_reach,
                    notes_reach,
                )
            )

        # ---- Final matrix ----
        print("\n" + BAR)
        print("SUMMARY MATRIX")
        print(SUB)
        print(
            f"{'meeting_id':<16}{'booking':<10}{'tenant':<10}{'by-date':<16}{'semantic'}"
        )
        for mid, bk, tn, dr, nr in summary_rows:
            print(f"{mid[:15]:<16}{bk:<10}{tn[:9]:<10}{dr:<16}{nr}")
        print(BAR)
        print("\nHow to read this:")
        print("  by-date OK + semantic OK   -> AI should recall this call reliably.")
        print(
            "  by-date OK + semantic MISS -> AI finds it only if it picks a date tool;"
        )
        print(
            "                                'what did we discuss' style questions will whiff."
        )
        print(
            "  both MISS                  -> AI is blind to this call. Fix booking match /"
        )
        print(
            "                                embedding / tenant before testing further."
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
