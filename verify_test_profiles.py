#!/usr/bin/env python3
"""
RYZE.ai — Test Profile Verification
Checks that both test user accounts have linked profiles and embeddings.

Run from the project root:
    python verify_test_profiles.py
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models.user import User, UserType
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder

db = SessionLocal()

TEST_CANDIDATE_EMAIL = "test_candidate@ryze.ai"
TEST_EMPLOYER_EMAIL = "test_employer@ryze.ai"

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

errors = 0

print()
print("=" * 56)
print("  RYZE.ai — Test Profile Verification")
print("=" * 56)


# ── 1. Users ───────────────────────────────────────────────
print("\n── Users ──────────────────────────────────────────────")

candidate_user = db.query(User).filter(User.email == TEST_CANDIDATE_EMAIL).first()
employer_user = db.query(User).filter(User.email == TEST_EMPLOYER_EMAIL).first()

if candidate_user:
    print(
        f"{PASS} Candidate user   id={candidate_user.id}  email={candidate_user.email}  type={candidate_user.user_type}"
    )
else:
    print(f"{FAIL} No user found for {TEST_CANDIDATE_EMAIL} — run seed_full.py")
    errors += 1

if employer_user:
    print(
        f"{PASS} Employer  user   id={employer_user.id}  email={employer_user.email}  type={employer_user.user_type}"
    )
else:
    print(f"{FAIL} No user found for {TEST_EMPLOYER_EMAIL} — run seed_full.py")
    errors += 1


# ── 2. Candidate Profile ───────────────────────────────────
print("\n── Candidate Profile ──────────────────────────────────")

candidate = db.query(Candidate).filter(Candidate.email == TEST_CANDIDATE_EMAIL).first()

if candidate:
    print(f"{PASS} Profile found    id={candidate.id}  name='{candidate.name}'")
    print(f"     title     : {candidate.current_title or '—'}")
    print(f"     level     : {candidate.ai_career_level or '—'}")
    print(f"     certs     : {candidate.ai_certifications or '—'}")
    print(f"     experience: {candidate.ai_years_experience or '—'} yrs")
    print(f"     tenant_id : {candidate.tenant_id or '—'}")

    if candidate.embedding is not None:
        print(f"{PASS} Embedding present — /me/job-matches will return ranked results")
    else:
        print(
            f"{WARN} No embedding — run run_backfill.py (matches will return unranked)"
        )
        errors += 1
else:
    print(
        f"{FAIL} No candidate profile for {TEST_CANDIDATE_EMAIL} — run seed_test_profiles.py"
    )
    errors += 1


# ── 3. Employer Profile ────────────────────────────────────
print("\n── Employer Profile ───────────────────────────────────")

employer = (
    db.query(EmployerProfile)
    .filter(EmployerProfile.primary_contact_email == TEST_EMPLOYER_EMAIL)
    .first()
)

if employer:
    print(
        f"{PASS} Profile found    id={employer.id}  company='{employer.company_name}'"
    )
    print(f"     industry  : {employer.ai_industry or '—'}")
    print(f"     size      : {employer.ai_company_size or '—'}")
    print(f"     tenant_id : {employer.tenant_id or '—'}")

    if employer.embedding is not None:
        print(f"{PASS} Embedding present")
    else:
        print(f"{WARN} No embedding — run run_backfill.py")

    # Job orders linked to this employer
    jobs = (
        db.query(JobOrder)
        .filter(JobOrder.employer_profile_id == employer.id, JobOrder.status == "open")
        .all()
    )

    if jobs:
        print(f"{PASS} {len(jobs)} open job order(s) linked:")
        for j in jobs:
            emb_status = "embedded ✓" if j.embedding is not None else "NO embedding ✗"
            print(f"     [{j.id}] {j.title} — {j.location or '—'} — {emb_status}")
    else:
        print(f"{FAIL} No open job orders linked to this employer profile")
        print(f"     Run seed_test_profiles.py to create them")
        errors += 1
else:
    print(
        f"{FAIL} No employer profile with primary_contact_email={TEST_EMPLOYER_EMAIL}"
    )
    print(f"     Run seed_full.py or seed_test_profiles.py")
    errors += 1


# ── 4. Summary ─────────────────────────────────────────────
print()
print("=" * 56)
if errors == 0:
    print("  ✅ All checks passed — dashboards should work correctly")
else:
    print(f"  ❌ {errors} issue(s) found — see above")
print("=" * 56)
print()

db.close()
