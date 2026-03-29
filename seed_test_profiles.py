#!/usr/bin/env python3
"""
RYZE.ai — Seed Test User Profiles
Creates (or repairs) the candidate and employer profiles linked to the two
test user accounts. Safe to run multiple times — skips records that already exist.

Run from the project root:
    python seed_test_profiles.py

Test user credentials:
    Employer : test_employer@ryze.ai  / TestPassword123
    Candidate: test_candidate@ryze.ai / TestPassword123
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
TENANT_ID = "ryze"

# ── Verify test users exist ────────────────────────────────────────────────
candidate_user = db.query(User).filter(User.email == TEST_CANDIDATE_EMAIL).first()
employer_user = db.query(User).filter(User.email == TEST_EMPLOYER_EMAIL).first()

if not candidate_user:
    print(f"✗ No user found for {TEST_CANDIDATE_EMAIL} — run seed_full.py first.")
    sys.exit(1)
if not employer_user:
    print(f"✗ No user found for {TEST_EMPLOYER_EMAIL} — run seed_full.py first.")
    sys.exit(1)

print(f"✓ Found candidate user  (id={candidate_user.id})")
print(f"✓ Found employer  user  (id={employer_user.id})")


# ── Candidate Profile ──────────────────────────────────────────────────────
existing_candidate = (
    db.query(Candidate).filter(Candidate.email == TEST_CANDIDATE_EMAIL).first()
)

if existing_candidate:
    # Repair: make sure tenant_id is set (missing tenant_id breaks /api/candidates/me)
    if not existing_candidate.tenant_id:
        existing_candidate.tenant_id = TENANT_ID
        db.commit()
        print(
            f"✓ Repaired candidate profile — added tenant_id  (id={existing_candidate.id})"
        )
    else:
        print(
            f"✓ Candidate profile already exists and is healthy  (id={existing_candidate.id})"
        )
else:
    candidate = Candidate(
        tenant_id=TENANT_ID,
        name="Test Candidate",
        email=TEST_CANDIDATE_EMAIL,
        phone="617-555-0099",
        current_title="Senior Accountant",
        current_company="Demo Corp",
        location="Boston, MA",
        ai_career_level="mid",
        ai_years_experience=5,
        ai_certifications="CPA",
        ai_summary=(
            "Senior Accountant with 5 years of experience in public accounting and industry. "
            "CPA certified. Strong NetSuite and Excel skills. Looking for a Controller opportunity "
            "in the Boston area."
        ),
        ai_experience=(
            "Demo Corp (2021–present) — Senior Accountant. "
            "Grant Thornton (2019–2021) — Staff Accountant."
        ),
        ai_education="BS Accounting, Northeastern, 2019",
        ai_skills=[
            "NetSuite",
            "Excel",
            "GAAP",
            "Month-end Close",
            "Financial Reporting",
        ],
        notes="Test candidate account — linked to test_candidate@ryze.ai login.",
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    print(f"✓ Created candidate profile  (id={candidate.id})")


# ── Employer Profile ───────────────────────────────────────────────────────
existing_employer = (
    db.query(EmployerProfile)
    .filter(EmployerProfile.primary_contact_email == TEST_EMPLOYER_EMAIL)
    .first()
)

if existing_employer:
    print(f"✓ Employer profile already exists  (id={existing_employer.id})")
    employer_profile_id = existing_employer.id
else:
    employer = EmployerProfile(
        tenant_id=TENANT_ID,
        company_name="Acme Financial Services",
        website_url="https://acmefinancial.com",
        primary_contact_email=TEST_EMPLOYER_EMAIL,
        phone="617-555-0001",
        ai_industry="Financial Services",
        ai_company_size="75 employees, $25M revenue",
        ai_company_overview=(
            "Boston-based financial services firm specializing in middle-market lending "
            "and asset management. PE-backed since 2022. Profitable, growing 30% YoY. "
            "Finance team of 4 — expanding ahead of a planned 2027 Series B."
        ),
        ai_hiring_needs='["Controller — CPA required, financial services background", "Senior FP&A Analyst — SaaS metrics a plus"]',
        ai_talking_points='["PE-backed with runway to grow", "Equity available for Controller role", "Lean team — high ownership, direct CFO access", "Hybrid 3 days Boston office"]',
        ai_red_flags=None,
        relationship_status="Active",
    )
    db.add(employer)
    db.commit()
    db.refresh(employer)
    employer_profile_id = employer.id
    print(f"✓ Created employer profile  (id={employer_profile_id})")


# ── Job Orders linked to test employer ────────────────────────────────────
existing_jobs = (
    db.query(JobOrder).filter(JobOrder.employer_profile_id == employer_profile_id).all()
)

if existing_jobs:
    print(
        f"✓ Job orders already exist  ({len(existing_jobs)} linked to employer profile)"
    )
else:
    jobs = [
        JobOrder(
            employer_profile_id=employer_profile_id,
            title="Controller",
            location="Boston, MA",
            salary_min=130000,
            salary_max=155000,
            status="open",
            requirements=(
                "CPA required. 7+ years experience including financial services or asset management. "
                "Will own the monthly close, manage 2 staff accountants, and lead audit. "
                "NetSuite experience strongly preferred."
            ),
        ),
        JobOrder(
            employer_profile_id=employer_profile_id,
            title="Senior FP&A Analyst",
            location="Boston, MA",
            salary_min=90000,
            salary_max=110000,
            status="open",
            requirements=(
                "3–6 years FP&A experience. Strong Excel and financial modeling. "
                "Will support CFO on board materials, annual budget, and investor KPI reporting. "
                "Financial services or PE-backed company background preferred."
            ),
        ),
    ]
    for j in jobs:
        db.add(j)
    db.commit()
    print(f"✓ Created {len(jobs)} job orders linked to employer profile")


# ── Summary ────────────────────────────────────────────────────────────────
print()
print("✅ Test profiles ready.")
print()
print("   Next step: generate embeddings so AI matching works.")
print("   Run:  python run_backfill.py")
print()
print("   Then test:")
print(
    f"   curl -H 'Authorization: Bearer <token>' https://api.ryze.ai/api/candidates/me"
)
print(
    f"   curl -H 'Authorization: Bearer <token>' https://api.ryze.ai/api/candidates/me/job-matches"
)

db.close()
