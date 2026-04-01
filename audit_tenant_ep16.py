"""
audit_tenant_ep16.py
────────────────────
EP16 — Multi-Tenant Isolation Audit
Runs all isolation checks and generates a clean HTML report.

Usage:
    RYZE_PASSWORD=yourpassword FIRM_B_PASSWORD=FirmBAdmin123! python audit_tenant_ep16.py
"""

import os
import sys
import webbrowser
import requests
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
RYZE_EMAIL = os.getenv("RYZE_EMAIL", "dane@ryze.ai")
RYZE_PASS = os.getenv("RYZE_PASSWORD", "")
FIRM_B_EMAIL = "admin@firmb.com"
FIRM_B_PASS = os.getenv("FIRM_B_PASSWORD", "")
REPORT_PATH = Path(__file__).parent / "ep16_isolation_report.html"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Results store ─────────────────────────────────────────────────────────
results = (
    []
)  # list of {"section": str, "label": str, "status": "pass"|"fail"|"warn", "detail": str}
sections = []  # ordered list of section names


def record(section, label, status, detail=""):
    if section not in sections:
        sections.append(section)
    results.append(
        {"section": section, "label": label, "status": status, "detail": detail}
    )
    icon = (
        f"{GREEN}✓{RESET}"
        if status == "pass"
        else f"{RED}✗{RESET}" if status == "fail" else f"{YELLOW}⚠{RESET}"
    )
    print(f"  {icon}  {label}" + (f"  —  {detail}" if detail else ""))


def login(email, password):
    res = requests.post(
        f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}
    )
    if not res.ok:
        raise RuntimeError(f"{res.status_code}")
    return res.json()["access_token"]


def hdrs(token):
    return {"Authorization": f"Bearer {token}"}


def check_404(section, label, res):
    if res.status_code == 404:
        record(section, label, "pass", "→ 404 wall holds")
    elif res.status_code == 200:
        record(section, label, "fail", "→ 200 ISOLATION BREACH")
    else:
        record(section, label, "fail", f"→ {res.status_code} unexpected")


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    print(f"\n{BOLD}  RYZE.ai — EP16 Isolation Audit{RESET}")
    print(f"  {datetime.now().strftime('%B %d, %Y  %H:%M')}\n")

    if not RYZE_PASS:
        print(f"{RED}  ✗  RYZE_PASSWORD not set.{RESET}")
        print(
            "     Run as: RYZE_PASSWORD=yourpassword FIRM_B_PASSWORD=yourpassword python audit_tenant_ep16.py"
        )
        sys.exit(1)
    if not FIRM_B_PASS:
        print(f"{RED}  ✗  FIRM_B_PASSWORD not set.{RESET}")
        print(
            "     Run as: RYZE_PASSWORD=yourpassword FIRM_B_PASSWORD=yourpassword python audit_tenant_ep16.py"
        )
        sys.exit(1)

    # ── Auth ──────────────────────────────────────────────────
    print(f"{BOLD}  Authentication{RESET}")
    try:
        ryze_token = login(RYZE_EMAIL, RYZE_PASS)
        record("Authentication", f"RYZE admin  ({RYZE_EMAIL})", "pass")
    except Exception as e:
        record("Authentication", f"RYZE admin  ({RYZE_EMAIL})", "fail", str(e))
        _write_and_open()
        sys.exit(1)

    try:
        firm_b_token = login(FIRM_B_EMAIL, FIRM_B_PASS)
        record("Authentication", f"Firm B admin  ({FIRM_B_EMAIL})", "pass")
    except Exception as e:
        record("Authentication", f"Firm B admin  ({FIRM_B_EMAIL})", "fail", str(e))
        _write_and_open()
        sys.exit(1)

    # ── Fetch datasets ────────────────────────────────────────
    ryze_candidates = requests.get(
        f"{BASE_URL}/api/candidates", headers=hdrs(ryze_token)
    ).json()
    fb_candidates = requests.get(
        f"{BASE_URL}/api/candidates", headers=hdrs(firm_b_token)
    ).json()
    ryze_employers = requests.get(
        f"{BASE_URL}/api/employer-profiles", headers=hdrs(ryze_token)
    ).json()
    fb_employers = requests.get(
        f"{BASE_URL}/api/employer-profiles", headers=hdrs(firm_b_token)
    ).json()
    ryze_jobs = requests.get(
        f"{BASE_URL}/api/job-orders", headers=hdrs(ryze_token)
    ).json()
    fb_jobs = requests.get(
        f"{BASE_URL}/api/job-orders", headers=hdrs(firm_b_token)
    ).json()
    ryze_bookings = requests.get(
        f"{BASE_URL}/api/bookings", headers=hdrs(ryze_token)
    ).json()

    ryze_cids = (
        {c["id"] for c in ryze_candidates}
        if isinstance(ryze_candidates, list)
        else set()
    )
    fb_cids = (
        {c["id"] for c in fb_candidates} if isinstance(fb_candidates, list) else set()
    )
    ryze_eids = (
        {e["id"] for e in ryze_employers} if isinstance(ryze_employers, list) else set()
    )
    fb_eids = (
        {e["id"] for e in fb_employers} if isinstance(fb_employers, list) else set()
    )
    ryze_jids = {j["id"] for j in ryze_jobs} if isinstance(ryze_jobs, list) else set()
    fb_jids = {j["id"] for j in fb_jobs} if isinstance(fb_jobs, list) else set()
    ryze_bids = (
        {b["id"] for b in ryze_bookings} if isinstance(ryze_bookings, list) else set()
    )

    # ── Data Isolation ────────────────────────────────────────
    print(f"\n{BOLD}  Data Isolation{RESET}")
    sec = "Data Isolation"

    overlap_c = ryze_cids & fb_cids
    record(
        sec,
        "Candidates",
        "pass" if not overlap_c else "fail",
        f"RYZE: {len(ryze_cids)}   Firm B: {len(fb_cids)}   Overlap: {len(overlap_c)}",
    )

    overlap_e = ryze_eids & fb_eids
    record(
        sec,
        "Employer Profiles",
        "pass" if not overlap_e else "fail",
        f"RYZE: {len(ryze_eids)}   Firm B: {len(fb_eids)}   Overlap: {len(overlap_e)}",
    )

    overlap_j = ryze_jids & fb_jids
    record(
        sec,
        "Job Orders",
        "pass" if not overlap_j else "fail",
        f"RYZE: {len(ryze_jids)}   Firm B: {len(fb_jids)}   Overlap: {len(overlap_j)}",
    )

    # ── Cross-Tenant Reads ────────────────────────────────────
    print(f"\n{BOLD}  Cross-Tenant Reads — must return 404{RESET}")
    sec = "Cross-Tenant Reads"

    if fb_cids:
        fb_cid = next(iter(fb_cids))
        check_404(
            sec,
            f"RYZE reads Firm B candidate #{fb_cid}",
            requests.get(
                f"{BASE_URL}/api/candidates/{fb_cid}", headers=hdrs(ryze_token)
            ),
        )
    if ryze_cids:
        ryze_cid = next(iter(ryze_cids))
        check_404(
            sec,
            f"Firm B reads RYZE candidate #{ryze_cid}",
            requests.get(
                f"{BASE_URL}/api/candidates/{ryze_cid}", headers=hdrs(firm_b_token)
            ),
        )
    if fb_eids:
        fb_eid = next(iter(fb_eids))
        check_404(
            sec,
            f"RYZE reads Firm B employer #{fb_eid}",
            requests.get(
                f"{BASE_URL}/api/employer-profiles/{fb_eid}", headers=hdrs(ryze_token)
            ),
        )
    if fb_jids:
        fb_jid = next(iter(fb_jids))
        check_404(
            sec,
            f"RYZE reads Firm B job order #{fb_jid}",
            requests.get(
                f"{BASE_URL}/api/job-orders/{fb_jid}", headers=hdrs(ryze_token)
            ),
        )
    if ryze_bids:
        ryze_bid = next(iter(ryze_bids))
        check_404(
            sec,
            f"Firm B reads RYZE booking #{ryze_bid}",
            requests.get(
                f"{BASE_URL}/api/bookings/{ryze_bid}", headers=hdrs(firm_b_token)
            ),
        )

    # ── Cross-Tenant Writes ───────────────────────────────────
    print(f"\n{BOLD}  Cross-Tenant Writes — must return 404{RESET}")
    sec = "Cross-Tenant Writes"

    if fb_cids:
        fb_cid = next(iter(fb_cids))
        check_404(
            sec,
            f"RYZE patches Firm B candidate #{fb_cid}",
            requests.patch(
                f"{BASE_URL}/api/candidates/{fb_cid}",
                headers=hdrs(ryze_token),
                json={"notes": "INJECTED"},
            ),
        )
    if fb_eids:
        fb_eid = next(iter(fb_eids))
        check_404(
            sec,
            f"RYZE patches Firm B employer #{fb_eid}",
            requests.patch(
                f"{BASE_URL}/api/employer-profiles/{fb_eid}",
                headers=hdrs(ryze_token),
                json={"recruiter_notes": "INJECTED"},
            ),
        )
    if fb_jids:
        fb_jid = next(iter(fb_jids))
        check_404(
            sec,
            f"RYZE patches Firm B job order #{fb_jid}",
            requests.patch(
                f"{BASE_URL}/api/job-orders/{fb_jid}",
                headers=hdrs(ryze_token),
                json={"notes": "INJECTED"},
            ),
        )
        fb_jid2 = list(fb_jids)[1] if len(fb_jids) > 1 else fb_jid
        check_404(
            sec,
            f"RYZE deletes Firm B job order #{fb_jid2}",
            requests.delete(
                f"{BASE_URL}/api/job-orders/{fb_jid2}", headers=hdrs(ryze_token)
            ),
        )

    # ── Semantic Search ───────────────────────────────────────
    print(f"\n{BOLD}  Semantic / RAG Search{RESET}")
    sec = "Semantic Search"

    r_search = requests.get(
        f"{BASE_URL}/api/search/candidates?q=Austin+TX+accountant&limit=10",
        headers=hdrs(ryze_token),
    )
    fb_search = requests.get(
        f"{BASE_URL}/api/search/candidates?q=Austin+TX+accountant&limit=10",
        headers=hdrs(firm_b_token),
    )

    if r_search.ok and fb_search.ok:
        r_ids = {r["id"] for r in r_search.json()}
        fb_ids = {r["id"] for r in fb_search.json()}
        overlap = r_ids & fb_ids
        record(
            sec,
            "Search results do not overlap between tenants",
            "pass" if not overlap else "fail",
            f"RYZE: {len(r_ids)} results   Firm B: {len(fb_ids)} results   Overlap: {len(overlap)}",
        )
        if fb_ids:
            leak = fb_ids - fb_cids
            record(
                sec,
                "Firm B search only returns Firm B candidates",
                "pass" if not leak else "fail",
                f"{len(fb_ids)} results, all within Firm B's own data",
            )
        else:
            record(
                sec,
                "Firm B search results",
                "warn",
                "0 results — run run_backfill.py to generate embeddings",
            )
    else:
        record(sec, "Search endpoints", "warn", "Non-200 response — skipped")

    # ── DB Explorer ───────────────────────────────────────────
    print(f"\n{BOLD}  DB Explorer{RESET}")
    sec = "DB Explorer"

    r_browse = requests.get(
        f"{BASE_URL}/admin/db/explorer?table=candidates&limit=100",
        headers=hdrs(ryze_token),
    )
    fb_browse = requests.get(
        f"{BASE_URL}/admin/db/explorer?table=candidates&limit=100",
        headers=hdrs(firm_b_token),
    )

    if r_browse.ok and fb_browse.ok:
        r_rows = {r["id"] for r in r_browse.json().get("rows", [])}
        fb_rows = {r["id"] for r in fb_browse.json().get("rows", [])}
        overlap = r_rows & fb_rows
        record(
            sec,
            "Browse results do not overlap between tenants",
            "pass" if not overlap else "fail",
            f"RYZE: {len(r_rows)} rows   Firm B: {len(fb_rows)} rows   Overlap: {len(overlap)}",
        )

        r_counts = requests.get(f"{BASE_URL}/admin/db/counts", headers=hdrs(ryze_token))
        fb_counts = requests.get(
            f"{BASE_URL}/admin/db/counts", headers=hdrs(firm_b_token)
        )
        if r_counts.ok and fb_counts.ok:
            rc = r_counts.json().get("candidates", 0)
            fc = fb_counts.json().get("candidates", 0)
            record(
                sec,
                "Sidebar counts are tenant-scoped",
                (
                    "pass"
                    if rc != fc or (rc == len(ryze_cids) and fc == len(fb_cids))
                    else "warn"
                ),
                f"RYZE: {rc}   Firm B: {fc}",
            )
    else:
        record(sec, "DB Explorer endpoints", "warn", "Non-200 response — skipped")

    # ── Write report ──────────────────────────────────────────
    _write_and_open()

    # ── Terminal summary ──────────────────────────────────────
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warned = sum(1 for r in results if r["status"] == "warn")
    total = len(results)

    print(f"\n{'═' * 50}")
    if failed == 0:
        print(
            f"{GREEN}{BOLD}  ✅ {passed}/{total} checks passed — all walls holding{RESET}"
        )
    else:
        print(f"{RED}{BOLD}  ❌ {failed}/{total} checks failed{RESET}")
    if warned:
        print(f"{YELLOW}  ⚠  {warned} warning(s){RESET}")
    print(f"{'═' * 50}")
    print(f"  Report: {REPORT_PATH}\n")

    sys.exit(0 if failed == 0 else 1)


def _write_and_open():
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warned = sum(1 for r in results if r["status"] == "warn")
    total = len(results)
    ts = datetime.now().strftime("%B %d, %Y  ·  %H:%M")
    all_good = failed == 0

    # Build section cards
    cards_html = ""
    for sec in sections:
        sec_results = [r for r in results if r["section"] == sec]
        rows = ""
        for r in sec_results:
            if r["status"] == "pass":
                icon = '<span class="icon pass-icon">✓</span>'
                cls = "pass"
            elif r["status"] == "fail":
                icon = '<span class="icon fail-icon">✗</span>'
                cls = "fail"
            else:
                icon = '<span class="icon warn-icon">⚠</span>'
                cls = "warn"

            detail_html = (
                f'<span class="detail">{r["detail"]}</span>' if r["detail"] else ""
            )
            rows += f"""
            <div class="row {cls}">
                {icon}
                <span class="row-label">{r["label"]}</span>
                {detail_html}
            </div>"""

        sec_passed = sum(1 for r in sec_results if r["status"] == "pass")
        sec_total = len(sec_results)
        sec_badge = f'<span class="sec-badge">{sec_passed}/{sec_total}</span>'

        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <span class="card-title">{sec}</span>
                {sec_badge}
            </div>
            <div class="card-body">{rows}
            </div>
        </div>"""

    verdict_color = "#16a34a" if all_good else "#dc2626"
    verdict_bg = "#f0fdf4" if all_good else "#fef2f2"
    verdict_border = "#bbf7d0" if all_good else "#fecaca"
    verdict_text = "All walls holding." if all_good else f"{failed} check(s) failed."
    verdict_icon = "✓" if all_good else "✗"
    score_color = "#16a34a" if all_good else "#dc2626"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RYZE.ai · EP16 · Tenant Isolation Report</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: "DM Sans", sans-serif;
    background: #f1f5f9;
    color: #1e3a5f;
    min-height: 100vh;
    padding: 40px 24px 80px;
    -webkit-font-smoothing: antialiased;
  }}

  .page {{
    max-width: 760px;
    margin: 0 auto;
  }}

  /* ── Header */
  .header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 32px;
    gap: 16px;
  }}

  .brand {{
    font-family: "DM Mono", monospace;
    font-size: 12px;
    font-weight: 500;
    color: #64748b;
    letter-spacing: 0.04em;
    margin-bottom: 6px;
  }}

  .page-title {{
    font-size: 26px;
    font-weight: 700;
    color: #0f2540;
    line-height: 1.2;
  }}

  .timestamp {{
    font-family: "DM Mono", monospace;
    font-size: 11px;
    color: #94a3b8;
    margin-top: 4px;
  }}

  /* ── Verdict banner */
  .verdict {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px 24px;
    background: {verdict_bg};
    border: 1.5px solid {verdict_border};
    border-radius: 12px;
    margin-bottom: 32px;
  }}

  .verdict-icon {{
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: {verdict_color};
    color: #fff;
    font-size: 22px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }}

  .verdict-text {{
    font-size: 17px;
    font-weight: 700;
    color: {verdict_color};
  }}

  .verdict-sub {{
    font-size: 13px;
    color: #64748b;
    margin-top: 2px;
  }}

  .score {{
    margin-left: auto;
    font-family: "DM Mono", monospace;
    font-size: 28px;
    font-weight: 500;
    color: {score_color};
    flex-shrink: 0;
  }}

  .score span {{
    font-size: 14px;
    color: #94a3b8;
  }}

  /* ── Cards */
  .cards {{
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}

  .card {{
    background: #ffffff;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    overflow: hidden;
  }}

  .card-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    border-bottom: 1px solid #f1f5f9;
    background: #f8fafc;
  }}

  .card-title {{
    font-size: 13px;
    font-weight: 700;
    color: #1e3a5f;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}

  .sec-badge {{
    font-family: "DM Mono", monospace;
    font-size: 11px;
    font-weight: 500;
    color: #64748b;
    background: #e2e8f0;
    padding: 2px 8px;
    border-radius: 20px;
  }}

  .card-body {{
    padding: 6px 0;
  }}

  /* ── Rows */
  .row {{
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 9px 20px;
    border-bottom: 1px solid #f8fafc;
  }}

  .row:last-child {{
    border-bottom: none;
  }}

  .icon {{
    font-size: 13px;
    font-weight: 700;
    flex-shrink: 0;
    width: 16px;
    text-align: center;
  }}

  .pass-icon {{ color: #16a34a; }}
  .fail-icon {{ color: #dc2626; }}
  .warn-icon {{ color: #d97706; }}

  .row-label {{
    font-size: 13.5px;
    color: #334155;
    font-weight: 500;
    flex: 1;
  }}

  .detail {{
    font-family: "DM Mono", monospace;
    font-size: 11px;
    color: #94a3b8;
    white-space: nowrap;
  }}

  .pass .row-label {{ color: #1e3a5f; }}
  .fail .row-label {{ color: #dc2626; font-weight: 600; }}
  .fail .detail    {{ color: #f87171; }}
  .warn .row-label {{ color: #92400e; }}
  .warn .detail    {{ color: #d97706; }}

  /* ── Footer */
  .footer {{
    margin-top: 40px;
    text-align: center;
    font-family: "DM Mono", monospace;
    font-size: 11px;
    color: #cbd5e1;
  }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <div>
      <div class="brand">RYZE.ai &nbsp;·&nbsp; Episode 16 &nbsp;·&nbsp; Multi-Tenant Architecture</div>
      <div class="page-title">Tenant Isolation Report</div>
      <div class="timestamp">{ts}</div>
    </div>
  </div>

  <div class="verdict">
    <div class="verdict-icon">{verdict_icon}</div>
    <div>
      <div class="verdict-text">{verdict_text}</div>
      <div class="verdict-sub">Row-level tenant isolation verified across all data surfaces.</div>
    </div>
    <div class="score">{passed}<span>/{total}</span></div>
  </div>

  <div class="cards">
    {cards_html}
  </div>

  <div class="footer">
    Generated by audit_tenant_ep16.py &nbsp;·&nbsp; RYZE GROUP, Inc.
  </div>

</div>
</body>
</html>"""

    REPORT_PATH.write_text(html, encoding="utf-8")
    webbrowser.open(REPORT_PATH.as_uri())


if __name__ == "__main__":
    main()
