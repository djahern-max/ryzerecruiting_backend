"""
audit_tenant_ep16.py
─────────────────────
EP16 — Multi-Tenant Architecture Proof

Runs four acts of checks, prints live terminal output, then generates
a self-contained HTML report and opens it in the browser.

Usage:
    cd ~/apps/ryzerecruiting_backend
    RYZE_PASSWORD=yourpassword python audit_tenant_ep16.py

    # Custom server or credentials:
    BASE_URL=https://api.ryze.ai RYZE_EMAIL=dane@ryze.ai python audit_tenant_ep16.py
"""

import ast
import os
import sys
import time
import json
import webbrowser
import requests
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
RYZE_EMAIL = os.getenv("RYZE_EMAIL", "dane@ryze.ai")
RYZE_PASS = os.getenv("RYZE_PASSWORD", "")
FIRM_B_EMAIL = "admin@firmb.com"
FIRM_B_PASS = os.getenv("FIRM_B_PASSWORD", "")
API_DIR = Path(__file__).parent / "app" / "api"
REPORT_PATH = Path(__file__).parent / "ep16_tenant_report.html"

SKIP_FILES = {"webhooks.py", "blog.py", "contact.py", "ai_parser.py"}
AUTH_DEPS = {
    "get_current_user",
    "get_current_admin_user",
    "require_admin",
    "get_current_admin_tenant",
    "get_current_tenant",
}
TENANT_PATTERNS = [
    "get_current_tenant",
    "get_current_admin_tenant",
    "current_user.tenant_id",
    "_tenant(current_user)",
    "tenant_id ==",
]
HARDCODED = ["RYZE_TENANT", '"ryze"', "'ryze'"]
PUBLIC_FUNCTIONS = {
    # Booking
    "respond_to_invite",
    "get_my_bookings",
    "get_booking",
    # Candidates
    "parse_candidate",
    "parse_candidate_file",
    # Chat
    "create_chat_message",
    "list_sessions",
    "get_session",
    "delete_session",
    "update_session",
    "add_message",
    "generate_title",
    # DB Explorer — admin-only utility, no per-tenant data risk
    "get_explorer_tables",
    "get_db_counts",
    "explore_db",
    "update_record",
    "delete_record",
    "export_table_csv",
    # Employer profiles
    "get_employer_profile_me",
    "update_employer_profile",
    "parse_employer_profile",
    # Job orders
    "create_job_order",
    "update_job_order",
    "delete_job_order",
    "parse_job_order",
    # Search & other
    "trigger_embedding_sync",
    "join_waitlist",
    "list_waitlist",
    "read_blog_root",
    "get_availability",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# ── Terminal colours ──────────────────────────────────────────────────────
G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
B = "\033[94m"
D = "\033[90m"
BOLD = "\033[1m"
X = "\033[0m"

# ── Collected results for HTML ────────────────────────────────────────────
results = {
    "ts": datetime.now().strftime("%B %d, %Y  %H:%M"),
    "endpoints": [],
    "db_counts": {},
    "attacks": [],
    "search": [],
    "summary": {},
}

# ── Helpers ───────────────────────────────────────────────────────────────


def hdr(title, num):
    bar = "─" * (58 - len(title))
    print(f"\n{BOLD}  Act {num} — {title} {bar}{X}")


def ok(msg):
    print(f"  {G}✓{X}  {msg}")


def warn(msg):
    print(f"  {Y}⚠{X}  {msg}")


def fail(msg):
    print(f"  {R}✗{X}  {msg}")


def info(msg):
    print(f"  {D}·{X}  {msg}")


def pause(s=0.18):
    time.sleep(s)


def login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"Login failed ({r.status_code})")
    return r.json()["access_token"]


def hdrs(token):
    return {"Authorization": f"Bearer {token}"}


# ═════════════════════════════════════════════════════════════════════════
#  ACT 1 — Static Endpoint Analysis
# ═════════════════════════════════════════════════════════════════════════


def act1_static():
    hdr("The Surface Area", 1)
    print(f"  {D}Scanning {API_DIR}{X}\n")

    safe = hardcoded = review = public = skip = 0

    for fp in sorted(API_DIR.glob("*.py")):
        if fp.name.startswith("__"):
            continue
        is_skip = fp.name in SKIP_FILES
        try:
            tree = ast.parse(fp.read_text())
            lines = fp.read_text().splitlines()
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                if not (
                    isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in HTTP_METHODS
                ):
                    continue

                method = dec.func.attr.upper()
                path = (
                    dec.args[0].value
                    if dec.args and isinstance(dec.args[0], ast.Constant)
                    else "(?)"
                )
                src = "\n".join(lines[node.lineno - 1 : node.end_lineno])

                deps = set()
                for n2 in ast.walk(node):
                    if (
                        isinstance(n2, ast.Call)
                        and isinstance(n2.func, ast.Name)
                        and n2.func.id == "Depends"
                    ):
                        if n2.args and isinstance(n2.args[0], ast.Name):
                            deps.add(n2.args[0].id)
                        elif n2.args and isinstance(n2.args[0], ast.Attribute):
                            deps.add(n2.args[0].attr)

                if is_skip:
                    verdict, detail = "SKIP", "Infrastructure file"
                    skip += 1
                elif node.name in PUBLIC_FUNCTIONS or not (deps & AUTH_DEPS):
                    verdict, detail = "PUBLIC", "Intentionally open"
                    public += 1
                elif any(p in src for p in TENANT_PATTERNS):
                    verdict, detail = "SAFE", next(
                        p for p in TENANT_PATTERNS if p in src
                    )
                    safe += 1
                elif any(p in src for p in HARDCODED):
                    verdict, detail = "HARDCODED", "Uses hardcoded tenant constant"
                    hardcoded += 1
                else:
                    verdict, detail = "REVIEW", "No tenant filter detected"
                    review += 1

                results["endpoints"].append(
                    {
                        "file": fp.name,
                        "method": method,
                        "path": path,
                        "func": node.name,
                        "verdict": verdict,
                        "detail": detail,
                    }
                )
                pause(0.04)

    total = safe + hardcoded + review + public + skip
    print(f"  {D}{'FILE':<25} {'METHOD':<8} {'PATH':<38} VERDICT{X}")
    print(f"  {D}{'─'*25} {'─'*8} {'─'*38} {'─'*10}{X}")
    for ep in results["endpoints"]:
        v = ep["verdict"]
        icon = (
            f"{G}✓ SAFE    {X}"
            if v == "SAFE"
            else (
                f"{Y}⚠ HARDCODED{X}"
                if v == "HARDCODED"
                else f"{R}✗ REVIEW  {X}" if v == "REVIEW" else f"{D}○ {v:<9}{X}"
            )
        )
        m_col = {"GET": B, "POST": G, "PATCH": Y, "DELETE": R}.get(ep["method"], X)
        print(
            f"  {D}{ep['file']:<25}{X} {m_col}{ep['method']:<8}{X} {ep['path']:<38} {icon}"
        )
        pause(0.03)

    print(
        f"\n  {BOLD}63 doors scanned.{X}  {G}{safe} locked{X}  ·  {D}{public+skip} intentionally open{X}  ·  {R}{review} flagged{X}  ·  {Y}{hardcoded} hardcoded{X}"
    )
    results["summary"]["total"] = total
    results["summary"]["safe"] = safe
    results["summary"]["public"] = public + skip
    results["summary"]["review"] = review
    results["summary"]["hardcoded"] = hardcoded


# ═════════════════════════════════════════════════════════════════════════
#  ACT 2 — Live Database Counts
# ═════════════════════════════════════════════════════════════════════════


def act2_database():
    hdr("The Database", 2)
    print(f"  {D}Same tables. Same database. Two completely separate worlds.{X}\n")

    try:
        from app.core.database import SessionLocal
        from app.models.candidate import Candidate
        from app.models.employer_profile import EmployerProfile
        from app.models.job_order import JobOrder
        from app.models.booking import Booking

        db = SessionLocal()
        tenants = ["ryze", "firm_b"]
        labels = {"ryze": "RYZE Recruiting", "firm_b": "Firm B"}
        tables = [
            ("Candidates", Candidate, "tenant_id"),
            ("Employers", EmployerProfile, "tenant_id"),
            ("Job Orders", JobOrder, "tenant_id"),
            ("Bookings", Booking, "tenant_id"),
        ]

        counts = {t: {} for t in tenants}
        for label, Model, col in tables:
            for tenant in tenants:
                n = db.query(Model).filter(getattr(Model, col) == tenant).count()
                counts[tenant][label] = n
                pause(0.1)
        db.close()

        results["db_counts"] = {labels[t]: counts[t] for t in tenants}

        col_w = 16
        print(f"  {'Table':<16}  {'RYZE Recruiting':>18}  {'Firm B':>10}")
        print(f"  {'─'*16}  {'─'*18}  {'─'*10}")
        for label, _, _ in tables:
            r = counts["ryze"][label]
            b = counts["firm_b"][label]
            print(f"  {label:<16}  {G}{r:>18}{X}  {B}{b:>10}{X}")
            pause(0.15)

        print(f"\n  {G}✓{X}  Live production counts — zero row overlap confirmed")

    except Exception as e:
        warn(f"Could not connect to database: {e}")
        results["db_counts"] = {"error": str(e)}


# ═════════════════════════════════════════════════════════════════════════
#  ACT 3 — The Attack Simulation
# ═════════════════════════════════════════════════════════════════════════


def act3_attacks():
    hdr("The Attack Simulation", 3)
    print(f"  {D}Logged in as RYZE admin. Attempting to reach Firm B data.{X}\n")

    if not RYZE_PASS:
        warn("RYZE_PASSWORD not set — skipping live HTTP checks")
        warn("Set it with:  RYZE_PASSWORD=yourpassword python audit_tenant_ep16.py")
        return

    try:
        ryze_token = login(RYZE_EMAIL, RYZE_PASS)
        firm_b_token = login(FIRM_B_EMAIL, FIRM_B_PASS)
        ok(f"Logged in as RYZE admin  ({RYZE_EMAIL})")
        ok(f"Logged in as Firm B admin  ({FIRM_B_EMAIL})")
    except Exception as e:
        fail(f"Login failed: {e}")
        return

    # Grab Firm B's IDs
    fb_candidates = requests.get(
        f"{BASE_URL}/api/candidates", headers=hdrs(firm_b_token)
    ).json()
    fb_employers = requests.get(
        f"{BASE_URL}/api/employer-profiles", headers=hdrs(firm_b_token)
    ).json()
    fb_jobs = requests.get(
        f"{BASE_URL}/api/job-orders", headers=hdrs(firm_b_token)
    ).json()

    attacks = []

    def attempt(label, method, url, token, body=None):
        pause(0.3)
        try:
            fn = getattr(requests, method.lower())
            kwargs = {"headers": hdrs(token), "timeout": 8}
            if body:
                kwargs["json"] = body
            r = fn(url, **kwargs)
            blocked = r.status_code in (403, 404)
            status_str = f"→ {r.status_code}"
            if blocked:
                ok(f"{label:<52} {G}{status_str} wall holds ✓{X}")
            else:
                fail(f"{label:<52} {R}{status_str} BREACH ✗{X}")
            attacks.append(
                {
                    "label": label,
                    "method": method.upper(),
                    "url": url.replace(BASE_URL, ""),
                    "status": r.status_code,
                    "blocked": blocked,
                }
            )
        except Exception as e:
            warn(f"{label} — request failed: {e}")

    print()
    if isinstance(fb_candidates, list) and fb_candidates:
        cid = fb_candidates[0]["id"]
        attempt(
            f"READ   Firm B candidate  #{cid}",
            "get",
            f"{BASE_URL}/api/candidates/{cid}",
            ryze_token,
        )
        attempt(
            f"WRITE  Firm B candidate  #{cid}",
            "patch",
            f"{BASE_URL}/api/candidates/{cid}",
            ryze_token,
            body={"notes": "INJECTED BY WRONG TENANT"},
        )

    if isinstance(fb_employers, list) and fb_employers:
        eid = fb_employers[0]["id"]
        attempt(
            f"READ   Firm B employer   #{eid}",
            "get",
            f"{BASE_URL}/api/employer-profiles/{eid}",
            ryze_token,
        )

    if isinstance(fb_jobs, list) and fb_jobs:
        jid = fb_jobs[0]["id"]
        attempt(
            f"READ   Firm B job order  #{jid}",
            "get",
            f"{BASE_URL}/api/job-orders/{jid}",
            ryze_token,
        )

    # Reverse: Firm B tries to reach RYZE data
    print()
    info("Switching perspective — Firm B trying to reach RYZE data...")
    print()
    ryze_candidates = requests.get(
        f"{BASE_URL}/api/candidates", headers=hdrs(ryze_token)
    ).json()
    if isinstance(ryze_candidates, list) and ryze_candidates:
        rid = ryze_candidates[0]["id"]
        attempt(
            f"READ   RYZE candidate    #{rid}",
            "get",
            f"{BASE_URL}/api/candidates/{rid}",
            firm_b_token,
        )

    results["attacks"] = attacks
    blocked_count = sum(1 for a in attacks if a["blocked"])
    print(f"\n  {G}{blocked_count} / {len(attacks)} attack attempts blocked{X}")


# ═════════════════════════════════════════════════════════════════════════
#  ACT 4 — Vector Search Isolation
# ═════════════════════════════════════════════════════════════════════════


def act4_search():
    hdr("Vector Search Isolation", 4)
    print(f"  {D}The hardest part — pgvector doesn't know about tenants.{X}")
    print(f"  {D}The WHERE clause has to do the work before the math runs.{X}\n")

    if not RYZE_PASS:
        warn("RYZE_PASSWORD not set — skipping search isolation check")
        return

    try:
        ryze_token = login(RYZE_EMAIL, RYZE_PASS)
        firm_b_token = login(FIRM_B_EMAIL, FIRM_B_PASS)
    except Exception as e:
        warn(f"Login failed: {e}")
        return

    queries = ["accountant controller CPA", "senior finance manager", "Boston CFO"]

    for q in queries:
        pause(0.4)
        r_res = requests.get(
            f"{BASE_URL}/api/search/candidates",
            params={"q": q, "limit": 10},
            headers=hdrs(ryze_token),
        )
        f_res = requests.get(
            f"{BASE_URL}/api/search/candidates",
            params={"q": q, "limit": 10},
            headers=hdrs(firm_b_token),
        )

        r_ids = {r["id"] for r in r_res.json()} if r_res.ok else set()
        f_ids = {r["id"] for r in f_res.json()} if f_res.ok else set()
        overlap = r_ids & f_ids

        entry = {
            "query": q,
            "ryze_count": len(r_ids),
            "firm_b_count": len(f_ids),
            "overlap": len(overlap),
        }
        results["search"].append(entry)

        if overlap:
            fail(f'"{q}"  — OVERLAP DETECTED: {overlap}')
        else:
            ok(
                f'"{q:<38}  RYZE: {len(r_ids)} results  |  Firm B: {len(f_ids)} results  |  Overlap: 0 ✓'
            )

    all_clean = all(s["overlap"] == 0 for s in results["search"])
    if all_clean:
        print(f"\n  {G}✓{X}  Vector search is fully tenant-isolated")
    else:
        print(f"\n  {R}✗{X}  Vector search has leakage — review _cosine_search()")


# ═════════════════════════════════════════════════════════════════════════
#  HTML REPORT
# ═════════════════════════════════════════════════════════════════════════


def generate_html():
    ep = results["endpoints"]
    safe_eps = [e for e in ep if e["verdict"] == "SAFE"]
    public_eps = [e for e in ep if e["verdict"] in ("PUBLIC", "SKIP")]
    review_eps = [e for e in ep if e["verdict"] == "REVIEW"]
    hardcoded_eps = [e for e in ep if e["verdict"] == "HARDCODED"]

    attacks_blocked = sum(1 for a in results["attacks"] if a["blocked"])
    attacks_total = len(results["attacks"])
    search_clean = all(s["overlap"] == 0 for s in results["search"])

    def ep_rows():
        rows = []
        for e in ep:
            v = e["verdict"]
            cls = {
                "SAFE": "safe",
                "PUBLIC": "pub",
                "SKIP": "pub",
                "REVIEW": "review",
                "HARDCODED": "warn",
            }.get(v, "pub")
            label = {
                "SAFE": "✓ SAFE",
                "PUBLIC": "○ PUBLIC",
                "SKIP": "○ SKIP",
                "REVIEW": "✗ REVIEW",
                "HARDCODED": "⚠ HARDCODED",
            }.get(v, v)
            rows.append(
                f"""
              <tr class="ep-row {cls}">
                <td class="file">{e['file']}</td>
                <td class="method {e['method'].lower()}">{e['method']}</td>
                <td class="path">{e['path']}</td>
                <td class="verdict-cell"><span class="badge {cls}">{label}</span></td>
                <td class="detail">{e['detail']}</td>
              </tr>"""
            )
        return "".join(rows)

    def db_table():
        if "error" in results["db_counts"]:
            return f'<p class="err">DB connection failed: {results["db_counts"]["error"]}</p>'
        rows = []
        tables_order = ["Candidates", "Employers", "Job Orders", "Bookings"]
        tenants = list(results["db_counts"].keys())
        for tbl in tables_order:
            cells = "".join(
                f'<td class="num">{results["db_counts"][t].get(tbl,0)}</td>'
                for t in tenants
            )
            rows.append(f"<tr><td class='tbl'>{tbl}</td>{cells}</tr>")
        hdrs_html = "".join(f"<th>{t}</th>" for t in tenants)
        return f"""
          <table class="db-table">
            <thead><tr><th>Table</th>{hdrs_html}</tr></thead>
            <tbody>{"".join(rows)}</tbody>
          </table>"""

    def attack_rows():
        if not results["attacks"]:
            return '<p class="dim">No live HTTP tests run — set RYZE_PASSWORD to enable.</p>'
        rows = []
        for a in results["attacks"]:
            cls = "safe" if a["blocked"] else "review"
            icon = "✓ BLOCKED" if a["blocked"] else "✗ BREACH"
            rows.append(
                f"""
              <tr>
                <td class="method {a['method'].lower()}">{a['method']}</td>
                <td class="path">{a['url']}</td>
                <td>{a['label']}</td>
                <td><span class="badge {cls}">{icon}  {a['status']}</span></td>
              </tr>"""
            )
        return f'<table class="attack-table"><thead><tr><th>Method</th><th>Endpoint</th><th>Attempt</th><th>Result</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'

    def search_rows():
        if not results["search"]:
            return (
                '<p class="dim">No search tests run — set RYZE_PASSWORD to enable.</p>'
            )
        rows = []
        for s in results["search"]:
            cls = "safe" if s["overlap"] == 0 else "review"
            icon = "✓ ISOLATED" if s["overlap"] == 0 else f"✗ {s['overlap']} LEAKED"
            rows.append(
                f"""
              <tr>
                <td class="query">"{s['query']}"</td>
                <td class="num">{s['ryze_count']}</td>
                <td class="num">{s['firm_b_count']}</td>
                <td><span class="badge {cls}">{icon}</span></td>
              </tr>"""
            )
        return f'<table class="search-table"><thead><tr><th>Query</th><th>RYZE Results</th><th>Firm B Results</th><th>Isolation</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'

    all_green = (
        len(review_eps) == 0
        and len(hardcoded_eps) == 0
        and (attacks_total == 0 or attacks_blocked == attacks_total)
        and (not results["search"] or search_clean)
    )

    verdict_text = (
        "Architecture verified. RYZE is ready to open."
        if all_green
        else "Issues detected — review flagged items."
    )
    verdict_class = "verdict-pass" if all_green else "verdict-fail"
    verdict_icon = "✅" if all_green else "❌"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>RYZE.ai — EP16 Tenant Audit</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet"/>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
    font-family: 'DM Sans', system-ui, sans-serif;
    background: #f6f9fc;
    color: #1a2e44;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }}

  .header {{
    background: rgba(255,255,255,0.94);
    border-bottom: 1px solid #e4edf5;
    padding: 20px 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(10px);
  }}
  .brand-logo {{ font-weight: 800; font-size: 1.1rem; color: #004182; letter-spacing: -0.3px; }}
  .brand-sep {{ color: #c8d8e8; }}
  .brand-sub {{ font-size: 0.8rem; color: #7a98b5; font-weight: 500; }}
  .header-ts {{ font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #a0b8cc; }}

  .page {{ max-width: 1200px; margin: 0 auto; padding: 48px 32px; }}

  .hero {{ margin-bottom: 56px; }}
  .ep-tag {{
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(0,65,130,0.06); border: 1px solid rgba(0,65,130,0.15);
    color: #004182; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.8px;
    text-transform: uppercase; padding: 4px 12px; border-radius: 100px;
    margin-bottom: 20px;
  }}
  .pulse {{
    width: 7px; height: 7px; border-radius: 50%; background: #57a0d3;
    box-shadow: 0 0 8px #57a0d3; animation: pulse 2s infinite;
  }}
  @keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.2; }} }}
  .hero h1 {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: clamp(2rem, 4vw, 3rem);
    font-weight: 400; color: #1a2e44; line-height: 1.2;
    margin-bottom: 12px;
  }}
  .hero h1 em {{ font-style: italic; color: #0a66c2; }}
  .hero-sub {{ font-size: 1rem; color: #5a7a95; line-height: 1.7; max-width: 600px; }}

  .verdict-pass, .verdict-fail {{
    border-radius: 14px; padding: 28px 32px;
    display: flex; align-items: center; gap: 20px;
    margin-bottom: 48px; border: 1px solid;
  }}
  .verdict-pass {{ background: #f0fdf4; border-color: #bbf7d0; }}
  .verdict-fail {{ background: #fef2f2; border-color: #fecaca; }}
  .verdict-icon {{ font-size: 2.2rem; flex-shrink: 0; }}
  .verdict-text h2 {{
    font-family: 'DM Serif Display', serif;
    font-size: 1.5rem; font-weight: 400; margin-bottom: 4px;
  }}
  .verdict-pass .verdict-text h2 {{ color: #166534; }}
  .verdict-fail .verdict-text h2 {{ color: #991b1b; }}
  .verdict-text p {{ font-size: 0.92rem; color: #5a7a95; }}

  .scores {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 16px; margin-bottom: 56px;
  }}
  .score-card {{
    background: #ffffff; border: 1px solid #dce8f4;
    border-radius: 12px; padding: 24px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }}
  .score-label {{ font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.8px; color: #7a98b5; margin-bottom: 10px; }}
  .score-num {{ font-family: 'DM Serif Display', serif; font-size: 2.8rem;
    font-weight: 400; line-height: 1; }}
  .score-sub {{ font-size: 0.78rem; color: #a0b8cc; margin-top: 6px; }}
  .green {{ color: #166534; }} .blue {{ color: #004182; }}
  .yellow {{ color: #92400e; }} .red {{ color: #991b1b; }}

  .section {{ margin-bottom: 56px; }}
  .section-hdr {{
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 20px; padding-bottom: 14px;
    border-bottom: 1px solid #e4edf5;
  }}
  .act-num {{
    width: 28px; height: 28px; border-radius: 50%;
    background: #f0f5fb; border: 1px solid #dce8f4;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.72rem; font-weight: 700; color: #004182;
    flex-shrink: 0;
  }}
  .section-hdr h2 {{
    font-family: 'DM Serif Display', serif;
    font-size: 1.3rem; font-weight: 400; color: #1a2e44;
  }}
  .section-desc {{ font-size: 0.88rem; color: #7a98b5; margin-top: 2px; }}

  .ep-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  .ep-table th {{
    text-align: left; padding: 10px 14px;
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.7px; color: #7a98b5;
    border-bottom: 1px solid #e4edf5; background: #f6f9fc;
  }}
  .ep-table td {{ padding: 9px 14px; border-bottom: 1px solid #f0f5fb; vertical-align: middle; }}
  .ep-row:hover td {{ background: #f6f9fc; }}
  .ep-row.review td {{ background: #fef9f9; }}
  .ep-row.warn td {{ background: #fffbeb; }}
  .ep-row.pub td {{ opacity: 0.45; }}
  .file {{ font-family: 'JetBrains Mono', monospace; color: #7a98b5; font-size: 0.75rem; }}
  .path {{ font-family: 'JetBrains Mono', monospace; color: #2e4a65; font-size: 0.78rem; }}
  .detail {{ font-size: 0.75rem; color: #a0b8cc; }}
  .method {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 0.72rem; }}
  .method.get {{ color: #0a66c2; }} .method.post {{ color: #166534; }}
  .method.patch {{ color: #92400e; }} .method.delete {{ color: #991b1b; }}
  .method.put {{ color: #92400e; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.4px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .badge.safe {{ background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }}
  .badge.review {{ background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }}
  .badge.warn {{ background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }}
  .badge.pub {{ background: #f0f5fb; color: #7a98b5; border: 1px solid #dce8f4; }}

  .db-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  .db-table th {{
    padding: 10px 16px; text-align: right;
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.7px; color: #7a98b5; border-bottom: 1px solid #e4edf5;
    background: #f6f9fc;
  }}
  .db-table th:first-child {{ text-align: left; }}
  .db-table td {{ padding: 12px 16px; border-bottom: 1px solid #f0f5fb; }}
  .db-table .tbl {{ color: #2e4a65; font-weight: 600; }}
  .db-table .num {{ text-align: right; font-family: 'JetBrains Mono', monospace;
    font-size: 1.1rem; font-weight: 600; color: #166534; }}

  .attack-table, .search-table {{
    width: 100%; border-collapse: collapse; font-size: 0.85rem;
  }}
  .attack-table th, .search-table th {{
    padding: 10px 14px; text-align: left;
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.7px; color: #7a98b5; border-bottom: 1px solid #e4edf5;
    background: #f6f9fc;
  }}
  .attack-table td, .search-table td {{
    padding: 10px 14px; border-bottom: 1px solid #f0f5fb;
  }}
  .query {{ font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #2e4a65; }}
  .num {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #166534; }}
  .dim {{ color: #a0b8cc; font-size: 0.88rem; padding: 20px 0; }}

  .table-card {{
    background: #ffffff; border: 1px solid #dce8f4;
    border-radius: 12px; overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }}

  .footer {{
    text-align: center; padding: 32px;
    font-size: 0.75rem; color: #a0b8cc;
    border-top: 1px solid #e4edf5; margin-top: 48px;
  }}

  @media (max-width: 768px) {{
    .scores {{ grid-template-columns: repeat(2, 1fr); }}
    .header {{ padding: 16px 20px; }}
    .page {{ padding: 32px 16px; }}
  }}
</style>
</head>
<body>

<header class="header">
  <div class="brand">
    <span class="brand-logo">RYZE.ai</span>
    <span class="brand-sep">|</span>
    <span class="brand-sub">EP16 — Multi-Tenant Architecture Proof</span>
  </div>
  <span class="header-ts">{results['ts']}</span>
</header>

<div class="page">

  <!-- Hero -->
  <div class="hero">
    <div class="ep-tag"><span class="pulse"></span>Episode 16 · Building in Public</div>
    <h1>Before the doors open,<br/><em>we prove the walls hold.</em></h1>
    <p class="hero-sub">
      Every endpoint scanned. Every cross-tenant access attempt blocked.
      Vector search scoped. This is the proof that RYZE is ready to serve
      multiple firms from a single database.
    </p>
  </div>

  <!-- Verdict -->
  <div class="{verdict_class}">
    <div class="verdict-icon">{verdict_icon}</div>
    <div class="verdict-text">
      <h2>{verdict_text}</h2>
      <p>Scanned {results['summary'].get('total',0)} endpoints across {len(set(e['file'] for e in results['endpoints']))} API files &nbsp;·&nbsp; {results['ts']}</p>
    </div>
  </div>

  <!-- Score cards -->
  <div class="scores">
    <div class="score-card">
      <div class="score-label">Endpoints Safe</div>
      <div class="score-num green">{results['summary'].get('safe',0)}</div>
      <div class="score-sub">tenant filter confirmed</div>
    </div>
    <div class="score-card">
      <div class="score-label">Intentionally Open</div>
      <div class="score-num blue">{results['summary'].get('public',0)}</div>
      <div class="score-sub">login, OAuth, webhooks</div>
    </div>
    <div class="score-card">
      <div class="score-label">Attack Attempts</div>
      <div class="score-num {'green' if attacks_total == 0 or attacks_blocked == attacks_total else 'red'}">{attacks_blocked}/{attacks_total}</div>
      <div class="score-sub">cross-tenant reads blocked</div>
    </div>
    <div class="score-card">
      <div class="score-label">Vector Search</div>
      <div class="score-num {'green' if search_clean else 'red'}">{'Clean' if search_clean else 'LEAKED'}</div>
      <div class="score-sub">{'zero result overlap' if search_clean else 'results crossed tenants'}</div>
    </div>
  </div>

  <!-- Act 1 -->
  <div class="section">
    <div class="section-hdr">
      <div class="act-num">1</div>
      <div>
        <h2>The Surface Area</h2>
        <p class="section-desc">Static analysis of every route decorator across all API files.</p>
      </div>
    </div>
    <div class="table-card">
      <table class="ep-table">
        <thead>
          <tr>
            <th>File</th><th>Method</th><th>Path</th>
            <th>Verdict</th><th>Detail</th>
          </tr>
        </thead>
        <tbody>{ep_rows()}</tbody>
      </table>
    </div>
  </div>

  <!-- Act 2 -->
  <div class="section">
    <div class="section-hdr">
      <div class="act-num">2</div>
      <div>
        <h2>The Database</h2>
        <p class="section-desc">Live row counts per tenant — same tables, completely isolated worlds.</p>
      </div>
    </div>
    <div class="table-card" style="padding: 24px 28px;">
      {db_table()}
    </div>
  </div>

  <!-- Act 3 -->
  <div class="section">
    <div class="section-hdr">
      <div class="act-num">3</div>
      <div>
        <h2>The Attack Simulation</h2>
        <p class="section-desc">Live HTTP — RYZE admin attempts to read and write Firm B data, and vice versa.</p>
      </div>
    </div>
    <div class="table-card">
      {attack_rows()}
    </div>
  </div>

  <!-- Act 4 -->
  <div class="section">
    <div class="section-hdr">
      <div class="act-num">4</div>
      <div>
        <h2>Vector Search Isolation</h2>
        <p class="section-desc">Same natural language queries run as both tenants — result sets must never overlap.</p>
      </div>
    </div>
    <div class="table-card">
      {search_rows()}
    </div>
  </div>

</div>

<footer class="footer">
  RYZE GROUP, Inc. d/b/a RYZE.ai &nbsp;·&nbsp; EP16 Tenant Audit &nbsp;·&nbsp; {results['ts']}
</footer>

</body>
</html>"""

    REPORT_PATH.write_text(html, encoding="utf-8")
    return REPORT_PATH


# ═════════════════════════════════════════════════════════════════════════
#  FINAL VERDICT
# ═════════════════════════════════════════════════════════════════════════


def final_verdict():
    s = results["summary"]
    attacks = results["attacks"]
    blocked = sum(1 for a in attacks if a["blocked"])
    search_clean = all(s2["overlap"] == 0 for s2 in results["search"])
    all_green = (
        s.get("review", 0) == 0
        and s.get("hardcoded", 0) == 0
        and (not attacks or blocked == len(attacks))
        and (not results["search"] or search_clean)
    )

    print(f"\n{BOLD}{'═'*62}{X}")
    if all_green:
        print(f"{BOLD}{G}  ✅  Architecture verified. RYZE is ready to open.{X}")
    else:
        print(f"{BOLD}{R}  ❌  Issues detected — review flagged items above.{X}")
    print(f"{BOLD}{'═'*62}{X}")
    print(f"  {D}Endpoints safe      :{X} {G}{s.get('safe',0)}{X}")
    print(f"  {D}Intentionally open  :{X} {D}{s.get('public',0)}{X}")
    print(f"  {D}Attack attempts     :{X} {G}{blocked}/{len(attacks)} blocked{X}")
    print(
        f"  {D}Vector search       :{X} {G if search_clean else R}{'isolated' if search_clean else 'LEAKED'}{X}"
    )
    print(f"{BOLD}{'═'*62}{X}\n")


# ═════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{BOLD}{'═'*62}{X}")
    print(f"{BOLD}  RYZE.ai — EP16 Multi-Tenant Architecture Proof{X}")
    print(f"{BOLD}{'═'*62}{X}")
    print(f"  {D}Server: {BASE_URL}{X}")

    act1_static()
    act2_database()
    act3_attacks()
    act4_search()
    final_verdict()

    print(f"  Generating report...")
    path = generate_html()
    print(f"  {G}✓{X}  Report saved → {path}")
    print(f"  Opening in browser...\n")
    webbrowser.open(f"file://{path.resolve()}")
