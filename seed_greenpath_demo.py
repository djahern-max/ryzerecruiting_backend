#!/usr/bin/env python3
"""
RYZE.ai — Greenpath Recruiting Demo Seed (Grand Finale)
=======================================================

Wipes the database down to the superadmin (user id 1), then seeds a rich,
fully green-industry dataset into the `green_path_recruiting` tenant:

    22 candidates   — designers, superintendents, arborists, horticulturists,
                      irrigation pros, crew leads, nursery & garden-center staff
    12 employers    — landscaping firms, golf clubs, nurseries, tree care,
                      irrigation, sod farm, interiorscape, garden center
    18 job orders   — incl. the flagship "Landscape Designer" at Greenscene
                      Landscaping (Walt Kessler), tuned as Renata Voss's #1 match
    28 bookings     — client intake calls + candidate screens with AI meeting
                      summaries, next steps, keywords; a few upcoming/pending

Renata Voss and Walt Kessler are re-created as seeded fixtures (with synthetic
meeting summaries + short transcripts) so the demo loop from earlier episodes —
"Show me matches for Renata Voss", Walt's Greenscene job — still works.

IMPORTANT — tenant handling:
  * Recruiter dashboards and Intelligence chat are tenant-scoped.
  * On seed, user id 1 is stamped tenant_id='green_path_recruiting' so YOUR
    login sees all of this data. (You remain superuser.)
  * On --wipe-only, user id 1 is restored to tenant_id='ryze'.
  * The green_path_recruiting Tenant row is created if missing and forced to
    status='active' so a mid-demo trial expiry can never 402 you.

Usage (backend repo root, venv active, .env loaded):
    python seed_greenpath_demo.py               # wipe everything (except user 1) + seed
    python seed_greenpath_demo.py --wipe-only   # post-demo teardown: wipe + restore user 1 to ryze

Then generate embeddings (required for AI matching):
    python run_backfill.py

THIS SCRIPT DELETES ALL DATA except users.id = 1. It will ask you to type
'yes' before doing anything. Run extract_call_data.py first if you want to
snapshot any real Zoom transcripts (tokens expire ~24h).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from datetime import date, datetime, timedelta

from sqlalchemy import text

# Import all models so SQLAlchemy resolves every FK
import app.models.user  # noqa: F401
import app.models.tenant  # noqa: F401
import app.models.booking  # noqa: F401
import app.models.candidate  # noqa: F401
import app.models.employer_profile  # noqa: F401
import app.models.job_order  # noqa: F401
import app.models.chat_session  # noqa: F401
import app.models.chat_message  # noqa: F401
import app.models.contact  # noqa: F401
import app.models.waitlist  # noqa: F401
import app.models.webhook_log  # noqa: F401

from app.core.database import SessionLocal
from app.models.user import User
from app.models.tenant import Tenant
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder
from app.models.booking import Booking

TENANT = "green_path_recruiting"
BRAND = "Green Path Recruiting"
SEED_MARKER = "__GREENPATH_SEED__"
SUPERADMIN_ID = 1

db = SessionLocal()
today = date.today()


def d(days_ago):
    return today - timedelta(days=days_ago)


def dt(days_ago, hour=10):
    return datetime(today.year, today.month, today.day, hour, 0) - timedelta(days=days_ago)


def mark(text_):
    return f"{text_} {SEED_MARKER}" if text_ else SEED_MARKER


# ── WIPE ─────────────────────────────────────────────────────────────────────
# Order matters for FKs: children first. Each table is wrapped so a missing
# table (schema drift between environments) never aborts the wipe.

WIPE_TABLES = [
    "chat_messages",     # FK -> chat_sessions
    "chat_sessions",     # FK -> users
    "job_interests",     # FK -> candidates / job_orders
    "bookings",          # FK -> employer_profiles, candidates, users
    "job_orders",        # FK -> employer_profiles
    "candidates",        # FK -> users (SET NULL), bookings (SET NULL)
    "employer_profiles",
    "webhook_logs",
    "contacts",
    "waitlist",
]


def wipe_all(restore_ryze_tenant: bool):
    print("🗑️  Wiping database (preserving user id 1)...\n")
    for table in WIPE_TABLES:
        try:
            result = db.execute(text(f"DELETE FROM {table}"))
            db.commit()
            print(f"   ✓ {table:<18} {result.rowcount} deleted")
        except Exception as e:
            db.rollback()
            print(f"   ⚠ {table:<18} skipped ({type(e).__name__})")

    # All users except the superadmin
    result = db.execute(text("DELETE FROM users WHERE id != :sid"), {"sid": SUPERADMIN_ID})
    db.commit()
    print(f"   ✓ {'users':<18} {result.rowcount} deleted (kept id={SUPERADMIN_ID})")

    # Reset sequences so demo IDs start at 1 (users sequence left alone)
    for table in WIPE_TABLES:
        try:
            db.execute(text(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1"))
            db.commit()
        except Exception:
            db.rollback()
    print("   ✓ ID sequences reset (users untouched)\n")

    admin = db.query(User).filter(User.id == SUPERADMIN_ID).first()
    if admin is None:
        print(f"❌ No user with id={SUPERADMIN_ID} found — aborting.")
        sys.exit(1)

    if restore_ryze_tenant:
        admin.tenant_id = "ryze"
        db.commit()
        print(f"   ✓ user #{SUPERADMIN_ID} ({admin.email}) restored to tenant 'ryze'\n")
    return admin


def ensure_tenant():
    """Create/activate the Greenpath tenant so billing checks never 402."""
    tenant = db.query(Tenant).filter(Tenant.slug == TENANT).first()
    if tenant is None:
        tenant = Tenant(slug=TENANT, company_name=BRAND, status="active")
        db.add(tenant)
        db.commit()
        print(f"   ✓ Tenant '{TENANT}' created (status=active)")
    else:
        tenant.status = "active"
        db.commit()
        print(f"   ✓ Tenant '{TENANT}' set to status=active")
    return tenant


def stamp_admin_tenant(admin):
    admin.tenant_id = TENANT
    db.commit()
    print(f"   ✓ user #{SUPERADMIN_ID} ({admin.email}) moved into tenant '{TENANT}'")
    print(f"     → your login now sees all Greenpath data (still superuser)\n")

# ── CANDIDATES ───────────────────────────────────────────────────────────────


def seed_candidates():
    print("Seeding candidates...")
    candidates = [
        # ── Flagship: Renata Voss (matches the Greenscene Landscape Designer job) ──
        Candidate(
            tenant_id=TENANT,
            name="Renata Voss",
            email="renata.voss@gmail.com",
            phone="704-555-0101",
            current_title="Landscape Designer",
            current_company="Terra Firma Design Group",
            location="Charlotte, NC",
            linkedin_url="https://linkedin.com/in/renatavoss",
            source="booking",
            ai_career_level="senior",
            ai_years_experience=9,
            ai_certifications="APLD Certified Landscape Designer",
            ai_summary="Accomplished landscape designer with 9 years leading residential and boutique commercial design-build projects from concept through construction documents. Deep planting-design expertise for the Southeast (zones 7b–8a), strong AutoCAD and SketchUp skills, and a proven record presenting to clients and managing install crews through construction. Ready to be the lead designer at a growing design-build firm.",
            ai_experience="Terra Firma Design Group, Charlotte (2020–present) — Landscape Designer: 30+ residential design-build projects/yr, avg contract $85K, leads client presentations and construction docs. Southern Roots Landscapes, Raleigh (2017–2020) — Junior Designer: planting plans, hardscape layouts, permit sets.",
            ai_education="BLA Landscape Architecture, NC State University, 2017",
            ai_skills=["AutoCAD", "SketchUp", "Planting Design", "Construction Documents", "Design-Build", "Client Presentations", "Grading & Drainage", "Native Plants"],
            meeting_transcript=mark(
                "Recruiter: Renata, thanks for hopping on. Walk me through what you're doing at Terra Firma. "
                "Renata: I run design-build projects end to end — concept sketches, planting plans, hardscape layout, full construction documents, then I stay involved through install. Last year I closed about thirty projects, average contract around eighty-five thousand. "
                "Recruiter: What's pulling you to look? "
                "Renata: I want to be THE lead designer somewhere that's growing — own the design studio, mentor a junior, shape the portfolio. Terra Firma is great but the senior chair is taken. "
                "Recruiter: Comp expectations? "
                "Renata: High eighties to about a hundred, plus a real project bonus. Staying in Charlotte."
            ),
            notes=mark("Flagship candidate. Wants lead-designer seat at a growing design-build firm. Target $85–100K, Charlotte only. Perfect match for Greenscene."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Marcus Webb",
            email="mwebb.turf@gmail.com",
            phone="910-555-0102",
            current_title="Golf Course Superintendent",
            current_company="Longleaf Pines Golf Club",
            location="Pinehurst, NC",
            source="manual",
            ai_career_level="senior",
            ai_years_experience=15,
            ai_certifications="GCSAA Class A, NC Pesticide Applicator License",
            ai_summary="Class A superintendent with 15 years on championship bermudagrass and bentgrass surfaces in the Sandhills. Led a full greens renovation (ultradwarf conversion), manages a crew of 22 and a $1.4M maintenance budget. Known for tournament-grade conditioning and strong agronomic planning.",
            ai_experience="Longleaf Pines GC (2016–present) — Superintendent: 18-hole private club, greens renovation 2021, hosts state amateur events. Whispering Sands GC (2011–2016) — Assistant Superintendent.",
            ai_education="AAS Turfgrass Management, Sandhills Community College, 2011",
            ai_skills=["Bermudagrass", "Bentgrass Greens", "Budget Management", "Crew Leadership", "Irrigation Central Control", "Tournament Prep", "Agronomic Planning"],
            notes=mark("Open to director-level or a bigger club. Target $110–130K + housing consideration."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Daniela Cruz",
            email="dcruz.hort@gmail.com",
            phone="704-555-0103",
            current_title="Nursery Production Manager",
            current_company="Yadkin Valley Growers",
            location="Statesville, NC",
            source="linkedin",
            ai_career_level="senior",
            ai_years_experience=11,
            ai_certifications="NC Certified Plant Professional",
            ai_summary="Horticulturist and production manager running 40 acres of container ornamentals — propagation through finished goods. Cut crop loss 30% with a revamped IPM program and manages a seasonal team of 25. Strong on production scheduling, inventory forecasting, and wholesale quality standards.",
            ai_experience="Yadkin Valley Growers (2018–present) — Production Manager: 40-acre container operation, 400+ SKUs. Metrolina-area grower (2013–2018) — Section Grower: annuals and perennials.",
            ai_education="BS Horticultural Science, NC State University, 2013",
            ai_skills=["Container Production", "Propagation", "IPM", "Production Scheduling", "Team Leadership", "Wholesale Standards", "Greenhouse Operations"],
            notes=mark("Bilingual EN/ES. Wants a head-grower or GM path. Target $80–95K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Tyler Brandt",
            email="tbrandt.trees@gmail.com",
            phone="828-555-0104",
            current_title="Crew Leader / Climber",
            current_company="Blue Ridge Tree Service",
            location="Asheville, NC",
            source="manual",
            ai_career_level="mid",
            ai_years_experience=7,
            ai_certifications="ISA Certified Arborist, EHAP, CPR/First Aid",
            ai_summary="ISA Certified Arborist and lead climber with 7 years in residential and municipal tree care. Comfortable with technical removals, crane work, and pruning to ANSI A300. Runs a 3-person crew and handles client walk-throughs and estimates on smaller jobs.",
            ai_experience="Blue Ridge Tree Service (2019–present) — Crew Leader: technical removals, crane jobs, storm response. Asheville Parks contractor crews (2017–2019) — Groundman to climber.",
            ai_education="Certificate in Arboriculture, A-B Tech, 2018",
            ai_skills=["Technical Removals", "Crane Work", "ANSI A300 Pruning", "Rigging", "Crew Leadership", "Estimating", "Storm Response"],
            notes=mark("Wants a foreman/ops path at a larger TCIA-accredited company. Target $30–35/hr."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Aisha Simmons",
            email="asimmons.design@gmail.com",
            phone="704-555-0105",
            current_title="Junior Landscape Designer",
            current_company="Freelance",
            location="Charlotte, NC",
            source="resume",
            ai_career_level="junior",
            ai_years_experience=2,
            ai_certifications=None,
            ai_summary="Recent landscape architecture graduate with two years of freelance residential design work. Strong rendering and 3D visualization skills (Lumion, SketchUp) and a fresh, plant-forward design sensibility. Looking for her first full-time studio seat under a senior designer.",
            ai_experience="Freelance (2024–present) — 15 residential planting and patio designs in the Charlotte metro. Internship at city planning department, 2023.",
            ai_education="BLA Landscape Architecture, UNC Charlotte, 2024",
            ai_skills=["SketchUp", "Lumion", "Adobe Creative Suite", "Planting Design", "Rendering", "AutoCAD"],
            notes=mark("High-upside junior. Would pair well under a senior designer. Target $52–60K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Greg Holloway",
            email="gholloway.grounds@gmail.com",
            phone="919-555-0106",
            current_title="Branch Manager",
            current_company="TruNorth Landscape Services",
            location="Raleigh, NC",
            source="linkedin",
            ai_career_level="executive",
            ai_years_experience=18,
            ai_certifications="NALP Landscape Industry Certified Manager",
            ai_summary="Commercial landscape branch leader running a $6.5M maintenance and enhancement book across HOA, retail, and Class-A office portfolios. Grew branch revenue 40% in three years, holds 92% client retention, and manages 55 field staff across 9 routes. P&L owner with strong estimating and account-management discipline.",
            ai_experience="TruNorth Landscape Services (2015–present) — Branch Manager, Raleigh: $6.5M revenue, 55 FTE. BrightView (2008–2015) — Account Manager then Ops Manager.",
            ai_education="BS Business Administration, ECU, 2008",
            ai_skills=["P&L Management", "Commercial Maintenance", "Account Management", "Estimating", "Snow Operations", "Fleet Oversight", "Client Retention"],
            notes=mark("Confidential search — wants regional/GM role. Target $120–140K + bonus."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Priya Natarajan",
            email="priya.irrigation@gmail.com",
            phone="704-555-0107",
            current_title="Irrigation Designer",
            current_company="AquaLogic Systems",
            location="Charlotte, NC",
            source="manual",
            ai_career_level="senior",
            ai_years_experience=10,
            ai_certifications="EPA WaterSense Partner, Certified Irrigation Designer (CID), Hunter & Rain Bird factory training",
            ai_summary="Certified Irrigation Designer with a decade of commercial and high-end residential system design — hydraulic calcs, smart-controller specification, and water-budget compliance. Has designed 200+ systems including athletic fields and two-wire commercial installs, and mentors field techs on troubleshooting.",
            ai_experience="AquaLogic Systems (2019–present) — Irrigation Designer: commercial + estate systems, smart controllers, LEED water budgets. Southeast irrigation contractor (2015–2019) — Service Tech to Design Assistant.",
            ai_education="BS Civil Engineering, UNC Charlotte, 2015",
            ai_skills=["Hydraulic Design", "Two-Wire Systems", "Smart Controllers", "Water Budgeting", "AutoCAD", "Athletic Field Irrigation", "Troubleshooting"],
            notes=mark("Wants design-lead or water-management director role. Target $90–105K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Sam Ortiz",
            email="sortiz.hardscape@gmail.com",
            phone="803-555-0108",
            current_title="Hardscape Foreman",
            current_company="StoneBridge Outdoor Construction",
            location="Rock Hill, SC",
            source="manual",
            ai_career_level="mid",
            ai_years_experience=9,
            ai_certifications="ICPI Certified Installer, NCMA Certified SRW Installer",
            ai_summary="Hardscape foreman specializing in paver patios, retaining walls, and outdoor kitchens. ICPI and NCMA certified with a reputation for tight tolerances and zero-callback installs. Reads plans fluently, runs skid steers and mini-ex, and manages 2 crews on projects up to $250K.",
            ai_experience="StoneBridge Outdoor Construction (2018–present) — Foreman: patios, SRW walls, outdoor kitchens, pool decks. Residential mason crews (2015–2018).",
            ai_education="High school diploma; ICPI/NCMA certification coursework",
            ai_skills=["Paver Installation", "Segmental Retaining Walls", "Outdoor Kitchens", "Plan Reading", "Equipment Operation", "Crew Management", "Grading"],
            notes=mark("Wants superintendent role on larger design-build projects. Target $75–85K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Kelly Runyon",
            email="krunyon.gc@gmail.com",
            phone="704-555-0109",
            current_title="Assistant Store Manager",
            current_company="Pike Nurseries",
            location="Matthews, NC",
            source="resume",
            ai_career_level="mid",
            ai_years_experience=6,
            ai_certifications="NC Certified Plant Professional",
            ai_summary="Garden-center retail leader with 6 years across merchandising, green-goods buying, and seasonal staffing. Runs a $3M-revenue store's plant department, built its spring workshop program, and consistently posts the chain's lowest shrink on live goods.",
            ai_experience="Pike Nurseries, Matthews (2020–present) — Assistant Store Manager. Local independent garden center (2018–2020) — Perennials lead.",
            ai_education="BA Communications, Appalachian State, 2018",
            ai_skills=["Retail Management", "Green Goods Buying", "Merchandising", "Seasonal Staffing", "Customer Education", "Inventory / Shrink Control"],
            notes=mark("Ready for a store-manager seat at an independent. Target $60–70K + bonus."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Victor Alvarez",
            email="valvarez.phc@gmail.com",
            phone="704-555-0110",
            current_title="Plant Health Care Technician",
            current_company="Carolina Lawn Doctors",
            location="Concord, NC",
            source="manual",
            ai_career_level="mid",
            ai_years_experience=5,
            ai_certifications="NC Pesticide Applicator License (L, N, D), ISA Certified Arborist candidate",
            ai_summary="Licensed spray tech running turf and ornamental PHC routes — fertilization, weed control, disease and insect programs. Diagnoses in the field, manages 400+ accounts on a route, and is studying for the ISA arborist exam to move into tree PHC.",
            ai_experience="Carolina Lawn Doctors (2021–present) — PHC Technician: turf + ornamental programs, route management. Landscape maintenance crews (2019–2021).",
            ai_education="AAS Horticulture Technology, CPCC, 2021",
            ai_skills=["Pesticide Application", "Turf Programs", "Ornamental PHC", "Field Diagnosis", "Route Management", "Customer Communication"],
            notes=mark("Wants tree PHC role with arborist mentorship. Target $25–28/hr."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Joanne Fitch",
            email="jfitch.landscape@gmail.com",
            phone="704-555-0111",
            current_title="Landscape Account Manager",
            current_company="Metro Grounds Management",
            location="Charlotte, NC",
            source="linkedin",
            ai_career_level="senior",
            ai_years_experience=12,
            ai_certifications="NALP Landscape Industry Certified",
            ai_summary="Commercial account manager carrying a $2.8M maintenance portfolio of HOA and office properties with a 95% renewal rate. Strong estimator — takeoffs, enhancement proposals, snow contracts — and a calm, board-meeting-ready client presence.",
            ai_experience="Metro Grounds Management (2017–present) — Account Manager: $2.8M book, enhancement sales $600K/yr. Yellowstone Landscape (2013–2017) — Assistant AM.",
            ai_education="BS Horticulture, Clemson University, 2013",
            ai_skills=["Account Management", "Estimating & Takeoffs", "Enhancement Sales", "HOA Boards", "Snow Contracts", "Contract Renewals"],
            notes=mark("Wants senior AM or client-services director. Target $85–95K + commission."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Dustin Pham",
            email="dpham.turf@gmail.com",
            phone="336-555-0112",
            current_title="Assistant Golf Course Superintendent",
            current_company="Oak Hollow Golf Course",
            location="High Point, NC",
            source="manual",
            ai_career_level="mid",
            ai_years_experience=6,
            ai_certifications="GCSAA Class C, NC Pesticide Applicator License",
            ai_summary="Assistant superintendent with 6 years on public and semi-private courses. Owns daily course setup, chemical applications, and irrigation troubleshooting on an aging Toro system. Hungry for his first superintendent seat and known for squeezing quality out of tight budgets.",
            ai_experience="Oak Hollow GC (2021–present) — Assistant Superintendent. Tanglewood Park golf maintenance (2018–2021) — Spray tech / crew.",
            ai_education="Turfgrass Management Certificate, NC State, 2018",
            ai_skills=["Course Setup", "Chemical Applications", "Irrigation Repair", "Toro Systems", "Budget-Conscious Agronomy", "Crew Supervision"],
            notes=mark("First superintendent seat, will relocate in NC. Target $70–85K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Carmen Delgado",
            email="cdelgado.plants@gmail.com",
            phone="704-555-0113",
            current_title="Interiorscape Supervisor",
            current_company="Verdant Interiors",
            location="Charlotte, NC",
            source="manual",
            ai_career_level="mid",
            ai_years_experience=8,
            ai_certifications="NC Certified Plant Professional",
            ai_summary="Interior plantscape supervisor maintaining living installations across 60 corporate and hospitality accounts uptown. Expert in low-light tropicals, moss walls, and holiday décor programs; manages 6 techs and handles design refreshes and account upsells.",
            ai_experience="Verdant Interiors (2017–present) — Supervisor: 60 accounts, 6 techs, holiday program lead. Hotel horticulture team (2016–2017).",
            ai_education="AAS Horticulture Technology, CPCC, 2016",
            ai_skills=["Interior Plantscaping", "Tropical Plant Care", "Moss Walls", "Holiday Décor Programs", "Account Upsells", "Team Supervision"],
            notes=mark("Wants ops-manager role or to build a division. Target $65–75K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Bobby Lane",
            email="blane.sod@gmail.com",
            phone="704-555-0114",
            current_title="Farm Operations Manager",
            current_company="Catawba River Sod",
            location="Mount Holly, NC",
            source="manual",
            ai_career_level="senior",
            ai_years_experience=14,
            ai_certifications="NC Pesticide Applicator License, CDL Class A",
            ai_summary="Sod farm operations manager over 600 production acres of TifTuf bermuda, zoysia, and fescue. Runs harvest scheduling, big-roll and slab logistics, a 12-person crew, and equipment maintenance for harvesters, sprayers, and irrigation pivots. CDL holder who still jumps in the truck when it matters.",
            ai_experience="Catawba River Sod (2014–present) — Operations Manager: 600 acres, delivery fleet, wholesale + contractor sales support. Row-crop farm operations (2010–2014).",
            ai_education="AAS Agribusiness, Gaston College, 2010",
            ai_skills=["Sod Production", "Harvest Logistics", "Equipment Maintenance", "Irrigation Pivots", "Crew Management", "CDL / Fleet", "Wholesale Fulfillment"],
            notes=mark("Happy but listening for GM-level farm roles. Target $95–110K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Hannah Brooks",
            email="hbrooks.la@gmail.com",
            phone="704-555-0115",
            current_title="Landscape Designer",
            current_company="Copper Creek Landscapes",
            location="Huntersville, NC",
            source="linkedin",
            ai_career_level="mid",
            ai_years_experience=5,
            ai_certifications=None,
            ai_summary="Design-build landscape designer with 5 years of residential work — patios, pool surrounds, and layered planting plans. Solid AutoCAD and hand-sketching skills; strong at value-engineering designs to hit client budgets without losing the look.",
            ai_experience="Copper Creek Landscapes (2021–present) — Designer: ~20 projects/yr, avg $45K. Design internships during school.",
            ai_education="BS Horticultural Science (Landscape Design), NC State, 2021",
            ai_skills=["AutoCAD", "Hand Sketching", "Planting Plans", "Pool Surrounds", "Value Engineering", "Client Consultations"],
            notes=mark("Solid #2 designer profile. Target $68–78K. Second match for Greenscene behind Renata."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Miguel Santos",
            email="msantos.crew@gmail.com",
            phone="704-555-0116",
            current_title="Maintenance Crew Leader",
            current_company="GreenWorks Landscaping",
            location="Gastonia, NC",
            source="manual",
            ai_career_level="mid",
            ai_years_experience=8,
            ai_certifications="NC Pesticide Applicator License",
            ai_summary="Bilingual crew leader running high-density commercial maintenance routes — mowing, detail work, seasonal color rotations, and light irrigation repair. Trains new hires, keeps route efficiency top-of-branch, and has zero preventable equipment losses in four years.",
            ai_experience="GreenWorks Landscaping (2018–present) — Crew Leader: 2 trucks, 5-person crew, 40+ commercial stops/week.",
            ai_education="High school diploma",
            ai_skills=["Route Efficiency", "Commercial Maintenance", "Seasonal Color", "Equipment Care", "Bilingual EN/ES", "Training New Hires", "Irrigation Repair Basics"],
            notes=mark("Field-supervisor material. Target $24–27/hr. Bilingual — big plus for larger ops."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Evan McAllister",
            email="emcallister.turf@gmail.com",
            phone="919-555-0117",
            current_title="Sports Turf Manager",
            current_company="Wake County Athletic Complex",
            location="Cary, NC",
            source="linkedin",
            ai_career_level="senior",
            ai_years_experience=10,
            ai_certifications="CSFM (Certified Sports Field Manager), NC Pesticide Applicator License",
            ai_summary="Certified Sports Field Manager overseeing 14 natural-grass and 4 synthetic fields hosting 3,000+ events a year. MS in crop science with a research background in traffic tolerance; rebuilt two Bermuda soccer fields to college-showcase standard on a municipal budget.",
            ai_experience="Wake County Athletic Complex (2019–present) — Sports Turf Manager. NC State turfgrass research program (2016–2019) — Graduate research assistant.",
            ai_education="MS Crop Science (Turfgrass), NC State, 2018; BS Agronomy, Virginia Tech, 2016",
            ai_skills=["Sports Field Management", "Bermudagrass", "Field Renovation", "Synthetic Turf Care", "Event Scheduling", "Agronomy Research", "Municipal Budgets"],
            notes=mark("Open to premier facilities or golf-adjacent director roles. Target $85–100K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Lila Moreau",
            email="lmoreau.eco@gmail.com",
            phone="828-555-0118",
            current_title="Restoration Ecologist",
            current_company="Headwaters Ecological",
            location="Asheville, NC",
            source="resume",
            ai_career_level="mid",
            ai_years_experience=7,
            ai_certifications="NC Certified Environmental Educator, Chainsaw certification (S-212)",
            ai_summary="Ecological restoration specialist focused on native plant communities, invasive removal, and streambank stabilization. Has managed 30+ acres of active restoration sites, writes planting specs for pollinator meadows and riparian buffers, and leads volunteer field days.",
            ai_experience="Headwaters Ecological (2019–present) — Restoration Ecologist: project design + field crews. Conservation corps crew lead (2017–2019).",
            ai_education="BS Environmental Science, Warren Wilson College, 2017",
            ai_skills=["Native Plants", "Invasive Species Management", "Streambank Stabilization", "Pollinator Meadows", "Planting Specifications", "Volunteer Leadership"],
            notes=mark("Great fit for firms adding ecological/native design services. Target $60–70K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Doug Whitfield",
            email="dwhitfield.fleet@gmail.com",
            phone="704-555-0119",
            current_title="Fleet & Equipment Manager",
            current_company="Premier Landscape Group",
            location="Charlotte, NC",
            source="manual",
            ai_career_level="senior",
            ai_years_experience=16,
            ai_certifications="ASE certifications, CDL Class B",
            ai_summary="Fleet and equipment manager for a 40-truck landscape operation — preventive maintenance programs, small-engine shop supervision, purchasing, and telematics. Cut equipment downtime 35% and saved six figures annually by bringing mower and hydraulics repair in-house.",
            ai_experience="Premier Landscape Group (2013–present) — Fleet & Equipment Manager: 40 trucks, 300+ pieces of equipment, 3 mechanics. Heavy-equipment dealership service dept (2008–2013).",
            ai_education="Diesel Technology diploma, NASCAR Technical Institute, 2008",
            ai_skills=["Fleet Maintenance", "Small Engine Repair", "Hydraulics", "Telematics", "Purchasing", "Shop Management", "DOT Compliance"],
            notes=mark("Passive candidate. Would move for multi-branch equipment director role. Target $90–105K."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Sara Jenkins",
            email="sjenkins.sales@gmail.com",
            phone="704-555-0120",
            current_title="Territory Sales Representative",
            current_company="SiteOne Landscape Supply",
            location="Charlotte, NC",
            source="linkedin",
            ai_career_level="mid",
            ai_years_experience=8,
            ai_certifications="NC Certified Plant Professional",
            ai_summary="Green-industry sales rep covering contractor accounts across the Charlotte metro — nursery stock, hardscape materials, and irrigation supplies. Grew territory revenue 25% in two years and is equally comfortable talking plant material with growers and margins with branch managers.",
            ai_experience="SiteOne Landscape Supply (2020–present) — Territory Sales Rep: $4M territory. Wholesale nursery inside sales (2017–2020).",
            ai_education="BS Agricultural Business, NC A&T, 2017",
            ai_skills=["B2B Sales", "Nursery Stock Knowledge", "Contractor Relationships", "Territory Management", "Hardscape Materials", "Irrigation Supplies"],
            notes=mark("Wants wholesale-grower sales or sales-manager seat. Target $75–90K OTE."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Andre Thompson",
            email="athompson.irr@gmail.com",
            phone="704-555-0121",
            current_title="Irrigation Service Technician",
            current_company="Independent Contractor",
            location="Charlotte, NC",
            source="manual",
            ai_career_level="mid",
            ai_years_experience=6,
            ai_certifications="Certified Irrigation Technician (CIT), Backflow Prevention Tester (NC)",
            ai_summary="Certified irrigation tech and licensed backflow tester handling diagnostics, repairs, seasonal startups/winterizations, and controller upgrades. Runs his own service book of 250 residential systems but wants the stability and bigger projects of a commercial team.",
            ai_experience="Independent (2022–present) — 250-system residential service book. Irrigation contractor (2019–2022) — Service tech.",
            ai_education="High school diploma; IA certification coursework",
            ai_skills=["System Diagnostics", "Backflow Testing", "Controller Programming", "Wire Tracing", "Winterization", "Customer Service"],
            notes=mark("Wants commercial service-tech or small-team lead. Target $28–32/hr."),
        ),
        Candidate(
            tenant_id=TENANT,
            name="Beth Calloway",
            email="bcalloway.ops@gmail.com",
            phone="704-555-0122",
            current_title="Office & Operations Manager",
            current_company="Southern Charm Landscapes",
            location="Fort Mill, SC",
            source="resume",
            ai_career_level="senior",
            ai_years_experience=13,
            ai_certifications=None,
            ai_summary="Back-office backbone of a $4M residential landscape company — scheduling 8 crews, AR/AP, payroll, job costing in LMN, and customer communications. Implemented the company's first job-costing system, lifting gross margin visibility from zero to weekly reporting.",
            ai_experience="Southern Charm Landscapes (2016–present) — Office & Operations Manager. Construction office admin roles (2012–2016).",
            ai_education="AAS Business Administration, York Technical College, 2012",
            ai_skills=["Scheduling", "Job Costing", "LMN Software", "AR/AP", "Payroll", "Customer Communications", "Process Building"],
            notes=mark("Wants ops-manager role at a larger, systems-minded company. Target $70–80K."),
        ),
    ]
    for c in candidates:
        db.add(c)
    db.commit()
    print(f"  ✓ {len(candidates)} candidates")
    return {c.name: c for c in candidates}

# ── EMPLOYERS ────────────────────────────────────────────────────────────────


def seed_employers():
    print("Seeding employers...")
    employers = [
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Greenscene Landscaping",
            website_url="https://greenscene.io/",
            primary_contact_email="walt@greenscene.io",
            phone="704-555-0201",
            ai_industry="Landscaping & Outdoor Design",
            ai_company_size="35 employees, ~$5M revenue",
            ai_company_overview="Greenscene Landscaping is a design-build landscaping firm serving residential and boutique commercial clients in the Charlotte, NC area, led by owner Walt Kessler. The firm handles projects from concept design through installation and is growing its design team.",
            ai_hiring_needs='["Landscape Designer — lead the design studio, residential design-build", "Future: junior designer once the lead seat is filled"]',
            ai_talking_points='["Owner-led, design-forward culture", "Lead-designer seat with real portfolio ownership", "Project bonus structure", "Growing 25% YoY"]',
            ai_red_flags=None,
            relationship_status="Active",
            recruiter_notes=mark("Flagship client. Walt Kessler is decisive — moves fast on strong candidates. Renata Voss presented."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Queen City Turf & Lawn",
            website_url="https://queencityturf.com",
            primary_contact_email="hiring@queencityturf.com",
            phone="704-555-0202",
            ai_industry="Commercial Landscape Maintenance",
            ai_company_size="120 employees, $11M revenue",
            ai_company_overview="Commercial maintenance contractor covering HOA, retail, and office portfolios across the Charlotte metro. 20+ route crews, in-house enhancement and seasonal-color divisions, and a growing snow-response book.",
            ai_hiring_needs='["Landscape Account Manager — $2M+ book", "Maintenance Crew Leaders — bilingual preferred"]',
            ai_talking_points='["Route density means less windshield time", "Clear AM commission plan", "Promote-from-within track record"]',
            ai_red_flags='["Fast-paced spring season — 50+ hr weeks March–June"]',
            relationship_status="Active",
            recruiter_notes=mark("Two open searches. Ops director Dana Pruitt is main contact."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Carolina Pines Golf Club",
            website_url="https://carolinapinesgc.com",
            primary_contact_email="gm@carolinapinesgc.com",
            phone="910-555-0203",
            ai_industry="Golf Course Maintenance",
            ai_company_size="60 employees (25 in maintenance)",
            ai_company_overview="Private 27-hole club in the Sandhills with championship bermuda surfaces and a recently approved $2M irrigation renovation. Maintenance operation runs a $1.6M budget under a long-tenured superintendent nearing retirement.",
            ai_hiring_needs='["Assistant Superintendent — succession-track hire", "Equipment Technician (future)"]',
            ai_talking_points='["Clear succession path to superintendent within 2–3 years", "Irrigation renovation = modern system experience", "Housing stipend available"]',
            ai_red_flags=None,
            relationship_status="Active",
            recruiter_notes=mark("GM Tom Ricci wants a succession-track assistant. Dustin Pham submitted."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Bluebird Nurseries",
            website_url="https://bluebirdnurseries.com",
            primary_contact_email="office@bluebirdnurseries.com",
            phone="704-555-0204",
            ai_industry="Wholesale Nursery",
            ai_company_size="45 full-time + 30 seasonal, $8M revenue",
            ai_company_overview="Family-owned wholesale nursery in Monroe, NC growing container ornamentals, natives, and B&B trees on 120 acres. Sells to landscapers and independent garden centers across the Carolinas; second generation now leading a modernization push.",
            ai_hiring_needs='["Nursery Production Manager — modernize scheduling and IPM", "Territory Sales Rep — contractor accounts"]',
            ai_talking_points='["Family culture with real investment appetite", "New propagation houses funded for 2027", "Production manager gets true autonomy"]',
            ai_red_flags='["Compensation historically below market — owners know and are adjusting"]',
            relationship_status="Active",
            recruiter_notes=mark("Two searches. Daniela Cruz is the clear production fit; Sara Jenkins for sales."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Ironwood Tree Experts",
            website_url="https://ironwoodtree.com",
            primary_contact_email="careers@ironwoodtree.com",
            phone="704-555-0205",
            ai_industry="Tree Care / Arboriculture",
            ai_company_size="28 employees, $4M revenue",
            ai_company_overview="TCIA-accredited tree care company serving Charlotte and Lake Norman — removals, pruning, PHC, and consulting arborist work. Runs two cranes and a growing plant health care division led by a board-certified master arborist.",
            ai_hiring_needs='["ISA Certified Arborist / Climber Foreman", "Plant Health Care Technician"]',
            ai_talking_points='["TCIA accreditation and real safety culture", "Master arborist mentorship for PHC hires", "Paid ISA cert prep and exam fees"]',
            ai_red_flags=None,
            relationship_status="Active",
            recruiter_notes=mark("Tyler Brandt and Victor Alvarez both mapped here. Owner Jim Ferro values certs."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Summit Outdoor Living",
            website_url="https://summitoutdoorliving.com",
            primary_contact_email="build@summitoutdoorliving.com",
            phone="828-555-0206",
            ai_industry="Design-Build / Hardscape Construction",
            ai_company_size="40 employees, $7M revenue",
            ai_company_overview="High-end outdoor living builder in Asheville — pools, pavilions, masonry, and full landscape packages for mountain estates. Average project $180K; backlog runs 6+ months.",
            ai_hiring_needs='["Hardscape Foreman / Superintendent", "Estimator with design-build experience"]',
            ai_talking_points='["Premium projects, photo-portfolio quality", "6-month backlog = stability", "Per-project completion bonuses"]',
            ai_red_flags='["Mountain sites — travel within 45-min radius daily"]',
            relationship_status="Active",
            recruiter_notes=mark("Sam Ortiz strong for foreman; Joanne Fitch could flex to estimator."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="GreenLeaf Interior Plantscapes",
            website_url="https://greenleafinteriors.com",
            primary_contact_email="hello@greenleafinteriors.com",
            phone="704-555-0207",
            ai_industry="Interior Plantscaping",
            ai_company_size="18 employees, $2.2M revenue",
            ai_company_overview="Interiorscape firm designing and maintaining living installations for uptown Charlotte offices, hotels, and healthcare lobbies. Growing fast on moss-wall and biophilic-design demand.",
            ai_hiring_needs='["Interiorscape Operations Supervisor"]',
            ai_talking_points='["Biophilic design boom — 40% growth", "Weekday daytime routes, no weekend work", "Design input welcomed from field staff"]',
            ai_red_flags=None,
            relationship_status="Prospect",
            recruiter_notes=mark("First search with us. Carmen Delgado is the obvious match."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Piedmont Sod Farms",
            website_url="https://piedmontsod.com",
            primary_contact_email="jobs@piedmontsod.com",
            phone="704-555-0208",
            ai_industry="Sod Production / Agriculture",
            ai_company_size="35 employees, 900 production acres",
            ai_company_overview="Large sod producer supplying TifTuf bermuda, zoysia, and fescue to contractors, golf courses, and big-box retail across the Carolinas. Expanding acreage and adding a second harvest line in 2027.",
            ai_hiring_needs='["Farm Operations Manager — run the expanded footprint"]',
            ai_talking_points='["Expansion-funded role, not a backfill", "Modern harvester fleet on order", "Profit-share for ops leadership"]',
            ai_red_flags='["Harvest season starts 4:30 AM"]',
            relationship_status="Active",
            recruiter_notes=mark("Bobby Lane mapped — passive but the profit-share may move him."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="RainWise Irrigation Systems",
            website_url="https://rainwiseirrigation.com",
            primary_contact_email="office@rainwiseirrigation.com",
            phone="704-555-0209",
            ai_industry="Irrigation Design & Installation",
            ai_company_size="26 employees, $3.8M revenue",
            ai_company_overview="Commercial and estate irrigation contractor — design, install, and service — with a growing water-management consulting practice. Hunter and Rain Bird preferred contractor; strong two-wire and smart-controller expertise.",
            ai_hiring_needs='["Irrigation Designer — lead the design desk", "Irrigation Service Technician — commercial routes"]',
            ai_talking_points='["Design-lead seat with consulting upside", "Certification costs fully covered", "Year-round work via service contracts"]',
            ai_red_flags=None,
            relationship_status="Active",
            recruiter_notes=mark("Priya Natarajan for designer; Andre Thompson for service tech."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Magnolia Garden Center",
            website_url="https://magnoliagardencenter.com",
            primary_contact_email="owner@magnoliagardencenter.com",
            phone="704-555-0210",
            ai_industry="Garden Center Retail",
            ai_company_size="22 full-time + seasonal, $4.5M revenue",
            ai_company_overview="Beloved independent garden center in Matthews, NC — full nursery yard, greenhouse, gift shop, and landscape-design counter. Owner is stepping back and wants a store manager to run daily operations.",
            ai_hiring_needs='["Store Manager — full P&L for daily operations"]',
            ai_talking_points='["Owner transition = real authority", "Loyal customer base, 4.9-star reviews", "Bonus tied to store performance"]',
            ai_red_flags='["Seven-day operation in spring — manager works most Saturdays"]',
            relationship_status="Active",
            recruiter_notes=mark("Kelly Runyon is a strong culture fit — set up intro."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="Fairway Ridge Country Club",
            website_url="https://fairwayridgecc.com",
            primary_contact_email="search@fairwayridgecc.com",
            phone="336-555-0211",
            ai_industry="Golf Course Maintenance",
            ai_company_size="80 employees (30 in maintenance)",
            ai_company_overview="Established private club in Greensboro whose longtime superintendent retires this fall. Bentgrass greens, $1.8M maintenance budget, and a membership that expects tournament conditions. Board has approved a competitive package to land a proven superintendent.",
            ai_hiring_needs='["Golf Course Superintendent — retirement replacement"]',
            ai_talking_points='["$1.8M budget, supportive green committee", "Comp to $135K + benefits + dues", "Capital plan approved for bunker renovation"]',
            ai_red_flags='["High member visibility — communication skills essential"]',
            relationship_status="Active",
            recruiter_notes=mark("Marcus Webb is the target. Board interviews late this month."),
        ),
        EmployerProfile(
            tenant_id=TENANT,
            company_name="EverGreen Commercial Grounds",
            website_url="https://evergreengrounds.com",
            primary_contact_email="talent@evergreengrounds.com",
            phone="919-555-0212",
            ai_industry="Commercial Landscape Maintenance",
            ai_company_size="200 employees, $18M revenue",
            ai_company_overview="Triangle-based commercial grounds company serving corporate campuses, healthcare systems, and municipalities from Raleigh to Durham. Private-equity backed since 2025 and acquiring smaller operators; needs leadership to integrate them.",
            ai_hiring_needs='["Branch Manager — Raleigh flagship branch", "Sports Turf Manager — new athletic-fields division"]',
            ai_talking_points='["PE backing = growth and equity potential for leaders", "New division head roles, not inherited messes", "Modern fleet and telematics"]',
            ai_red_flags='["PE pace — aggressive targets"]',
            relationship_status="Active",
            recruiter_notes=mark("Greg Holloway for Branch Manager (confidential). Evan McAllister for sports turf."),
        ),
    ]
    for e in employers:
        db.add(e)
    db.commit()
    print(f"  ✓ {len(employers)} employers")
    return {e.company_name: e for e in employers}


# ── JOB ORDERS ───────────────────────────────────────────────────────────────


def seed_job_orders(employers):
    print("Seeding job orders...")
    E = employers
    jobs = [
        # Flagship — tuned as Renata's #1 match
        dict(employer="Greenscene Landscaping", title="Landscape Designer", location="Charlotte, NC",
             salary_min=82000, salary_max=100000,
             requirements="Greenscene Landscaping is seeking an experienced landscape designer to lead residential and boutique commercial design-build projects from concept through construction documents. 5+ years of design-build experience, expert AutoCAD and SketchUp, strong Southeast planting-design knowledge (zones 7b–8a), grading and drainage fundamentals, and polished client presentation skills. You will own the design studio, present to clients, and partner with install crews through construction. APLD certification a plus. Project bonus structure.",
             notes="Flagship search. Walt Kessler wants a true lead designer. Renata Voss is the target profile."),
        dict(employer="Fairway Ridge Country Club", title="Golf Course Superintendent", location="Greensboro, NC",
             salary_min=115000, salary_max=135000,
             requirements="Private club seeks a proven superintendent for bentgrass greens and tournament-standard conditioning. GCSAA Class A preferred, 10+ years including superintendent or senior assistant experience, budget ownership ($1.8M), crew leadership of 25+, and strong member communication. Bunker renovation project leadership in year one.",
             notes="Retirement replacement. Marcus Webb submitted — board round scheduled."),
        dict(employer="Carolina Pines Golf Club", title="Assistant Golf Course Superintendent", location="Pinehurst, NC",
             salary_min=72000, salary_max=85000,
             requirements="Succession-track assistant superintendent for a 27-hole private Sandhills club. GCSAA Class C+, NC pesticide license, irrigation troubleshooting (renovation to a modern system underway), chemical application programs, and crew supervision. Clear path to superintendent in 2–3 years. Housing stipend available.",
             notes="Succession hire. Dustin Pham is the front-runner."),
        dict(employer="Bluebird Nurseries", title="Nursery Production Manager", location="Monroe, NC",
             salary_min=80000, salary_max=95000,
             requirements="Lead container production on a 120-acre wholesale nursery: propagation through finished goods, IPM program ownership, production scheduling, inventory forecasting, and a 25+ seasonal team. Horticulture degree preferred, NC Certified Plant Professional a plus, bilingual EN/ES strongly preferred.",
             notes="Modernization mandate. Daniela Cruz is the clear match."),
        dict(employer="Bluebird Nurseries", title="Territory Sales Representative", location="Charlotte metro, NC",
             salary_min=65000, salary_max=90000,
             requirements="Grow contractor and independent-garden-center accounts across the Carolinas for a wholesale grower. Deep plant knowledge, existing contractor relationships, CRM discipline, and comfort with a base + commission plan (OTE listed). Green-goods buying or distributor sales background ideal.",
             notes="Sara Jenkins mapped — her SiteOne relationships transfer directly."),
        dict(employer="Ironwood Tree Experts", title="Climber Foreman (ISA Certified Arborist)", location="Charlotte, NC",
             salary_min=62000, salary_max=75000,
             requirements="Lead a removal and pruning crew for a TCIA-accredited company. ISA Certified Arborist required, technical removal and rigging expertise, crane experience preferred, ANSI A300 fluency, EHAP, and a clean driving record. Estimating exposure a plus — foremen quote small jobs on site.",
             notes="Tyler Brandt submitted. Owner values his crane background."),
        dict(employer="Ironwood Tree Experts", title="Plant Health Care Technician", location="Charlotte, NC",
             salary_min=52000, salary_max=60000,
             requirements="Run tree and shrub PHC routes — deep-root fertilization, insect and disease treatments, soil care. NC pesticide license required, field-diagnosis skills, and interest in ISA certification (prep and exam paid). Master-arborist mentorship provided.",
             notes="Victor Alvarez is a strong match — mentorship is his ask."),
        dict(employer="Summit Outdoor Living", title="Hardscape Superintendent", location="Asheville, NC",
             salary_min=75000, salary_max=88000,
             requirements="Run high-end outdoor living builds — paver systems, SRW and natural stone walls, outdoor kitchens, pool surrounds. ICPI and NCMA certifications preferred, plan-reading fluency, equipment operation, and multi-crew management on projects to $250K+. Per-project completion bonuses.",
             notes="Sam Ortiz submitted — portfolio review went very well."),
        dict(employer="Summit Outdoor Living", title="Design-Build Estimator", location="Asheville, NC",
             salary_min=70000, salary_max=85000,
             requirements="Estimate pools, hardscape, and landscape packages for mountain estate projects. Takeoff proficiency, unit-cost library management, subcontractor scoping, and design-team collaboration. Landscape or outdoor-construction estimating background required.",
             notes="Open. Joanne Fitch could flex here if AM search stalls."),
        dict(employer="Queen City Turf & Lawn", title="Landscape Account Manager", location="Charlotte, NC",
             salary_min=75000, salary_max=90000,
             requirements="Own a $2M+ commercial maintenance book — HOA and office portfolios. Renewal management, enhancement sales, site walks, board presentations, and snow-contract administration. NALP certification a plus. Commission on enhancements and renewals.",
             notes="Joanne Fitch is the target — her renewal rate is exactly what Dana wants."),
        dict(employer="Queen City Turf & Lawn", title="Maintenance Crew Leader", location="Charlotte, NC",
             salary_min=48000, salary_max=56000,
             requirements="Lead a 5-person commercial maintenance crew — route efficiency, quality control, equipment care, and new-hire training. 3+ years maintenance experience, bilingual EN/ES strongly preferred, NC pesticide license a plus. Clear path to field supervisor.",
             notes="Miguel Santos submitted."),
        dict(employer="EverGreen Commercial Grounds", title="Branch Manager", location="Raleigh, NC",
             salary_min=115000, salary_max=140000,
             requirements="P&L leadership of the $7M flagship Raleigh branch — 60 field staff, commercial maintenance and enhancements. 10+ years including branch or ops leadership, estimating depth, client-retention track record, and comfort with PE-pace growth targets. Equity participation for the right leader.",
             notes="CONFIDENTIAL — Greg Holloway. Do not post publicly."),
        dict(employer="EverGreen Commercial Grounds", title="Sports Turf Manager", location="Raleigh, NC",
             salary_min=85000, salary_max=100000,
             requirements="Build and lead a new athletic-fields division serving schools, municipalities, and training facilities. CSFM strongly preferred, natural and synthetic field expertise, renovation project leadership, and agronomic program design. Division-head role reporting to the COO.",
             notes="Evan McAllister mapped — new-division angle fits his ambitions."),
        dict(employer="RainWise Irrigation Systems", title="Irrigation Designer", location="Charlotte, NC",
             salary_min=88000, salary_max=105000,
             requirements="Lead the design desk for commercial and estate systems — hydraulic calculations, two-wire design, smart-controller specification, and water-budget compliance. CID strongly preferred, AutoCAD proficiency, and mentoring of field techs. Consulting-practice upside.",
             notes="Priya Natarajan submitted — design-lead seat is exactly her ask."),
        dict(employer="RainWise Irrigation Systems", title="Irrigation Service Technician", location="Charlotte, NC",
             salary_min=56000, salary_max=66000,
             requirements="Commercial service routes — diagnostics, repairs, seasonal startups and winterizations, controller upgrades. CIT preferred, NC backflow tester license a big plus, wire-tracing and two-wire troubleshooting skills. Year-round work, take-home van.",
             notes="Andre Thompson matched — backflow license checks the hardest box."),
        dict(employer="Magnolia Garden Center", title="Store Manager", location="Matthews, NC",
             salary_min=62000, salary_max=72000,
             requirements="Run daily operations of a beloved independent garden center — merchandising, green-goods buying, seasonal staffing to 40, event programming, and full store P&L. Plant knowledge required (NC CPP a plus), independent-retail or garden-center leadership background preferred. Performance bonus.",
             notes="Kelly Runyon intro scheduled with the owner."),
        dict(employer="GreenLeaf Interior Plantscapes", title="Interiorscape Operations Supervisor", location="Charlotte, NC",
             salary_min=62000, salary_max=72000,
             requirements="Supervise maintenance routes across 80+ corporate and hospitality accounts — tech scheduling, quality audits, install support for moss walls and biophilic features, and account-refresh upsells. Interior tropical plant expertise required; supervisory experience preferred.",
             notes="Carmen Delgado is the obvious match — first search for this client, make it count."),
        dict(employer="Piedmont Sod Farms", title="Farm Operations Manager", location="Mount Holly, NC",
             salary_min=95000, salary_max=115000,
             requirements="Run 900 production acres — harvest scheduling, logistics for big-roll and slab delivery, irrigation-pivot management, equipment fleet, and a 15-person crew. Agronomy or agribusiness background, pesticide license, CDL a plus. Profit-share on farm performance. Expansion-funded role.",
             notes="Bobby Lane mapped — profit-share is the hook for a passive candidate."),
    ]

    created = []
    for spec in jobs:
        emp = E[spec.pop("employer")]
        job = JobOrder(
            tenant_id=TENANT,
            status="open",
            employer_profile_id=emp.id,
            title=spec["title"],
            location=spec["location"],
            salary_min=spec["salary_min"],
            salary_max=spec["salary_max"],
            requirements=spec["requirements"],
            notes=mark(spec["notes"]),
        )
        db.add(job)
        created.append(job)
    db.commit()
    print(f"  ✓ {len(created)} job orders (all linked to employer profiles)")
    return created

# ── BOOKINGS ─────────────────────────────────────────────────────────────────


def seed_bookings(candidates, employers):
    print("Seeding bookings...")
    C, E = candidates, employers

    def emp_id(name):
        return E[name].id

    def cand_id(name):
        return C[name].id

    bookings = [
        # ── Flagship pair: Walt Kessler (employer) + Renata Voss (candidate) ──
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Walt Kessler", employer_email="walt@greenscene.io",
            company_name="Greenscene Landscaping", website_url="https://greenscene.io/",
            employer_profile_id=emp_id("Greenscene Landscaping"),
            date=d(15), time_slot="10:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011001",
            meeting_summary="Intake call with Walt Kessler, owner of Greenscene Landscaping (Charlotte design-build, ~$5M, growing 25% YoY). Opening a lead Landscape Designer seat — wants someone to own the design studio end to end: concepts, construction documents, client presentations, and crew handoff. 5+ years design-build required, AutoCAD/SketchUp expert, Southeast planting knowledge. Budget $82–100K plus project bonus. Walt is decisive and will move fast on the right person.",
            meeting_next_steps="• Present Renata Voss — profile is a near-perfect match\n• Hannah Brooks as backup profile\n• Target shortlist to Walt within one week",
            meeting_keywords="landscape designer, design-build, AutoCAD, SketchUp, planting design, Charlotte, lead designer",
            meeting_transcript=mark(
                "Recruiter: Walt, tell me about the seat. "
                "Walt: I need a real lead designer. I'm still drawing half our projects myself and I'm the owner — that math doesn't work at twenty-five percent growth. "
                "Recruiter: What does great look like? "
                "Walt: Someone who can take a first client meeting, come back with a concept that makes them say wow, produce clean construction documents, and hand off to my install crews without babysitting. Design-build experience is non-negotiable. "
                "Recruiter: Budget? "
                "Walt: Eighty-two to a hundred, plus a project bonus. If they're great, I'll stretch."
            ),
            call_outcome="follow_up", created_at=dt(15, 9),
            call_notes=mark("Flagship search opened. Renata is the target."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Renata Voss", employer_email="renata.voss@gmail.com",
            candidate_id=cand_id("Renata Voss"),
            date=d(12), time_slot="2:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011002",
            meeting_summary="Screen with Renata Voss, Landscape Designer at Terra Firma Design Group (Charlotte). 9 years of residential design-build — 30+ projects/yr at ~$85K average contract, owns concept through construction documents and client presentations. APLD certified, NC State BLA. Wants a lead-designer seat at a growing firm where she shapes the portfolio and mentors a junior. Target $85–100K plus project bonus, Charlotte only. Presented the Greenscene opportunity — she lit up.",
            meeting_next_steps="• Submit Renata to Greenscene immediately\n• Prep her portfolio deck for Walt\n• Schedule Walt–Renata intro this week",
            meeting_keywords="landscape designer, design-build, APLD, AutoCAD, SketchUp, Charlotte, lead designer, Greenscene",
            call_outcome="follow_up", created_at=dt(12, 13),
            call_notes=mark("Star candidate. Greenscene match confirmed on the call."),
        ),
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Walt Kessler", employer_email="walt@greenscene.io",
            company_name="Greenscene Landscaping",
            employer_profile_id=emp_id("Greenscene Landscaping"),
            date=today + timedelta(days=3), time_slot="11:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011003",
            notes="Walt + Renata intro call — recruiter facilitating. Portfolio deck sent ahead.",
            created_at=dt(2, 16),
            call_notes=mark("Upcoming: Walt–Renata introduction."),
        ),

        # ── Golf searches ──
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Board Search Committee", employer_email="search@fairwayridgecc.com",
            company_name="Fairway Ridge Country Club",
            employer_profile_id=emp_id("Fairway Ridge Country Club"),
            date=d(28), time_slot="3:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011004",
            meeting_summary="Kickoff with Fairway Ridge CC search committee. Longtime superintendent retires in the fall — need a proven superintendent for bentgrass greens and a demanding membership. $1.8M budget, crew of 30, bunker renovation in year one. Comp approved to $135K plus benefits and dues. Committee wants strong member-communication skills as much as agronomy.",
            meeting_next_steps="• Present Marcus Webb as lead candidate\n• Two backup profiles from GCSAA network",
            meeting_keywords="golf course superintendent, bentgrass, GCSAA, Greensboro, retirement replacement",
            call_outcome="follow_up", created_at=dt(28, 14),
            call_notes=mark("Well-run committee. Marcus Webb is the play."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Marcus Webb", employer_email="mwebb.turf@gmail.com",
            candidate_id=cand_id("Marcus Webb"),
            date=d(25), time_slot="4:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011005",
            meeting_summary="Screen with Marcus Webb, Superintendent at Longleaf Pines GC (Pinehurst). Class A, 15 years, led an ultradwarf greens conversion, runs a crew of 22 and a $1.4M budget. Interested in Fairway Ridge — bigger budget, bentgrass challenge, and the bunker renovation appeals to him. Target $110–130K; housing consideration would help but isn't a dealbreaker.",
            meeting_next_steps="• Submit to Fairway Ridge committee\n• Coach him on member-communication examples for the board round",
            meeting_keywords="superintendent, Class A, bermudagrass, bentgrass, renovation, Fairway Ridge",
            call_outcome="follow_up", created_at=dt(25, 15),
            call_notes=mark("Submitted to Fairway Ridge. Board round pending."),
        ),
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Tom Ricci", employer_email="gm@carolinapinesgc.com",
            company_name="Carolina Pines Golf Club",
            employer_profile_id=emp_id("Carolina Pines Golf Club"),
            date=d(22), time_slot="9:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011006",
            meeting_summary="Call with GM Tom Ricci at Carolina Pines GC (Pinehurst, 27 holes). Superintendent is 3 years from retirement — wants a succession-track assistant now. $2M irrigation renovation approved, so modern-system experience will be built on the job. Budget $72–85K with housing stipend. Values hunger over pedigree.",
            meeting_next_steps="• Present Dustin Pham — succession angle fits his first-seat ambition",
            meeting_keywords="assistant superintendent, succession, Pinehurst, irrigation renovation",
            call_outcome="follow_up", created_at=dt(22, 8),
            call_notes=mark("Succession-track search. Dustin Pham front-runner."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Dustin Pham", employer_email="dpham.turf@gmail.com",
            candidate_id=cand_id("Dustin Pham"),
            date=d(20), time_slot="1:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011007",
            meeting_summary="Screen with Dustin Pham, Assistant Superintendent at Oak Hollow GC. 6 years, Class C, pesticide licensed, strong irrigation troubleshooting on aging equipment. Wants his first superintendent path and will relocate within NC. The Carolina Pines succession story is exactly what he's looking for. Target $70–85K.",
            meeting_next_steps="• Submit to Carolina Pines\n• On-course working interview with the superintendent",
            meeting_keywords="assistant superintendent, succession, irrigation, Pinehurst",
            call_outcome="follow_up", created_at=dt(20, 12),
            call_notes=mark("Submitted to Carolina Pines."),
        ),

        # ── Nursery / garden center ──
        Booking(
            booking_type="inbound", tenant_id=TENANT,
            employer_name="Grace Whitley", employer_email="office@bluebirdnurseries.com",
            company_name="Bluebird Nurseries", website_url="https://bluebirdnurseries.com",
            employer_profile_id=emp_id("Bluebird Nurseries"),
            date=d(35), time_slot="10:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011008",
            meeting_summary="Inbound from Bluebird Nurseries (Monroe, 120-acre wholesale grower, family-owned). Second-generation owner Grace Whitley is modernizing — needs a Production Manager to overhaul scheduling and IPM, plus a Territory Sales Rep for contractor accounts. Acknowledged past below-market comp and has adjusted budgets: $80–95K production, $65–90K OTE sales.",
            meeting_next_steps="• Open two searches\n• Daniela Cruz for production; Sara Jenkins for sales",
            meeting_keywords="wholesale nursery, production manager, sales rep, IPM, Monroe",
            call_outcome="follow_up", created_at=dt(35, 9),
            call_notes=mark("Two searches opened. Family-owned, real investment appetite."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Daniela Cruz", employer_email="dcruz.hort@gmail.com",
            candidate_id=cand_id("Daniela Cruz"),
            date=d(32), time_slot="11:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011009",
            meeting_summary="Screen with Daniela Cruz, Production Manager at Yadkin Valley Growers. 11 years, NC CPP, cut crop loss 30% with a revamped IPM program, manages 25 seasonal staff, bilingual. Wants head-grower autonomy — Bluebird's modernization mandate is a fit. Target $80–95K, which Bluebird's new budget covers.",
            meeting_next_steps="• Submit to Bluebird\n• Farm-walk interview with Grace Whitley",
            meeting_keywords="nursery production, IPM, container ornamentals, bilingual, Bluebird",
            call_outcome="follow_up", created_at=dt(32, 10),
            call_notes=mark("Submitted to Bluebird. Strong mutual fit."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Sara Jenkins", employer_email="sjenkins.sales@gmail.com",
            candidate_id=cand_id("Sara Jenkins"),
            date=d(30), time_slot="3:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011010",
            meeting_summary="Screen with Sara Jenkins, Territory Sales Rep at SiteOne. 8 years green-industry sales, $4M territory grown 25% in two years, contractor relationships across the Charlotte metro. Wants a grower-side seat where plant knowledge matters more. Bluebird OTE works if base is $60K+.",
            meeting_next_steps="• Submit to Bluebird sales search\n• Verify base/commission split with Grace",
            meeting_keywords="territory sales, wholesale nursery, contractor accounts, SiteOne",
            call_outcome="follow_up", created_at=dt(30, 14),
            call_notes=mark("Submitted to Bluebird sales search."),
        ),
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Pam Ostrander", employer_email="owner@magnoliagardencenter.com",
            company_name="Magnolia Garden Center",
            employer_profile_id=emp_id("Magnolia Garden Center"),
            date=d(18), time_slot="2:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011011",
            meeting_summary="Call with Pam Ostrander, owner of Magnolia Garden Center (Matthews, $4.5M independent). Stepping back after 30 years — wants a Store Manager with real authority over daily ops, buying, and staffing. Plant knowledge non-negotiable; culture fit with a loyal customer base matters most. Budget $62–72K plus performance bonus.",
            meeting_next_steps="• Introduce Kelly Runyon — culture fit looks ideal",
            meeting_keywords="garden center, store manager, retail, Matthews, owner transition",
            call_outcome="follow_up", created_at=dt(18, 13),
            call_notes=mark("Kelly Runyon intro arranged."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Kelly Runyon", employer_email="krunyon.gc@gmail.com",
            candidate_id=cand_id("Kelly Runyon"),
            date=d(16), time_slot="10:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011012",
            meeting_summary="Screen with Kelly Runyon, Assistant Store Manager at Pike Nurseries. 6 years, NC CPP, runs a $3M store's plant department with the chain's lowest live-goods shrink. Wants an independent where she can own the whole store. Magnolia's owner-transition story excites her; Saturday schedule is fine. Target $60–70K plus bonus — aligned.",
            meeting_next_steps="• In-store working session with Pam next week",
            meeting_keywords="garden center, retail manager, green goods, Magnolia",
            call_outcome="follow_up", created_at=dt(16, 9),
            call_notes=mark("Intro with Pam scheduled."),
        ),

        # ── Tree care ──
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Jim Ferro", employer_email="careers@ironwoodtree.com",
            company_name="Ironwood Tree Experts",
            employer_profile_id=emp_id("Ironwood Tree Experts"),
            date=d(40), time_slot="8:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011013",
            meeting_summary="Intake with Jim Ferro, owner of Ironwood Tree Experts (TCIA-accredited, Charlotte/Lake Norman). Two needs: a Climber Foreman who's an ISA Certified Arborist with crane experience, and a PHC Technician to grow under his board-certified master arborist. Pays for cert prep and exams. Foreman $62–75K; PHC $52–60K.",
            meeting_next_steps="• Tyler Brandt for foreman\n• Victor Alvarez for PHC — mentorship is his exact ask",
            meeting_keywords="arborist, climber foreman, PHC, TCIA, crane, ISA",
            call_outcome="follow_up", created_at=dt(40, 7),
            call_notes=mark("Two searches. Cert-friendly employer."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Tyler Brandt", employer_email="tbrandt.trees@gmail.com",
            candidate_id=cand_id("Tyler Brandt"),
            date=d(38), time_slot="5:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011014",
            meeting_summary="Screen with Tyler Brandt, ISA Certified Arborist and crew leader at Blue Ridge Tree Service. 7 years, technical removals, crane work, runs a 3-person crew and quotes small jobs. Wants a foreman/ops path at a TCIA-accredited shop. Ironwood checks every box. Target $30–35/hr — within Jim's range.",
            meeting_next_steps="• Submit to Ironwood foreman role\n• Climbing evaluation on site",
            meeting_keywords="ISA arborist, climber, crane, foreman, Ironwood",
            call_outcome="follow_up", created_at=dt(38, 16),
            call_notes=mark("Submitted to Ironwood."),
        ),
        Booking(
            booking_type="inbound_candidate", tenant_id=TENANT,
            employer_name="Victor Alvarez", employer_email="valvarez.phc@gmail.com",
            candidate_id=cand_id("Victor Alvarez"),
            date=d(36), time_slot="12:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011015",
            meeting_summary="Inbound candidate call with Victor Alvarez, PHC tech at Carolina Lawn Doctors. Licensed applicator (L, N, D), 400-account route, studying for his ISA exam. Wants tree PHC with real arborist mentorship — Ironwood's master-arborist program is exactly that. Target $25–28/hr.",
            meeting_next_steps="• Submit to Ironwood PHC role",
            meeting_keywords="PHC, pesticide license, ISA candidate, mentorship",
            call_outcome="follow_up", created_at=dt(36, 11),
            call_notes=mark("Submitted to Ironwood PHC."),
        ),

        # ── Commercial maintenance & leadership ──
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Dana Pruitt", employer_email="hiring@queencityturf.com",
            company_name="Queen City Turf & Lawn",
            employer_profile_id=emp_id("Queen City Turf & Lawn"),
            date=d(45), time_slot="1:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011016",
            meeting_summary="Intake with Dana Pruitt, Ops Director at Queen City Turf & Lawn ($11M commercial maintenance). Needs an Account Manager for a $2M+ HOA/office book (renewals, enhancement sales, board presentations) and bilingual Crew Leaders for spring routes. AM budget $75–90K plus commission; crew leaders $48–56K.",
            meeting_next_steps="• Joanne Fitch for AM — her 95% renewal rate is the headline\n• Miguel Santos for crew leader",
            meeting_keywords="account manager, commercial maintenance, HOA, crew leader, bilingual",
            call_outcome="follow_up", created_at=dt(45, 12),
            call_notes=mark("Two searches with Dana."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Joanne Fitch", employer_email="jfitch.landscape@gmail.com",
            candidate_id=cand_id("Joanne Fitch"),
            date=d(43), time_slot="9:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011017",
            meeting_summary="Screen with Joanne Fitch, Account Manager at Metro Grounds. $2.8M book, 95% renewal rate, $600K/yr enhancement sales, comfortable in HOA board meetings. Open to Queen City if commission plan is real. Target $85–95K plus commission.",
            meeting_next_steps="• Submit to Queen City AM role\n• Get commission-plan detail from Dana before her interview",
            meeting_keywords="account manager, renewals, enhancements, HOA, Queen City",
            call_outcome="follow_up", created_at=dt(43, 8),
            call_notes=mark("Submitted to Queen City."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Miguel Santos", employer_email="msantos.crew@gmail.com",
            candidate_id=cand_id("Miguel Santos"),
            date=d(41), time_slot="6:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011018",
            meeting_summary="Evening screen with Miguel Santos, crew leader at GreenWorks. 8 years, bilingual, top route efficiency in his branch, zero preventable equipment losses in four years. Wants a bigger operation with a field-supervisor path. Queen City fits. Target $24–27/hr.",
            meeting_next_steps="• Submit to Queen City crew-leader opening",
            meeting_keywords="crew leader, bilingual, route efficiency, Queen City",
            call_outcome="follow_up", created_at=dt(41, 17),
            call_notes=mark("Submitted to Queen City."),
        ),
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Rachel Yoon", employer_email="talent@evergreengrounds.com",
            company_name="EverGreen Commercial Grounds",
            employer_profile_id=emp_id("EverGreen Commercial Grounds"),
            date=d(50), time_slot="11:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011019",
            meeting_summary="Intake with Rachel Yoon, Talent Director at EverGreen ($18M, PE-backed, Triangle). Two leadership searches: Branch Manager for the $7M Raleigh flagship ($115–140K plus equity potential) and a Sports Turf Manager to launch an athletic-fields division ($85–100K, division-head role). PE pace — they want shortlists in two weeks.",
            meeting_next_steps="• Greg Holloway for Branch Manager (CONFIDENTIAL)\n• Evan McAllister for Sports Turf division head",
            meeting_keywords="branch manager, sports turf, PE-backed, Raleigh, division head",
            call_outcome="follow_up", created_at=dt(50, 10),
            call_notes=mark("Two leadership searches. Fast timeline."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Greg Holloway", employer_email="gholloway.grounds@gmail.com",
            candidate_id=cand_id("Greg Holloway"),
            date=d(47), time_slot="7:00 AM", status="confirmed",
            meeting_url="https://zoom.us/j/880011020",
            meeting_summary="Confidential early-morning call with Greg Holloway, Branch Manager at TruNorth ($6.5M branch, 55 FTE, 92% retention, grew revenue 40% in three years). Quietly exploring — wants regional/GM scope and equity. EverGreen's PE story and equity potential land well. Target $120–140K plus bonus. CONFIDENTIAL — current employer must not hear.",
            meeting_next_steps="• Submit to EverGreen under confidential cover\n• No reference calls until offer stage",
            meeting_keywords="branch manager, confidential, P&L, equity, EverGreen",
            call_outcome="follow_up", created_at=dt(47, 6),
            call_notes=mark("CONFIDENTIAL search. Handle references carefully."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Evan McAllister", employer_email="emcallister.turf@gmail.com",
            candidate_id=cand_id("Evan McAllister"),
            date=d(46), time_slot="2:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011021",
            meeting_summary="Screen with Evan McAllister, CSFM, Sports Turf Manager at Wake County Athletic Complex. MS in crop science, 18 fields, 3,000+ events/yr, rebuilt two Bermuda soccer fields to showcase standard on municipal money. The build-a-division angle at EverGreen fits his ambition perfectly. Target $85–100K.",
            meeting_next_steps="• Submit to EverGreen Sports Turf division-head role",
            meeting_keywords="CSFM, sports turf, division head, field renovation, EverGreen",
            call_outcome="follow_up", created_at=dt(46, 13),
            call_notes=mark("Submitted to EverGreen."),
        ),

        # ── Irrigation, hardscape, interiorscape, sod ──
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Curt Baylor", employer_email="office@rainwiseirrigation.com",
            company_name="RainWise Irrigation Systems",
            employer_profile_id=emp_id("RainWise Irrigation Systems"),
            date=d(33), time_slot="4:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011022",
            meeting_summary="Intake with Curt Baylor, GM of RainWise Irrigation ($3.8M, commercial + estate). Needs an Irrigation Designer to lead the design desk (hydraulics, two-wire, smart controllers, water budgets — CID preferred, $88–105K) and a commercial Service Tech ($56–66K, take-home van). Consulting practice gives the designer seat real upside.",
            meeting_next_steps="• Priya Natarajan for designer\n• Andre Thompson for service tech — his backflow license is the differentiator",
            meeting_keywords="irrigation designer, CID, two-wire, service tech, backflow",
            call_outcome="follow_up", created_at=dt(33, 15),
            call_notes=mark("Two irrigation searches."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Priya Natarajan", employer_email="priya.irrigation@gmail.com",
            candidate_id=cand_id("Priya Natarajan"),
            date=d(31), time_slot="12:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011023",
            meeting_summary="Screen with Priya Natarajan, CID, Irrigation Designer at AquaLogic. 10 years, 200+ systems designed including athletic fields and two-wire commercial, civil-engineering degree, mentors field techs. Wants a design-lead seat — RainWise's desk plus consulting upside is her exact ask. Target $90–105K.",
            meeting_next_steps="• Submit to RainWise designer role",
            meeting_keywords="CID, hydraulic design, two-wire, design lead, RainWise",
            call_outcome="follow_up", created_at=dt(31, 11),
            call_notes=mark("Submitted to RainWise."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Sam Ortiz", employer_email="sortiz.hardscape@gmail.com",
            candidate_id=cand_id("Sam Ortiz"),
            date=d(26), time_slot="5:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011024",
            meeting_summary="Screen with Sam Ortiz, Hardscape Foreman at StoneBridge (Rock Hill). 9 years, ICPI + NCMA certified, zero-callback reputation, runs 2 crews on projects to $250K. Summit's estate-level work and completion bonuses appeal; open to Asheville relocation. Target $75–85K.",
            meeting_next_steps="• Submit to Summit superintendent role\n• Portfolio review with Summit's build director",
            meeting_keywords="hardscape, ICPI, NCMA, foreman, Summit, Asheville",
            call_outcome="follow_up", created_at=dt(26, 16),
            call_notes=mark("Submitted to Summit. Portfolio review done — went very well."),
        ),
        Booking(
            booking_type="inbound", tenant_id=TENANT,
            employer_name="Nadia Osei", employer_email="hello@greenleafinteriors.com",
            company_name="GreenLeaf Interior Plantscapes", website_url="https://greenleafinteriors.com",
            employer_profile_id=emp_id("GreenLeaf Interior Plantscapes"),
            date=d(14), time_slot="1:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011025",
            meeting_summary="Inbound from GreenLeaf Interior Plantscapes — first contact. Founder Nadia Osei is riding 40% growth in biophilic design and needs an Operations Supervisor for 80+ accounts: tech scheduling, quality audits, moss-wall install support. Budget $62–72K. New client — make this search a showcase.",
            meeting_next_steps="• Open search\n• Carmen Delgado is the obvious first submission",
            meeting_keywords="interiorscape, biophilic, operations supervisor, moss walls",
            call_outcome="follow_up", created_at=dt(14, 12),
            call_notes=mark("New client — first search. Deliver fast."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Carmen Delgado", employer_email="cdelgado.plants@gmail.com",
            candidate_id=cand_id("Carmen Delgado"),
            date=d(11), time_slot="3:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011026",
            meeting_summary="Screen with Carmen Delgado, Interiorscape Supervisor at Verdant Interiors. 8 years, 60 accounts, 6 techs, runs the holiday-décor program and drives account upsells. Wants an ops-manager role where she can build systems — GreenLeaf's growth stage fits. Target $65–75K; GreenLeaf tops out at $72K, workable.",
            meeting_next_steps="• Submit to GreenLeaf\n• Site visit to two flagship accounts",
            meeting_keywords="interiorscape, operations, supervisor, GreenLeaf",
            call_outcome="follow_up", created_at=dt(11, 14),
            call_notes=mark("Submitted to GreenLeaf."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Bobby Lane", employer_email="blane.sod@gmail.com",
            candidate_id=cand_id("Bobby Lane"),
            date=d(8), time_slot="7:00 PM", status="confirmed",
            meeting_url="https://zoom.us/j/880011027",
            meeting_summary="Evening call with Bobby Lane, Ops Manager at Catawba River Sod (600 acres). Passive — happy where he is — but Piedmont's expansion-funded GM-level role with profit-share got his attention. 14 years, CDL, harvest logistics and pivot-irrigation expert. Would need $95K+ base plus the profit-share to move.",
            meeting_next_steps="• Feel out Piedmont on base flexibility before formal submission",
            meeting_keywords="sod farm, operations manager, profit share, passive candidate",
            call_outcome="follow_up", created_at=dt(8, 18),
            call_notes=mark("Passive. Profit-share is the hook."),
        ),

        # ── Realism: upcoming, cancelled, no-show ──
        Booking(
            booking_type="inbound_candidate", tenant_id=TENANT,
            employer_name="Aisha Simmons", employer_email="asimmons.design@gmail.com",
            candidate_id=cand_id("Aisha Simmons"),
            date=today + timedelta(days=2), time_slot="10:00 AM", status="pending",
            notes="Inbound junior designer — freelance portfolio, UNCC BLA 2024. Could pair under whoever lands the Greenscene lead seat.",
            created_at=dt(1, 9),
            call_notes=mark("Pending intro call."),
        ),
        Booking(
            booking_type="inbound", tenant_id=TENANT,
            employer_name="Hank Dillard", employer_email="hdillard@dillardlandworks.com",
            company_name="Dillard Landworks",
            date=today + timedelta(days=6), time_slot="9:00 AM", status="pending",
            notes="New inbound — grading and land-clearing contractor asking about an estimator search. Qualify scope on the call.",
            created_at=dt(0, 8),
            call_notes=mark("New inbound. Qualify on call."),
        ),
        Booking(
            booking_type="outbound_candidate", tenant_id=TENANT,
            employer_name="Lila Moreau", employer_email="lmoreau.eco@gmail.com",
            candidate_id=cand_id("Lila Moreau"),
            date=d(6), time_slot="11:00 AM", status="confirmed",
            call_outcome="no_show",
            notes="No show — emailed to reschedule. Restoration background still interesting for firms adding native-design services.",
            created_at=dt(9, 10),
            call_notes=mark("No-show. One reschedule attempt made."),
        ),
        Booking(
            booking_type="outbound_employer", tenant_id=TENANT,
            employer_name="Marty Boggs", employer_email="marty@boggslandscape.com",
            company_name="Boggs Landscape Co",
            date=d(4), time_slot="2:00 PM", status="cancelled",
            call_outcome="not_a_fit",
            notes="Cancelled — owner decided to promote his crew lead instead of hiring externally.",
            created_at=dt(7, 13),
            call_notes=mark("Search cancelled before kickoff."),
        ),
    ]
    for b in bookings:
        db.add(b)
    db.commit()
    print(f"  ✓ {len(bookings)} bookings")


# ── MAIN ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Greenpath Recruiting demo seed (wipes DB except user id 1).")
    parser.add_argument("--wipe-only", action="store_true",
                        help="Post-demo teardown: wipe everything except user 1 and restore them to the 'ryze' tenant.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    args = parser.parse_args()

    action = "WIPE (no re-seed)" if args.wipe_only else "WIPE + SEED Greenpath demo data"
    print(f"\n⚠️  This will DELETE ALL DATA except users.id={SUPERADMIN_ID}.")
    print(f"    Action: {action}\n")
    if not args.yes:
        if input("Type 'yes' to continue: ").strip().lower() != "yes":
            print("Aborted.")
            return

    try:
        admin = wipe_all(restore_ryze_tenant=args.wipe_only)

        if args.wipe_only:
            print("✅ Teardown complete. Database is empty; you are back on the 'ryze' tenant.")
            return

        print("🌱 Seeding Greenpath Recruiting demo data...\n")
        ensure_tenant()
        stamp_admin_tenant(admin)
        candidates = seed_candidates()
        employers = seed_employers()
        seed_job_orders(employers)
        seed_bookings(candidates, employers)

        print("\n✅ Seed complete.")
        print("\nNEXT STEP (required for AI matching):")
        print("   python run_backfill.py     # generates pgvector embeddings")
        print("\nDemo login: your superadmin (user id 1) — now scoped to Green Path Recruiting.")
        print("Flagship thread: Walt Kessler / Greenscene → 'Landscape Designer' → Renata Voss.")
        print("Intelligence chat prompts that will shine:")
        print('   "Show me matches for Renata Voss"')
        print('   "What did Walt Kessler say he was looking for?"')
        print('   "Which candidates fit the Fairway Ridge superintendent search?"')
        print("   \"Summarize my open searches and who I have submitted.\"")
        print(f"\nAfter the demo: python {os.path.basename(__file__)} --wipe-only")

    finally:
        db.close()


if __name__ == "__main__":
    main()
