# seed_landscaping_jobs.py
# ---------------------------------------------------------------------------
# Seeds the database with open landscaping-industry job orders for the
# RYZE.ai demo video, then generates pgvector embeddings for each so the
# candidate dashboard's AI matching ranks them against Renata's profile.
#
# The flagship job — "Landscape Designer" at Greenscene Landscaping
# (Walt Kessler's company, greenscene.io) — is linked to Greenscene's
# EmployerProfile. The script REUSES an existing Greenscene profile if the
# booking flow already created one (matched by name or website), and only
# creates a new profile if none exists. This makes the demo loop complete:
#   - Renata's dashboard: Greenscene role ranks as a top match
#   - Walt's employer dashboard: his job order appears under
#     "Your AI Opportunities" with Renata in the candidate matches
#   - Intelligence chat: "Show me matches for Renata Voss" surfaces it
#
# Usage (from the backend repo root, with your venv active):
#     python seed_landscaping_jobs.py
#
# To wipe job orders and re-seed (does NOT delete employer profiles):
#     python seed_landscaping_jobs.py --reset
# ---------------------------------------------------------------------------

import sys

from sqlalchemy import or_

from app.core.database import SessionLocal
from app.models.job_order import JobOrder, RYZE_TENANT
from app.models.employer_profile import EmployerProfile
from app.models.user import User  # noqa: F401 — registers `users` table for EmployerProfile.user_id FK
from app.services.embedding_service import (
    embed_job_order_background,
    embed_employer_background,
)

GREENSCENE_NAME = "Greenscene Landscaping"
GREENSCENE_URL = "https://greenscene.io/"

# The flagship demo job — tuned to be Renata's #1 match.
GREENSCENE_JOB = {
    "title": "Landscape Designer",
    "location": "Charlotte, NC",
    "salary_min": 82000,
    "salary_max": 100000,
    "requirements": (
        "Greenscene Landscaping is seeking an experienced landscape designer "
        "to lead residential and boutique commercial design-build projects "
        "from concept through construction documents. The right candidate has "
        "10+ years of progressive experience, owns client relationships on "
        "premium projects ($75K+), produces full planting and hardscape "
        "plans, coordinates with build crews, and mentors junior designers. "
        "Deep knowledge of Carolinas plant palettes required; NC Certified "
        "Plant Professional strongly preferred. CAD proficiency essential."
    ),
    "notes": "Walt Kessler (owner) — priority requisition from discovery call.",
}

# Supporting roles — realistic pipeline filler with varied match strength.
OTHER_JOBS = [
    {
        "title": "Lead Designer — Residential Design-Build",
        "location": "Asheville, NC",
        "salary_min": 78000,
        "salary_max": 95000,
        "requirements": (
            "Established design-build studio in the Blue Ridge region looking for a "
            "lead designer with mountain-property experience. Responsibilities include "
            "site surveys, plant selection for elevation and microclimate, CAD "
            "drafting, construction documentation, and representing the studio at "
            "regional home and garden shows. Senior-level candidates with 10+ years "
            "preferred."
        ),
        "notes": "Relocation assistance available.",
    },
    {
        "title": "Landscape Architect / Senior Designer",
        "location": "Greenville, SC",
        "salary_min": 80000,
        "salary_max": 98000,
        "requirements": (
            "Growing outdoor living company seeking a senior designer to lead its "
            "high-end residential division. End-to-end project ownership: concept "
            "design, client presentations, construction documents, subcontractor "
            "coordination, and installation oversight. Certified Plant Professional "
            "or equivalent certification a plus. OSHA awareness required for "
            "job-site walks."
        ),
        "notes": None,
    },
    {
        "title": "Landscape Project Manager",
        "location": "Raleigh, NC",
        "salary_min": 70000,
        "salary_max": 88000,
        "requirements": (
            "Commercial landscape contractor seeking a project manager to oversee "
            "installation crews, scheduling, budgets, and client communication for "
            "commercial campus and HOA projects. Design background helpful but the "
            "role is primarily field and operations management. 5+ years in the "
            "green industry required."
        ),
        "notes": None,
    },
    {
        "title": "Garden Center Design Consultant",
        "location": "Columbia, SC",
        "salary_min": 52000,
        "salary_max": 64000,
        "requirements": (
            "Retail garden center seeking an in-house design consultant to create "
            "small-scale residential planting plans for walk-in customers, run "
            "seasonal design workshops, and support the nursery sales team with "
            "plant recommendations. Horticulture knowledge required; CAD optional."
        ),
        "notes": None,
    },
    {
        "title": "Irrigation Technician",
        "location": "Charlotte, NC",
        "salary_min": 45000,
        "salary_max": 58000,
        "requirements": (
            "Landscape maintenance company hiring an irrigation technician for "
            "installation, troubleshooting, and repair of residential and commercial "
            "irrigation systems. Backflow certification preferred. Entry to "
            "mid-level; no design responsibilities."
        ),
        "notes": None,
    },
]


def get_or_create_greenscene(db):
    """
    Reuse the Greenscene EmployerProfile if the booking flow already created
    one (Walt's discovery call auto-creates a stub matched by email/website).
    Only create a fresh profile if none exists. Never duplicates.
    """
    profile = (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.tenant_id == RYZE_TENANT,
            or_(
                EmployerProfile.company_name.ilike("%greenscene%"),
                EmployerProfile.website_url.ilike("%greenscene.io%"),
            ),
        )
        .first()
    )
    if profile:
        print(
            f"Found existing Greenscene profile #{profile.id} "
            f"('{profile.company_name}') — linking job order to it."
        )
        return profile, False

    profile = EmployerProfile(
        tenant_id=RYZE_TENANT,
        company_name=GREENSCENE_NAME,
        website_url=GREENSCENE_URL,
        ai_industry="Landscaping & Outdoor Design",
        ai_company_overview=(
            "Greenscene Landscaping is a design-build landscaping firm serving "
            "residential and boutique commercial clients in the Charlotte, NC "
            "area, led by owner Walt Kessler. The firm handles projects from "
            "concept design through installation and is growing its design team."
        ),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    print(f"Created new Greenscene profile #{profile.id}.")
    return profile, True


def main() -> None:
    reset = "--reset" in sys.argv
    db = SessionLocal()
    try:
        if reset:
            deleted = (
                db.query(JobOrder)
                .filter(JobOrder.tenant_id == RYZE_TENANT)
                .delete(synchronize_session=False)
            )
            db.commit()
            print(f"Deleted {deleted} existing job order(s) for tenant '{RYZE_TENANT}'.")

        # ── Greenscene: employer profile + flagship job order ──────────────
        greenscene, created = get_or_create_greenscene(db)

        created_job_ids = []

        flagship = JobOrder(
            tenant_id=RYZE_TENANT,
            status="open",
            employer_profile_id=greenscene.id,
            **GREENSCENE_JOB,
        )
        db.add(flagship)
        db.commit()
        db.refresh(flagship)
        created_job_ids.append(flagship.id)
        print(
            f"Created job order #{flagship.id}: {flagship.title} "
            f"(Greenscene Landscaping, employer_profile_id={greenscene.id})"
        )

        # ── Supporting job orders (no employer link) ───────────────────────
        for spec in OTHER_JOBS:
            job = JobOrder(tenant_id=RYZE_TENANT, status="open", **spec)
            db.add(job)
            db.commit()
            db.refresh(job)
            created_job_ids.append(job.id)
            print(f"Created job order #{job.id}: {job.title} ({job.location})")

        # ── Embeddings (synchronous — needs OPENAI key in env) ─────────────
        print("\nGenerating embeddings (calls OpenAI)...")
        for job_id in created_job_ids:
            embed_job_order_background(job_id)

        # Only embed the employer profile if WE created it. If the booking
        # flow created it, it already has (or will get) an embedding, and we
        # don't want to overwrite anything from the real interview data.
        if created:
            embed_employer_background(greenscene.id)

        print(f"\nDone. Seeded {len(created_job_ids)} open job orders.")
        print("Check: Renata's dashboard, Walt's employer dashboard, and")
        print('Intelligence chat ("Show me matches for Renata Voss").')
    finally:
        db.close()


if __name__ == "__main__":
    main()
