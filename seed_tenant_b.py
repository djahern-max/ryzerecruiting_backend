"""
seed_tenant_b.py
────────────────
EP16 — Seeds a second tenant ("firm_b") for isolation testing.

Creates:
  • 1 admin user  (admin@firmb.com / FirmBAdmin123!)
  • 4 candidates  (all tenant_id = "firm_b")
  • 2 employer profiles  (all tenant_id = "firm_b")
  • 2 job orders  (all tenant_id = "firm_b")

Run once before running test_tenant_isolation.py:
  python seed_tenant_b.py

Safe to re-run — skips records that already exist.
"""

import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserType
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder

FIRM_B = "firm_b"
ADMIN_EMAIL = "admin@firmb.com"
ADMIN_PASSWORD = os.getenv("FIRM_B_PASSWORD", "")

GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")


def skip(msg):
    print(f"  {YELLOW}–{RESET} {msg} (already exists)")


def main():
    db = SessionLocal()
    print("\n── Seeding Tenant B (firm_b) ───────────────────────────\n")

    try:
        # ── Admin user ───────────────────────────────────────────
        existing_user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing_user:
            skip(f"User {ADMIN_EMAIL}")
            firm_b_user = existing_user
        else:
            firm_b_user = User(
                email=ADMIN_EMAIL,
                hashed_password=get_password_hash(ADMIN_PASSWORD),
                full_name="Firm B Admin",
                user_type=UserType.ADMIN,
                is_active=True,
                is_superuser=True,
                tenant_id=FIRM_B,
            )
            db.add(firm_b_user)
            db.commit()
            db.refresh(firm_b_user)
            ok(f"Created admin user: {ADMIN_EMAIL}  (tenant={FIRM_B})")

        # ── Candidates ───────────────────────────────────────────
        candidates = [
            dict(
                name="Rachel Torres",
                email="rtorres@gmail.com",
                phone="617-555-0201",
                current_title="Senior Accountant",
                current_company="Blue Ridge Capital",
                location="Austin, TX",
                ai_career_level="mid",
                ai_years_experience=6,
                ai_summary="Senior Accountant at a mid-size PE-backed firm. CPA candidate, strong month-end close skills.",
                notes="Target $85–95K. Open to Controller track.",
            ),
            dict(
                name="Marcus Webb",
                email="mwebb@gmail.com",
                phone="617-555-0202",
                current_title="Controller",
                current_company="Lone Star Manufacturing",
                location="Dallas, TX",
                ai_career_level="senior",
                ai_years_experience=11,
                ai_certifications="CPA",
                ai_summary="Controller at a 200-person manufacturer. Full close ownership, manages 3-person team. Prior Big 4 at Deloitte.",
                notes="Target $130–150K. Wants Director of Finance path.",
            ),
            dict(
                name="Priya Nair",
                email="pnair@gmail.com",
                phone="617-555-0203",
                current_title="FP&A Analyst",
                current_company="SaaS Corp",
                location="Austin, TX",
                ai_career_level="junior",
                ai_years_experience=3,
                ai_summary="FP&A Analyst at a 50-person SaaS company. Owns board deck and ARR reporting. Fast-tracker.",
                notes="Target $75–85K. Wants FP&A Manager role.",
            ),
            dict(
                name="Derek Owens",
                email="dowens@gmail.com",
                phone="617-555-0204",
                current_title="CFO",
                current_company="Venture Partners TX",
                location="Houston, TX",
                ai_career_level="executive",
                ai_years_experience=20,
                ai_certifications="CPA, MBA",
                ai_summary="CFO at a $200M AUM venture firm. Prior operating CFO at two PE-backed portfolio companies. Deep M&A background.",
                notes="Target $250K+. Only interested in operating CFO or VP Finance roles.",
            ),
        ]

        for c_data in candidates:
            existing = (
                db.query(Candidate)
                .filter(
                    Candidate.email == c_data["email"], Candidate.tenant_id == FIRM_B
                )
                .first()
            )
            if existing:
                skip(f"Candidate {c_data['name']}")
            else:
                candidate = Candidate(tenant_id=FIRM_B, **c_data)
                db.add(candidate)
                ok(f"Created candidate: {c_data['name']}  (tenant={FIRM_B})")

        db.commit()

        # ── Employer profiles ────────────────────────────────────
        employers = [
            dict(
                company_name="Bluehorn Technologies",
                website_url="https://bluehorn.io",
                primary_contact_email="hr@bluehorn.io",
                ai_industry="SaaS / Technology",
                ai_company_size="150–200 employees",
                ai_company_overview="B2B SaaS company focused on supply chain automation. Series C. Growing finance team.",
                relationship_status="active",
                tenant_id=FIRM_B,
            ),
            dict(
                company_name="Redrock Investments",
                website_url="https://redrockfund.com",
                primary_contact_email="ops@redrockfund.com",
                ai_industry="Private Equity / Investment Management",
                ai_company_size="30–50 employees",
                ai_company_overview="Lower middle-market PE fund. $500M AUM. Hiring across portfolio companies.",
                relationship_status="prospect",
                tenant_id=FIRM_B,
            ),
        ]

        for e_data in employers:
            existing = (
                db.query(EmployerProfile)
                .filter(
                    EmployerProfile.company_name == e_data["company_name"],
                    EmployerProfile.tenant_id == FIRM_B,
                )
                .first()
            )
            if existing:
                skip(f"Employer {e_data['company_name']}")
                if e_data["company_name"] == "Bluehorn Technologies":
                    bluehorn_id = existing.id
                else:
                    redrock_id = existing.id
            else:
                ep = EmployerProfile(**e_data)
                db.add(ep)
                db.flush()
                if e_data["company_name"] == "Bluehorn Technologies":
                    bluehorn_id = ep.id
                else:
                    redrock_id = ep.id
                ok(f"Created employer: {e_data['company_name']}  (tenant={FIRM_B})")

        db.commit()

        # ── Job orders ───────────────────────────────────────────
        job_orders = [
            dict(
                title="Senior Accountant",
                location="Austin, TX",
                salary_min=85000,
                salary_max=100000,
                requirements="CPA preferred. 5+ years experience. SaaS industry a plus.",
                status="open",
                tenant_id=FIRM_B,
                employer_profile_id=bluehorn_id,
            ),
            dict(
                title="Portfolio Finance Manager",
                location="Dallas, TX (hybrid)",
                salary_min=120000,
                salary_max=145000,
                requirements="PE background required. 8+ years. CPA preferred.",
                status="open",
                tenant_id=FIRM_B,
                employer_profile_id=redrock_id,
            ),
        ]

        for j_data in job_orders:
            existing = (
                db.query(JobOrder)
                .filter(
                    JobOrder.title == j_data["title"],
                    JobOrder.tenant_id == FIRM_B,
                )
                .first()
            )
            if existing:
                skip(f"Job order: {j_data['title']}")
            else:
                job = JobOrder(**j_data)
                db.add(job)
                ok(f"Created job order: {j_data['title']}  (tenant={FIRM_B})")

        db.commit()

    except Exception as e:
        db.rollback()
        print(f"\n  ✗ Error: {e}")
        raise
    finally:
        db.close()

    print(f"\n── Seed complete ───────────────────────────────────────")
    print(f"  Admin login : {ADMIN_EMAIL}")
    print(f"  Password    : {ADMIN_PASSWORD}")
    print(f"  Tenant      : {FIRM_B}")
    print(f"\n  Next step   : python test_tenant_isolation.py\n")


if __name__ == "__main__":
    main()
