# app/services/candidate_stub.py
"""
EP18 — Candidate stub creation service.

When an outbound_candidate or inbound_candidate booking is confirmed,
the candidate record should be born at that moment. This service handles
find-or-create logic with email-based duplicate prevention.

Duplicate scenarios handled:
  A) Booking confirmed → stub created. Resume uploaded later for same email
     → candidates.py UPDATES the existing record, does not create duplicate.

  B) Candidate manually created first. Booking confirmed for same email
     → this service finds the existing record and links it, no duplicate.

  C) Two bookings for same email (rescheduled call).
     → second booking links to the same candidate, no duplicate.

  D) No email on booking (phone-only).
     → stub created with null email, flagged source="booking" for manual review.
"""
import logging
from sqlalchemy.orm import Session

from app.models.candidate import Candidate

logger = logging.getLogger(__name__)


def find_or_create_candidate_stub(
    db: Session,
    booking,  # Booking ORM instance
    tenant_id: str,
) -> Candidate:
    """
    Find an existing candidate by email (within the same tenant) or create a
    minimal stub. Sets the bi-directional link:
      - booking.candidate_id → candidate.id
      - candidate.booking_id → booking.id  (only when the stub is newly created)

    Does NOT commit — the caller is responsible for committing. Uses db.flush()
    to generate a candidate.id when a new record is created so the caller can
    set booking.candidate_id before the final commit.

    Returns the Candidate instance (new or existing).
    """
    candidate = None

    # ── Try email match first ────────────────────────────────────────────
    if booking.employer_email:
        candidate = (
            db.query(Candidate)
            .filter(
                Candidate.email == booking.employer_email,
                Candidate.tenant_id == tenant_id,
            )
            .first()
        )
        if candidate:
            logger.info(
                f"[candidate_stub] Linked existing candidate #{candidate.id} "
                f"({candidate.name}) to booking #{booking.id} — matched by email"
            )

    # ── Create stub if no match found ────────────────────────────────────
    if not candidate:
        candidate = Candidate(
            tenant_id=tenant_id,
            name=booking.employer_name,
            email=booking.employer_email or None,
            phone=booking.phone or None,
            notes=booking.notes or None,
            source="booking",
            # booking_id set below after flush gives us candidate.id
        )
        db.add(candidate)
        db.flush()  # generate candidate.id without committing the transaction

        # EP18 — set back-reference so we know which booking created this stub
        candidate.booking_id = booking.id

        logger.info(
            f"[candidate_stub] Created stub candidate #{candidate.id} "
            f"({candidate.name}) for booking #{booking.id}"
        )

    # ── Link booking → candidate (forward reference) ─────────────────────
    booking.candidate_id = candidate.id
    # Caller commits

    return candidate
