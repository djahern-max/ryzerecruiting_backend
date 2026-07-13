#!/usr/bin/env python3
"""
reset_candidate_profile.py — blank a candidate's parsed-resume fields so the
resume-parse flow can be demonstrated live, without touching anything the rest
of the app depends on.

NEVER deletes the candidate row: bookings.candidate_id is ON DELETE SET NULL,
so a delete would orphan the linked call and break the transcript modal and
get_candidate_calls.

PRESERVED: id, tenant_id, name, email, source, booking_id, meeting_transcript.
The transcript is deliberately kept — build_candidate_text() includes it, so the
blanked record still embeds and stays findable by what was said on the call.
Only the structured profile disappears.

    python reset_candidate_profile.py --email renata.voss.design@gmail.com            # dry run
    python reset_candidate_profile.py --email renata.voss.design@gmail.com --apply    # snapshot + blank
    python reset_candidate_profile.py --email renata.voss.design@gmail.com --restore  # put it all back
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

import app.models.user  # noqa: F401
import app.models.tenant  # noqa: F401
import app.models.booking  # noqa: F401
import app.models.candidate  # noqa: F401

from app.core.database import SessionLocal
from app.models.candidate import Candidate
from app.services.embedding_service import embed_candidate_background

# Everything the resume parser populates. hasattr-guarded, so a column that
# doesn't exist on your model is skipped rather than raising.
PARSED_FIELDS = [
    "current_title",
    "current_company",
    "location",
    "phone",
    "ai_summary",
    "ai_experience",
    "ai_education",
    "ai_skills",
    "ai_career_level",
    "ai_years_experience",
    "ai_certifications",
    "linkedin_raw_text",
    "resume_url",
    "photo_url",
]

SNAPSHOT_DIR = "demo_snapshots"


def snapshot_path(email: str) -> str:
    safe = email.replace("@", "_at_").replace(".", "_")
    return os.path.join(SNAPSHOT_DIR, f"candidate_{safe}.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument(
        "--apply", action="store_true", help="Actually write. Default is dry run."
    )
    ap.add_argument(
        "--restore", action="store_true", help="Restore from the snapshot instead."
    )
    args = ap.parse_args()

    db = SessionLocal()
    try:
        cand = (
            db.query(Candidate)
            .filter(Candidate.email.ilike(args.email.strip()))
            .first()
        )
        if not cand:
            sys.exit(f"No candidate found with email {args.email}")

        print(f"Candidate #{cand.id} — {cand.name} (tenant={cand.tenant_id})")
        print(
            f"  transcript on record: {bool(cand.meeting_transcript)} "
            f"({len(cand.meeting_transcript or '')} chars) — PRESERVED"
        )

        path = snapshot_path(args.email)

        # ── Restore ──────────────────────────────────────────────────────
        if args.restore:
            if not os.path.exists(path):
                sys.exit(f"No snapshot at {path}")
            with open(path) as f:
                saved = json.load(f)
            for field, value in saved.items():
                if hasattr(cand, field):
                    setattr(cand, field, value)
            cand.embedding = None
            cand.embedded_at = None
            cand.updated_at = datetime.utcnow()
            db.commit()
            print(f"\nRestored {len(saved)} field(s) from {path}")
            embed_candidate_background(cand.id)
            print("Re-embedded.")
            return

        # ── Blank ────────────────────────────────────────────────────────
        to_clear = {
            f: getattr(cand, f)
            for f in PARSED_FIELDS
            if hasattr(cand, f) and getattr(cand, f) is not None
        }

        print(f"\nWould clear {len(to_clear)} populated field(s):")
        for field, value in to_clear.items():
            preview = str(value).replace("\n", " ")[:70]
            print(f"  {field:24} = {preview}{'…' if len(str(value)) > 70 else ''}")

        if not args.apply:
            print("\nDRY RUN — nothing written. Re-run with --apply.")
            return

        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(to_clear, f, indent=2, default=str)
        print(f"\nSnapshot written to {path}")

        for field in to_clear:
            setattr(cand, field, None)
        cand.embedding = None
        cand.embedded_at = None
        cand.updated_at = datetime.utcnow()
        db.commit()
        print(f"Cleared {len(to_clear)} field(s) on candidate #{cand.id}")

        # Re-embed from what's left (name + transcript) so she stays findable.
        embed_candidate_background(cand.id)
        print("Re-embedded from transcript only.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
