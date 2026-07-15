"""
backfill_signup_tenants.py

One-time backfill for users created before signup stamped tenant_id
explicitly (see app/services/tenant_resolution.py): resolves the correct
tenant for existing CANDIDATE/EMPLOYER users still sitting in ryze/NULL.

Dry-run by default — prints the rows that WOULD change, writes nothing.
Pass --commit to actually apply and commit. Never touches ADMIN/superusers.
Idempotent: a second run after --commit prints zero changes.

Usage:
    python backfill_signup_tenants.py            # dry run
    python backfill_signup_tenants.py --commit    # apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import all models so SQLAlchemy can resolve all foreign keys
from app.models.user import User, UserType
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile

from sqlalchemy import or_

from app.core.database import SessionLocal
from app.core.deps import RYZE_TENANT
from app.services.tenant_resolution import resolve_signup_tenant


def main(commit: bool) -> None:
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(
                User.user_type.in_([UserType.CANDIDATE, UserType.EMPLOYER]),
                or_(User.tenant_id.is_(None), User.tenant_id == RYZE_TENANT),
            )
            .all()
        )

        changes = []
        for user in users:
            new_tenant = resolve_signup_tenant(db, user.email, user.user_type)
            if new_tenant != user.tenant_id:
                changes.append((user, user.tenant_id or "NULL", new_tenant))

        for user, old, new_tenant in changes:
            print(
                f"{user.id} | {user.email} | {user.user_type.value} | {old} -> {new_tenant}"
            )

        print(f"\n{len(changes)} user(s) would change.")

        if not commit:
            print("Dry run — no changes written. Re-run with --commit to apply.")
            return

        if not changes:
            print("Nothing to commit.")
            return

        for user, _old, new_tenant in changes:
            user.tenant_id = new_tenant
        db.commit()
        print(f"✅ Committed {len(changes)} update(s).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill tenant_id for self-registered candidate/employer users."
    )
    parser.add_argument(
        "--commit", action="store_true", help="Apply changes (default is dry-run)."
    )
    args = parser.parse_args()
    main(commit=args.commit)
