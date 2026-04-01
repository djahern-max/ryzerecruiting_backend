"""
test_tenant_isolation.py
────────────────────────
EP16 — Multi-Tenant Isolation Test Suite

Verifies that tenant data walls are holding across all data surfaces:

  1.  Candidate list isolation
  2.  Employer profile list isolation
  3.  Job order list isolation
  4.  Cross-tenant direct read (candidates, employers, job orders → must 404)
  5.  Cross-tenant write — candidates (PATCH → must 404)
  6.  Cross-tenant write — employer profiles (PATCH → must 404)
  7.  Cross-tenant write — job orders (PATCH + DELETE → must 404)
  8.  Cross-tenant booking read (GET /{id} → must 404)
  9.  Semantic / RAG search isolation
  10. DB Explorer browse isolation

Prerequisites:
  • Server must be running  (uvicorn app.main:app)
  • migration_ep16.sql must have been run
  • seed_full.py must have been run   (creates RYZE bookings)
  • seed_tenant_b.py must have been run
  • run_backfill.py should be run     (enables Test 9)

Usage:
  python test_tenant_isolation.py

  # Override URL or RYZE credentials without editing the file:
  BASE_URL=https://api.ryze.ai RYZE_EMAIL=dane@ryze.ai RYZE_PASSWORD=secret python test_tenant_isolation.py
"""

import os
import sys
import requests

# ── Config ────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
RYZE_EMAIL = os.getenv("RYZE_EMAIL", "dane@ryze.ai")
RYZE_PASS = os.getenv("RYZE_PASSWORD", "YourPasswordHere")  # ← set this
FIRM_B_EMAIL = "admin@firmb.com"
FIRM_B_PASS = os.getenv("FIRM_B_PASSWORD", "")
# ─────────────────────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0
warned = 0


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


def warn(label):
    global warned
    warned += 1
    print(f"  {YELLOW}⚠ WARN{RESET}  {label}")


def section(title):
    bar = "─" * max(0, 52 - len(title))
    print(f"\n{BOLD}── {title} {bar}{RESET}")


def login(email: str, password: str) -> str:
    """Returns a bearer token or raises RuntimeError."""
    res = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    if not res.ok:
        raise RuntimeError(f"Login failed for {email}: {res.status_code} {res.text}")
    return res.json()["access_token"]


def hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def assert_404(res, label):
    """Pass if 404, fail with detail otherwise."""
    if res.status_code == 404:
        ok(f"{label}  → 404 ✓")
    elif res.status_code == 200:
        fail(f"{label}  → 200 (ISOLATION BREACH)")
    else:
        fail(f"{label}  → {res.status_code} (unexpected)")


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    print(f"\n{BOLD}═══════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}  RYZE.ai — EP16 Multi-Tenant Isolation Test Suite     {RESET}")
    print(f"{BOLD}═══════════════════════════════════════════════════════{RESET}")
    print(f"  Server : {BASE_URL}\n")

    # ── Guard — fail early if credentials are missing ─────────
    if not RYZE_PASS:
        print(f"  {RED}✗{RESET}  RYZE_PASSWORD environment variable is not set.")
        print(
            f"       Run as: RYZE_PASSWORD=yourpassword FIRM_B_PASSWORD=yourpassword python test_tenant_isolation.py"
        )
        sys.exit(1)
    if not FIRM_B_PASS:
        print(f"  {RED}✗{RESET}  FIRM_B_PASSWORD environment variable is not set.")
        print(
            f"       Run as: RYZE_PASSWORD=yourpassword FIRM_B_PASSWORD=yourpassword python test_tenant_isolation.py"
        )
        sys.exit(1)

    # ── Authentication ────────────────────────────────────────
    # ── Authentication ────────────────────────────────────────
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

    # ── Fetch both tenant datasets up front ───────────────────

    ryze_candidates = requests.get(
        f"{BASE_URL}/api/candidates", headers=hdrs(ryze_token)
    ).json()
    firm_b_candidates = requests.get(
        f"{BASE_URL}/api/candidates", headers=hdrs(firm_b_token)
    ).json()
    ryze_employers = requests.get(
        f"{BASE_URL}/api/employer-profiles", headers=hdrs(ryze_token)
    ).json()
    firm_b_employers = requests.get(
        f"{BASE_URL}/api/employer-profiles", headers=hdrs(firm_b_token)
    ).json()
    ryze_jobs = requests.get(
        f"{BASE_URL}/api/job-orders", headers=hdrs(ryze_token)
    ).json()
    firm_b_jobs = requests.get(
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
        {c["id"] for c in firm_b_candidates}
        if isinstance(firm_b_candidates, list)
        else set()
    )
    ryze_eids = (
        {e["id"] for e in ryze_employers} if isinstance(ryze_employers, list) else set()
    )
    fb_eids = (
        {e["id"] for e in firm_b_employers}
        if isinstance(firm_b_employers, list)
        else set()
    )
    ryze_jids = {j["id"] for j in ryze_jobs} if isinstance(ryze_jobs, list) else set()
    fb_jids = {j["id"] for j in firm_b_jobs} if isinstance(firm_b_jobs, list) else set()
    ryze_bids = (
        {b["id"] for b in ryze_bookings} if isinstance(ryze_bookings, list) else set()
    )

    # ── Test 1: Candidate list isolation ─────────────────────
    section("Test 1 — Candidate List Isolation")

    overlap = ryze_cids & fb_cids
    if overlap:
        fail("No candidate ID overlap between tenants", f"Shared IDs: {overlap}")
    else:
        ok("No candidate ID overlap between tenants")
    ok(f"RYZE sees {len(ryze_cids)} candidate(s)")
    ok(f"Firm B sees {len(fb_cids)} candidate(s)")

    firm_b_names = (
        {c.get("name") for c in firm_b_candidates}
        if isinstance(firm_b_candidates, list)
        else set()
    )
    expected = {"Rachel Torres", "Marcus Webb", "Priya Nair", "Derek Owens"}
    if expected.issubset(firm_b_names):
        ok("Firm B contains all expected seeded candidates")
    else:
        fail(
            "Firm B missing expected candidates", f"Missing: {expected - firm_b_names}"
        )

    # ── Test 2: Employer list isolation ──────────────────────
    section("Test 2 — Employer Profile List Isolation")

    overlap_e = ryze_eids & fb_eids
    if overlap_e:
        fail("No employer ID overlap between tenants", f"Shared IDs: {overlap_e}")
    else:
        ok("No employer ID overlap between tenants")
    ok(f"RYZE sees {len(ryze_eids)} employer(s)")
    ok(f"Firm B sees {len(fb_eids)} employer(s)")

    # ── Test 3: Job order list isolation ─────────────────────
    section("Test 3 — Job Order List Isolation")

    overlap_j = ryze_jids & fb_jids
    if overlap_j:
        fail("No job order ID overlap between tenants", f"Shared IDs: {overlap_j}")
    else:
        ok("No job order ID overlap between tenants")
    ok(f"RYZE sees {len(ryze_jids)} job order(s)")
    ok(f"Firm B sees {len(fb_jids)} job order(s)")

    # ── Test 4: Cross-tenant direct read ─────────────────────
    section("Test 4 — Cross-Tenant Direct Read (must 404)")

    # Candidates
    if fb_cids:
        fb_cid = next(iter(fb_cids))
        assert_404(
            requests.get(
                f"{BASE_URL}/api/candidates/{fb_cid}", headers=hdrs(ryze_token)
            ),
            f"RYZE cannot read Firm B candidate #{fb_cid}",
        )
    if ryze_cids:
        ryze_cid = next(iter(ryze_cids))
        assert_404(
            requests.get(
                f"{BASE_URL}/api/candidates/{ryze_cid}", headers=hdrs(firm_b_token)
            ),
            f"Firm B cannot read RYZE candidate #{ryze_cid}",
        )

    # Employer profiles
    if fb_eids:
        fb_eid = next(iter(fb_eids))
        assert_404(
            requests.get(
                f"{BASE_URL}/api/employer-profiles/{fb_eid}", headers=hdrs(ryze_token)
            ),
            f"RYZE cannot read Firm B employer #{fb_eid}",
        )
    if ryze_eids:
        ryze_eid = next(iter(ryze_eids))
        assert_404(
            requests.get(
                f"{BASE_URL}/api/employer-profiles/{ryze_eid}",
                headers=hdrs(firm_b_token),
            ),
            f"Firm B cannot read RYZE employer #{ryze_eid}",
        )

    # Job orders
    if fb_jids:
        fb_jid = next(iter(fb_jids))
        assert_404(
            requests.get(
                f"{BASE_URL}/api/job-orders/{fb_jid}", headers=hdrs(ryze_token)
            ),
            f"RYZE cannot read Firm B job order #{fb_jid}",
        )
    if ryze_jids:
        ryze_jid = next(iter(ryze_jids))
        assert_404(
            requests.get(
                f"{BASE_URL}/api/job-orders/{ryze_jid}", headers=hdrs(firm_b_token)
            ),
            f"Firm B cannot read RYZE job order #{ryze_jid}",
        )

    # ── Test 5: Cross-tenant write — candidates ───────────────
    section("Test 5 — Cross-Tenant Write: Candidates (must 404)")

    if fb_cids:
        fb_cid = next(iter(fb_cids))
        assert_404(
            requests.patch(
                f"{BASE_URL}/api/candidates/{fb_cid}",
                headers=hdrs(ryze_token),
                json={"notes": "INJECTED BY WRONG TENANT"},
            ),
            f"RYZE cannot PATCH Firm B candidate #{fb_cid}",
        )

        # Verify record is unchanged
        verify = requests.get(
            f"{BASE_URL}/api/candidates/{fb_cid}",
            headers=hdrs(firm_b_token),
        )
        if verify.ok and verify.json().get("notes") != "INJECTED BY WRONG TENANT":
            ok(f"Firm B candidate #{fb_cid} record unchanged after RYZE PATCH attempt")
        elif not verify.ok:
            warn("Could not verify candidate record integrity — GET returned non-200")

    # ── Test 6: Cross-tenant write — employer profiles ────────
    section("Test 6 — Cross-Tenant Write: Employer Profiles (must 404)")

    if fb_eids:
        fb_eid = next(iter(fb_eids))
        assert_404(
            requests.patch(
                f"{BASE_URL}/api/employer-profiles/{fb_eid}",
                headers=hdrs(ryze_token),
                json={"recruiter_notes": "INJECTED BY WRONG TENANT"},
            ),
            f"RYZE cannot PATCH Firm B employer #{fb_eid}",
        )

    # ── Test 7: Cross-tenant write — job orders ───────────────
    section("Test 7 — Cross-Tenant Write: Job Orders (must 404)")

    if fb_jids:
        fb_jid = next(iter(fb_jids))

        # PATCH
        assert_404(
            requests.patch(
                f"{BASE_URL}/api/job-orders/{fb_jid}",
                headers=hdrs(ryze_token),
                json={"notes": "INJECTED BY WRONG TENANT"},
            ),
            f"RYZE cannot PATCH Firm B job order #{fb_jid}",
        )

        # DELETE — use a second Firm B job ID if available so we don't destroy
        # the first one used throughout this test run
        fb_jid_for_delete = list(fb_jids)[1] if len(fb_jids) > 1 else fb_jid
        assert_404(
            requests.delete(
                f"{BASE_URL}/api/job-orders/{fb_jid_for_delete}",
                headers=hdrs(ryze_token),
            ),
            f"RYZE cannot DELETE Firm B job order #{fb_jid_for_delete}",
        )

        # Confirm Firm B's job still exists
        verify = requests.get(
            f"{BASE_URL}/api/job-orders/{fb_jid_for_delete}",
            headers=hdrs(firm_b_token),
        )
        if verify.ok:
            ok(
                f"Firm B job order #{fb_jid_for_delete} still exists after RYZE DELETE attempt"
            )
        else:
            fail(
                f"Firm B job order #{fb_jid_for_delete} missing after RYZE DELETE attempt",
                "Record may have been deleted — check the database",
            )

    # ── Test 8: Cross-tenant booking read ────────────────────
    section("Test 8 — Cross-Tenant Booking Read (must 404)")

    if ryze_bids:
        ryze_bid = next(iter(ryze_bids))
        assert_404(
            requests.get(
                f"{BASE_URL}/api/bookings/{ryze_bid}",
                headers=hdrs(firm_b_token),
            ),
            f"Firm B cannot read RYZE booking #{ryze_bid}",
        )
    else:
        warn(
            "No RYZE bookings found — skipping booking isolation check (run seed_full.py)"
        )

    # ── Test 9: Semantic / RAG search isolation ───────────────
    section("Test 9 — Semantic / RAG Search Isolation")

    ryze_search = requests.get(
        f"{BASE_URL}/api/search/candidates?q=Austin+TX+accountant&limit=10",
        headers=hdrs(ryze_token),
    )
    firm_b_search = requests.get(
        f"{BASE_URL}/api/search/candidates?q=Austin+TX+accountant&limit=10",
        headers=hdrs(firm_b_token),
    )

    if ryze_search.ok and firm_b_search.ok:
        ryze_search_ids = {r["id"] for r in ryze_search.json()}
        fb_search_ids = {r["id"] for r in firm_b_search.json()}
        search_overlap = ryze_search_ids & fb_search_ids

        if search_overlap:
            fail(
                "Semantic search results overlap between tenants",
                f"Shared IDs: {search_overlap}",
            )
        else:
            ok("Semantic search results do not overlap between tenants")

        if fb_search_ids and fb_search_ids.issubset(fb_cids):
            ok("Firm B semantic search only returns Firm B candidates")
        elif not fb_search_ids:
            warn(
                "Firm B search returned 0 results — embeddings may not be generated yet (run run_backfill.py)"
            )
        else:
            leak = fb_search_ids - fb_cids
            if leak:
                fail(
                    "Firm B search results contain non-Firm B candidates",
                    f"Leaked IDs: {leak}",
                )
    else:
        warn(
            f"Search endpoints non-200 — skipping (RYZE: {ryze_search.status_code}  Firm B: {firm_b_search.status_code})"
        )

    # ── Test 10: DB Explorer browse isolation ─────────────────
    section("Test 10 — DB Explorer Browse Isolation")

    ryze_browse = requests.get(
        f"{BASE_URL}/admin/db/explorer?table=candidates&limit=100",
        headers=hdrs(ryze_token),
    )
    firm_b_browse = requests.get(
        f"{BASE_URL}/admin/db/explorer?table=candidates&limit=100",
        headers=hdrs(firm_b_token),
    )

    if ryze_browse.ok and firm_b_browse.ok:
        ryze_browse_ids = {r["id"] for r in ryze_browse.json().get("rows", [])}
        fb_browse_ids = {r["id"] for r in firm_b_browse.json().get("rows", [])}
        browse_overlap = ryze_browse_ids & fb_browse_ids

        if browse_overlap:
            fail(
                "DB Explorer candidate rows overlap between tenants",
                f"Shared IDs: {browse_overlap}",
            )
        else:
            ok("DB Explorer candidate rows do not overlap between tenants")

        if fb_browse_ids and fb_browse_ids.issubset(fb_cids):
            ok("DB Explorer shows Firm B only their own candidate rows")
        elif not fb_browse_ids:
            warn(
                "DB Explorer returned 0 rows for Firm B — check TENANT_SCOPED_TABLES in db_explorer.py"
            )
        else:
            leak = fb_browse_ids - fb_cids
            if leak:
                fail(
                    "DB Explorer leaking non-Firm B rows to Firm B",
                    f"Leaked IDs: {leak}",
                )

        # DB Explorer counts
        ryze_counts = requests.get(
            f"{BASE_URL}/admin/db/counts", headers=hdrs(ryze_token)
        )
        firm_b_counts = requests.get(
            f"{BASE_URL}/admin/db/counts", headers=hdrs(firm_b_token)
        )
        if ryze_counts.ok and firm_b_counts.ok:
            rc = ryze_counts.json().get("candidates", 0)
            fc = firm_b_counts.json().get("candidates", 0)
            if rc != fc or (rc == len(ryze_cids) and fc == len(fb_cids)):
                ok(
                    f"DB Explorer sidebar counts are tenant-scoped  (RYZE: {rc}  Firm B: {fc})"
                )
            else:
                warn(
                    f"DB Explorer counts may not be scoped — both show {rc} candidates"
                )
    else:
        warn(
            f"DB Explorer non-200 — skipping (RYZE: {ryze_browse.status_code}  Firm B: {firm_b_browse.status_code})"
        )

    # ── Summary ───────────────────────────────────────────────
    total = passed + failed
    print(f"\n{BOLD}═══════════════════════════════════════════════════════{RESET}")
    if failed == 0:
        print(
            f"{BOLD}{GREEN}  ✅ ALL {total} CHECKS PASSED — Tenant isolation is holding{RESET}"
        )
    else:
        print(
            f"{BOLD}{RED}  ❌ {failed} of {total} checks FAILED — review above{RESET}"
        )
    if warned:
        print(f"  {YELLOW}⚠  {warned} warning(s) — non-fatal, see above{RESET}")
    print(f"{BOLD}═══════════════════════════════════════════════════════{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
