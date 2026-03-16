#!/usr/bin/env python3
"""
RYZE.ai Demo Seed Script
Inserts 20 candidates, 8 employers, 6 job orders, 10 bookings with meeting summaries.
Run: python seed_demo.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from app.core.database import SessionLocal
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder
from app.models.booking import Booking
from app.models.user import User
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage

db = SessionLocal()

# ── Candidates ─────────────────────────────────────────────────────────────
print("Seeding candidates...")

candidates = [
    Candidate(
        name="Jennifer Walsh",
        current_title="Senior Manager",
        current_company="Deloitte",
        location="Boston, MA",
        ai_career_level="Senior",
        ai_certifications="CPA",
        ai_years_experience="12",
        ai_summary="Big 4 audit manager at Deloitte with 12 years experience. Strong technical accounting background, experienced with SOX compliance and public company reporting. NetSuite certified. Ready to transition to industry as Controller.",
        ai_skills='["Big 4", "SOX", "NetSuite", "Public Reporting", "Audit", "GAAP"]',
    ),
    Candidate(
        name="David Kim",
        current_title="Controller",
        current_company="Apex Portfolio Co",
        location="New York, NY",
        ai_career_level="Senior",
        ai_certifications="CPA",
        ai_years_experience="10",
        ai_summary="Controller at a PE-backed portfolio company with IPO-readiness experience. Managed the full close cycle, built out the accounting team from 3 to 12, and led a successful audit for a $200M revenue business.",
        ai_skills='["PE-backed", "IPO Readiness", "Close Management", "Team Building", "NetSuite", "FP&A"]',
    ),
    Candidate(
        name="Priya Patel",
        current_title="Audit Manager",
        current_company="PwC",
        location="Boston, MA",
        ai_career_level="Senior",
        ai_certifications="CPA",
        ai_years_experience="9",
        ai_summary="PwC audit manager with deep Big 4 assurance experience. Served clients in financial services and life sciences. Strong GAAP and IFRS knowledge. Looking to move into a Director of Finance or Controller role in biotech.",
        ai_skills='["Big 4", "Assurance", "IFRS", "GAAP", "Life Sciences", "Financial Services"]',
    ),
    Candidate(
        name="Marcus Johnson",
        current_title="VP Finance",
        current_company="CloudMetrics Inc",
        location="Chicago, IL",
        ai_career_level="Executive",
        ai_certifications="CPA",
        ai_years_experience="16",
        ai_summary="VP Finance at a SaaS company with full P&L ownership. Built the FP&A function from scratch, drove ARR reporting, and partnered with the CEO on Series C fundraising. Expertise in SaaS metrics and board-level reporting.",
        ai_skills='["FP&A", "SaaS Metrics", "Board Reporting", "Series C", "ARR", "Strategic Finance"]',
    ),
    Candidate(
        name="Sarah Chen",
        current_title="Senior Accountant",
        current_company="MedBridge Health",
        location="Boston, MA",
        ai_career_level="Mid",
        ai_certifications=None,
        ai_years_experience="5",
        ai_summary="Senior accountant with strong NetSuite skills and healthcare industry background. Manages the monthly close, reconciliations, and revenue recognition. Detail-oriented, fast learner, looking to step into a manager role.",
        ai_skills='["NetSuite", "Revenue Recognition", "Close Management", "Healthcare", "Reconciliations"]',
    ),
    Candidate(
        name="Ben Neuwirth",
        current_title="Senior Accountant",
        current_company="CareFirst NFP",
        location="Boston, MA",
        ai_career_level="Mid",
        ai_certifications="CPA",
        ai_years_experience="6",
        ai_summary="CPA with healthcare and nonprofit accounting experience. Manages grant accounting, government compliance, and audit prep. Strong technical writer, excellent with stakeholder communication.",
        ai_skills='["NFP Accounting", "Grant Accounting", "Healthcare", "Audit Prep", "Government Compliance"]',
    ),
    Candidate(
        name="Cole Hamparian",
        current_title="Senior Accountant",
        current_company="Bridgepoint Capital",
        location="Boston, MA",
        ai_career_level="Mid",
        ai_certifications="CPA/CGMA",
        ai_years_experience="7",
        ai_summary="CPA/CGMA with private equity and real estate accounting background. Experienced with fund accounting, waterfall calculations, and investor reporting. Strong Excel and Yardi skills.",
        ai_skills='["Private Equity", "Real Estate", "Fund Accounting", "Yardi", "Waterfall Calculations", "Investor Reporting"]',
    ),
    Candidate(
        name="Jacqueline Bui",
        current_title="Senior Accountant",
        current_company="Grant Thornton",
        location="Woburn, MA",
        ai_career_level="Mid",
        ai_certifications=None,
        ai_years_experience="5",
        ai_summary="Senior accountant with both tax and audit experience from Grant Thornton. Versatile background across industries including manufacturing and retail. Looking to move into a corporate accounting role in the Boston area.",
        ai_skills='["Tax", "Audit", "Manufacturing", "Retail", "Corporate Accounting"]',
    ),
    Candidate(
        name="Osmani Rodriguez",
        current_title="Senior Tax Accountant",
        current_company="RSM US LLP",
        location="Boston, MA",
        ai_career_level="Senior",
        ai_certifications=None,
        ai_years_experience="8",
        ai_summary="Senior tax professional specializing in international tax, transfer pricing, and cross-border transactions. Extensive experience with multinational clients at RSM. ASC 740 expertise. Fluent in Spanish.",
        ai_skills='["International Tax", "Transfer Pricing", "ASC 740", "Cross-border", "RSM", "Multinational"]',
    ),
    Candidate(
        name="Lauren Murphy",
        current_title="FP&A Manager",
        current_company="Harrington Manufacturing",
        location="Hartford, CT",
        ai_career_level="Senior",
        ai_certifications="CMA",
        ai_years_experience="9",
        ai_summary="FP&A Manager with deep manufacturing cost accounting experience. Owns the annual budget process, monthly variance analysis, and capital expenditure tracking. CMA certified. Strong in Hyperion and SAP.",
        ai_skills='["FP&A", "Cost Accounting", "Manufacturing", "Hyperion", "SAP", "Variance Analysis"]',
    ),
    Candidate(
        name="James Okafor",
        current_title="CFO",
        current_company="NovaSpark Ventures",
        location="Providence, RI",
        ai_career_level="Executive",
        ai_certifications="CPA",
        ai_years_experience="18",
        ai_summary="Seasoned CFO with startup and venture-backed company experience. Has taken two companies through Series B fundraising and one through acquisition. Board-level communicator, strong in financial modeling and investor relations.",
        ai_skills='["CFO", "Fundraising", "M&A", "Investor Relations", "Financial Modeling", "Startup"]',
    ),
    Candidate(
        name="Meraf Haile",
        current_title="Senior Accountant",
        current_company="Steward Health Care",
        location="Stoneham, MA",
        ai_career_level="Mid",
        ai_certifications=None,
        ai_years_experience="5",
        ai_summary="Senior accountant at a large regional healthcare system. Handles complex intercompany eliminations, patient revenue accounting, and Medicare/Medicaid reporting. Detail-focused and deadline-driven.",
        ai_skills='["Healthcare", "Revenue Accounting", "Medicare", "Medicaid", "Intercompany", "Close"]',
    ),
    Candidate(
        name="Amy Thornton",
        current_title="Director of Finance",
        current_company="Lexington Biosciences",
        location="Waltham, MA",
        ai_career_level="Executive",
        ai_certifications="CPA",
        ai_years_experience="14",
        ai_summary="Director of Finance at a pre-commercial biotech with deep life sciences expertise. Manages SEC reporting, technical accounting for complex instruments, and partnership with the CFO on capital markets activity.",
        ai_skills='["Biotech", "Life Sciences", "SEC Reporting", "Technical Accounting", "Capital Markets", "Pre-IPO"]',
    ),
    Candidate(
        name="Chris Park",
        current_title="Staff Accountant",
        current_company="Novak & Associates CPA",
        location="Cambridge, MA",
        ai_career_level="Junior",
        ai_certifications=None,
        ai_years_experience="2",
        ai_summary="Staff accountant at a public accounting firm with two years of tax and bookkeeping experience. Recent graduate, eager to move into a corporate accounting role. Strong QuickBooks and Excel foundation.",
        ai_skills='["Public Accounting", "Tax", "QuickBooks", "Excel", "Bookkeeping"]',
    ),
    Candidate(
        name="Rachel Donovan",
        current_title="Tax Manager",
        current_company="BDO USA",
        location="Springfield, MA",
        ai_career_level="Senior",
        ai_certifications="CPA",
        ai_years_experience="10",
        ai_summary="Tax Manager at BDO with deep expertise in SALT, corporate tax, and multi-state compliance. Manages a book of business including manufacturing, distribution, and professional services clients.",
        ai_skills='["SALT", "Corporate Tax", "Multi-state Compliance", "BDO", "Manufacturing", "Distribution"]',
    ),
    Candidate(
        name="Kevin Liu",
        current_title="Financial Analyst",
        current_company="Fidelity Investments",
        location="Boston, MA",
        ai_career_level="Mid",
        ai_certifications="CFA",
        ai_years_experience="6",
        ai_summary="CFA charterholder with investment management and financial analysis experience at Fidelity. Strong in financial modeling, equity research, and portfolio analytics. Looking to transition from buy-side to corporate FP&A.",
        ai_skills='["CFA", "Investment Management", "Equity Research", "Financial Modeling", "FP&A", "Portfolio Analytics"]',
    ),
    Candidate(
        name="Diana Frost",
        current_title="Accounting Manager",
        current_company="Apex Distribution",
        location="Worcester, MA",
        ai_career_level="Senior",
        ai_certifications="CPA",
        ai_years_experience="11",
        ai_summary="Accounting Manager with distribution and operations background. Manages a team of 4, owns the full close cycle, and drives process automation initiatives. QuickBooks Enterprise and NetSuite implementation experience.",
        ai_skills='["Distribution", "Operations", "NetSuite", "QuickBooks", "Process Automation", "Team Management"]',
    ),
    Candidate(
        name="Tom Reilly",
        current_title="Payroll Manager",
        current_company="Eastern Consolidated HR",
        location="Quincy, MA",
        ai_career_level="Mid",
        ai_certifications=None,
        ai_years_experience="8",
        ai_summary="Payroll Manager with multi-state payroll and HR systems experience. Manages payroll for 600+ employees across 8 states. ADP Workforce Now and Workday certified. Strong understanding of wage and hour compliance.",
        ai_skills='["Payroll", "Multi-state", "ADP", "Workday", "HR Systems", "Compliance"]',
    ),
    Candidate(
        name="Natasha Brennan",
        current_title="Interim Controller",
        current_company="Self-employed",
        location="Boston, MA (Remote)",
        ai_career_level="Senior",
        ai_certifications="CPA",
        ai_years_experience="13",
        ai_summary="Fractional and interim Controller with consulting experience across 10+ companies. Specializes in CAS engagements, month-end close buildouts, and ERP implementations. Available for interim or permanent placement.",
        ai_skills='["Interim Controller", "Fractional CFO", "CAS", "ERP Implementation", "Close Buildout", "Consulting"]',
    ),
    Candidate(
        name="Andre Williams",
        current_title="Assistant Controller",
        current_company="Merrimack Construction",
        location="Lowell, MA",
        ai_career_level="Mid",
        ai_certifications="CPA",
        ai_years_experience="7",
        ai_summary="Assistant Controller at a mid-size construction firm. Manages job costing, WIP schedules, and subcontractor compliance. Strong in Sage 300 and construction-specific accounting. Ready to step up to Controller.",
        ai_skills='["Construction", "Job Costing", "WIP Schedules", "Sage 300", "Subcontractor Compliance"]',
    ),
]

for c in candidates:
    db.add(c)
db.commit()
print(f"  ✓ {len(candidates)} candidates inserted")

# ── Employers ───────────────────────────────────────────────────────────────
print("Seeding employers...")

employers = [
    EmployerProfile(
        company_name="Acme Manufacturing Corp",
        website_url="https://acmemfg.com",
        ai_industry="Manufacturing",
        ai_company_size="200 employees",
        ai_company_overview="PE-backed manufacturer of industrial components based in Boston. $45M revenue, targeting $2M EBITDA improvement. Currently upgrading ERP from SAP to NetSuite.",
        ai_hiring_needs='["Controller — urgent, current Controller leaving end of month"]',
        ai_talking_points='["PE sponsor is Summit Partners", "NetSuite go-live in Q3", "Salary flexible to $155K for right person", "Cultural fit is critical — lean team"]',
        ai_red_flags='["Timeline is urgent — need hire in 30 days"]',
        relationship_status="Active",
    ),
    EmployerProfile(
        company_name="Riverside Capital Partners",
        website_url="https://riversidecapital.com",
        ai_industry="Private Equity",
        ai_company_size="45 employees",
        ai_company_overview="Mid-market private equity firm with $1.2B AUM. Focused on business services and healthcare services buyouts. Typically hold companies 4-7 years.",
        ai_hiring_needs='["VP Finance — for a portfolio company CFO succession plan"]',
        ai_talking_points='["Strong carry opportunity", "Exposure to full deal lifecycle", "Report directly to Managing Partner", "Travel 20-30%"]',
        ai_red_flags=None,
        relationship_status="Active",
    ),
    EmployerProfile(
        company_name="ClearPath Health",
        website_url="https://clearpathhealth.com",
        ai_industry="Healthcare",
        ai_company_size="320 employees",
        ai_company_overview="Regional behavioral health network with 12 outpatient clinics across New England. Medicaid and commercial payer mix. Recently received $15M growth equity investment.",
        ai_hiring_needs='["Senior Accountant — to support the Controller with month-end close and payer reporting"]',
        ai_talking_points='["Mission-driven culture", "Great work-life balance", "Strong benefits", "Hybrid schedule available"]',
        ai_red_flags=None,
        relationship_status="Active",
    ),
    EmployerProfile(
        company_name="Vertex Software Inc",
        website_url="https://vertexsoftware.com",
        ai_industry="SaaS / Technology",
        ai_company_size="180 employees",
        ai_company_overview="B2B SaaS company providing workflow automation for mid-market professional services firms. $28M ARR, growing 40% YoY. Series B closed 8 months ago.",
        ai_hiring_needs='["FP&A Manager — to build out the finance function post-Series B"]',
        ai_talking_points='["Equity upside significant", "Direct line to CFO", "Build the FP&A function from scratch", "Remote-friendly"]',
        ai_red_flags=None,
        relationship_status="Active",
    ),
    EmployerProfile(
        company_name="Harborview Real Estate",
        website_url="https://harborviewre.com",
        ai_industry="Real Estate",
        ai_company_size="60 employees",
        ai_company_overview="Boston-based real estate investment and management firm with $400M AUM across multifamily and mixed-use properties in New England.",
        ai_hiring_needs='["Assistant Controller — to support fund accounting and investor reporting"]',
        ai_talking_points='["Growing portfolio — 3 acquisitions planned this year", "Collaborative team", "Yardi Voyager shop", "Direct mentorship from Controller"]',
        ai_red_flags=None,
        relationship_status="Warm",
    ),
    EmployerProfile(
        company_name="Northeast Biotech Group",
        website_url="https://nebiotech.com",
        ai_industry="Life Sciences",
        ai_company_size="95 employees",
        ai_company_overview="Clinical-stage biotech based in Lexington developing oncology therapies. Phase 2 trials underway. Well-funded with $120M in the bank from recent Series C.",
        ai_hiring_needs='["Director of Finance — to lead SEC reporting and prepare for IPO"]',
        ai_talking_points='["Pre-IPO equity", "High-impact role", "Partner with CFO on capital markets", "Lexington office, hybrid OK"]',
        ai_red_flags='["Pre-revenue — candidate must be comfortable with R&D accounting"]',
        relationship_status="Active",
    ),
    EmployerProfile(
        company_name="Atlantic Distribution Co",
        website_url="https://atlanticdist.com",
        ai_industry="Distribution",
        ai_company_size="410 employees",
        ai_company_overview="Regional wholesale distributor of building materials and industrial supplies. Family-owned, $90M revenue. Strong culture, low turnover. ERP is NetSuite.",
        ai_hiring_needs='["Accounting Manager — to own the close and supervise 3 staff accountants"]',
        ai_talking_points='["Stable, profitable business", "Long-tenured team", "Competitive salary + profit sharing", "Worcester location"]',
        ai_red_flags=None,
        relationship_status="Active",
    ),
    EmployerProfile(
        company_name="Summit CPA Group",
        website_url="https://summitcpa.com",
        ai_industry="Public Accounting",
        ai_company_size="55 employees",
        ai_company_overview="Regional CPA firm based in Boston serving closely-held businesses and high-net-worth individuals. Mix of tax, audit, and advisory services. Growing 15% per year.",
        ai_hiring_needs='["Tax Manager — to lead the corporate tax practice and mentor staff"]',
        ai_talking_points='["Partner track available in 3-4 years", "Flexible schedule", "Strong mentorship culture", "Diverse client base"]',
        ai_red_flags=None,
        relationship_status="Active",
    ),
]

for e in employers:
    db.add(e)
db.commit()
print(f"  ✓ {len(employers)} employers inserted")

# ── Job Orders ──────────────────────────────────────────────────────────────
print("Seeding job orders...")

job_orders = [
    JobOrder(
        title="Controller",
        company_name="Acme Manufacturing Corp",
        location="Boston, MA",
        salary_min=130000,
        salary_max=155000,
        status="open",
        requirements="CPA required. 8+ years experience. Manufacturing or PE-backed company background preferred. NetSuite a plus. Must be comfortable with tight timeline.",
    ),
    JobOrder(
        title="VP Finance",
        company_name="Riverside Capital Partners",
        location="Boston, MA",
        salary_min=175000,
        salary_max=210000,
        status="open",
        requirements="CPA preferred. 12+ years experience. PE or investment management background. Board-level communication skills. Travel required.",
    ),
    JobOrder(
        title="Senior Accountant",
        company_name="ClearPath Health",
        location="Waltham, MA",
        salary_min=85000,
        salary_max=105000,
        status="open",
        requirements="3-6 years experience. Healthcare or nonprofit background a plus. NetSuite experience preferred. Strong close and reconciliation skills.",
    ),
    JobOrder(
        title="FP&A Manager",
        company_name="Vertex Software Inc",
        location="Cambridge, MA",
        salary_min=120000,
        salary_max=145000,
        status="open",
        requirements="5+ years FP&A experience. SaaS company background strongly preferred. Experience with ARR, CAC, LTV metrics. Adaptive or Anaplan a plus.",
    ),
    JobOrder(
        title="Director of Finance",
        company_name="Northeast Biotech Group",
        location="Lexington, MA",
        salary_min=160000,
        salary_max=195000,
        status="open",
        requirements="CPA required. 10+ years experience. Life sciences or biotech required. SEC reporting and pre-IPO experience strongly preferred.",
    ),
    JobOrder(
        title="Tax Manager",
        company_name="Summit CPA Group",
        location="Boston, MA",
        salary_min=110000,
        salary_max=135000,
        status="open",
        requirements="CPA required. 7+ years tax experience. Public accounting background preferred. Corporate tax and SALT expertise. Partner track opportunity.",
    ),
]

for j in job_orders:
    db.add(j)
db.commit()
print(f"  ✓ {len(job_orders)} job orders inserted")

# ── Bookings with Meeting Summaries ─────────────────────────────────────────
print("Seeding bookings...")

today = date.today()

bookings = [
    # Today x2
    Booking(
        booking_type="outbound_employer",
        employer_name="Michael Torres",
        employer_email="mtorres@acmemfg.com",
        company_name="Acme Manufacturing Corp",
        date=today,
        time_slot="9:00 AM",
        status="confirmed",
        meeting_url="https://zoom.us/j/123456789",
        meeting_summary="Met with CFO Michael Torres re: Controller search. Company is 200 employees, PE-backed by Summit Partners, targeting $2M EBITDA improvement this year. Need a CPA with manufacturing cost accounting experience and NetSuite familiarity. Current Controller leaving end of month — timeline is urgent. Salary budget flexible to $155K for the right person. Strong cultural fit matters — lean team, no politics. Follow up Friday with top 3 candidates. Key question: must be comfortable with PE sponsor reporting cadence.",
    ),
    Booking(
        booking_type="outbound_candidate",
        employer_name="Sarah Chen",
        employer_email="schen@email.com",
        company_name=None,
        date=today,
        time_slot="11:30 AM",
        status="confirmed",
        meeting_url="https://zoom.us/j/987654321",
        meeting_summary="Intro call with Sarah Chen. Currently Senior Accountant at MedBridge Health in Boston. 5 years experience, strong NetSuite skills, healthcare background. Interested in moving into an Accounting Manager or Controller track role. Salary target $95-110K. Open to hybrid. Very polished communicator — would present well to clients. Follow up: send her the ClearPath Health Senior Accountant role and the Atlantic Distribution Accounting Manager role.",
    ),
    # This week x3
    Booking(
        booking_type="outbound_employer",
        employer_name="Amanda Price",
        employer_email="aprice@riversidecapital.com",
        company_name="Riverside Capital Partners",
        date=today - timedelta(days=1),
        time_slot="10:00 AM",
        status="confirmed",
        meeting_url="https://zoom.us/j/111222333",
        meeting_summary="Call with Amanda Price, Chief of Staff at Riverside Capital. They are building out the finance function for a portfolio company in the business services space — $80M revenue, targeting add-on acquisitions. Need a VP Finance who can eventually step into CFO role. Candidate must have PE exposure and be comfortable with board-level reporting. Comp: $175-210K base plus meaningful carry. Timeline: 60 days. Send Marcus Johnson and James Okafor profiles this week.",
    ),
    Booking(
        booking_type="outbound_candidate",
        employer_name="Marcus Johnson",
        employer_email="mjohnson@email.com",
        company_name=None,
        date=today - timedelta(days=1),
        time_slot="2:00 PM",
        status="confirmed",
        meeting_url="https://zoom.us/j/444555666",
        meeting_summary="Strong call with Marcus Johnson. VP Finance at CloudMetrics, 16 years experience, CPA, SaaS background. Currently earning $195K total comp. Target $210-230K for a move. Open to PE-backed environments — has worked with board-level stakeholders at CloudMetrics. Confident presenter, very strategic thinker. Excellent fit for Riverside Capital VP Finance role. Also potentially right for the Vertex FP&A Manager role if he's open to a step back in title for equity upside. Schedule follow-up next week.",
    ),
    Booking(
        booking_type="outbound_employer",
        employer_name="Dr. Lisa Park",
        employer_email="lpark@nebiotech.com",
        company_name="Northeast Biotech Group",
        date=today - timedelta(days=2),
        time_slot="3:00 PM",
        status="confirmed",
        meeting_url="https://zoom.us/j/777888999",
        meeting_summary="Discovery call with Dr. Lisa Park, CFO of Northeast Biotech Group. Pre-revenue clinical stage biotech, Phase 2 trials in oncology. Well-funded — $120M cash on hand post Series C. Hiring a Director of Finance to lead SEC reporting and prepare for a potential IPO in 18-24 months. Must have Big 4 or public biotech background. Pre-IPO equity package is strong. Top candidates: Priya Patel (Big 4, life sciences interest) and Amy Thornton (current Director at Lexington Biosciences). Schedule second call after sending profiles.",
    ),
    # Past x5
    Booking(
        booking_type="outbound_employer",
        employer_name="Greg Hanson",
        employer_email="ghanson@vertexsoftware.com",
        company_name="Vertex Software Inc",
        date=today - timedelta(days=7),
        time_slot="1:00 PM",
        status="confirmed",
        meeting_url="https://zoom.us/j/101010101",
        meeting_summary="Intro call with Greg Hanson, CFO at Vertex Software. SaaS company, $28M ARR growing 40% YoY, just closed Series B. Needs an FP&A Manager to build out the finance function — currently just Greg and one analyst. Ideal candidate: 5+ years FP&A, SaaS metrics fluency (ARR, CAC, LTV, churn), Adaptive or Anaplan experience a plus. Comp: $120-145K plus equity. Open to remote. Great culture — Greg is an excellent mentor. Marcus Johnson would be a great fit if salary works.",
    ),
    Booking(
        booking_type="outbound_candidate",
        employer_name="Jennifer Walsh",
        employer_email="jwalsh@email.com",
        company_name=None,
        date=today - timedelta(days=8),
        time_slot="9:00 AM",
        status="confirmed",
        meeting_url="https://zoom.us/j/202020202",
        meeting_summary="Excellent call with Jennifer Walsh. Senior Manager at Deloitte, 12 years Big 4, CPA, NetSuite certified. Looking to make the jump to industry as a Controller. Target salary $140-155K. Boston only — not open to relocation. Very polished, would interview extremely well. Strong technical accounting skills — SOX, GAAP, audit. Perfect fit for the Acme Manufacturing Controller role. She is motivated and ready to move quickly. Submit her profile to Acme this week. Also keep in mind for any future Controller searches.",
    ),
    Booking(
        booking_type="outbound_employer",
        employer_name="Robert Chang",
        employer_email="rchang@atlanticdist.com",
        company_name="Atlantic Distribution Co",
        date=today - timedelta(days=10),
        time_slot="11:00 AM",
        status="confirmed",
        meeting_url="https://zoom.us/j/303030303",
        meeting_summary="Call with Robert Chang, Controller at Atlantic Distribution. Family-owned distribution business, $90M revenue, very stable. Hiring an Accounting Manager to own the close and supervise 3 staff. NetSuite shop. Culture is old-school but very loyal — average tenure is 9 years. Salary $95-115K plus profit sharing. Looking for someone who wants to grow with the company long-term. Diana Frost is a strong match — distribution background, NetSuite, manages a team. Also consider Natasha Brennan if she is open to permanent.",
    ),
    Booking(
        booking_type="outbound_candidate",
        employer_name="Amy Thornton",
        employer_email="athornton@email.com",
        company_name=None,
        date=today - timedelta(days=12),
        time_slot="10:00 AM",
        status="confirmed",
        meeting_url="https://zoom.us/j/404040404",
        meeting_summary="Call with Amy Thornton. Director of Finance at Lexington Biosciences, CPA, 14 years experience. Deep biotech and life sciences background — SEC reporting, technical accounting for complex instruments, capital markets work. Currently earning $185K. Open to a move for the right pre-IPO opportunity with meaningful equity. Would be a perfect fit for Northeast Biotech Director of Finance role. She asked good questions about the IPO timeline and sponsor quality. Very impressive candidate. Submit to Northeast Biotech immediately.",
    ),
    Booking(
        booking_type="outbound_employer",
        employer_name="Patricia Moore",
        employer_email="pmoore@summitcpa.com",
        company_name="Summit CPA Group",
        date=today - timedelta(days=14),
        time_slot="2:30 PM",
        status="confirmed",
        meeting_url="https://zoom.us/j/505050505",
        meeting_summary="Discovery call with Patricia Moore, Managing Partner at Summit CPA Group. Regional firm, 55 people, growing 15% per year. Hiring a Tax Manager to lead the corporate tax practice and mentor 4 staff. Partner track available in 3-4 years for the right person. Must have CPA and 7+ years tax experience, public accounting background preferred. Comp $110-135K. Rachel Donovan is a strong fit — BDO background, SALT expertise, manages a book of business. Also consider Osmani Rodriguez for the international tax component.",
    ),
]

for b in bookings:
    db.add(b)
db.commit()
print(f"  ✓ {len(bookings)} bookings inserted")

db.close()
print("\n✅ Seed complete. Run the embedding backfill next.")
print(
    '   python -c "from app.services.embedding_service import sync_embeddings, backfill_bookings; sync_embeddings(); backfill_bookings()"'
)
