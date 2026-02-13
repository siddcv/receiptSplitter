r"""
Test math-node persistence: save_final_costs() and save_math_data()

Seeds vision + interview prerequisite rows, then exercises:
  1. save_final_costs()            — basic insert
  2. save_final_costs() idempotency — re-insert same data
  3. save_math_data() orchestrator  — end-to-end via orchestrator
  4. Edge: empty participant_costs
  5. Edge: no participants in DB
  6. Edge: updated values overwrite

Run:
    .\rSplit\Scripts\python.exe test_math_persistence.py
"""

import sys, os, json
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

# ── ensure project root is on sys.path ──────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("USE_IN_MEMORY", "0")

from psycopg import connect
from app.database import get_database_url
from app.persistence import (
    save_receipt_data,
    save_receipt_items,
    save_participants,
    save_assignments,
    save_final_costs,
    save_math_data,
    save_audit_events,
    PersistenceError,
)

DSN = get_database_url()
THREAD = "test-math-persist-001"

passed = 0
failed = 0


def ok(label):
    global passed
    passed += 1
    print(f"   \u2705 {label}")


def fail(label):
    global failed
    failed += 1
    print(f"   \u274c {label}")


def check(condition, label):
    if condition:
        ok(label)
    else:
        fail(label)


def q(sql, params=None):
    """Quick single-result helper."""
    with connect(DSN) as c, c.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def cleanup():
    """Remove all test data."""
    with connect(DSN) as c, c.cursor() as cur:
        cur.execute("DELETE FROM final_costs WHERE receipt_id = %s", (THREAD,))
        cur.execute("DELETE FROM assignments WHERE item_id IN (SELECT id FROM receipt_items WHERE receipt_id = %s)", (THREAD,))
        cur.execute("DELETE FROM receipt_items WHERE receipt_id = %s", (THREAD,))
        cur.execute("DELETE FROM participants WHERE receipt_id = %s", (THREAD,))
        cur.execute("DELETE FROM audit_logs WHERE receipt_id = %s", (THREAD,))
        cur.execute("DELETE FROM receipts WHERE id = %s", (THREAD,))
        c.commit()


# ═══════════════════════════════════════════════════════════════════════
print("\U0001f9ea **TESTING MATH NODE PERSISTENCE**")
print("=" * 60)

# ── Seed prerequisites: receipt, items, participants, assignments ──
print("\U0001f527 Setup: seeding receipt + items + participants + assignments")
cleanup()

# Receipt
totals = {
    "subtotal": "30.00",
    "tax_total": "3.00",
    "tip_total": "6.00",
    "fees_total": "1.00",
    "grand_total": "40.00",
}
save_receipt_data(THREAD, totals)

# Items
items_raw = [
    {"name": "Caesar Salad", "price": "12.00", "quantity": "1"},
    {"name": "Pizza Margherita", "price": "15.00", "quantity": "1"},
    {"name": "Tiramisu", "price": "3.00", "quantity": "1"},
]
from app.graph.state import Item
items = [Item(name=i["name"], price=Decimal(i["price"]), quantity=Decimal(i["quantity"])) for i in items_raw]
save_receipt_items(THREAD, items)

# Participants
pmap = save_participants(THREAD, ["Alice", "Bob"])

# Assignments (Alice: salad + half tiramisu, Bob: pizza + half tiramisu)
assignments = [
    {"item_index": 0, "shares": [{"participant": "Alice", "fraction": "1.0"}]},
    {"item_index": 1, "shares": [{"participant": "Bob", "fraction": "1.0"}]},
    {"item_index": 2, "shares": [
        {"participant": "Alice", "fraction": "0.5"},
        {"participant": "Bob", "fraction": "0.5"},
    ]},
]
save_assignments(THREAD, assignments, pmap)
print("   \u2705 Seeded receipt, 3 items, 2 participants, 3 assignments\n")

# ── Test 1: save_final_costs() basic ─────────────────────────────────
print("\U0001f4b0 Test 1: save_final_costs()")

participant_costs = [
    {
        "participant": "Alice",
        "subtotal": "13.50",
        "tax_share": "1.35",
        "tip_share": "2.70",
        "fees_share": "0.45",
        "total_owed": "18.00",
        "item_costs": [
            {"item_index": 0, "item_name": "Caesar Salad", "cost": 12.0, "share_percentage": 100.0},
            {"item_index": 2, "item_name": "Tiramisu", "cost": 1.5, "share_percentage": 50.0},
        ],
    },
    {
        "participant": "Bob",
        "subtotal": "16.50",
        "tax_share": "1.65",
        "tip_share": "3.30",
        "fees_share": "0.55",
        "total_owed": "22.00",
        "item_costs": [
            {"item_index": 1, "item_name": "Pizza Margherita", "cost": 15.0, "share_percentage": 100.0},
            {"item_index": 2, "item_name": "Tiramisu", "cost": 1.5, "share_percentage": 50.0},
        ],
    },
]

rows = save_final_costs(THREAD, participant_costs)
check(rows == 2, f"Inserted {rows} rows (expected 2)")

db_rows = q(
    """
    SELECT p.name, fc.subtotal, fc.tax_share, fc.tip_share, fc.fees_share, fc.total_owed, fc.item_costs
    FROM final_costs fc
    JOIN participants p ON p.id = fc.participant_id
    WHERE fc.receipt_id = %s
    ORDER BY p.name
    """,
    (THREAD,),
)
check(len(db_rows) == 2, f"2 rows in DB (got {len(db_rows)})")
# Alice row
alice = db_rows[0]
check(alice[0] == "Alice", f"First row is Alice: {alice[0]}")
check(alice[1] == Decimal("13.50"), f"Alice subtotal = {alice[1]}")
check(alice[5] == Decimal("18.00"), f"Alice total_owed = {alice[5]}")
check(isinstance(alice[6], list) and len(alice[6]) == 2, f"Alice has 2 item_costs entries")
# Bob row
bob = db_rows[1]
check(bob[0] == "Bob", f"First row is Bob: {bob[0]}")
check(bob[1] == Decimal("16.50"), f"Bob subtotal = {bob[1]}")
check(bob[5] == Decimal("22.00"), f"Bob total_owed = {bob[5]}")
print()

# ── Test 2: save_final_costs() idempotency ──────────────────────────
print("\U0001f504 Test 2: save_final_costs() idempotency")
rows2 = save_final_costs(THREAD, participant_costs)
check(rows2 == 2, f"Re-insert returned {rows2} rows (expected 2)")
db_count = q("SELECT COUNT(*) FROM final_costs WHERE receipt_id = %s", (THREAD,))
check(db_count[0][0] == 2, f"Still exactly 2 rows in DB (got {db_count[0][0]})")
print()

# ── Test 3: save_final_costs() value update ─────────────────────────
print("\U0001f504 Test 3: save_final_costs() value update on re-insert")
updated_costs = [
    {**participant_costs[0], "total_owed": "19.00", "tip_share": "3.70"},
    participant_costs[1],
]
save_final_costs(THREAD, updated_costs)
alice_updated = q(
    """
    SELECT fc.total_owed, fc.tip_share
    FROM final_costs fc
    JOIN participants p ON p.id = fc.participant_id
    WHERE fc.receipt_id = %s AND p.name = 'Alice'
    """,
    (THREAD,),
)
check(alice_updated[0][0] == Decimal("19.00"), f"Alice total_owed updated to {alice_updated[0][0]}")
check(alice_updated[0][1] == Decimal("3.70"), f"Alice tip_share updated to {alice_updated[0][1]}")
print()

# ── Test 4: save_math_data() orchestrator ───────────────────────────
print("\U0001f680 Test 4: save_math_data() orchestrator")
# Clean final_costs + audit first to verify orchestrator re-creates them
with connect(DSN) as c, c.cursor() as cur:
    cur.execute("DELETE FROM final_costs WHERE receipt_id = %s", (THREAD,))
    cur.execute("DELETE FROM audit_logs WHERE receipt_id = %s", (THREAD,))
    c.commit()

state = {
    "thread_id": THREAD,
    "final_costs": {
        "participant_costs": participant_costs,
        "breakdown": {},
        "validation": {"valid": True},
        "calculated_at": str(datetime.now()),
    },
    "audit_log": [
        {
            "timestamp": datetime.now(timezone.utc),
            "node": "math",
            "message": "Cost calculation complete for 2 participants",
            "details": {"participant_count": 2},
        }
    ],
}
save_math_data(state)

fc_count = q("SELECT COUNT(*) FROM final_costs WHERE receipt_id = %s", (THREAD,))
check(fc_count[0][0] == 2, f"Orchestrator: {fc_count[0][0]} final_cost rows")

audit_count = q(
    "SELECT COUNT(*) FROM audit_logs WHERE receipt_id = %s AND node = 'math'",
    (THREAD,),
)
check(audit_count[0][0] >= 1, f"Orchestrator: {audit_count[0][0]} math audit log(s)")
print()

# ── Test 5: Edge — empty participant_costs ──────────────────────────
print("\u26a0\ufe0f  Test 5: Edge case — empty participant_costs")
rows_empty = save_final_costs(THREAD, [])
check(rows_empty == 0, f"Returned 0 for empty list: {rows_empty}")
print()

# ── Test 6: Edge — no participants in DB for thread ─────────────────
print("\u26a0\ufe0f  Test 6: Edge case — no participants in DB")
rows_nop = save_final_costs("nonexistent-thread-xyz", participant_costs)
check(rows_nop == 0, f"Returned 0 (no participants found): {rows_nop}")
print()

# ── Test 7: Edge — save_math_data with no final_costs ───────────────
print("\u26a0\ufe0f  Test 7: Edge case — save_math_data with no final_costs")
# Should log a warning and return without error
save_math_data({"thread_id": THREAD})
ok("No error raised for missing final_costs")
print()

# ── Cleanup ─────────────────────────────────────────────────────────
print("\U0001f9f9 Cleanup\u2026")
cleanup()

final_check = q(
    """
    SELECT
        (SELECT COUNT(*) FROM receipts WHERE id = %s),
        (SELECT COUNT(*) FROM participants WHERE receipt_id = %s),
        (SELECT COUNT(*) FROM receipt_items WHERE receipt_id = %s),
        (SELECT COUNT(*) FROM final_costs WHERE receipt_id = %s)
    """,
    (THREAD, THREAD, THREAD, THREAD),
)
r = final_check[0]
print(f"\U0001f4ca Final DB state:  receipts={r[0]}  participants={r[1]}  items={r[2]}  final_costs={r[3]}")

# ── Summary ─────────────────────────────────────────────────────────
print("=" * 60)
print(f"\U0001f3c1 Results:  \u2705 {passed} passed   \u274c {failed} failed")
if failed == 0:
    print("\U0001f389 All math persistence tests passed!")
else:
    print("\u26a0\ufe0f  Some tests failed — review output above.")
    sys.exit(1)
