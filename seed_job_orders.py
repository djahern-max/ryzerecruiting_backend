"""
seed_job_orders.py
------------------
Populates the job_orders table with realistic fake data for demo/video purposes.

Usage:
    python seed_job_orders.py

Reads DATABASE_URL from environment (or edit DB_URL below directly).
"""

import os
import random
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values

# ── Config ──────────────────────────────────────────────────────────────────
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://dane@localhost/ryzerecruiting",  # ← adjust if needed
)
DEFAULT_TENANT = "ryze"
NUM_JOBS = 40  # how many fake orders to insert

# ── Job data pools ───────────────────────────────────────────────────────────

TITLES = [
    "Senior Software Engineer",
    "Full Stack Developer",
    "DevOps Engineer",
    "Backend Engineer (Python)",
    "Frontend React Developer",
    "Cloud Infrastructure Engineer",
    "Data Engineer",
    "Machine Learning Engineer",
    "Site Reliability Engineer",
    "Platform Engineer",
    "Mobile Developer (iOS)",
    "Mobile Developer (Android)",
    "QA Automation Engineer",
    "Security Engineer",
    "Staff Software Engineer",
    "Principal Engineer",
    "Engineering Manager",
    "VP of Engineering",
    "Director of Software Development",
    "Product Manager – Platform",
    "Technical Program Manager",
    "Solutions Architect",
    "Enterprise Account Executive",
    "Sales Development Representative",
    "Customer Success Manager",
    "Head of Customer Success",
    "UX/UI Designer",
    "Product Designer",
    "Data Analyst",
    "Business Intelligence Engineer",
    "Controller",
    "Senior Accountant",
    "HR Business Partner",
    "Talent Acquisition Specialist",
    "Marketing Manager",
    "Content Marketing Lead",
    "Growth Marketing Manager",
    "Operations Manager",
    "Chief of Staff",
    "General Counsel",
]

LOCATIONS = [
    "Boston, MA (Hybrid)",
    "New York, NY (Remote)",
    "Austin, TX (On-site)",
    "San Francisco, CA (Hybrid)",
    "Chicago, IL (Remote)",
    "Seattle, WA (Hybrid)",
    "Denver, CO (Remote)",
    "Atlanta, GA (On-site)",
    "Nashville, TN (Hybrid)",
    "Remote – USA",
    "Manchester, NH (Hybrid)",
    "Dallas, TX (On-site)",
    "Miami, FL (Remote)",
    "Los Angeles, CA (Hybrid)",
    "Philadelphia, PA (On-site)",
]

STATUSES = ["open", "open", "open", "open", "on_hold", "filled"]  # weighted toward open

REQUIREMENTS_POOL = [
    "5+ years of professional software development experience\n• Strong proficiency in Python and/or Go\n• Experience with cloud platforms (AWS, GCP, or Azure)\n• Excellent communication and collaboration skills\n• BS/MS in Computer Science or equivalent",
    "3-5 years in a similar role\n• Proficiency with React and TypeScript\n• Experience with REST APIs and GraphQL\n• Familiarity with CI/CD pipelines\n• Strong attention to detail and UX sensibility",
    "7+ years of relevant industry experience\n• Proven leadership and cross-functional collaboration skills\n• Strong analytical and problem-solving abilities\n• Experience in fast-paced, high-growth environments\n• Excellent written and verbal communication",
    "Experience with containerization (Docker, Kubernetes)\n• Strong understanding of networking, security, and infrastructure\n• Proficient in Terraform or Ansible\n• Track record of improving system reliability and uptime\n• On-call rotation willingness",
    "SQL proficiency and experience with data warehousing (Snowflake, Redshift, BigQuery)\n• Experience with dbt or similar transformation tools\n• Python scripting for automation and pipeline management\n• Strong stakeholder communication skills\n• 4+ years of data engineering experience",
    "Proven track record of closing enterprise deals ($100K+)\n• Strong consultative selling skills\n• Experience with Salesforce CRM\n• Excellent negotiation and relationship-building skills\n• 3+ years of B2B SaaS sales experience",
    "Deep understanding of user-centered design principles\n• Proficiency in Figma and prototyping tools\n• Experience conducting user research and usability testing\n• Portfolio demonstrating end-to-end product design\n• Strong collaboration with engineering and product teams",
    "CPA or CPA candidate preferred\n• 4+ years of accounting experience\n• Proficiency with NetSuite or similar ERP\n• Strong knowledge of GAAP\n• Experience with month-end close and financial reporting",
]

NOTES_POOL = [
    "Client is looking to fill ASAP. Strong preference for candidates who can start within 30 days.",
    "This role has been open for 2 months. Client wants to see a diverse slate of candidates.",
    "Confidential search. Do not share client name with candidates until first interview.",
    "Hybrid is flexible — client will consider fully remote for the right candidate.",
    "Budget is firm. Do not submit candidates above $X max.",
    "Client prefers candidates from fintech or healthtech backgrounds.",
    "First interview is a technical screen via HackerRank; warm candidates before sending.",
    "High-growth Series B startup, great equity upside. Sell the mission.",
    "Client has had 3 rejections at offer stage — focus on candidates who are motivated to move.",
    "Newly created headcount. JD still being refined — use this as a guide only.",
]

SALARY_RANGES = [
    (80_000, 100_000),
    (90_000, 120_000),
    (100_000, 130_000),
    (110_000, 140_000),
    (120_000, 155_000),
    (130_000, 165_000),
    (140_000, 175_000),
    (150_000, 190_000),
    (160_000, 200_000),
    (180_000, 220_000),
    (70_000, 90_000),
    (75_000, 95_000),
]


def random_date(days_back=180):
    delta = timedelta(days=random.randint(0, days_back))
    return datetime.utcnow() - delta


def build_job(employer_ids, tenant_id):
    title = random.choice(TITLES)
    salary_min, salary_max = random.choice(SALARY_RANGES)
    status = random.choice(STATUSES)
    created_at = random_date()
    filled_at = random_date() if status == "filled" else None

    return (
        tenant_id,  # tenant_id
        random.choice(employer_ids) if employer_ids else None,  # employer_profile_id
        title,  # title
        random.choice(LOCATIONS),  # location
        salary_min,  # salary_min
        salary_max,  # salary_max
        random.choice(REQUIREMENTS_POOL),  # requirements
        random.choice(NOTES_POOL),  # notes
        f"{title} — Full requirements available upon request.",  # raw_text
        status,  # status
        created_at,  # created_at
        created_at,  # updated_at
        filled_at,  # filled_at
    )


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # 1. Fetch existing employer_profile_ids for this tenant
    cur.execute(
        "SELECT id FROM employer_profiles WHERE tenant_id = %s",
        (DEFAULT_TENANT,),
    )
    employer_ids = [row[0] for row in cur.fetchall()]
    if not employer_ids:
        print(
            "⚠️  No employer_profiles found for tenant 'ryze'. "
            "Jobs will be inserted with employer_profile_id = NULL."
        )
    else:
        print(f"✅ Found {len(employer_ids)} employer profile(s): {employer_ids}")

    # 2. Build rows — use each title once, shuffle the rest
    titles_shuffled = TITLES.copy()
    random.shuffle(titles_shuffled)

    rows = [build_job(employer_ids, DEFAULT_TENANT) for _ in range(NUM_JOBS)]

    # 3. Insert
    insert_sql = """
        INSERT INTO job_orders (
            tenant_id, employer_profile_id, title, location,
            salary_min, salary_max, requirements, notes, raw_text,
            status, created_at, updated_at, filled_at
        ) VALUES %s
    """
    execute_values(cur, insert_sql, rows)
    conn.commit()

    print(f"🎉 Inserted {NUM_JOBS} fake job orders into the database.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
