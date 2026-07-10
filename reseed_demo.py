#!/usr/bin/env python3
"""
reseed_demo.py — rebuild the two actor-call demo records from the snapshot
==========================================================================

Runs AFTER the DB wipe. Reads webhook_snapshot.json (which is on disk and
survives the wipe) and reconstructs:

  * Booking #? outbound_candidate — Renata Voss (greenpath_recruiting)
  * Booking #? outbound_employer  — Walt Kessler (greenpath_recruiting)

For each it goes through the SAME service path production uses, so the result
is indistinguishable from a real accepted-invite call:

  create Booking (confirmed, ORIGINAL meeting_url reused so the preserved
  webhook_logs still match)  ->  find_or_create_candidate/employer stub  ->
  attach cleaned transcript  ->  embed booking + candidate  ->  regenerate
  summary / next_steps / keywords from the transcript.

Idempotent: purges any existing booking with the same meeting_url (and its
linked stub) before recreating, so you can run it repeatedly.

Run:
    python reseed_demo.py                 # rebuild both
    python reseed_demo.py --no-summary    # skip the Claude summary step
    python reseed_demo.py --snapshot demo.json

Nothing here is destructive beyond removing the two demo rows it manages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal
from app.models.booking import Booking
from app.models.candidate import Candidate

# Service functions — imported defensively so a missing one degrades gracefully.
try:
    from app.services.candidate_stub import find_or_create_candidate_stub
except Exception:
    find_or_create_candidate_stub = None
try:
    from app.services.employer_stub import find_or_create_employer_stub
except Exception:
    find_or_create_employer_stub = None
try:
    from app.services.embedding_service import (
        embed_booking_background,
        embed_candidate_background,
    )
except Exception:
    embed_booking_background = embed_candidate_background = None
try:
    from app.api.webhooks import _generate_summary_from_transcript
except Exception:
    _generate_summary_from_transcript = None


# ---------------------------------------------------------------------------
# Config — the two demo contacts, keyed by email (the join key across records)
# ---------------------------------------------------------------------------
TENANT_ID = "greenpath_recruiting"  # literal tenant_id string from the live bookings

# Speaker relabeling — Zoom attributed speech to the actors' real names.
SPEAKER_MAP = {
    "Ashlyn Bishop": "Renata Voss",
    "Gary": "Walt Kessler",
    # "Dane Ahern" left as-is (the recruiter)
}

# Per-contact transcript choice + optional pre-roll trim.
#   take: "refetched" | "stored" | "longest"
#   trim_before: if set, everything before the first occurrence of this
#                substring is dropped (use it to cut the glitchy setup chatter;
#                paste the first real scripted line here once you've read the JSON)
TRANSCRIPT_CHOICE = {
    "renata.voss.design@gmail.com": {"take": "refetched", "trim_before": None},  # 15,381 take
    "hello@greenscene.io":          {"take": "stored",    "trim_before": None},  # 8,678 take
}

# Renata's structured profile, lifted from her resume so the candidate card is
# rich in the demo (embedding + Intelligence pick these up).
CANDIDATE_ENRICH = {
    "renata.voss.design@gmail.com": {
        "phone": "(704) 555-0148",
        "location": "Charlotte, NC",
        "current_title": "Senior Landscape Designer",
        "current_company": "Sundale Outdoor Living",
        "ai_career_level": "Senior",
        "ai_years_experience": 12,
        "ai_summary": (
            "Landscape designer with 12+ years across residential and boutique "
            "commercial properties in the Carolinas, from concept sketch through "
            "construction documents. Runs client meetings solo, coordinates with "
            "build crews on site, and owns the highest-budget tier of projects "
            "($75K+). Background spans full-service design-build firms and an "
            "independent studio practice."
        ),
        "ai_experience": (
            "Senior Landscape Designer, Sundale Outdoor Living (2019–present) — "
            "lead designer on 40+ residential projects/yr; built the firm's first "
            "standardized proposal and plant-list template, cutting design-phase "
            "turnaround ~1/3; mentors two junior designers. "
            "Landscape Designer, Root & Stone Design Studio (2014–2019) — planting "
            "and hardscape plans, construction documents, subcontractor coordination. "
            "Design Assistant, Blue Ridge Grounds Co. (2011–2014)."
        ),
        "ai_education": "B.L.A., Landscape Architecture — NC State University (2011)",
        "ai_certifications": (
            "NC Certified Plant Professional (NC Nursery & Landscape Association); "
            "OSHA 10-Hour Construction Safety"
        ),
        "ai_skills": [
            "AutoCAD", "SketchUp", "Site grading & drainage design",
            "Planting design", "Hardscape layout", "Construction documentation",
            "Client presentations", "Budget & proposal development",
        ],
    }
}

# Walt's company details (from his script + email domain).
EMPLOYER_ENRICH = {
    "hello@greenscene.io": {
        "company_name": "Green Scene",
        "website_url": "https://greenscene.io",
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean_transcript(text: str | None, trim_before: str | None) -> str | None:
    if not text:
        return None
    if trim_before:
        idx = text.find(trim_before)
        if idx != -1:
            text = text[idx:]
    for old, new in SPEAKER_MAP.items():
        text = text.replace(f"{old}:", f"{new}:")
    return text.strip() or None


def choose_transcript(meeting: dict, take: str) -> str | None:
    stored = (meeting.get("booking") or {}).get("meeting_transcript")
    refetched = meeting.get("refetched_transcript")
    if take == "stored":
        return stored or refetched
    if take == "refetched":
        return refetched or stored
    # longest
    candidates = [t for t in (stored, refetched) if t]
    return max(candidates, key=len) if candidates else None


def purge_existing(db, meeting_url: str | None) -> None:
    if not meeting_url:
        return
    olds = db.query(Booking).filter(Booking.meeting_url == meeting_url).all()
    for b in olds:
        # remove stub candidate created from this booking, if any
        stubs = (
            db.query(Candidate)
            .filter(Candidate.booking_id == b.id, Candidate.source == "booking")
            .all()
        )
        for c in stubs:
            db.delete(c)
        db.delete(b)
    if olds:
        db.commit()
        print(f"  purged {len(olds)} existing booking(s) for {meeting_url[:48]}…")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", default="webhook_snapshot.json")
    ap.add_argument("--no-summary", action="store_true", help="Skip the Claude summary step")
    ap.add_argument("--date", default=None, help="Booking date YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    with open(args.snapshot, encoding="utf-8") as fh:
        snapshot = json.load(fh)

    booking_date = date.fromisoformat(args.date) if args.date else date.today()

    db = SessionLocal()
    created = []
    try:
        for meeting in snapshot.get("meetings", []):
            b = meeting.get("booking")
            if not b:
                continue

            email = (b.get("employer_email") or "").lower()
            btype = b.get("booking_type")
            meeting_url = b.get("meeting_url")

            choice = TRANSCRIPT_CHOICE.get(email, {"take": "longest", "trim_before": None})
            raw = choose_transcript(meeting, choice["take"])
            transcript = clean_transcript(raw, choice["trim_before"])

            print(f"\n▶ {b.get('employer_name')} ({btype}) — {email}")
            print(f"  take={choice['take']}  transcript_chars={len(transcript) if transcript else 0}")

            purge_existing(db, meeting_url)

            booking = Booking(
                booking_type=btype,
                tenant_id=TENANT_ID,
                employer_id=None,
                employer_name=b.get("employer_name"),
                employer_email=b.get("employer_email") or "",  # column is NOT NULL
                company_name=(EMPLOYER_ENRICH.get(email, {}).get("company_name")
                              or b.get("company_name")),
                website_url=(EMPLOYER_ENRICH.get(email, {}).get("website_url")
                             or b.get("website_url")),
                date=booking_date,
                time_slot=b.get("time_slot") or "10:00 AM",
                phone=(CANDIDATE_ENRICH.get(email, {}).get("phone") or b.get("phone")),
                notes=b.get("notes"),
                status="confirmed",
                response_token=None,
                meeting_url=meeting_url,  # reuse original so webhook_logs still match
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)
            print(f"  booking #{booking.id} created")

            # ── Candidate path ────────────────────────────────────────────
            if btype in ("outbound_candidate", "inbound_candidate"):
                cand = None
                if find_or_create_candidate_stub:
                    cand = find_or_create_candidate_stub(db, booking, TENANT_ID)
                    db.commit()
                    db.refresh(booking)
                else:  # fallback: create a minimal candidate directly
                    cand = Candidate(
                        tenant_id=TENANT_ID, name=booking.employer_name,
                        email=booking.employer_email or None, source="booking",
                        booking_id=booking.id,
                    )
                    db.add(cand)
                    db.commit()
                    db.refresh(cand)
                    booking.candidate_id = cand.id
                    db.commit()

                for field, value in CANDIDATE_ENRICH.get(email, {}).items():
                    setattr(cand, field, value)
                cand.meeting_transcript = transcript
                cand.embedding = None
                cand.embedded_at = None
                db.commit()
                print(f"  candidate #{cand.id} enriched + transcript attached")
                if embed_candidate_background:
                    embed_candidate_background(cand.id)

            # ── Employer path ─────────────────────────────────────────────
            elif btype == "outbound_employer":
                if find_or_create_employer_stub:
                    try:
                        profile = find_or_create_employer_stub(db, booking, TENANT_ID)
                        db.commit()
                        db.refresh(booking)
                        print(f"  employer profile #{getattr(profile, 'id', '?')} linked")
                    except Exception as e:
                        print(f"  employer stub skipped: {e}")

            # ── Transcript on booking + embed + summary ───────────────────
            booking.meeting_transcript = transcript
            booking.embedding = None
            booking.embedded_at = None
            db.commit()

            if embed_booking_background:
                embed_booking_background(booking.id)
                print("  booking embedded")

            if transcript and not args.no_summary and _generate_summary_from_transcript:
                print("  generating summary from transcript (Claude)…")
                _generate_summary_from_transcript(booking.id)  # opens its own session
                db.expire_all()
                fresh = db.query(Booking).filter(Booking.id == booking.id).first()
                if fresh and fresh.meeting_summary:
                    print(f"  summary: {fresh.meeting_summary[:120]}…")

            created.append((booking.id, b.get("employer_name")))

        print("\n" + "=" * 60)
        print("Reseed complete. Created bookings:")
        for bid, name in created:
            print(f"  #{bid}  {name}")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
