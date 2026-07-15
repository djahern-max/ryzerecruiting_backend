"""
diagnose_signup_tenant_backfill.py — read-only, one-off.

Explains a "0 user(s) would change" result from backfill_signup_tenants.py:
  1. How many CANDIDATE/EMPLOYER users are actually in scope (tenant_id
     NULL or 'ryze')?
  2. Of those, how many have an email that also appears in candidates/
     employer_profiles under a DIFFERENT (non-ryze) tenant?
  3. How many candidate/employer profiles exist under non-ryze tenants at
     all, so we know whether there's any firm data to match against.

Writes nothing. Delete after use.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.booking import Booking  # noqa: F401
from app.models.user import User, UserType
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile

from app.core.database import SessionLocal
from app.core.deps import RYZE_TENANT

db = SessionLocal()
try:
    scoped_users = (
        db.query(User)
        .filter(
            User.user_type.in_([UserType.CANDIDATE, UserType.EMPLOYER]),
            (User.tenant_id.is_(None)) | (User.tenant_id == RYZE_TENANT),
        )
        .all()
    )
    print(f"Users in backfill scope (CANDIDATE/EMPLOYER, ryze/NULL): {len(scoped_users)}")
    for u in scoped_users:
        print(f"  {u.id} | {u.email} | {u.user_type.value} | tenant_id={u.tenant_id}")

    non_ryze_candidates = (
        db.query(Candidate)
        .filter(Candidate.tenant_id.isnot(None), Candidate.tenant_id != RYZE_TENANT)
        .all()
    )
    print(f"\nCandidate rows under a non-ryze tenant: {len(non_ryze_candidates)}")
    for c in non_ryze_candidates:
        print(f"  candidate #{c.id} | {c.email} | tenant_id={c.tenant_id}")

    non_ryze_employers = (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.tenant_id.isnot(None),
            EmployerProfile.tenant_id != RYZE_TENANT,
        )
        .all()
    )
    print(f"\nEmployerProfile rows under a non-ryze tenant: {len(non_ryze_employers)}")
    for e in non_ryze_employers:
        print(f"  employer_profile #{e.id} | {e.primary_contact_email} | tenant_id={e.tenant_id}")

    scoped_emails = {u.email.strip().lower() for u in scoped_users if u.email}
    candidate_emails = {c.email.strip().lower() for c in non_ryze_candidates if c.email}
    employer_emails = {
        e.primary_contact_email.strip().lower()
        for e in non_ryze_employers
        if e.primary_contact_email
    }
    overlap = scoped_emails & (candidate_emails | employer_emails)
    print(f"\nEmails present in BOTH scoped users and a non-ryze profile: {len(overlap)}")
    for email in sorted(overlap):
        print(f"  {email}")
finally:
    db.close()
