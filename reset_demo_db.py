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
    connections). You do NOT need to stop the API for this.
  * Tables are discovered by REFLECTING the live schema, so nothing is missed.
  * Delete order is computed from the FK graph MYSELF, considering only the FKs
    that actually constrain deletion order (NO ACTION / RESTRICT). ON DELETE
    SET NULL / CASCADE / SET DEFAULT edges impose no ordering, so they're
    excluded — which also dissolves the bookings<->candidates cycle cleanly.
  * Sequences: RESTART WITH 1 for tables that end up empty; setval(MAX(id)) for
    tables that keep rows (users). Preserved tables are left untouched.
  * DRY RUN by default. Prints the plan and exits. Pass --execute to run.
  * Everything happens in one transaction — any error rolls back with zero
    changes (as the first run demonstrated).

Usage:
    python reset_demo_db.py                            # dry run
    python reset_demo_db.py --execute --preserve tenants
    python reset_demo_db.py --execute                  # wipe tenants too

Full demo loop:
    python reset_demo_db.py --execute --preserve tenants
    python reseed_demo.py
    python diagnose_intelligence.py
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from collections import defaultdict, deque

from sqlalchemy import MetaData, text
from sqlalchemy.exc import SAWarning

sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal

# pgvector's 'vector' column type isn't known to core reflection — harmless here
# (we only DELETE rows, never touch column types), so silence the noise.
warnings.filterwarnings(
    "ignore", message="Did not recognize type 'vector'", category=SAWarning
)

PRESERVE_TABLES = {"webhook_logs", "alembic_version"}
KEEP_USER_ID = 1

# ON DELETE actions that force child-before-parent ordering. SET NULL / CASCADE /
# SET DEFAULT do not, so they're deliberately absent.
CONSTRAINING_ONDELETE = {None, "NO ACTION", "RESTRICT"}

BAR = "=" * 78


def looks_like_tenant_table(name: str) -> bool:
    n = name.lower()
    return "tenant" in n or "branding" in n


def build_delete_order(md: MetaData) -> list[str]:
    """
    Topologically sort tables so each child is deleted before its parent,
    considering ONLY constraining FKs (NO ACTION / RESTRICT). Edge child->parent
    means 'delete child before parent'. Returns table names, children first.
    """
    names = list(md.tables.keys())
    successors: dict[str, set[str]] = defaultdict(set)  # child -> {parents}
    indegree = {n: 0 for n in names}

    for table in md.tables.values():
        child = table.name
        for fk in table.foreign_key_constraints:
            ondelete = fk.ondelete
            normalized = ondelete.upper() if isinstance(ondelete, str) else ondelete
            if normalized not in CONSTRAINING_ONDELETE:
                continue  # SET NULL / CASCADE / SET DEFAULT — no ordering needed
            parent = fk.referred_table.name
            if parent == child or parent not in indegree:
                continue
            if parent not in successors[child]:
                successors[child].add(parent)
                indegree[parent] += 1

    # Kahn's algorithm — nodes with no one that must precede them go first.
    queue = deque(sorted(n for n in names if indegree[n] == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for parent in sorted(successors[node]):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)

    if len(order) != len(names):
        # Genuine cycle among constraining FKs (shouldn't happen here). Append
        # the rest; a bad order will safely roll back rather than corrupt.
        leftover = [n for n in names if n not in order]
        print(f"  [warn] unresolved constraining cycle among: {leftover}")
        order.extend(leftover)
    return order


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the wipe. Without this, dry run only.",
    )
    ap.add_argument(
        "--preserve",
        nargs="*",
        default=[],
        help="Additional table names to preserve (e.g. tenants)",
    )
    args = ap.parse_args()

    preserve = set(PRESERVE_TABLES) | set(args.preserve)

    db = SessionLocal()
    try:
        bind = db.get_bind()
        md = MetaData()
        md.reflect(bind=bind)

        delete_order = build_delete_order(md)

        print(BAR)
        print(
            "RESET PLAN"
            + (
                "  [DRY RUN — nothing will be deleted]"
                if not args.execute
                else "  [EXECUTE]"
            )
        )
        print(BAR)
        print(f"Preserve entirely : {sorted(preserve)}")
        print(f"Keep in users     : id = {KEEP_USER_ID} (all other users deleted)")
        print(f"Delete order      : {[n for n in delete_order if n not in preserve]}")
        print("-" * 78)

        tenant_warns = []
        for name in delete_order:
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
            print(f"  {name:<28} {action}")

        if tenant_warns:
            print("\n" + "!" * 78)
            print(
                f"HEADS UP: tenant/branding config tables set to DELETE: {tenant_warns}"
            )
            print(
                "If wiped, get_branding() for greenpath_recruiting falls back to defaults."
            )
            print("To keep them:  --preserve " + " ".join(tenant_warns))
            print("!" * 78)

        if not args.execute:
            print("\nDry run complete. Re-run with --execute to perform the wipe.")
            return

        # ---- Execute: one transaction, all-or-nothing ---------------------
        print("\nExecuting wipe…")
        for name in delete_order:
            if name in preserve:
                continue
            if name == "users":
                res = db.execute(
                    text('DELETE FROM "users" WHERE id <> :keep'),
                    {"keep": KEEP_USER_ID},
                )
            else:
                res = db.execute(text(f'DELETE FROM "{name}"'))
            print(f"  deleted {res.rowcount:>4} from {name}")

        # ---- Sequence resets ----------------------------------------------
        for name in delete_order:
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
            if name in preserve:
                tag = "  <- preserved"
            elif name == "users":
                tag = f"  <- kept id={KEEP_USER_ID}"
            else:
                tag = ""
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
