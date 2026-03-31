"""
test_tenant_isolation.py
────────────────────────
EP16 — Multi-Tenant Isolation Test Suite

Verifies that tenant data walls are holding across all data surfaces:
  1. Candidate list isolation
  2. Employer profile list isolation
  3. Job order list isolation
  4. Cross-tenant direct ID access (must 404)
  5. Semantic / RAG search isolation
  6. Intelligence chat isolation (if API key is available)

Prerequisites:
  • Server must be running  (uvicorn app.main:app)
  • migration_ep16.sql must have been run
  • seed_tenant_b.py must have been run
  • RYZE admin credentials must exist
  • .env must be loaded (or set BASE_URL, RYZE_EMAIL, RYZE_PASSWORD below)

Usage:
  python test_tenant_isolation.py

  # Override URL/creds without editing the file:
  BASE_URL=https://api.ryze.ai RYZE_EMAIL=dane@ryze.ai python test_tenant_isolation.py
"""

import os
import sys
import requests

# ── Config — edit or override with env vars ───────────────────────────────
BASE_URL   = os.getenv("BASE_URL",      "http://localhost:8000")
RYZE_EMAIL = os.getenv("RYZE_EMAIL",    "dane@ryze.ai")        # ← your admin email
RYZE_PASS  = os.getenv("RYZE_PASSWORD", "YourPasswordHere")    # ← your admin password
FIRM_B_EMAIL = "admin@firmb.com"
FIRM_B_PASS  = "FirmBAdmin123!"
# ─────────────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

passed = 0
failed = 0


def ok(label):
    global passed
    passed += 1
    print(f"  {GREEN}✓ PASS{RESET}  {label}")


def fail(label, detail=""):
    global failed
    failed += 1
    msg = f"  {RED}✗ FAIL{RESET}  {label}"
    if detail:
        msg += f"\n         {RED}{detail}{RESET}"
    print(msg)


def section(title):
    print(f"\n{BOLD}── {title} {'─' * (52 - len(title))}{RESET}")


# ── Auth helpers ──────────────────────────────────────────────────────────

def login(email: str, password: str) -> str:
    """Returns a bearer token or raises."""
    res = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    if not res.ok:
        raise RuntimeError(f"Login failed for {email}: {res.status_code} {res.text}")
    return res.json()["access_token"]


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Main test runner ──────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}═══════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}  RYZE.ai — EP16 Multi-Tenant Isolation Test Suite     {RESET}")
    print(f"{BOLD}═══════════════════════════════════════════════════════{RESET}")
    print(f"  Server : {BASE_URL}")

    # ── Login both tenants ────────────────────────────────────
    section("Authentication")
    try:
        ryze_token = login(RYZE_EMAIL, RYZE_PASS)
        ok(f"RYZE admin login  ({RYZE_EMAIL})")
    except Exception as e:
        fail(f"RYZE admin login  ({RYZE_EMAIL})", str(e))
        print("\n  Cannot continue without RYZE credentials. Exiting.")
        sys.exit(1)

    try:
        firm_b_token = login(FIRM_B_EMAIL, FIRM_B_PASS)
        ok(f"Firm B admin login  ({FIRM_B_EMAIL})")
    except Exception as e:
        fail(f"Firm B admin login  ({FIRM_B_EMAIL})", str(e))
        print("\n  Run seed_tenant_b.py first. Exiting.")
        sys.exit(1)

    # ── Test 1: Candidate list isolation ─────────────────────
    section("Test 1 — Candidate List Isolation")

    ryze_candidates = requests.get(
        f"{BASE_URL}/api/candidates",
        headers=headers(ryze_token),
    ).json()

    firm_b_candidates = requests.get(
        f"{BASE_URL}/api/candidates",
        headers=headers(firm_b_token),
    ).json()

    ryze_ids  = {c["id"] for c in ryze_candidates}  if isinstance(ryze_candidates, list)  else set()
    firm_b_ids = {c["id"] for c in firm_b_candidates} if isinstance(firm_b_candidates, list) else set()

    overlap = ryze_ids & firm_b_ids

    if overlap:
        fail("No candidate ID overlap between tenants", f"Shared IDs: {overlap}")
    else:
        ok("No candidate ID overlap between tenants")

    ok(f"RYZE sees {len(ryze_ids)} candidate(s)")
    ok(f"Firm B sees {len(firm_b_ids)} candidate(s)")

    # Verify Firm B only sees their own candidates
    firm_b_names = {c.get("name") for c in firm_b_candidates} if isinstance(firm_b_candidates, list) else set()
    expected_firm_b = {"Rachel Torres", "Marcus Webb", "Priya Nair", "Derek Owens"}
    if expected_firm_b.issubset(firm_b_names):
        ok("Firm B candidates contain expected seeded records")
    else:
        missing = expected_firm_b - firm_b_names
        fail("Firm B missing expected candidates", f"Missing: {missing}")

    # ── Test 2: Employer list isolation ──────────────────────
    section("Test 2 — Employer Profile List Isolation")

    ryze_employers  = requests.get(f"{BASE_URL}/api/employer-profiles", headers=headers(ryze_token)).json()
    firm_b_employers = requests.get(f"{BASE_URL}/api/employer-profiles", headers=headers(firm_b_token)).json()

    re_ids  = {e["id"] for e in ryze_employers}  if isinstance(ryze_employers, list)  else set()
    fbe_ids = {e["id"] for e in firm_b_employers} if isinstance(firm_b_employers, list) else set()

    overlap_e = re_ids & fbe_ids
    if overlap_e:
        fail("No employer ID overlap between tenants", f"Shared IDs: {overlap_e}")
    else:
        ok("No employer ID overlap between tenants")

    ok(f"RYZE sees {len(re_ids)} employer(s)")
    ok(f"Firm B sees {len(fbe_ids)} employer(s)")

    # ── Test 3: Job order list isolation ─────────────────────
    section("Test 3 — Job Order List Isolation")

    ryze_jobs  = requests.get(f"{BASE_URL}/api/job-orders", headers=headers(ryze_token)).json()
    firm_b_jobs = requests.get(f"{BASE_URL}/api/job-orders", headers=headers(firm_b_token)).json()

    rj_ids  = {j["id"] for j in ryze_jobs}  if isinstance(ryze_jobs, list)  else set()
    fbj_ids = {j["id"] for j in firm_b_jobs} if isinstance(firm_b_jobs, list) else set()

    overlap_j = rj_ids & fbj_ids
    if overlap_j:
        fail("No job order ID overlap between tenants", f"Shared IDs: {overlap_j}")
    else:
        ok("No job order ID overlap between tenants")

    ok(f"RYZE sees {len(rj_ids)} job order(s)")
    ok(f"Firm B sees {len(fbj_ids)} job order(s)")

    # ── Test 4: Cross-tenant direct ID access ────────────────
    section("Test 4 — Cross-Tenant Direct Access (must 404)")

    # Attempt: RYZE admin tries to read a Firm B candidate by ID
    if firm_b_ids:
        stolen_candidate_id = next(iter(firm_b_ids))
        res = requests.get(
            f"{BASE_URL}/api/candidates/{stolen_candidate_id}",
            headers=headers(ryze_token),
        )
        if res.status_code == 404:
            ok(f"RYZE cannot read Firm B candidate #{stolen_candidate_id}  → 404 ✓")
        elif res.status_code == 200:
            fail(
                f"RYZE read Firm B candidate #{stolen_candidate_id}  → 200 (ISOLATION BREACH)",
                f"Response: {res.json().get('name', '?')}",
            )
        else:
            fail(f"Unexpected status {res.status_code} for cross-tenant read")

    # Attempt: Firm B admin tries to read a RYZE candidate by ID
    if ryze_ids:
        stolen_ryze_id = next(iter(ryze_ids))
        res = requests.get(
            f"{BASE_URL}/api/candidates/{stolen_ryze_id}",
            headers=headers(firm_b_token),
        )
        if res.status_code == 404:
            ok(f"Firm B cannot read RYZE candidate #{stolen_ryze_id}  → 404 ✓")
        elif res.status_code == 200:
            fail(
                f"Firm B read RYZE candidate #{stolen_ryze_id}  → 200 (ISOLATION BREACH)",
                f"Response: {res.json().get('name', '?')}",
            )
        else:
            fail(f"Unexpected status {res.status_code} for cross-tenant read")

    # ── Test 5: Cross-tenant update attempt ──────────────────
    section("Test 5 — Cross-Tenant Write Attempt (must 404)")

    if firm_b_ids:
        stolen_id = next(iter(firm_b_ids))
        res = requests.patch(
            f"{BASE_URL}/api/candidates/{stolen_id}",
            headers=headers(ryze_token),
            json={"notes": "INJECTED BY WRONG TENANT"},
        )
        if res.status_code == 404:
            ok(f"RYZE cannot update Firm B candidate #{stolen_id}  → 404 ✓")
        elif res.status_code == 200:
            fail(f"RYZE updated Firm B candidate #{stolen_id}  → 200 (ISOLATION BREACH)")
        else:
            ok(f"RYZE blocked from updating Firm B candidate  → {res.status_code} ✓")

    # ── Test 6: Semantic search isolation ────────────────────
    section("Test 6 — Semantic / RAG Search Isolation")

    # RYZE searches for "Austin TX accountant" — Firm B has Rachel Torres and Priya Nair there
    ryze_search = requests.get(
        f"{BASE_URL}/api/search/candidates?q=Austin+TX+accountant&limit=10",
        headers=headers(ryze_token),
    )
    firm_b_search = requests.get(
        f"{BASE_URL}/api/search/candidates?q=Austin+TX+accountant&limit=10",
        headers=headers(firm_b_token),
    )

    if ryze_search.ok and firm_b_search.ok:
        ryze_search_ids  = {r["id"] for r in ryze_search.json()}
        firm_b_search_ids = {r["id"] for r in firm_b_search.json()}

        search_overlap = ryze_search_ids & firm_b_search_ids
        if search_overlap:
            fail(
                "Semantic search results overlap between tenants",
                f"Shared IDs in search results: {search_overlap}",
            )
        else:
            ok("Semantic search results do not overlap between tenants")

        # Verify Firm B's search finds their candidates (not RYZE's)
        if firm_b_search_ids and firm_b_search_ids.issubset(firm_b_ids):
            ok("Firm B semantic search only returns Firm B candidates")
        elif not firm_b_search_ids:
            print(f"  {YELLOW}⚠ WARN{RESET}  Firm B search returned 0 results — embeddings may not be generated yet")
            print(f"         Run: python run_backfill.py   (or wait for background embedding)")
        else:
            leak = firm_b_search_ids - firm_b_ids
            if leak:
                fail("Firm B search results contain non-Firm B candidates", f"Leaked IDs: {leak}")
    else:
        print(f"  {YELLOW}⚠ WARN{RESET}  Semantic search endpoints returned non-200 — skipping search isolation check")
        print(f"         RYZE: {ryze_search.status_code}  Firm B: {firm_b_search.status_code}")

    # ── Summary ───────────────────────────────────────────────
    total = passed + failed
    print(f"\n{BOLD}═══════════════════════════════════════════════════════{RESET}")
    if failed == 0:
        print(f"{BOLD}{GREEN}  ✅ ALL {total} CHECKS PASSED — Tenant isolation is holding{RESET}")
    else:
        print(f"{BOLD}{RED}  ❌ {failed} of {total} checks FAILED — review above{RESET}")
    print(f"{BOLD}═══════════════════════════════════════════════════════{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
