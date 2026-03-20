#!/usr/bin/env python3
"""
RYZE.ai Seed Cleanup Script
Removes all seeded demo data while preserving real records (users, waitlist).

Run BEFORE re-seeding:
    python seed_cleanup.py

Safe to run multiple times.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.core.database import SessionLocal

db = SessionLocal()

print("🧹 Cleaning up seed data...\n")

try:
    # chat_messages must go before chat_sessions (FK constraint)
    result = db.execute(text("DELETE FROM chat_messages"))
    db.commit()
    print(f"  ✓ Deleted {result.rowcount} chat messages")

    result = db.execute(text("DELETE FROM chat_sessions"))
    db.commit()
    print(f"  ✓ Deleted {result.rowcount} chat sessions")

    result = db.execute(text("DELETE FROM job_orders"))
    db.commit()
    print(f"  ✓ Deleted {result.rowcount} job orders")

    result = db.execute(text("DELETE FROM bookings"))
    db.commit()
    print(f"  ✓ Deleted {result.rowcount} bookings")

    result = db.execute(text("DELETE FROM candidates"))
    db.commit()
    print(f"  ✓ Deleted {result.rowcount} candidates")

    result = db.execute(text("DELETE FROM employer_profiles"))
    db.commit()
    print(f"  ✓ Deleted {result.rowcount} employer profiles")

    # Reset sequences so IDs start at 1 on next seed
    for table in ["chat_messages", "chat_sessions", "job_orders", "bookings", "candidates", "employer_profiles"]:
        db.execute(text(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1"))
    db.commit()
    print("\n  ✓ ID sequences reset to 1")

    print("\n✅ Cleanup complete. Ready to re-seed:")
    print("   python seed_full.py")
    print("   python run_backfill.py")

except Exception as e:
    db.rollback()
    print(f"\n❌ Cleanup failed: {e}")
    raise
finally:
    db.close()
