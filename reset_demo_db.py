#!/usr/bin/env python3
"""
reset_demo_db.py — wipe everything except webhook_logs and users.id = 1
=======================================================================

Clears the database back to a clean demo slate while preserving:
  * the webhook_logs table (your captured ground truth)
  * the user with id = 1 (your superuser login)

Design choices (all deliberate, matching the RYZE conventions):
  * ORDERED DELETE, children -> parents. Never TRUNCATE ... CASCADE, so this is
    safe to run while ryze-api is up (row-level locks don't block active
    connections; TRUNCATE's ACCESS EXCLUSIVE lock would). You do NOT need to
    stop the API for this.
  * Tables are discovered by REFLECTING the live schema, so nothing is missed
    (newsletter tables, contacts, chat_*, etc. all get picked up automatically).
  * The one booking<->candidate FK cycle resolves itself via your ON DELETE
    SET NULL constraints, so deletion order can't deadlock on it.
  * Sequences: RESTART WITH 1 for tables that end up empty; setval(MAX(id)) for
    tables that keep rows (users). webhook_logs is untouched, sequence included.
  * DRY RUN by default. Prints the exact plan and exits. Pass --execute to run.

Usage:
    python reset_demo_db.py                 # dry run — shows the plan, deletes nothing
    python reset_demo_db.py --execute       # actually wipe
    python reset_demo_db.py --execute --preserve tenants  # also keep the tenants table

Full demo loop:
    python reset_demo_db.py --execute       # wipe
    python reseed_demo.py                   # rebuild Renata + Walt from the snapshot
    python diagnose_intelligence.py         # confirm tenant alignment + retrieval
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import MetaData, text

sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal

# Never deleted. `alembic_version` is preserved so migration state is intact.
PRESERVE_TABLES = {"webhook_logs", "alembic_version"}

# The user row to keep. Everything else in `users` is deleted.
KEEP_USER_ID = 1

BAR = "=" * 78


def looks_like_tenant_table(name: str) -> bool:
    n = name.lower()
    return "tenant" in n or "branding" in n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="Actually perform the wipe. Without this, dry run only.")
    ap.add_argument("--preserve", nargs="*", default=[],
                    help="Additional table names to preserve (e.g. tenants)")
    args = ap.parse_args()

    preserve = set(PRESERVE_TABLES) | set(args.preserve)

    db = SessionLocal()
    try:
        bind = db.get_bind()

        # Reflect the live schema so we can't miss a table.
        md = MetaData()
        md.reflect(bind=bind)

        # children -> parents (reverse of dependency-sorted order).
        delete_order = list(reversed(md.sorted_tables))

        print(BAR)
        print("RESET PLAN" + ("  [DRY RUN — nothing will be deleted]" if not args.execute else "  [EXECUTE]"))
        print(BAR)
        print(f"Preserve entirely : {sorted(preserve)}")
        print(f"Keep in users     : id = {KEEP_USER_ID} (all other users deleted)")
        print("-" * 78)

        tenant_warns = []
        plan = []
        for tbl in delete_order:
            name = tbl.name
            try:
                count = db.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            except Exception:
                count = "?"

            if name in preserve:
                action = f"PRESERVE  (untouched, {count} rows)"
            elif name == "users":
                action = f"DELETE WHERE id <> {KEEP_USER_ID}  ({count} rows now)"
            else:
                action = f"DELETE ALL  ({count} rows)"
                if looks_like_tenant_table(name):
                    tenant_warns.append(name)
            plan.append((name, action))
            print(f"  {name:<28} {action}")

        if tenant_warns:
            print("\n" + "!" * 78)
            print("HEADS UP: these look like tenant/branding config tables and are set to")
            print(f"be DELETED: {tenant_warns}")
            print("If wiped, get_branding() for greenpath_recruiting falls back to defaults")
            print("after reseed. To keep them:  --preserve " + " ".join(tenant_warns))
            print("!" * 78)

        if not args.execute:
            print("\nDry run complete. Re-run with --execute to perform the wipe.")
            return

        # ---- Execute: one transaction, all-or-nothing ---------------------
        print("\nExecuting wipe…")
        deleted = {}
        for name, _ in plan:
            if name in preserve:
                continue
            if name == "users":
                res = db.execute(text(f'DELETE FROM "users" WHERE id <> :keep'),
                                 {"keep": KEEP_USER_ID})
            else:
                res = db.execute(text(f'DELETE FROM "{name}"'))
            deleted[name] = res.rowcount

        # ---- Sequence resets ----------------------------------------------
        for name, _ in plan:
            if name in preserve:
                continue
            seq = db.execute(
                text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": name}
            ).scalar()
            if not seq:
                continue
            remaining = db.execute(
                text(f'SELECT COALESCE(MAX(id), 0) FROM "{name}"')
            ).scalar()
            if remaining and remaining > 0:
                db.execute(text("SELECT setval(:s, :v)"), {"s": seq, "v": remaining})
            else:
                db.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))

        db.commit()

        # ---- Verify --------------------------------------------------------
        print("\n" + BAR)
        print("WIPE COMPLETE — post-state row counts")
        print("-" * 78)
        for name in sorted(md.tables.keys()):
            try:
                count = db.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            except Exception:
                count = "?"
            tag = "  <- preserved" if name in preserve else ""
            if name == "users":
                tag = f"  <- kept id={KEEP_USER_ID}"
            print(f"  {name:<28} {count} rows{tag}")
        print(BAR)
        print("\nNext:")
        print("  python reseed_demo.py")
        print("  python diagnose_intelligence.py")

    except Exception as e:
        db.rollback()
        print(f"\nERROR — transaction rolled back, no changes made: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
