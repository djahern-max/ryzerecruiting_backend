#!/usr/bin/env python3
"""
extract_call_data.py — pull the REAL content out of your Zoom webhook logs
==========================================================================

Why this exists
---------------
Your `webhook_logs` table stores the raw webhook *payloads*. Those payloads do
NOT contain the transcript text — only a `download_url` and a short-lived
`download_token` (valid ~24h). The actual transcript is downloaded separately
and written onto:

    bookings.meeting_transcript          <- source of truth
    candidates.meeting_transcript        <- EP17 copy (candidate bookings only)

So the durable, recoverable content lives on the booking/candidate ROWS right
now. If you wipe those rows before capturing them — and the Zoom tokens have
expired — the transcripts are gone. `webhook_logs` alone cannot rebuild them.

What this script does (READ-ONLY — never writes to the database)
----------------------------------------------------------------
  1. Groups every webhook log by meeting_id and prints the event timeline
     (which events arrived, when, whether a booking matched, the result).
  2. For each meeting, finds the matched Booking (meeting_url contains
     meeting_id) and the linked Candidate, and pulls their CURRENT
     meeting_transcript / meeting_summary / next_steps / keywords.
  3. Writes everything — raw payloads + the live transcript/summary text — to a
     JSON fixture (default: webhook_snapshot.json). THIS FILE is what survives a
     database wipe and what your re-seed method should read from.
  4. Optional --refetch: for any log that still carries a live download_token,
     attempts to re-download the transcript straight from Zoom (recovers text
     that never made it onto a row, IF the token hasn't expired yet).

How to run
----------
From the backend project root (the dir containing the `app/` package), with
your venv active and DATABASE_URL / .env available:

    python extract_call_data.py                 # analyze + snapshot
    python extract_call_data.py --refetch        # also try live re-download
    python extract_call_data.py --hours 48       # only logs from last 48h
    python extract_call_data.py --out demo.json  # custom fixture path

Read the printed summary, open the JSON, confirm you have Renata's and Walt's
transcripts captured. ONLY THEN move on to cleanup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# Make the app package importable when run from the project root.
sys.path.insert(0, os.getcwd())

try:
    from app.core.database import SessionLocal
    from app.models.webhook_log import WebhookLog
    from app.models.booking import Booking
    from app.models.candidate import Candidate
except Exception as e:  # pragma: no cover
    print(
        "\nCould not import app models. Run this from the backend project root "
        "(the directory that contains the `app/` package), with your venv active.\n"
        f"Import error: {e}\n"
    )
    sys.exit(1)

# download_recording_file is only needed for --refetch; import defensively.
try:
    from app.services.zoom import download_recording_file
except Exception:
    download_recording_file = None


BAR = "=" * 78
PREVIEW_CHARS = 400  # how much transcript text to echo to stdout (full text -> JSON)


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------
def load_payload(log: "WebhookLog") -> dict:
    try:
        return json.loads(log.raw_payload) if log.raw_payload else {}
    except Exception:
        return {}


def extract_ids(payload: dict) -> tuple[str | None, str | None]:
    obj = (payload.get("payload") or {}).get("object") or {}
    mid = obj.get("id")
    uuid = obj.get("uuid")
    return (str(mid) if mid is not None else None, uuid)


def extract_transcript_ref(payload: dict) -> tuple[str | None, str | None]:
    """Return (transcript_download_url, download_token) if a TRANSCRIPT file is present."""
    token = payload.get("download_token") or ""
    obj = (payload.get("payload") or {}).get("object") or {}
    for f in obj.get("recording_files", []) or []:
        ftype = (f.get("file_type") or "").upper()
        rtype = f.get("recording_type") or ""
        if ftype == "TRANSCRIPT" or rtype == "audio_transcript":
            return f.get("download_url"), token
    return None, token


def preview(text: str | None) -> str:
    if not text:
        return "—"
    text = text.strip()
    if len(text) <= PREVIEW_CHARS:
        return text
    return text[:PREVIEW_CHARS] + f"… [+{len(text) - PREVIEW_CHARS} more chars]"


def fmt_ts(dt) -> str:
    if not dt:
        return "—"
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out", default="webhook_snapshot.json", help="Fixture output path"
    )
    ap.add_argument(
        "--hours", type=int, default=None, help="Only logs from last N hours"
    )
    ap.add_argument(
        "--refetch",
        action="store_true",
        help="Attempt live transcript re-download for logs with a still-valid token",
    )
    args = ap.parse_args()

    if args.refetch and download_recording_file is None:
        print(
            "[warn] --refetch requested but app.services.zoom.download_recording_file "
            "could not be imported; skipping re-download."
        )

    db = SessionLocal()
    try:
        q = db.query(WebhookLog)
        if args.hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
            q = q.filter(WebhookLog.received_at >= cutoff)
        logs = q.order_by(WebhookLog.received_at.asc()).all()

        print(BAR)
        print("RYZE — webhook log content extraction (READ-ONLY)")
        print(f"logs found : {len(logs)}")
        print(BAR)

        if not logs:
            print("No webhook logs to analyze.")
            return

        # Group by meeting_id (fall back to uuid), skip id-less/validation noise.
        groups: dict[str, list] = defaultdict(list)
        noise = 0
        for log in logs:
            payload = load_payload(log)
            mid, uuid = extract_ids(payload)
            key = mid or uuid
            event = payload.get("event", "")
            if not key or event == "endpoint.url_validation":
                noise += 1
                continue
            groups[key].append((log, payload))

        # Quick event tally.
        tally: dict[str, int] = defaultdict(int)
        for log in logs:
            tally[load_payload(log).get("event", "unknown")] += 1
        print("\nEvent tally across all logs:")
        for ev, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3}  {ev}")
        if noise:
            print(
                f"\n({noise} id-less/validation logs excluded from per-meeting analysis)"
            )

        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "meetings": [],
        }

        for key in sorted(groups.keys()):
            entries = sorted(
                groups[key],
                key=lambda t: (t[0].received_at or datetime.min),
            )
            meeting_id, meeting_uuid = extract_ids(entries[0][1])

            print("\n" + BAR)
            print(
                f"MEETING  meeting_id={meeting_id or '?'}  uuid={(meeting_uuid or '?')[:24]}…"
            )

            # Event timeline
            events = []
            print("  Events:")
            for log, payload in entries:
                ev = payload.get("event", "?")
                print(
                    f"    {fmt_ts(log.received_at):<32} {ev:<32} "
                    f"booking_found={log.booking_found or '—':<4} result={log.result or '—'}"
                )
                events.append(
                    {
                        "webhook_log_id": log.id,
                        "event": ev,
                        "received_at": fmt_ts(log.received_at),
                        "booking_found": log.booking_found,
                        "result": log.result,
                    }
                )

            # Matched booking (same matcher the webhook handler uses)
            booking = None
            if meeting_id:
                booking = (
                    db.query(Booking)
                    .filter(Booking.meeting_url.contains(meeting_id))
                    .first()
                )

            booking_snap = None
            candidate_snap = None
            if booking:
                print(
                    f"\n  Booking  #{booking.id}  type={booking.booking_type}  "
                    f"tenant={booking.tenant_id}  status={booking.status}"
                )
                print(
                    f"           who={booking.employer_name}  email={booking.employer_email or '—'}"
                )
                print(f"           transcript: {preview(booking.meeting_transcript)}")
                print(f"           summary   : {preview(booking.meeting_summary)}")

                booking_snap = {
                    "id": booking.id,
                    "booking_type": booking.booking_type,
                    "tenant_id": booking.tenant_id,
                    "status": booking.status,
                    "employer_name": booking.employer_name,
                    "employer_email": booking.employer_email,
                    "company_name": booking.company_name,
                    "website_url": booking.website_url,
                    "date": str(booking.date) if booking.date else None,
                    "time_slot": booking.time_slot,
                    "phone": booking.phone,
                    "notes": booking.notes,
                    "meeting_url": booking.meeting_url,
                    "candidate_id": booking.candidate_id,
                    "meeting_transcript": booking.meeting_transcript,
                    "meeting_summary": booking.meeting_summary,
                    "meeting_next_steps": booking.meeting_next_steps,
                    "meeting_keywords": booking.meeting_keywords,
                }

                if booking.candidate_id:
                    cand = (
                        db.query(Candidate)
                        .filter(Candidate.id == booking.candidate_id)
                        .first()
                    )
                    if cand:
                        print(
                            f"  Candidate #{cand.id} {cand.name}  "
                            f"transcript_copied={'yes' if cand.meeting_transcript else 'NO'}"
                        )
                        candidate_snap = {
                            "id": cand.id,
                            "name": cand.name,
                            "email": cand.email,
                            "phone": cand.phone,
                            "source": cand.source,
                            "tenant_id": cand.tenant_id,
                            "meeting_transcript": cand.meeting_transcript,
                        }
            else:
                print(
                    "\n  Booking  : NONE matched (meeting_id not found inside any meeting_url)."
                )
                print(
                    "             This call never landed on a booking row — transcript, if any,"
                )
                print(
                    "             is only recoverable via --refetch while the token is valid."
                )

            # Optional live re-download from a still-valid token
            refetched = None
            if args.refetch and download_recording_file is not None:
                for _, payload in entries:
                    url, token = extract_transcript_ref(payload)
                    if url and token:
                        print("  Refetch  : attempting live download from Zoom…")
                        try:
                            refetched = download_recording_file(url, token)
                        except Exception as e:
                            print(f"             refetch failed: {e}")
                        if refetched:
                            print(f"             recovered {len(refetched)} chars")
                            break
                        else:
                            print(
                                "             refetch returned empty (token likely expired)"
                            )

            snapshot["meetings"].append(
                {
                    "meeting_id": meeting_id,
                    "meeting_uuid": meeting_uuid,
                    "events": events,
                    "booking": booking_snap,
                    "candidate": candidate_snap,
                    "refetched_transcript": refetched,
                }
            )

        # Write the durable fixture
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, ensure_ascii=False)

        print("\n" + BAR)
        print(f"Snapshot written: {args.out}")
        print(f"Meetings captured: {len(snapshot['meetings'])}")
        have_tx = sum(
            1
            for m in snapshot["meetings"]
            if (m["booking"] and m["booking"]["meeting_transcript"])
            or m["refetched_transcript"]
        )
        print(f"Meetings with recoverable transcript text: {have_tx}")
        print(BAR)
        print(
            "\nNext: open the snapshot, confirm Renata's and Walt's transcripts are\n"
            "captured, pick the good take, strip glitches/off-script. That cleaned\n"
            "content feeds the re-seed method. Do NOT wipe the DB until this is done."
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
