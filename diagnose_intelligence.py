"""
diagnose_intelligence.py — why does the Intelligence chat say "not in our database"?

Surfaces the two things that actually determine whether a UI query finds a person:
  1. TENANT — which tenant each user resolves to, and which tenant each candidate
     lives under. If your login's tenant != the candidate's tenant, it is
     correctly invisible and NO spelling will ever find them.
  2. NAME MATCHING — how tool_get_candidate_by_name (exact substring ilike) and
     the vector search behave across correct vs misspelled names.

Read-only. Run from the project root:  python diagnose_intelligence.py
"""

# Register every model first so SQLAlchemy resolves all FKs (bookings.employer_id -> users).
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
from app.models.candidate import Candidate
from app.api.chat import tool_get_candidate_by_name, tool_search_candidates

BAR = "=" * 78
SPELLINGS = ["Renata Voss", "Renata", "Rentata Voss", "Rentat Voss", "Voss"]


def main():
    db = SessionLocal()
    try:
        # ---- 1. Users and their tenants ------------------------------------
        print(BAR)
        print("USERS  (which tenant does each login resolve to?)")
        print("-" * 78)
        users = db.query(User).all()
        user_tenants = set()
        for u in users:
            tid = getattr(u, "tenant_id", None)
            user_tenants.add(tid)
            print(
                f"  id={getattr(u,'id','?'):<4} email={getattr(u,'email','?'):<40} tenant_id={tid!r}"
            )
        print(f"\n  Distinct user tenants: {sorted(str(t) for t in user_tenants)}")

        # ---- 2. Candidates and their tenants -------------------------------
        print("\n" + BAR)
        print("CANDIDATES  (which tenant is each person under? do they have data?)")
        print("-" * 78)
        candidates = db.query(Candidate).all()
        cand_tenants = set()
        for c in candidates:
            tid = getattr(c, "tenant_id", None)
            cand_tenants.add(tid)
            has_summary = bool(getattr(c, "ai_summary", None))
            print(
                f"  id={getattr(c,'id','?'):<4} name={getattr(c,'name','?')!r:<22} "
                f"tenant_id={tid!r:<26} source={getattr(c,'source',None)!r} "
                f"summary={'yes' if has_summary else 'NO'}"
            )
        print(f"\n  Distinct candidate tenants: {sorted(str(t) for t in cand_tenants)}")

        # ---- 3. The key comparison -----------------------------------------
        print("\n" + BAR)
        print("TENANT OVERLAP CHECK")
        print("-" * 78)
        overlap = {str(t) for t in user_tenants} & {str(t) for t in cand_tenants}
        if overlap:
            print(f"  Users and candidates SHARE tenant(s): {sorted(overlap)}")
            print(
                "  -> A user in a shared tenant CAN see those candidates (if spelling matches)."
            )
        else:
            print("  !!! NO SHARED TENANT between any user and any candidate. !!!")
            print(
                "  -> This is the bug: every logged-in user is scoped to a tenant that has"
            )
            print("     no candidates. The chat will ALWAYS say 'not in our database',")
            print(
                "     no matter how the name is spelled. Fix the tenant, not the matcher."
            )

        # ---- 4. Name-matching behavior across spellings --------------------
        print("\n" + BAR)
        print("NAME LOOKUP PROBE  (tool_get_candidate_by_name = exact substring ilike)")
        print("-" * 78)
        probe_tenants = sorted(
            {str(t) for t in (cand_tenants | user_tenants) if t is not None}
        )
        for tenant in probe_tenants:
            print(f"\n  tenant = {tenant!r}")
            for spelling in SPELLINGS:
                res = tool_get_candidate_by_name(db, spelling, tenant)
                names = [c.get("name") for c in res.get("candidates", [])]
                print(
                    f"    get_candidate_by_name({spelling!r:<16}) -> count={res.get('count',0)}  {names}"
                )

        # ---- 5. Vector search (needs OpenAI; skips if unavailable) ----------
        print("\n" + BAR)
        print("VECTOR SEARCH PROBE  (semantic — does it rescue a misspelled name?)")
        print("-" * 78)
        try:
            for tenant in probe_tenants:
                res = tool_search_candidates(
                    db, "Rentata Voss college education", limit=5, tenant_id=tenant
                )
                names = [c.get("name") for c in res.get("candidates", [])]
                print(f"  tenant={tenant!r:<26} query='Rentata Voss...' -> {names}")
        except Exception as e:
            print(f"  (vector search skipped: {e})")

        print("\n" + BAR)
        print("HOW TO READ THIS")
        print("-" * 78)
        print(
            "  * If your login's tenant is NOT in the candidate tenants -> tenant bug."
        )
        print(
            "  * If 'Renata Voss' matches but 'Rentata Voss' returns 0 -> typo intolerance;"
        )
        print("    the fix is fuzzy name matching, and the UI failures were spelling.")
        print(
            "  * If even the vector search misses the misspelling -> name resolution needs"
        )
        print(
            "    a fuzzy/trigram path, since embeddings don't reliably catch typo'd names."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
