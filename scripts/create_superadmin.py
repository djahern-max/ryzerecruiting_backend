#!/usr/bin/env python3
"""
scripts/create_superadmin.py

Creates a RYZE platform-owner superadmin account (tenant_id='ryze').
No Tenant row is needed — deps.py treats the 'ryze' slug as always-active
without one. Refuses to run if a user with the given email already exists.

Usage (from project root):
    python scripts/create_superadmin.py --email you@ryze.ai
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
from app.models.user import User, UserType


def main():
    parser = argparse.ArgumentParser(description="Create a RYZE superadmin user.")
    parser.add_argument("--email", required=True, help="Email address for the new superadmin")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            print(f"ERROR: a user with email {args.email} already exists (id={existing.id}).")
            sys.exit(1)

        password = getpass.getpass("Password: ")

        user = User(
            email=args.email,
            hashed_password=get_password_hash(password),
            user_type=UserType.ADMIN,
            is_superuser=True,
            is_active=True,
            tenant_id="ryze",
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
