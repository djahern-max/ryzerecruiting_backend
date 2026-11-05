#!/usr/bin/env python3
"""
scripts/create_superadmin.py

Creates a platform-owner superadmin account (is_superuser=True) inside a
tenant. The tenant row must exist — there is no house tenant; a slug with
no tenants row gets 403 on every data endpoint.
Refuses to run if a user with the given email already exists.

Usage (from project root):
    python scripts/create_superadmin.py --email you@example.com
    python scripts/create_superadmin.py --email you@example.com --tenant acme_recruiting
"""

import sys
import os
import argparse
import getpass

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.tenant import Tenant
from app.models.user import User, UserType

DEFAULT_TENANT = "green_path_recruiting"


def main():
    parser = argparse.ArgumentParser(description="Create a platform-owner superadmin user.")
    parser.add_argument("--email", required=True, help="Email address for the new superadmin")
    parser.add_argument(
        "--tenant",
        default=DEFAULT_TENANT,
        help=f"Tenant slug the account belongs to (default: {DEFAULT_TENANT}); the tenants row must exist",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            print(f"ERROR: a user with email {args.email} already exists (id={existing.id}).")
            sys.exit(1)

        if db.query(Tenant).filter(Tenant.slug == args.tenant).first() is None:
            print(f"ERROR: no tenants row with slug {args.tenant!r} — create the tenant first.")
            sys.exit(1)

        password = getpass.getpass("Password: ")

        user = User(
            email=args.email,
            hashed_password=get_password_hash(password),
            user_type=UserType.ADMIN,
            is_superuser=True,
            is_active=True,
            tenant_id=args.tenant,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        print(f"Created superadmin: id={user.id} email={user.email}")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
