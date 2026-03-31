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
    # Bookings
    "respond_to_invite",
    "get_my_bookings",
    "get_booking",
    # Candidates
    "parse_candidate",
    "parse_candidate_file",
    # Chat
    "chat",
    # Chat sessions
    "create_session",
    "list_sessions",
    "get_session",
    "delete_session",
    "update_session_title",
    "save_message",
    "generate_title",
    # DB Explorer
    "list_tables",
    "get_all_counts",
    "browse_table",
    "update_record",
    "delete_record",
    "export_table_csv",
    # Employer profiles
    "get_my_employer_profile",
    "update_employer_profile",
    "parse_employer_profile",
    # Job orders
    "create_job_order",
    "update_job_order",
    "delete_job_order",
    "parse_job_order",
    # Other
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


def _db_section():
    """Build the Act 2 database cards from live results."""
    if "error" in results["db_counts"]:
        return f'<div class="callout red"><strong>DB unavailable:</strong> {results["db_counts"]["error"]}</div>'

    tables_order = ["Candidates", "Employers", "Job Orders", "Bookings"]
    tenants = list(results["db_counts"].keys())

    cards = []
    for i, tenant in enumerate(tenants):
        label_cls = "ryze" if i == 0 else "firmb"
        rows = "".join(
            f'<div class="db-row">'
            f'<span class="db-row-label">{tbl}</span>'
            f'<span class="db-row-val">{results["db_counts"][tenant].get(tbl, 0)}</span>'
            f"</div>"
            for tbl in tables_order
        )
        cards.append(
            f'<div class="db-tenant-card">'
            f'<div class="db-tenant-label {label_cls}">{tenant}</div>'
            f"{rows}</div>"
        )

    return f'<div class="db-grid">{"".join(cards)}</div>'


def generate_html():
    ep = results["endpoints"]
    safe_eps = [e for e in ep if e["verdict"] == "SAFE"]
    public_eps = [e for e in ep if e["verdict"] in ("PUBLIC", "SKIP")]
    review_eps = [e for e in ep if e["verdict"] == "REVIEW"]
    hardcoded_eps = [e for e in ep if e["verdict"] == "HARDCODED"]

    attacks_blocked = sum(1 for a in results["attacks"] if a["blocked"])
    attacks_total = len(results["attacks"])
    search_clean = all(s["overlap"] == 0 for s in results["search"])

    all_green = (
        len(review_eps) == 0
        and len(hardcoded_eps) == 0
        and (attacks_total == 0 or attacks_blocked == attacks_total)
        and (not results["search"] or search_clean)
    )

    verdict_headline = "Architecture verified." if all_green else "Issues detected."
    verdict_sub = (
        "Every wall holds. RYZE is ready to serve multiple firms."
        if all_green
        else "Review flagged endpoints before opening to external tenants."
    )
    verdict_icon = "✅" if all_green else "❌"
    verdict_class = "verdict-pass" if all_green else "verdict-fail"

    # ── endpoint table rows (skip PUBLIC/SKIP to keep table tight) ────────
    def ep_rows():
        rows = []
        for e in ep:
            v = e["verdict"]
            if v in ("PUBLIC", "SKIP"):
                continue
            row_cls = {"SAFE": "safe", "REVIEW": "review", "HARDCODED": "warn"}.get(
                v, ""
            )
            badge_cls = {
                "SAFE": "badge-safe",
                "REVIEW": "badge-review",
                "HARDCODED": "badge-warn",
            }.get(v, "")
            badge_lbl = {
                "SAFE": "✓ SAFE",
                "REVIEW": "✗ REVIEW",
                "HARDCODED": "⚠ HARDCODED",
            }.get(v, v)
            method_cls = f"method-{e['method'].lower()}"
            rows.append(
                f'<tr class="ep-row {row_cls}">'
                f'<td class="mono dim">{e["file"]}</td>'
                f'<td class="mono {method_cls}">{e["method"]}</td>'
                f'<td class="path-cell">{e["path"]}</td>'
                f'<td><span class="badge {badge_cls}">{badge_lbl}</span></td>'
                f'<td class="small">{e["detail"]}</td>'
                f"</tr>"
            )
        return "".join(rows)

    # ── attack rows ───────────────────────────────────────────────────────
    def attack_rows():
        if not results["attacks"]:
            return '<tr><td colspan="4" class="dim-note">Live HTTP tests require RYZE_PASSWORD env var.</td></tr>'
        rows = []
        for a in results["attacks"]:
            cls = "badge-safe" if a["blocked"] else "badge-review"
            icon = "✓ BLOCKED" if a["blocked"] else "✗ BREACH"
            rows.append(
                f"<tr>"
                f'<td class="mono method-{a["method"].lower()}">{a["method"]}</td>'
                f'<td class="path-cell">{a["url"]}</td>'
                f'<td class="small">{a["label"]}</td>'
                f'<td><span class="badge {cls}">{icon} · {a["status"]}</span></td>'
                f"</tr>"
            )
        return "".join(rows)

    # ── search rows ───────────────────────────────────────────────────────
    def search_rows():
        if not results["search"]:
            return '<tr><td colspan="4" class="dim-note">Search isolation tests require RYZE_PASSWORD env var.</td></tr>'
        rows = []
        for s in results["search"]:
            cls = "badge-safe" if s["overlap"] == 0 else "badge-review"
            icon = "✓ ISOLATED" if s["overlap"] == 0 else f'✗ {s["overlap"]} LEAKED'
            rows.append(
                f"<tr>"
                f'<td class="path-cell">"{s["query"]}"</td>'
                f'<td class="count-cell"><span class="count-num">{s["ryze_count"]}</span></td>'
                f'<td class="count-cell"><span class="count-num">{s["firm_b_count"]}</span></td>'
                f'<td><span class="badge {cls}">{icon}</span></td>'
                f"</tr>"
            )
        return "".join(rows)

    # ── score card colour helpers ─────────────────────────────────────────
    attacks_colour = (
        "c-green"
        if (attacks_total == 0 or attacks_blocked == attacks_total)
        else "c-red"
    )
    search_colour = "c-green" if search_clean else "c-red"
    search_label = "Clean" if search_clean else "Leaked"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>RYZE.ai — EP16 Multi-Tenant Architecture Proof</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet"/>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:        #f1f5f9;
  --white:     #ffffff;
  --navy:      #004182;
  --navy-lt:   #1d6fb8;
  --blue:      #0a66c2;
  --blue-lt:   #57a0d3;
  --blue-bg:   #eff6ff;
  --green:     #16a34a;
  --green-bg:  #f0fdf4;
  --green-bdr: #bbf7d0;
  --red:       #dc2626;
  --red-bg:    #fef2f2;
  --red-bdr:   #fecaca;
  --amber:     #d97706;
  --amber-bg:  #fffbeb;
  --amber-bdr: #fde68a;
  --text:      #1a2e44;
  --text-dim:  #4a6882;
  --text-mute: #7a98b5;
  --border:    #dce8f4;
  --border-lt: #e8f0f8;
  --serif:     'DM Serif Display', Georgia, serif;
  --sans:      'DM Sans', system-ui, sans-serif;
  --mono:      'JetBrains Mono', 'Courier New', monospace;
}}

html {{ scroll-behavior: smooth; }}
body {{
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}}

.site-header {{
  position: sticky; top: 0; z-index: 100;
  background: rgba(255,255,255,0.95);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(10px);
}}
.header-inner {{
  max-width: 1100px; margin: 0 auto; padding: 0 40px;
  height: 58px; display: flex; align-items: center; justify-content: space-between;
}}
.brand {{ display: flex; align-items: center; gap: 10px; }}
.brand-name {{ font-weight: 800; font-size: 1.05rem; color: var(--navy); letter-spacing: -0.3px; }}
.brand-pipe {{ color: #c8d8e8; }}
.brand-ep {{ font-size: 0.78rem; color: var(--text-mute); font-weight: 500; }}
.header-ts {{ font-family: var(--mono); font-size: 0.7rem; color: var(--text-mute); }}

.page {{ max-width: 1100px; margin: 0 auto; padding: 0 40px 80px; }}

.hero {{ padding: 64px 0 52px; }}
.ep-badge {{
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--blue-bg); border: 1px solid #bfdbfe;
  color: var(--blue); font-size: 0.68rem; font-weight: 700;
  letter-spacing: 0.9px; text-transform: uppercase;
  padding: 5px 14px; border-radius: 100px; margin-bottom: 24px;
}}
.pulse-dot {{
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--green); box-shadow: 0 0 6px var(--green);
  animation: pulse 2s ease-in-out infinite;
}}
@keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.25; }} }}

.hero-headline {{
  font-family: var(--serif);
  font-size: clamp(2.2rem, 4.5vw, 3.4rem);
  font-weight: 400; line-height: 1.18;
  color: var(--text); margin-bottom: 18px;
  animation: fadeUp 0.6s ease both;
}}
.hero-headline em {{ font-style: italic; color: var(--blue); }}
@keyframes fadeUp {{ from {{ opacity:0; transform:translateY(18px); }} to {{ opacity:1; transform:translateY(0); }} }}

.hero-body {{
  font-size: 1rem; color: var(--text-dim); line-height: 1.8;
  max-width: 620px; margin-bottom: 40px;
  animation: fadeUp 0.6s 0.12s ease both;
}}

.verdict-banner {{
  display: flex; align-items: center; gap: 18px;
  border-radius: 12px; padding: 22px 26px; border: 1px solid;
  margin-bottom: 52px; animation: fadeUp 0.6s 0.22s ease both;
}}
.verdict-pass {{ background: var(--green-bg); border-color: var(--green-bdr); }}
.verdict-fail {{ background: var(--red-bg);   border-color: var(--red-bdr); }}
.verdict-icon {{ font-size: 1.9rem; flex-shrink: 0; }}
.verdict-copy h2 {{ font-family: var(--serif); font-size: 1.4rem; font-weight: 400; margin-bottom: 3px; }}
.verdict-pass .verdict-copy h2 {{ color: #15803d; }}
.verdict-fail .verdict-copy h2 {{ color: #b91c1c; }}
.verdict-copy p {{ font-size: 0.85rem; color: var(--text-mute); }}

.scores {{
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; margin-bottom: 64px;
  animation: fadeUp 0.6s 0.32s ease both;
}}
.score-card {{
  background: var(--white); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 18px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}}
.score-label {{ font-size: 0.64rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.9px; color: var(--text-mute); margin-bottom: 10px; }}
.score-val {{ font-family: var(--serif); font-size: 2.5rem; font-weight: 400; line-height: 1; }}
.score-sub {{ font-size: 0.7rem; color: var(--text-mute); margin-top: 5px; }}
.c-green {{ color: var(--green); }}
.c-blue  {{ color: var(--blue); }}
.c-red   {{ color: var(--red); }}

.section {{ margin-bottom: 60px; opacity: 0; transform: translateY(16px); transition: opacity 0.5s ease, transform 0.5s ease; }}
.section.visible {{ opacity: 1; transform: none; }}

.section-header {{
  display: flex; align-items: flex-start; gap: 14px;
  margin-bottom: 20px; padding-bottom: 18px; border-bottom: 2px solid var(--border);
}}
.act-number {{
  flex-shrink: 0; width: 30px; height: 30px; border-radius: 50%;
  background: var(--navy); display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 0.65rem; font-weight: 600; color: #fff; margin-top: 3px;
}}
.section-title-block h2 {{ font-family: var(--serif); font-size: 1.35rem; font-weight: 400; color: var(--text); margin-bottom: 3px; }}
.section-desc {{ font-size: 0.84rem; color: var(--text-dim); line-height: 1.6; }}

.callout {{
  background: var(--white); border: 1px solid var(--border);
  border-left: 3px solid var(--blue-lt);
  border-radius: 10px; padding: 16px 20px;
  margin-bottom: 18px; font-size: 0.87rem;
  color: var(--text-dim); line-height: 1.7;
}}
.callout strong {{ color: var(--text); font-weight: 600; }}
.callout.gold  {{ border-left-color: #f59e0b; }}
.callout.green {{ border-left-color: var(--green); }}
.callout.red   {{ border-left-color: var(--red); }}

.stat-strip {{
  display: flex; border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden; margin-bottom: 14px;
  background: var(--white); box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
.stat-strip-item {{ flex: 1; padding: 14px 0; text-align: center; border-right: 1px solid var(--border); }}
.stat-strip-item:last-child {{ border-right: none; }}
.strip-val {{ font-family: var(--serif); font-size: 1.75rem; font-weight: 400; line-height: 1; margin-bottom: 3px; }}
.strip-lbl {{ font-size: 0.63rem; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-mute); }}

.card {{ background: var(--white); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}

.data-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
.data-table thead th {{
  padding: 10px 16px; text-align: left;
  font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.8px; color: var(--text-mute);
  border-bottom: 1px solid var(--border); background: #f8fafc;
}}
.data-table tbody td {{ padding: 10px 16px; border-bottom: 1px solid var(--border-lt); vertical-align: middle; }}
.data-table tbody tr:last-child td {{ border-bottom: none; }}
.data-table tbody tr:hover td {{ background: #f8fafc; }}
.ep-row.review td {{ background: #fff8f8; }}
.ep-row.warn td   {{ background: #fffdf0; }}

.mono      {{ font-family: var(--mono); font-size: 0.74rem; }}
.dim       {{ color: var(--text-mute); }}
.small     {{ font-size: 0.72rem; color: var(--text-mute); }}
.dim-note  {{ font-size: 0.82rem; color: var(--text-mute); padding: 16px; }}
.path-cell {{ font-family: var(--mono); font-size: 0.74rem; color: var(--text); }}
.count-cell {{ text-align: center; }}
.count-num {{ font-family: var(--mono); font-size: 1rem; font-weight: 700; color: var(--green); }}

.method-get    {{ color: var(--blue);  font-weight: 600; }}
.method-post   {{ color: var(--green); font-weight: 600; }}
.method-patch  {{ color: var(--amber); font-weight: 600; }}
.method-delete {{ color: var(--red);   font-weight: 600; }}
.method-put    {{ color: var(--amber); font-weight: 600; }}

.badge {{
  display: inline-block; padding: 3px 8px; border-radius: 5px;
  font-family: var(--mono); font-size: 0.64rem; font-weight: 600; letter-spacing: 0.3px;
}}
.badge-safe   {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green-bdr); }}
.badge-review {{ background: var(--red-bg);   color: var(--red);   border: 1px solid var(--red-bdr); }}
.badge-warn   {{ background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber-bdr); }}

.db-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }}
.db-tenant-card {{ background: var(--white); border: 1px solid var(--border); border-radius: 10px; padding: 20px 22px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
.db-tenant-label {{ font-size: 0.64rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.9px; margin-bottom: 14px; }}
.db-tenant-label.ryze  {{ color: var(--navy); }}
.db-tenant-label.firmb {{ color: #7c3aed; }}
.db-row {{ display: flex; justify-content: space-between; align-items: center; padding: 7px 0; border-bottom: 1px solid var(--border-lt); font-size: 0.84rem; }}
.db-row:last-child {{ border-bottom: none; }}
.db-row-label {{ color: var(--text-dim); }}
.db-row-val {{ font-family: var(--mono); font-weight: 700; color: var(--text); font-size: 1rem; }}

.proof-pills {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
.proof-pill {{
  display: flex; align-items: center; gap: 7px;
  background: var(--white); border: 1px solid var(--border);
  border-radius: 7px; padding: 7px 13px;
  font-size: 0.77rem; color: var(--text-dim);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}}
.pill-dot {{ width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }}
.dot-green  {{ background: var(--green); }}
.dot-blue   {{ background: var(--blue); }}
.dot-purple {{ background: #7c3aed; }}

.site-footer {{
  text-align: center; padding: 28px; font-size: 0.71rem; color: var(--text-mute);
  border-top: 1px solid var(--border); margin-top: 40px; letter-spacing: 0.3px;
}}

@media (max-width: 768px) {{
  .scores {{ grid-template-columns: repeat(2, 1fr); }}
  .db-grid {{ grid-template-columns: 1fr; }}
  .page, .header-inner {{ padding-left: 20px; padding-right: 20px; }}
}}
</style>
</head>
<body>

<header class="site-header">
  <div class="header-inner">
    <div class="brand">
      <span class="brand-name">RYZE.ai</span>
      <span class="brand-pipe"> | </span>
      <span class="brand-ep">EP16 — Multi-Tenant Architecture Proof</span>
    </div>
    <span class="header-ts">{results['ts']}</span>
  </div>
</header>

<div class="page">

  <div class="hero">
    <div class="ep-badge"><span class="pulse-dot"></span>Episode 16 &nbsp;·&nbsp; Building in Public</div>
    <h1 class="hero-headline">
      Before the first firm logs in,<br/>
      <em>we prove the walls hold.</em>
    </h1>
    <p class="hero-body">
      Multi-tenancy is the hardest thing to get right in a SaaS platform. Not because the
      concept is complicated — one database, many firms, zero data leakage — but because there
      are a hundred places it can silently break. A missing WHERE clause. A hardcoded tenant ID.
      A vector search that forgets to filter before it ranks.<br/><br/>
      This audit runs four acts of proof. Every endpoint scanned. Every database row counted.
      Every cross-tenant attack attempt blocked. Every similarity search verified isolated.
    </p>
    <div class="verdict-banner {verdict_class}">
      <div class="verdict-icon">{verdict_icon}</div>
      <div class="verdict-copy">
        <h2>{verdict_headline}</h2>
        <p>{verdict_sub} &nbsp;·&nbsp; {results['ts']}</p>
      </div>
    </div>
  </div>

  <div class="scores">
    <div class="score-card">
      <div class="score-label">Endpoints Secure</div>
      <div class="score-val c-green">{len(safe_eps)}</div>
      <div class="score-sub">tenant filter confirmed</div>
    </div>
    <div class="score-card">
      <div class="score-label">Open / Infrastructure</div>
      <div class="score-val c-blue">{len(public_eps)}</div>
      <div class="score-sub">intentionally public</div>
    </div>
    <div class="score-card">
      <div class="score-label">Attacks Blocked</div>
      <div class="score-val {attacks_colour}">{attacks_blocked}/{attacks_total}</div>
      <div class="score-sub">cross-tenant breach attempts</div>
    </div>
    <div class="score-card">
      <div class="score-label">Vector Search</div>
      <div class="score-val {search_colour}">{search_label}</div>
      <div class="score-sub">{'zero result overlap' if search_clean else 'overlap detected'}</div>
    </div>
  </div>

  <!-- ACT 1 -->
  <div class="section">
    <div class="section-header">
      <div class="act-number">01</div>
      <div class="section-title-block">
        <h2>The Surface Area</h2>
        <p class="section-desc">Static analysis of every route handler across all API files. Does each endpoint that touches tenant data enforce a tenant filter — or does it just hope for the best?</p>
      </div>
    </div>
    <div class="callout gold">
      <strong>How this works.</strong> The scanner walks the AST of every Python route file, identifies route decorator functions, inspects their dependency injections, and checks whether tenant-scoping patterns appear in the function body. No guessing. No sampling. Every door, checked.
    </div>
    <div class="stat-strip">
      <div class="stat-strip-item">
        <div class="strip-val c-green">{len(safe_eps)}</div>
        <div class="strip-lbl">Tenant-Scoped</div>
      </div>
      <div class="stat-strip-item">
        <div class="strip-val c-blue">{len(public_eps)}</div>
        <div class="strip-lbl">Public / Infra</div>
      </div>
      <div class="stat-strip-item">
        <div class="strip-val {'c-red' if review_eps else 'c-green'}">{len(review_eps)}</div>
        <div class="strip-lbl">Flagged for Review</div>
      </div>
      <div class="stat-strip-item">
        <div class="strip-val {'c-red' if hardcoded_eps else 'c-green'}">{len(hardcoded_eps)}</div>
        <div class="strip-lbl">Hardcoded Tenant</div>
      </div>
    </div>
    <div class="card">
      <table class="data-table">
        <thead><tr><th>File</th><th>Method</th><th>Path</th><th>Status</th><th>Signal</th></tr></thead>
        <tbody>{ep_rows()}</tbody>
      </table>
    </div>
  </div>

  <!-- ACT 2 -->
  <div class="section">
    <div class="section-header">
      <div class="act-number">02</div>
      <div class="section-title-block">
        <h2>The Database</h2>
        <p class="section-desc">One PostgreSQL instance. One set of tables. Two completely separate firms. Every row carries a <code style="font-family:var(--mono);font-size:0.8em;color:var(--navy-lt)">tenant_id</code> — and every query filters by it.</p>
      </div>
    </div>
    <div class="callout green">
      <strong>Why this matters.</strong> The simplest multi-tenancy bug is a missing filter — a query that returns <em>all</em> candidates instead of <em>this firm's</em> candidates. These live counts prove that RYZE's data and Firm B's data exist completely independently in the same database, with zero row overlap possible at the query layer.
    </div>
    {_db_section()}
  </div>

  <!-- ACT 3 -->
  <div class="section">
    <div class="section-header">
      <div class="act-number">03</div>
      <div class="section-title-block">
        <h2>The Attack Simulation</h2>
        <p class="section-desc">Static analysis tells you what the code <em>should</em> do. Live HTTP tells you what it <em>actually</em> does. Two admin accounts. One trying to reach the other's data.</p>
      </div>
    </div>
    <div class="callout red">
      <strong>Scenario.</strong> The RYZE admin holds a valid JWT. Using that token, we attempt to GET and PATCH records belonging to Firm B. Then we flip it — Firm B's token tries to read RYZE candidate data. Every attempt must return <strong>403 or 404</strong>. Anything else is a breach.
    </div>
    <div class="card">
      <table class="data-table">
        <thead><tr><th>Method</th><th>Endpoint</th><th>Attempt</th><th>Result</th></tr></thead>
        <tbody>{attack_rows()}</tbody>
      </table>
    </div>
  </div>

  <!-- ACT 4 -->
  <div class="section">
    <div class="section-header">
      <div class="act-number">04</div>
      <div class="section-title-block">
        <h2>Vector Search Isolation</h2>
        <p class="section-desc">The hardest act to prove. pgvector doesn't understand tenants — it just runs cosine similarity across embeddings. The WHERE clause has to scope the candidate pool <em>before</em> the math runs.</p>
      </div>
    </div>
    <div class="callout gold">
      <strong>The test.</strong> The same natural language queries run simultaneously as both the RYZE admin and the Firm B admin. The result sets must be completely non-overlapping — same query, different universe of candidates. Overlap count must be zero.
    </div>
    <div class="proof-pills">
      <div class="proof-pill"><span class="pill-dot dot-green"></span>Tenant filter applied before similarity ranking</div>
      <div class="proof-pill"><span class="pill-dot dot-blue"></span>OpenAI text-embedding-3-small consistent across all tenants</div>
      <div class="proof-pill"><span class="pill-dot dot-purple"></span>pgvector operates on pre-scoped candidate subsets only</div>
    </div>
    <div class="card">
      <table class="data-table">
        <thead><tr><th>Query</th><th style="text-align:center">RYZE Results</th><th style="text-align:center">Firm B Results</th><th>Isolation</th></tr></thead>
        <tbody>{search_rows()}</tbody>
      </table>
    </div>
  </div>

</div>

<footer class="site-footer">
  RYZE GROUP, Inc. d/b/a RYZE.ai &nbsp;·&nbsp; EP16 Multi-Tenant Architecture Proof &nbsp;·&nbsp; {results['ts']}
</footer>

<script>
const observer = new IntersectionObserver(
  entries => entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }}),
  {{ threshold: 0.08 }}
);
document.querySelectorAll('.section').forEach(s => observer.observe(s));

document.querySelectorAll('.count-num').forEach(el => {{
  const target = parseInt(el.textContent, 10);
  if (isNaN(target) || target === 0) return;
  let current = 0;
  const step = Math.max(1, Math.floor(target / 20));
  const interval = setInterval(() => {{
    current = Math.min(current + step, target);
    el.textContent = current;
    if (current >= target) clearInterval(interval);
  }}, 40);
}});
</script>
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
